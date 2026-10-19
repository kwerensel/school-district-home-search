import { CommuteControls } from "./CommuteControls";
import { getCommuteEstimates } from "@/lib/discovery/commute.functions";
import { withinCommuteCaps } from "@/lib/discovery/commute";
import { shortlistExplorerHref } from "@/lib/discovery/shortlist";
import type { DiscoveryProfile, WizardStep } from "@/lib/discovery/profile";
import { DistrictComparisonDrawer } from "./DistrictComparisonDrawer";
import { GreennessExplainer } from "@/components/metrics/GreennessExplainer";
import { lazy, Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import { ClientOnly } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { Calculator, Home, MapPinned, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AccountButton } from "@/components/auth/AccountButton";
import { SaveProfileButton } from "@/components/auth/SaveProfileButton";
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
  DEFAULT_WEIGHTS,
  parseDiscoveryProfile,
  parseDollarAmount,
  serializeDiscoveryProfile,
  type RegionFilter,
  type WeightKey,
} from "@/lib/discovery/profile";
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

function commuteAnchorLabel(regionGroup: string) {
  return regionGroup === "pa-mainline" ? "Center City Philadelphia" : "Grand Central Terminal";
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
  const getCommutes = useServerFn(getCommuteEstimates);

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
  const [comparisonIds, setComparisonIds] = useState<number[]>([]);
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [details, setDetails] = useState<
    Pick<
      DiscoveryProfile,
      "grossMonthlyIncome" | "monthlyDebt" | "wizardStep" | "shortlist" | "commuteAnchors"
    >
  >({});
  const [incomeText, setIncomeText] = useState("");
  const [debtText, setDebtText] = useState("");
  const wizardStep = details.wizardStep ?? "results";
  const anchors = useMemo(() => details.commuteAnchors ?? [], [details.commuteAnchors]);
  const shortlist = details.shortlist ?? [];
  const setWizardStep = (step: WizardStep) => {
    if (step === "results" && window.location.pathname !== "/discover/results") {
      const params = serializeDiscoveryProfile({ ...currentProfile, wizardStep: "results" });
      if (new URLSearchParams(window.location.search).get("save") === "1") params.set("save", "1");
      window.location.assign(`/discover/results?${params}`);
      return;
    }
    setDetails((current) => ({ ...current, wizardStep: step }));
  };
  const toggleShortlist = (slug: string) =>
    setDetails((current) => {
      const slugs = current.shortlist ?? [];
      return {
        ...current,
        shortlist: slugs.includes(slug)
          ? slugs.filter((value) => value !== slug)
          : slugs.length < 10
            ? [...slugs, slug]
            : slugs,
      };
    });

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
      details.grossMonthlyIncome,
      details.monthlyDebt,
    ],
    queryFn: () =>
      getPurchasingPower({
        data: {
          monthlyBudget,
          downPaymentAmount,
          creditBand,
          environmentWeights: weights,
          grossMonthlyIncome: details.grossMonthlyIncome,
          monthlyDebt: details.monthlyDebt,
          ...(regionGroup === "all" ? {} : { regionGroup }),
        },
      }),
    staleTime: 60 * 1000,
  });

  const commutesQuery = useQuery({
    queryKey: ["request-commutes", anchors, regionGroup],
    queryFn: () =>
      getCommutes({ data: { anchors, ...(regionGroup === "all" ? {} : { regionGroup }) } }),
    enabled: urlHydrated && anchors.length > 0,
    retry: false,
    staleTime: 24 * 60 * 60 * 1000,
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
      [...purchasingPower]
        .filter((district) => {
          if (!anchors.length) return true;
          const estimate = commutesQuery.data?.districts.find(
            (row) => row.districtRegionId === district.districtRegionId,
          );
          return Boolean(estimate && withinCommuteCaps(estimate, anchors));
        })
        .sort(
          (a, b) =>
            b.matchScore - a.matchScore ||
            b.maxPurchasePrice - a.maxPurchasePrice ||
            a.districtName.localeCompare(b.districtName),
        ),
    [purchasingPower, anchors, commutesQuery.data],
  );
  const selected =
    ranked.find((district) => district.districtSlug === selectedSlug) ?? ranked[0] ?? null;
  const rankBySlug = useMemo(
    () => new Map(ranked.map((district, index) => [district.districtSlug, index + 1])),
    [ranked],
  );
  const comparisonDistricts = comparisonIds.flatMap((id) => {
    const district = ranked.find((item) => item.districtRegionId === id);
    return district ? [district] : [];
  });
  const toggleComparison = (id: number) => {
    setComparisonIds((current) => {
      const available = current.filter((value) =>
        ranked.some((district) => district.districtRegionId === value),
      );
      return available.includes(id)
        ? available.filter((value) => value !== id)
        : available.length < 2
          ? [...available, id]
          : available;
    });
  };
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
    return serializeDiscoveryProfile({
      monthlyBudget,
      downPayment: downPaymentAmount,
      creditBand,
      regionGroup,
      weights,
      ...details,
    }).toString();
  }, [monthlyBudget, downPaymentAmount, creditBand, regionGroup, weights, details]);
  const currentProfile = useMemo(
    () => ({
      monthlyBudget,
      downPayment: downPaymentAmount,
      creditBand,
      regionGroup,
      weights,
      ...details,
    }),
    [monthlyBudget, downPaymentAmount, creditBand, regionGroup, weights, details],
  );
  const shortlistDistricts = shortlist.flatMap((slug) => {
    const district = purchasingPower.find((item) => item.districtSlug === slug);
    return district ? [district] : [];
  });
  const shortlistHref = shortlistExplorerHref(currentProfile, purchasingPower);
  const shortlistEligible = shortlist.every((slug) =>
    ranked.some((district) => district.districtSlug === slug),
  );
  const selectedExplorerHref = useMemo(() => {
    const params = new URLSearchParams(profileSearch);
    if (selected) {
      params.set("district", selected.districtName);
      params.set("districtSlug", selected.districtSlug);
      params.set("maxPrice", String(Math.floor(selected.maxPurchasePrice)));
    }
    const query = params.toString();
    return `/explore${query ? `?${query}` : ""}`;
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
    const profile = parseDiscoveryProfile(new URLSearchParams(window.location.search));
    setMonthlyBudget(profile.monthlyBudget);
    setMonthlyBudgetText(currencyInputValue(profile.monthlyBudget));
    setDownPaymentAmount(profile.downPayment);
    setDownPaymentText(currencyInputValue(profile.downPayment));
    setCreditBand(profile.creditBand);
    setRegionGroup(profile.regionGroup);
    setWeights(profile.weights);
    setDetails({
      grossMonthlyIncome: profile.grossMonthlyIncome,
      monthlyDebt: profile.monthlyDebt,
      wizardStep:
        profile.wizardStep ?? (window.location.pathname === "/discover" ? "region" : "results"),
      shortlist: profile.shortlist,
      commuteAnchors: profile.commuteAnchors,
    });
    setIncomeText(
      profile.grossMonthlyIncome === undefined ? "" : String(profile.grossMonthlyIncome),
    );
    setDebtText(profile.monthlyDebt === undefined ? "" : String(profile.monthlyDebt));
    setUrlHydrated(true);
  }, []);

  useEffect(() => {
    if (!urlHydrated) return;
    const params = new URLSearchParams(profileSearch);
    if (new URLSearchParams(window.location.search).get("save") === "1") params.set("save", "1");
    window.history.replaceState(null, "", `${window.location.pathname}?${params}`);
  }, [profileSearch, urlHydrated]);

  return (
    <div className="flex h-screen w-full flex-col bg-background">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-2">
          <MapPinned className="h-5 w-5 text-primary" />
          <h1 className="text-base font-semibold text-foreground">Groundtruth Discovery</h1>
        </div>
        <div className="flex items-center gap-2">
          <SaveProfileButton profile={currentProfile} ready={urlHydrated} />
          <Button asChild variant="outline" size="sm">
            <a href="/explore">
              <Search className="mr-2 h-4 w-4" />
              Explorer
            </a>
          </Button>
          <AccountButton
            returnTo={`${wizardStep === "results" ? "/discover/results" : "/discover"}?${profileSearch}`}
          />
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="min-h-0 overflow-y-auto border-b border-border md:border-r md:border-b-0">
          <div className="space-y-6 p-5">
            <section className="space-y-3" aria-label="Guided Discovery">
              <h2 className="text-sm font-semibold">Build your search</h2>
              <nav className="grid grid-cols-2 gap-2" aria-label="Discovery steps">
                {(["region", "budget", "priorities", "results"] as WizardStep[]).map(
                  (step, index) => (
                    <Button
                      key={step}
                      size="sm"
                      variant={wizardStep === step ? "default" : "outline"}
                      aria-current={wizardStep === step ? "step" : undefined}
                      onClick={() => setWizardStep(step)}
                    >
                      {index + 1}. {step.charAt(0).toUpperCase() + step.slice(1)}
                    </Button>
                  ),
                )}
              </nav>
              {wizardStep === "region" ? (
                <p className="text-sm text-muted-foreground">
                  Choose where to compare districts, then set a housing budget and the priorities
                  that matter to you.
                </p>
              ) : null}
              <Label>Comparison area</Label>
              <Select
                value={regionGroup}
                onValueChange={(value) => {
                  setRegionGroup(value as RegionFilter);
                  setComparisonIds([]);
                  setComparisonOpen(false);
                }}
              >
                <SelectTrigger aria-label="Comparison area">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Both supported regions</SelectItem>
                  <SelectItem value="pa-mainline">PA Main Line</SelectItem>
                  <SelectItem value="hudson-valley">Hudson Valley</SelectItem>
                </SelectContent>
              </Select>
              {wizardStep !== "results" ? (
                <Button
                  className="w-full"
                  onClick={() =>
                    setWizardStep(
                      wizardStep === "region"
                        ? "budget"
                        : wizardStep === "budget"
                          ? "priorities"
                          : "results",
                    )
                  }
                >
                  {wizardStep === "priorities" ? "See matching districts" : "Continue"}
                </Button>
              ) : null}
            </section>
            <section
              className="space-y-4"
              hidden={wizardStep !== "budget" && wizardStep !== "results"}
            >
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

              <div className="space-y-3 rounded-md border border-border p-3">
                <h3 className="text-sm font-medium">Income and debt (optional)</h3>
                <p className="text-xs text-muted-foreground">
                  Add gross monthly income to also apply a 36% debt-to-income ceiling after monthly
                  debts. Leave blank to use only your housing budget.
                </p>
                <Label htmlFor="gross-income">Gross monthly income</Label>
                <Input
                  id="gross-income"
                  inputMode="decimal"
                  value={incomeText}
                  onChange={(event) => setIncomeText(event.target.value)}
                  onBlur={() => {
                    const value = incomeText.trim()
                      ? parseDollarAmount(incomeText, details.grossMonthlyIncome ?? 0)
                      : undefined;
                    setDetails((current) => ({
                      ...current,
                      grossMonthlyIncome: value && value <= 1_000_000 ? value : undefined,
                    }));
                  }}
                  placeholder="Optional"
                />
                <Label htmlFor="monthly-debt">Other monthly debt payments</Label>
                <Input
                  id="monthly-debt"
                  inputMode="decimal"
                  value={debtText}
                  onChange={(event) => setDebtText(event.target.value)}
                  onBlur={() => {
                    const value = debtText.trim()
                      ? parseDollarAmount(debtText, details.monthlyDebt ?? 0, true)
                      : undefined;
                    setDetails((current) => ({
                      ...current,
                      monthlyDebt: value !== undefined && value <= 1_000_000 ? value : undefined,
                    }));
                  }}
                  placeholder="Optional"
                />
              </div>
            </section>

            {selected && wizardStep === "results" ? (
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

            <section
              className="space-y-4"
              hidden={wizardStep !== "priorities" && wizardStep !== "results"}
            >
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

            <div hidden={wizardStep !== "priorities" && wizardStep !== "results"}>
              <CommuteControls
                anchors={anchors}
                onChange={(commuteAnchors) =>
                  setDetails((current) => ({ ...current, commuteAnchors }))
                }
              />
            </div>
            {anchors.length ? (
              <section className="space-y-2 rounded-md border border-border p-3" aria-live="polite">
                {commutesQuery.isPending ? (
                  <p className="text-sm">Checking district drive-time caps…</p>
                ) : commutesQuery.isError ? (
                  <>
                    <p className="text-sm">
                      Commute estimates could not load. Results are withheld while these caps cannot
                      be verified.
                    </p>
                    <Button size="sm" onClick={() => void commutesQuery.refetch()}>
                      Retry commute check
                    </Button>
                  </>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    {ranked.length} districts meet every drive-time cap from a representative
                    district point. Unroutable districts are excluded. No live traffic.
                  </p>
                )}
              </section>
            ) : null}
            <section
              className="space-y-3 rounded-md border border-border p-4"
              hidden={wizardStep !== "results"}
            >
              <h2 className="text-sm font-semibold">Shortlist ({shortlist.length} / 10)</h2>
              <p className="text-xs text-muted-foreground">
                The URL shares your shortlist, budget, and priorities. Each district keeps its own
                estimated max home price in Explorer.
              </p>
              {shortlist.map((slug) => (
                <div className="flex items-center justify-between gap-2 text-sm" key={slug}>
                  <span>
                    {shortlistDistricts.find((district) => district.districtSlug === slug)
                      ?.districtName ?? "District outside this comparison area"}
                  </span>
                  <Button size="sm" variant="ghost" onClick={() => toggleShortlist(slug)}>
                    Remove
                  </Button>
                </div>
              ))}
              {shortlist.length &&
              shortlistDistricts.length === shortlist.length &&
              shortlistEligible ? (
                <Button asChild className="w-full">
                  <a href={shortlistHref}>Search shortlisted districts</a>
                </Button>
              ) : (
                <p className="text-xs text-muted-foreground">
                  {shortlist.length
                    ? "Some shortlisted districts are outside this area or current commute caps. Adjust the area or caps, or remove them."
                    : "Add districts from the ranked results below."}
                </p>
              )}
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

            <section
              className="space-y-3 rounded-md border border-border p-4"
              aria-label="District comparison selection"
            >
              <h2 className="text-sm font-semibold">Compare two districts</h2>
              <p className="text-xs text-muted-foreground">
                Choose up to two districts below. Selection order sets the first and second
                district.
              </p>
              <ol className="space-y-2 text-sm">
                {comparisonDistricts.map((district, index) => (
                  <li
                    key={district.districtRegionId}
                    className="flex items-center justify-between gap-2"
                  >
                    <span>
                      {index + 1}. {district.districtName}
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => toggleComparison(district.districtRegionId)}
                      aria-label={`Remove ${district.districtName} from comparison`}
                    >
                      Remove
                    </Button>
                  </li>
                ))}
              </ol>
              <Button
                className="w-full"
                disabled={comparisonDistricts.length !== 2}
                onClick={() => setComparisonOpen(true)}
              >
                Compare selected districts
              </Button>
            </section>
            <section className="space-y-2" hidden={wizardStep !== "results"}>
              <h2 className="text-sm font-semibold text-foreground">Ranked Districts</h2>
              <div className="space-y-2">
                {ranked.map((district, index) => {
                  const reasons = districtReasons(district, weights);
                  return (
                    <div key={district.districtSlug} className="space-y-1">
                      <button
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
                            {district.archetype ? (
                              <p className="mt-1 text-xs font-medium text-primary">
                                {district.archetype.label}
                              </p>
                            ) : null}
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
                      <Button
                        size="sm"
                        variant="outline"
                        className="w-full"
                        aria-pressed={shortlist.includes(district.districtSlug)}
                        disabled={
                          shortlist.length >= 10 && !shortlist.includes(district.districtSlug)
                        }
                        onClick={() => toggleShortlist(district.districtSlug)}
                      >
                        {shortlist.includes(district.districtSlug)
                          ? "Remove from shortlist"
                          : "Add to shortlist"}
                        <span className="sr-only"> {district.districtName}</span>
                      </Button>
                      {anchors.length ? (
                        <p className="text-xs text-muted-foreground">
                          {commutesQuery.data?.districts
                            .find((row) => row.districtRegionId === district.districtRegionId)
                            ?.anchors.map(
                              (estimate, i) =>
                                `${anchors[i].label}: ${estimate.minutes?.toFixed(0) ?? "unroutable"} min`,
                            )
                            .join(" · ")}
                        </p>
                      ) : null}
                      <Button
                        size="sm"
                        variant="outline"
                        className="w-full"
                        aria-pressed={comparisonIds.includes(district.districtRegionId)}
                        disabled={
                          comparisonDistricts.length === 2 &&
                          !comparisonIds.includes(district.districtRegionId)
                        }
                        onClick={() => toggleComparison(district.districtRegionId)}
                      >
                        {comparisonIds.includes(district.districtRegionId)
                          ? "Remove from comparison"
                          : "Add to comparison"}
                        <span className="sr-only"> {district.districtName}</span>
                      </Button>
                    </div>
                  );
                })}
              </div>
            </section>
          </div>
        </aside>

        <main className="relative isolate min-h-[420px] md:min-h-0">
          {isBooting ? (
            <div className="h-full w-full bg-muted" />
          ) : tokenQuery.isError || districtsQuery.isError || purchasingPowerQuery.isError ? (
            <EmptyMapState
              title="Discovery data didn't load"
              body="The district comparison request failed. Check your connection and try again."
              actionLabel="Try again"
              onAction={() => {
                void Promise.all([
                  tokenQuery.refetch(),
                  districtsQuery.refetch(),
                  purchasingPowerQuery.refetch(),
                ]);
              }}
            />
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
      <DistrictComparisonDrawer
        open={comparisonOpen}
        onOpenChange={setComparisonOpen}
        districtIds={comparisonDistricts.map((district) => district.districtRegionId)}
        profile={{
          monthlyBudget,
          downPaymentAmount,
          creditBand,
          environmentWeights: weights,
          grossMonthlyIncome: details.grossMonthlyIncome,
          monthlyDebt: details.monthlyDebt,
          ...(regionGroup === "all" ? {} : { regionGroup }),
        }}
      />
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
      {selected.archetype ? (
        <div className="mt-2 rounded-md bg-muted px-3 py-2">
          <p className="text-xs font-semibold text-foreground">{selected.archetype.label}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{selected.archetype.description}</p>
        </div>
      ) : null}
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
            label="Street-adjacent greenness (satellite)"
            value={
              selected.environmentMetrics.gviNdviStreet === null
                ? "No data"
                : `${selected.environmentMetrics.gviNdviStreet.toFixed(2)} NDVI`
            }
            help={<GreennessExplainer />}
            active={mapMetric === "satelliteGreenness"}
            onActivate={() => onMapMetricChange("satelliteGreenness")}
          />
          <MetricBox
            label="Canopy / street-greenness gap"
            value={
              selected.environmentMetrics.greenDivergence === null
                ? "No data"
                : `${selected.environmentMetrics.greenDivergence > 0 ? "+" : ""}${selected.environmentMetrics.greenDivergence.toFixed(1)} percentile points`
            }
            help={<GreennessExplainer divergence />}
            active={mapMetric === "greenDivergence"}
            onActivate={() => onMapMetricChange("greenDivergence")}
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
          <MetricBox
            label="Transit-stop density"
            value={
              selected.environmentMetrics.transitAccess === null
                ? "-"
                : `${oneDecimal.format(selected.environmentMetrics.transitAccess)} mapped stops / km²`
            }
            help={
              <MetricExplainer
                compact
                label="How transit access works"
                title="Mapped transit-stop density"
              >
                <p>
                  Active GTFS stops mapped by Transitland per square kilometer, averaged across the
                  district from census-tract data.
                </p>
                <p>It does not measure service frequency, reliability, or walking access.</p>
              </MetricExplainer>
            }
            active={mapMetric === "transitAccess"}
            onActivate={() => onMapMetricChange("transitAccess")}
          />
          <MetricBox
            label={`Drive time to ${commuteAnchorLabel(selected.regionGroup)}`}
            value={formatOptionalNumber(selected.environmentMetrics.commuteMinutes, " min")}
            help={
              <MetricExplainer compact label="How drive time works" title="Regional drive time">
                <p>
                  Population-weighted district context derived from routed census-tract origins to
                  the named city anchor under the routing engine's standard driving assumptions.
                </p>
                <p>It is not live traffic and is not a promise for a specific address or hour.</p>
              </MetricExplainer>
            }
            active={mapMetric === "commuteMinutes"}
            onActivate={() => onMapMetricChange("commuteMinutes")}
          />
          <MetricBox
            label="Annual mean daily AQI"
            value={formatOptionalNumber(selected.environmentMetrics.aqiAnnualMean, " AQI")}
            help={
              <MetricExplainer compact label="How air quality works" title="Annual air quality">
                <p>
                  EPA daily Air Quality Index values are averaged at regulatory monitor sites, then
                  interpolated to census tracts from monitors within 30 km. Lower is cleaner.
                </p>
                <p>
                  County monitor means fill gaps. This is coarse neighborhood context, not a live
                  reading or an address-level measurement.
                </p>
              </MetricExplainer>
            }
            active={mapMetric === "airQuality"}
            onActivate={() => onMapMetricChange("airQuality")}
          />
          <MetricBox
            label="Modeled transportation noise"
            value={
              selected.environmentMetrics.noisePctOver55 === null
                ? "-"
                : `${oneDecimal.format(selected.environmentMetrics.noisePctOver55)}% of district area at or above 55 dBA${
                    selected.environmentMetrics.noiseMeanDba === null
                      ? ""
                      : ` · ${oneDecimal.format(selected.environmentMetrics.noiseMeanDba)} dBA modeled mean`
                  }`
            }
            help={
              <MetricExplainer
                compact
                label="How transportation noise works"
                title="Modeled transportation noise"
                sourceHref="https://www.bts.gov/geospatial/national-transportation-noise-map"
                sourceLabel="View the BTS National Transportation Noise Map"
              >
                <p>
                  The Bureau of Transportation Statistics models 24-hour average aviation, road, and
                  rail noise. This value is the share of district land in modeled classes at or
                  above 55 dBA.
                </p>
                <p>
                  It is national screening context, not a live or address-specific measurement. The
                  simplified model omits shielding and can overestimate some locations.
                </p>
              </MetricExplainer>
            }
            active={mapMetric === "transportationNoise"}
            onActivate={() => onMapMetricChange("transportationNoise")}
          />
          <MetricBox
            label="Emergency-response facility density"
            value={
              selected.environmentMetrics.noiseSirenDensity === null
                ? "-"
                : `${selected.environmentMetrics.noiseSirenDensity.toFixed(2)} mapped facilities / km²`
            }
            help={
              <MetricExplainer
                compact
                label="How this source proxy works"
                title="Mapped emergency-response facilities"
                sourceHref="https://www.openstreetmap.org/copyright"
                sourceLabel="OpenStreetMap data and attribution"
              >
                <p>
                  OpenStreetMap fire stations, police stations, and hospitals are counted per square
                  kilometer and averaged across the district. This is a possible siren-source proxy,
                  not a measurement of siren events or sound.
                </p>
                <p>Community mapping completeness varies by place and over time.</p>
              </MetricExplainer>
            }
            active={mapMetric === "sirenSources"}
            onActivate={() => onMapMetricChange("sirenSources")}
          />
          <MetricBox
            label="Nightlife venue density"
            value={
              selected.environmentMetrics.noiseNightlifeDensity === null
                ? "-"
                : `${selected.environmentMetrics.noiseNightlifeDensity.toFixed(2)} mapped venues / km²`
            }
            help={
              <MetricExplainer
                compact
                label="How this source proxy works"
                title="Mapped nightlife venues"
                sourceHref="https://www.openstreetmap.org/copyright"
                sourceLabel="OpenStreetMap data and attribution"
              >
                <p>
                  OpenStreetMap bars, pubs, and nightclubs are counted per square kilometer and
                  averaged across the district. This is venue context, not a measurement of noise,
                  opening hours, or activity.
                </p>
                <p>Community mapping completeness varies by place and over time.</p>
              </MetricExplainer>
            }
            active={mapMetric === "nightlifeSources"}
            onActivate={() => onMapMetricChange("nightlifeSources")}
          />
          <MetricBox
            label="Mapped industrial land"
            value={
              selected.environmentMetrics.noiseIndustrialLandPct === null
                ? "-"
                : `${oneDecimal.format(selected.environmentMetrics.noiseIndustrialLandPct)}% of district land`
            }
            help={
              <MetricExplainer
                compact
                label="How this source proxy works"
                title="Mapped industrial land"
                sourceHref="https://www.openstreetmap.org/copyright"
                sourceLabel="OpenStreetMap data and attribution"
              >
                <p>
                  The mapped share of land tagged industrial in OpenStreetMap, averaged from
                  census-tract coverage. It is context for possible activity sources, not an
                  emissions, operating-hours, or sound measurement.
                </p>
                <p>Community mapping completeness and land-use tagging vary by place.</p>
              </MetricExplainer>
            }
            active={mapMetric === "industrialLand"}
            onActivate={() => onMapMetricChange("industrialLand")}
          />
          <MetricBox
            label="Active freight-capable rail density"
            value={
              selected.environmentMetrics.noiseFreightRailDensity === null
                ? "-"
                : `${selected.environmentMetrics.noiseFreightRailDensity.toFixed(2)} rail km / km²`
            }
            help={
              <MetricExplainer
                compact
                label="How this rail proxy works"
                title="Active freight-capable rail"
                sourceHref="https://railroads.dot.gov/rail-network-development/maps-and-data/maps-geographic"
                sourceLabel="View FRA rail network sources"
              >
                <p>
                  Federal Railroad Administration lines classified as active main, industrial,
                  siding, or yard track are measured per square kilometer. Classification indicates
                  freight capability, not actual train frequency, schedules, horns, or sound.
                </p>
              </MetricExplainer>
            }
            active={mapMetric === "freightRail"}
            onActivate={() => onMapMetricChange("freightRail")}
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

function EmptyMapState({
  title,
  body,
  actionLabel,
  onAction,
}: {
  title: string;
  body?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="rounded-md border border-dashed border-border p-6 text-center">
        <Home className="mx-auto h-5 w-5 text-muted-foreground" />
        <p className="mt-2 text-sm font-medium text-foreground">{title}</p>
        {body ? <p className="mt-2 text-sm text-muted-foreground">{body}</p> : null}
        {actionLabel && onAction ? (
          <Button type="button" className="mt-4" size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
