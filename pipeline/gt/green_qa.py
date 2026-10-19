"""Paired canopy/satellite QA with explicit staging and geographic-grain labels."""
from pathlib import Path
import json
import os
import geopandas as gpd
import psycopg
from gt.db.migrate import database_url, repo_root


def render_green_qa(region_slug: str, *, staged: bool = True) -> Path:
    qa = repo_root() / 'data/reports/qa'
    qa.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR', str(qa / '.matplotlib-cache'))
    import matplotlib.pyplot as plt
    if staged:
        query = '''
          WITH canopy AS (
            SELECT DISTINCT ON (rm.region_id) rm.region_id,rm.value
            FROM region_metrics rm WHERE rm.metric_key='tree_canopy_pct'
            ORDER BY rm.region_id,rm.vintage DESC,rm.computed_at DESC
          ), paired AS (
            SELECT r.slug,r.geom,c.value AS canopy_value,g.value AS gvi_value,
              100*(percent_rank() OVER(ORDER BY c.value)-percent_rank() OVER(ORDER BY g.value)) AS divergence
            FROM staging.layer_region_metrics g
            JOIN regions r ON r.slug=g.region_slug JOIN canopy c ON c.region_id=r.id
            WHERE g.region_group=%s AND g.metric_key='gvi_ndvi_street'
              AND g.vintage='2025-summer' AND r.region_type='census_tract'
          ) SELECT * FROM paired
        '''
        listing_source = "staging.layer_listing_metrics"
    else:
        query = '''
          SELECT r.slug,r.geom,d.canopy_value,d.gvi_value,d.value AS divergence
          FROM green_divergence_region_metrics d JOIN regions r ON r.id=d.region_id
          WHERE r.region_group=%s AND r.region_type='census_tract'
        '''
        listing_source = "listing_metrics"
    with psycopg.connect(database_url()) as conn:
        frame = gpd.read_postgis(query,conn,params=(region_slug,),geom_col='geom')
        # Street-name match is only a candidate for local raster inspection;
        # address text cannot establish photographic eye-level vegetation.
        pairs = conn.execute(f'''
          SELECT a.listing_id,b.listing_id,la.address,lb.address,a.value,b.value,
            ST_Distance(la.geom::geography,lb.geom::geography) AS distance_m
          FROM {listing_source} a JOIN {listing_source} b ON a.listing_id<b.listing_id
          JOIN listings la ON la.id=a.listing_id JOIN listings lb ON lb.id=b.listing_id
          WHERE a.metric_key='gvi_ndvi_street' AND b.metric_key=a.metric_key
            AND a.grain='buffer_100m' AND b.grain=a.grain
            AND a.vintage='2025-summer' AND b.vintage=a.vintage
            AND la.region_slug=%s AND lb.region_slug=%s
            AND ST_DWithin(la.geom::geography,lb.geom::geography,200)
            AND regexp_replace(split_part(la.address,',',1),'^[0-9]+[A-Za-z]?\\s+','')
              = regexp_replace(split_part(lb.address,',',1),'^[0-9]+[A-Za-z]?\\s+','')
          ORDER BY abs(a.value-b.value) DESC,a.listing_id,b.listing_id LIMIT 1
        ''',(region_slug,region_slug)).fetchone()
    if frame.empty:
        raise RuntimeError('Paired canopy/GVI inputs required before green QA')
    fig,axes=plt.subplots(1,3,figsize=(19,8))
    for ax,column,title,cmap,limits in [
        (axes[0],'canopy_value','Canopy cover (%)','Greens',dict(vmin=0,vmax=100)),
        (axes[1],'gvi_value','Street-adjacent satellite NDVI','Greens',dict(vmin=-1,vmax=1)),
        (axes[2],'divergence','Canopy percentile − NDVI percentile (pp)','BrBG',dict(vmin=-100,vmax=100))]:
        frame.plot(column=column,ax=ax,legend=True,cmap=cmap,linewidth=.1,edgecolor='#777777',**limits)
        ax.set_title(title)
        ax.set_axis_off()
    fig.suptitle(f'{region_slug} · {"STAGED" if staged else "PROMOTED"} tract context · satellite estimate')
    fig.tight_layout()
    path=qa/f'green_comparison_{region_slug}{"_staged" if staged else ""}.png'
    fig.savefig(path,dpi=170)
    plt.close(fig)
    path.with_suffix('.json').write_text(json.dumps({
        'region':region_slug,'staged':staged,'tract_count':len(frame),
        'divergence_range':[float(frame.divergence.min()),float(frame.divergence.max())],
        'nearby_same_street_candidate':None if pairs is None else dict(zip(
            ['listing_a','listing_b','address_a','address_b','ndvi_a','ndvi_b','distance_m'],pairs)),
        'limitation':'Address/distance identify a candidate only. Inspect road/raster context before claiming same-block greenery acceptance; this is never photographic GVI.'
    },indent=2,default=str))
    return path
