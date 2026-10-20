import type { WeightKey } from "./profile";
import type { DistrictEnvironmentMetrics } from "../finance/server-data";

export type ComparisonMetric = keyof DistrictEnvironmentMetrics | "effectiveTaxRate";
export const ROW_PREFERENCES: Partial<
  Record<ComparisonMetric, { key: WeightKey; label: string; direction: "higher" | "lower" }>
> = {
  effectiveTaxRate: { key: "affordability", label: "Local price reach", direction: "lower" },
  medianHomeValue: { key: "affordability", label: "Local price reach", direction: "lower" },
  treeCanopyPct: { key: "green", label: "Tree cover", direction: "higher" },
  canopyHeightM: { key: "green", label: "Tree cover", direction: "higher" },
  walkabilityIndex: { key: "walkability", label: "EPA walkability", direction: "higher" },
  riskIndex: { key: "lowerRisk", label: "Lower risk", direction: "lower" },
  floodSfha: { key: "lowerFlood", label: "Lower flood", direction: "lower" },
  lightPollutionRadiance: { key: "darkSkies", label: "Darker skies", direction: "lower" },
  parkAccess: { key: "parkAccess", label: "Park access", direction: "higher" },
};

export type CellHighlight = { tone: "strongest" | "weakest" | "neutral"; label: string } | null;

// Compare at the displayed precision so visually identical values never get opposing labels.
export function compareRowValues(
  values: Array<number | null>,
  direction: "higher" | "lower" | null,
  { scale = 1, digits = 2 }: { scale?: number; digits?: number } = {},
): CellHighlight[] {
  const rounded = values.map((value) =>
    value === null || !Number.isFinite(value) ? null : Number((value * scale).toFixed(digits)),
  );
  const known = rounded.filter((value): value is number => value !== null);
  if (known.length < 2) return values.map(() => null);
  const min = Math.min(...known);
  const max = Math.max(...known);
  return rounded.map((value) => {
    if (value === null) return null;
    if (min === max) return { tone: "neutral", label: "Tied" };
    if (value !== min && value !== max) return null;
    const tied = known.filter((entry) => entry === value).length > 1;
    if (!direction)
      return {
        tone: "neutral",
        label: `${value === max ? "Highest" : "Lowest"}${tied ? " (tied)" : ""}`,
      };
    const strongest = direction === "higher" ? value === max : value === min;
    return {
      tone: strongest ? "strongest" : "weakest",
      label: `${strongest ? "Strongest" : "Weakest"}${tied ? " (tied)" : ""}`,
    };
  });
}
