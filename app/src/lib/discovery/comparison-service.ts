import { ComparisonQuerySchema, comparisonPayload, comparisonPayloadHash } from "./comparison";
import {
  deterministicTradeoffNarrative,
  guardedTradeoffNarrative,
  type TradeoffPayload,
} from "./tradeoff-narrative";
import type { DistrictPurchasingPower } from "@/lib/finance/server-data";
import type { z } from "zod";

type Narrative = { narrative: string; source: "template" | "claude" };
type CacheKey = { payload: TradeoffPayload; hash: string };
type ComparisonDependencies = {
  districts: DistrictPurchasingPower[];
  readCache: (key: CacheKey) => Promise<{ narrative: unknown; source: unknown } | null>;
  writeCache: (key: CacheKey, narrative: Narrative) => Promise<void>;
  generate?: (payload: TradeoffPayload) => Promise<Narrative>;
};

export async function resolveDistrictComparison(
  queryInput: z.infer<typeof ComparisonQuerySchema>,
  dependencies: ComparisonDependencies,
) {
  const query = ComparisonQuerySchema.parse(queryInput);
  const a = dependencies.districts.find(
    (district) => district.districtRegionId === query.regionAId,
  );
  const b = dependencies.districts.find(
    (district) => district.districtRegionId === query.regionBId,
  );
  if (!a || !b) throw new Error("Choose two available districts in this comparison area.");
  // Finance and all displayed differences come from deterministic server results.
  // Only this structured payload, never the financial profile, reaches generation.
  const payload = comparisonPayload(a, b);
  const key = { payload, hash: await comparisonPayloadHash(payload) };
  const fallback: Narrative = {
    narrative: deterministicTradeoffNarrative(payload),
    source: "template",
  };
  try {
    const cached = await dependencies.readCache(key);
    if (cached && typeof cached.narrative === "string") {
      if (cached.source === "template") return { payload, ...fallback };
      if (cached.source === "claude")
        return { payload, ...guardedTradeoffNarrative(cached.narrative, payload) };
    }
  } catch {
    // Cache availability must never gate the deterministic comparison.
    return { payload, ...fallback };
  }
  let result = fallback;
  if (dependencies.generate) {
    try {
      const candidate = await dependencies.generate(payload);
      result =
        candidate.source === "template"
          ? fallback
          : guardedTradeoffNarrative(candidate.narrative, payload);
    } catch {
      /* Timeouts and provider failures retain deterministic copy. */
    }
  }
  try {
    await dependencies.writeCache(key, result);
  } catch {
    /* Best-effort cache. */
  }
  return { payload, ...result };
}
