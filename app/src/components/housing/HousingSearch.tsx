import { useEffect, useMemo, useState, lazy, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { ClientOnly, Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { Compass, Filter as FilterIcon, Home } from "lucide-react";
import { FiltersSidebar } from "./FiltersSidebar";
import { ListingDetailPanel } from "./ListingDetailPanel";

const MapView = lazy(() => import("./MapView").then((m) => ({ default: m.MapView })));
import { getDistricts, getListings } from "@/lib/housing/listings.functions";
import { getMapboxToken } from "@/lib/housing/mapbox-token.functions";
import { applyFilters, DEFAULT_FILTERS, priceBounds, uniqueDistricts } from "@/lib/housing/filters";
import type { DistrictFC, Filters, ListingFC, ListingFeature } from "@/lib/housing/types";
import type { ExplorerMapMetricKey } from "@/lib/metrics/presentation";

const EMPTY_LISTINGS: ListingFC = { type: "FeatureCollection", features: [] };

export function HousingSearch() {
  const getToken = useServerFn(getMapboxToken);
  const getListingsFn = useServerFn(getListings);
  const getDistrictsFn = useServerFn(getDistricts);

  const tokenQuery = useQuery({
    queryKey: ["mapbox-token"],
    queryFn: () => getToken(),
    staleTime: Infinity,
  });

  const listingsQuery = useQuery({
    queryKey: ["listings"],
    queryFn: () => getListingsFn({ data: {} }),
    staleTime: Infinity,
  });

  const districtsQuery = useQuery({
    queryKey: ["districts"],
    queryFn: () => getDistrictsFn({ data: { simplifyTolerance: 0.001, representedOnly: true } }),
    staleTime: 60 * 60 * 1000,
  });

  const token = tokenQuery.data?.token ?? "";
  const listings = listingsQuery.data ?? EMPTY_LISTINGS;
  const districts = (districtsQuery.data ?? null) as DistrictFC | null;

  const allListings = listings;
  const bounds = useMemo(() => priceBounds(allListings), [allListings]);
  const districtList = useMemo(() => uniqueDistricts(allListings), [allListings]);

  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selectedListing, setSelectedListing] = useState<ListingFeature | null>(null);
  const [filtersInitialized, setFiltersInitialized] = useState(false);
  const [mapMetric, setMapMetric] = useState<ExplorerMapMetricKey>("schoolDistricts");
  const [initialFocus, setInitialFocus] = useState<{
    districtName: string | null;
    districtSlug: string | null;
    regionGroup: string | null;
  }>({ districtName: null, districtSlug: null, regionGroup: null });

  useEffect(() => {
    if (listingsQuery.isPending || filtersInitialized) return;

    const params =
      typeof window === "undefined"
        ? new URLSearchParams()
        : new URLSearchParams(window.location.search);
    const maxPrice = Number(params.get("maxPrice"));
    const minBeds = Number(params.get("minBeds"));
    const minBaths = Number(params.get("minBaths"));
    const district = params.get("district");
    const treeCover = params.get("treeCover");
    const regionGroup = params.get("regionGroup");

    setInitialFocus({
      districtName: district,
      districtSlug: params.get("districtSlug"),
      regionGroup,
    });

    setFilters((current) => ({
      ...current,
      maxPrice:
        Number.isFinite(maxPrice) && maxPrice > 0 ? Math.min(maxPrice, bounds.max) : bounds.max,
      minBeds: Number.isFinite(minBeds) && minBeds >= 0 ? minBeds : current.minBeds,
      minBaths: Number.isFinite(minBaths) && minBaths >= 0 ? minBaths : current.minBaths,
      goodOnly: params.get("goodOnly") === "true" || current.goodOnly,
      district: district && districtList.includes(district) ? district : current.district,
      treeCover:
        treeCover === "some" || treeCover === "leafy" || treeCover === "very-leafy"
          ? treeCover
          : current.treeCover,
      floodOnly: params.get("floodOnly") === "true" || current.floodOnly,
    }));
    setFiltersInitialized(true);
  }, [bounds.max, districtList, filtersInitialized, listingsQuery.isPending]);

  const isBooting =
    tokenQuery.isPending ||
    listingsQuery.isPending ||
    districtsQuery.isPending ||
    !filtersInitialized;

  const filtered = useMemo(() => applyFilters(allListings, filters), [allListings, filters]);

  useEffect(() => {
    if (
      selectedListing &&
      !filtered.features.some((feature) => feature.properties.id === selectedListing.properties.id)
    ) {
      setSelectedListing(null);
    }
  }, [filtered, selectedListing]);

  const sidebar = (
    <FiltersSidebar
      filters={filters}
      setFilters={setFilters}
      districts={districtList}
      priceMax={Math.max(bounds.max, 100_000)}
      resultCount={filtered.features.length}
      totalCount={allListings.features.length}
    />
  );

  const hasData = allListings.features.length > 0;

  return (
    <div className="flex h-screen w-full flex-col bg-background">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-2">
          <Home className="h-5 w-5 text-primary" />
          <h1 className="text-base font-semibold text-foreground">Groundtruth Explorer</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline" size="sm" className="hidden md:inline-flex">
            <Link to="/discover/results">
              <Compass className="mr-2 h-4 w-4" />
              Discover
            </Link>
          </Button>
          <div className="md:hidden">
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" size="sm">
                  <FilterIcon className="mr-2 h-4 w-4" /> Filters
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-[320px] p-0">
                <SheetTitle className="sr-only">Filters</SheetTitle>
                {sidebar}
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-80 shrink-0 overflow-y-auto border-r border-border md:block">
          {sidebar}
        </aside>

        <main className="relative min-h-0 flex-1">
          {isBooting ? (
            <div className="h-full w-full bg-muted" />
          ) : tokenQuery.isError || listingsQuery.isError || districtsQuery.isError ? (
            <EmptyState
              title="Groundtruth data didn't load"
              body="The request failed before the map could open. Check your connection and try again."
              actionLabel="Try again"
              onAction={() => {
                void Promise.all([
                  tokenQuery.refetch(),
                  listingsQuery.refetch(),
                  districtsQuery.refetch(),
                ]);
              }}
            />
          ) : !token ? (
            <EmptyState
              title="Mapbox token missing"
              body="Add MAPBOX_PUBLIC_TOKEN to enable the map."
            />
          ) : !hasData ? (
            <EmptyState
              title="No listings loaded"
              body="Check the database connection and try again."
            />
          ) : (
            <ClientOnly fallback={<div className="h-full w-full bg-muted" />}>
              <Suspense fallback={<div className="h-full w-full bg-muted" />}>
                <MapView
                  token={token}
                  listings={filtered}
                  districts={districts ?? null}
                  goodOnly={filters.goodOnly}
                  mapMetric={mapMetric}
                  onMapMetricChange={setMapMetric}
                  initialDistrictName={initialFocus.districtName}
                  initialDistrictSlug={initialFocus.districtSlug}
                  initialRegionGroup={initialFocus.regionGroup}
                  selectedListingId={selectedListing?.properties.id ?? null}
                  onListingSelect={setSelectedListing}
                />
                {filtered.features.length === 0 ? (
                  <div className="absolute top-32 left-3 z-[500] max-w-[min(24rem,calc(100%-1.5rem))] rounded-md border border-border bg-background/95 p-3 shadow-sm">
                    <p className="text-sm font-semibold text-foreground">
                      No listings match these filters
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      The map remains focused on the selected area. Adjust the price or other
                      filters to see listings.
                    </p>
                  </div>
                ) : null}
                <ListingDetailPanel
                  listing={selectedListing}
                  onClose={() => setSelectedListing(null)}
                />
              </Suspense>
            </ClientOnly>
          )}
        </main>
      </div>
    </div>
  );
}

function EmptyState({
  title,
  body,
  actionLabel,
  onAction,
}: {
  title: string;
  body: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="max-w-md rounded-lg border border-dashed border-border bg-card p-6 text-center">
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{body}</p>
        {actionLabel && onAction ? (
          <Button type="button" className="mt-4" size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
