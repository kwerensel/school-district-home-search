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

  it("labels park access as an 800 m district-land share", () => {
    expect(formatMapMetricValue("parkAccess", 0.625)).toContain("62.5%");
    expect(formatMapMetricValue("parkAccess", 0.625)).toContain("within 800 m");
  });

  it("formats transit density and regional drive time with honest units", () => {
    expect(formatMapMetricValue("transitAccess", 6.25)).toBe("6.3 mapped stops / km²");
    expect(formatMapMetricValue("commuteMinutes", 54.6)).toBe("55 min by car");
    expect(formatMapMetricValue("airQuality", 41.7)).toBe("42 annual mean daily AQI");
    expect(formatMapMetricValue("transportationNoise", 18.25)).toBe("18.3% at or above 55 dBA");
  });

  it("labels supplemental noise-source maps as proxies rather than measurements", () => {
    expect(formatMapMetricValue("sirenSources", 0.825)).toBe("0.82 mapped facilities / km²");
    expect(formatMapMetricValue("nightlifeSources", 1.144)).toBe("1.14 mapped venues / km²");
    expect(formatMapMetricValue("industrialLand", 5.42)).toBe("5.4% mapped industrial land");
    expect(formatMapMetricValue("freightRail", 0.345)).toBe("0.34 rail km / km²");
  });
});
