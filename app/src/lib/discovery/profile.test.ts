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

describe("extended Discovery profile", () => {
  it("round-trips each wizard step, optional finance, shortlist and two commute anchors", () => {
    for (const wizardStep of ["region", "budget", "priorities", "results"] as const) {
      const profile = {
        ...DEFAULT_DISCOVERY_PROFILE,
        wizardStep,
        grossMonthlyIncome: 15000,
        monthlyDebt: 0,
        shortlist: ["district-a", "district-b"],
        commuteAnchors: [
          {
            label: "Public station",
            lat: 40.1,
            lng: -75.3,
            maxMinutes: 45,
            mode: "driving-car" as const,
          },
          {
            label: "Town hall",
            lat: 41.1,
            lng: -74.3,
            maxMinutes: 60,
            mode: "driving-car" as const,
          },
        ],
      };
      expect(parseDiscoveryProfile(serializeDiscoveryProfile(profile))).toEqual(profile);
    }
  });

  it("ignores malformed optional state without discarding a valid budget", () => {
    const profile = parseDiscoveryProfile(
      new URLSearchParams({
        monthlyBudget: "7000",
        grossMonthlyIncome: "NaN",
        monthlyDebt: "-1",
        step: "invalid",
        shortlist: "broken",
        commuteAnchors: JSON.stringify([
          { label: "invalid", lat: 99, lng: -75, maxMinutes: 45, mode: "driving-car" },
        ]),
      }),
    );
    expect(profile.monthlyBudget).toBe(7000);
    expect(profile.grossMonthlyIncome).toBeUndefined();
    expect(profile.monthlyDebt).toBeUndefined();
    expect(profile.wizardStep).toBeUndefined();
    expect(profile.shortlist).toBeUndefined();
    expect(profile.commuteAnchors).toBeUndefined();
  });

  it("bounds and deduplicates shareable shortlists", () => {
    expect(
      parseDiscoveryProfile(new URLSearchParams({ shortlist: JSON.stringify(["a", "a", "b"]) }))
        .shortlist,
    ).toEqual(["a", "b"]);
    expect(
      parseDiscoveryProfile(
        new URLSearchParams({
          shortlist: JSON.stringify(Array.from({ length: 11 }, (_, i) => `district-${i}`)),
        }),
      ).shortlist,
    ).toBeUndefined();
  });
});
