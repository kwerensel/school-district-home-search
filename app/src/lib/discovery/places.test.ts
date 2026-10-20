import { describe, expect, it, vi } from "vitest";
import { searchVerifiedPlaces, loadVerifiedPlace } from "./places";
import { executeDiscoveryTool, DiscoveryContextSchema } from "./conversation";
import { DEFAULT_DISCOVERY_PROFILE } from "./profile";

const town = {
  slug: "mun-merion",
  name: "Merion Station",
  kind: "municipality" as const,
  regionGroup: "pa-mainline",
};
const tract = {
  slug: "tract-a",
  name: "Census tract A",
  kind: "census_tract" as const,
  regionGroup: "pa-mainline",
};
const metric = {
  metricKey: "tree_canopy_pct",
  name: "Tree canopy",
  value: 60,
  units: "%",
  source: "Approved source",
  vintage: "2025",
  nativeResolution: "30 m",
};

describe("flexible verified-place context", () => {
  it("parameterizes place-name queries and scopes them to the active region", async () => {
    const execute = vi.fn().mockResolvedValue([town]);
    expect(
      await searchVerifiedPlaces({ query: "Merion", regionGroup: "pa-mainline" }, execute),
    ).toEqual([town]);
    expect(execute.mock.calls[0][1]).toEqual(["Merion", "pa-mainline"]);
    expect(execute.mock.calls[0][0]).not.toContain("ST_Contains");
  });
  it("keeps absent town metrics separate from overlapping whole-tract context", async () => {
    const execute = vi
      .fn()
      .mockResolvedValueOnce([town])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ ...tract, overlap: 0.4 }])
      .mockResolvedValueOnce([metric]);
    const result = await loadVerifiedPlace(town.slug, "pa-mainline", execute);
    expect(result?.metrics).toEqual([]);
    expect(result?.tractContexts[0].metrics).toEqual([metric]);
    expect(result?.tractContexts[0].fractionOfTractWithinPlace).toBe(0.4);
    const tool = await executeDiscoveryTool(
      "place_context",
      { slug: town.slug },
      DiscoveryContextSchema.parse({ profile: DEFAULT_DISCOVERY_PROFILE }),
      vi.fn(),
      { search: vi.fn(), context: vi.fn().mockResolvedValue(result) },
    );
    expect(tool.evidence[0].kind).toBe("unknown");
    expect(tool.evidence[0].details).toContain("district values have not been substituted");
    expect(tool.evidence[1].details).toContain("40.0% of this tract");
    expect(tool.evidence[1].details).toContain("entire tract");
    expect(tool.evidence[1].provenance?.[0].source).toBe(metric.source);
  });
  it("returns no fabricated place when the geography is unsupported", async () => {
    const result = await loadVerifiedPlace(
      "unknown-neighborhood",
      "all",
      vi.fn().mockResolvedValue([]),
    );
    expect(result).toBeNull();
  });
  it("supports arbitrary conversation goals without a fixed taxonomy", () => {
    const parsed = DiscoveryContextSchema.parse({
      profile: DEFAULT_DISCOVERY_PROFILE,
      contextNotes: "I need rehearsal space and time to care for my parents",
    });
    expect(parsed.contextNotes).toContain("rehearsal space");
    expect(parsed).not.toHaveProperty("goals");
  });
});
