import { useEffect, useMemo, useState, lazy, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { ClientOnly } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { Filter as FilterIcon, Home } from "lucide-react";
import { FiltersSidebar } from "./FiltersSidebar";

const MapView = lazy(() => import("./MapView").then((m) => ({ default: m.MapView })));
import { getDistricts, getListings } from "@/lib/housing/listings.functions";
import { getMapboxToken } from "@/lib/housing/mapbox-token.functions";
import { applyFilters, DEFAULT_FILTERS, priceBounds, uniqueDistricts } from "@/lib/housing/filters";
import type { DistrictFC, Filters, ListingFC } from "@/lib/housing/types";

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
    queryFn: () => getDistrictsFn({ data: { simplifyTolerance: 0.001 } }),
    staleTime: 60 * 60 * 1000,
  });

  const token = tokenQuery.data?.token ?? "";
  const listings = listingsQuery.data ?? EMPTY_LISTINGS;
  const districts = (districtsQuery.data ?? null) as DistrictFC | null;
  const isBooting = tokenQuery.isPending || listingsQuery.isPending || districtsQuery.isPending;

  const allListings = listings;
  const bounds = useMemo(() => priceBounds(allListings), [allListings]);
  const districtList = useMemo(() => uniqueDistricts(allListings), [allListings]);

  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);

  // Initialize maxPrice when data loads
  useEffect(() => {
    if (allListings.features.length) {
      setFilters((f) =>
        f.maxPrice === DEFAULT_FILTERS.maxPrice ? { ...f, maxPrice: bounds.max } : f,
      );
    }
  }, [allListings, bounds.max]);

  const filtered = useMemo(() => applyFilters(allListings, filters), [allListings, filters]);

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
          <h1 className="text-base font-semibold text-foreground">Housing Search</h1>
        </div>
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
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-80 shrink-0 overflow-y-auto border-r border-border md:block">
          {sidebar}
        </aside>

        <main className="relative min-h-0 flex-1">
          {isBooting ? (
            <div className="h-full w-full bg-muted" />
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
                />
              </Suspense>
            </ClientOnly>
          )}
        </main>
      </div>
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="max-w-md rounded-lg border border-dashed border-border bg-card p-6 text-center">
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{body}</p>
      </div>
    </div>
  );
}
