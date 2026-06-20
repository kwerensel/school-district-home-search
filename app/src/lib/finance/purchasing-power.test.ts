import { describe, expect, it } from "vitest";
import {
  computePurchasingPower,
  CREDIT_BAND_SPREADS,
  monthlyMortgageConstant,
} from "./purchasing-power";

describe("purchasing power", () => {
  it("computes the standard mortgage payment constant", () => {
    expect(monthlyMortgageConstant(0.06)).toBeCloseTo(0.0059955, 6);
  });

  it("applies credit-band spreads to the base rate", () => {
    const excellent = computePurchasingPower({
      monthlyBudget: 5500,
      effectiveTaxRate: 0.02,
      baseAnnualRate: 0.065,
      creditBand: "excellent",
    });
    const fair = computePurchasingPower({
      monthlyBudget: 5500,
      effectiveTaxRate: 0.02,
      baseAnnualRate: 0.065,
      creditBand: "fair",
    });

    expect(fair.annualRate - excellent.annualRate).toBeCloseTo(CREDIT_BAND_SPREADS.fair, 6);
    expect(fair.maxPurchasePrice).toBeLessThan(excellent.maxPurchasePrice);
  });

  it("reduces purchasing power when down payment triggers PMI", () => {
    const twentyDown = computePurchasingPower({
      monthlyBudget: 5500,
      effectiveTaxRate: 0.02,
      baseAnnualRate: 0.065,
      downPaymentFraction: 0.2,
    });
    const tenDown = computePurchasingPower({
      monthlyBudget: 5500,
      effectiveTaxRate: 0.02,
      baseAnnualRate: 0.065,
      downPaymentFraction: 0.1,
    });

    expect(tenDown.maxPurchasePrice).toBeLessThan(twentyDown.maxPurchasePrice);
  });

  it("uses DTI as a second ceiling when it is tighter than budget", () => {
    const result = computePurchasingPower({
      monthlyBudget: 5500,
      effectiveTaxRate: 0.02,
      grossMonthlyIncome: 11000,
      monthlyDebt: 900,
      maxDti: 0.36,
    });

    expect(result.bindingBound).toBe("dti");
    expect(result.dtiLimitedPrice).not.toBeNull();
    expect(result.maxPurchasePrice).toBe(result.dtiLimitedPrice);
  });

  it("preserves the Hudson Valley over Lower Merion ordering when taxes are lower", () => {
    const hudsonValley = computePurchasingPower({
      monthlyBudget: 5500,
      effectiveTaxRate: 0.018,
      baseAnnualRate: 0.065,
    });
    const lowerMerion = computePurchasingPower({
      monthlyBudget: 5500,
      effectiveTaxRate: 0.026,
      baseAnnualRate: 0.065,
    });

    expect(hudsonValley.maxPurchasePrice).toBeGreaterThan(lowerMerion.maxPurchasePrice);
  });
});
