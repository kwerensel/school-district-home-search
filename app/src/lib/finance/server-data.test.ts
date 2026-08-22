import { describe, expect, it, vi } from "vitest";
import { buildDistrictTaxRateSql, fetchDistrictPurchasingPower } from "./server-data";

describe("finance server data", () => {
  it("builds effective-tax district SQL with optional region filtering", () => {
    const fragment = buildDistrictTaxRateSql({ regionGroup: "hudson-valley" });

    expect(fragment.values[1]).toBe("hudson-valley");
    expect(fragment.text).toContain("FROM district_metrics dm");
    expect(fragment.text).toContain("dm.metric_key = ANY($1)");
    expect(fragment.text).toContain("d.region_group = $2");
    expect(fragment.text).toContain("median_home_value");
    expect(fragment.text).toContain("light_pollution_radiance");
    expect(fragment.text).toContain("GROUP BY d.id, d.slug, d.name, d.region_group");
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
        canopy_height_m: "20",
        tree_canopy_pct: "55",
        median_home_value: "650000",
        walkability_index: "14",
        risk_index: "20",
        flood_sfha: "0.05",
        light_pollution_radiance: "8",
      },
      {
        district_region_id: 2,
        district_slug: "sd-mainline",
        district_name: "Main Line Example",
        region_group: "pa-mainline",
        effective_tax_rate: "0.026",
        canopy_height_m: "12",
        tree_canopy_pct: "35",
        median_home_value: "450000",
        walkability_index: "11",
        risk_index: "40",
        flood_sfha: "0.2",
        light_pollution_radiance: "15",
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
    expect(payload.districts[0].environmentMetrics).toMatchObject({
      canopyHeightM: 20,
      medianHomeValue: 650000,
      lightPollutionRadiance: 8,
    });
    expect(payload.districts[0].matchComponents).toMatchObject({
      affordability: expect.any(Number),
      green: expect.any(Number),
      walkability: expect.any(Number),
    });
    expect(payload.districts[0].affordabilityRatio).toBeGreaterThan(1);
    expect(payload.districts[0].matchScore).toBeGreaterThan(payload.districts[1].matchScore);
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
        canopy_height_m: null,
        tree_canopy_pct: null,
        median_home_value: null,
        walkability_index: null,
        risk_index: null,
        flood_sfha: null,
        light_pollution_radiance: null,
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

  it("lets profile weights overpower pure purchasing power when requested", async () => {
    const execute = vi.fn().mockResolvedValue([
      {
        district_region_id: 1,
        district_slug: "sd-expensive-green",
        district_name: "Green Example",
        region_group: "hudson-valley",
        effective_tax_rate: 0.028,
        canopy_height_m: 30,
        tree_canopy_pct: 70,
        median_home_value: 1_200_000,
        walkability_index: 18,
        risk_index: 10,
        flood_sfha: 0.02,
        light_pollution_radiance: 3,
      },
      {
        district_region_id: 2,
        district_slug: "sd-cheap-gray",
        district_name: "Gray Example",
        region_group: "hudson-valley",
        effective_tax_rate: 0.01,
        canopy_height_m: 4,
        tree_canopy_pct: 10,
        median_home_value: 400_000,
        walkability_index: 4,
        risk_index: 90,
        flood_sfha: 0.5,
        light_pollution_radiance: 50,
      },
    ]);

    const payload = await fetchDistrictPurchasingPower(
      {
        monthlyBudget: 5500,
        downPaymentAmount: 150000,
        environmentWeights: {
          affordability: 0,
          green: 5,
          walkability: 4,
          lowerRisk: 3,
          lowerFlood: 3,
          darkSkies: 2,
        },
      },
      execute,
    );

    expect(payload.districts[0].maxPurchasePrice).toBeLessThan(
      payload.districts[1].maxPurchasePrice,
    );
    expect(payload.districts[0].matchScore).toBeGreaterThan(payload.districts[1].matchScore);
  });

  it("uses median home value for affordability scoring when available", async () => {
    const execute = vi.fn().mockResolvedValue([
      {
        district_region_id: 1,
        district_slug: "sd-high-price-high-value",
        district_name: "High Price High Value",
        region_group: "hudson-valley",
        effective_tax_rate: 0.015,
        canopy_height_m: null,
        tree_canopy_pct: null,
        median_home_value: 1_500_000,
        walkability_index: null,
        risk_index: null,
        flood_sfha: null,
        light_pollution_radiance: null,
      },
      {
        district_region_id: 2,
        district_slug: "sd-lower-price-lower-value",
        district_name: "Lower Price Lower Value",
        region_group: "hudson-valley",
        effective_tax_rate: 0.025,
        canopy_height_m: null,
        tree_canopy_pct: null,
        median_home_value: 500_000,
        walkability_index: null,
        risk_index: null,
        flood_sfha: null,
        light_pollution_radiance: null,
      },
    ]);

    const payload = await fetchDistrictPurchasingPower(
      {
        monthlyBudget: 5500,
        downPaymentAmount: 150000,
        environmentWeights: {
          affordability: 10,
          green: 0,
          walkability: 0,
          lowerRisk: 0,
          lowerFlood: 0,
          darkSkies: 0,
        },
      },
      execute,
    );

    expect(payload.districts[0].maxPurchasePrice).toBeGreaterThan(
      payload.districts[1].maxPurchasePrice,
    );
    expect(payload.districts[0].affordabilityRatio).toBeLessThan(
      payload.districts[1].affordabilityRatio ?? 0,
    );
    expect(payload.districts[1].matchScore).toBeGreaterThan(payload.districts[0].matchScore);
  });
});
