import {
  buildDistrictsSql,
  buildListingMetricsSql,
  buildListingsSql,
  EMPTY_FEATURE_COLLECTION,
} from "./server-queries";
import type { DistrictFC, ListingFC, ListingMetricItem, ListingMetricsPayload } from "./types";
import type {
  DistrictQuery,
  ListingMetricsQuery,
  ListingQuery,
  SqlFragment,
} from "./server-queries";

export type QueryExecutor = (
  queryWithPlaceholders: string,
  params?: unknown[],
) => Promise<Array<{ geojson?: unknown; payload?: unknown }>>;

async function runGeoJsonQuery<T>(fragment: SqlFragment, execute: QueryExecutor): Promise<T> {
  const rows = await execute(fragment.text, fragment.values);
  return (rows[0]?.geojson ?? EMPTY_FEATURE_COLLECTION) as T;
}

export function fetchListingsGeoJson(
  input: ListingQuery,
  execute: QueryExecutor,
): Promise<ListingFC> {
  return runGeoJsonQuery<ListingFC>(buildListingsSql(input), execute);
}

export function fetchDistrictsGeoJson(
  input: DistrictQuery,
  execute: QueryExecutor,
): Promise<DistrictFC> {
  return runGeoJsonQuery<DistrictFC>(buildDistrictsSql(input), execute);
}

type RawMetricItem = {
  metric_key: string;
  name: string;
  value: number;
  units: string | null;
  grain: string;
  vintage: string;
  source: string;
  native_resolution: string | null;
  context: ListingMetricItem["context"];
};

function mapMetric(item: RawMetricItem): ListingMetricItem {
  return {
    metricKey: item.metric_key,
    name: item.name,
    value: Number(item.value),
    units: item.units,
    grain: item.grain,
    vintage: item.vintage,
    source: item.source,
    nativeResolution: item.native_resolution,
    context: item.context,
  };
}

export async function fetchListingMetricsPayload(
  input: ListingMetricsQuery,
  execute: QueryExecutor,
): Promise<ListingMetricsPayload | null> {
  const fragment = buildListingMetricsSql(input);
  const rows = await execute(fragment.text, fragment.values);
  const payload = rows[0]?.payload as
    | (Omit<ListingMetricsPayload, "metrics" | "tractMetrics"> & {
        metrics?: RawMetricItem[];
        tractMetrics?: RawMetricItem[];
      })
    | null
    | undefined;

  if (!payload?.listing) return null;
  return {
    listing: payload.listing,
    metrics: (payload.metrics ?? []).map(mapMetric),
    tractMetrics: (payload.tractMetrics ?? []).map(mapMetric),
  };
}
