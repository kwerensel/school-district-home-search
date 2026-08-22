import type { Filters, ListingFC } from "./types";

export const DEFAULT_FILTERS: Filters = {
  maxPrice: 2_000_000,
  minBeds: 0,
  minBaths: 0,
  goodOnly: false,
  district: "all",
  treeCover: "all",
  floodOnly: false,
};

const TREE_COVER_MINIMUMS: Record<Exclude<Filters["treeCover"], "all">, number> = {
  some: 20,
  leafy: 40,
  "very-leafy": 60,
};

export function applyFilters(fc: ListingFC, f: Filters): ListingFC {
  return {
    type: "FeatureCollection",
    features: fc.features.filter((feat) => {
      const p = feat.properties;
      if (p.price > f.maxPrice) return false;
      if (p.beds < f.minBeds) return false;
      if (p.baths < f.minBaths) return false;
      if (f.goodOnly && !p.good_district) return false;
      if (f.district !== "all" && p.school_district !== f.district) return false;
      if (
        f.treeCover !== "all" &&
        (p.tree_canopy_pct_100m ?? -Infinity) < TREE_COVER_MINIMUMS[f.treeCover]
      )
        return false;
      if (f.floodOnly && (p.flood_sfha ?? 0) < 1) return false;
      return true;
    }),
  };
}

export function uniqueDistricts(fc: ListingFC): string[] {
  const set = new Set<string>();
  for (const f of fc.features)
    if (f.properties.school_district) set.add(f.properties.school_district);
  return Array.from(set).sort();
}

export function priceBounds(fc: ListingFC): { min: number; max: number } {
  if (!fc.features.length) return { min: 0, max: 2_000_000 };
  let min = Infinity;
  let max = 0;
  for (const f of fc.features) {
    const p = f.properties.price;
    if (p < min) min = p;
    if (p > max) max = p;
  }
  return { min: Math.floor(min), max: Math.ceil(max) };
}
