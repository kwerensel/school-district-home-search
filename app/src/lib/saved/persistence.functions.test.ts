import { describe, expect, it } from "vitest";
import { publicPersistenceError } from "./persistence.functions";

describe("saved-data error privacy", () => {
  it("never serializes financial profile contents into a public error", () => {
    const sensitive = {
      monthlyBudget: 8765,
      downPayment: 234567,
      creditBand: "fair",
    };
    const message = publicPersistenceError(new Error(JSON.stringify(sensitive)));

    expect(message).not.toContain("8765");
    expect(message).not.toContain("234567");
    expect(message).not.toContain("fair");
  });
});
