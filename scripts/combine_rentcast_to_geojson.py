import glob
import json
from pathlib import Path

INPUT_GLOB = str(Path.home() / "Downloads" / "rentcast_*.json")
OUTPUT = Path.home() / "Downloads" / "rentcast_listings.geojson"

features = []

for path in glob.glob(INPUT_GLOB):
    with open(path) as f:
        data = json.load(f)

    for item in data:
        lat = item.get("latitude")
        lon = item.get("longitude")
        if lat is None or lon is None:
            continue

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "address": item.get("formattedAddress") or item.get("addressLine1"),
                "city": item.get("city"),
                "state": item.get("state"),
                "zip": item.get("zipCode"),
                "price": item.get("price"),
                "beds": item.get("bedrooms"),
                "baths": item.get("bathrooms"),
                "propertyType": item.get("propertyType"),
                "squareFootage": item.get("squareFootage"),
                "url": item.get("listingUrl"),
            },
        })

geojson = {"type": "FeatureCollection", "features": features}
with open(OUTPUT, "w") as f:
    json.dump(geojson, f)

print(f"Saved {len(features)} listings to {OUTPUT}")
