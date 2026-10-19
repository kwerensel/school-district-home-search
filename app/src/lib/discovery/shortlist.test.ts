import { describe, expect, it, vi } from "vitest";
import { fetchDistrictPurchasingPower } from "@/lib/finance/server-data";
import { DEFAULT_DISCOVERY_PROFILE, DiscoveryProfileSchema } from "./profile";
import { parseDistrictPriceCaps, shortlistExplorerHref } from "./shortlist";
import { applyFilters, DEFAULT_FILTERS, serializeExplorerFilters } from "@/lib/housing/filters";
import { buildListingsSql } from "@/lib/housing/server-queries";
import type { ListingFC } from "@/lib/housing/types";

describe("multi-district shortlist", () => {
  it("preserves extended fields through saved-profile validation and Explorer handoff", async () => {
    const profile = {
      ...DEFAULT_DISCOVERY_PROFILE,
      wizardStep: "results" as const,
      shortlist: ["first", "second"],
      grossMonthlyIncome: 15000,
      monthlyDebt: 500,
    };
    expect(DiscoveryProfileSchema.parse(profile)).toEqual(profile);
    const { districts } = await fetchDistrictPurchasingPower(
      { monthlyBudget: 5500 },
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
          effective_tax_rate: 0.03,
        },
      ]),
    );
    const url = new URL(shortlistExplorerHref(profile, districts), "http://localhost");
    const caps = parseDistrictPriceCaps(url.searchParams);
    expect(caps.map((cap) => cap.slug)).toEqual(["first", "second"]);
    expect(caps[0].maxPrice).toBeGreaterThan(caps[1].maxPrice);
    const edited = serializeExplorerFilters(url.searchParams, {
      ...DEFAULT_FILTERS,
      districtCaps: caps,
    });
    expect(edited.get("grossMonthlyIncome")).toBe("15000");
    expect(edited.get("shortlist")).toBe(url.searchParams.get("shortlist"));
    expect(parseDistrictPriceCaps(edited)).toEqual(caps);
  });

  it("uses each district's cap and excludes other districts regardless of matching display names", () => {
    const caps = [
      { slug: "a", name: "Same name", maxPrice: 800000 },
      { slug: "b", name: "Same name", maxPrice: 400000 },
    ];
    const fc: ListingFC = {
      type: "FeatureCollection",
      features: [
        [1, "a", 700000],
        [2, "b", 700000],
        [3, "b", 350000],
        [4, "c", 300000],
      ].map(([id, slug, price]) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [-75, 40] },
        properties: {
          id: Number(id),
          district_slug: String(slug),
          school_district: "Same name",
          price: Number(price),
          beds: 3,
          baths: 2,
          address: "Example",
          city: "Example",
          zip: "19000",
          url: null,
          good_district: false,
        },
      })),
    };
    expect(
      applyFilters(fc, { ...DEFAULT_FILTERS, districtCaps: caps }).features.map(
        (feature) => feature.properties.id,
      ),
    ).toEqual([1, 3]);
    expect(
      applyFilters(fc, {
        ...DEFAULT_FILTERS,
        districtCaps: [{ slug: "a", name: "Same name", maxPrice: 0 }],
      }).features,
    ).toHaveLength(0);
    expect(
      applyFilters(fc, { ...DEFAULT_FILTERS, districtCaps: caps, maxPrice: 500000 }).features.map(
        (feature) => feature.properties.id,
      ),
    ).toEqual([3]);
  });

  it("parameterizes independent SQL caps and permits a zero ceiling without widening results", () => {
    const caps = [
      { slug: "a", name: "First", maxPrice: 800000 },
      { slug: "b", name: "Second", maxPrice: 0 },
    ];
    const query = buildListingsSql({ districtCaps: caps });
    expect(query.values).toEqual(["a", 800000, "b", 0]);
    expect(query.text).toContain("sr.slug = $1");
    expect(query.text).toContain("l.price <= $2");
    expect(query.text).toContain("sr.slug = $3");
    expect(query.text).toContain("l.price <= $4");
    expect(
      parseDistrictPriceCaps(new URLSearchParams({ districtCaps: JSON.stringify(caps) })),
    ).toEqual(caps);
  });
});
