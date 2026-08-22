import { lazy, Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import { ClientOnly } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { Calculator, Home, MapPinned, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { WalkabilityExplainer } from "@/components/metrics/WalkabilityExplainer";
import { MetricExplainer } from "@/components/metrics/MetricExplainer";
import { PurchasingPowerExplainer } from "@/components/metrics/PurchasingPowerExplainer";
import { getMapboxToken } from "@/lib/housing/mapbox-token.functions";
import { getDistricts } from "@/lib/housing/listings.functions";
import { getDistrictPurchasingPower } from "@/lib/finance/purchasing-power.functions";
import type { DistrictFC } from "@/lib/housing/types";
import type { CreditBand } from "@/lib/finance/purchasing-power";
import type { DistrictPurchasingPower } from "@/lib/finance/server-data";
import {
  lightPollutionCategory,
  riskCategory,
  treeCoverCategory,
  type MapMetricKey,
} from "@/lib/metrics/presentation";

const RegionChoroplethMap = lazy(() =>
  import("./RegionChoroplethMap").then((m) => ({ default: m.RegionChoroplethMap })),
);

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const percent = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 2,
});

const oneDecimal = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
});

type RegionFilter = "all" | "pa-mainline" | "hudson-valley";
type WeightKey =
  | "affordability"
  | "green"
  | "walkability"
  | "lowerRisk"
  | "lowerFlood"
  | "darkSkies"
  | "parkAccess";

const DEFAULT_WEIGHTS: Record<WeightKey, number> = {
  affordability: 5,
  green: 2,
  walkability: 2,
  lowerRisk: 1,
  lowerFlood: 1,
  darkSkies: 1,
  parkAccess: 1,
};

const weightControls: Array<{ key: WeightKey; label: string }> = [
  { key: "affordability", label: "Local price reach" },
  { key: "green", label: "Tree cover" },
  { key: "walkability", label: "EPA walkability" },
  { key: "lowerRisk", label: "Lower risk" },
  { key: "lowerFlood", label: "Lower flood" },
  { key: "darkSkies", label: "Darker skies" },
  { key: "parkAccess", label: "Park access" },
];

function formatCurrency(value: number) {
  return currency.format(Math.round(value));
}

function regionLabel(regionGroup: string) {
  if (regionGroup === "pa-mainline") return "PA Main Line";
  if (regionGroup === "hudson-valley") return "Hudson Valley";
  return regionGroup;
}

function parseDollarAmount(value: string, fallback: number, allowZero = false) {
  const parsed = Number(value.replace(/[$,\s]/g, ""));
  const isValid = Number.isFinite(parsed) && (allowZero ? parsed >= 0 : parsed > 0);
  return isValid ? parsed : fallback;
}

function currencyInputValue(value: number) {
  return String(Math.round(value));
}

function formatOptionalNumber(value: number | null, suffix = "") {
  return value === null ? "-" : `${oneDecimal.format(value)}${suffix}`;
}

function formatOptionalCurrency(value: number | null) {
  return value === null ? "-" : formatCurrency(value);
}

function formatOptionalPercent(value: number | null) {
  return value === null ? "-" : percent.format(value);
}

function comparisonScopeLabel(regionGroup: RegionFilter) {
  if (regionGroup === "all") return "both supported regions";
  return regionLabel(regionGroup);
}

const factorLabels: Record<WeightKey, string> = {
  affordability: "local price reach",
  green: "tree cover",
  walkability: "EPA walkability",
  lowerRisk: "lower hazard risk",
  lowerFlood: "lower flood exposure",
  darkSkies: "darker skies",
  parkAccess: "park access",
};

function districtReasons(district: DistrictPurchasingPower, weights: Record<WeightKey, number>) {
  const entries = (Object.keys(factorLabels) as WeightKey[])
    .map((key) => ({ key, score: district.matchComponents[key] }))
    .filter(
      (entry): entry is { key: WeightKey; score: number } =>
        entry.score !== null && weights[entry.key] > 0,
    );
  const strongest = [...entries].sort((a, b) => b.score - a.score);
  const weakest = [...entries].sort((a, b) => a.score - b.score);
  const strengths = strongest.filter((entry) => entry.score >= 60).slice(0, 2);
  const tradeoffs = weakest.filter((entry) => entry.score <= 40).slice(0, 1);

  return {
    strengths: (strengths.length ? strengths : strongest.slice(0, 1)).map(
      (entry) => factorLabels[entry.key],
    ),
    tradeoffs: tradeoffs.map((entry) => factorLabels[entry.key]),
  };
}

export function DiscoveryEngine() {
  const getToken = useServerFn(getMapboxToken);
  const getDistrictsFn = useServerFn(getDistricts);
  const getPurchasingPower = useServerFn(getDistrictPurchasingPower);

  const [monthlyBudget, setMonthlyBudget] = useState(5500);
  const [monthlyBudgetText, setMonthlyBudgetText] = useState(currencyInputValue(5500));
  const [downPaymentAmount, setDownPaymentAmount] = useState(150000);
  const [downPaymentText, setDownPaymentText] = useState(currencyInputValue(150000));
  const [creditBand, setCreditBand] = useState<CreditBand>("good");
  const [regionGroup, setRegionGroup] = useState<RegionFilter>("all");
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [weights, setWeights] = useState<Record<WeightKey, number>>(DEFAULT_WEIGHTS);
  const [mapMetric, setMapMetric] = useState<MapMetricKey>("purchasingPower");
  const [urlHydrated, setUrlHydrated] = useState(false);

  const tokenQuery = useQuery({
    queryKey: ["mapbox-token"],
    queryFn: () => getToken(),
    staleTime: Infinity,
  });

  const districtsQuery = useQuery({
    queryKey: ["districts", "discover"],
    queryFn: () => getDistrictsFn({ data: { simplifyTolerance: 0.002, representedOnly: false } }),
    staleTime: 60 * 60 * 1000,
  });

  const purchasingPowerQuery = useQuery({
    queryKey: [
      "district-purchasing-power",
      monthlyBudget,
      downPaymentAmount,
      creditBand,
      regionGroup,
      weights,
    ],
    queryFn: () =>
      getPurchasingPower({
        data: {
          monthlyBudget,
          downPaymentAmount,
          creditBand,
          environmentWeights: weights,
          ...(regionGroup === "all" ? {} : { regionGroup }),
        },
      }),
    staleTime: 60 * 1000,
  });

  const token = tokenQuery.data?.token ?? "";
  const districts = (districtsQuery.data ?? null) as DistrictFC | null;
  const purchasingPower = useMemo(
    () => purchasingPowerQuery.data?.districts ?? [],
    [purchasingPowerQuery.data],
  );
  const rateAssumption = purchasingPowerQuery.data?.rateAssumption ?? {
    annualRate: 0.0675,
    source: "fallback" as const,
    observationDate: null,
  };
  const ranked = useMemo(
    () =>
      [...purchasingPower].sort(
        (a, b) =>
          b.matchScore - a.matchScore ||
          b.maxPurchasePrice - a.maxPurchasePrice ||
          a.districtName.localeCompare(b.districtName),
      ),
    [purchasingPower],
  );
  const selected =
    ranked.find((district) => district.districtSlug === selectedSlug) ?? ranked[0] ?? null;
  const rankBySlug = useMemo(
    () => new Map(ranked.map((district, index) => [district.districtSlug, index + 1])),
    [ranked],
  );
  const selectedRank = selected ? (rankBySlug.get(selected.districtSlug) ?? null) : null;
  const averagePower =
    ranked.length > 0
      ? ranked.reduce((sum, district) => sum + district.maxPurchasePrice, 0) / ranked.length
      : 0;
  const isBooting =
    !urlHydrated ||
    tokenQuery.isPending ||
    districtsQuery.isPending ||
    purchasingPowerQuery.isPending;
  const profileSearch = useMemo(() => {
    const params = new URLSearchParams();
    params.set("monthlyBudget", String(monthlyBudget));
    params.set("downPayment", String(Math.round(downPaymentAmount)));
    params.set("creditBand", creditBand);
    if (regionGroup !== "all") params.set("regionGroup", regionGroup);
    for (const control of weightControls) {
      const value = weights[control.key];
      if (value !== DEFAULT_WEIGHTS[control.key]) params.set(control.key, String(value));
    }
    return params.toString();
  }, [monthlyBudget, downPaymentAmount, creditBand, regionGroup, weights]);
  const selectedExplorerHref = useMemo(() => {
    const params = new URLSearchParams(profileSearch);
    if (selected) {
      params.set("district", selected.districtName);
      params.set("districtSlug", selected.districtSlug);
      params.set("maxPrice", String(Math.floor(selected.maxPurchasePrice)));
    }
    const query = params.toString();
    return `/${query ? `?${query}` : ""}`;
  }, [profileSearch, selected]);
  const commitMonthlyBudget = () => {
    const nextMonthlyBudget = parseDollarAmount(monthlyBudgetText, monthlyBudget);
    setMonthlyBudget(nextMonthlyBudget);
    setMonthlyBudgetText(currencyInputValue(nextMonthlyBudget));
  };
  const commitDownPayment = () => {
    const nextDownPayment = parseDollarAmount(downPaymentText, downPaymentAmount, true);
    setDownPaymentAmount(nextDownPayment);
    setDownPaymentText(currencyInputValue(nextDownPayment));
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const nextCredit = params.get("creditBand");
    const nextRegion = params.get("regionGroup");
    const nextWeights = { ...DEFAULT_WEIGHTS };
    for (const control of weightControls) {
      const rawValue = params.get(control.key);
      if (rawValue === null) continue;
      const value = Number(rawValue);
      if (Number.isFinite(value) && value >= 0 && value <= 10) nextWeights[control.key] = value;
    }

    const nextMonthlyBudget = parseDollarAmount(params.get("monthlyBudget") ?? "", 5500);
    const nextDownPayment = parseDollarAmount(params.get("downPayment") ?? "", 150000, true);
    setMonthlyBudget(nextMonthlyBudget);
    setMonthlyBudgetText(currencyInputValue(nextMonthlyBudget));
    setDownPaymentAmount(nextDownPayment);
    setDownPaymentText(currencyInputValue(nextDownPayment));
    setCreditBand(nextCredit === "excellent" || nextCredit === "fair" ? nextCredit : "good");
    setRegionGroup(
      nextRegion === "pa-mainline" || nextRegion === "hudson-valley" ? nextRegion : "all",
    );
    setWeights(nextWeights);
    setUrlHydrated(true);
  }, []);

  useEffect(() => {
    if (!urlHydrated) return;
    window.history.replaceState(null, "", `${window.location.pathname}?${profileSearch}`);
  }, [profileSearch, urlHydrated]);

  return (
    <div className="flex h-screen w-full flex-col bg-background">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-2">
          <MapPinned className="h-5 w-5 text-primary" />
          <h1 className="text-base font-semibold text-foreground">Groundtruth Discovery</h1>
        </div>
        <Button asChild variant="outline" size="sm">
          <a href="/">
            <Search className="mr-2 h-4 w-4" />
            Explorer
          </a>
        </Button>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="min-h-0 overflow-y-auto border-b border-border md:border-r md:border-b-0">
          <div className="space-y-6 p-5">
            <section className="space-y-4">
              <div className="flex items-center gap-2">
                <Calculator className="h-4 w-4 text-primary" />
                <h2 className="text-sm font-semibold text-foreground">Budget</h2>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="monthly-budget">Monthly payment</Label>
                  <span className="text-sm font-medium text-foreground">
                    {formatCurrency(monthlyBudget)}
                  </span>
                </div>
                <Slider
                  id="monthly-budget"
                  min={1500}
                  max={12000}
                  step={250}
                  value={[monthlyBudget]}
                  onValueChange={(value) => {
                    setMonthlyBudget(value[0]);
                    setMonthlyBudgetText(currencyInputValue(value[0]));
                  }}
                />
                <Input
                  id="monthly-budget-input"
                  value={monthlyBudgetText}
                  inputMode="numeric"
                  aria-label="Monthly payment in dollars"
                  onChange={(event) => {
                    setMonthlyBudgetText(event.currentTarget.value);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") event.currentTarget.blur();
                  }}
                  onBlur={commitMonthlyBudget}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label>Credit</Label>
                  <Select
                    value={creditBand}
                    onValueChange={(value) => setCreditBand(value as CreditBand)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="excellent">Excellent</SelectItem>
                      <SelectItem value="good">Good</SelectItem>
                      <SelectItem value="fair">Fair</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="down-payment">Down payment</Label>
                  <Input
                    id="down-payment"
                    value={downPaymentText}
                    inputMode="numeric"
                    aria-label="Down payment in dollars"
                    onChange={(event) => {
                      setDownPaymentText(event.currentTarget.value);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") event.currentTarget.blur();
                    }}
                    onBlur={commitDownPayment}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label>Region</Label>
                <Select
                  value={regionGroup}
                  onValueChange={(value) => setRegionGroup(value as RegionFilter)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All regions</SelectItem>
                    <SelectItem value="pa-mainline">PA Main Line</SelectItem>
                    <SelectItem value="hudson-valley">Hudson Valley</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </section>

            {selected ? (
              <SelectedDistrictPanel
                selected={selected}
                selectedExplorerHref={selectedExplorerHref}
                rank={selectedRank}
                districtCount={ranked.length}
                comparisonScope={comparisonScopeLabel(regionGroup)}
                monthlyBudget={monthlyBudget}
                downPaymentAmount={downPaymentAmount}
                creditBand={creditBand}
                rateSource={rateAssumption.source}
                rateObservationDate={rateAssumption.observationDate}
                mapMetric={mapMetric}
                onMapMetricChange={setMapMetric}
              />
            ) : null}

            <section className="space-y-4">
              <h2 className="text-sm font-semibold text-foreground">Priorities</h2>
              <div className="space-y-4">
                {weightControls.map((control) => (
                  <div key={control.key} className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <Label htmlFor={`weight-${control.key}`}>{control.label}</Label>
                      <span className="w-6 text-right text-sm font-medium text-foreground">
                        {weights[control.key]}
                      </span>
                    </div>
                    <Slider
                      id={`weight-${control.key}`}
                      min={0}
                      max={10}
                      step={1}
                      value={[weights[control.key]]}
                      onValueChange={(value) =>
                        setWeights((current) => ({ ...current, [control.key]: value[0] }))
                      }
                    />
                  </div>
                ))}
              </div>
            </section>

            <section className="grid grid-cols-2 gap-3">
              <MetricBox label="Districts" value={String(ranked.length)} />
              <MetricBox
                label="Average max price"
                value={averagePower ? formatCurrency(averagePower) : "-"}
              />
            </section>

            <section className="rounded-md border border-border p-4">
              <p className="text-sm font-semibold text-foreground">How this ranking works</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Ranked among {ranked.length} districts in {comparisonScopeLabel(regionGroup)} using
                the priorities above. A rank is comparative—it is not a probability or a percentage
                of requirements satisfied.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-sm font-semibold text-foreground">Ranked Districts</h2>
              <div className="space-y-2">
                {ranked.slice(0, 18).map((district, index) => {
                  const reasons = districtReasons(district, weights);
                  return (
                    <button
                      key={district.districtSlug}
                      type="button"
                      onClick={() => setSelectedSlug(district.districtSlug)}
                      className={`w-full rounded-md border p-3 text-left transition-colors ${
                        district.districtSlug === selected?.districtSlug
                          ? "border-primary bg-accent"
                          : "border-border bg-background hover:bg-accent"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-foreground">
                            {district.districtName}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {regionLabel(district.regionGroup)}
                          </p>
                        </div>
                        <p className="shrink-0 text-xs font-semibold text-foreground">
                          #{index + 1} of {ranked.length}
                        </p>
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                        <div>
                          <p className="text-muted-foreground">Estimated max price</p>
                          <p className="mt-0.5 font-semibold text-foreground">
                            {formatCurrency(district.maxPurchasePrice)}
                          </p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">District median value</p>
                          <p className="mt-0.5 font-semibold text-foreground">
                            {formatOptionalCurrency(district.environmentMetrics.medianHomeValue)}
                          </p>
                        </div>
                      </div>
                      <div className="mt-3 space-y-1 text-xs text-muted-foreground">
                        {reasons.strengths.length ? (
                          <p>
                            <span className="font-medium text-foreground">Stronger here:</span>{" "}
                            {reasons.strengths.join(", ")}
                          </p>
                        ) : null}
                        {reasons.tradeoffs.length ? (
                          <p>
                            <span className="font-medium text-foreground">Tradeoff:</span>{" "}
                            {reasons.tradeoffs.join(", ")}
                          </p>
                        ) : null}
                      </div>
                    </button>
                  );
                })}
              </div>
            </section>
          </div>
        </aside>

        <main className="relative min-h-[420px] md:min-h-0">
          {isBooting ? (
            <div className="h-full w-full bg-muted" />
          ) : !token ? (
            <EmptyMapState title="Mapbox token missing" />
          ) : (
            <ClientOnly fallback={<div className="h-full w-full bg-muted" />}>
              <Suspense fallback={<div className="h-full w-full bg-muted" />}>
                <RegionChoroplethMap
                  token={token}
                  districts={districts}
                  purchasingPower={ranked}
                  selectedSlug={selected?.districtSlug ?? null}
                  rankBySlug={rankBySlug}
                  activeMetric={mapMetric}
                  onActiveMetricChange={setMapMetric}
                  onDistrictSelect={setSelectedSlug}
                />
              </Suspense>
            </ClientOnly>
          )}
        </main>
      </div>
    </div>
  );
}

function SelectedDistrictPanel({
  selected,
  selectedExplorerHref,
  rank,
  districtCount,
  comparisonScope,
  monthlyBudget,
  downPaymentAmount,
  creditBand,
  rateSource,
  rateObservationDate,
  mapMetric,
  onMapMetricChange,
}: {
  selected: DistrictPurchasingPower;
  selectedExplorerHref: string;
  rank: number | null;
  districtCount: number;
  comparisonScope: string;
  monthlyBudget: number;
  downPaymentAmount: number;
  creditBand: CreditBand;
  rateSource: "pmms" | "fallback" | "user";
  rateObservationDate: string | null;
  mapMetric: MapMetricKey;
  onMapMetricChange: (metric: MapMetricKey) => void;
}) {
  return (
    <section className="rounded-md border border-border p-4" data-testid="selected-district-panel">
      <div className="flex items-center justify-between gap-3 text-xs font-medium text-muted-foreground">
        <p className="uppercase tracking-normal">Selected District</p>
        <p>{rank ? `#${rank} of ${districtCount} districts` : `${districtCount} districts`}</p>
      </div>
      <h2 className="mt-1 text-lg font-semibold text-foreground">{selected.districtName}</h2>
      <p className="text-sm text-muted-foreground">
        Compared within {comparisonScope}
        {comparisonScope === regionLabel(selected.regionGroup)
          ? ""
          : ` · ${regionLabel(selected.regionGroup)}`}
      </p>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <MetricBox
          label="Estimated max home price"
          value={formatCurrency(selected.maxPurchasePrice)}
          help={
            <PurchasingPowerExplainer
              annualRate={selected.annualRate}
              effectiveTaxRate={selected.effectiveTaxRate}
              monthlyBudget={monthlyBudget}
              downPaymentAmount={downPaymentAmount}
              creditBand={creditBand}
              rateSource={rateSource}
              rateObservationDate={rateObservationDate}
            />
          }
          active={mapMetric === "purchasingPower"}
          onActivate={() => onMapMetricChange("purchasingPower")}
        />
        <MetricBox
          label="District median home value"
          value={formatOptionalCurrency(selected.environmentMetrics.medianHomeValue)}
        />
        <MetricBox
          label="Effective property-tax rate"
          value={percent.format(selected.effectiveTaxRate)}
        />
      </div>
      <div className="mt-4 border-t border-border pt-4">
        <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">
          District-level context
        </p>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <MetricBox
            label="Tree coverage"
            value={
              selected.environmentMetrics.treeCanopyPct === null
                ? "-"
                : `${treeCoverCategory(selected.environmentMetrics.treeCanopyPct)} · ${oneDecimal.format(selected.environmentMetrics.treeCanopyPct)}%`
            }
            help={<TreeCoverageExplainer />}
            active={mapMetric === "treeCanopy"}
            onActivate={() => onMapMetricChange("treeCanopy")}
          />
          <MetricBox
            label="EPA walkability"
            value={formatOptionalNumber(selected.environmentMetrics.walkabilityIndex, " / 20")}
            help={<WalkabilityExplainer />}
            active={mapMetric === "walkability"}
            onActivate={() => onMapMetricChange("walkability")}
          />
          <MetricBox
            label="Natural-hazard risk"
            value={
              selected.environmentMetrics.riskIndex === null
                ? "-"
                : `${riskCategory(selected.environmentMetrics.riskIndex)} · ${oneDecimal.format(selected.environmentMetrics.riskIndex)} / 100`
            }
            active={mapMetric === "risk"}
            onActivate={() => onMapMetricChange("risk")}
          />
          <MetricBox
            label="FEMA flood-zone land"
            value={
              selected.environmentMetrics.floodSfha === null
                ? "-"
                : `${formatOptionalPercent(selected.environmentMetrics.floodSfha)} of district land`
            }
            help={<FloodExplainer />}
            active={mapMetric === "floodExposure"}
            onActivate={() => onMapMetricChange("floodExposure")}
          />
          <MetricBox
            label="Light pollution"
            value={
              selected.environmentMetrics.lightPollutionRadiance === null
                ? "-"
                : `${lightPollutionCategory(selected.environmentMetrics.lightPollutionRadiance)} · ${oneDecimal.format(selected.environmentMetrics.lightPollutionRadiance)} radiance`
            }
            help={<LightPollutionExplainer />}
            active={mapMetric === "lightPollution"}
            onActivate={() => onMapMetricChange("lightPollution")}
          />
          <MetricBox
            label="Average canopy height"
            value={formatOptionalNumber(selected.environmentMetrics.canopyHeightM, " m")}
            help={<CanopyHeightExplainer />}
          />
          <MetricBox
            label="Park access"
            value={
              selected.environmentMetrics.parkAccess === null
                ? "-"
                : `${formatOptionalPercent(selected.environmentMetrics.parkAccess)} of district land within 800 m`
            }
            help={<ParkAccessExplainer />}
            active={mapMetric === "parkAccess"}
            onActivate={() => onMapMetricChange("parkAccess")}
          />
        </div>
      </div>
      <Button asChild className="mt-4 w-full" size="sm">
        <a href={selectedExplorerHref}>
          <Home className="mr-2 h-4 w-4" />
          Search listings
        </a>
      </Button>
    </section>
  );
}

function MetricBox({
  label,
  value,
  help,
  active = false,
  onActivate,
}: {
  label: string;
  value: string;
  help?: ReactNode;
  active?: boolean;
  onActivate?: () => void;
}) {
  return (
    <div
      className={`rounded-md border p-3 ${active ? "border-primary bg-accent" : "border-border"}`}
    >
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-semibold text-foreground">{value}</p>
      {help ? <div className="mt-2">{help}</div> : null}
      {onActivate ? (
        <button
          type="button"
          onClick={onActivate}
          className="mt-2 text-xs font-medium text-primary underline-offset-2 hover:underline"
        >
          {active ? "Shown on map" : "Show on map"}
        </button>
      ) : null}
    </div>
  );
}

function ParkAccessExplainer() {
  return (
    <MetricExplainer label="What this means" title="Park access">
      <p>
        The share of district land within 800 m of mapped public parks and open space from
        OpenStreetMap and USGS PAD-US.
      </p>
      <p>
        This is proximity context, not a promise about entrances, walking routes, hours, permits,
        safety, or amenities.
      </p>
    </MetricExplainer>
  );
}

function TreeCoverageExplainer() {
  return (
    <MetricExplainer label="What this means" title="Tree coverage">
      <p>
        The share of district land covered by tree canopy. Groundtruth translates the raw percentage
        into Sparse, Some trees, Leafy, or Very leafy so it is easier to compare.
      </p>
      <p>It describes coverage, not tree height, age, sidewalk shade, or walking comfort.</p>
    </MetricExplainer>
  );
}

function CanopyHeightExplainer() {
  return (
    <MetricExplainer label="What this means" title="Average canopy height">
      <p>
        Mean mapped vegetation height across the district. It can distinguish taller from lower
        vegetation, but does not measure tree age, old growth, or how shaded a specific sidewalk
        feels.
      </p>
    </MetricExplainer>
  );
}

function FloodExplainer() {
  return (
    <MetricExplainer
      label="What this means"
      title="FEMA flood-zone exposure"
      sourceHref="https://www.fema.gov/flood-maps/national-flood-hazard-layer"
      sourceLabel="View FEMA National Flood Hazard Layer"
    >
      <p>
        This is the percentage of district land inside a mapped Special Flood Hazard Area. It is not
        the percentage of homes affected and not the probability that the district will flood.
      </p>
      <p>Use it as screening context, then check the official parcel map and insurance details.</p>
    </MetricExplainer>
  );
}

function LightPollutionExplainer() {
  return (
    <MetricExplainer label="What this means" title="Light pollution">
      <p>
        VIIRS satellite radiance measures upward nighttime light. Lower is darker. The observed
        district values in this prototype run roughly from 0.26 to 100.7.
      </p>
      <p>
        A value such as 1 is not a 1-to-10 score; it is a radiance measurement. Groundtruth uses it
        to assign a plain-language category from Very dark to Very bright.
      </p>
      <p>This is coarse neighborhood context, not an address-level reading.</p>
    </MetricExplainer>
  );
}

function EmptyMapState({ title }: { title: string }) {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="rounded-md border border-dashed border-border p-6 text-center">
        <Home className="mx-auto h-5 w-5 text-muted-foreground" />
        <p className="mt-2 text-sm font-medium text-foreground">{title}</p>
      </div>
    </div>
  );
}
