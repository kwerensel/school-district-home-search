import { describe, expect, it, vi } from "vitest";
import { fetchDistrictPurchasingPower } from "@/lib/finance/server-data";
import { ComparisonQuerySchema, comparisonPayload, comparisonPayloadHash } from "./comparison";

async function districts() {
  const result = await fetchDistrictPurchasingPower(
    { monthlyBudget: 5500 },
    vi.fn().mockResolvedValue([
      {
        district_region_id: 1,
        district_slug: "first",
        district_name: "First",
        region_group: "pa-mainline",
        effective_tax_rate: 0.01,
        tree_canopy_pct: 60,
        park_access: 0.65,
        walkability_index: 12,
        commute_minutes: 30,
        median_home_value: 600000,
      },
      {
        district_region_id: 2,
        district_slug: "second",
        district_name: "Second",
        region_group: "pa-mainline",
        effective_tax_rate: 0.02,
        tree_canopy_pct: 40,
        park_access: 0.2,
        walkability_index: 8,
        commute_minutes: 45,
        median_home_value: 500000,
      },
    ]),
  );
  return result.districts;
}

describe("district comparison", () => {
  it("accepts only distinct trusted identifiers and a valid profile", () => {
    expect(
      ComparisonQuerySchema.safeParse({
        regionAId: 1,
        regionBId: 1,
        profile: { monthlyBudget: 5000 },
      }).success,
    ).toBe(false);
    expect(
      ComparisonQuerySchema.safeParse({
        regionAId: -1,
        regionBId: 2,
        profile: { monthlyBudget: 5000 },
      }).success,
    ).toBe(false);
    expect(
      ComparisonQuerySchema.safeParse({ regionAId: 1, regionBId: 2, profile: { monthlyBudget: 0 } })
        .success,
    ).toBe(false);
  });

  it("subtracts the second district from the first and converts land shares to percentages", async () => {
    const [a, b] = await districts();
    const payload = comparisonPayload(a, b);
    expect(payload.maxPurchasePriceDelta).toMatch(/^\+\$/);
    expect(payload.medianHomeValueDelta).toBe("+$100,000");
    expect(payload.commuteMinutesDelta).toBe("-15.0 min");
    expect(payload.topMetricGaps).toContainEqual({
      label: "Park access",
      regionAValue: "65.0%",
      regionBValue: "20.0%",
    });
    expect(comparisonPayload(b, a).medianHomeValueDelta).toBe("-$100,000");
  });

  it("omits unavailable values and comparisons between different commute anchors", async () => {
    const [a, b] = await districts();
    b.regionGroup = "hudson-valley";
    b.environmentMetrics.medianHomeValue = null;
    b.environmentMetrics.treeCanopyPct = null;
    const payload = comparisonPayload(a, b);
    expect(payload.commuteMinutesDelta).toBeNull();
    expect(payload.medianHomeValueDelta).toBeNull();
    expect(payload.topMetricGaps.some((gap) => gap.label === "Tree coverage")).toBe(false);
  });

  it("keys cached explanations to the exact ordered comparison values", async () => {
    const [a, b] = await districts();
    const payload = comparisonPayload(a, b);
    const hash = await comparisonPayloadHash(payload);
    expect(await comparisonPayloadHash({ ...payload })).toBe(hash);
    expect(await comparisonPayloadHash(comparisonPayload(b, a))).not.toBe(hash);
    expect(await comparisonPayloadHash({ ...payload, maxPurchasePriceDelta: "+$1" })).not.toBe(
      hash,
    );
    expect(hash).toMatch(/^[a-f0-9]{64}$/);
  });
});
