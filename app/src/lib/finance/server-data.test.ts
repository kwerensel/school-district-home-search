import { describe, expect, it, vi } from "vitest";
import { buildDistrictTaxRateSql, fetchDistrictPurchasingPower } from "./server-data";

describe("finance server data", () => {
  it("builds effective-tax district SQL with optional region filtering", () => {
    const fragment = buildDistrictTaxRateSql({ regionGroup: "hudson-valley" });

    expect(fragment.values).toEqual(["hudson-valley"]);
    expect(fragment.text).toContain("FROM district_metrics dm");
    expect(fragment.text).toContain("dm.metric_key = 'effective_tax_rate'");
    expect(fragment.text).toContain("d.region_group = $1");
    expect(fragment.text).toContain("ORDER BY d.region_group, d.name");
  });

  it("maps live district tax rows through the pure purchasing-power engine", async () => {
    const execute = vi.fn().mockResolvedValue([
      {
        district_region_id: 1,
        district_slug: "sd-hudson",
        district_name: "Hudson Example",
        region_group: "hudson-valley",
        effective_tax_rate: "0.018",
      },
      {
        district_region_id: 2,
        district_slug: "sd-mainline",
        district_name: "Main Line Example",
        region_group: "pa-mainline",
        effective_tax_rate: "0.026",
      },
    ]);

    const payload = await fetchDistrictPurchasingPower(
      {
        monthlyBudget: 5500,
        downPaymentAmount: 150000,
        baseAnnualRate: 0.065,
        creditBand: "good",
      },
      execute,
    );

    expect(execute).toHaveBeenCalledTimes(1);
    expect(payload.districts).toHaveLength(2);
    expect(payload.districts[0]).toMatchObject({
      districtRegionId: 1,
      districtSlug: "sd-hudson",
      effectiveTaxRate: 0.018,
      bindingBound: "budget",
    });
    expect(payload.districts[0].maxPurchasePrice).toBeGreaterThan(
      payload.districts[1].maxPurchasePrice,
    );
  });

  it("returns DTI-limited district purchasing power when income is the tighter bound", async () => {
    const execute = vi.fn().mockResolvedValue([
      {
        district_region_id: 1,
        district_slug: "sd-hudson",
        district_name: "Hudson Example",
        region_group: "hudson-valley",
        effective_tax_rate: 0.018,
      },
    ]);

    const payload = await fetchDistrictPurchasingPower(
      {
        monthlyBudget: 5500,
        downPaymentAmount: 150000,
        grossMonthlyIncome: 11000,
        monthlyDebt: 900,
        maxDti: 0.36,
      },
      execute,
    );

    expect(payload.districts[0].bindingBound).toBe("dti");
    expect(payload.districts[0].dtiLimitedPrice).not.toBeNull();
    expect(payload.districts[0].maxPurchasePrice).toBe(payload.districts[0].dtiLimitedPrice);
  });
});
