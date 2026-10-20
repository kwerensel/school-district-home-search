import { PreferenceWeights, type PreferenceWeightsProps } from "./PreferenceWeights";
import {
  compareRowValues,
  ROW_PREFERENCES,
  type CellHighlight,
} from "@/lib/discovery/comparison-highlights";
import type { WeightKey } from "@/lib/discovery/profile";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type {
  DistrictPurchasingPower,
  DistrictEnvironmentMetrics,
} from "@/lib/finance/server-data";

const decimal = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const dollars = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 2 });
const rows: Array<{
  label: string;
  key: keyof DistrictEnvironmentMetrics;
  unit?: string;
  fraction?: boolean;
  currency?: boolean;
  note?: string;
}> = [
  { label: "Tree cover", key: "treeCanopyPct", unit: "%" },
  {
    label: "EPA walkability",
    key: "walkabilityIndex",
    unit: " / 20",
    note: "Higher is more walkable",
  },
  { label: "District median home value", key: "medianHomeValue", currency: true },
  { label: "Average canopy height", key: "canopyHeightM", unit: " m" },
  { label: "Natural-hazard risk", key: "riskIndex", unit: " / 100", note: "Lower is less risk" },
  {
    label: "FEMA flood-zone land",
    key: "floodSfha",
    fraction: true,
    note: "Share of district land",
  },
  {
    label: "Light pollution",
    key: "lightPollutionRadiance",
    unit: " radiance",
    note: "Lower is darker",
  },
  { label: "Park access", key: "parkAccess", fraction: true, note: "District land within 800 m" },
  {
    label: "Transit-stop density",
    key: "transitAccess",
    unit: " stops/km²",
    note: "Mapped stops; not service frequency",
  },
  {
    label: "Drive time to city anchor",
    key: "commuteMinutes",
    unit: " min",
    note: "Anchor named in each cell; not live traffic",
  },
  {
    label: "Annual mean daily AQI",
    key: "aqiAnnualMean",
    unit: " AQI",
    note: "Lower is cleaner; coarse context",
  },
  {
    label: "Transportation noise exposure",
    key: "noisePctOver55",
    unit: "%",
    note: "District area modeled at ≥55 dBA",
  },
  { label: "Modeled mean transportation noise", key: "noiseMeanDba", unit: " dBA" },
  {
    label: "Emergency-response facilities",
    key: "noiseSirenDensity",
    unit: " facilities/km²",
    note: "Mapped density; not measured noise",
  },
  {
    label: "Nightlife venues",
    key: "noiseNightlifeDensity",
    unit: " venues/km²",
    note: "Mapped density; not measured noise",
  },
  {
    label: "Industrial land",
    key: "noiseIndustrialLandPct",
    unit: "%",
    note: "Mapped land share; not measured noise",
  },
  {
    label: "Freight-capable rail",
    key: "noiseFreightRailDensity",
    unit: " rail km/km²",
    note: "Mapped density; not measured noise",
  },
];

type ComparisonProps = { districts: DistrictPurchasingPower[]; weights: Record<WeightKey, number> };

function HighlightCell({ highlight, children }: { highlight: CellHighlight; children: ReactNode }) {
  const style =
    highlight?.tone === "strongest"
      ? "bg-emerald-50 text-emerald-950 dark:bg-emerald-950 dark:text-emerald-100"
      : highlight?.tone === "weakest"
        ? "bg-amber-50 text-amber-950 dark:bg-amber-950 dark:text-amber-100"
        : "";
  return (
    <td className={`border-b p-3 align-top tabular-nums ${style}`}>
      {children}
      {highlight && (
        <span
          className={`mt-1 block text-[10px] font-semibold ${highlight.tone === "neutral" ? "text-muted-foreground" : ""}`}
        >
          {highlight.label}
        </span>
      )}
    </td>
  );
}

function HighlightLegend() {
  return (
    <p className="text-xs leading-5 text-muted-foreground">
      <span className="rounded bg-emerald-50 px-1 text-emerald-950">Strongest</span>
      {" / "}
      <span className="rounded bg-amber-50 px-1 text-amber-950">Weakest</span> within your shortlist
      for active priorities. Row labels show priority weight out of 10 and preferred direction.
      Other rows show neutral highest/lowest values. Ties use displayed precision; missing values
      are excluded. Tax and median-value highlights follow local price reach; they are not the
      overall affordability score.
    </p>
  );
}

function ComparisonTable({
  districts,
  weights,
  expanded = false,
}: ComparisonProps & { expanded?: boolean }) {
  const affordabilityActive = weights.affordability > 0;
  const taxHighlights = compareRowValues(
    districts.map((district) => district.effectiveTaxRate),
    affordabilityActive ? "lower" : null,
    { scale: 100 },
  );
  return (
    <div
      className={`${expanded ? "min-h-0 flex-1" : "max-h-[55vh]"} overflow-auto rounded-md border focus-visible:outline-2 focus-visible:outline-ring`}
      role="region"
      aria-label="Scrollable district values"
      tabIndex={0}
    >
      <table className="w-full border-separate border-spacing-0 text-left text-xs">
        <caption className="sr-only">
          Verified district values for the current shortlist, ordered by preference match
        </caption>
        <thead>
          <tr>
            <th scope="col" className="sticky top-0 left-0 z-30 min-w-36 border-b bg-muted p-3">
              Tradeoff
            </th>
            {districts.map((district, index) => (
              <th
                scope="col"
                key={district.districtSlug}
                className="sticky top-0 z-20 min-w-36 border-b bg-muted p-3 align-top"
              >
                {district.districtName}
                <span className="mt-1 block font-normal text-muted-foreground">
                  Match #{index + 1} of {districts.length}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row" className="sticky left-0 z-10 border-b bg-background p-3 font-medium">
              Effective property-tax rate
              <span className="mt-1 block text-primary">
                {affordabilityActive
                  ? `Local price reach ${weights.affordability}/10 · lower preferred`
                  : "Local price reach off"}
              </span>
              <span className="mt-1 block font-normal text-muted-foreground">
                Area estimate; not a home's tax bill
              </span>
            </th>
            {districts.map((district, index) => (
              <HighlightCell key={district.districtSlug} highlight={taxHighlights[index]}>
                {percent.format(district.effectiveTaxRate)}
              </HighlightCell>
            ))}
          </tr>
          {rows.map((row) => {
            const preference = ROW_PREFERENCES[row.key];
            const active = preference && weights[preference.key] > 0;
            // Different city destinations are not a comparable commute benchmark.
            const mixedAnchors =
              row.key === "commuteMinutes" &&
              new Set(districts.map((district) => district.regionGroup)).size > 1;
            const highlights = mixedAnchors
              ? districts.map(() => null)
              : compareRowValues(
                  districts.map((district) => district.environmentMetrics[row.key]),
                  active ? preference.direction : null,
                  { scale: row.fraction ? 100 : 1, digits: row.currency ? 0 : 2 },
                );
            return (
              <tr key={row.key}>
                <th
                  scope="row"
                  className="sticky left-0 z-10 border-b bg-background p-3 font-medium"
                >
                  {row.label}
                  <span className="mt-1 block text-primary">
                    {preference
                      ? active
                        ? `${preference.label} ${weights[preference.key]}/10 · ${preference.direction} preferred`
                        : `${preference.label} off`
                      : mixedAnchors
                        ? "Different destinations; not ranked"
                        : "Context only · no matching priority"}
                  </span>
                  {row.note && (
                    <span className="mt-1 block font-normal text-muted-foreground">{row.note}</span>
                  )}
                </th>
                {districts.map((district, index) => {
                  const value = district.environmentMetrics[row.key];
                  const formatted =
                    value === null
                      ? "Unavailable"
                      : row.currency
                        ? dollars.format(value)
                        : row.fraction
                          ? percent.format(value)
                          : `${decimal.format(value)}${row.unit ?? ""}`;
                  return (
                    <HighlightCell key={district.districtSlug} highlight={highlights[index]}>
                      {formatted}
                      {row.key === "commuteMinutes" && (
                        <span className="mt-1 block text-muted-foreground">
                          {district.regionGroup === "pa-mainline"
                            ? "Center City Philadelphia"
                            : "Grand Central Terminal"}
                        </span>
                      )}
                    </HighlightCell>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Sources({ districts }: { districts: DistrictPurchasingPower[] }) {
  return (
    <details className="max-h-[20vh] shrink-0 overflow-y-auto text-xs text-muted-foreground">
      <summary className="cursor-pointer">Sources and vintages</summary>
      {districts.map((district) => (
        <div key={district.districtSlug} className="mt-3">
          <p className="font-semibold text-foreground">{district.districtName}</p>
          {district.metricProvenance?.length ? (
            <ul className="mt-1 space-y-1">
              {district.metricProvenance.map((source, index) => (
                <li key={`${source.metricKey}-${index}`}>
                  {source.metricKey}: {source.source ?? "Source unavailable"} · {source.vintage}
                  {source.nativeResolution ? ` · ${source.nativeResolution}` : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p>Source metadata unavailable.</p>
          )}
        </div>
      ))}
    </details>
  );
}

export function ShortlistComparison({
  districts,
  weights,
  onWeightChange,
  onResetWeights,
}: ComparisonProps &
  PreferenceWeightsProps & { onResetWeights: (weights: Record<WeightKey, number>) => void }) {
  const [openingWeights, setOpeningWeights] = useState<Record<WeightKey, number> | null>(null);
  const changed =
    openingWeights !== null &&
    (Object.keys(openingWeights) as WeightKey[]).some(
      (key) => weights[key] !== openingWeights[key],
    );
  if (districts.length < 2) return null;
  return (
    <section
      className="min-w-0 space-y-3 rounded-md border p-3"
      aria-label="Shortlist values comparison"
    >
      <h2 className="text-sm font-semibold">Your shortlist, side by side</h2>
      <p className="text-xs text-muted-foreground">
        Actual values from Groundtruth's verified data. District-level context, not address-level
        measurements. Unavailable values are not zero. Scroll sideways for more districts.
      </p>
      <Dialog onOpenChange={(open) => setOpeningWeights(open ? { ...weights } : null)}>
        <DialogTrigger asChild>
          <Button variant="outline" size="sm">
            Expand comparison
          </Button>
        </DialogTrigger>
        <DialogContent className="flex h-[90vh] w-[calc(100vw-2rem)] max-w-6xl flex-col gap-3">
          <DialogHeader>
            <DialogTitle>Your shortlist, side by side</DialogTitle>
            <DialogDescription>
              Compare the {districts.length} selected districts using verified district-level
              values. Unavailable means missing data. Scroll across for more districts.
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[30vh] shrink-0 overflow-y-auto">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!changed}
                aria-describedby="comparison-reset-help"
                onClick={() => {
                  if (openingWeights) onResetWeights({ ...openingWeights });
                }}
              >
                Reset preferences
              </Button>
              <p id="comparison-reset-help" className="text-xs text-muted-foreground">
                Restores weights from when you opened this comparison.
              </p>
            </div>
            <PreferenceWeights weights={weights} onWeightChange={onWeightChange} expanded />
          </div>
          <div className="shrink-0">
            <HighlightLegend />
          </div>
          <ComparisonTable districts={districts} weights={weights} expanded />
          <Sources districts={districts} />
        </DialogContent>
      </Dialog>
      <HighlightLegend />
      <ComparisonTable districts={districts} weights={weights} />
      <Sources districts={districts} />
    </section>
  );
}
