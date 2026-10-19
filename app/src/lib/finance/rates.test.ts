import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_ANNUAL_RATE } from "./purchasing-power";
import {
  clearMortgageRateCacheForTests,
  getMortgageRateAssumption,
  parsePmmsCsv,
  RATE_CACHE_TTL_MS,
  FALLBACK_RATE_CACHE_TTL_MS,
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

  it("briefly caches an outage fallback, then retries and recovers a fresh rate", async () => {
    let attempts = 0;
    const fetchImpl = vi.fn(async () => {
      attempts++;
      if (attempts === 1) throw new Error("offline");
      return new Response(csv, { status: 200 });
    });
    let currentTime = 1000;
    const first = await getMortgageRateAssumption({ fetchImpl, now: () => currentTime });
    currentTime += FALLBACK_RATE_CACHE_TTL_MS - 1;
    const second = await getMortgageRateAssumption({ fetchImpl, now: () => currentTime });
    expect(first.source).toBe("fallback");
    expect(second).toEqual(first);
    expect(fetchImpl).toHaveBeenCalledTimes(1);

    currentTime++;
    const recovered = await getMortgageRateAssumption({ fetchImpl, now: () => currentTime });
    expect(recovered.source).toBe("pmms");
    expect(recovered.annualRate).toBe(0.0665);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it.each([true, false])(
    "preserves concurrent PMMS success (success starts first: %s)",
    async (successStartsFirst) => {
      let rejectSlowFetch!: (error: Error) => void;
      let resolveFreshFetch!: (response: Response) => void;
      const slowFetch = vi.fn(
        () =>
          new Promise<Response>((_resolve, reject) => {
            rejectSlowFetch = reject;
          }),
      );
      const freshFetch = vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            resolveFreshFetch = resolve;
          }),
      );
      let pending: ReturnType<typeof getMortgageRateAssumption>;
      let freshPromise: ReturnType<typeof getMortgageRateAssumption>;
      if (successStartsFirst) {
        freshPromise = getMortgageRateAssumption({ fetchImpl: freshFetch, now: () => 1000 });
        pending = getMortgageRateAssumption({ fetchImpl: slowFetch, now: () => 1001 });
      } else {
        pending = getMortgageRateAssumption({ fetchImpl: slowFetch, now: () => 1000 });
        freshPromise = getMortgageRateAssumption({ fetchImpl: freshFetch, now: () => 1001 });
      }
      resolveFreshFetch(new Response(csv, { status: 200 }));
      const fresh = await freshPromise;
      rejectSlowFetch(new Error("offline"));
      expect(await pending).toEqual(fresh);
      const unexpectedFetch = vi.fn(async () => new Response(csv, { status: 200 }));
      expect(
        await getMortgageRateAssumption({ fetchImpl: unexpectedFetch, now: () => 1002 }),
      ).toEqual(fresh);
      expect(unexpectedFetch).not.toHaveBeenCalled();
    },
  );
});
