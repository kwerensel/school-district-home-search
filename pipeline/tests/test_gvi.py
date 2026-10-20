import numpy as np
import pytest
from affine import Affine
from rasterio.io import MemoryFile
from shapely.geometry import box

from gt.layers.gvi import COLLECTION, select_scenes, scene_ndvi, summer_median, dilate_invalid, _zonal, _band


def item(name, cloud=10, day="2025-06-01", tile="18TWL"):
    return {"id": name, "collection": COLLECTION, "properties": {"datetime": day + "T10:00:00Z", "s2:mgrs_tile": tile, "eo:cloud_cover": cloud}, "assets": {k: {} for k in ("red", "nir", "scl", "cloud")}}


def test_selection_stable_cloud_limit_and_unique_days():
    scenes = [item("b", 10), item("a", 5), item("bad", 21), item("c", 8, "2025-06-03")]
    assert [s["id"] for s in select_scenes(scenes)] == ["a", "c"]
    assert select_scenes(scenes) == select_scenes(list(reversed(scenes)))


def test_missing_calibration_fails_closed():
    with pytest.raises(RuntimeError, match="calibration"):
        _band(item("x"), "red")


def test_reflectance_offset_and_cloud_mask_dilation():
    red = np.full((15, 15), 2000)
    nir = np.full((15, 15), 4000)
    scl = np.full((15, 15), 4)
    cloud = np.zeros((15, 15))
    band = {"scale": 0.0001, "offset": -0.1}
    cloud[7, 7] = 51
    data = scene_ndvi(red, nir, scl, cloud, band, band)
    assert data[3, 3] == pytest.approx(0.5)  # raw DN would wrongly give 1/3
    assert np.isnan(data[5:10, 5:10]).all()
    assert data[4, 7] == pytest.approx(0.5)
    assert np.isnan(data[:2]).all()


def test_scl_rejects_shadow_dark_snow_but_keeps_water():
    band = {"scale": 0.0001, "offset": -0.1}
    for classification in range(12):
        shape = (7, 7)
        ndvi = scene_ndvi(np.full(shape, 2000), np.full(shape, 4000), np.full(shape, classification), np.zeros(shape), band, band)
        assert bool(np.isfinite(ndvi[3, 3])) == (classification in (4, 5, 6, 7))


def test_three_observation_floor_and_median():
    a, b, c = [np.array([[v, np.nan]], dtype="float32") for v in (0.2, 0.4, 0.9)]
    median, count = summer_median([a, b, c])
    assert median[0, 0] == pytest.approx(0.4)
    assert count.tolist() == [[3, 0]]
    assert np.isnan(median[0, 1])
    assert np.isnan(summer_median([a, b])[0]).all()


def test_zonal_keeps_negative_ndvi_and_missing_pixels():
    with MemoryFile() as memory:
        with memory.open(driver="GTiff", width=4, height=4, count=1, dtype="float32", crs="EPSG:32618", transform=Affine(10, 0, 0, 0, -10, 40), nodata=-9999) as dataset:
            data = np.full((4, 4), -0.5, dtype="float32")
            data[0, 0] = -9999
            dataset.write(data, 1)
            assert _zonal(dataset, box(0, 0, 40, 40)) == pytest.approx(-0.5)
            assert _zonal(dataset, box(100, 100, 110, 110)) is None


def test_clear_zero_cloud_probability_survives_source_nodata_metadata():
    from rasterio.vrt import WarpedVRT
    with MemoryFile() as memory:
        with memory.open(driver="GTiff", width=4, height=4, count=1, dtype="uint8", crs="EPSG:32618", transform=Affine(10, 0, 0, 0, -10, 40), nodata=0) as dataset:
            dataset.write(np.zeros((4, 4), dtype="uint8"), 1)
            with WarpedVRT(dataset, src_nodata=255, nodata=255) as warped:
                assert (warped.read(1) == 0).all()


def test_missing_buffer_diagnostics_separate_geometric_source_gap_from_cloud_gap():
    import geopandas as gpd
    from shapely.geometry import Point, LineString
    from gt.layers.gvi import missing_buffer_diagnostics
    listings = gpd.GeoDataFrame({'id': [1], 'geom': [Point(0, 0)]}, geometry='geom', crs=32618)
    missing = [{'listing_id': 1, 'grain': 'buffer_100m'}]
    distant = gpd.GeoDataFrame(geometry=[LineString([(200, -200), (200, 200)])], crs=32618)
    nearby = gpd.GeoDataFrame(geometry=[LineString([(20, -200), (20, 200)])], crs=32618)
    with MemoryFile() as memory:
        with memory.open(driver='GTiff', width=40, height=40, count=2, dtype='float32', crs=32618, transform=Affine(10, 0, -200, 0, -10, 200), nodata=-9999) as dataset:
            dataset.write(np.full((40, 40), -9999, dtype='float32'), 1)
            dataset.write(np.zeros((40, 40), dtype='float32'), 2)
            gap = missing_buffer_diagnostics(dataset, listings, distant, missing)[0]
            assert gap['source_gap_category'] == 'no_road_corridor'
            assert gap['nearest_cached_drive_road_m'] == pytest.approx(200)
            assert gap['corridor_pixel_centers_in_buffer'] == 0
            dataset.write(np.full((40, 40), 2, dtype='float32'), 2)
            gap = missing_buffer_diagnostics(dataset, listings, nearby, missing)[0]
            assert gap['source_gap_category'] == 'insufficient_valid_observations'
            assert gap['corridor_buffer_geometric_intersection'] is True
            assert gap['corridor_pixel_centers_in_buffer'] > 0
            dataset.write(np.full((40, 40), 3, dtype='float32'), 2)
            assert missing_buffer_diagnostics(dataset, listings, nearby, missing)[0]['source_gap_category'] == 'reducer_inconsistency'


@pytest.mark.parametrize("listing_count,page_size", [(1,6),(3,2)])
def test_missing500m_qa_preserves_crs_grain_and_paginated_evidence(tmp_path, monkeypatch, listing_count, page_size):
    from contextlib import nullcontext
    import json
    import geopandas as gpd
    import rasterio
    from shapely.geometry import Point, LineString
    from gt import gvi_qa
    cache = tmp_path / 'cache'
    cache.mkdir()
    reports = tmp_path / 'data/reports'
    (reports / 'qa').mkdir(parents=True)
    crs = 'EPSG:32617'
    x, y = 500000, 4500000
    listings = gpd.GeoDataFrame({'id': list(range(1,listing_count+1)), 'address': ['Test']*listing_count, 'geom': [Point(x,y)]*listing_count}, geometry='geom', crs=crs).to_crs(4326)
    roads = gpd.GeoDataFrame(geometry=[LineString([(x+700,y-600),(x+700,y+600)])], crs=crs).to_crs(4326)
    roads.to_file(cache / 'osm-roads.geojson', driver='GeoJSON')
    path = cache / 'street-ndvi.tif'
    with rasterio.open(path, 'w', driver='GTiff', width=160, height=160, count=2, dtype='float32', crs=crs, transform=Affine(10,0,x-800,0,-10,y+800), nodata=-9999) as source:
        source.write(np.full((160,160), -9999, dtype='float32'), 1)
        source.write(np.zeros((160,160), dtype='float32'), 2)
    (reports / 'layer_gvi_ndvi_street_test_latest.json').write_text(json.dumps({'checks': {'raster_path': str(path), 'missing_listing_buffers': [{'listing_id':i,'grain':'buffer_500m'} for i in range(1,listing_count+1)]}}))
    monkeypatch.setattr(gvi_qa, '_qa_setup', lambda region: tmp_path)
    monkeypatch.setattr(gvi_qa.psycopg, 'connect', lambda *args, **kwargs: nullcontext(None))
    monkeypatch.setattr(gvi_qa.gpd, 'read_postgis', lambda *args, **kwargs: listings)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://unused-test')
    image = gvi_qa.render_gvi_missing_qa('test',page_size=page_size)
    evidence = json.loads(image.with_suffix('.json').read_text())
    assert image.exists()
    assert evidence['source_crs'] == crs
    assert len(evidence['pages']) == (listing_count+page_size-1)//page_size
    assert all(__import__('pathlib').Path(page).exists() for page in evidence['pages'])
    assert [row['listing_id'] for row in evidence['results']] == list(range(1,listing_count+1))
    assert evidence['results'][0]['buffer_radius_m'] == 500
    assert evidence['results'][0]['grain'] == 'buffer_500m'
    assert evidence['results'][0]['nearest_cached_drive_road_m'] == pytest.approx(700)
    assert evidence['results'][0]['source_gap_category'] == 'no_road_corridor'


def source_gap_checks():
    return {
        'listings_expected': 2, 'listing_buffer_100m_computed': 1,
        'listing_buffer_500m_computed': 2,
        'missing_listing_buffers': [{'listing_id': 1, 'grain': 'buffer_100m'}],
        'missing_buffer_diagnostics': [{
            'listing_id': 1, 'grain': 'buffer_100m',
            'source_gap_category': 'no_road_corridor',
            'nearest_cached_drive_road_m': 160,
            'corridor_buffer_geometric_intersection': False,
            'corridor_pixel_centers_in_buffer': 0,
            'pixels_with_any_observations': 0,
            'pixels_with_minimum_observations': 0,
            'maximum_valid_observation_days': 0,
            'minimum_unique_acquisition_days': 3,
        }],
    }


def test_unknown_policy_requires_complete_accounting_without_imputation():
    from gt.layers.gvi import listing_source_gap_policy
    checks = source_gap_checks()
    result = listing_source_gap_policy(checks)
    assert result['passed']
    assert result['accounting']['buffer_100m'] == {
        'computed': 1, 'explicit_unknown': 1, 'expected': 2, 'complete': True}
    assert checks['listing_buffer_100m_computed'] == 1
    assert result['accepted_unknowns'] == [
        {'listing_id': 1, 'grain': 'buffer_100m', 'reason': 'no_road_corridor'}]


@pytest.mark.parametrize('field,value', [
    ('source_gap_category', 'insufficient_valid_observations'),
    ('source_gap_category', 'road_corridor_without_pixel_centers'),
    ('source_gap_category', 'outside_composite_bounds'),
    ('source_gap_category', 'reducer_inconsistency'),
    ('corridor_buffer_geometric_intersection', True),
    ('nearest_cached_drive_road_m', 149),
    ('nearest_cached_drive_road_m', float('nan')),
    ('pixels_with_any_observations', 1),
    ('pixels_with_minimum_observations', 1),
    ('corridor_pixel_centers_in_buffer', 1),
    ('maximum_valid_observation_days', 1),
    ('minimum_unique_acquisition_days', 2),
    ('listing_id', 99),
    ('grain', 'buffer_500m'),
])
def test_unknown_policy_rejects_unproven_or_inconsistent_source_gaps(field, value):
    from gt.layers.gvi import listing_source_gap_policy
    checks = source_gap_checks()
    checks['missing_buffer_diagnostics'][0][field] = value
    assert not listing_source_gap_policy(checks)['passed']


@pytest.mark.parametrize('failure', ['missing_diagnostic', 'duplicate_diagnostic', 'duplicate_missing', 'missing_computed'])
def test_unknown_policy_fails_closed_on_incomplete_or_duplicate_evidence(failure):
    from gt.layers.gvi import listing_source_gap_policy
    checks = source_gap_checks()
    if failure == 'missing_diagnostic':
        checks['missing_buffer_diagnostics'] = []
    elif failure == 'duplicate_diagnostic':
        checks['missing_buffer_diagnostics'] *= 2
    elif failure == 'duplicate_missing':
        checks['missing_listing_buffers'] *= 2
    else:
        checks['listing_buffer_500m_computed'] -= 1
    assert not listing_source_gap_policy(checks)['passed']


def test_geofabrik_cache_requires_complete_coverage_proof(tmp_path):
    import json
    import geopandas as gpd
    from shapely.geometry import LineString
    from gt.layers.gvi import _roads
    polygon=box(-74.1,40.9,-73.9,41.1)
    gpd.GeoDataFrame(geometry=[LineString([(-74,41),(-74,41.01)])],crs=4326).to_file(tmp_path/'osm-roads.geojson',driver='GeoJSON')
    evidence={'source_type':'geofabrik_pbf','network_type':'drive','geometry_preserved':True,
              'complete':True,'served_footprint_covered':True,'full_footprint_covered':False,
              'excluded_tract_source_gaps':['coastal'],'bbox':list(polygon.bounds)}
    path=tmp_path/'osm-request.json'
    path.write_text(json.dumps(evidence))
    assert len(_roads(tmp_path,polygon))==1
    with pytest.raises(RuntimeError,match='envelope differs'):
        _roads(tmp_path,box(-75,40,-73,42))
    evidence['complete']=False
    path.write_text(json.dumps(evidence))
    with pytest.raises(RuntimeError,match='coverage proof is incomplete'):
        _roads(tmp_path,polygon)
    assert (tmp_path/'osm-roads.geojson').exists()


def test_missing_buffer_qa_handles_complete_coverage_without_opening_sources(tmp_path,monkeypatch):
    import json
    from gt import gvi_qa
    reports=tmp_path/'data/reports'
    (reports/'qa').mkdir(parents=True)
    (reports/'layer_gvi_ndvi_street_test_latest.json').write_text(json.dumps({'checks':{'missing_listing_buffers':[]}}))
    monkeypatch.setattr(gvi_qa,'_qa_setup',lambda region:tmp_path)
    path=gvi_qa.render_gvi_missing_qa('test')
    assert json.loads(path.read_text())['status']=='no_missing_listing_buffers'


def test_concurrent_composite_is_identical_to_serial_with_day_overlap(tmp_path):
    import geopandas as gpd
    import rasterio
    from shapely.geometry import Point,LineString
    from gt.layers.gvi import _composite
    x,y=500000,4500000
    tracts=gpd.GeoDataFrame({'slug':['tract']},geometry=[box(x-2700,y-100,x+2700,y+100)],crs=32618).to_crs(4326)
    listings=gpd.GeoDataFrame({'id':[1]},geometry=[Point(x,y)],crs=32618).to_crs(4326)
    roads=gpd.GeoDataFrame(geometry=[LineString([(x-3000,y),(x+3000,y)])],crs=32618).to_crs(4326)
    scenes=[]
    for i,(day,nir) in enumerate([('2025-06-01',4000),('2025-06-01',6000),('2025-06-02',5000),('2025-06-03',9000)]):
        scene=item(str(i),day=day,tile='18TWM' if i==1 else '18TWL')
        for key,value in [('red',2000),('nir',nir),('scl',4),('cloud',0)]:
            path=tmp_path/f'{i}-{key}.tif'
            data=np.full((160,700),value,dtype='uint16')
            if key=='scl': data[76:81,60:65]=9
            with rasterio.open(path,'w',driver='GTiff',width=700,height=160,count=1,dtype='uint16',crs=32618,transform=Affine(10,0,x-3500,0,-10,y+800),nodata=0) as out:
                out.write(data,1)
            scene['assets'][key]={'href':str(path),'raster:bands':[{'scale':.0001,'offset':-.1}]}
        scenes.append(scene)
    outputs=[]
    stats=[]
    for workers in (1,4):
        cache=tmp_path/f'workers-{workers}';cache.mkdir()
        roads.to_file(cache/'osm-roads.geojson',driver='GeoJSON')
        path,summary=_composite(cache,scenes,tracts,listings,roads,workers=workers)
        with rasterio.open(path) as source:
            outputs.append(source.read())
            assert source.crs.to_epsg()==32618
            assert np.max(outputs[-1][1])==3  # Duplicate same-day scene is not a fourth day.
            finite=outputs[-1][0][outputs[-1][0]!=-9999]
            assert len(finite)>0
            assert np.median(finite)==pytest.approx(.6)
        stats.append(summary)
    np.testing.assert_array_equal(outputs[0],outputs[1])
    assert stats[0]==stats[1]


@pytest.mark.parametrize('distance,accepted', [(149.9,True),(140.4,True),(130,False),(151,False)])
def test_native_pixel_gap_is_unknown_only_at_a_verified_grid_edge(distance,accepted):
    from gt.layers.gvi import listing_source_gap_policy
    checks=source_gap_checks()
    gap=checks['missing_buffer_diagnostics'][0]
    gap.update(source_gap_category='road_corridor_without_pixel_centers',
               corridor_buffer_geometric_intersection=True,
               nearest_cached_drive_road_m=distance)
    result=listing_source_gap_policy(checks)
    assert result['passed'] is accepted
    if accepted:
        assert result['accepted_unknowns'][0]['reason']=='road_corridor_without_pixel_centers'
    gap['pixels_with_any_observations']=1
    assert not listing_source_gap_policy(checks)['passed']


def test_tract_source_gaps_distinguish_missing_roads_from_reducer_failure():
    import geopandas as gpd
    from shapely.geometry import LineString
    from gt.layers.gvi import missing_tract_diagnostics
    tracts=gpd.GeoDataFrame({'slug':['tract'],'geom':[box(-50,-50,50,50)]},geometry='geom',crs=32618)
    roads=gpd.GeoDataFrame(geometry=[LineString([(180,-100),(180,100)])],crs=32618)
    with MemoryFile() as memory:
        with memory.open(driver='GTiff',width=40,height=40,count=2,dtype='float32',crs=32618,transform=Affine(10,0,-200,0,-10,200),nodata=-9999) as source:
            source.write(np.zeros((40,40),dtype='float32'),2)
            assert missing_tract_diagnostics(source,tracts,roads,set(),set())[0]['reason']=='no_road_corridor'
            source.write(np.full((40,40),3,dtype='float32'),2)
            assert missing_tract_diagnostics(source,tracts,roads,set(),set())[0]['reason']=='reducer_inconsistency'
            assert missing_tract_diagnostics(source,tracts,roads,set(),{'tract'})[0]['reason']=='outside_complete_road_extract_support'
            assert missing_tract_diagnostics(source,tracts,roads,{'tract'},set())==[]
