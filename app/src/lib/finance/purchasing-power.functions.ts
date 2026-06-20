import { createServerFn } from "@tanstack/react-start";
import { setResponseHeader } from "@tanstack/react-start/server";
import { sql } from "@/server/db";
import { fetchDistrictPurchasingPower, PurchasingPowerQuerySchema } from "./server-data";
import type { PurchasingPowerPayload } from "./server-data";

export const getDistrictPurchasingPower = createServerFn({ method: "GET" })
  .validator(PurchasingPowerQuerySchema)
  .handler(async ({ data }): Promise<PurchasingPowerPayload> => {
    setResponseHeader("Cache-Control", "private, max-age=60");
    return fetchDistrictPurchasingPower(data, (text, values) => sql.query(text, values));
  });
