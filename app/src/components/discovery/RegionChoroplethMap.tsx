import { useEffect, useMemo, useRef } from "react";
import type { Feature, Geometry } from "geojson";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { DistrictFC, DistrictProps } from "@/lib/housing/types";
import type { DistrictPurchasingPower } from "@/lib/finance/server-data";
import {
  colorForMetricValue,
  DISCOVERY_MAP_METRICS,
  formatMapMetricValue,
  MAP_METRIC_SCALES,
  type MapMetricKey,
} from "@/lib/metrics/presentation";

interface Props {
  token: string;
  districts: DistrictFC | null;
  purchasingPower: DistrictPurchasingPower[];
  selectedSlug: string | null;
  rankBySlug: Map<string, number>;
  activeMetric: MapMetricKey;
  onActiveMetricChange: (metric: MapMetricKey) => void;
  onDistrictSelect: (slug: string | null) => void;
}

type DistrictGeoFeature = Feature<Geometry, DistrictProps>;
const DEFAULT_CENTER: L.LatLngTuple = [40.6, -74.4];

function metricValue(district: DistrictPurchasingPower, metric: MapMetricKey) {
  if (metric === "purchasingPower") return district.maxPurchasePrice;
  if (metric === "treeCanopy") return district.environmentMetrics.treeCanopyPct;
  if (metric === "floodExposure") return district.environmentMetrics.floodSfha;
  if (metric === "lightPollution") return district.environmentMetrics.lightPollutionRadiance;
  if (metric === "walkability") return district.environmentMetrics.walkabilityIndex;
  if (metric === "parkAccess") return district.environmentMetrics.parkAccess;
  if (metric === "transitAccess") return district.environmentMetrics.transitAccess;
  if (metric === "commuteMinutes") return district.environmentMetrics.commuteMinutes;
  if (metric === "airQuality") return district.environmentMetrics.aqiAnnualMean;
  return district.environmentMetrics.riskIndex;
}

export function RegionChoroplethMap({
  token,
  districts,
  purchasingPower,
  selectedSlug,
  rankBySlug,
  activeMetric,
  onActiveMetricChange,
  onDistrictSelect,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const districtsLayerRef = useRef<L.GeoJSON | null>(null);
  const onDistrictSelectRef = useRef(onDistrictSelect);
  const powerBySlug = useMemo(
    () => new Map(purchasingPower.map((district) => [district.districtSlug, district])),
    [purchasingPower],
  );
  const scopeKey = useMemo(
    () =>
      purchasingPower
        .map((district) => district.districtSlug)
        .sort()
        .join("|"),
    [purchasingPower],
  );
  const eligibleSlugs = useMemo(() => new Set(scopeKey.split("|")), [scopeKey]);
  const visibleDistricts = useMemo<DistrictFC | null>(() => {
    if (!districts) return null;
    return {
      type: "FeatureCollection",
      features: districts.features.filter((feature) => {
        const slug = feature.properties.district_slug;
        return Boolean(slug && eligibleSlugs.has(slug));
      }),
    };
  }, [districts, eligibleSlugs]);
  const values = purchasingPower
    .map((district) => metricValue(district, activeMetric))
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const selected = selectedSlug ? powerBySlug.get(selectedSlug) : null;
  const selectedValue = selected ? metricValue(selected, activeMetric) : null;
  const scale = MAP_METRIC_SCALES[activeMetric];

  useEffect(() => {
    onDistrictSelectRef.current = onDistrictSelect;
  }, [onDistrictSelect]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current || !token) return;

    const map = L.map(containerRef.current, {
      zoomControl: false,
      renderer: L.svg(),
    }).setView(DEFAULT_CENTER, 8);
    L.control.zoom({ position: "topright" }).addTo(map);
    L.tileLayer(
      `https://api.mapbox.com/styles/v1/mapbox/light-v11/tiles/512/{z}/{x}/{y}@2x?access_token=${token}`,
      {
        tileSize: 512,
        zoomOffset: -1,
        maxZoom: 18,
        attribution:
          '&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      },
    ).addTo(map);

    districtsLayerRef.current = L.geoJSON(undefined, {
      style: { color: "#334155", weight: 1, fillColor: "#cbd5e1", fillOpacity: 0.35 },
      onEachFeature: (feature: DistrictGeoFeature, layer: L.Layer) => {
        const slug = feature.properties?.district_slug ?? null;
        layer.on("click", () => onDistrictSelectRef.current(slug));
      },
    }).addTo(map);

    mapRef.current = map;
    setTimeout(() => map.invalidateSize(), 0);

    return () => {
      districtsLayerRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, [token]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = districtsLayerRef.current;
    if (!map || !layer || !visibleDistricts) return;

    layer.clearLayers();
    layer.addData(visibleDistricts);
    const bounds = layer.getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [28, 28] });
  }, [visibleDistricts, scopeKey]);

  useEffect(() => {
    const layer = districtsLayerRef.current;
    if (!layer) return;

    layer.eachLayer((districtLayer) => {
      const feature = (districtLayer as L.Path & { feature?: DistrictGeoFeature }).feature;
      const slug = feature?.properties?.district_slug ?? null;
      const district = slug ? powerBySlug.get(slug) : undefined;
      const value = district ? metricValue(district, activeMetric) : null;
      const isSelected = slug === selectedSlug;
      const path = districtLayer as L.Path;

      path.setStyle({
        color: isSelected ? "#0f172a" : "#475569",
        weight: isSelected ? 3 : 1,
        fillColor: colorForMetricValue(activeMetric, value, min, max),
        fillOpacity: value === null ? 0.15 : 0.58,
        opacity: 1,
      });
      if (district) {
        const rank = rankBySlug.get(district.districtSlug);
        path.bindTooltip(
          `${district.districtName} · ${rank ? `#${rank} of ${purchasingPower.length} · ` : ""}${formatMapMetricValue(activeMetric, value)}`,
          { sticky: true },
        );
      }
      if (isSelected) path.bringToFront();
    });
  }, [activeMetric, max, min, powerBySlug, purchasingPower.length, rankBySlug, selectedSlug]);

  return (
    <div className="absolute inset-0">
      <div
        ref={containerRef}
        className="h-full w-full"
        aria-label="Discovery map"
        data-district-count={visibleDistricts?.features.length ?? 0}
      />
      <div className="absolute top-3 left-3 z-[500] w-56 rounded-md border border-border bg-background/95 p-3 shadow-sm">
        <label className="mb-2 block text-xs font-medium text-foreground">Color map by</label>
        <Select
          value={activeMetric}
          onValueChange={(value) => onActiveMetricChange(value as MapMetricKey)}
        >
          <SelectTrigger className="h-8 bg-background" aria-label="Color map by">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DISCOVERY_MAP_METRICS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="mt-2 text-[11px] leading-4 text-muted-foreground">
          One district-level layer at a time. Hover for the value.
        </p>
      </div>

      {selected ? (
        <div
          className="absolute top-32 left-3 z-[500] max-w-[min(22rem,calc(100%-1.5rem))] rounded-md border border-border bg-background/95 p-3 shadow-sm"
          data-testid="selected-district-map-card"
        >
          <div className="flex items-center justify-between gap-3 text-[11px] font-medium uppercase tracking-normal text-muted-foreground">
            <p>Selected district</p>
            <p>
              #{rankBySlug.get(selected.districtSlug) ?? "-"} of {purchasingPower.length}
            </p>
          </div>
          <p className="mt-1 truncate text-sm font-semibold text-foreground">
            {selected.districtName}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">{scale.shortLabel}</p>
          <p className="mt-0.5 text-sm font-semibold text-foreground">
            {formatMapMetricValue(activeMetric, selectedValue)}
          </p>
        </div>
      ) : null}

      <div
        className="absolute right-3 bottom-3 z-[500] rounded-md border border-border bg-background/95 p-3 shadow-sm"
        data-testid="district-layer-legend"
      >
        <p className="text-xs font-medium text-foreground">{scale.label}</p>
        <div className="mt-2 flex items-center gap-0.5">
          {scale.colors.map((color) => (
            <span key={color} className="h-2 w-8" style={{ backgroundColor: color }} />
          ))}
        </div>
        <div className="mt-1 flex justify-between gap-6 text-[11px] text-muted-foreground">
          <span>{scale.lowLabel}</span>
          <span>{scale.highLabel}</span>
        </div>
        <p className="mt-2 text-[10px] text-muted-foreground">District-level comparison</p>
      </div>
    </div>
  );
}
