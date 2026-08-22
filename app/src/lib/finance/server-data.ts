import { z } from "zod";
import { computePurchasingPower } from "./purchasing-power";
import { DEFAULT_ANNUAL_RATE } from "./purchasing-power";
import type { MortgageRateAssumption } from "./rates";
import type { BindingBound, CreditBand, PurchasingPowerInput } from "./purchasing-power";

export const PurchasingPowerQuerySchema = z.object({
  monthlyBudget: z.number().positive(),
  baseAnnualRate: z.number().min(0).optional(),
  downPaymentAmount: z.number().min(0).optional(),
  downPaymentFraction: z.number().min(0).lt(1).optional(),
  insuranceAnnualRate: z.number().min(0).optional(),
  pmiAnnualRate: z.number().min(0).optional(),
  creditBand: z.enum(["excellent", "good", "fair"]).optional(),
  grossMonthlyIncome: z.number().positive().optional(),
  monthlyDebt: z.number().min(0).optional(),
  maxDti: z.number().positive().max(1).optional(),
  regionGroup: z.enum(["pa-mainline", "hudson-valley"]).optional(),
  environmentWeights: z
    .object({
      affordability: z.number().min(0).max(10).optional(),
      green: z.number().min(0).max(10).optional(),
      walkability: z.number().min(0).max(10).optional(),
      lowerRisk: z.number().min(0).max(10).optional(),
      lowerFlood: z.number().min(0).max(10).optional(),
      darkSkies: z.number().min(0).max(10).optional(),
      parkAccess: z.number().min(0).max(10).optional(),
    })
    .optional(),
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
  canopy_height_m: number | string | null;
  tree_canopy_pct: number | string | null;
  median_home_value: number | string | null;
  walkability_index: number | string | null;
  risk_index: number | string | null;
  flood_sfha: number | string | null;
  light_pollution_radiance: number | string | null;
  park_access: number | string | null;
};

export type DistrictEnvironmentMetrics = {
  canopyHeightM: number | null;
  treeCanopyPct: number | null;
  medianHomeValue: number | null;
  walkabilityIndex: number | null;
  riskIndex: number | null;
  floodSfha: number | null;
  lightPollutionRadiance: number | null;
  parkAccess: number | null;
};

export type DistrictPurchasingPower = {
  districtRegionId: number;
  districtSlug: string;
  districtName: string;
  regionGroup: string;
  effectiveTaxRate: number;
  environmentMetrics: DistrictEnvironmentMetrics;
  matchComponents: Record<
    keyof Required<NonNullable<PurchasingPowerQuery["environmentWeights"]>>,
    number | null
  >;
  matchScore: number;
  affordabilityRatio: number | null;
  maxPurchasePrice: number;
  budgetLimitedPrice: number;
  dtiLimitedPrice: number | null;
  bindingBound: BindingBound;
  annualRate: number;
  monthlyCostFactor: number;
};

export type PurchasingPowerPayload = {
  districts: DistrictPurchasingPower[];
  rateAssumption: MortgageRateAssumption;
};

type ScoreKey = NonNullable<PurchasingPowerQuery["environmentWeights"]>;

export function buildDistrictTaxRateSql(input: Pick<PurchasingPowerQuery, "regionGroup">) {
  const values: unknown[] = [];
  const metricKeys = [
    "effective_tax_rate",
    "canopy_height_m",
    "tree_canopy_pct",
    "median_home_value",
    "walkability_index",
    "risk_index",
    "flood_sfha",
    "light_pollution_radiance",
    "park_access",
  ];
  const where = [`dm.metric_key = ANY($1)`];
  values.push(metricKeys);

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
        max(dm.value) FILTER (WHERE dm.metric_key = 'effective_tax_rate') AS effective_tax_rate,
        max(dm.value) FILTER (WHERE dm.metric_key = 'canopy_height_m') AS canopy_height_m,
        max(dm.value) FILTER (WHERE dm.metric_key = 'tree_canopy_pct') AS tree_canopy_pct,
        max(dm.value) FILTER (WHERE dm.metric_key = 'median_home_value') AS median_home_value,
        max(dm.value) FILTER (WHERE dm.metric_key = 'walkability_index') AS walkability_index,
        max(dm.value) FILTER (WHERE dm.metric_key = 'risk_index') AS risk_index,
        max(dm.value) FILTER (WHERE dm.metric_key = 'flood_sfha') AS flood_sfha,
        max(dm.value) FILTER (WHERE dm.metric_key = 'light_pollution_radiance') AS light_pollution_radiance,
        max(dm.value) FILTER (WHERE dm.metric_key = 'park_access') AS park_access
      FROM district_metrics dm
      JOIN regions d ON d.id = dm.district_region_id
      WHERE ${where.join(" AND ")}
      GROUP BY d.id, d.slug, d.name, d.region_group
      HAVING max(dm.value) FILTER (WHERE dm.metric_key = 'effective_tax_rate') IS NOT NULL
      ORDER BY d.region_group, d.name
    `,
    values,
  };
}

export async function fetchDistrictPurchasingPower(
  input: PurchasingPowerQuery,
  execute: QueryExecutor<DistrictPurchasingPowerRow>,
  fetchedRate?: MortgageRateAssumption,
): Promise<PurchasingPowerPayload> {
  const rateAssumption: MortgageRateAssumption =
    input.baseAnnualRate !== undefined
      ? { annualRate: input.baseAnnualRate, source: "user", observationDate: null }
      : (fetchedRate ?? {
          annualRate: DEFAULT_ANNUAL_RATE,
          source: "fallback",
          observationDate: null,
        });
  const resolvedInput = { ...input, baseAnnualRate: rateAssumption.annualRate };
  const fragment = buildDistrictTaxRateSql(resolvedInput);
  const rows = await execute(fragment.text, fragment.values);
  const districts = rows.map((row) => computeDistrictPurchasingPower(resolvedInput, row));

  return {
    districts: addMatchScores(districts, resolvedInput.environmentWeights),
    rateAssumption,
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
    downPaymentAmount: input.downPaymentAmount,
    downPaymentFraction: input.downPaymentFraction,
    insuranceAnnualRate: input.insuranceAnnualRate,
    pmiAnnualRate: input.pmiAnnualRate,
    creditBand: input.creditBand as CreditBand | undefined,
    grossMonthlyIncome: input.grossMonthlyIncome,
    monthlyDebt: input.monthlyDebt,
    maxDti: input.maxDti,
  };
  const result = computePurchasingPower(financeInput);
  const medianHomeValue = nullableNumber(row.median_home_value);
  const affordabilityRatio =
    medianHomeValue !== null && medianHomeValue > 0
      ? result.maxPurchasePrice / medianHomeValue
      : null;

  return {
    districtRegionId: Number(row.district_region_id),
    districtSlug: row.district_slug,
    districtName: row.district_name,
    regionGroup: row.region_group,
    effectiveTaxRate,
    environmentMetrics: {
      canopyHeightM: nullableNumber(row.canopy_height_m),
      treeCanopyPct: nullableNumber(row.tree_canopy_pct),
      medianHomeValue,
      walkabilityIndex: nullableNumber(row.walkability_index),
      riskIndex: nullableNumber(row.risk_index),
      floodSfha: nullableNumber(row.flood_sfha),
      lightPollutionRadiance: nullableNumber(row.light_pollution_radiance),
      parkAccess: nullableNumber(row.park_access),
    },
    matchComponents: {
      affordability: null,
      green: null,
      walkability: null,
      lowerRisk: null,
      lowerFlood: null,
      darkSkies: null,
      parkAccess: null,
    },
    matchScore: 0,
    affordabilityRatio,
    maxPurchasePrice: result.maxPurchasePrice,
    budgetLimitedPrice: result.budgetLimitedPrice,
    dtiLimitedPrice: result.dtiLimitedPrice,
    bindingBound: result.bindingBound,
    annualRate: result.annualRate,
    monthlyCostFactor: result.monthlyCostFactor,
  };
}

function nullableNumber(value: number | string | null | undefined) {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function addMatchScores(
  districts: DistrictPurchasingPower[],
  weights: PurchasingPowerQuery["environmentWeights"],
) {
  const normalizedWeights = {
    affordability: weights?.affordability ?? 5,
    green: weights?.green ?? 2,
    walkability: weights?.walkability ?? 2,
    lowerRisk: weights?.lowerRisk ?? 1,
    lowerFlood: weights?.lowerFlood ?? 1,
    darkSkies: weights?.darkSkies ?? 1,
    parkAccess: weights?.parkAccess ?? 1,
  } satisfies Required<ScoreKey>;

  const scoreInputs = {
    affordability: districtScores(
      districts,
      (district) => district.affordabilityRatio ?? district.maxPurchasePrice,
      "higher",
    ),
    green: averagedScores([
      districtScores(districts, (district) => district.environmentMetrics.canopyHeightM, "higher"),
      districtScores(districts, (district) => district.environmentMetrics.treeCanopyPct, "higher"),
    ]),
    walkability: districtScores(
      districts,
      (district) => district.environmentMetrics.walkabilityIndex,
      "higher",
    ),
    lowerRisk: districtScores(
      districts,
      (district) => district.environmentMetrics.riskIndex,
      "lower",
    ),
    lowerFlood: districtScores(
      districts,
      (district) => district.environmentMetrics.floodSfha,
      "lower",
    ),
    darkSkies: districtScores(
      districts,
      (district) => district.environmentMetrics.lightPollutionRadiance,
      "lower",
    ),
    parkAccess: districtScores(
      districts,
      (district) => district.environmentMetrics.parkAccess,
      "higher",
    ),
  };

  return districts.map((district) => {
    let weightedTotal = 0;
    let weightTotal = 0;
    for (const key of Object.keys(normalizedWeights) as Array<keyof typeof normalizedWeights>) {
      const weight = normalizedWeights[key];
      const score = scoreInputs[key].get(district.districtSlug);
      if (score === undefined || weight <= 0) continue;
      weightedTotal += score * weight;
      weightTotal += weight;
    }
    return {
      ...district,
      matchComponents: {
        affordability: scoreInputs.affordability.get(district.districtSlug) ?? null,
        green: scoreInputs.green.get(district.districtSlug) ?? null,
        walkability: scoreInputs.walkability.get(district.districtSlug) ?? null,
        lowerRisk: scoreInputs.lowerRisk.get(district.districtSlug) ?? null,
        lowerFlood: scoreInputs.lowerFlood.get(district.districtSlug) ?? null,
        darkSkies: scoreInputs.darkSkies.get(district.districtSlug) ?? null,
        parkAccess: scoreInputs.parkAccess.get(district.districtSlug) ?? null,
      },
      matchScore: weightTotal > 0 ? weightedTotal / weightTotal : 0,
    };
  });
}

function districtScores(
  districts: DistrictPurchasingPower[],
  getValue: (district: DistrictPurchasingPower) => number | null,
  direction: "higher" | "lower",
) {
  const values = districts
    .map((district) => getValue(district))
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const scores = new Map<string, number>();
  for (const district of districts) {
    const value = getValue(district);
    if (value === null || !Number.isFinite(value)) continue;
    const rank = max === min ? 0.5 : (value - min) / (max - min);
    scores.set(district.districtSlug, (direction === "higher" ? rank : 1 - rank) * 100);
  }
  return scores;
}

function averagedScores(scoreMaps: Array<Map<string, number>>) {
  const scores = new Map<string, number>();
  const slugs = new Set(scoreMaps.flatMap((scoreMap) => [...scoreMap.keys()]));
  for (const slug of slugs) {
    const values = scoreMaps
      .map((scoreMap) => scoreMap.get(slug))
      .filter((value): value is number => value !== undefined);
    if (values.length)
      scores.set(slug, values.reduce((sum, value) => sum + value, 0) / values.length);
  }
  return scores;
}
