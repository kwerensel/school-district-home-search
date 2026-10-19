import { createServerFn } from "@tanstack/react-start";
import { setResponseHeader } from "@tanstack/react-start/server";
import { sql } from "@/server/db";
import { GeocodeQuerySchema, geocodeAddress } from "./geocode";

export const geocodeCommuteAddress = createServerFn({ method: "POST" })
  .validator(GeocodeQuerySchema)
  .handler(async ({ data }) => {
    setResponseHeader("Cache-Control", "private, no-store");
    if (!process.env.GEOCODIO_API_KEY || process.env.GEOCODIO_FREE_TIER_ONLY !== "true") {
      throw new Error("Address lookup is not configured. You can enter coordinates instead.");
    }
    // Atomic app-wide ceiling, including failed provider requests, leaves 1,500
    // of the provider's 2,500 daily free lookups as headroom for other account use.
    const quota = await sql`
      INSERT INTO geocoder_daily_usage (provider,usage_day,requests)
      VALUES ('geocodio',(now() AT TIME ZONE 'America/New_York')::date,1)
      ON CONFLICT (provider,usage_day) DO UPDATE SET requests=geocoder_daily_usage.requests+1
      WHERE geocoder_daily_usage.requests<1000 RETURNING requests
    `;
    if (!quota.length)
      throw new Error("Today's free address lookup allowance is used. Enter coordinates instead.");
    try {
      return await geocodeAddress(data.address, { apiKey: process.env.GEOCODIO_API_KEY });
    } catch {
      throw new Error("Address lookup unavailable. Enter coordinates or try later.");
    }
  });
