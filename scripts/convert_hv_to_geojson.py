#!/usr/bin/env python3
"""
Convert RentCast HV JSON responses to a single GeoJSON FeatureCollection.
Reads from data/rentcast_hv/*.json, writes to data/rentcast_hv/hv_listings_raw.geojson.
"""

import glob
import json
from pathlib import Path

INPUT_DIR = Path(__file__).parent.parent / "data" / "rentcast_hv"
OUTPUT = INPUT_DIR / "hv_listings_raw.geojson"

features = []
skipped_no_coords = 0

for path in sorted(glob.glob(str(INPUT_DIR / "rentcast_*.json"))):
    with open(path) as f:
        data = json.load(f)

    if not isinstance(data, list):
        continue

    for item in data:
        lat = item.get("latitude")
        lon = item.get("longitude")
        if lat is None or lon is None:
            skipped_no_coords += 1
            continue

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "id": item.get("id"),
                "address": item.get("formattedAddress") or item.get("addressLine1"),
                "city": item.get("city"),
                "state": item.get("state"),
                "zip": item.get("zipCode"),
                "county": item.get("county"),
                "price": item.get("price"),
                "beds": item.get("bedrooms"),
                "baths": item.get("bathrooms"),
                "propertyType": item.get("propertyType"),
                "squareFootage": item.get("squareFootage"),
                "yearBuilt": item.get("yearBuilt"),
                "url": item.get("listingUrl"),
                "listedDate": item.get("listedDate"),
                "daysOnMarket": item.get("daysOnMarket"),
                "status": item.get("status"),
            },
        })

geojson = {"type": "FeatureCollection", "features": features}
OUTPUT.write_text(json.dumps(geojson))

print(f"Saved {len(features)} listings to {OUTPUT}")
print(f"Skipped {skipped_no_coords} listings with missing coordinates")
