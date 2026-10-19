import { describe, expect, it } from "vitest";
import { safeReturnTo } from "./auth-navigation";

describe("auth return navigation", () => {
  it("accepts local paths and rejects external redirects", () => {
    expect(safeReturnTo("/discover/results?monthlyBudget=5000")).toContain("/discover/results");
    expect(safeReturnTo("https://evil.example")).toBe("/saved");
    expect(safeReturnTo("//evil.example")).toBe("/saved");
  });
});
