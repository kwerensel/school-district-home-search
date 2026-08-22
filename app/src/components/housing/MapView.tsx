import { useEffect, useMemo, useRef } from "react";
import type { Feature, Geometry, Point } from "geojson";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  DistrictFC,
  DistrictProps,
  ListingFC,
  ListingFeature,
  ListingProps,
} from "@/lib/housing/types";
import {
  colorForMetricValue,
  EXPLORER_MAP_METRICS,
  formatMapMetricValue,
  MAP_METRIC_SCALES,
  type ExplorerMapMetricKey,
  type MapMetricKey,
} from "@/lib/metrics/presentation";

interface Props {
  token: string;
  listings: ListingFC;
  districts: DistrictFC | null;
  goodOnly: boolean;
  mapMetric: ExplorerMapMetricKey;
  onMapMetricChange: (metric: ExplorerMapMetricKey) => void;
  initialDistrictName: string | null;
  initialDistrictSlug: string | null;
  initialRegionGroup: string | null;
  selectedListingId: number | null;
  onListingSelect: (listing: ListingFeature) => void;
}

const DEFAULT_CENTER: L.LatLngTuple = [39.95, -75.3];
type ListingGeoFeature = Feature<Point, ListingProps>;
type DistrictGeoFeature = Feature<Geometry, DistrictProps>;

function markerStyle(props: ListingProps, selectedListingId: number | null): L.CircleMarkerOptions {
  const price = Number(props.price ?? 0);
  const radius = price >= 2_000_000 ? 12 : price >= 1_000_000 ? 10 : price >= 500_000 ? 8 : 6;
  const isSelected = props.id === selectedListingId;

  return {
    radius: isSelected ? radius + 4 : radius,
    weight: isSelected ? 3 : 1.5,
    color: isSelected ? "#111827" : "#ffffff",
    fillColor: props.good_district ? "#2563eb" : "#475569",
    fillOpacity: 0.92,
  };
}

function districtMetricValue(props: DistrictProps, metric: ExplorerMapMetricKey) {
  if (metric === "treeCanopy") return props.tree_canopy_pct ?? null;
  if (metric === "floodExposure") return props.flood_sfha ?? null;
  if (metric === "lightPollution") return props.light_pollution_radiance ?? null;
  if (metric === "walkability") return props.walkability_index ?? null;
  if (metric === "parkAccess") return props.park_access ?? null;
  if (metric === "risk") return props.risk_index ?? null;
  return null;
}

export function MapView({
  token,
  listings,
  districts,
  goodOnly,
  mapMetric,
  onMapMetricChange,
  initialDistrictName,
  initialDistrictSlug,
  initialRegionGroup,
  selectedListingId,
  onListingSelect,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const listingsLayerRef = useRef<L.GeoJSON | null>(null);
  const districtsLayerRef = useRef<L.GeoJSON | null>(null);
  const onListingSelectRef = useRef(onListingSelect);
  const hasInitialFitRef = useRef(false);
  const metricValues = useMemo(
    () =>
      districts?.features
        .map((feature) => districtMetricValue(feature.properties, mapMetric))
        .filter((value): value is number => value !== null && Number.isFinite(value)) ?? [],
    [districts, mapMetric],
  );
  const minMetricValue = metricValues.length ? Math.min(...metricValues) : 0;
  const maxMetricValue = metricValues.length ? Math.max(...metricValues) : 0;

  useEffect(() => {
    onListingSelectRef.current = onListingSelect;
  }, [onListingSelect]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current || !token) return;

    const map = L.map(containerRef.current, {
      zoomControl: false,
      renderer: L.svg(),
    }).setView(DEFAULT_CENTER, 11);
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
      style: {
        color: "#64748b",
        weight: 1,
        fillColor: "#94a3b8",
        fillOpacity: 0.08,
        opacity: 1,
      },
    }).addTo(map);

    listingsLayerRef.current = L.geoJSON(undefined, {
      pointToLayer: (_feature: ListingGeoFeature, latlng: L.LatLng) =>
        L.circleMarker(latlng, {
          radius: 7,
          weight: 1.5,
          color: "#ffffff",
          fillColor: "#2563eb",
          fillOpacity: 0.92,
        }),
      onEachFeature: (feature: ListingGeoFeature, layer: L.Layer) => {
        const props = feature.properties as ListingProps;
        const marker = layer as L.CircleMarker;
        marker.setStyle(markerStyle(props, null));
        marker.on("click", () => onListingSelectRef.current(feature));
      },
    }).addTo(map);

    mapRef.current = map;
    setTimeout(() => map.invalidateSize(), 0);

    return () => {
      listingsLayerRef.current = null;
      districtsLayerRef.current = null;
      hasInitialFitRef.current = false;
      map.remove();
      mapRef.current = null;
    };
  }, [token]);

  useEffect(() => {
    const listingsLayer = listingsLayerRef.current;
    if (!listingsLayer) return;
    listingsLayer.eachLayer((layer) => {
      const marker = layer as L.CircleMarker & { feature?: ListingGeoFeature };
      const props = marker.feature?.properties;
      if (props) marker.setStyle(markerStyle(props, selectedListingId));
    });
  }, [selectedListingId]);

  useEffect(() => {
    const listingsLayer = listingsLayerRef.current;
    if (!listingsLayer) return;
    listingsLayer.clearLayers();
    listingsLayer.addData(listings);
  }, [listings]);

  useEffect(() => {
    const districtsLayer = districtsLayerRef.current;
    if (!districtsLayer) return;
    districtsLayer.clearLayers();
    if (districts) districtsLayer.addData(districts);

    districtsLayer.eachLayer((layer) => {
      const path = layer as L.Path & { feature?: DistrictGeoFeature };
      const props = path.feature?.properties;
      if (!props) return;
      const isGood = Boolean(props.good_district);
      const value = districtMetricValue(props, mapMetric);
      const isSchoolLayer = mapMetric === "schoolDistricts";
      const visible = isSchoolLayer ? !goodOnly || isGood : true;
      const fillColor = isSchoolLayer
        ? isGood
          ? "#16a34a"
          : "#94a3b8"
        : colorForMetricValue(mapMetric, value, minMetricValue, maxMetricValue);

      path.setStyle({
        color: isSchoolLayer && isGood ? "#15803d" : "#64748b",
        weight: 1,
        fillColor,
        fillOpacity: visible
          ? isSchoolLayer
            ? isGood
              ? 0.16
              : 0.08
            : value === null
              ? 0.1
              : 0.52
          : 0,
        opacity: visible ? 1 : 0,
      });

      if (isSchoolLayer) {
        path.bindTooltip(`${props.name}${isGood ? " · Good-district placeholder" : ""}`, {
          sticky: true,
        });
      } else {
        path.bindTooltip(`${props.name} · ${formatMapMetricValue(mapMetric, value)}`, {
          sticky: true,
        });
      }
    });

    listingsLayerRef.current?.eachLayer((layer) => {
      (layer as L.Path).bringToFront();
    });
  }, [districts, goodOnly, mapMetric, minMetricValue, maxMetricValue]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !districts || hasInitialFitRef.current) return;

    const focusDistrict = districts.features.find((feature) => {
      if (initialDistrictSlug && feature.properties.district_slug === initialDistrictSlug) {
        return true;
      }
      return Boolean(
        initialDistrictName &&
        feature.properties.name === initialDistrictName &&
        (!initialRegionGroup || feature.properties.region_group === initialRegionGroup),
      );
    });

    if (focusDistrict) {
      const bounds = L.geoJSON(focusDistrict).getBounds();
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [36, 36], maxZoom: 12 });
      hasInitialFitRef.current = true;
      return;
    }

    if (listings.features.length) {
      const bounds = L.latLngBounds(
        listings.features.map((feature) => [
          feature.geometry.coordinates[1],
          feature.geometry.coordinates[0],
        ]),
      );
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: 14 });
      hasInitialFitRef.current = true;
      return;
    }

    if (initialRegionGroup) {
      const regionFeatures = districts.features.filter(
        (feature) => feature.properties.region_group === initialRegionGroup,
      );
      const bounds = L.geoJSON({ type: "FeatureCollection", features: regionFeatures }).getBounds();
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [36, 36] });
      hasInitialFitRef.current = true;
    }
  }, [districts, initialDistrictName, initialDistrictSlug, initialRegionGroup, listings]);

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="h-full w-full" aria-label="Map" />
      <div className="absolute top-3 left-3 z-[500] w-56 rounded-md border border-border bg-background/95 p-3 shadow-sm">
        <label className="mb-2 block text-xs font-medium text-foreground">Color map by</label>
        <Select
          value={mapMetric}
          onValueChange={(value) => onMapMetricChange(value as ExplorerMapMetricKey)}
        >
          <SelectTrigger className="h-8 bg-background" aria-label="Color map by">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {EXPLORER_MAP_METRICS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {mapMetric !== "schoolDistricts" ? (
          <p className="mt-2 text-[11px] leading-4 text-muted-foreground">
            District-level context, not a property-level reading.
          </p>
        ) : null}
      </div>
      <MapLegend
        goodOnly={goodOnly}
        mapMetric={mapMetric}
        minMetricValue={minMetricValue}
        maxMetricValue={maxMetricValue}
      />
    </div>
  );
}

function MapLegend({
  goodOnly,
  mapMetric,
  minMetricValue,
  maxMetricValue,
}: {
  goodOnly: boolean;
  mapMetric: ExplorerMapMetricKey;
  minMetricValue: number;
  maxMetricValue: number;
}) {
  if (mapMetric !== "schoolDistricts") {
    const scale = MAP_METRIC_SCALES[mapMetric as MapMetricKey];
    return (
      <div className="absolute right-3 bottom-3 z-[500] rounded-md border border-border bg-background/95 p-3 text-xs shadow-sm">
        <p className="font-medium text-foreground">{scale.label}</p>
        <div className="mt-2 flex items-center gap-0.5">
          {scale.colors.map((color) => (
            <span key={color} className="h-2 w-8" style={{ backgroundColor: color }} />
          ))}
        </div>
        <div className="mt-1 flex justify-between gap-6 text-[11px] text-muted-foreground">
          <span>{scale.lowLabel}</span>
          <span>{scale.highLabel}</span>
        </div>
        <p className="mt-2 text-[10px] text-muted-foreground">District-level context</p>
        <p className="mt-1 max-w-72 text-[10px] text-muted-foreground">
          Observed range: {formatMapMetricValue(mapMetric, minMetricValue)} to{" "}
          {formatMapMetricValue(mapMetric, maxMetricValue)}
        </p>
      </div>
    );
  }

  return (
    <div
      className="absolute right-3 bottom-3 z-[500] max-w-[min(18rem,calc(100%-1.5rem))] rounded-md border border-border bg-background/95 p-3 text-xs shadow-sm"
      data-testid="explorer-map-legend"
    >
      <p className="mb-2 font-medium text-foreground">Map colors</p>
      <div className="space-y-2">
        <LegendRow color="#2563eb" label="Listing with prototype district flag" shape="dot" />
        <LegendRow color="#475569" label="Other listing" shape="dot" />
        <LegendRow color="#16a34a" label="Prototype-flagged district" shape="area" />
        {!goodOnly ? (
          <LegendRow color="#94a3b8" label="Other district boundary" shape="area" />
        ) : null}
      </div>
    </div>
  );
}

function LegendRow({
  color,
  label,
  shape,
}: {
  color: string;
  label: string;
  shape: "area" | "dot";
}) {
  return (
    <div className="flex items-center gap-2 text-muted-foreground">
      <span
        className={shape === "dot" ? "h-3 w-3 rounded-full" : "h-3 w-5 rounded-sm border"}
        style={{
          backgroundColor: color,
          borderColor: shape === "area" ? color : undefined,
          opacity: shape === "area" ? 0.45 : 1,
        }}
        aria-hidden="true"
      />
      <span>{label}</span>
    </div>
  );
}
