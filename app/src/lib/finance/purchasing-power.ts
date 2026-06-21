export type CreditBand = "excellent" | "good" | "fair";
export type BindingBound = "budget" | "dti";

export interface PurchasingPowerInput {
  monthlyBudget: number;
  effectiveTaxRate: number;
  baseAnnualRate?: number;
  downPaymentAmount?: number;
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
  const mortgageConstant = monthlyMortgageConstant(annualRate);
  const dtiBudget = computeDtiHousingBudget(input);

  if (input.downPaymentAmount !== undefined) {
    const downPaymentAmount = requireNonNegative(input.downPaymentAmount, "downPaymentAmount");
    const monthlyCostAtPrice = (price: number) =>
      monthlyCostForPrice({
        price,
        downPaymentAmount,
        mortgageConstant,
        effectiveTaxRate,
        insuranceAnnualRate,
        pmiAnnualRate,
      });
    const budgetLimitedPrice = solveMaxPrice(monthlyBudget, monthlyCostAtPrice);
    const dtiLimitedPrice =
      dtiBudget === null ? null : solveMaxPrice(dtiBudget, monthlyCostAtPrice);
    const maxPurchasePrice =
      dtiLimitedPrice === null ? budgetLimitedPrice : Math.min(budgetLimitedPrice, dtiLimitedPrice);

    return {
      maxPurchasePrice,
      budgetLimitedPrice,
      dtiLimitedPrice,
      bindingBound:
        dtiLimitedPrice !== null && dtiLimitedPrice < budgetLimitedPrice ? "dti" : "budget",
      annualRate,
      monthlyPrincipalInterestFactor: monthlyPrincipalInterestAtPrice(
        maxPurchasePrice,
        downPaymentAmount,
        mortgageConstant,
      ),
      monthlyCostFactor:
        maxPurchasePrice > 0 ? monthlyCostAtPrice(maxPurchasePrice) / maxPurchasePrice : 0,
    };
  }

  const downPaymentFraction = input.downPaymentFraction ?? DEFAULT_DOWN_PAYMENT_FRACTION;
  if (downPaymentFraction < 0 || downPaymentFraction >= 1) {
    throw new Error("downPaymentFraction must be at least 0 and less than 1");
  }

  const mortgageFactor = (1 - downPaymentFraction) * mortgageConstant;
  const pmiFactor =
    downPaymentFraction < 0.2 ? ((1 - downPaymentFraction) * pmiAnnualRate) / 12 : 0;
  const monthlyCostFactor =
    mortgageFactor + effectiveTaxRate / 12 + insuranceAnnualRate / 12 + pmiFactor;
  if (monthlyCostFactor <= 0) throw new Error("monthlyCostFactor must be positive");

  const budgetLimitedPrice = monthlyBudget / monthlyCostFactor;
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

function monthlyCostForPrice({
  price,
  downPaymentAmount,
  mortgageConstant,
  effectiveTaxRate,
  insuranceAnnualRate,
  pmiAnnualRate,
}: {
  price: number;
  downPaymentAmount: number;
  mortgageConstant: number;
  effectiveTaxRate: number;
  insuranceAnnualRate: number;
  pmiAnnualRate: number;
}): number {
  if (price <= 0) return 0;
  const loanAmount = Math.max(price - downPaymentAmount, 0);
  const principalInterest = loanAmount * mortgageConstant;
  const taxAndInsurance = price * ((effectiveTaxRate + insuranceAnnualRate) / 12);
  const pmi = downPaymentAmount / price < 0.2 ? loanAmount * (pmiAnnualRate / 12) : 0;
  return principalInterest + taxAndInsurance + pmi;
}

function monthlyPrincipalInterestAtPrice(
  price: number,
  downPaymentAmount: number,
  mortgageConstant: number,
): number {
  if (price <= 0) return 0;
  return Math.max(price - downPaymentAmount, 0) * mortgageConstant;
}

function solveMaxPrice(
  monthlyLimit: number,
  monthlyCostAtPrice: (price: number) => number,
): number {
  if (monthlyLimit <= 0) return 0;
  let low = 0;
  let high = 250_000;
  while (monthlyCostAtPrice(high) <= monthlyLimit && high < 100_000_000) {
    low = high;
    high *= 2;
  }

  for (let i = 0; i < 80; i += 1) {
    const mid = (low + high) / 2;
    if (monthlyCostAtPrice(mid) <= monthlyLimit) {
      low = mid;
    } else {
      high = mid;
    }
  }
  return low;
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
