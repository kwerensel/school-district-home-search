import { describe, expect, it } from "vitest";
import {
  colorForMetricValue,
  formatMapMetricValue,
  lightPollutionCategory,
  treeCoverCategory,
} from "./presentation";

describe("consumer metric presentation", () => {
  it("turns raw tree-cover percentages into stable plain-language categories", () => {
    expect(treeCoverCategory(12)).toBe("Sparse");
    expect(treeCoverCategory(27)).toBe("Some trees");
    expect(treeCoverCategory(48)).toBe("Leafy");
    expect(treeCoverCategory(72)).toBe("Very leafy");
  });

  it("does not present VIIRS radiance as a 1-to-100 consumer score", () => {
    expect(lightPollutionCategory(1)).toBe("Very dark");
    expect(lightPollutionCategory(9)).toBe("Moderate glow");
    expect(formatMapMetricValue("lightPollution", 9)).toContain("radiance");
  });

  it("uses a dark-to-bright light-pollution color scale", () => {
    expect(colorForMetricValue("lightPollution", 0.3, 0.3, 100)).toBe("#24104f");
    expect(colorForMetricValue("lightPollution", 100, 0.3, 100)).toBe("#fde047");
  });
});
