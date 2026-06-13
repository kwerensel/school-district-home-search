import { buildDistrictsSql, buildListingsSql, EMPTY_FEATURE_COLLECTION } from "./server-queries";
import type { DistrictFC, ListingFC } from "./types";
import type { DistrictQuery, ListingQuery, SqlFragment } from "./server-queries";

export type QueryExecutor = (
  queryWithPlaceholders: string,
  params?: unknown[],
) => Promise<Array<{ geojson?: unknown }>>;

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
