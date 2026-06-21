import { lazy, Suspense, useEffect, useMemo, useState } from "react";
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
import { getMapboxToken } from "@/lib/housing/mapbox-token.functions";
import { getDistricts } from "@/lib/housing/listings.functions";
import { getDistrictPurchasingPower } from "@/lib/finance/purchasing-power.functions";
import type { DistrictFC } from "@/lib/housing/types";
import type { CreditBand } from "@/lib/finance/purchasing-power";
import type { DistrictPurchasingPower } from "@/lib/finance/server-data";

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

type RegionFilter = "all" | "pa-mainline" | "hudson-valley";

function formatCurrency(value: number) {
  return currency.format(Math.round(value));
}

function regionLabel(regionGroup: string) {
  if (regionGroup === "pa-mainline") return "PA Main Line";
  if (regionGroup === "hudson-valley") return "Hudson Valley";
  return regionGroup;
}

function parsePositiveNumber(value: string, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function DiscoveryEngine() {
  const getToken = useServerFn(getMapboxToken);
  const getDistrictsFn = useServerFn(getDistricts);
  const getPurchasingPower = useServerFn(getDistrictPurchasingPower);

  const [monthlyBudget, setMonthlyBudget] = useState(5500);
  const [downPaymentFraction, setDownPaymentFraction] = useState(0.2);
  const [creditBand, setCreditBand] = useState<CreditBand>("good");
  const [regionGroup, setRegionGroup] = useState<RegionFilter>("all");
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [urlHydrated, setUrlHydrated] = useState(false);

  const tokenQuery = useQuery({
    queryKey: ["mapbox-token"],
    queryFn: () => getToken(),
    staleTime: Infinity,
  });

  const districtsQuery = useQuery({
    queryKey: ["districts", "discover"],
    queryFn: () => getDistrictsFn({ data: { simplifyTolerance: 0.002 } }),
    staleTime: 60 * 60 * 1000,
  });

  const purchasingPowerQuery = useQuery({
    queryKey: [
      "district-purchasing-power",
      monthlyBudget,
      downPaymentFraction,
      creditBand,
      regionGroup,
    ],
    queryFn: () =>
      getPurchasingPower({
        data: {
          monthlyBudget,
          downPaymentFraction,
          creditBand,
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
  const ranked = useMemo(
    () =>
      [...purchasingPower].sort(
        (a, b) =>
          b.maxPurchasePrice - a.maxPurchasePrice || a.districtName.localeCompare(b.districtName),
      ),
    [purchasingPower],
  );
  const selected =
    ranked.find((district) => district.districtSlug === selectedSlug) ?? ranked[0] ?? null;
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
    params.set("downPayment", String(Math.round(downPaymentFraction * 100)));
    params.set("creditBand", creditBand);
    if (regionGroup !== "all") params.set("regionGroup", regionGroup);
    return params.toString();
  }, [monthlyBudget, downPaymentFraction, creditBand, regionGroup]);
  const explorerHref = useMemo(() => {
    const params = new URLSearchParams(profileSearch);
    if (selected) {
      params.set("district", selected.districtName);
      params.set("maxPrice", String(Math.floor(selected.maxPurchasePrice)));
    }
    const query = params.toString();
    return `/${query ? `?${query}` : ""}`;
  }, [profileSearch, selected]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const nextCredit = params.get("creditBand");
    const nextRegion = params.get("regionGroup");

    setMonthlyBudget(parsePositiveNumber(params.get("monthlyBudget") ?? "", 5500));
    setDownPaymentFraction(parsePositiveNumber(params.get("downPayment") ?? "", 20) / 100);
    setCreditBand(nextCredit === "excellent" || nextCredit === "fair" ? nextCredit : "good");
    setRegionGroup(
      nextRegion === "pa-mainline" || nextRegion === "hudson-valley" ? nextRegion : "all",
    );
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
          <a href={explorerHref}>
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
                  onValueChange={(value) => setMonthlyBudget(value[0])}
                />
                <Input
                  value={monthlyBudget}
                  inputMode="numeric"
                  onChange={(event) =>
                    setMonthlyBudget(parsePositiveNumber(event.currentTarget.value, monthlyBudget))
                  }
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
                    value={Math.round(downPaymentFraction * 100)}
                    inputMode="numeric"
                    onChange={(event) => {
                      const next = parsePositiveNumber(event.currentTarget.value, 20) / 100;
                      setDownPaymentFraction(Math.min(Math.max(next, 0), 0.95));
                    }}
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

            <section className="grid grid-cols-2 gap-3">
              <MetricBox label="Districts" value={String(ranked.length)} />
              <MetricBox
                label="Average ceiling"
                value={averagePower ? formatCurrency(averagePower) : "-"}
              />
            </section>

            {selected ? (
              <section className="rounded-md border border-border p-4">
                <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">
                  Selected District
                </p>
                <h2 className="mt-1 text-lg font-semibold text-foreground">
                  {selected.districtName}
                </h2>
                <p className="text-sm text-muted-foreground">{regionLabel(selected.regionGroup)}</p>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <MetricBox
                    label="Price ceiling"
                    value={formatCurrency(selected.maxPurchasePrice)}
                  />
                  <MetricBox label="Tax rate" value={percent.format(selected.effectiveTaxRate)} />
                </div>
                <Button asChild className="mt-4 w-full" size="sm">
                  <a href={explorerHref}>
                    <Home className="mr-2 h-4 w-4" />
                    Search listings
                  </a>
                </Button>
              </section>
            ) : null}

            <section className="space-y-2">
              <h2 className="text-sm font-semibold text-foreground">Ranked Districts</h2>
              <div className="space-y-2">
                {ranked.slice(0, 18).map((district) => (
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
                      <p className="shrink-0 text-sm font-semibold text-foreground">
                        {formatCurrency(district.maxPurchasePrice)}
                      </p>
                    </div>
                  </button>
                ))}
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

function MetricBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-semibold text-foreground">{value}</p>
    </div>
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
