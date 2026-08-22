import { describe, expect, it } from "vitest";
import { safeErrorForLog } from "./safe-error";

describe("safe error logging", () => {
  it("never serializes sensitive profile fields from an error", () => {
    const profile = {
      monthlyBudget: 8500,
      downPayment: 275000,
      creditBand: "fair",
    };
    const safe = JSON.stringify(
      safeErrorForLog(new Error(`Profile failed: ${JSON.stringify(profile)}`)),
    );

    expect(safe).not.toContain("8500");
    expect(safe).not.toContain("275000");
    expect(safe).not.toContain("creditBand");
    expect(safe).not.toContain("fair");
  });
});
