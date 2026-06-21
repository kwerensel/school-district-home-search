import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { ExternalLink, Home, MapPin, Trees, Waves, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getListingMetrics } from "@/lib/housing/listings.functions";
import type { ListingFeature, ListingMetricContext, ListingMetricItem } from "@/lib/housing/types";

interface Props {
  listing: ListingFeature | null;
  onClose: () => void;
}

const contextOrder: ListingMetricContext[] = ["property", "street", "neighborhood"];
const contextLabels: Record<ListingMetricContext, string> = {
  property: "Property",
  street: "Street & Nearby",
  neighborhood: "Neighborhood Context",
};

function formatPrice(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatMetricValue(metric: ListingMetricItem) {
  if (metric.metricKey === "flood_sfha") return metric.value >= 1 ? "Yes" : "No";
  if (metric.units === "percent" || metric.metricKey.endsWith("_pct")) {
    return `${metric.value.toFixed(1)}%`;
  }
  if (metric.units) return `${metric.value.toFixed(1)} ${metric.units}`;
  return metric.value.toFixed(1);
}

function grainLabel(grain: string) {
  if (grain === "point") return "Point";
  if (grain === "buffer_100m") return "100 m";
  if (grain === "buffer_500m") return "500 m";
  if (grain === "census_tract") return "Tract";
  return grain;
}

function metricIcon(metric: ListingMetricItem) {
  if (metric.metricKey.includes("flood")) return <Waves className="h-4 w-4 text-sky-700" />;
  if (metric.metricKey.includes("canopy")) return <Trees className="h-4 w-4 text-emerald-700" />;
  return <MapPin className="h-4 w-4 text-slate-600" />;
}

export function ListingDetailPanel({ listing, onClose }: Props) {
  const getMetrics = useServerFn(getListingMetrics);
  const listingId = listing?.properties.id ?? null;

  const metricsQuery = useQuery({
    queryKey: ["listing-metrics", listingId],
    queryFn: () => getMetrics({ data: { listingId: listingId ?? 0 } }),
    enabled: listingId !== null,
    staleTime: 5 * 60 * 1000,
  });

  if (!listing) return null;

  const details = metricsQuery.data;
  const listingProps = details?.listing ?? listing.properties;
  const allMetrics = [...(details?.metrics ?? []), ...(details?.tractMetrics ?? [])];
  const knownValues = [
    typeof listingProps.canopy_height_m_100m === "number"
      ? {
          key: "canopy-height",
          label: "Canopy height",
          detail: "100 m known value",
          value: `${listingProps.canopy_height_m_100m.toFixed(1)} m`,
          icon: <Trees className="h-4 w-4 text-emerald-700" />,
        }
      : null,
    typeof listingProps.flood_sfha === "number"
      ? {
          key: "flood-sfha",
          label: "Mapped SFHA",
          detail: "FEMA point known value",
          value: listingProps.flood_sfha >= 1 ? "Yes" : "No",
          icon: <Waves className="h-4 w-4 text-sky-700" />,
        }
      : null,
  ].filter((value): value is NonNullable<typeof value> => value !== null);
  const href = listingProps.url && listingProps.url !== "null" ? listingProps.url : null;

  return (
    <aside className="absolute inset-x-3 bottom-3 z-[500] max-h-[74vh] overflow-hidden rounded-md border border-border bg-background shadow-lg md:inset-x-auto md:right-4 md:top-4 md:bottom-4 md:w-[380px]">
      <div className="flex h-full flex-col">
        <div className="flex items-start justify-between gap-3 border-b border-border p-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Home className="h-4 w-4 shrink-0 text-primary" />
              <p className="truncate text-lg font-semibold text-foreground">
                {formatPrice(listingProps.price)}
              </p>
            </div>
            <p className="mt-1 text-sm text-foreground">
              {listingProps.beds} bd · {listingProps.baths} ba
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              {listingProps.address}
              <br />
              {listingProps.city}, {listingProps.zip}
            </p>
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="space-y-3 border-b border-border pb-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-normal text-muted-foreground">
                School District
              </p>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium text-foreground">
                  {listingProps.school_district}
                </p>
                {listingProps.good_district ? <Badge variant="secondary">Good</Badge> : null}
              </div>
            </div>
            {href ? (
              <Button asChild className="w-full" size="sm">
                <a href={href} target="_blank" rel="noreferrer noopener">
                  <ExternalLink className="mr-2 h-4 w-4" />
                  View listing
                </a>
              </Button>
            ) : null}
          </div>

          {metricsQuery.isPending ? (
            <div className="space-y-2 py-4">
              <div className="h-4 w-32 rounded bg-muted" />
              <div className="h-12 rounded bg-muted" />
              <div className="h-12 rounded bg-muted" />
            </div>
          ) : null}

          {!metricsQuery.isPending && allMetrics.length === 0 && knownValues.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">No known values found.</p>
          ) : null}

          <div className="space-y-5 pt-4">
            {knownValues.length ? (
              <section className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">
                  Known Values
                </h3>
                <div className="divide-y divide-border rounded-md border border-border">
                  {knownValues.map((value) => (
                    <div key={value.key} className="flex items-center gap-3 px-3 py-2.5">
                      {value.icon}
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-foreground">
                          {value.label}
                        </p>
                        <p className="text-xs text-muted-foreground">{value.detail}</p>
                      </div>
                      <p className="shrink-0 text-sm font-semibold text-foreground">
                        {value.value}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            {contextOrder.map((context) => {
              const metrics = allMetrics.filter((metric) => metric.context === context);
              if (!metrics.length) return null;
              return (
                <section key={context} className="space-y-2">
                  <h3 className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">
                    {contextLabels[context]}
                  </h3>
                  <div className="divide-y divide-border rounded-md border border-border">
                    {metrics.map((metric) => (
                      <div
                        key={`${metric.metricKey}-${metric.grain}-${metric.vintage}`}
                        className="flex items-center gap-3 px-3 py-2.5"
                      >
                        {metricIcon(metric)}
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-foreground">
                            {metric.name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {grainLabel(metric.grain)} · {metric.nativeResolution ?? metric.vintage}
                          </p>
                        </div>
                        <p className="shrink-0 text-sm font-semibold text-foreground">
                          {formatMetricValue(metric)}
                        </p>
                      </div>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      </div>
    </aside>
  );
}
