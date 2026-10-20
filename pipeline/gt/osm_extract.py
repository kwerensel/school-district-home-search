"""Approved offline OSM road recovery using a checksum-pinned Geofabrik PBF."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import Polygon
from shapely.ops import unary_union

# Match the installed OSMnx drive filter, including its substring regex semantics.
DRIVE_EXCLUDED = (
    'abandoned|bridleway|bus_guideway|construction|corridor|cycleway|elevator|'
    'escalator|footway|no|path|pedestrian|planned|platform|proposed|raceway|razed|'
    'rest_area|service|services|steps|track'
)
SERVICE_EXCLUDED = 'alley|driveway|emergency_access|parking|parking_aisle|private'
DRIVE_FILTER_VERSION = 'osmnx-drive-v1-full-way-geometry'
OSM_CONFIG = '''[general]
closed_ways_are_polygons=
[lines]
osm_id=yes
osm_version=no
osm_timestamp=no
osm_uid=no
osm_user=no
osm_changeset=no
attributes=highway,area,access,motor_vehicle,motorcar,service
other_tags=no
'''


def is_drive_way(tags: dict) -> bool:
    """Replicate the approved drive tag rules without a live Overpass query."""
    return isinstance(tags.get('highway'), str) and bool(tags['highway']) and not any(
        re.search(pattern, tags.get(key) if isinstance(tags.get(key), str) else '')
        for key, pattern in (
            ('highway', DRIVE_EXCLUDED), ('area', 'yes'), ('access', 'private'),
            ('motor_vehicle', 'no'), ('motorcar', 'no'), ('service', SERVICE_EXCLUDED),
        )
    )


def read_poly(path: Path):
    """Read the Geofabrik .poly extent, including separate islands and holes."""
    lines = iter(path.read_text().splitlines()[1:])
    shells, holes = [], []
    for name in lines:
        name = name.strip()
        if name == 'END':
            break
        if not name:
            continue
        coordinates = []
        for line in lines:
            if line.strip() == 'END':
                break
            coordinates.append(tuple(map(float, line.split())))
        ring = Polygon(coordinates)
        if not ring.is_valid or ring.is_empty:
            raise ValueError('Invalid Geofabrik extract boundary')
        (holes if name.startswith('!') else shells).append(ring)
    boundary = unary_union(shells).difference(unary_union(holes))
    if boundary.is_empty or not boundary.is_valid:
        raise ValueError('Missing or invalid Geofabrik extract boundary')
    return boundary


def file_digest(path: Path, algorithm: str = 'sha256') -> str:
    digest = hashlib.new(algorithm)
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_geofabrik_roads(
    extract_path: Path, boundary_path: Path, checksum_path: Path,
    cache: Path, polygon, required_support,
    additional_extracts: list[tuple[Path, Path, Path]] | None = None,
    tract_supports: gpd.GeoDataFrame | None = None,
    listing_support=None,
) -> Path:
    """Filter complete OSM ways locally; never spatial-filter PBF nodes or clip.

    The SQL predicate runs on reconstructed way geometry. A driver-level bbox
    filter could discard nodes and truncate ways, so it is deliberately absent.
    The required analytical footprint must be covered by the extract boundary.
    """
    extracts = [(extract_path, boundary_path, checksum_path), *(additional_extracts or [])]
    boundary = unary_union([read_poly(item[1]) for item in extracts])
    excluded_tracts = []
    full_coverage = boundary.covers(required_support)
    if not full_coverage:
        if tract_supports is None or listing_support is None or not boundary.covers(listing_support):
            raise ValueError('Geofabrik extracts do not cover the entire analytical footprint')
        if tract_supports.crs is None or tract_supports.crs.to_epsg() != 4326:
            raise ValueError('Tract support geometries must be EPSG:4326')
        covered = tract_supports.geometry.covered_by(boundary)
        excluded_tracts = sorted(tract_supports.loc[~covered, 'slug'].tolist())
        # Existing 99% tract threshold still applies in the layer validator.
        # Do not calculate a partly supported coastal tract from partial roads.
        served_support = unary_union([listing_support, tract_supports.loc[covered].geometry.union_all()])
        if not boundary.covers(served_support):
            raise ValueError('Served geometry is outside the extract boundaries')
    sources = []
    for extract, extent, checksum in extracts:
        checksum_fields = checksum.read_text().split()
        if len(checksum_fields) != 2 or checksum_fields[1].lstrip('*') != extract.name:
            raise ValueError('Extract checksum filename mismatch')
        if file_digest(extract, 'md5') != checksum_fields[0]:
            raise ValueError('Geofabrik extract checksum mismatch')
        sources.append({
            'source_url': 'https://download.geofabrik.de/north-america/us/' + extract.name,
            'extract_sha256': file_digest(extract), 'extract_md5': checksum_fields[0],
            'boundary_sha256': file_digest(extent),
        })
    cache.mkdir(parents=True, exist_ok=True)
    config = cache / 'geofabrik-osmconf.ini'
    config.write_text(OSM_CONFIG)
    bounds = tuple(float(v) for v in polygon.bounds)
    if len(bounds) != 4 or not (-180 <= bounds[0] < bounds[2] <= 180 and -90 <= bounds[1] < bounds[3] <= 90):
        raise ValueError('Require valid EPSG:4326 extraction envelope')
    envelope = ','.join(repr(v) for v in bounds)
    sql = (
        'SELECT geometry,osm_id,highway,area,access,motor_vehicle,motorcar,service '
        'FROM lines WHERE highway IS NOT NULL '
        f'AND ST_Intersects(geometry, BuildMbr({envelope},4326))'
    )
    frames = []
    for (extract, _, _), provenance in zip(extracts, sources, strict=True):
        contract = {'extract_sha256': provenance['extract_sha256'], 'bounds': bounds,
                    'filter': DRIVE_FILTER_VERSION, 'config': OSM_CONFIG}
        key = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()[:16]
        intermediate = cache / f'geofabrik-roads-{key}.gpkg'
        if intermediate.exists():
            frame = gpd.read_file(intermediate)
        else:
            print(f'Reconstructing full OSM ways: {extract.name}', flush=True)
            frame = pyogrio.read_dataframe(extract, sql=sql, sql_dialect='SQLITE', CONFIG_FILE=str(config))
            if frame.crs is None or frame.crs.to_epsg() != 4326 or frame.empty:
                raise ValueError('Extract yielded no EPSG:4326 road candidates')
            provenance['candidate_ways'] = len(frame)
            frame = frame.loc[frame.apply(lambda row: is_drive_way(row.to_dict()), axis=1)].copy()
            if frame.empty or not frame.geometry.is_valid.all() or not frame.geometry.geom_type.eq('LineString').all():
                raise ValueError('Require valid full LineString road ways')
            temporary_part = intermediate.with_name(intermediate.stem + '.partial.gpkg')
            frame[['osm_id', 'geometry']].to_file(temporary_part, driver='GPKG', layer='roads')
            temporary_part.replace(intermediate)
        provenance['drive_ways'] = len(frame)
        frames.append(frame[['osm_id', 'geometry']])
        print(json.dumps({'extract': extract.name, 'drive_ways': len(frame)}), flush=True)
    roads = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=4326)
    shapes = roads.geometry.normalize().to_wkb()
    if shapes.groupby(roads.osm_id).nunique().gt(1).any():
        raise ValueError('Neighboring extracts disagree on full geometry for an OSM way')
    roads = roads.drop_duplicates('osm_id')
    roads = roads.loc[~roads.geometry.normalize().to_wkb().duplicated()].sort_values('osm_id')
    path = cache / 'osm-roads.geojson'
    if path.exists():
        raise FileExistsError('Do not overwrite an existing road cache')
    temporary = cache / 'osm-roads.partial.geojson'
    roads[['osm_id', 'geometry']].to_file(temporary, driver='GeoJSON')
    temporary.replace(path)
    evidence = {
        'source_type': 'geofabrik_pbf', 'extracts': sources,
        'provider_approved_on': '2026-10-19', 'license': 'ODbL-1.0',
        'attribution': 'OpenStreetMap contributors; extract by Geofabrik',
        'full_footprint_covered': bool(full_coverage),
        'served_footprint_covered': True,
        'excluded_tract_source_gaps': excluded_tracts,
        'network_type': 'drive', 'filter_version': DRIVE_FILTER_VERSION,
        'geometry_preserved': True, 'complete': True,
        'simplify': False, 'topology_note': 'Full OSM way vertices; no graph simplification or isolated-ring removal',
        'bbox': list(bounds), 'features': len(roads),
        'retrieved_at': datetime.now(timezone.utc).isoformat(),
    }
    (cache / 'osm-request.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps({'drive_ways': len(roads), 'path': str(path)}), flush=True)
    return path
