import { useEffect, useRef } from "react";
import type { Feature, Geometry, Point } from "geojson";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { DistrictFC, ListingFC, ListingFeature, ListingProps } from "@/lib/housing/types";

interface Props {
  token: string;
  listings: ListingFC;
  districts: DistrictFC | null;
  goodOnly: boolean;
  selectedListingId: number | null;
  onListingSelect: (listing: ListingFeature) => void;
}

const DEFAULT_CENTER: L.LatLngTuple = [39.95, -75.3];
type ListingGeoFeature = Feature<Point, ListingProps>;
type DistrictGeoFeature = Feature<Geometry, { good_district?: boolean }>;

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

export function MapView({
  token,
  listings,
  districts,
  goodOnly,
  selectedListingId,
  onListingSelect,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const listingsLayerRef = useRef<L.GeoJSON | null>(null);
  const districtsLayerRef = useRef<L.GeoJSON | null>(null);
  const onListingSelectRef = useRef(onListingSelect);

  useEffect(() => {
    onListingSelectRef.current = onListingSelect;
  }, [onListingSelect]);

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
        marker.setStyle(markerStyle(props, null));
        marker.on("click", () => onListingSelectRef.current(feature));
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
    const listingsLayer = listingsLayerRef.current;
    if (!listingsLayer) return;

    listingsLayer.eachLayer((layer) => {
      const marker = layer as L.CircleMarker & { feature?: ListingGeoFeature };
      const props = marker.feature?.properties;
      if (props) marker.setStyle(markerStyle(props, selectedListingId));
    });
  }, [selectedListingId]);

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
