import { describe, expect, it } from "vitest";
import {
  DEFAULT_DISCOVERY_PROFILE,
  parseDiscoveryProfile,
  parseDollarAmount,
  serializeDiscoveryProfile,
} from "./profile";

describe("Discovery profile parsing", () => {
  it("preserves the default when a URL amount is missing", () => {
    expect(parseDollarAmount("", 150000, true)).toBe(150000);
    expect(parseDollarAmount("   ", 5500)).toBe(5500);
  });

  it("accepts explicit zero only for fields that allow it", () => {
    expect(parseDollarAmount("0", 150000, true)).toBe(0);
    expect(parseDollarAmount("0", 5500)).toBe(5500);
  });

  it("accepts formatted dollar strings", () => {
    expect(parseDollarAmount("$275,000", 150000, true)).toBe(275000);
  });

  it("uses safe defaults for missing or invalid URL values", () => {
    const profile = parseDiscoveryProfile(
      new URLSearchParams(
        "monthlyBudget=nope&downPayment=-1&creditBand=unknown&regionGroup=elsewhere&green=11",
      ),
    );

    expect(profile).toEqual(DEFAULT_DISCOVERY_PROFILE);
  });

  it("round-trips a customized shareable profile", () => {
    const profile = {
      ...DEFAULT_DISCOVERY_PROFILE,
      monthlyBudget: 7250,
      downPayment: 0,
      creditBand: "excellent" as const,
      regionGroup: "hudson-valley" as const,
      weights: { ...DEFAULT_DISCOVERY_PROFILE.weights, green: 8, parkAccess: 4 },
    };

    const serialized = serializeDiscoveryProfile(profile);

    expect(serialized.has("walkability")).toBe(false);
    expect(parseDiscoveryProfile(serialized)).toEqual(profile);
  });
});
