import { describe, expect, it } from "vitest";
import { DEFAULT_DISCOVERY_PROFILE } from "./profile";
import { DiscoveryContextSchema, executeDiscoveryTool } from "./conversation";
import { fetchDistrictPurchasingPower } from "@/lib/finance/server-data";
import type { DistrictPurchasingPowerRow } from "@/lib/finance/server-data";

// Opt-in read-only smoke test. Never call a model, load a key, or write database state.
describe.skipIf(process.env.DISCOVERY_DB_SMOKE !== "1")("promoted Discovery data smoke", () => {
  it("reads promoted metrics and source metadata for both project regions", async () => {
    const { sql } = await import("@/server/db");
    for (const regionGroup of ["pa-mainline", "hudson-valley"] as const) {
      const profile = { ...DEFAULT_DISCOVERY_PROFILE, regionGroup };
      const getDistricts = () =>
        fetchDistrictPurchasingPower(
          {
            monthlyBudget: profile.monthlyBudget,
            downPaymentAmount: profile.downPayment,
            creditBand: profile.creditBand,
            regionGroup,
            environmentWeights: profile.weights,
            baseAnnualRate: 0.06,
          },
          async (text, params) => (await sql.query(text, params)) as DistrictPurchasingPowerRow[],
        );
      const data = await getDistricts();
      expect(data.districts.length).toBeGreaterThan(0);
      expect(data.districts.every((district) => district.regionGroup === regionGroup)).toBe(true);
      expect(
        data.districts.every((district) =>
          district.metricProvenance?.some(
            (metric) =>
              metric.metricKey === "effective_tax_rate" && metric.source && metric.vintage,
          ),
        ),
      ).toBe(true);
      const selected = data.districts.slice(0, 2).map((district) => district.districtSlug);
      const analysis = await executeDiscoveryTool(
        "compare_housing_costs",
        {},
        DiscoveryContextSchema.parse({
          profile,
          comparisonSlugs: selected,
          housing: { purchasePrice: 500000, additionalMonthlyCosts: 500 },
          opportunity: { monthlyContribution: 0, upfrontCapital: 0, years: 10, annualReturn: 0 },
        }),
        getDistricts,
      );
      expect(analysis.evidence).toHaveLength(3);
      expect(
        analysis.evidence[0].provenance?.some(
          (metric) => metric.metricKey === "effective_tax_rate",
        ),
      ).toBe(true);
      expect(analysis.evidence.at(-1)?.id).toBe("housing-opportunity");
    }
  }, 30000);
  it("resolves named towns and keeps their metric gaps explicit", async () => {
    const { sql } = await import("@/server/db");
    const { searchVerifiedPlaces, loadVerifiedPlace } = await import("./places");
    const execute = async (text: string, params: unknown[]) => sql.query(text, params);
    const matches = await searchVerifiedPlaces(
      { query: "Merion Station", regionGroup: "pa-mainline" },
      execute,
    );
    const municipality = matches.find((place) => place.kind === "municipality");
    expect(municipality).toBeDefined();
    const context = await loadVerifiedPlace(municipality!.slug, "pa-mainline", execute);
    expect(context?.place.kind).toBe("municipality");
    expect(context?.metrics).toEqual([]);
    expect(context?.tractContexts.every((tract) => tract.place.kind === "census_tract")).toBe(true);
  }, 30000);
  it("carries a multi-district shortlist through the frozen listing payload", async () => {
    const { sql } = await import("@/server/db");
    const { fetchListingsGeoJson } = await import("@/lib/housing/server-data");
    const { applyFilters, DEFAULT_FILTERS } = await import("@/lib/housing/filters");
    const listings = await fetchListingsGeoJson({ payloadVersion: 2 }, async (text, params) =>
      sql.query(text, params),
    );
    expect(listings.features).toHaveLength(4505);
    expect(
      listings.features.every(
        (feature) => feature.properties.region_group && feature.properties.district_slug,
      ),
    ).toBe(true);
    const selected = applyFilters(listings, {
      ...DEFAULT_FILTERS,
      maxPrice: 100000000,
      regionGroup: "pa-mainline",
      districtSlugs: ["sd-4214160", "sd-4219920", "sd-4223640"],
    });
    expect(selected.features).toHaveLength(134);
  }, 30000);
});
