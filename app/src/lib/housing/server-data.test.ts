import { describe, expect, it, vi } from "vitest";
import { buildDistrictsSql, buildListingsSql } from "./server-queries";
import { fetchDistrictsGeoJson, fetchListingsGeoJson } from "./server-data";

const emptyCollection = { type: "FeatureCollection", features: [] };

describe("housing server data", () => {
  it("builds filtered listings SQL with positional parameters", () => {
    const fragment = buildListingsSql({
      bbox: [-76, 39, -73, 42],
      maxPrice: 750000,
      minBeds: 3,
      minBaths: 2,
      goodOnly: true,
      districtSlug: "4214160",
    });

    expect(fragment.values).toEqual([-76, 39, -73, 42, 750000, 3, 2, "4214160"]);
    expect(fragment.text).toContain("ST_MakeEnvelope($1, $2, $3, $4, 4326)");
    expect(fragment.text).toContain("l.price <= $5");
    expect(fragment.text).toContain("l.beds >= $6");
    expect(fragment.text).toContain("l.baths >= $7");
    expect(fragment.text).toContain("COALESCE(dq.good_district, false) = true");
    expect(fragment.text).toContain("d.nces_geoid = $8");
  });

  it("builds represented-district SQL with simplification and optional state", () => {
    const fragment = buildDistrictsSql({
      bbox: [-76, 39, -73, 42],
      state: "NY",
      simplifyTolerance: 0.005,
    });

    expect(fragment.values).toEqual([0.005, -76, 39, -73, 42, "NY"]);
    expect(fragment.text).toContain("ST_SimplifyPreserveTopology(d.geom, $1)");
    expect(fragment.text).toContain("EXISTS (SELECT 1 FROM listings l WHERE l.district_id = d.id)");
    expect(fragment.text).toContain("ST_MakeEnvelope($2, $3, $4, $5, 4326)");
    expect(fragment.text).toContain("d.state = $6");
  });

  it("fetches listing GeoJSON with a mocked SQL executor", async () => {
    const execute = vi.fn().mockResolvedValue([{ geojson: emptyCollection }]);

    await expect(fetchListingsGeoJson({}, execute)).resolves.toEqual(emptyCollection);
    expect(execute).toHaveBeenCalledTimes(1);
    expect(execute.mock.calls[0][0]).toContain("FROM listings l");
  });

  it("fetches district GeoJSON with a mocked SQL executor", async () => {
    const execute = vi.fn().mockResolvedValue([{ geojson: emptyCollection }]);

    await expect(fetchDistrictsGeoJson({ simplifyTolerance: 0.001 }, execute)).resolves.toEqual(
      emptyCollection,
    );
    expect(execute).toHaveBeenCalledTimes(1);
    expect(execute.mock.calls[0][0]).toContain("FROM school_districts d");
  });
});
