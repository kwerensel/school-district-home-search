"""Reversible Phase 11 research helpers; no imagery download or live writes.

Inputs are frozen listing points and the cached Phase 8 EPSG:4326 OSM roads.
All distance work uses EPSG:5070; emitted point coordinates remain EPSG:4326.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from datetime import datetime, timezone
import math
import os
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import geopandas as gpd
import numpy as np
from shapely.geometry import Point

PROJECTED_CRS = "EPSG:5070"
MAPILLARY_IMAGES_URL = "https://graph.mapillary.com/images"


@dataclass(frozen=True)
class RoadSample:
    listing_id: int
    sample_id: str
    longitude: float
    latitude: float
    distance_m: float


def sample_listing_roads(
    listings: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    *,
    spacing_m: float = 25,
    radius_m: float = 150,
    max_points: int = 5,
) -> list[RoadSample]:
    """Nearest 3–5 available regular road samples; never invent sparse samples.

    Return fewer than three when coverage is sparse. Callers must preserve this
    deficiency in evidence, rather than extending the search radius. Reversed
    lines and duplicate OSM edges yield the same candidate set.
    """
    if not 3 <= max_points <= 5 or not 0 < radius_m <= 150 or spacing_m <= 0:
        raise ValueError("Require 3–5 samples, a radius at most 150 m, and positive spacing")
    for frame in (listings, roads):
        if frame.crs is None or frame.crs.to_epsg() != 4326:
            raise ValueError("Research inputs must explicitly use EPSG:4326")
    if "id" not in listings or listings["id"].duplicated().any():
        raise ValueError("Frozen listings require unique id values")
    if not listings.geometry.geom_type.eq("Point").all():
        raise ValueError("Frozen listings must contain points")
    projected_roads = roads.to_crs(PROJECTED_CRS)
    coordinates: set[tuple[float, float]] = set()
    for geom in projected_roads.geometry:
        if geom is None or geom.is_empty:
            continue
        parts = list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom]
        for line in parts:
            if line.geom_type != "LineString":
                raise ValueError("Road cache must contain line geometries")
            # Canonical orientation makes sample positions independent of OSM direction.
            line = line.normalize()
            count = max(1, math.ceil(line.length / spacing_m))
            for index in range(count + 1):
                point = line.interpolate(min(index * spacing_m, line.length))
                coordinates.add((round(point.x, 3), round(point.y, 3)))
    if not coordinates:
        return []
    candidates = gpd.GeoSeries([Point(xy) for xy in sorted(coordinates)], crs=PROJECTED_CRS)
    wgs84 = candidates.to_crs(4326)
    output: list[RoadSample] = []
    for row in listings.to_crs(PROJECTED_CRS).sort_values("id").itertuples():
        indices = candidates.sindex.query(row.geometry.buffer(radius_m))
        eligible = sorted(
            ((float(row.geometry.distance(candidates.iloc[i])), int(i)) for i in indices),
            key=lambda pair: (pair[0], candidates.iloc[pair[1]].x, candidates.iloc[pair[1]].y),
        )
        for distance, index in [pair for pair in eligible if pair[0] <= radius_m][:max_points]:
            point = wgs84.iloc[index]
            identifier = sha256(candidates.iloc[index].wkb).hexdigest()[:16]
            output.append(RoadSample(int(row.id), identifier, point.x, point.y, distance))
    return output


def frozen_listings(conn: Any, region_group: str) -> gpd.GeoDataFrame:
    """Read-only production-baseline loader; never reads local three-row sample."""
    expected = {"pa-mainline": 251, "hudson-valley": 4254}
    if region_group not in expected:
        raise ValueError("Research is restricted to the two frozen project regions")
    frame = gpd.read_postgis(
        "SELECT id, geom AS geometry FROM listings WHERE region_slug = %s ORDER BY id",
        conn, params=(region_group,), geom_col="geometry",
    )
    if len(frame) != expected[region_group]:
        raise ValueError("Frozen listing count differs; research sampling refused")
    return frame


def image_coverage(
    samples: Iterable[RoadSample],
    images: Iterable[Mapping[str, Any]],
    *,
    listing_ids: Iterable[int],
    max_image_distance_m: float = 50,
    minimum_images: int = 3,
) -> list[dict[str, Any]]:
    """Unique image counts near sampled roads, not usable segmentation counts.

    Input image records have id, longitude, latitude (EPSG:4326). No thumbnail
    URLs, access tokens, or image bytes are accepted by this pure reducer.
    """
    if not 0 < max_image_distance_m <= 150 or minimum_images < 1:
        raise ValueError("Invalid image coverage thresholds")
    sample_list = list(samples)
    ids = sorted(set(int(value) for value in listing_ids))
    found: dict[int, set[str]] = {value: set() for value in ids}
    if sample_list:
        points = gpd.GeoSeries(
            [Point(s.longitude, s.latitude) for s in sample_list], crs=4326,
        ).to_crs(PROJECTED_CRS)
        image_list = list(images)
        if image_list:
            image_points = gpd.GeoSeries(
                [Point(float(i["longitude"]), float(i["latitude"])) for i in image_list],
                crs=4326,
            ).to_crs(PROJECTED_CRS)
            for sample, point in zip(sample_list, points, strict=True):
                if sample.listing_id not in found:
                    raise ValueError("Sample listing is outside the frozen sample contract")
                for index in image_points.sindex.query(point.buffer(max_image_distance_m)):
                    if point.distance(image_points.iloc[index]) <= max_image_distance_m:
                        found[sample.listing_id].add(str(image_list[index]["id"]))
    return [
        {"listing_id": value, "image_ids": sorted(found[value]),
         "candidate_image_count": len(found[value]),
         "coverage_eligible": len(found[value]) >= minimum_images}
        for value in ids
    ]


def aggregate_segmented_images(
    image_fractions: Mapping[str, float | None], *, minimum_images: int = 3,
) -> dict[str, Any]:
    """Aggregate distinct successfully segmented images; thin coverage stays null."""
    if minimum_images < 1:
        raise ValueError("minimum_images must be positive")
    values = [float(v) for v in image_fractions.values() if v is not None]
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError("Vegetation fractions must be finite and in [0, 1]")
    eligible = len(values) >= minimum_images
    return {
        "gvi_streetlevel": float(np.mean(values)) if eligible else None,
        "gvi_streetlevel_n_images": len(values),
        "display_source": "streetlevel" if eligible else "estimated from satellite",
    }


def paired_correlation(
    satellite: Mapping[int, float | None],
    streetlevel: Mapping[int, float | None],
    *, minimum_pairs: int = 3,
) -> dict[str, Any]:
    if minimum_pairs < 3:
        raise ValueError("At least three pairs are required")
    pairs = [
        (float(satellite[key]), float(streetlevel[key]))
        for key in sorted(satellite.keys() & streetlevel.keys())
        if satellite[key] is not None and streetlevel[key] is not None
        and math.isfinite(float(satellite[key])) and math.isfinite(float(streetlevel[key]))
    ]
    reason = None
    coefficient = None
    if len(pairs) < minimum_pairs:
        reason = "insufficient_pairs"
    else:
        values = np.array(pairs)
        if np.ptp(values[:, 0]) == 0 or np.ptp(values[:, 1]) == 0:
            reason = "constant_values"
        else:
            coefficient = float(np.corrcoef(values.T)[0, 1])
    return {"paired_count": len(pairs), "pearson_r": coefficient,
            "status": "computed" if coefficient is not None else "not_computable", "reason": reason}


def mapillary_coverage(
    bbox: tuple[float, float, float, float],
    *, cache_dir: Path, max_pages: int = 2, page_size: int = 100,
    requester: Callable[[Request], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Bounded metadata-only Graph query, cached without credentials.

    Pagination is deliberately capped and marks truncation. A capped response
    is a lower bound, never an assertion that all nearby imagery was found.
    """
    west, south, east, north = bbox
    if not all(math.isfinite(v) for v in bbox) or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("Invalid EPSG:4326 bounding box")
    if not 1 <= max_pages <= 10 or not 1 <= page_size <= 1000:
        raise ValueError("Coverage requests must be bounded")
    contract = {"bbox": list(bbox), "max_pages": max_pages, "limit": page_size,
                "fields": "id,computed_geometry,captured_at,sequence", "version": 2}
    key = sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()
    path = cache_dir / f"coverage_{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    token = os.environ.get("MAPILLARY_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("MAPILLARY_ACCESS_TOKEN is required for metadata coverage")
    fetch = requester or _request_metadata
    after = None
    images: dict[str, dict[str, Any]] = {}
    truncated = False
    for _ in range(max_pages):
        params = {"bbox": ",".join(str(v) for v in bbox), "fields": contract["fields"], "limit": page_size}
        if after:
            params["after"] = after
        request = Request(f"{MAPILLARY_IMAGES_URL}?{urlencode(params)}",
                          headers={"Authorization": f"OAuth {token}"})
        try:
            body = fetch(request)
        except Exception:
            # Provider exceptions can contain credential-bearing URLs/headers.
            raise RuntimeError("Mapillary metadata request failed; no imagery was fetched") from None
        for record in body.get("data", []):
            geometry = record.get("computed_geometry") or {}
            coords = geometry.get("coordinates", [])
            if geometry.get("type") != "Point" or len(coords) != 2:
                continue
            lon, lat = map(float, coords)
            if not (math.isfinite(lon) and math.isfinite(lat) and west <= lon <= east and south <= lat <= north):
                continue
            identifier = str(record["id"])
            images[identifier] = {"id": identifier, "longitude": lon, "latitude": lat,
                                  "captured_at": record.get("captured_at"), "sequence": record.get("sequence")}
        paging = body.get("paging", {})
        after = (paging.get("cursors") or {}).get("after") if paging.get("next") else None
        truncated = bool(paging.get("next")) or len(body.get("data", [])) >= page_size
        if not after:
            break
    result = {"request": contract, "images": [images[k] for k in sorted(images)],
              "truncated": truncated, "imagery_downloaded": False,
              "retrieved_at": datetime.now(timezone.utc).isoformat()}
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2))
    return result


def _request_metadata(request: Request) -> Mapping[str, Any]:
    with urlopen(request, timeout=20) as response:
        return json.load(response)
