import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_ANNUAL_RATE } from "./purchasing-power";
import {
  clearMortgageRateCacheForTests,
  getMortgageRateAssumption,
  parsePmmsCsv,
  RATE_CACHE_TTL_MS,
} from "./rates";

const csv = `observation_date,MORTGAGE30US
2026-08-13,6.67
2026-08-20,6.65
`;

describe("PMMS mortgage-rate assumption", () => {
  beforeEach(() => clearMortgageRateCacheForTests());

  it("parses the latest valid weekly observation as a decimal annual rate", () => {
    expect(parsePmmsCsv(csv)).toEqual({
      annualRate: 0.0665,
      source: "pmms",
      observationDate: "2026-08-20",
    });
  });

  it("caches a successful fetch for 24 hours", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(csv, { status: 200 }));
    let currentTime = 1_000;

    const first = await getMortgageRateAssumption({ fetchImpl, now: () => currentTime });
    currentTime += RATE_CACHE_TTL_MS - 1;
    const second = await getMortgageRateAssumption({ fetchImpl, now: () => currentTime });

    expect(first.source).toBe("pmms");
    expect(second).toEqual(first);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("uses the documented fallback when the source is unavailable", async () => {
    const assumption = await getMortgageRateAssumption({
      fetchImpl: vi.fn().mockRejectedValue(new Error("offline")),
    });

    expect(assumption).toEqual({
      annualRate: DEFAULT_ANNUAL_RATE,
      source: "fallback",
      observationDate: null,
    });
  });
});
