import { useEffect, useMemo, useState, lazy, Suspense } from "react";
import { useServerFn } from "@tanstack/react-start";
import { ClientOnly } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { Filter as FilterIcon, Home } from "lucide-react";
import { FiltersSidebar } from "./FiltersSidebar";

const MapView = lazy(() => import("./MapView").then((m) => ({ default: m.MapView })));
import { getMapboxToken } from "@/lib/housing/mapbox-token.functions";
import { applyFilters, DEFAULT_FILTERS, priceBounds, uniqueDistricts } from "@/lib/housing/filters";
import type { DistrictFC, Filters, ListingFC } from "@/lib/housing/types";

const EMPTY_LISTINGS: ListingFC = { type: "FeatureCollection", features: [] };

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export function HousingSearch() {
  const getToken = useServerFn(getMapboxToken);
  const [token, setToken] = useState("");
  const [listings, setListings] = useState<ListingFC>(EMPTY_LISTINGS);
  const [districts, setDistricts] = useState<DistrictFC | null>(null);
  const [isBooting, setIsBooting] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsBooting(true);

      const [tokenResult, listingsResult, districtsResult] = await Promise.allSettled([
        getToken(),
        fetchJson<ListingFC>("/data/listings.geojson"),
        fetchJson<DistrictFC>("/data/districts.geojson"),
      ]);

      if (cancelled) return;

      setToken(tokenResult.status === "fulfilled" ? (tokenResult.value?.token ?? "") : "");
      setListings(
        listingsResult.status === "fulfilled"
          ? (listingsResult.value ?? EMPTY_LISTINGS)
          : EMPTY_LISTINGS,
      );
      setDistricts(districtsResult.status === "fulfilled" ? (districtsResult.value ?? null) : null);
      setIsBooting(false);
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

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
              body="Add public/data/listings.geojson (and optionally public/data/districts.geojson) to see pins on the map."
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
