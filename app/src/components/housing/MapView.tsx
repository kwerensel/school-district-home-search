import { useEffect, useRef } from "react";
import type { Feature, Geometry, Point } from "geojson";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { DistrictFC, ListingFC, ListingProps } from "@/lib/housing/types";

interface Props {
  token: string;
  listings: ListingFC;
  districts: DistrictFC | null;
  goodOnly: boolean;
}

const DEFAULT_CENTER: L.LatLngTuple = [39.95, -75.3];
type ListingGeoFeature = Feature<Point, ListingProps>;
type DistrictGeoFeature = Feature<Geometry, { good_district?: boolean }>;

function popupMarkup(p: ListingProps) {
  const href = p.url && p.url !== "null" ? p.url : "#";

  return `
    <div style="min-width:220px;padding:4px 2px;font-family:inherit;line-height:1.4;">
      <div style="font-size:16px;font-weight:600;color:#0f172a;">$${p.price.toLocaleString()}</div>
      <div style="margin-top:4px;font-size:14px;color:#0f172a;">${p.beds} bd · ${p.baths} ba</div>
      <div style="margin-top:6px;font-size:13px;color:#475569;">
        ${p.address}<br />
        ${p.city}, ${p.zip}
      </div>
      <div style="margin-top:6px;font-size:12px;color:#475569;">
        District: <strong style="color:#0f172a;">${p.school_district}</strong>
        ${p.good_district ? '<span style="margin-left:6px;display:inline-block;border-radius:999px;background:#dbeafe;padding:2px 6px;font-size:10px;font-weight:600;color:#1d4ed8;">Good</span>' : ""}
      </div>
      ${href === "#" ? "" : `<a href="${href}" target="_blank" rel="noreferrer noopener" style="margin-top:10px;display:inline-flex;width:100%;justify-content:center;border-radius:8px;background:#0f172a;padding:8px 12px;font-size:12px;font-weight:600;color:#ffffff;text-decoration:none;">View listing</a>`}
    </div>
  `;
}

export function MapView({ token, listings, districts, goodOnly }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const listingsLayerRef = useRef<L.GeoJSON | null>(null);
  const districtsLayerRef = useRef<L.GeoJSON | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current || !token) return;

    const map = L.map(containerRef.current, {
      zoomControl: false,
      preferCanvas: true,
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
        const price = Number(props.price ?? 0);
        const radius = price >= 2_000_000 ? 12 : price >= 1_000_000 ? 10 : price >= 500_000 ? 8 : 6;

        marker.setRadius(radius);
        marker.setStyle({ fillColor: props.good_district ? "#2563eb" : "#475569" });
        marker.bindPopup(popupMarkup(props), { maxWidth: 280, offset: [0, -2] });
      },
    }).addTo(map);

    districtsLayerRef.current = L.geoJSON(undefined, {
      style: (feature?: DistrictGeoFeature) => {
        const isGood = Boolean(feature?.properties?.good_district);
        const visible = !goodOnly || isGood;

        return {
          color: isGood ? "#15803d" : "#64748b",
          weight: 1,
          fillColor: isGood ? "#16a34a" : "#94a3b8",
          fillOpacity: visible ? (isGood ? 0.16 : 0.08) : 0,
          opacity: visible ? 1 : 0,
        };
      },
      interactive: false,
    }).addTo(map);

    mapRef.current = map;
    setTimeout(() => map.invalidateSize(), 0);

    return () => {
      listingsLayerRef.current = null;
      districtsLayerRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, [token, goodOnly]);

  useEffect(() => {
    const map = mapRef.current;
    const listingsLayer = listingsLayerRef.current;
    if (!map || !listingsLayer) return;

    listingsLayer.clearLayers();
    listingsLayer.addData(listings);

    if (listings.features.length) {
      const bounds = L.latLngBounds(
        listings.features.map((feature) => [
          feature.geometry.coordinates[1],
          feature.geometry.coordinates[0],
        ]),
      );
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: 14 });
    }
  }, [listings]);

  useEffect(() => {
    const districtsLayer = districtsLayerRef.current;
    if (!districtsLayer) return;

    districtsLayer.clearLayers();
    if (districts) districtsLayer.addData(districts);

    districtsLayer.setStyle((feature?: DistrictGeoFeature) => {
      const isGood = Boolean(feature?.properties?.good_district);
      const visible = !goodOnly || isGood;

      return {
        color: isGood ? "#15803d" : "#64748b",
        weight: 1,
        fillColor: isGood ? "#16a34a" : "#94a3b8",
        fillOpacity: visible ? (isGood ? 0.16 : 0.08) : 0,
        opacity: visible ? 1 : 0,
      };
    });
  }, [districts, goodOnly]);

  return <div ref={containerRef} className="absolute inset-0" aria-label="Map" />;
}
