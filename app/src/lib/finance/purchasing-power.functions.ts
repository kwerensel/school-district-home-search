import { createServerFn } from "@tanstack/react-start";
import { setResponseHeader } from "@tanstack/react-start/server";
import { sql } from "@/server/db";
import { fetchDistrictPurchasingPower, PurchasingPowerQuerySchema } from "./server-data";
import type { DistrictPurchasingPowerRow, PurchasingPowerPayload } from "./server-data";
import { getMortgageRateAssumption } from "./rates";

export const getDistrictPurchasingPower = createServerFn({ method: "GET" })
  .validator(PurchasingPowerQuerySchema)
  .handler(async ({ data }): Promise<PurchasingPowerPayload> => {
    setResponseHeader("Cache-Control", "private, max-age=60");
    const rateAssumption =
      data.baseAnnualRate === undefined ? await getMortgageRateAssumption() : undefined;
    return fetchDistrictPurchasingPower(
      data,
      async (text, values) =>
        (await sql.query(text, values)) as unknown as DistrictPurchasingPowerRow[],
      rateAssumption,
    );
  });
