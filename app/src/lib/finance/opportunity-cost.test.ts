import { describe, expect, it } from "vitest";
import { computeOpportunityCost } from "./opportunity-cost";

describe("opportunity cost", () => {
  it("preserves cash exactly at zero return", () => {
    const result = computeOpportunityCost({
      monthlyContribution: 500,
      upfrontCapital: 10000,
      years: 10,
      annualReturn: 0,
    });
    expect(result.futureValue).toBe(70000);
    expect(result.modeledGrowth).toBe(0);
  });
  it("compounds an effective annual return rather than dividing it by twelve", () => {
    const result = computeOpportunityCost({
      monthlyContribution: 0,
      upfrontCapital: 10000,
      years: 2,
      annualReturn: 0.1,
    });
    expect(result.futureValue).toBeCloseTo(12100, 5);
  });
  it("uses end-of-month contributions and supports negative hypothetical returns", () => {
    const result = computeOpportunityCost({
      monthlyContribution: 100,
      upfrontCapital: 0,
      years: 1,
      annualReturn: -0.12,
    });
    const monthly = 0.88 ** (1 / 12);
    const independent = Array.from({ length: 12 }, (_, i) => 100 * monthly ** i).reduce(
      (a, b) => a + b,
      0,
    );
    expect(result.futureValue).toBeCloseTo(independent, 6);
    expect(result.futureValue).toBeLessThan(1200);
  });
  it.each([NaN, Infinity, -1])("rejects invalid cash inputs %s", (monthlyContribution) => {
    expect(() =>
      computeOpportunityCost({
        monthlyContribution,
        upfrontCapital: 0,
        years: 10,
        annualReturn: 0,
      }),
    ).toThrow();
  });
});

import { computeHousingCashFlow, computeHousingOpportunity } from "./opportunity-cost";

describe("same-price housing comparison", () => {
  const base = {
    purchasePrice: 500000,
    downPayment: 100000,
    annualRate: 0,
    effectiveTaxRate: 0.02,
    monthlyBudget: 5000,
    additionalMonthlyCosts: 200,
  };
  it("isolates tax differences without double-counting", () => {
    const lower = computeHousingCashFlow(base);
    const higher = computeHousingCashFlow({ ...base, effectiveTaxRate: 0.03 });
    expect(higher.monthlyTotal - lower.monthlyTotal).toBeCloseTo((500000 * 0.01) / 12, 8);
    expect(lower.housingBudgetHeadroom - higher.housingBudgetHeadroom).toBeCloseTo(
      (500000 * 0.01) / 12,
      8,
    );
    expect(lower.principalInterest).toBeCloseTo(400000 / 360);
    expect(lower.pmi).toBe(0);
  });
  it("includes additional costs and PMI only when applicable", () => {
    const result = computeHousingCashFlow({ ...base, downPayment: 50000 });
    expect(result.pmi).toBe(225);
    expect(result.monthlyTotal).toBeCloseTo(
      result.principalInterest + result.taxes + result.insurance + result.pmi + 200,
    );
  });
  it("handles a cash purchase without negative loan costs", () => {
    const result = computeHousingCashFlow({ ...base, downPayment: 600000 });
    expect(result.principalInterest).toBe(0);
    expect(result.pmi).toBe(0);
    expect(result.taxes).toBeGreaterThan(0);
  });
});

describe("housing-cost opportunity difference", () => {
  it("isolates the same cash difference when compared in reverse", () => {
    const forward = computeHousingOpportunity(2000, 2500, { years: 10, annualReturn: 0 });
    const reverse = computeHousingOpportunity(2500, 2000, { years: 10, annualReturn: 0 });
    expect(forward.monthlyDifference).toBe(500);
    expect(reverse.monthlyDifference).toBe(-500);
    expect(forward.cheaper).toBe("a");
    expect(reverse.cheaper).toBe("b");
    expect(forward.investment.futureValue).toBe(60000);
    expect(reverse.investment.futureValue).toBe(60000);
  });
  it("does not invent an opportunity difference when housing costs are equal", () => {
    expect(
      computeHousingOpportunity(2000, 2000, { years: 10, annualReturn: 0.1 }).investment
        .futureValue,
    ).toBe(0);
  });
  it("preserves numerical stability for tiny assumed returns", () => {
    const result = computeOpportunityCost({
      monthlyContribution: 500,
      upfrontCapital: 0,
      years: 10,
      annualReturn: 1e-14,
    });
    expect(result.futureValue).toBeCloseTo(60000, 5);
  });
});
