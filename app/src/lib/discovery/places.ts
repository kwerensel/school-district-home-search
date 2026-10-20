import { z } from "zod";

export const PlaceSchema = z.object({
  slug: z.string(),
  name: z.string(),
  kind: z.enum(["school_district", "municipality", "census_tract"]),
  regionGroup: z.string(),
});
export type Place = z.infer<typeof PlaceSchema>;
export const PlaceSearchSchema = z
  .object({
    query: z.string().trim().min(2).max(120),
    regionGroup: z.enum(["all", "pa-mainline", "hudson-valley"]),
  })
  .strict();
const MetricSchema = z.object({
  metricKey: z.string(),
  name: z.string(),
  value: z.number().finite().nullable(),
  units: z.string().nullable(),
  source: z.string(),
  vintage: z.string(),
  nativeResolution: z.string().nullable(),
});
export type PlaceMetric = z.infer<typeof MetricSchema>;
export type PlaceContext = {
  place: Place;
  metrics: PlaceMetric[];
  tractContexts: Array<{
    place: Place;
    fractionOfTractWithinPlace: number;
    metrics: PlaceMetric[];
  }>;
};
export type PlaceAccess = {
  search: (query: string, regionGroup: string) => Promise<Place[]>;
  context: (slug: string, regionGroup: string) => Promise<PlaceContext | null>;
};
type Execute = (text: string, params: unknown[]) => Promise<Record<string, unknown>[]>;

const placeColumns = `r.slug,r.name,r.region_type AS kind,r.region_group AS "regionGroup"`;
export async function searchVerifiedPlaces(
  input: z.infer<typeof PlaceSearchSchema>,
  execute: Execute,
) {
  const data = PlaceSearchSchema.parse(input);
  return z.array(PlaceSchema).parse(
    await execute(
      `SELECT ${placeColumns} FROM regions r
    WHERE r.region_type IN ('school_district','municipality','census_tract')
      AND ($2='all' OR r.region_group=$2)
      AND (r.name ILIKE '%' || $1 || '%' OR r.slug=$1)
    ORDER BY CASE WHEN lower(r.name)=lower($1) THEN 0 ELSE 1 END,r.region_type,r.name,r.slug LIMIT 12`,
      [data.query, data.regionGroup],
    ),
  );
}

export async function loadVerifiedPlace(
  slug: string,
  regionGroup: string,
  execute: Execute,
): Promise<PlaceContext | null> {
  const row = (
    await execute(
      `SELECT ${placeColumns} FROM regions r WHERE r.slug=$1 AND ($2='all' OR r.region_group=$2)
    AND r.region_type IN ('school_district','municipality','census_tract')`,
      [slug, regionGroup],
    )
  )[0];
  if (!row) return null;
  const place = PlaceSchema.parse(row);
  const metrics = await placeMetrics(place.slug, place.kind === "school_district", execute);
  const tracts =
    place.kind === "municipality"
      ? await execute(
          `SELECT ${placeColumns}, ro.area_weight AS overlap
    FROM region_overlaps ro JOIN regions r ON r.id=ro.child_region_id JOIN regions parent ON parent.id=ro.parent_region_id
    WHERE parent.slug=$1 AND r.region_type='census_tract' AND ro.area_weight>0
    ORDER BY ro.area_weight DESC,r.slug LIMIT 6`,
          [slug],
        )
      : [];
  const tractContexts = await Promise.all(
    tracts.map(async (tract) => {
      const parsed = PlaceSchema.parse(tract);
      return {
        place: parsed,
        fractionOfTractWithinPlace: z.number().min(0).max(1.000001).parse(Number(tract.overlap)),
        metrics: await placeMetrics(parsed.slug, false, execute),
      };
    }),
  );
  return { place, metrics, tractContexts };
}

async function placeMetrics(slug: string, district: boolean, execute: Execute) {
  // Read only already-promoted values and stored overlap relationships. No new spatial joins or rollups.
  const rows = await execute(
    `SELECT m.metric_key AS "metricKey",md.name,m.value,md.units,md.source,m.vintage,md.native_resolution AS "nativeResolution"
    FROM ${district ? "district_metrics" : "region_metrics"} m
    JOIN regions r ON r.id=m.${district ? "district_region_id" : "region_id"}
    JOIN metric_definitions md ON md.metric_key=m.metric_key
    WHERE r.slug=$1 ORDER BY m.metric_key,m.vintage`,
    [slug],
  );
  return z.array(MetricSchema).parse(rows);
}
