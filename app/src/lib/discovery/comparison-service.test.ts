import { describe, expect, it, vi } from "vitest";
import { fetchDistrictPurchasingPower } from "@/lib/finance/server-data";
import { deterministicTradeoffNarrative } from "./tradeoff-narrative";
import { resolveDistrictComparison } from "./comparison-service";

async function fixture() {
  const { districts } = await fetchDistrictPurchasingPower(
    { monthlyBudget: 5000 },
    vi.fn().mockResolvedValue([
      {
        district_region_id: 1,
        district_slug: "first",
        district_name: "First",
        region_group: "pa-mainline",
        effective_tax_rate: 0.01,
      },
      {
        district_region_id: 2,
        district_slug: "second",
        district_name: "Second",
        region_group: "pa-mainline",
        effective_tax_rate: 0.02,
      },
    ]),
  );
  return {
    districts,
    readCache: vi.fn().mockResolvedValue(null),
    writeCache: vi.fn().mockResolvedValue(undefined),
  };
}
const query = {
  regionAId: 1,
  regionBId: 2,
  profile: { monthlyBudget: 5000, grossMonthlyIncome: 20000, monthlyDebt: 1000 },
};

describe("guarded comparison endpoint service", () => {
  it("rejects unknown or duplicate district IDs before touching the narrative cache or generator", async () => {
    const dependencies = { ...(await fixture()), generate: vi.fn() };
    await expect(
      resolveDistrictComparison({ ...query, regionBId: 999 }, dependencies),
    ).rejects.toThrow("available districts");
    await expect(
      resolveDistrictComparison({ ...query, regionBId: 1 }, dependencies),
    ).rejects.toThrow("different districts");
    expect(dependencies.readCache).not.toHaveBeenCalled();
    expect(dependencies.generate).not.toHaveBeenCalled();
  });

  it("returns deterministic copy on cache read failure and ignores poisoned template copy", async () => {
    const dependencies = await fixture();
    dependencies.readCache.mockRejectedValueOnce(new Error("cache offline"));
    const failed = await resolveDistrictComparison(query, dependencies);
    expect(failed.source).toBe("template");
    expect(failed.narrative).toBe(deterministicTradeoffNarrative(failed.payload));
    dependencies.readCache.mockResolvedValue({
      narrative: "Fabricated 999999 results",
      source: "template",
    });
    const poisoned = await resolveDistrictComparison(query, dependencies);
    expect(poisoned.narrative).toBe(deterministicTradeoffNarrative(poisoned.payload));
  });

  it("checks cached Claude numerals and preserves truthful cache provenance", async () => {
    const dependencies = await fixture();
    dependencies.readCache.mockResolvedValue({
      narrative: "First is 987654321 minutes faster.",
      source: "claude",
    });
    const poisoned = await resolveDistrictComparison(query, dependencies);
    expect(poisoned.source).toBe("template");
    expect(poisoned.narrative).not.toContain("987654321");
    dependencies.readCache.mockResolvedValue({
      narrative: "Compare the district estimates with your housing priorities.",
      source: "claude",
    });
    expect((await resolveDistrictComparison(query, dependencies)).source).toBe("claude");
    expect(dependencies.writeCache).not.toHaveBeenCalled();
  });

  it("falls back on generator timeout and survives a cache write failure", async () => {
    const dependencies = {
      ...(await fixture()),
      generate: vi.fn().mockRejectedValue(new DOMException("Timed out", "TimeoutError")),
    };
    dependencies.writeCache.mockRejectedValue(new Error("cache offline"));
    const result = await resolveDistrictComparison(query, dependencies);
    expect(result.source).toBe("template");
    expect(result.narrative).toBe(deterministicTradeoffNarrative(result.payload));
  });

  it("guards fresh generated numerals and never sends raw financial inputs for generation", async () => {
    const dependencies = {
      ...(await fixture()),
      generate: vi.fn().mockResolvedValue({
        narrative: "First provides $99999999 more buying power.",
        source: "claude",
      }),
    };
    const result = await resolveDistrictComparison(query, dependencies);
    expect(result.source).toBe("template");
    expect(dependencies.generate).toHaveBeenCalledWith(result.payload);
    const serialized = JSON.stringify(dependencies.generate.mock.calls[0][0]);
    expect(serialized).not.toContain("grossMonthlyIncome");
    expect(serialized).not.toContain("monthlyDebt");
    expect(result.payload.maxPurchasePriceDelta).not.toBe("+$99999999");
  });

  it("changes the cache hash when deterministic displayed values or district order change", async () => {
    const dependencies = await fixture();
    await resolveDistrictComparison(query, dependencies);
    const original = dependencies.readCache.mock.calls[0][0].hash;
    dependencies.districts[0].maxPurchasePrice += 1000;
    await resolveDistrictComparison(query, dependencies);
    expect(dependencies.readCache.mock.calls[1][0].hash).not.toBe(original);
    await resolveDistrictComparison({ ...query, regionAId: 2, regionBId: 1 }, dependencies);
    expect(dependencies.readCache.mock.calls[2][0].hash).not.toBe(
      dependencies.readCache.mock.calls[1][0].hash,
    );
  });
});
