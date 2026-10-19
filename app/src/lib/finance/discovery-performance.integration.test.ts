import { describe, it } from "vitest";

const enabled = process.env.GROUNDTRUTH_DISCOVERY_PERFORMANCE === "1";

// Read-only and opt-in: exercises real Neon reads, rate resolution, finance and
// scoring. It does not invoke commute/geocoding, narratives or account flows.
describe.runIf(enabled)("warm Discovery data performance", () => {
  it("returns each region's computed district results within 500 ms after warming", async () => {
    let stage = "initialization";
    try {
      const { sql } = await import("@/server/db");
      const { fetchDistrictPurchasingPower } = await import("./server-data");
      const { getMortgageRateAssumption } = await import("./rates");
      const { mkdir, writeFile } = await import("node:fs/promises");
      const { dirname } = await import("node:path");
      const { fileURLToPath } = await import("node:url");
      const results = [];
      for (const regionGroup of [undefined, "pa-mainline", "hudson-valley"] as const) {
        const measure = async () => {
          const start = performance.now();
          const rate = await getMortgageRateAssumption();
          const payload = await fetchDistrictPurchasingPower(
            { monthlyBudget: 6500, regionGroup },
            async (query, params) =>
              (await sql.query(
                query,
                params,
              )) as unknown as import("./server-data").DistrictPurchasingPowerRow[],
            rate,
          );
          return {
            elapsedMs: performance.now() - start,
            districtCount: payload.districts.length,
            rateSource: payload.rateAssumption.source,
          };
        };
        stage = `warming:${regionGroup ?? "both"}`;
        await measure();
        const samples = [];
        stage = `measuring:${regionGroup ?? "both"}`;
        for (let index = 0; index < 3; index++) samples.push(await measure());
        if (samples.some((sample) => sample.districtCount === 0))
          throw new Error("Expected nonempty district results");
        results.push({ regionGroup: regionGroup ?? "both", samples });
      }
      stage = "report";
      const passed = results.every((result) =>
        result.samples.every((sample) => sample.elapsedMs < 500),
      );
      const report = {
        observedAt: new Date().toISOString(),
        scope: "Neon read + rate resolution + finance + district ranking; warmed per region",
        limitation:
          "Local server-data timing; excludes browser, HTTP framework, commute and narratives",
        thresholdMs: 500,
        samplesPerRegion: 3,
        passed,
        results,
      };
      const path = fileURLToPath(
        new URL("../../../../data/reports/qa/discovery-warm-performance.json", import.meta.url),
      );
      await mkdir(dirname(path), { recursive: true });
      await writeFile(path, JSON.stringify(report, null, 2));
      // Public counts/timings only; no input profile, SQL, URL or credentials.
      console.info(JSON.stringify(report));
      stage = "warm-target";
      if (!passed) throw new Error("Warm data path exceeded the 500 ms target");
    } catch {
      throw new Error(`Read-only Discovery performance check failed at ${stage}`);
    }
  }, 90_000);
});
