import { describe, expect, it } from "vitest";
import { addMatchScores } from "./match-scoring";
import { fetchDistrictPurchasingPower } from "./server-data";

async function fixtures() {
  const payload = await fetchDistrictPurchasingPower(
    { monthlyBudget: 5500, downPaymentAmount: 150000, baseAnnualRate: 0.065 },
    async () =>
      [10, 20, 100].map((value, index) => ({
        district_region_id: index + 1,
        district_slug: `sd-${index}`,
        district_name: `District ${index}`,
        region_group: "pa-mainline",
        effective_tax_rate: 0.02,
        tree_canopy_pct: value,
        canopy_height_m: null,
        risk_index: value,
        median_home_value: null,
        walkability_index: null,
        flood_sfha: null,
        light_pollution_radiance: null,
        park_access: null,
        transit_access: null,
        commute_minutes: null,
        aqi_annual_mean: null,
        noise_mean_dba: null,
        noise_pct_over_55: null,
        noise_siren_density: null,
        noise_nightlife_density: null,
        noise_industrial_land_pct: null,
        noise_freight_rail_density: null,
        archetype_label: null,
        archetype_description: null,
      })),
  );
  return payload.districts;
}

describe("comparison scope scoring", () => {
  it("recalculates shortlist factors without the regional outlier or mutating facts", async () => {
    const districts = await fixtures();
    const original = structuredClone(districts);
    const pair = addMatchScores(districts.slice(0, 2), { green: 10, affordability: 0 });
    expect(districts[1].matchComponents.green).toBeCloseTo(100 / 9);
    expect(pair.map((district) => district.matchComponents.green)).toEqual([0, 100]);
    expect(pair.map((district) => district.matchComponents.lowerRisk)).toEqual([100, 0]);
    expect(pair[1].maxPurchasePrice).toBe(districts[1].maxPurchasePrice);
    expect(districts).toEqual(original);
  });

  it("keeps ties neutral, missing values unknown, and singleton comparisons neutral", async () => {
    const districts = await fixtures();
    const pair = addMatchScores(districts.slice(0, 2), {});
    expect(pair.map((district) => district.matchComponents.affordability)).toEqual([50, 50]);
    expect(pair[0].matchComponents.walkability).toBeNull();
    const single = addMatchScores(districts.slice(0, 1), {});
    expect(single[0].matchComponents.green).toBe(50);
    expect(addMatchScores([], {})).toEqual([]);
  });

  it("changes preference ordering when the user changes priorities within the same pair", async () => {
    const pair = (await fixtures()).slice(0, 2);
    const only = {
      affordability: 0,
      green: 0,
      walkability: 0,
      lowerRisk: 0,
      lowerFlood: 0,
      darkSkies: 0,
      parkAccess: 0,
    };
    const green = addMatchScores(pair, { ...only, green: 10 });
    const risk = addMatchScores(pair, { ...only, lowerRisk: 10 });
    expect(green[1].matchScore).toBeGreaterThan(green[0].matchScore);
    expect(risk[0].matchScore).toBeGreaterThan(risk[1].matchScore);
  });
});
