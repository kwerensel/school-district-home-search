import { describe, expect, it } from "vitest";
import { compareRowValues, ROW_PREFERENCES } from "./comparison-highlights";

describe("shortlist row highlights", () => {
  it("uses higher canopy and walkability but lower taxes, risk and flood for active priorities", () => {
    expect(ROW_PREFERENCES.treeCanopyPct).toMatchObject({ key: "green", direction: "higher" });
    expect(ROW_PREFERENCES.walkabilityIndex).toMatchObject({
      key: "walkability",
      direction: "higher",
    });
    for (const key of ["effectiveTaxRate", "riskIndex", "floodSfha"] as const)
      expect(ROW_PREFERENCES[key]?.direction).toBe("lower");
    expect(compareRowValues([48, 50, 47], "higher")).toEqual([
      null,
      { tone: "strongest", label: "Strongest" },
      { tone: "weakest", label: "Weakest" },
    ]);
    expect(compareRowValues([0.0107, 0.0123, 0.012], "lower", { scale: 100 })).toEqual([
      { tone: "strongest", label: "Strongest" },
      { tone: "weakest", label: "Weakest" },
      null,
    ]);
  });

  it("does not invent a preference for inactive or unsupported metrics", () => {
    expect(ROW_PREFERENCES.noiseSirenDensity).toBeUndefined();
    expect(ROW_PREFERENCES.transitAccess).toBeUndefined();
    expect(compareRowValues([1, 2, 3], null)).toEqual([
      { tone: "neutral", label: "Lowest" },
      null,
      { tone: "neutral", label: "Highest" },
    ]);
  });

  it("shares tied extrema and treats equal displayed values as neutral", () => {
    expect(compareRowValues([5, 5, 1], "higher").slice(0, 2)).toEqual([
      { tone: "strongest", label: "Strongest (tied)" },
      { tone: "strongest", label: "Strongest (tied)" },
    ]);
    expect(compareRowValues([1.231, 1.234], "higher")).toEqual([
      { tone: "neutral", label: "Tied" },
      { tone: "neutral", label: "Tied" },
    ]);
    expect(compareRowValues([0.012301, 0.012304], "lower", { scale: 100 })).toEqual([
      { tone: "neutral", label: "Tied" },
      { tone: "neutral", label: "Tied" },
    ]);
  });

  it("excludes missing/nonfinite values and needs two known values", () => {
    expect(compareRowValues([null, NaN, 3], "higher")).toEqual([null, null, null]);
    expect(compareRowValues([null, 1, 3], "higher")).toEqual([
      null,
      { tone: "weakest", label: "Weakest" },
      { tone: "strongest", label: "Strongest" },
    ]);
    expect(compareRowValues([], "lower")).toEqual([]);
  });
});
