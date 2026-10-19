import { z } from "zod";

import { CommuteAnchorSchema } from "./profile";
export { CommuteAnchorSchema } from "./profile";
export const CommuteQuerySchema = z.object({
  anchors: z.array(CommuteAnchorSchema).min(1).max(2),
  regionGroup: z.enum(["pa-mainline", "hudson-valley"]).optional(),
});
export type CommuteAnchor = z.infer<typeof CommuteAnchorSchema>;
export type CommuteOrigin = { districtRegionId: number; lat: number; lng: number };
export type CommuteEstimate = {
  minutes: number | null;
  status: "routed" | "unroutable";
  sourceSnapM: number | null;
  destinationSnapM: number | null;
};
export type CommuteDistrict = { districtRegionId: number; anchors: CommuteEstimate[] };
export type CommuteResponse = {
  districts: CommuteDistrict[];
  provenance: {
    origin: "district representative point";
    mode: "driving-car";
    traffic: "No live traffic or arrival-time prediction";
    computedAt: string;
    engine: string | null;
  };
};

export function withinCommuteCaps(district: CommuteDistrict, anchors: CommuteAnchor[]) {
  return (
    anchors.length > 0 &&
    district.anchors.length === anchors.length &&
    district.anchors.every(
      (estimate, index) =>
        estimate.status === "routed" &&
        estimate.minutes !== null &&
        estimate.minutes <= anchors[index].maxMinutes,
    )
  );
}

export class CommuteRoutingError extends Error {
  constructor(readonly status: number) {
    super("Commute routing is unavailable. Try again later.");
    this.name = "CommuteRoutingError";
  }
}

export async function routeDistrictCommutes(
  origins: CommuteOrigin[],
  anchors: CommuteAnchor[],
  options: { apiKey: string; fetcher?: typeof fetch },
): Promise<CommuteResponse> {
  const parsed = z.array(CommuteAnchorSchema).min(1).max(2).parse(anchors);
  if (origins.length > 150) throw new Error("Commute comparison area exceeds the request limit");
  const districts: CommuteDistrict[] = [];
  let engine: string | null = null;
  for (let start = 0; start < origins.length; start += 49) {
    const batch = origins.slice(start, start + 49);
    const locations = [
      ...batch.map((origin) => [origin.lng, origin.lat]),
      ...parsed.map((anchor) => [anchor.lng, anchor.lat]),
    ];
    const response = await (options.fetcher ?? fetch)(
      "https://api.heigit.org/openrouteservice/v2/matrix/driving-car",
      {
        method: "POST",
        signal: AbortSignal.timeout(12000),
        headers: { "Content-Type": "application/json", Authorization: options.apiKey },
        body: JSON.stringify({
          locations,
          sources: batch.map((_, index) => index),
          destinations: parsed.map((_, index) => batch.length + index),
          metrics: ["duration"],
        }),
      },
    );
    if (!response.ok) throw new CommuteRoutingError(response.status);
    const body = (await response.json()) as {
      durations?: Array<Array<number | null>>;
      sources?: Array<{ snapped_distance?: number }>;
      destinations?: Array<{ snapped_distance?: number }>;
      metadata?: { engine?: { version?: string } };
    };
    if (
      !body.durations ||
      body.durations.length !== batch.length ||
      body.durations.some((row) => !Array.isArray(row) || row.length !== parsed.length)
    ) {
      throw new Error("Commute routing returned an incomplete matrix");
    }
    engine = body.metadata?.engine?.version ?? engine;
    batch.forEach((origin, index) =>
      districts.push({
        districtRegionId: origin.districtRegionId,
        anchors: parsed.map((_, anchorIndex) => {
          const seconds = body.durations![index][anchorIndex];
          const valid = typeof seconds === "number" && Number.isFinite(seconds) && seconds >= 0;
          return {
            minutes: valid ? seconds / 60 : null,
            status: valid ? "routed" : "unroutable",
            sourceSnapM: body.sources?.[index]?.snapped_distance ?? null,
            destinationSnapM: body.destinations?.[anchorIndex]?.snapped_distance ?? null,
          };
        }),
      }),
    );
  }
  return {
    districts,
    provenance: {
      origin: "district representative point",
      mode: "driving-car",
      traffic: "No live traffic or arrival-time prediction",
      computedAt: new Date().toISOString(),
      engine,
    },
  };
}
