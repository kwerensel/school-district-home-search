import { useQuery } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { Bus, ExternalLink, Home, MapPin, Ruler, Trees, Waves, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { WalkabilityExplainer } from "@/components/metrics/WalkabilityExplainer";
import { MetricExplainer } from "@/components/metrics/MetricExplainer";
import { getListingMetrics } from "@/lib/housing/listings.functions";
import { lightPollutionCategory, treeCoverCategory } from "@/lib/metrics/presentation";
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

function formatDistance(value: number) {
  return value < 1000 ? `${Math.round(value)} m` : `${(value / 1000).toFixed(1)} km`;
}

function formatMetricValue(metric: ListingMetricItem) {
  if (metric.metricKey === "flood_sfha") {
    return metric.grain === "point"
      ? metric.value >= 1
        ? "Yes"
        : "No"
      : `${(metric.value * 100).toFixed(1)}% of land`;
  }
  if (metric.metricKey === "tree_canopy_pct") {
    return `${treeCoverCategory(metric.value)} · ${metric.value.toFixed(0)}%`;
  }
  if (metric.metricKey === "light_pollution_radiance") {
    return `${lightPollutionCategory(metric.value)} · ${metric.value.toFixed(1)}`;
  }
  if (metric.metricKey === "walkability_index") return `${metric.value.toFixed(1)} / 20`;
  if (metric.metricKey === "effective_tax_rate") {
    return `${(metric.value * 100).toFixed(2)}%`;
  }
  if (metric.metricKey === "park_access") {
    return `${(metric.value * 100).toFixed(1)}% of land within 800 m`;
  }
  if (metric.metricKey === "transit_access") {
    return `${metric.value.toFixed(1)} mapped stops / km²`;
  }
  if (metric.metricKey.startsWith("commute_minutes_")) {
    return `${metric.value.toFixed(0)} min by car`;
  }
  if (metric.metricKey === "aqi_annual_mean") {
    return `${metric.value.toFixed(0)} annual mean daily AQI`;
  }
  if (metric.metricKey === "noise_mean_dba") {
    return `${metric.value.toFixed(1)} dBA modeled mean`;
  }
  if (metric.metricKey === "noise_pct_over_45") {
    return `${metric.value.toFixed(1)}% at or above 45 dBA`;
  }
  if (metric.metricKey === "noise_pct_over_55") {
    return `${metric.value.toFixed(1)}% at or above 55 dBA`;
  }
  if (metric.metricKey === "noise_siren_distance_m") {
    return formatDistance(metric.value);
  }
  if (metric.metricKey === "noise_nightlife_count_300m") {
    return metric.value === 0
      ? "None mapped within 300 m"
      : `${Math.round(metric.value)} mapped within 300 m`;
  }
  if (metric.metricKey === "noise_industrial_distance_m") {
    return `${metric.value <= 500 ? "Within 500 m · " : ""}${formatDistance(metric.value)}`;
  }
  if (metric.metricKey === "noise_freight_rail_distance_m") {
    return `${metric.value <= 500 ? "Within 500 m · " : ""}${formatDistance(metric.value)}`;
  }
  if (metric.metricKey === "park_distance_m" || metric.metricKey === "transit_distance_m") {
    return formatDistance(metric.value);
  }
  if (metric.units === "percent" || metric.metricKey.endsWith("_pct")) {
    return `${metric.value.toFixed(1)}%`;
  }
  if (metric.units) return `${metric.value.toFixed(1)} ${metric.units}`;
  return metric.value.toFixed(1);
}

function grainLabel(grain: string) {
  if (grain === "point") return "Point";
  if (grain === "buffer_100m") return "100 m";
  if (grain === "buffer_300m") return "300 m";
  if (grain === "buffer_500m") return "500 m";
  if (grain === "census_tract") return "Tract";
  return grain;
}

function metricIcon(metric: ListingMetricItem) {
  if (metric.metricKey.includes("flood")) return <Waves className="h-4 w-4 text-sky-700" />;
  if (metric.metricKey === "tree_canopy_pct") {
    return <Trees className="h-4 w-4 text-emerald-700" />;
  }
  if (metric.metricKey === "park_distance_m") {
    return <Trees className="h-4 w-4 text-green-700" />;
  }
  if (metric.metricKey === "transit_distance_m") {
    return <Bus className="h-4 w-4 text-blue-700" />;
  }
  if (metric.metricKey === "canopy_height_m") {
    return <Ruler className="h-4 w-4 text-emerald-800" />;
  }
  return <MapPin className="h-4 w-4 text-slate-600" />;
}

function metricName(metric: ListingMetricItem) {
  if (metric.metricKey === "flood_sfha") {
    return metric.grain === "point"
      ? "Inside FEMA high-risk flood zone"
      : "FEMA flood-zone exposure";
  }
  if (metric.metricKey === "tree_canopy_pct") return "Tree coverage";
  if (metric.metricKey === "canopy_height_m") return "Average canopy height";
  if (metric.metricKey === "light_pollution_radiance") return "Light pollution";
  if (metric.metricKey === "park_distance_m") return "Distance to mapped park or open space";
  if (metric.metricKey === "transit_distance_m") return "Distance to mapped transit stop";
  if (metric.metricKey === "transit_access") return "Transit-stop density";
  if (metric.metricKey === "aqi_annual_mean") return "Annual mean daily AQI";
  if (metric.metricKey === "noise_mean_dba") return "Modeled transportation noise";
  if (metric.metricKey === "noise_pct_over_45") return "Area with modeled noise ≥45 dBA";
  if (metric.metricKey === "noise_pct_over_55") return "Area with modeled noise ≥55 dBA";
  if (metric.metricKey === "noise_siren_distance_m") {
    return "Nearest mapped emergency-response facility";
  }
  if (metric.metricKey === "noise_nightlife_count_300m") {
    return "Mapped nightlife venues nearby";
  }
  if (metric.metricKey === "noise_industrial_distance_m") {
    return "Distance to mapped industrial land";
  }
  if (metric.metricKey === "noise_freight_rail_distance_m") {
    return "Distance to active freight-capable rail";
  }
  return metric.name;
}

function metricHelp(metric: ListingMetricItem) {
  if (metric.metricKey === "walkability_index") return <WalkabilityExplainer compact />;
  if (metric.metricKey === "park_distance_m") {
    return (
      <MetricExplainer compact label="How park distance works" title="Mapped park proximity">
        <p>
          Straight-line distance from the listing point to the nearest mapped public park or open
          space polygon edge. Zero means the point falls inside a mapped polygon.
        </p>
        <p>It is not walking-route distance and does not confirm an accessible entrance.</p>
      </MetricExplainer>
    );
  }
  if (metric.metricKey === "transit_distance_m") {
    return (
      <MetricExplainer compact label="How transit distance works" title="Mapped transit proximity">
        <p>
          Straight-line distance from the listing point to the nearest active GTFS stop mapped by
          Transitland.
        </p>
        <p>
          It is not a walking route and does not measure service frequency, reliability, or
          accessibility.
        </p>
      </MetricExplainer>
    );
  }
  if (metric.metricKey === "transit_access") {
    return (
      <MetricExplainer compact label="How transit access works" title="Mapped transit-stop density">
        <p>
          Active GTFS stops mapped by Transitland per square kilometer. This tract-level context
          does not measure service frequency, reliability, or walking access.
        </p>
      </MetricExplainer>
    );
  }
  if (metric.metricKey.startsWith("commute_minutes_")) {
    return (
      <MetricExplainer compact label="How drive time works" title="Regional drive time">
        <p>
          Routed from a population-weighted census-tract origin to the named city anchor under the
          routing engine's standard driving assumptions.
        </p>
        <p>It is neighborhood context, not live traffic or an address-specific estimate.</p>
      </MetricExplainer>
    );
  }
  if (metric.metricKey === "aqi_annual_mean") {
    return (
      <MetricExplainer compact label="How air quality works" title="Annual air quality">
        <p>
          EPA daily AQI is averaged at regulatory monitors and interpolated to this census tract
          from monitors within 30 km, with a county monitor mean fallback. Lower is cleaner.
        </p>
        <p>This is coarse neighborhood context, not a live or address-level reading.</p>
      </MetricExplainer>
    );
  }
  if (
    metric.metricKey === "noise_siren_distance_m" ||
    metric.metricKey === "noise_nightlife_count_300m" ||
    metric.metricKey === "noise_industrial_distance_m"
  ) {
    return (
      <MetricExplainer
        compact
        label="How this source proxy works"
        title="Mapped possible noise source"
        sourceHref="https://www.openstreetmap.org/copyright"
        sourceLabel="OpenStreetMap data and attribution"
      >
        <p>
          This value uses mapped emergency-response facilities, nightlife venues, or industrial land
          as context for a possible activity source. It does not measure sound, events, operating
          hours, or route-level exposure.
        </p>
        <p>
          Distances are straight-line distances. OpenStreetMap is community maintained, so mapping
          completeness varies by place and over time.
        </p>
      </MetricExplainer>
    );
  }
  if (metric.metricKey === "noise_freight_rail_distance_m") {
    return (
      <MetricExplainer
        compact
        label="How this rail proxy works"
        title="Active freight-capable rail proximity"
        sourceHref="https://railroads.dot.gov/rail-network-development/maps-and-data/maps-geographic"
        sourceLabel="View FRA rail network sources"
      >
        <p>
          Straight-line distance to a Federal Railroad Administration line classified as active
          main, industrial, siding, or yard track. Classification indicates freight capability, not
          actual train frequency, schedules, horns, or sound.
        </p>
      </MetricExplainer>
    );
  }
  if (
    metric.metricKey === "noise_mean_dba" ||
    metric.metricKey === "noise_pct_over_45" ||
    metric.metricKey === "noise_pct_over_55"
  ) {
    return (
      <MetricExplainer
        compact
        label="How transportation noise works"
        title="Modeled transportation noise"
        sourceHref="https://www.bts.gov/geospatial/national-transportation-noise-map"
        sourceLabel="View the BTS National Transportation Noise Map"
      >
        <p>
          The Bureau of Transportation Statistics models 24-hour average aviation, road, and rail
          noise. Mean dBA is estimated from the published noise-class midpoints; threshold values
          preserve the published classes.
        </p>
        <p>
          This is screening context, not a live measurement or parcel study. The simplified model
          omits shielding and can overestimate some locations.
        </p>
      </MetricExplainer>
    );
  }
  if (metric.metricKey === "tree_canopy_pct") {
    return (
      <MetricExplainer compact label="How tree coverage works" title="Tree coverage">
        <p>
          The share of land covered by tree canopy in this area. Consumer labels run from Sparse to
          Very leafy; the percentage remains available as supporting detail.
        </p>
        <p>A 100 m value describes the nearby street context, not only this parcel.</p>
      </MetricExplainer>
    );
  }
  if (metric.metricKey === "canopy_height_m") {
    return (
      <MetricExplainer compact label="How canopy height works" title="Average canopy height">
        <p>
          Mean mapped vegetation height across the stated area. It can help distinguish taller from
          lower vegetation, but it does not measure tree age, old growth, or sidewalk shade.
        </p>
      </MetricExplainer>
    );
  }
  if (metric.metricKey === "light_pollution_radiance") {
    return (
      <MetricExplainer compact label="How light pollution works" title="Light pollution">
        <p>
          VIIRS satellite radiance measures upward nighttime light. Lower is darker. A raw value
          such as 1 is not a 1-to-10 score; it is a radiance measurement used to assign the
          plain-language darkness category.
        </p>
        <p>This is coarse neighborhood context, not an address-level reading.</p>
      </MetricExplainer>
    );
  }
  if (metric.metricKey === "flood_sfha") {
    return (
      <MetricExplainer
        compact
        label="How FEMA flood-zone data works"
        title="FEMA high-risk flood zone"
        sourceHref="https://www.fema.gov/flood-maps/national-flood-hazard-layer"
        sourceLabel="View FEMA National Flood Hazard Layer"
      >
        <p>
          A property value says whether the listing point falls inside a mapped Special Flood Hazard
          Area. A neighborhood or district value instead shows the share of land covered.
        </p>
        <p>It is screening context, not a parcel survey or insurance determination.</p>
      </MetricExplainer>
    );
  }
  return null;
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
    typeof listingProps.tree_canopy_pct_100m === "number"
      ? {
          key: "tree-cover",
          label: "Nearby tree coverage",
          detail: `${listingProps.tree_canopy_pct_100m.toFixed(0)}% within 100 m`,
          value: treeCoverCategory(listingProps.tree_canopy_pct_100m),
          icon: <Trees className="h-4 w-4 text-emerald-700" />,
        }
      : null,
    typeof listingProps.canopy_height_m_100m === "number"
      ? {
          key: "canopy-height",
          label: "Average canopy height",
          detail: "Mapped vegetation within 100 m",
          value: `${listingProps.canopy_height_m_100m.toFixed(1)} m`,
          icon: <Ruler className="h-4 w-4 text-emerald-800" />,
        }
      : null,
    typeof listingProps.flood_sfha === "number"
      ? {
          key: "flood-sfha",
          label: "Inside FEMA high-risk flood zone",
          detail: "Listing point in mapped SFHA",
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
                {listingProps.good_district ? (
                  <Badge variant="secondary">Prototype district flag</Badge>
                ) : null}
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
                          <div className="flex items-center gap-1.5">
                            <p className="truncate text-sm font-medium text-foreground">
                              {metricName(metric)}
                            </p>
                            {metricHelp(metric)}
                          </div>
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
