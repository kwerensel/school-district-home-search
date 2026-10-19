import { describe, expect, it } from "vitest";
import { hasAuthConfiguration } from "./auth-configuration";

describe("optional account configuration", () => {
  it("is unavailable without every required server setting", () => {
    expect(hasAuthConfiguration({})).toBe(false);
    expect(
      hasAuthConfiguration({
        DATABASE_URL: "configured",
        BETTER_AUTH_URL: "http://localhost",
        BETTER_AUTH_SECRET: "short",
      }),
    ).toBe(false);
    expect(
      hasAuthConfiguration({
        DATABASE_URL: "configured",
        BETTER_AUTH_URL: "http://localhost",
        BETTER_AUTH_SECRET: "x".repeat(32),
      }),
    ).toBe(true);
  });
});
