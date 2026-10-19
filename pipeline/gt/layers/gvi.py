"""Seasonal Sentinel-2 street-corridor proxy; never photographic/address GVI."""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import math
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen
import warnings

import geopandas as gpd
import numpy as np
import psycopg
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from shapely.geometry import box

from gt.region_read_context import connect_layer_database
from gt.db.migrate import database_url, repo_root
from gt.layers.tree_canopy import (
    RegionMetric, ListingMetric, _read_tracts, _read_listings, _clear_staging,
    _stage_region_metrics, _stage_listing_metrics, _validation_checks, _array_masked_mean,
)
from gt.manifests import load_layer_manifest
from gt.reports import ValidationReport, write_report

STAC = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
SEASON = "2025-06-01T00:00:00Z/2025-08-31T23:59:59Z"
SCENES_PER_TILE = 12
MIN_OBSERVATIONS = 3
ALGORITHM = "summer2025-v1-12scenes-3days-scl4to7-cloud50-dilate20m"
NODATA = -9999.0


def select_scenes(items: list[dict]) -> list[dict]:
    """Stable clearest-scene selection, independent of API pagination order."""
    tiles: dict[str, list[dict]] = {}
    for item in items:
        p = item["properties"]
        if item.get("collection") != COLLECTION or not (0 <= p.get("eo:cloud_cover", 101) <= 20):
            continue
        if not all(k in item["assets"] for k in ("red", "nir", "scl", "cloud")):
            raise ValueError(f"Missing required optical/mask asset: {item['id']}")
        tile = p.get("s2:mgrs_tile") or p.get("grid:code")
        if not tile:
            raise ValueError(f"Missing MGRS tile: {item['id']}")
        tiles.setdefault(tile, []).append(item)
    selected = []
    for tile in sorted(tiles):
        ordered = sorted(tiles[tile], key=lambda i: (
            i["properties"]["eo:cloud_cover"], i["properties"]["datetime"], i["id"],
        ))
        # Reprocessed duplicates of the same day do not count as new observations.
        days: set[str] = set()
        for item in ordered:
            day = item["properties"]["datetime"][:10]
            if day not in days:
                selected.append(item)
                days.add(day)
            if len(days) == SCENES_PER_TILE:
                break
    return selected


def _fetch_scenes(cache: Path, bounds: tuple) -> tuple[list[dict], dict]:
    path = cache / "selected-scenes.json"
    contract = {"algorithm": ALGORITHM, "bbox": list(bounds), "datetime": SEASON, "collection": COLLECTION}
    if path.exists():
        saved = json.loads(path.read_text())
        if saved["contract"] != contract:
            raise RuntimeError("Cached scene selection differs from current source contract; use a new cache version")
        return saved["items"], saved
    url = STAC + "/search?" + urlencode({"collections": COLLECTION, "bbox": ",".join(map(str, bounds)), "datetime": SEASON, "limit": 100})
    items = []
    page = 0
    while url:
        with urlopen(url, timeout=120) as response:
            payload = json.load(response)
        (cache / f"stac-page-{page:03d}.json").write_text(json.dumps(payload))
        items.extend(payload["features"])
        url = next((link["href"] for link in payload.get("links", []) if link["rel"] == "next"), None)
        page += 1
    selected = select_scenes(items)
    if not selected:
        raise RuntimeError("No qualified Sentinel-2 scenes")
    saved = {"contract": contract, "retrieved_at": datetime.now(timezone.utc).isoformat(), "candidate_count": len(items), "items": selected}
    path.write_text(json.dumps(saved, indent=2))
    return selected, saved


def _roads(cache: Path, polygon) -> gpd.GeoDataFrame:
    path = cache / "osm-roads.geojson"
    request_path = cache / "osm-request.json"
    simplified_cache = path.exists() and request_path.exists() and json.loads(request_path.read_text()).get("simplify") is True
    if simplified_cache:
        roads = gpd.read_file(path)
    else:
        import osmnx as ox

        if path.exists():
            path.replace(cache / "osm-roads-unsimplified.geojson")
        ox.settings.cache_folder = str(cache / "osmnx-cache" / str(urlparse(ox.settings.overpass_url).hostname))
        graph = ox.graph_from_polygon(polygon, network_type="drive", simplify=True, retain_all=True, truncate_by_edge=True)
        roads = ox.graph_to_gdfs(graph, nodes=False).to_crs(4326)[["geometry"]]
        # A drive graph includes both directions; geometrically identical reverse
        # edges have identical corridors. Preserve intermediate coordinates.
        roads = roads.loc[~roads.geometry.normalize().to_wkb().duplicated()].copy()
        roads.to_file(path, driver="GeoJSON")
        (cache / "osm-request.json").write_text(json.dumps({"overpass_endpoint": ox.settings.overpass_url, "endpoint_reference": "https://wiki.openstreetmap.org/wiki/Overpass_API", "network_type": "drive", "simplify": True, "retain_all": True, "bbox": list(polygon.bounds), "retrieved_at": datetime.now(timezone.utc).isoformat(), "features": len(roads)}, indent=2))
    if roads.empty or roads.crs is None or roads.crs.to_epsg() != 4326:
        raise RuntimeError("Road cache missing roads or EPSG:4326")
    return roads


def dilate_invalid(mask: np.ndarray, radius: int = 2) -> np.ndarray:
    """Square 20 m mask expansion on a 10 m grid, with window halos."""
    padded = np.pad(mask, radius, constant_values=True)
    out = np.zeros_like(mask, dtype=bool)
    for dy in range(2 * radius + 1):
        for dx in range(2 * radius + 1):
            out |= padded[dy:dy + mask.shape[0], dx:dx + mask.shape[1]]
    return out


def scene_ndvi(red, nir, scl, cloud, red_band: dict, nir_band: dict) -> np.ndarray:
    r = np.asarray(red, dtype="float32") * red_band["scale"] + red_band["offset"]
    n = np.asarray(nir, dtype="float32") * nir_band["scale"] + nir_band["offset"]
    invalid = ~np.isin(scl, [4, 5, 6, 7]) | (cloud > 50)
    invalid = dilate_invalid(invalid)
    invalid |= (red == 0) | (nir == 0) | (r < 0) | (n < 0) | ((r + n) <= 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (n - r) / (n + r)
    ndvi[invalid | ~np.isfinite(ndvi) | (np.abs(ndvi) > 1)] = np.nan
    return ndvi


def summer_median(observations: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    stack = np.stack(observations)
    counts = np.isfinite(stack).sum(axis=0).astype("uint16")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        median = np.nanmedian(stack, axis=0)
    median[counts < MIN_OBSERVATIONS] = np.nan
    return median, counts


def _band(item: dict, key: str) -> dict:
    bands = item["assets"][key].get("raster:bands", [])
    if not bands or "scale" not in bands[0] or "offset" not in bands[0]:
        raise RuntimeError(f"Missing reflectance calibration: {item['id']} {key}")
    return bands[0]


def _composite(cache: Path, items: list[dict], tracts, listings, roads) -> tuple[Path, dict]:
    target_crs = tracts.estimate_utm_crs()
    if target_crs is None:
        raise RuntimeError("Cannot derive meter-based UTM CRS")
    bounds_frame = gpd.GeoSeries([box(*tracts.total_bounds), *listings.geometry], crs=4326).to_crs(target_crs)
    bounds = bounds_frame.buffer(600).total_bounds
    left, bottom = np.floor(bounds[:2] / 10) * 10
    right, top = np.ceil(bounds[2:] / 10) * 10
    width, height = int((right - left) / 10), int((top - bottom) / 10)
    transform = Affine(10, 0, left, 0, -10, top)
    path = cache / "street-ndvi.tif"
    stats_path = cache / "composite-stats.json"
    fingerprint = hashlib.sha256(json.dumps({"algorithm": ALGORITHM, "ids": [i["id"] for i in items], "roads_sha256": hashlib.sha256((cache / "osm-roads.geojson").read_bytes()).hexdigest(), "bounds": bounds.tolist(), "crs": str(target_crs)}, sort_keys=True).encode()).hexdigest()
    if path.exists() and stats_path.exists():
        stats = json.loads(stats_path.read_text())
        if stats.get("fingerprint") != fingerprint:
            raise RuntimeError("Cached composite source/geometry fingerprint mismatch")
        return path, stats
    corridors = roads.to_crs(target_crs).geometry.buffer(50)
    index = corridors.sindex
    profile = dict(driver="GTiff", width=width, height=height, count=2, dtype="float32", crs=target_crs, transform=transform, nodata=NODATA, tiled=True, compress="deflate", blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")
    stats = {"fingerprint": fingerprint, "algorithm": ALGORITHM, "target_crs": str(target_crs), "source_crs": [], "selected_scene_ids": [i["id"] for i in items], "minimum_unique_acquisition_days": MIN_OBSERVATIONS, "road_features": len(roads), "corridor_pixels": 0, "valid_corridor_pixels": 0, "valid_observation_histogram": {}, "mask_invalid_scene_pixels": 0, "scene_pixels": 0}
    temporary = path.with_suffix(".partial.tif")
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_HTTP_MAX_RETRY=4, GDAL_HTTP_RETRY_DELAY=2), ExitStack() as handles:
        started = time.monotonic()
        print(f"GVI opening {len(items)} scenes; grid {width} x {height}", flush=True)
        readers = []
        for item in items:
            assets = {}
            for key in ("red", "nir", "scl", "cloud"):
                source = handles.enter_context(rasterio.open(item["assets"][key]["href"]))
                if source.crs is None:
                    raise RuntimeError(f"Missing source CRS {item['id']}")
                stats["source_crs"].append(str(source.crs))
                # Cloud probability 0 is a valid clear value, despite STAC's nodata=0.
                assets[key] = handles.enter_context(WarpedVRT(source, crs=target_crs, transform=transform, width=width, height=height, resampling=Resampling.nearest, src_nodata=0 if key != "cloud" else 255, nodata=255 if key == "cloud" else 0))
            readers.append((item, assets))
        with rasterio.open(temporary, "w", **profile) as out:
            out.set_band_description(1, "Street corridor NDVI summer median")
            out.set_band_description(2, "Valid unique acquisition days")
            processed = 0
            for _, window in out.block_windows(1):
                wt = out.window_transform(window)
                wb = rasterio.windows.bounds(window, transform)
                candidates = index.query(box(*wb), predicate="intersects")
                mask = rasterize([(corridors.iloc[i], 1) for i in candidates], out_shape=(int(window.height), int(window.width)), transform=wt, fill=0, dtype="uint8").astype(bool) if len(candidates) else np.zeros((int(window.height), int(window.width)), dtype=bool)
                if not mask.any():
                    out.write(np.full(mask.shape, NODATA, dtype="float32"), 1, window=window)
                    out.write(np.zeros(mask.shape, dtype="float32"), 2, window=window)
                    continue
                # Halo avoids cloud seams between processing blocks.
                col, row = int(window.col_off), int(window.row_off)
                x0, y0 = max(0, col - 2), max(0, row - 2)
                expanded = Window(x0, y0, min(width, col + int(window.width) + 2) - x0, min(height, row + int(window.height) + 2) - y0)
                days: dict[str, np.ndarray] = {}
                for item, assets in readers:
                    data = {k: reader.read(1, window=expanded) for k, reader in assets.items()}
                    ndvi = scene_ndvi(**data, red_band=_band(item, "red"), nir_band=_band(item, "nir"))
                    ndvi = ndvi[row-y0:row-y0+int(window.height), col-x0:col-x0+int(window.width)]
                    stats["scene_pixels"] += int(mask.sum())
                    stats["mask_invalid_scene_pixels"] += int((mask & ~np.isfinite(ndvi)).sum())
                    day = item["properties"]["datetime"][:10]
                    if day in days:
                        # Tile overlap is resolved in stable tile order, never counted twice.
                        days[day] = np.where(np.isfinite(days[day]), days[day], ndvi)
                    else:
                        days[day] = ndvi
                processed += 1
                if processed % 25 == 0:
                    print(f"GVI corridor blocks {processed}; elapsed {time.monotonic() - started:.0f}s; valid pixels {stats['valid_corridor_pixels']}", flush=True)
                median, counts = summer_median(list(days.values()))
                valid = mask & np.isfinite(median)
                stats["corridor_pixels"] += int(mask.sum())
                stats["valid_corridor_pixels"] += int(valid.sum())
                values, frequencies = np.unique(counts[mask], return_counts=True)
                for value, count in zip(values, frequencies, strict=True):
                    key = str(int(value))
                    stats["valid_observation_histogram"][key] = stats["valid_observation_histogram"].get(key, 0) + int(count)
                out.write(np.where(valid, median, NODATA).astype("float32"), 1, window=window)
                out.write(np.where(mask, counts, 0).astype("float32"), 2, window=window)
    stats["selected_tile_counts"] = {str(tile): sum((i["properties"].get("s2:mgrs_tile") or i["properties"].get("grid:code")) == tile for i in items) for tile in sorted({i["properties"].get("s2:mgrs_tile") or i["properties"].get("grid:code") for i in items})}
    stats["source_crs"] = sorted(set(stats["source_crs"]))
    stats["corridor_valid_fraction"] = stats["valid_corridor_pixels"] / stats["corridor_pixels"] if stats["corridor_pixels"] else 0
    stats["scene_invalid_fraction_including_nodata"] = stats["mask_invalid_scene_pixels"] / stats["scene_pixels"] if stats["scene_pixels"] else 0
    temporary.replace(path)
    stats_path.write_text(json.dumps(stats, indent=2))
    return path, stats


def _zonal(source, geometry) -> float | None:
    from rasterio.windows import from_bounds
    window = from_bounds(*geometry.bounds, transform=source.transform).round_offsets().round_lengths()
    try:
        window = window.intersection(Window(0, 0, source.width, source.height))
    except rasterio.errors.WindowError:
        return None
    if window.width < 1 or window.height < 1:
        return None
    data = source.read(1, window=window, masked=True)
    # Shared reducer accepts 0..100 canopy; offset NDVI to preserve [-1,1].
    value = _array_masked_mean(data + 1, source.window_transform(window), geometry)
    return None if value is None else value - 1


def run_gvi(manifest_path: Path, region_slug: str, grain: str) -> tuple[ValidationReport, Path]:
    manifest = load_layer_manifest(manifest_path)
    if manifest.metric_key != "gvi_ndvi_street" or grain not in {"tract", "listing", "both"}:
        raise ValueError("gvi_ndvi_street supports tract, listing, or both")
    with connect_layer_database(region_slug) as conn:
        tracts, listings = _read_tracts(conn, region_slug), _read_listings(conn, region_slug)
    if tracts.empty or (listings.empty and grain in {"listing", "both"}) or tracts.crs.to_epsg() != 4326 or listings.crs.to_epsg() != 4326:
        raise RuntimeError("Require frozen listings and tracts in EPSG:4326")
    cache = repo_root() / "data" / "raw" / "gvi_ndvi_street" / region_slug / ALGORITHM
    cache.mkdir(parents=True, exist_ok=True)
    query = gpd.GeoSeries([box(*tracts.total_bounds), *listings.geometry], crs=4326).to_crs(tracts.estimate_utm_crs()).buffer(600).to_crs(4326)
    bounds = tuple(float(x) for x in query.total_bounds)
    items, selection = _fetch_scenes(cache, bounds)
    print(f"GVI {region_slug}: {len(items)} scenes selected from {selection['candidate_count']} candidates; fetching cached OSM roads", flush=True)
    roads = _roads(cache, box(*bounds))
    print(f"GVI {region_slug}: {len(roads)} road edges", flush=True)
    raster_path, source_stats = _composite(cache, items, tracts, listings, roads)
    region_metrics, listing_metrics = [], []
    with rasterio.open(raster_path) as source:
        if grain in {"tract", "both"}:
            for row in tracts.to_crs(source.crs).itertuples():
                value = _zonal(source, row.geom)
                if value is not None:
                    region_metrics.append(RegionMetric(str(row.slug), value))
        if grain in {"listing", "both"}:
            projected = listings.to_crs(source.crs)
            for row in projected.itertuples():
                for radius in (100, 500):
                    value = _zonal(source, row.geom.buffer(radius))
                    if value is not None:
                        listing_metrics.append(ListingMetric(int(row.id), f"buffer_{radius}m", value))
    with connect_layer_database(region_slug) as conn:
        with conn.cursor() as cur:
            _clear_staging(cur, region_slug, manifest.metric_key)
            _stage_region_metrics(cur, region_slug, manifest, region_metrics)
            _stage_listing_metrics(cur, region_slug, manifest, listing_metrics)
            checks = _validation_checks(cur, region_slug, manifest, grain)
        conn.commit()
    values = [m.value for m in [*region_metrics, *listing_metrics]]
    seen = {(m.listing_id, m.grain) for m in listing_metrics}
    checks |= {"nonfinite_values": sum(not math.isfinite(v) for v in values), "source": source_stats, "selection_manifest": str(cache / "selected-scenes.json"), "source_retrieved_at": selection["retrieved_at"], "raster_path": str(raster_path), "missing_listing_buffers": [{"listing_id": int(i), "grain": g} for i in listings.id for g in ("buffer_100m", "buffer_500m") if (int(i), g) not in seen] if grain in {"listing", "both"} else []}
    with rasterio.open(raster_path) as source:
        checks["missing_buffer_diagnostics"] = missing_buffer_diagnostics(source, listings, roads, checks["missing_listing_buffers"])
    checks["listing_source_gap_policy"] = listing_source_gap_policy(checks)
    promotable = bool(values) and checks["nonfinite_values"] == 0 and -1 <= checks["range_min"] <= checks["range_max"] <= 1 and (grain == "listing" or checks["tract_coverage"] >= manifest.coverage_threshold) and (grain == "tract" or checks["listing_source_gap_policy"]["passed"])
    report = ValidationReport(report_type="layer", target=f"{manifest.metric_key}:{region_slug}", status="staged", promotable=promotable, checks=checks)
    return report, write_report(report, f"layer_{manifest.metric_key}_{region_slug}_latest.json")


def listing_source_gap_policy(checks: dict) -> dict:
    """Account for every listing buffer, accepting only proven no-road Unknowns.

    User approved this source-gap policy on 2026-10-19. Cloud insufficiency,
    raster bounds and reducer inconsistencies still fail closed. Missing values
    stay absent metric rows, never zero or an interpolated estimate.
    """
    missing = checks["missing_listing_buffers"]
    diagnostics = checks["missing_buffer_diagnostics"]
    keys = [(row["listing_id"], row["grain"]) for row in missing]
    diagnostic_keys = [(row["listing_id"], row["grain"]) for row in diagnostics]
    matched = (len(set(keys)) == len(keys) == len(diagnostic_keys)
               and len(set(diagnostic_keys)) == len(diagnostic_keys)
               and set(keys) == set(diagnostic_keys))
    accepted = []
    for row in diagnostics:
        radius = {"buffer_100m": 100, "buffer_500m": 500}.get(row["grain"])
        distance = row.get("nearest_cached_drive_road_m")
        if (radius is not None and row.get("source_gap_category") == "no_road_corridor"
                and row.get("corridor_buffer_geometric_intersection") is False
                and isinstance(distance, (int, float)) and math.isfinite(distance)
                and distance > radius + 50
                and all(row.get(field) == 0 for field in (
                    "corridor_pixel_centers_in_buffer", "pixels_with_any_observations",
                    "pixels_with_minimum_observations", "maximum_valid_observation_days"))):
            accepted.append({"listing_id": row["listing_id"], "grain": row["grain"],
                             "reason": "no_road_corridor"})
    accounting = {}
    for grain in ("buffer_100m", "buffer_500m"):
        computed = checks[f"listing_{grain}_computed"]
        unknown = sum(row["grain"] == grain for row in accepted)
        accounting[grain] = {"computed": computed, "explicit_unknown": unknown,
                             "expected": checks["listings_expected"],
                             "complete": computed + unknown == checks["listings_expected"]}
    return {"policy": "verified_no_road_corridor_unknown_v1", "approved_on": "2026-10-19",
            "diagnostics_match_missing": matched, "accepted_unknowns": accepted,
            "accounting": accounting,
            "passed": matched and len(accepted) == len(missing)
                      and all(row["complete"] for row in accounting.values())}


def missing_buffer_diagnostics(source, listings, roads, missing: list[dict]) -> list[dict]:
    """Explain missing source support without imputing values."""
    from rasterio.features import geometry_mask
    from rasterio.windows import from_bounds
    if not source.crs or not source.crs.is_projected:
        raise ValueError("Missing-buffer diagnostics require the projected composite CRS")
    projected_roads = roads.to_crs(source.crs)
    projected_listings = listings.to_crs(source.crs).set_index("id")
    result = []
    for missing_buffer in missing:
        listing_id = int(missing_buffer["listing_id"])
        grain = missing_buffer["grain"]
        if grain not in {"buffer_100m", "buffer_500m"}:
            raise ValueError(f"Unsupported GVI listing grain: {grain}")
        radius = 100 if grain == "buffer_100m" else 500
        point = projected_listings.loc[listing_id, projected_listings.geometry.name]
        buffer = point.buffer(radius)
        nearest = projected_roads.sindex.nearest(point, return_all=False, return_distance=True)
        road = projected_roads.iloc[int(nearest[0][1][0])].geometry
        distance = float(nearest[1][0])
        window = from_bounds(*buffer.bounds, transform=source.transform).round_offsets().round_lengths()
        try:
            window = window.intersection(Window(0, 0, source.width, source.height))
        except rasterio.errors.WindowError:
            result.append(dict(missing_buffer, source_gap_category="outside_composite_bounds", nearest_cached_drive_road_m=distance))
            continue
        transform = source.window_transform(window)
        counts = source.read(2, window=window)
        inside = geometry_mask([buffer], out_shape=counts.shape, transform=transform, invert=True)
        local = projected_roads.iloc[projected_roads.sindex.query(buffer.buffer(50), predicate="intersects")]
        intersects = bool(local.geometry.buffer(50).intersects(buffer).any()) if len(local) else False
        corridor = rasterize([(geom.buffer(50), 1) for geom in local.geometry], out_shape=counts.shape, transform=transform, fill=0, dtype="uint8").astype(bool) if len(local) else np.zeros(counts.shape, dtype=bool)
        corridor_count = int((inside & corridor).sum())
        any_observations = int((inside & (counts > 0)).sum())
        sufficient = int((inside & (counts >= MIN_OBSERVATIONS)).sum())
        category = (
            "no_road_corridor" if not intersects else
            "road_corridor_without_pixel_centers" if not corridor_count else
            "insufficient_valid_observations" if not sufficient else
            "reducer_inconsistency"
        )
        result.append(dict(
            missing_buffer,
            source_gap_category=category,
            nearest_cached_drive_road_m=distance,
            corridor_buffer_geometric_intersection=intersects,
            corridor_pixel_centers_in_buffer=corridor_count,
            pixels_with_any_observations=any_observations,
            pixels_with_minimum_observations=sufficient,
            minimum_unique_acquisition_days=MIN_OBSERVATIONS,
            maximum_valid_observation_days=int(counts[inside].max()) if inside.any() else 0,
        ))
    return result
