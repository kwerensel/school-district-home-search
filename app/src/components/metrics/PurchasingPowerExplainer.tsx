import {
  DEFAULT_INSURANCE_ANNUAL_RATE,
  DEFAULT_PMI_ANNUAL_RATE,
  type CreditBand,
} from "@/lib/finance/purchasing-power";
import { MetricExplainer } from "./MetricExplainer";

const percent = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 2,
});

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

export function PurchasingPowerExplainer({
  annualRate,
  effectiveTaxRate,
  monthlyBudget,
  downPaymentAmount,
  creditBand,
  compact = false,
}: {
  annualRate: number;
  effectiveTaxRate: number;
  monthlyBudget: number;
  downPaymentAmount: number;
  creditBand: CreditBand;
  compact?: boolean;
}) {
  return (
    <MetricExplainer compact={compact} label="How calculated" title="Estimated max home price">
      <p>
        Estimated max home price your monthly housing budget may support. This is planning math, not
        a lender preapproval.
      </p>
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 rounded-md bg-muted p-3 text-xs">
        <dt>Monthly housing budget</dt>
        <dd className="font-medium text-foreground">{currency.format(monthlyBudget)}</dd>
        <dt>Down payment</dt>
        <dd className="font-medium text-foreground">{currency.format(downPaymentAmount)}</dd>
        <dt>Rate used ({creditBand} credit)</dt>
        <dd className="font-medium text-foreground">{percent.format(annualRate)}</dd>
        <dt>District property-tax rate</dt>
        <dd className="font-medium text-foreground">{percent.format(effectiveTaxRate)}</dd>
        <dt>Homeowners insurance assumption</dt>
        <dd className="font-medium text-foreground">
          {percent.format(DEFAULT_INSURANCE_ANNUAL_RATE)} / year
        </dd>
        <dt>PMI assumption when under 20% down</dt>
        <dd className="font-medium text-foreground">
          {percent.format(DEFAULT_PMI_ANNUAL_RATE)} / year
        </dd>
      </dl>
      <p>
        Uses a 30-year mortgage. It excludes closing costs, HOA fees, utilities, maintenance, and
        lender-specific underwriting. The rate shown is the app&apos;s current fallback assumption
        plus the selected credit-band adjustment.
      </p>
    </MetricExplainer>
  );
}
