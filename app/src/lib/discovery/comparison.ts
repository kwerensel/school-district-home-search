import { z } from "zod";
import { PurchasingPowerQuerySchema } from "@/lib/finance/server-data";
import type { DistrictPurchasingPower } from "@/lib/finance/server-data";
import type { TradeoffPayload } from "./tradeoff-narrative";

export const ComparisonQuerySchema = z
  .object({
    regionAId: z.number().int().positive(),
    regionBId: z.number().int().positive(),
    profile: PurchasingPowerQuerySchema,
  })
  .refine((data) => data.regionAId !== data.regionBId, "Choose two different districts");

export function comparisonPayload(
  a: DistrictPurchasingPower,
  b: DistrictPurchasingPower,
): TradeoffPayload {
  const dollars = (value: number) =>
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
      signDisplay: "exceptZero",
    }).format(value);
  const gaps = [
    [
      "Street-adjacent satellite NDVI",
      a.environmentMetrics.gviNdviStreet,
      b.environmentMetrics.gviNdviStreet,
      "",
    ],
    ["Tree coverage", a.environmentMetrics.treeCanopyPct, b.environmentMetrics.treeCanopyPct, "%"],
    [
      "Park access",
      a.environmentMetrics.parkAccess === null ? null : a.environmentMetrics.parkAccess * 100,
      b.environmentMetrics.parkAccess === null ? null : b.environmentMetrics.parkAccess * 100,
      "%",
    ],
    [
      "Walkability index",
      a.environmentMetrics.walkabilityIndex,
      b.environmentMetrics.walkabilityIndex,
      "",
    ],
  ] as const;
  return {
    regionA: { id: a.districtRegionId, name: a.districtName },
    regionB: { id: b.districtRegionId, name: b.districtName },
    maxPurchasePriceDelta: dollars(a.maxPurchasePrice - b.maxPurchasePrice),
    medianHomeValueDelta:
      a.environmentMetrics.medianHomeValue !== null && b.environmentMetrics.medianHomeValue !== null
        ? dollars(a.environmentMetrics.medianHomeValue - b.environmentMetrics.medianHomeValue)
        : null,
    commuteMinutesDelta:
      a.environmentMetrics.commuteMinutes !== null &&
      b.environmentMetrics.commuteMinutes !== null &&
      a.regionGroup === b.regionGroup
        ? `${(a.environmentMetrics.commuteMinutes - b.environmentMetrics.commuteMinutes).toFixed(1)} min`
        : null,
    topMetricGaps: gaps.flatMap(([label, av, bv, unit]) =>
      av === null || bv === null
        ? []
        : [
            {
              label,
              regionAValue: `${av.toFixed(label.includes("NDVI") ? 3 : 1)}${unit}`,
              regionBValue: `${bv.toFixed(label.includes("NDVI") ? 3 : 1)}${unit}`,
            },
          ],
    ),
    // No raw financial profile is stored in the cache key.
    profileBucket: "comparison-v1",
  };
}

export async function comparisonPayloadHash(payload: TradeoffPayload) {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
