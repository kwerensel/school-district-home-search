import type { Feature, FeatureCollection, Point, Polygon, MultiPolygon } from "geojson";

export interface ListingProps {
  address: string;
  city: string;
  zip: string | number;
  price: number;
  beds: number;
  baths: number;
  url: string;
  school_district: string;
  good_district: boolean;
}

export interface DistrictProps {
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
}
