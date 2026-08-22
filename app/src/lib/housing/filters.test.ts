import { describe, expect, it } from "vitest";
import { applyFilters, DEFAULT_FILTERS } from "./filters";
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
});
