export type CreditBand = "excellent" | "good" | "fair";
export type BindingBound = "budget" | "dti";

export interface PurchasingPowerInput {
  monthlyBudget: number;
  effectiveTaxRate: number;
  baseAnnualRate?: number;
  downPaymentFraction?: number;
  insuranceAnnualRate?: number;
  pmiAnnualRate?: number;
  creditBand?: CreditBand;
  grossMonthlyIncome?: number;
  monthlyDebt?: number;
  maxDti?: number;
}

export interface PurchasingPowerResult {
  maxPurchasePrice: number;
  budgetLimitedPrice: number;
  dtiLimitedPrice: number | null;
  bindingBound: BindingBound;
  annualRate: number;
  monthlyPrincipalInterestFactor: number;
  monthlyCostFactor: number;
}

export const DEFAULT_ANNUAL_RATE = 0.0675;
export const DEFAULT_DOWN_PAYMENT_FRACTION = 0.2;
export const DEFAULT_INSURANCE_ANNUAL_RATE = 0.004;
export const DEFAULT_PMI_ANNUAL_RATE = 0.006;
export const DEFAULT_MAX_DTI = 0.36;

export const CREDIT_BAND_SPREADS: Record<CreditBand, number> = {
  excellent: 0,
  good: 0.004,
  fair: 0.009,
};

export function monthlyMortgageConstant(annualRate: number, termMonths = 360): number {
  if (annualRate < 0) throw new Error("annualRate must be non-negative");
  if (!Number.isInteger(termMonths) || termMonths <= 0) {
    throw new Error("termMonths must be a positive integer");
  }
  if (annualRate === 0) return 1 / termMonths;

  const monthlyRate = annualRate / 12;
  const growth = (1 + monthlyRate) ** termMonths;
  return (monthlyRate * growth) / (growth - 1);
}

export function computePurchasingPower(input: PurchasingPowerInput): PurchasingPowerResult {
  const monthlyBudget = requirePositive(input.monthlyBudget, "monthlyBudget");
  const effectiveTaxRate = requireNonNegative(input.effectiveTaxRate, "effectiveTaxRate");
  const downPaymentFraction = input.downPaymentFraction ?? DEFAULT_DOWN_PAYMENT_FRACTION;
  if (downPaymentFraction < 0 || downPaymentFraction >= 1) {
    throw new Error("downPaymentFraction must be at least 0 and less than 1");
  }

  const creditBand = input.creditBand ?? "good";
  const annualRate =
    requireNonNegative(input.baseAnnualRate ?? DEFAULT_ANNUAL_RATE, "baseAnnualRate") +
    CREDIT_BAND_SPREADS[creditBand];
  const insuranceAnnualRate = requireNonNegative(
    input.insuranceAnnualRate ?? DEFAULT_INSURANCE_ANNUAL_RATE,
    "insuranceAnnualRate",
  );
  const pmiAnnualRate = requireNonNegative(
    input.pmiAnnualRate ?? DEFAULT_PMI_ANNUAL_RATE,
    "pmiAnnualRate",
  );

  const mortgageFactor = (1 - downPaymentFraction) * monthlyMortgageConstant(annualRate);
  const pmiFactor =
    downPaymentFraction < 0.2 ? ((1 - downPaymentFraction) * pmiAnnualRate) / 12 : 0;
  const monthlyCostFactor =
    mortgageFactor + effectiveTaxRate / 12 + insuranceAnnualRate / 12 + pmiFactor;
  if (monthlyCostFactor <= 0) throw new Error("monthlyCostFactor must be positive");

  const budgetLimitedPrice = monthlyBudget / monthlyCostFactor;
  const dtiBudget = computeDtiHousingBudget(input);
  const dtiLimitedPrice = dtiBudget === null ? null : dtiBudget / monthlyCostFactor;
  const maxPurchasePrice =
    dtiLimitedPrice === null ? budgetLimitedPrice : Math.min(budgetLimitedPrice, dtiLimitedPrice);

  return {
    maxPurchasePrice,
    budgetLimitedPrice,
    dtiLimitedPrice,
    bindingBound:
      dtiLimitedPrice !== null && dtiLimitedPrice < budgetLimitedPrice ? "dti" : "budget",
    annualRate,
    monthlyPrincipalInterestFactor: mortgageFactor,
    monthlyCostFactor,
  };
}

function computeDtiHousingBudget(input: PurchasingPowerInput): number | null {
  if (input.grossMonthlyIncome === undefined) return null;
  const grossMonthlyIncome = requirePositive(input.grossMonthlyIncome, "grossMonthlyIncome");
  const monthlyDebt = requireNonNegative(input.monthlyDebt ?? 0, "monthlyDebt");
  const maxDti = requirePositive(input.maxDti ?? DEFAULT_MAX_DTI, "maxDti");
  return Math.max(grossMonthlyIncome * maxDti - monthlyDebt, 0);
}

function requirePositive(value: number, name: string): number {
  if (!Number.isFinite(value) || value <= 0) throw new Error(`${name} must be positive`);
  return value;
}

function requireNonNegative(value: number, name: string): number {
  if (!Number.isFinite(value) || value < 0) throw new Error(`${name} must be non-negative`);
  return value;
}
