import type { Feature, FeatureCollection, Point, Polygon, MultiPolygon } from "geojson";

export interface ListingProps {
  id: number;
  address: string;
  city: string;
  zip: string | number;
  price: number;
  beds: number;
  baths: number;
  url: string | null;
  school_district: string;
  county_name?: string | null;
  good_district: boolean;
  canopy_height_m_100m?: number | null;
  flood_sfha?: number | null;
}

export interface DistrictProps {
  nces_geoid?: string;
  district_slug?: string | null;
  region_group?: string | null;
  name: string;
  good_district?: boolean;
}

export type ListingFeature = Feature<Point, ListingProps>;
export type ListingFC = FeatureCollection<Point, ListingProps>;
export type DistrictFeature = Feature<Polygon | MultiPolygon, DistrictProps>;
export type DistrictFC = FeatureCollection<Polygon | MultiPolygon, DistrictProps>;

export interface Filters {
  maxPrice: number;
  minBeds: number;
  minBaths: number;
  goodOnly: boolean;
  district: string; // "all" or a school_district name
  minCanopyHeight: number;
  floodOnly: boolean;
}

export type ListingMetricContext = "street" | "property" | "neighborhood";

export interface ListingMetricItem {
  metricKey: string;
  name: string;
  value: number;
  units: string | null;
  grain: string;
  vintage: string;
  source: string;
  nativeResolution: string | null;
  context: ListingMetricContext;
}

export interface ListingMetricsPayload {
  listing: ListingProps;
  metrics: ListingMetricItem[];
  tractMetrics: ListingMetricItem[];
}
