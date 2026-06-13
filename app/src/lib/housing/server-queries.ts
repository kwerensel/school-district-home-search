import { z } from "zod";

export const BboxSchema = z
  .tuple([z.number(), z.number(), z.number(), z.number()])
  .refine(([west, south, east, north]) => west < east && south < north, {
    message: "bbox must be [west, south, east, north]",
  });

export const ListingQuerySchema = z
  .object({
    bbox: BboxSchema.optional(),
    maxPrice: z.number().positive().optional(),
    minBeds: z.number().int().min(0).optional(),
    minBaths: z.number().min(0).optional(),
    goodOnly: z.boolean().optional(),
    districtSlug: z.string().min(1).optional(),
  })
  .default({});

export const DistrictQuerySchema = z
  .object({
    bbox: BboxSchema.optional(),
    state: z.enum(["PA", "NY"]).optional(),
    simplifyTolerance: z.number().min(0).max(0.1).default(0.001),
  })
  .default({});

export type ListingQuery = z.infer<typeof ListingQuerySchema>;
export type DistrictQuery = z.infer<typeof DistrictQuerySchema>;

export const EMPTY_FEATURE_COLLECTION = {
  type: "FeatureCollection",
  features: [],
} as const;

export type SqlFragment = {
  text: string;
  values: unknown[];
};

export function buildListingsSql(input: ListingQuery): SqlFragment {
  const values: unknown[] = [];
  const where = ["l.district_id IS NOT NULL"];

  if (input.bbox) {
    values.push(...input.bbox);
    where.push(
      `l.geom && ST_MakeEnvelope($${values.length - 3}, $${values.length - 2}, $${values.length - 1}, $${values.length}, 4326)`,
    );
  }

  if (input.maxPrice !== undefined) {
    values.push(input.maxPrice);
    where.push(`l.price <= $${values.length}`);
  }

  if (input.minBeds !== undefined) {
    values.push(input.minBeds);
    where.push(`l.beds >= $${values.length}`);
  }

  if (input.minBaths !== undefined) {
    values.push(input.minBaths);
    where.push(`l.baths >= $${values.length}`);
  }

  if (input.goodOnly) {
    where.push("COALESCE(dq.good_district, false) = true");
  }

  if (input.districtSlug) {
    values.push(input.districtSlug);
    where.push(`d.nces_geoid = $${values.length}`);
  }

  return {
    text: `
      SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(json_agg(ST_AsGeoJSON(row)::json ORDER BY row.id), '[]'::json)
      ) AS geojson
      FROM (
        SELECT
          l.id,
          l.geom,
          l.address,
          l.city,
          l.state,
          l.zip,
          l.price,
          l.beds,
          l.baths,
          l.url,
          d.name_display AS school_district,
          l.county AS county_name,
          COALESCE(dq.good_district, false) AS good_district
        FROM listings l
        JOIN school_districts d ON d.id = l.district_id
        LEFT JOIN district_quality dq ON dq.district_id = d.id
        WHERE ${where.join(" AND ")}
      ) row
    `,
    values,
  };
}

export function buildDistrictsSql(input: DistrictQuery): SqlFragment {
  const values: unknown[] = [input.simplifyTolerance];
  const where = ["EXISTS (SELECT 1 FROM listings l WHERE l.district_id = d.id)"];

  if (input.bbox) {
    values.push(...input.bbox);
    where.push(
      `d.geom && ST_MakeEnvelope($${values.length - 3}, $${values.length - 2}, $${values.length - 1}, $${values.length}, 4326)`,
    );
  }

  if (input.state) {
    values.push(input.state);
    where.push(`d.state = $${values.length}`);
  }

  return {
    text: `
      SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(json_agg(ST_AsGeoJSON(row)::json ORDER BY row.name), '[]'::json)
      ) AS geojson
      FROM (
        SELECT
          d.id,
          ST_SimplifyPreserveTopology(d.geom, $1) AS geom,
          d.name_display AS name,
          COALESCE(dq.good_district, false) AS good_district
        FROM school_districts d
        LEFT JOIN district_quality dq ON dq.district_id = d.id
        WHERE ${where.join(" AND ")}
      ) row
    `,
    values,
  };
}
