import { useEffect, useMemo, useRef } from "react";
import type { Feature, Geometry } from "geojson";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { DistrictFC, DistrictProps } from "@/lib/housing/types";
import type { DistrictPurchasingPower } from "@/lib/finance/server-data";

interface Props {
  token: string;
  districts: DistrictFC | null;
  purchasingPower: DistrictPurchasingPower[];
  selectedSlug: string | null;
  onDistrictSelect: (slug: string | null) => void;
}

type DistrictGeoFeature = Feature<Geometry, DistrictProps>;

const DEFAULT_CENTER: L.LatLngTuple = [40.6, -74.4];
const COLOR_STOPS = ["#b91c1c", "#f97316", "#eab308", "#22c55e", "#0284c7"];

function interpolateRank(value: number, min: number, max: number) {
  if (!Number.isFinite(value) || min === max) return 0.5;
  return Math.min(Math.max((value - min) / (max - min), 0), 1);
}

function colorForValue(value: number | undefined, min: number, max: number) {
  if (value === undefined) return "#cbd5e1";
  const rank = interpolateRank(value, min, max);
  const index = Math.min(Math.floor(rank * COLOR_STOPS.length), COLOR_STOPS.length - 1);
  return COLOR_STOPS[index];
}

export function RegionChoroplethMap({
  token,
  districts,
  purchasingPower,
  selectedSlug,
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
  const values = purchasingPower.map((district) => district.maxPurchasePrice);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;

  useEffect(() => {
    onDistrictSelectRef.current = onDistrictSelect;
  }, [onDistrictSelect]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current || !token) return;

    const map = L.map(containerRef.current, {
      zoomControl: false,
      preferCanvas: true,
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
    if (!map || !layer) return;

    layer.clearLayers();
    if (districts) {
      layer.addData(districts);
      const bounds = layer.getBounds();
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [28, 28] });
    }
  }, [districts]);

  useEffect(() => {
    const layer = districtsLayerRef.current;
    if (!layer) return;

    layer.eachLayer((districtLayer) => {
      const feature = (districtLayer as L.Path & { feature?: DistrictGeoFeature }).feature;
      const slug = feature?.properties?.district_slug ?? null;
      const power = slug ? powerBySlug.get(slug) : undefined;
      const isSelected = slug === selectedSlug;

      (districtLayer as L.Path).setStyle({
        color: isSelected ? "#0f172a" : "#475569",
        weight: isSelected ? 3 : 1,
        fillColor: colorForValue(power?.maxPurchasePrice, min, max),
        fillOpacity: power ? 0.55 : 0.16,
        opacity: 1,
      });
    });
  }, [powerBySlug, selectedSlug, min, max]);

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="h-full w-full" aria-label="Discovery map" />
      <div className="absolute right-3 bottom-3 z-[500] rounded-md border border-border bg-background/95 p-3 shadow-sm">
        <div className="flex items-center gap-1">
          {COLOR_STOPS.map((color) => (
            <span
              key={color}
              className="h-2 w-8"
              style={{ backgroundColor: color }}
              aria-hidden="true"
            />
          ))}
        </div>
        <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
          <span>Lower</span>
          <span>Higher</span>
        </div>
      </div>
    </div>
  );
}
