import { describe, expect, it } from "vitest";
import { parseDollarAmount } from "./profile";

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
});
