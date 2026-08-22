import { describe, expect, it, vi } from "vitest";
import { buildDistrictsSql, buildListingMetricsSql, buildListingsSql } from "./server-queries";
import {
  fetchDistrictsGeoJson,
  fetchListingMetricsPayload,
  fetchListingsGeoJson,
} from "./server-data";

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
    expect(fragment.text).toContain("canopy.metric_key = 'canopy_height_m'");
    expect(fragment.text).toContain("tree_cover.metric_key = 'tree_canopy_pct'");
    expect(fragment.text).toContain("flood.metric_key = 'flood_sfha'");
  });

  it("builds represented-district SQL with simplification and optional state", () => {
    const fragment = buildDistrictsSql({
      bbox: [-76, 39, -73, 42],
      state: "NY",
      simplifyTolerance: 0.005,
      representedOnly: true,
    });

    expect(fragment.values).toEqual([0.005, -76, 39, -73, 42, "NY"]);
    expect(fragment.text).toContain("ST_SimplifyPreserveTopology(d.geom, $1)");
    expect(fragment.text).toContain("EXISTS (SELECT 1 FROM listings l WHERE l.district_id = d.id)");
    expect(fragment.text).toContain("ST_MakeEnvelope($2, $3, $4, $5, 4326)");
    expect(fragment.text).toContain("d.state = $6");
    expect(fragment.text).toContain("dr.slug AS district_slug");
    expect(fragment.text).toContain("dr.region_group");
    expect(fragment.text).toContain("FROM district_metrics");
    expect(fragment.text).toContain("light_pollution_radiance");
  });

  it("builds listing metric detail SQL for listing and tract context", () => {
    const fragment = buildListingMetricsSql({ listingId: 42 });

    expect(fragment.values).toEqual([42]);
    expect(fragment.text).toContain("FROM listing_metrics lm");
    expect(fragment.text).toContain("FROM region_metrics rm");
    expect(fragment.text).toContain("ST_Contains(r.geom, t.geom)");
    expect(fragment.text).toContain("'neighborhood' AS context");
  });

  it("fetches listing GeoJSON with a mocked SQL executor", async () => {
    const execute = vi.fn().mockResolvedValue([{ geojson: emptyCollection }]);

    await expect(fetchListingsGeoJson({}, execute)).resolves.toEqual(emptyCollection);
    expect(execute).toHaveBeenCalledTimes(1);
    expect(execute.mock.calls[0][0]).toContain("FROM listings l");
  });

  it("fetches district GeoJSON with a mocked SQL executor", async () => {
    const execute = vi.fn().mockResolvedValue([{ geojson: emptyCollection }]);

    await expect(
      fetchDistrictsGeoJson({ simplifyTolerance: 0.001, representedOnly: true }, execute),
    ).resolves.toEqual(emptyCollection);
    expect(execute).toHaveBeenCalledTimes(1);
    expect(execute.mock.calls[0][0]).toContain("FROM school_districts d");
  });

  it("maps listing metric payload rows to camelCase fields", async () => {
    const execute = vi.fn().mockResolvedValue([
      {
        payload: {
          listing: {
            id: 42,
            address: "1 Main St",
            city: "Wayne",
            zip: "19087",
            price: 750000,
            beds: 3,
            baths: 2,
            url: null,
            school_district: "Radnor",
            county_name: "Delaware",
            good_district: true,
            canopy_height_m_100m: 18.2,
            tree_canopy_pct_100m: 62.1,
            flood_sfha: 0,
          },
          metrics: [
            {
              metric_key: "canopy_height_m",
              name: "Canopy height",
              value: 18.2,
              units: "m",
              grain: "buffer_100m",
              vintage: "2026",
              source: "WRI/Meta",
              native_resolution: "1m",
              context: "street",
            },
          ],
          tractMetrics: [],
        },
      },
    ]);

    await expect(fetchListingMetricsPayload({ listingId: 42 }, execute)).resolves.toMatchObject({
      listing: { id: 42 },
      metrics: [{ metricKey: "canopy_height_m", nativeResolution: "1m" }],
      tractMetrics: [],
    });
  });
});
