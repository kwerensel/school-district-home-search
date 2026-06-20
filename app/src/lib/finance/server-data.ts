import { z } from "zod";
import { computePurchasingPower } from "./purchasing-power";
import type { BindingBound, CreditBand, PurchasingPowerInput } from "./purchasing-power";

export const PurchasingPowerQuerySchema = z.object({
  monthlyBudget: z.number().positive(),
  baseAnnualRate: z.number().min(0).optional(),
  downPaymentFraction: z.number().min(0).lt(1).optional(),
  insuranceAnnualRate: z.number().min(0).optional(),
  pmiAnnualRate: z.number().min(0).optional(),
  creditBand: z.enum(["excellent", "good", "fair"]).optional(),
  grossMonthlyIncome: z.number().positive().optional(),
  monthlyDebt: z.number().min(0).optional(),
  maxDti: z.number().positive().max(1).optional(),
  regionGroup: z.enum(["pa-mainline", "hudson-valley"]).optional(),
});

export type PurchasingPowerQuery = z.infer<typeof PurchasingPowerQuerySchema>;

export type SqlFragment = {
  text: string;
  values: unknown[];
};

export type QueryExecutor<T> = (queryWithPlaceholders: string, params?: unknown[]) => Promise<T[]>;

export type DistrictPurchasingPowerRow = {
  district_region_id: number;
  district_slug: string;
  district_name: string;
  region_group: string;
  effective_tax_rate: number | string;
};

export type DistrictPurchasingPower = {
  districtRegionId: number;
  districtSlug: string;
  districtName: string;
  regionGroup: string;
  effectiveTaxRate: number;
  maxPurchasePrice: number;
  budgetLimitedPrice: number;
  dtiLimitedPrice: number | null;
  bindingBound: BindingBound;
  annualRate: number;
  monthlyCostFactor: number;
};

export type PurchasingPowerPayload = {
  districts: DistrictPurchasingPower[];
};

export function buildDistrictTaxRateSql(input: Pick<PurchasingPowerQuery, "regionGroup">) {
  const values: unknown[] = [];
  const where = ["dm.metric_key = 'effective_tax_rate'"];

  if (input.regionGroup) {
    values.push(input.regionGroup);
    where.push(`d.region_group = $${values.length}`);
  }

  return {
    text: `
      SELECT
        d.id AS district_region_id,
        d.slug AS district_slug,
        d.name AS district_name,
        d.region_group,
        dm.value AS effective_tax_rate
      FROM district_metrics dm
      JOIN regions d ON d.id = dm.district_region_id
      WHERE ${where.join(" AND ")}
      ORDER BY d.region_group, d.name
    `,
    values,
  };
}

export async function fetchDistrictPurchasingPower(
  input: PurchasingPowerQuery,
  execute: QueryExecutor<DistrictPurchasingPowerRow>,
): Promise<PurchasingPowerPayload> {
  const fragment = buildDistrictTaxRateSql(input);
  const rows = await execute(fragment.text, fragment.values);

  return {
    districts: rows.map((row) => computeDistrictPurchasingPower(input, row)),
  };
}

function computeDistrictPurchasingPower(
  input: PurchasingPowerQuery,
  row: DistrictPurchasingPowerRow,
): DistrictPurchasingPower {
  const effectiveTaxRate = Number(row.effective_tax_rate);
  const financeInput: PurchasingPowerInput = {
    monthlyBudget: input.monthlyBudget,
    effectiveTaxRate,
    baseAnnualRate: input.baseAnnualRate,
    downPaymentFraction: input.downPaymentFraction,
    insuranceAnnualRate: input.insuranceAnnualRate,
    pmiAnnualRate: input.pmiAnnualRate,
    creditBand: input.creditBand as CreditBand | undefined,
    grossMonthlyIncome: input.grossMonthlyIncome,
    monthlyDebt: input.monthlyDebt,
    maxDti: input.maxDti,
  };
  const result = computePurchasingPower(financeInput);

  return {
    districtRegionId: Number(row.district_region_id),
    districtSlug: row.district_slug,
    districtName: row.district_name,
    regionGroup: row.region_group,
    effectiveTaxRate,
    maxPurchasePrice: result.maxPurchasePrice,
    budgetLimitedPrice: result.budgetLimitedPrice,
    dtiLimitedPrice: result.dtiLimitedPrice,
    bindingBound: result.bindingBound,
    annualRate: result.annualRate,
    monthlyCostFactor: result.monthlyCostFactor,
  };
}
