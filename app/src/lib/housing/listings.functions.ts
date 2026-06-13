import { createServerFn } from "@tanstack/react-start";
import { setResponseHeader } from "@tanstack/react-start/server";
import { sql } from "@/server/db";
import { DistrictQuerySchema, ListingQuerySchema } from "./server-queries";
import { fetchDistrictsGeoJson, fetchListingsGeoJson } from "./server-data";
import type { DistrictFC, ListingFC } from "./types";

function setGeoJsonCacheHeaders() {
  setResponseHeader("Cache-Control", "public, max-age=3600");
}

export const getListings = createServerFn({ method: "GET" })
  .validator(ListingQuerySchema)
  .handler(async ({ data }): Promise<ListingFC> => {
    setGeoJsonCacheHeaders();
    return fetchListingsGeoJson(data, (text, values) => sql.query(text, values));
  });

export const getDistricts = createServerFn({ method: "GET" })
  .validator(DistrictQuerySchema)
  .handler(async ({ data }): Promise<DistrictFC> => {
    setGeoJsonCacheHeaders();
    return fetchDistrictsGeoJson(data, (text, values) => sql.query(text, values));
  });
