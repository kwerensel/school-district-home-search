import { describe, expect, it } from "vitest";
import { applyFilters, DEFAULT_FILTERS, serializeExplorerFilters } from "./filters";
import type { ListingFC } from "./types";

const listings: ListingFC = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-74, 41] },
      properties: {
        id: 1,
        address: "1 Leafy Lane",
        city: "Example",
        zip: "10001",
        price: 500000,
        beds: 3,
        baths: 2,
        url: null,
        school_district: "Example",
        good_district: false,
        tree_canopy_pct_100m: 64,
      },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-74.1, 41.1] },
      properties: {
        id: 2,
        address: "2 Open Road",
        city: "Example",
        zip: "10002",
        price: 450000,
        beds: 3,
        baths: 2,
        url: null,
        school_district: "Example",
        good_district: false,
        tree_canopy_pct_100m: 18,
      },
    },
  ],
};

describe("listing filters", () => {
  it("filters consumer tree-cover categories using the 100 m coverage percentage", () => {
    const result = applyFilters(listings, {
      ...DEFAULT_FILTERS,
      maxPrice: 1_000_000,
      treeCover: "very-leafy",
    });

    expect(result.features.map((feature) => feature.properties.id)).toEqual([1]);
  });

  it("serializes filters without dropping the Discovery profile", () => {
    const params = serializeExplorerFilters(
      new URLSearchParams("monthlyBudget=5500&creditBand=good&districtSlug=example"),
      {
        ...DEFAULT_FILTERS,
        maxPrice: 875000,
        minBeds: 3,
        district: "Example",
        treeCover: "leafy",
      },
    );

    expect(params.get("monthlyBudget")).toBe("5500");
    expect(params.get("districtSlug")).toBe("example");
    expect(params.get("maxPrice")).toBe("875000");
    expect(params.get("minBeds")).toBe("3");
    expect(params.get("minBaths")).toBeNull();
    expect(params.get("district")).toBe("Example");
    expect(params.get("treeCover")).toBe("leafy");
  });
});

describe("Explorer navigation filters", () => {
  it("filters the existing dataset by region and a multi-district shortlist", () => {
    const scoped: ListingFC = {
      ...listings,
      features: listings.features.map((feature, index) => ({
        ...feature,
        properties: {
          ...feature.properties,
          region_group: index === 0 ? "pa-mainline" : "hudson-valley",
          district_slug: index === 0 ? "sd-pa" : "sd-ny",
        },
      })),
    };
    expect(
      applyFilters(scoped, { ...DEFAULT_FILTERS, regionGroup: "pa-mainline" }).features.map(
        (feature) => feature.properties.id,
      ),
    ).toEqual([1]);
    expect(
      applyFilters(scoped, { ...DEFAULT_FILTERS, districtSlugs: ["sd-pa", "sd-ny"] }).features,
    ).toHaveLength(2);
    expect(
      applyFilters(scoped, { ...DEFAULT_FILTERS, districtSlugs: ["sd-ny"] }).features.map(
        (feature) => feature.properties.id,
      ),
    ).toEqual([2]);
  });
  it("clears a stale focused district slug after selecting a different district", () => {
    const params = serializeExplorerFilters(
      new URLSearchParams("district=Old&districtSlug=sd-old&monthlyBudget=5500"),
      { ...DEFAULT_FILTERS, district: "New" },
    );
    expect(params.get("districtSlug")).toBeNull();
    expect(params.get("district")).toBe("New");
    expect(params.get("monthlyBudget")).toBe("5500");
  });
  it("roundtrips a region and district shortlist without leaking unrelated scenario inputs", () => {
    const params = serializeExplorerFilters(new URLSearchParams(), {
      ...DEFAULT_FILTERS,
      regionGroup: "pa-mainline",
      districtSlugs: ["sd-a", "sd-b"],
    });
    expect(params.get("regionGroup")).toBe("pa-mainline");
    expect(params.get("districts")).toBe("sd-a,sd-b");
    expect(params.get("contextNotes")).toBeNull();
  });
});
