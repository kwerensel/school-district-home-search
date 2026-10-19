import { z } from "zod";
export const GeocodeQuerySchema = z.object({ address: z.string().trim().min(8).max(240) });
export const GeocodeCandidateSchema = z.object({
  label: z.string().min(1).max(160),
  lat: z.number().finite().min(-90).max(90),
  lng: z.number().finite().min(-180).max(180),
  accuracy: z.number().finite().min(0).max(1),
  source: z.string().max(300),
});
export type GeocodeCandidate = z.infer<typeof GeocodeCandidateSchema>;
export async function geocodeAddress(
  address: string,
  options: { apiKey: string; fetcher?: typeof fetch },
) {
  const data = GeocodeQuerySchema.parse({ address });
  const url = new URL("https://api.geocod.io/v2/geocode");
  url.searchParams.set("q", data.address);
  url.searchParams.set("country", "USA");
  // No fields/appends: one address is one lookup. Key is never part of a URL.
  const response = await (options.fetcher ?? fetch)(url, {
    headers: { Authorization: `Bearer ${options.apiKey}` },
    signal: AbortSignal.timeout(6000),
  });
  if (!response.ok) throw new Error("Address lookup unavailable. Enter coordinates or try later.");
  const body = (await response.json()) as { results?: unknown[] };
  if (!Array.isArray(body.results))
    throw new Error("Address lookup returned an incomplete response");
  const candidates: GeocodeCandidate[] = [];
  for (const value of body.results.slice(0, 5)) {
    const row = value as {
      formatted_address?: unknown;
      location?: { lat?: unknown; lng?: unknown };
      accuracy?: unknown;
      source?: unknown;
    };
    const parsed = GeocodeCandidateSchema.safeParse({
      label: row.formatted_address,
      lat: row.location?.lat,
      lng: row.location?.lng,
      accuracy: row.accuracy,
      source: typeof row.source === "string" ? row.source.slice(0, 300) : "Geocodio",
    });
    if (parsed.success) candidates.push(parsed.data);
  }
  return { candidates, provider: "Geocodio" as const };
}
