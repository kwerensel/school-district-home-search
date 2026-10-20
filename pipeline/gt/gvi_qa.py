"""Reproducible local satellite GVI spatial QA; reads registered frozen listings.

Uses the normal DATABASE_URL configuration; never reads or logs env files.
No external imagery/road requests, imputation, promotion, or threshold changes.
"""
from pathlib import Path
import json
import os
import geopandas as gpd
import psycopg
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds, bounds as window_bounds
from gt.db.migrate import database_url, repo_root
from gt.green_qa import render_green_qa
from gt.layers.gvi import _zonal
from gt.manifests import load_region_manifest

def _qa_setup(region: str) -> Path:
    root = repo_root()
    load_region_manifest(root / 'pipeline/manifests/regions' / f'{region}.yaml')
    with psycopg.connect(database_url()) as conn:
        exists = conn.execute('SELECT EXISTS(SELECT 1 FROM regions WHERE region_group=%s)', (region,)).fetchone()[0]
    if not exists:
        raise ValueError('Local GVI QA requires a registered public region')
    os.environ.setdefault('MPLCONFIGDIR', str(root / 'data/reports/qa/.matplotlib-cache'))
    os.environ.setdefault('XDG_CACHE_HOME', str(root / 'data/reports/qa/.cache'))
    return root

def render_gvi_spotcheck(region: str) -> Path:
    """Render the nearby same-street candidate with native raster cells and 100m buffers."""
    root = _qa_setup(region)
    import matplotlib.pyplot as plt
    paired = render_green_qa(region, staged=True)
    print('PAIRED', paired, flush=True)
    metadata = json.loads(paired.with_suffix('.json').read_text())
    candidate = metadata['nearby_same_street_candidate']
    if not candidate:
        raise RuntimeError('No nearby same-street candidate: needs explicit spot-review')
    report = json.loads((root / f'data/reports/layer_gvi_ndvi_street_{region}_latest.json').read_text())
    raster_path = Path(report['checks']['raster_path'])
    with psycopg.connect(database_url()) as conn:
        listings = gpd.read_postgis('SELECT id,address,geom FROM listings WHERE id=ANY(%s) ORDER BY id', conn, params=([candidate['listing_a'], candidate['listing_b']],), geom_col='geom')
    with rasterio.open(raster_path) as source:
        points = listings.to_crs(source.crs)
        extent_geom = points.geometry.buffer(220).union_all().envelope
        window = from_bounds(*extent_geom.bounds, transform=source.transform).round_offsets().round_lengths().intersection(Window(0, 0, source.width, source.height))
        ndvi = source.read(1, window=window, masked=True)
        counts = source.read(2, window=window, masked=True)
        minx, miny, maxx, maxy = window_bounds(window, source.transform)
        roads = gpd.read_file(raster_path.parent / 'osm-roads.geojson', bbox=transform_bounds(source.crs, 4326, minx, miny, maxx, maxy)).to_crs(source.crs)
        checks = []
        for row in points.itertuples():
            value = _zonal(source, row.geom.buffer(100))
            expected = candidate['ndvi_a'] if row.id == candidate['listing_a'] else candidate['ndvi_b']
            if abs(value - expected) > 1e-07:
                raise RuntimeError('Staged metric differs from raster reduction')
            checks.append({'listing_id': row.id, 'address': row.address, 'buffer_100m_ndvi': value, 'staged_value': expected})
        fig, axes = plt.subplots(1, 2, figsize=(13, 7))
        for ax, data, title, cmap, vmin, vmax in [(axes[0], ndvi, 'Seasonal median satellite NDVI', 'YlGn', -0.1, 0.9), (axes[1], counts, 'Valid unique observation days', 'viridis', 0, float(counts.max()))]:
            image = ax.imshow(data, extent=(minx, maxx, miny, maxy), cmap=cmap, vmin=vmin, vmax=vmax, interpolation='nearest')
            fig.colorbar(image, ax=ax, shrink=0.65)
            if not roads.empty:
                roads.plot(ax=ax, color='#374151', linewidth=0.7, alpha=0.8)
            for row, color in zip(points.itertuples(), ['#2563eb', '#dc2626'], strict=True):
                gpd.GeoSeries([row.geom.buffer(100)], crs=points.crs).boundary.plot(ax=ax, color=color, linewidth=1.8)
                ax.scatter([row.geom.x], [row.geom.y], color=color, edgecolors='white', s=55, zorder=5)
                result = next((c for c in checks if c['listing_id'] == row.id))
                ax.annotate(f"{row.id}: {result['buffer_100m_ndvi']:.3f}", (row.geom.x, row.geom.y), xytext=(7, 8), textcoords='offset points', color=color, fontsize=9, weight='bold')
            ax.set_title(title)
            ax.set_xlim(minx, maxx)
            ax.set_ylim(miny, maxy)
            ax.set_aspect('equal')
            ax.set_xlabel('Projected easting (m)')
            ax.set_ylabel('Projected northing (m)')
        fig.suptitle(f'{region}: nearby same-street listing spot check\n100 m buffers; 50 m OSM road corridor; satellite estimate, not eye-level GVI')
        fig.tight_layout()
        path = root / f'data/reports/qa/gvi_same_street_{region}_staged.png'
        fig.savefig(path, dpi=180)
        plt.close(fig)
        evidence = {'region': region, 'staged': True, 'candidate': candidate, 'listing_checks': checks, 'actual_road_features_in_closeup': len(roads), 'ndvi_100m_difference': abs(candidate['ndvi_a'] - candidate['ndvi_b']), 'source_raster': str(raster_path), 'source_crs': str(source.crs), 'minimum_observation_days': 3, 'limitations': 'Seasonal satellite street-corridor context. Address text and nearby geometry identify candidate pair; image is not photographic or address-specific vegetation evidence.'}
        path.with_suffix('.json').write_text(json.dumps(evidence, indent=2))
        print('CLOSEUP', path, flush=True)
        print(json.dumps(evidence, indent=2), flush=True)
    return path

def render_gvi_missing_qa(region: str, *, page_size: int = 6) -> Path:
    """Render road/raster support for each missing 100m or 500m listing buffer."""
    if not 1 <= page_size <= 8:
        raise ValueError("Missing-buffer QA page size must be between 1 and 8")
    from gt.layers.gvi import missing_buffer_diagnostics
    root = _qa_setup(region)
    import matplotlib.pyplot as plt
    report = json.loads((root / f'data/reports/layer_gvi_ndvi_street_{region}_latest.json').read_text())
    missing = report['checks']['missing_listing_buffers']
    stem = root / f'data/reports/qa/gvi_missing_buffers_{region}_staged'
    if not missing:
        path = stem.with_suffix('.json')
        path.write_text(json.dumps({'region': region, 'results': [], 'status': 'no_missing_listing_buffers'}, indent=2))
        return path
    ids = sorted({int(value['listing_id']) for value in missing})
    raster_path = Path(report['checks']['raster_path'])
    with psycopg.connect(database_url()) as conn:
        listings = gpd.read_postgis('SELECT id,address,geom FROM listings WHERE id=ANY(%s) ORDER BY id', conn, params=(ids,), geom_col='geom')
    roads_4326 = gpd.read_file(raster_path.parent / 'osm-roads.geojson')
    with rasterio.open(raster_path) as source:
        roads = roads_4326.to_crs(source.crs)
        points = listings.to_crs(source.crs)
        rows = {int(row.id): row for row in points.itertuples()}
        results = missing_buffer_diagnostics(source, listings, roads_4326, missing)
        pages = []
        for page_start in range(0, len(missing), page_size):
            page_missing = missing[page_start:page_start + page_size]
            page_results = results[page_start:page_start + page_size]
            fig, axes = plt.subplots(len(page_missing), 2, figsize=(14, 6 * len(page_missing)), squeeze=False)
            for entry, pair, evidence in zip(page_missing, axes, page_results, strict=True):
                row = rows[int(entry['listing_id'])]
                grain = entry['grain']
                if grain not in {'buffer_100m', 'buffer_500m'}:
                    raise ValueError(f'Unsupported missing buffer grain: {grain}')
                radius = 100 if grain == 'buffer_100m' else 500
                distance = evidence['nearest_cached_drive_road_m']
                extent_geom = row.geom.buffer(max(radius + 150, distance + 80)).envelope
                window = from_bounds(*extent_geom.bounds, transform=source.transform).round_offsets().round_lengths().intersection(Window(0, 0, source.width, source.height))
                ndvi = source.read(1, window=window, masked=True)
                counts = source.read(2, window=window, masked=True)
                minx, miny, maxx, maxy = window_bounds(window, source.transform)
                local = roads.iloc[roads.sindex.query(extent_geom, predicate='intersects')]
                evidence.update(address=row.address, buffer_radius_m=radius, buffer_reduction=_zonal(source, row.geom.buffer(radius)))
                panels = [(pair[0], ndvi, 'Satellite NDVI', 'YlGn', -0.1, 0.9), (pair[1], counts, 'Valid observation days', 'viridis', 0, max(float(counts.max()), 3))]
                for ax, data, title, cmap, vmin, vmax in panels:
                    raster = ax.imshow(data, extent=(minx, maxx, miny, maxy), cmap=cmap, vmin=vmin, vmax=vmax, interpolation='nearest')
                    fig.colorbar(raster, ax=ax, shrink=0.6)
                    if not local.empty:
                        local.plot(ax=ax, color='#374151', linewidth=0.8)
                        local.geometry.buffer(50).boundary.plot(ax=ax, color='#6b7280', linewidth=0.5, alpha=0.7)
                    gpd.GeoSeries([row.geom.buffer(radius)], crs=source.crs).boundary.plot(ax=ax, color='#dc2626', linewidth=1.5)
                    ax.scatter([row.geom.x], [row.geom.y], c='#dc2626', s=60, edgecolor='white', zorder=5)
                    ax.set_xlim(minx, maxx)
                    ax.set_ylim(miny, maxy)
                    ax.set_aspect('equal')
                    ax.set_title(f'{row.id} · {title}\nnearest cached road {distance:.1f} m; red = {radius} m buffer')
                    ax.set_xlabel('Projected easting (m)')
                    ax.set_ylabel('Projected northing (m)')
            fig.suptitle(f'{region}: missing street-corridor coverage investigation')
            fig.tight_layout(rect=(0, 0, 1, 0.97))
            path = (stem if page_start == 0 else stem.with_name(stem.name + f'_page-{page_start // page_size + 1:03d}')).with_suffix('.png')
            fig.savefig(path, dpi=170)
            plt.close(fig)
            pages.append(str(path))
        stem.with_suffix('.json').write_text(json.dumps({'region': region, 'source_crs': str(source.crs), 'pages': pages, 'page_size': page_size, 'results': results, 'limitation': 'Cached OSM drive road context; no missing value is imputed. Native 10m raster centers diagnose source support; each panel uses its declared buffer radius.'}, indent=2))
    return Path(pages[0])
