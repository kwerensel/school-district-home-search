import { z } from "zod";
import {
  monthlyMortgageConstant,
  DEFAULT_INSURANCE_ANNUAL_RATE,
  DEFAULT_PMI_ANNUAL_RATE,
} from "./purchasing-power";

export const OpportunityCostSchema = z
  .object({
    monthlyContribution: z.number().finite().min(0).max(100000),
    upfrontCapital: z.number().finite().min(0).max(100000000),
    years: z.number().int().min(1).max(50),
    annualReturn: z.number().finite().min(-0.5).max(0.3),
  })
  .strict();

export type OpportunityCostInput = z.infer<typeof OpportunityCostSchema>;

/** End-of-month contributions; effective annual nominal return; no tax/inflation adjustment. */
export function computeOpportunityCost(input: OpportunityCostInput) {
  const assumptions = OpportunityCostSchema.parse(input);
  const months = assumptions.years * 12;
  const monthlyRate = Math.expm1(Math.log1p(assumptions.annualReturn) / 12);
  const logGrowth = (Math.log1p(assumptions.annualReturn) / 12) * months;
  const growth = Math.exp(logGrowth);
  const contributions = assumptions.monthlyContribution * months;
  const annuity = monthlyRate === 0 ? months : Math.expm1(logGrowth) / monthlyRate;
  const futureValue =
    assumptions.upfrontCapital * growth + assumptions.monthlyContribution * annuity;
  return {
    assumptions,
    contributedCapital: assumptions.upfrontCapital + contributions,
    futureValue,
    modeledGrowth: futureValue - assumptions.upfrontCapital - contributions,
    monthlyRate,
    timing: "end-of-month" as const,
    limitations:
      "Hypothetical constant return; excludes taxes, fees, inflation and housing equity. This is not a buy-versus-rent or total-wealth comparison.",
  };
}

export const HousingScenarioSchema = z
  .object({
    purchasePrice: z.number().finite().positive().max(100000000),
    additionalMonthlyCosts: z.number().finite().min(0).max(100000),
  })
  .strict();

/** Same-price comparison: taxes are included once, never subtracted again. */
export function computeHousingCashFlow(
  input: z.infer<typeof HousingScenarioSchema> & {
    downPayment: number;
    annualRate: number;
    effectiveTaxRate: number;
    monthlyBudget: number;
  },
) {
  const scenario = HousingScenarioSchema.parse({
    purchasePrice: input.purchasePrice,
    additionalMonthlyCosts: input.additionalMonthlyCosts,
  });
  for (const key of ["downPayment", "annualRate", "effectiveTaxRate", "monthlyBudget"] as const) {
    if (!Number.isFinite(input[key]) || input[key] < 0) throw new Error(`Invalid ${key}`);
  }
  const loan = Math.max(scenario.purchasePrice - input.downPayment, 0);
  const principalInterest = loan * monthlyMortgageConstant(input.annualRate);
  const taxes = (scenario.purchasePrice * input.effectiveTaxRate) / 12;
  const insurance = (scenario.purchasePrice * DEFAULT_INSURANCE_ANNUAL_RATE) / 12;
  const pmi =
    input.downPayment / scenario.purchasePrice < 0.2 ? (loan * DEFAULT_PMI_ANNUAL_RATE) / 12 : 0;
  const monthlyTotal =
    principalInterest + taxes + insurance + pmi + scenario.additionalMonthlyCosts;
  return {
    principalInterest,
    taxes,
    insurance,
    pmi,
    additionalMonthlyCosts: scenario.additionalMonthlyCosts,
    monthlyTotal,
    housingBudgetHeadroom: input.monthlyBudget - monthlyTotal,
    assumedInsuranceAnnualRate: DEFAULT_INSURANCE_ANNUAL_RATE,
    assumedPmiAnnualRate: DEFAULT_PMI_ANNUAL_RATE,
  };
}

/** Isolate redirecting a monthly housing-cost difference, with no extra upfront investment. */
export function computeHousingOpportunity(
  monthlyCostA: number,
  monthlyCostB: number,
  assumptions: Pick<OpportunityCostInput, "years" | "annualReturn">,
) {
  if (![monthlyCostA, monthlyCostB].every((cost) => Number.isFinite(cost) && cost >= 0)) {
    throw new Error("Monthly housing costs must be finite and nonnegative");
  }
  const monthlyDifference = monthlyCostB - monthlyCostA;
  const investment = computeOpportunityCost({
    ...assumptions,
    monthlyContribution: Math.abs(monthlyDifference),
    upfrontCapital: 0,
  });
  return {
    monthlyDifference,
    cheaper: monthlyDifference > 0 ? "a" : monthlyDifference < 0 ? "b" : "equal",
    investment,
  };
}
