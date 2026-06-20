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

export const ListingMetricsQuerySchema = z.object({
  listingId: z.number().int().positive(),
});

export type ListingQuery = z.infer<typeof ListingQuerySchema>;
export type DistrictQuery = z.infer<typeof DistrictQuerySchema>;
export type ListingMetricsQuery = z.infer<typeof ListingMetricsQuerySchema>;

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
          COALESCE(dq.good_district, false) AS good_district,
          canopy.value AS canopy_height_m_100m,
          flood.value AS flood_sfha
        FROM listings l
        JOIN school_districts d ON d.id = l.district_id
        LEFT JOIN district_quality dq ON dq.district_id = d.id
        LEFT JOIN listing_metrics canopy
          ON canopy.listing_id = l.id
         AND canopy.metric_key = 'canopy_height_m'
         AND canopy.grain = 'buffer_100m'
        LEFT JOIN listing_metrics flood
          ON flood.listing_id = l.id
         AND flood.metric_key = 'flood_sfha'
         AND flood.grain = 'point'
        WHERE ${where.join(" AND ")}
      ) row
    `,
    values,
  };
}

export function buildListingMetricsSql(input: ListingMetricsQuery): SqlFragment {
  return {
    text: `
      WITH target AS (
        SELECT
          l.id,
          l.address,
          l.city,
          l.zip,
          l.price,
          l.beds,
          l.baths,
          l.url,
          l.county AS county_name,
          l.region_slug,
          l.geom,
          d.name_display AS school_district,
          COALESCE(dq.good_district, false) AS good_district,
          canopy.value AS canopy_height_m_100m,
          flood.value AS flood_sfha
        FROM listings l
        JOIN school_districts d ON d.id = l.district_id
        LEFT JOIN district_quality dq ON dq.district_id = d.id
        LEFT JOIN listing_metrics canopy
          ON canopy.listing_id = l.id
         AND canopy.metric_key = 'canopy_height_m'
         AND canopy.grain = 'buffer_100m'
        LEFT JOIN listing_metrics flood
          ON flood.listing_id = l.id
         AND flood.metric_key = 'flood_sfha'
         AND flood.grain = 'point'
        WHERE l.id = $1
      ),
      tract AS (
        SELECT r.id
        FROM regions r
        JOIN target t
          ON r.region_group = t.region_slug
         AND ST_Contains(r.geom, t.geom)
        WHERE r.region_type = 'census_tract'
        ORDER BY ST_Area(r.geom::geography)
        LIMIT 1
      ),
      listing_metric_rows AS (
        SELECT
          lm.metric_key,
          md.name,
          lm.value,
          md.units,
          lm.grain,
          lm.vintage,
          md.source,
          md.native_resolution,
          CASE
            WHEN lm.metric_key = 'flood_sfha' AND lm.grain = 'point' THEN 'property'
            WHEN lm.grain IN ('buffer_100m', 'buffer_500m') THEN 'street'
            ELSE 'neighborhood'
          END AS context
        FROM listing_metrics lm
        JOIN metric_definitions md ON md.metric_key = lm.metric_key
        WHERE lm.listing_id = $1
      ),
      tract_metric_rows AS (
        SELECT
          rm.metric_key,
          md.name,
          rm.value,
          md.units,
          'census_tract' AS grain,
          rm.vintage,
          md.source,
          md.native_resolution,
          'neighborhood' AS context
        FROM region_metrics rm
        JOIN metric_definitions md ON md.metric_key = rm.metric_key
        JOIN tract ON tract.id = rm.region_id
        WHERE NOT EXISTS (
          SELECT 1
          FROM listing_metrics lm
          WHERE lm.listing_id = $1
            AND lm.metric_key = rm.metric_key
        )
      )
      SELECT json_build_object(
        'listing', (
          SELECT to_jsonb(t) - 'geom' - 'region_slug'
          FROM target t
        ),
        'metrics', COALESCE((
          SELECT json_agg(row_to_json(m) ORDER BY m.metric_key, m.grain)
          FROM listing_metric_rows m
        ), '[]'::json),
        'tractMetrics', COALESCE((
          SELECT json_agg(row_to_json(m) ORDER BY m.metric_key)
          FROM tract_metric_rows m
        ), '[]'::json)
      ) AS payload
    `,
    values: [input.listingId],
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
          d.nces_geoid,
          dr.slug AS district_slug,
          dr.region_group,
          d.name_display AS name,
          COALESCE(dq.good_district, false) AS good_district
        FROM school_districts d
        LEFT JOIN district_quality dq ON dq.district_id = d.id
        LEFT JOIN regions dr
          ON dr.district_id = d.id
         AND dr.region_type = 'school_district'
        WHERE ${where.join(" AND ")}
      ) row
    `,
    values,
  };
}
