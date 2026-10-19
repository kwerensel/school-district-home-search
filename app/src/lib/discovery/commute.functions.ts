import { createServerFn } from "@tanstack/react-start";
import { setResponseHeader } from "@tanstack/react-start/server";
import { sql } from "@/server/db";
import { CommuteQuerySchema, CommuteRoutingError, routeDistrictCommutes } from "./commute";
import type { CommuteResponse } from "./commute";

const cache = new Map<string, { expiresAt: number; result: Promise<CommuteResponse> }>();
const TTL = 24 * 60 * 60 * 1000;

export const getCommuteEstimates = createServerFn({ method: "POST" })
  .validator(CommuteQuerySchema)
  .handler(async ({ data }) => {
    setResponseHeader("Cache-Control", "private, no-store");
    const apiKey = process.env.ORS_API_KEY;
    if (!apiKey) {
      console.warn("Commute routing configuration unavailable", { keyPresent: false });
      throw new Error("Commute routing is not configured.");
    }
    // Exclude labels, caps and all financial fields: they do not affect routes.
    const key = JSON.stringify([
      data.regionGroup ?? "all",
      ...data.anchors.map((a) => [a.lng, a.lat, a.mode]),
    ]);
    const existing = cache.get(key);
    if (existing && existing.expiresAt > Date.now()) return existing.result;
    if (cache.size >= 64) cache.delete(cache.keys().next().value!);
    let stage: "database" | "routing" = "database";
    const result = (async () => {
      const rows = await sql`
        SELECT r.id, ST_X(ST_PointOnSurface(r.geom)) AS lng, ST_Y(ST_PointOnSurface(r.geom)) AS lat
        FROM regions r WHERE r.region_type='school_district'
          AND r.region_group IN ('pa-mainline','hudson-valley')
          AND (${data.regionGroup ?? null}::text IS NULL OR r.region_group=${data.regionGroup ?? null})
        ORDER BY r.id LIMIT 151
      `;
      stage = "routing";
      return routeDistrictCommutes(
        rows.map((row) => ({
          districtRegionId: Number(row.id),
          lat: Number(row.lat),
          lng: Number(row.lng),
        })),
        data.anchors,
        { apiKey },
      );
    })();
    cache.set(key, { expiresAt: Date.now() + TTL, result });
    try {
      return await result;
    } catch (error) {
      console.warn("Commute request failed", {
        stage,
        errorName: error instanceof Error ? error.name : "UnknownError",
        ...(error instanceof CommuteRoutingError ? { httpStatus: error.status } : {}),
      });
      cache.delete(key);
      throw new Error("Commute routing is unavailable. Please retry.");
    }
  });
