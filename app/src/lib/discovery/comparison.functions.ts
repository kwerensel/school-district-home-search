import { createServerFn } from "@tanstack/react-start";
import { setResponseHeader } from "@tanstack/react-start/server";
import { sql } from "@/server/db";
import { fetchDistrictPurchasingPower } from "@/lib/finance/server-data";
import type { DistrictPurchasingPowerRow } from "@/lib/finance/server-data";
import { getMortgageRateAssumption } from "@/lib/finance/rates";
import { ComparisonQuerySchema } from "./comparison";
import { resolveDistrictComparison } from "./comparison-service";
import { requestTradeoffNarrative } from "./tradeoff-narrative";

export const getDistrictComparison = createServerFn({ method: "POST" })
  .validator(ComparisonQuerySchema)
  .handler(async ({ data }) => {
    setResponseHeader("Cache-Control", "private, no-store");
    const rate =
      data.profile.baseAnnualRate === undefined ? await getMortgageRateAssumption() : undefined;
    const { districts } = await fetchDistrictPurchasingPower(
      data.profile,
      async (query, values) =>
        (await sql.query(query, values)) as unknown as DistrictPurchasingPowerRow[],
      rate,
    );
    const apiKey = process.env.ANTHROPIC_API_KEY;
    return resolveDistrictComparison(data, {
      districts,
      readCache: async ({ payload, hash }) => {
        const cached = await sql`
          SELECT narrative, source FROM tradeoff_narratives
          WHERE region_a_id=${payload.regionA.id} AND region_b_id=${payload.regionB.id}
            AND profile_bucket=${payload.profileBucket} AND payload_hash=${hash}
            AND created_at > now() - interval '7 days' LIMIT 1
        `;
        return cached[0] ? { narrative: cached[0].narrative, source: cached[0].source } : null;
      },
      writeCache: async ({ payload, hash }, result) => {
        await sql`
          INSERT INTO tradeoff_narratives (region_a_id,region_b_id,profile_bucket,payload_hash,narrative,source)
          VALUES (${payload.regionA.id},${payload.regionB.id},${payload.profileBucket},${hash},${result.narrative},${result.source})
          ON CONFLICT (region_a_id,region_b_id,profile_bucket,payload_hash)
          DO UPDATE SET narrative=EXCLUDED.narrative,source=EXCLUDED.source,created_at=now()
        `;
      },
      ...(apiKey ? { generate: (payload) => requestTradeoffNarrative(payload, { apiKey }) } : {}),
    });
  });
