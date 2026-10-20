from pathlib import Path
import hashlib

import geopandas as gpd
import pytest
from shapely.geometry import box,LineString

from gt.osm_extract import is_drive_way,read_poly,prepare_geofabrik_roads,OSM_CONFIG


@pytest.mark.parametrize('highway', ['residential','tertiary','motorway','trunk_link','unclassified','living_street'])
def test_drive_filter_includes_public_motor_roads(highway):
    assert is_drive_way({'highway':highway})


@pytest.mark.parametrize('tags', [
    {}, {'highway':'footway'}, {'highway':'service'}, {'highway':'track'},
    {'highway':'residential','access':'private'},
    {'highway':'residential','area':'yes'},
    {'highway':'residential','motor_vehicle':'no'},
    {'highway':'residential','motorcar':'no'},
    {'highway':'residential','service':'driveway'},
    {'highway':'residential','service':'parking_aisle'},
    {'highway':'residential','service':'emergency_access'},
])
def test_drive_filter_excludes_non_drivable_or_private_ways(tags):
    assert not is_drive_way(tags)


def test_poly_preserves_islands_and_holes(tmp_path):
    p=tmp_path/'region.poly'
    p.write_text('region\n1\n0 0\n4 0\n4 4\n0 4\n0 0\nEND\n!1\n1 1\n2 1\n2 2\n1 2\n1 1\nEND\n2\n6 0\n7 0\n7 1\n6 1\n6 0\nEND\nEND\n')
    boundary=read_poly(p)
    assert boundary.area==16
    assert not boundary.covers(box(1.1,1.1,1.9,1.9))
    assert boundary.covers(box(6.1,.1,6.9,.9))


def test_local_osm_import_preserves_way_vertices_and_drive_access(tmp_path):
    # Entire way reconstructed despite extraction bounds containing only its
    # middle node. Closed residential loops also stay lines; area=yes is rejected.
    p=tmp_path/'fixture.osm'
    p.write_text('''<osm version="0.6">
      <node id="1" lat="41" lon="-74.1"/>
      <node id="2" lat="41.01" lon="-74"/>
      <node id="3" lat="41.02" lon="-73.9"/>
      <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="residential"/></way>
      <way id="11"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/><tag k="access" v="private"/></way>
      <way id="12"><nd ref="1"/><nd ref="2"/><tag k="highway" v="service"/></way>
      <way id="13"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="1"/><tag k="highway" v="residential"/><tag k="area" v="yes"/></way>
    </osm>''')
    boundary=tmp_path/'region.poly'
    boundary.write_text('region\n1\n-75 40\n-73 40\n-73 42\n-75 42\n-75 40\nEND\nEND\n')
    checksum=tmp_path/'fixture.md5'
    checksum.write_text(hashlib.md5(p.read_bytes()).hexdigest()+'  '+p.name)
    cache=tmp_path/'cache'
    path=prepare_geofabrik_roads(p,boundary,checksum,cache,box(-74.01,41,-73.99,41.02),box(-74.01,41,-73.99,41.02))
    roads=gpd.read_file(path)
    assert roads.osm_id.tolist()==['10']
    assert list(roads.geometry.iloc[0].coords)==[(-74.1,41),(-74,41.01),(-73.9,41.02)]
    assert roads.crs.to_epsg()==4326
    with pytest.raises(ValueError,match='entire analytical footprint'):
        prepare_geofabrik_roads(p,boundary,checksum,tmp_path/'bad',box(-74,41,-73.9,41.1),box(-76,41,-75.9,41.1))
    checksum.write_text('0'*32+'  '+p.name)
    with pytest.raises(ValueError,match='checksum mismatch'):
        prepare_geofabrik_roads(p,boundary,checksum,tmp_path/'bad',box(-74,41,-73.9,41.1),box(-74,41,-73.9,41.1))


def test_only_source_covered_tracts_are_served_and_listings_must_be_complete(tmp_path):
    p=tmp_path/'fixture.osm'
    p.write_text('<osm version="0.6"><node id="1" lat="41" lon="-74"/><node id="2" lat="41.01" lon="-74"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way></osm>')
    extent=tmp_path/'region.poly'
    extent.write_text('region\n1\n-75 40\n-73 40\n-73 42\n-75 42\n-75 40\nEND\nEND\n')
    checksum=tmp_path/'fixture.md5'
    checksum.write_text(hashlib.md5(p.read_bytes()).hexdigest()+'  '+p.name)
    tracts=gpd.GeoDataFrame({'slug':['land','coastal']},geometry=[box(-74.1,41,-73.9,41.1),box(-75.1,41,-74.9,41.1)],crs=4326)
    kwargs=dict(tract_supports=tracts,listing_support=box(-74.1,41,-73.9,41.1))
    path=prepare_geofabrik_roads(p,extent,checksum,tmp_path/'cache',box(-74.2,40.9,-73.8,41.2),tracts.geometry.union_all(),**kwargs)
    import json
    evidence=json.loads(path.with_name('osm-request.json').read_text())
    assert evidence['full_footprint_covered'] is False
    assert evidence['served_footprint_covered'] is True
    assert evidence['excluded_tract_source_gaps']==['coastal']
    kwargs['listing_support']=box(-75.1,41,-74.9,41.1)
    with pytest.raises(ValueError,match='entire analytical footprint'):
        prepare_geofabrik_roads(p,extent,checksum,tmp_path/'blocked',box(-74.2,40.9,-73.8,41.2),tracts.geometry.union_all(),**kwargs)
