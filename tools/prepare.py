#!/usr/bin/env python3
"""Prepare real, cached LINZ/OSM scenery. All coordinates are NZTM2000 metres.

Public COGs are read by HTTP range, then cropped/downsampled into local rasters.
No API keys. A completed cache can rebuild with --offline.
"""
from __future__ import annotations
import argparse
import concurrent.futures as futures
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import warnings
import time
from urllib.parse import urljoin

import numpy as np
from PIL import Image
from pyproj import Transformer
import rasterio
from rasterio.errors import NodataShadowWarning
warnings.filterwarnings("ignore", category=NodataShadowWarning)
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
import requests
from shapely.geometry import box, shape, Polygon, LineString, Point, mapping
from shapely.ops import polygonize, unary_union, linemerge
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache'
OUT = ROOT / 'public/world'
CONFIG = json.loads((ROOT / 'world.config.json').read_text())
FORWARD = Transformer.from_crs(4326, 2193, always_xy=True)
INVERSE = Transformer.from_crs(2193, 4326, always_xy=True)
CX, CY = FORWARD.transform(CONFIG['center']['longitude'], CONFIG['center']['latitude'])
HALF = CONFIG['extentMeters'] / 2
BOUNDS = (CX-HALF, CY-HALF, CX+HALF, CY+HALF)
AREA = box(*BOUNDS)
LOCAL_AREA = box(-HALF, -HALF, HALF, HALF)
OFFLINE = False
SURVEYS = {}
SESSION = requests.Session()
SESSION.headers['User-Agent'] = 'LytteltonWorldPrototype/0.1 (local research viewer)'


def log(*parts):
    print(*parts, flush=True)


def cached_json(url, *, query=None):
    key = hashlib.sha256((url + (query or '')).encode()).hexdigest()
    path = CACHE / 'http' / (key + '.json')
    if path.exists():
        return json.loads(path.read_text())
    if OFFLINE:
        raise RuntimeError(f'Offline cache missing: {url}')
    path.parent.mkdir(parents=True, exist_ok=True)
    failure = None
    for attempt in range(3):
        try:
            r = SESSION.post(url, data={'data':query}, timeout=240) if query else SESSION.get(url, timeout=60)
            r.raise_for_status()
            result = r.json()
            if result.get('remark'):
                raise RuntimeError(f'Incomplete Overpass response: {result["remark"]}')
            tmp = path.with_suffix('.tmp')
            tmp.write_text(json.dumps(result))
            tmp.replace(path)
            return result
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            failure = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f'Could not retrieve {url}: {failure}')


def collection(bucket, slug, product):
    url = f'https://{bucket}.s3-ap-southeast-2.amazonaws.com/{slug}/{product}/2193/collection.json'
    c = cached_json(url)
    SURVEYS[url] = {'title':c['title'], 'url':url, 'license':c['license'],
                    'dates':c['extent']['temporal']['interval'], 'providers':c.get('providers',[])}
    return url, c


def selected_assets(bucket, slug, product):
    """Decode LINZ map-sheet grids from one authoritative item per nearby sheet.

    A Topo50 sheet is 24 km east-west and 36 km north-south. Subdivisions
    use scale denominator / 50000. Check inferred bounds against metadata.
    """
    url, c = collection(bucket, slug, product)
    # Lyttelton's entire 10 km square is in BX24. Restrict metadata reads to
    # this sheet, but verify all four corners before trusting that restriction.
    links = [l for l in c['links'] if l['rel']=='item' and ('/BX24_' in l['href'] or l['href'].endswith('/BX24.json'))]
    if not links:
        log('  No BX24 coverage:', c['title'])
        SURVEYS.pop(url,None)
        return []
    sample_url = urljoin(url, links[0]['href'])
    sample = cached_json(sample_url)
    sample_name = sample['id']
    match = re.fullmatch(r'([A-Z]{2}\d{2})_(\d+)_(\d+)', sample_name)
    if sample_name == 'BX24':
        match = re.fullmatch(r'([A-Z]{2}\d{2})_(\d+)_(\d+)', 'BX24_50000_11')
    if not match:
        raise RuntimeError(f'Unrecognised LINZ tile name: {sample_name}')
    scale = int(match[2]); digits = len(match[3])//2
    row, col = int(match[3][:digits]), int(match[3][digits:])
    width, height = 24000 * scale/50000, 36000 * scale/50000
    # Reprojecting the geometry corners is enough to infer the integer sheet
    # origin; the actual COG transform is checked again when read.
    coords = np.array(sample['geometry']['coordinates'][0])
    xx, yy = FORWARD.transform(coords[:,0],coords[:,1])
    sheet_left = round(min(xx) - (col-1)*width)
    sheet_top = round(max(yy) + (row-1)*height)
    sheet = box(sheet_left,sheet_top-36000,sheet_left+24000,sheet_top)
    if not sheet.covers(AREA):
        raise RuntimeError('Configured extent leaves BX24; extend sheet selection before changing the region.')
    selected=[]
    for l in links:
        name=Path(l['href']).stem
        tail='11' if name == 'BX24' else name.split('_')[-1]; row,col=int(tail[:len(tail)//2]),int(tail[len(tail)//2:])
        left=sheet_left+(col-1)*width; top=sheet_top-(row-1)*height
        if not box(left,top-height,left+width,top).intersects(AREA):
            continue
        selected.append((urljoin(url,l['href']), (left,top-height,left+width,top)))
    log(' ',c['title'], ':',len(selected),'intersecting assets')
    if not selected:SURVEYS.pop(url,None)
    return selected


def crop_asset(item_url, expected_bounds, kind):
    key=hashlib.sha256((item_url+kind+'v1').encode()).hexdigest()
    path=CACHE/'rasters'/(key+'.tif')
    if path.exists():
        return path
    if OFFLINE:
        raise RuntimeError(f'Offline raster missing: {item_url}')
    item=cached_json(item_url)
    asset=item['assets'].get('visual') or next(a for a in item['assets'].values() if 'tiff' in a.get('type',''))
    href=urljoin(item_url,asset['href'])
    spacing=1 if kind=='imagery' else 2
    left=max(BOUNDS[0],expected_bounds[0]); right=min(BOUNDS[2],expected_bounds[2])
    bottom=max(BOUNDS[1],expected_bounds[1]); top=min(BOUNDS[3],expected_bounds[3])
    # Snap every cropped source to the common output grid.
    c0=max(0,math.floor((left-BOUNDS[0])/spacing)); c1=min(int(10000/spacing),math.ceil((right-BOUNDS[0])/spacing))
    r0=max(0,math.floor((BOUNDS[3]-top)/spacing)); r1=min(int(10000/spacing),math.ceil((BOUNDS[3]-bottom)/spacing))
    dst_transform=from_origin(BOUNDS[0]+c0*spacing,BOUNDS[3]-r0*spacing,spacing,spacing)
    path.parent.mkdir(parents=True,exist_ok=True)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tiff,.tif',
                      GDAL_HTTP_MAX_RETRY=3, GDAL_HTTP_RETRY_DELAY=2, GDAL_HTTP_TIMEOUT=90):
        with rasterio.open(href) as src:
            if src.crs.to_epsg()!=2193 or max(abs(a-b) for a,b in zip(src.bounds,expected_bounds))>2:
                raise RuntimeError(f'Unexpected source projection/bounds: {href}')
            from rasterio.vrt import WarpedVRT
            with WarpedVRT(src,crs='EPSG:2193',transform=dst_transform,width=c1-c0,height=r1-r0,
                           resampling=Resampling.average if kind=='imagery' else Resampling.bilinear,
                           nodata=0 if kind=='imagery' else -9999) as vrt:
                bands=[1,2,3] if kind=='imagery' else [1]
                data=vrt.read(bands)
                valid=vrt.dataset_mask()
            profile={'driver':'GTiff','height':r1-r0,'width':c1-c0,'count':len(bands),
                     'dtype':data.dtype,'crs':'EPSG:2193','transform':dst_transform,
                     'compress':'deflate','tiled':True,'nodata':0 if kind=='imagery' else -9999}
            temp=path.with_suffix('.tmp.tif')
            with rasterio.open(temp,'w',**profile) as dst:
                dst.write(data)
                dst.write_mask(valid)
            temp.replace(path)
    return path


def crop_with_retry(item_url, expected_bounds, kind):
    for attempt in range(4):
        try:
            return crop_asset(item_url, expected_bounds, kind)
        except (rasterio.errors.RasterioIOError, rasterio.errors.RasterioError) as exc:
            if attempt == 3:
                raise
            log('  Retrying source read:', Path(item_url).name, str(exc)[:100])
            time.sleep(2 * (attempt + 1))


def build_raster(kind, selections):
    final=CACHE/(kind+'.tif')
    if final.exists():
        return final
    all_paths=[]
    # Each collection is an overlay: later/newer surveys replace valid pixels.
    for assets in selections:
        with futures.ThreadPoolExecutor(max_workers=6) as pool:
            jobs=[pool.submit(crop_with_retry,u,b,kind) for u,b in assets]
            for n,job in enumerate(jobs):
                all_paths.append(job.result())
                if (n+1)%20==0:log('  Cached',kind,n+1,'/',len(jobs))
    if not all_paths:
        raise RuntimeError(f'No real source data for {kind}')
    spacing=1 if kind=='imagery' else 2
    count=3 if kind=='imagery' else 1
    size=int(10000/spacing)
    dtype='uint8' if kind=='imagery' else 'float32'
    nodata=0 if kind=='imagery' else -9999
    data=np.full((count,size,size),nodata,dtype=dtype)
    validity=np.zeros((size,size),dtype='uint8')
    for path in all_paths:
        with rasterio.open(path) as src:
            c=round((src.bounds.left-BOUNDS[0])/spacing)
            r=round((BOUNDS[3]-src.bounds.top)/spacing)
            block=src.read(); mask=src.dataset_mask()>0
            target=data[:,r:r+src.height,c:c+src.width]
            target[:,mask]=block[:,mask]
            validity[r:r+src.height,c:c+src.width][mask]=255
    with rasterio.open(final,'w',driver='GTiff',height=size,width=size,count=count,dtype=dtype,
                       crs='EPSG:2193',transform=from_origin(BOUNDS[0],BOUNDS[3],spacing,spacing),
                       nodata=nodata,compress='deflate',tiled=True) as dst:
        dst.write(data);dst.write_mask(validity)
    return final


def get_osm():
    lon0,lat0=INVERSE.transform(BOUNDS[0]-200,BOUNDS[1]-200)
    lon1,lat1=INVERSE.transform(BOUNDS[2]+200,BOUNDS[3]+200)
    bbox=f'{lat0},{lon0},{lat1},{lon1}'
    query=f'''[out:json][timeout:180];(
way[building]({bbox});relation[building][type=multipolygon]({bbox});
way[highway]({bbox});way[natural=coastline]({bbox});
way[natural~"^(wood|water)$"]({bbox});relation[natural~"^(wood|water)$"]({bbox});
way[landuse~"^(forest|reservoir)$"]({bbox});relation[landuse~"^(forest|reservoir)$"]({bbox});
);out geom;'''
    last=None
    for endpoint in ['https://overpass-api.de/api/interpreter','https://overpass.kumi.systems/api/interpreter']:
        try:
            return cached_json(endpoint,query=query)
        except RuntimeError as exc:
            last=exc
    raise RuntimeError(f'OSM fetch failed: {last}')


def coords(geometry):
    if not geometry or any(p is None for p in geometry):return []
    x,y=FORWARD.transform([p['lon'] for p in geometry],[p['lat'] for p in geometry])
    return list(zip(np.array(x)-CX,np.array(y)-CY))


def osm_polygon(element):
    try:
        if element['type']=='way':
            p=coords(element.get('geometry'))
            return Polygon(p).buffer(0) if len(p)>=4 and p[0]==p[-1] else None
        rings={role:[] for role in ['outer','inner']}
        for m in element.get('members',[]):
            p=coords(m.get('geometry'))
            if len(p)>=2:rings['inner' if m.get('role')=='inner' else 'outer'].append(LineString(p))
        outer=unary_union(list(polygonize(unary_union(rings['outer']))))
        inner=unary_union(list(polygonize(unary_union(rings['inner']))))
        return outer.difference(inner).buffer(0)
    except (ValueError,TypeError):return None


def polygons(g):
    if g is None or g.is_empty:return []
    if g.geom_type=='Polygon':return [g]
    return [p for p in g.geoms if p.geom_type=='Polygon']


def water_polygons(elements):
    coast=[];water=[]
    for e in elements:
        tags=e.get('tags',{})
        if tags.get('natural')=='coastline':
            p=coords(e.get('geometry'))
            if len(p)>1:
                clipped=LineString(p).intersection(LOCAL_AREA)
                if clipped.geom_type=='LineString' and not clipped.is_empty:coast.append(clipped)
                elif clipped.geom_type=='MultiLineString':coast.extend(clipped.geoms)
        if tags.get('natural')=='water' or tags.get('landuse')=='reservoir':
            water.extend(polygons(osm_polygon(e)))
    if not coast:raise RuntimeError('No OSM coastline: cannot safely identify harbour water.')
    faces=list(polygonize(unary_union(coast+[LOCAL_AREA.boundary])))
    for face in faces:
        p=face.representative_point()
        line=min(coast,key=lambda l:l.distance(p))
        t=line.project(p);a=line.interpolate(max(0,t-0.5));b=line.interpolate(min(line.length,t+0.5))
        cross=(b.x-a.x)*(p.y-a.y)-(b.y-a.y)*(p.x-a.x)
        # OSM coastline direction has land to the left and sea to the right.
        if cross<0:water.append(face)
    merged=unary_union(water).intersection(LOCAL_AREA)
    if merged.area<1e6:raise RuntimeError('Harbour water polygon is unexpectedly small; inspect OSM coastlines.')
    return merged


def sample_grid(grid,x,y,spacing=2):
    """Bilinear pixel-centre sampling; coordinates are local east/north."""
    col=np.clip((np.asarray(x)+HALF)/spacing-0.5,0,grid.shape[1]-1)
    row=np.clip((HALF-np.asarray(y))/spacing-0.5,0,grid.shape[0]-1)
    c=np.floor(col).astype(int);r=np.floor(row).astype(int)
    c1=np.minimum(c+1,grid.shape[1]-1);r1=np.minimum(r+1,grid.shape[0]-1)
    fx=col-c;fy=row-r
    return grid[r,c]*(1-fx)*(1-fy)+grid[r,c1]*fx*(1-fy)+grid[r1,c]*(1-fx)*fy+grid[r1,c1]*fx*fy


def building_roof(poly, dem, dsm, tags):
    """Fit flat or two-plane gable roof to measured DSM pixels inside footprint.

    Plane fitting is conservative: reject weak fits; retain measured height.
    No facade detail is claimed as observed.
    """
    minx,miny,maxx,maxy=poly.bounds
    xx=np.arange(math.ceil((minx+1)/2)*2,maxx-1,2)
    yy=np.arange(math.ceil((miny+1)/2)*2,maxy-1,2)
    if not len(xx) or not len(yy):xx=np.array([poly.centroid.x]); yy=np.array([poly.centroid.y])
    gx,gy=np.meshgrid(xx,yy);gx=gx.ravel();gy=gy.ravel()
    from shapely import contains_xy
    keep=contains_xy(poly.buffer(-0.8),gx,gy);gx=gx[keep];gy=gy[keep]
    if len(gx)>12000:gx=gx[::math.ceil(len(gx)/12000)];gy=gy[::math.ceil(len(gy)/12000)]
    boundary=np.array(poly.exterior.coords)
    grounds=sample_grid(dem,boundary[:,0],boundary[:,1])
    ground=float(np.median(grounds[grounds>-1000])) if np.any(grounds>-1000) else 0
    surface=sample_grid(dsm,gx,gy) if len(gx) else np.array([])
    valid=(surface>ground+2)&(surface<ground+100)&np.isfinite(surface)
    measured=len(surface)>0 and valid.sum()>=8 and valid.mean()>=0.55
    if measured:
        z=surface[valid];x=gx[valid];y=gy[valid]
        lo,hi=np.percentile(z,[5,95]);ok=(z>=lo)&(z<=hi+0.1);x=x[ok];y=y[ok];z=z[ok]
        flat=float(np.median(z))
        best={'kind':'flat','height':round(max(2,flat-ground),2),'source':'dsm','error':round(float(np.sqrt(np.mean((z-flat)**2))),2)}
        rect=np.array(poly.minimum_rotated_rectangle.exterior.coords)
        edge=rect[1]-rect[0];angle=math.atan2(edge[1],edge[0])
        for theta in ([] if len(poly.interiors) else [angle,angle+math.pi/2]):
            u=np.array([math.cos(theta),math.sin(theta)])
            projections=boundary@u;center=(projections.min()+projections.max())/2
            distances=np.abs(x*u[0]+y*u[1]-center)
            a=np.column_stack([np.ones(len(x)),distances])
            coefficients=np.linalg.lstsq(a,z,rcond=None)[0]
            pred=a@coefficients;rmse=float(np.sqrt(np.mean((z-pred)**2)))
            span=(projections.max()-projections.min())/2;rise=-coefficients[1]*span
            if coefficients[1]<-0.12 and 0.8<rise<12 and rmse<min(1.2,best['error']*0.72):
                best={'kind':'gable','source':'dsm','height':round(float(coefficients[0]-ground),2),
                      'axis':[round(float(u[0]),6),round(float(u[1]),6)],'center':round(float(center),3),
                      'slope':round(float(coefficients[1]),5),'error':round(rmse,2)}
        return ground,best
    def number(v):
        try:return float(str(v).replace('m','').strip())
        except (ValueError,TypeError):return None
    h=number(tags.get('height'));levels=number(tags.get('building:levels'))
    return ground,{'kind':'flat','height':max(2,min(100,h or (levels*3 if levels else CONFIG['buildingDefaultHeight']))),
                   'source':'osm' if h or levels else 'default','error':None}


def build_features(elements,dem,dsm,water):
    buildings=[];roads=[];wood=[];seen=set();bridges=0
    # Relation members must not also appear as standalone building footprints.
    member_ids={m['ref'] for e in elements if e['type']=='relation' and e.get('tags',{}).get('building')
                for m in e.get('members',[]) if m.get('type')=='way'}
    for e in elements:
        tags=e.get('tags',{})
        if tags.get('building') and tags.get('building')!='no':
            if e['type']=='way' and e['id'] in member_ids:continue
            g=osm_polygon(e)
            for p in polygons(g):
                p=p.intersection(LOCAL_AREA)
                for poly in polygons(p):
                    if poly.area<8 or not poly.is_valid:continue
                    key=poly.wkb_hex
                    if key in seen:continue
                    seen.add(key)
                    ground,roof=building_roof(poly,dem,dsm,tags)
                    buildings.append({'id':f'{e["type"]}/{e["id"]}','name':tags.get('name',''),
                       'use':tags.get('building'),'ring':np.round(np.array(poly.exterior.coords)[:-1],2).tolist(),
                       'holes':[np.round(np.array(r.coords)[:-1],2).tolist() for r in poly.interiors],
                       'ground':round(ground,2),'roof':roof})
        if tags.get('highway') and e['type']=='way' and tags.get('tunnel') not in ['yes','building_passage'] and tags.get('covered')!='yes':
            p=coords(e.get('geometry'))
            if len(p)<2:continue
            line=LineString(p).intersection(LOCAL_AREA)
            lines=[line] if line.geom_type=='LineString' else list(line.geoms) if line.geom_type=='MultiLineString' else []
            bridge=tags.get('bridge') not in [None,'no'];bridges+=int(bridge)
            widths={'motorway':11,'trunk':10,'primary':9,'secondary':8,'tertiary':7,'residential':6,'service':3.5,'unclassified':5,'track':2.5,'footway':1.2,'path':1.2,'steps':1.2,'cycleway':2}
            try:width=min(24,max(0.7,float(tags.get('width',widths.get(tags['highway'],3)))))
            except ValueError:width=widths.get(tags['highway'],3)
            for l in lines:
                if l.length<1:continue
                count=max(2,math.ceil(l.length/5)+1)
                points=np.array([[l.interpolate(t).x,l.interpolate(t).y] for t in np.linspace(0,l.length,count)])
                z=sample_grid(dem,points[:,0],points[:,1])
                if np.any(z<-1000):continue
                if bridge:z=np.linspace(z[0],z[-1],count)+0.5
                roads.append({'id':e['id'],'name':tags.get('name',''),'kind':tags['highway'],'bridge':bridge,
                              'width':width,'points':np.round(np.column_stack([points,z+0.25]),2).tolist()})
        if tags.get('natural')=='wood' or tags.get('landuse')=='forest':
            wood.extend(polygons(osm_polygon(e)))
    forest=unary_union(wood).intersection(LOCAL_AREA).difference(water)
    exclusions=[Polygon(b['ring']).buffer(5) for b in buildings]
    exclusions += [LineString([(p[0],p[1]) for p in r['points']]).buffer(r['width']/2+3) for r in roads]
    if exclusions:forest=forest.difference(unary_union(exclusions))
    rng=np.random.default_rng(CONFIG['seed'])
    tree_points=[]
    for p in polygons(forest):
        a,b,c,d=p.bounds
        # Widely spaced, illustrative instances; not individually surveyed trees.
        n=min(30000,int(p.area/180))
        x=rng.uniform(a,c,n*2);y=rng.uniform(b,d,n*2)
        from shapely import contains_xy
        mask=contains_xy(p,x,y)
        x=x[mask][:n];y=y[mask][:n]
        z=sample_grid(dem,x,y);tops=sample_grid(dsm,x,y);h=tops-z
        for xx,yy,zz,hh in zip(x,y,z,h):
            if zz<-1000:continue
            height=float(np.clip(hh,5,22)) if 3<hh<45 else float(rng.uniform(5,11))
            tree_points.append([round(float(xx),2),round(float(yy),2),round(float(zz),2),round(height,2),round(float(rng.uniform(0,math.tau)),3)])
    features={'buildings':buildings,'roads':roads,'trees':tree_points,
              'water':[{'ring':np.round(np.array(p.exterior.coords)[:-1],2).tolist(),
                        'holes':[np.round(np.array(r.coords)[:-1],2).tolist() for r in p.interiors]} for p in polygons(water)]}
    return features


def write_world(dem_path,dsm_path,imagery_path,osm):
    OUT.mkdir(parents=True,exist_ok=True)
    with rasterio.open(dem_path) as src:dem=src.read(1)
    with rasterio.open(dsm_path) as src:dsm=src.read(1)
    water=water_polygons(osm['elements'])
    from rasterio.features import rasterize
    transform=from_origin(BOUNDS[0],BOUNDS[3],2,2)
    from shapely.affinity import translate
    sea=rasterize([(mapping(translate(water,xoff=CX,yoff=CY)),1)],out_shape=dem.shape,transform=transform,dtype='uint8').astype(bool)
    missing=(dem<-1000)&~sea
    missing_count=int(missing.sum())
    log('Land elevation missing pixels:',missing_count,'/',int((~sea).sum()))
    # Only mapped water is assigned a sea-floor height. Missing land stays NaN.
    dem[sea]=-2;dem[missing]=np.nan
    grid_x,grid_y=np.meshgrid(np.linspace(-HALF,HALF,1001),np.linspace(HALF,-HALF,1001))
    terrain=sample_grid(dem,grid_x,grid_y)
    log('Building geometry, roads and woodland...')
    features=build_features(osm['elements'],np.nan_to_num(dem,nan=-9999),dsm,water)
    # Align scenery bases to the displayed 10 m terrain, not just the finer
    # source raster. Keep measured roof elevations in world coordinates.
    def display_ground(x, y):
        return sample_grid(terrain, np.asarray(x)+5, np.asarray(y)-5, 10)
    for building in features['buildings']:
        ring=np.array(building['ring'])
        base=display_ground(ring[:,0],ring[:,1])
        valid=base[np.isfinite(base)]
        building['foundation']=round(float(min(valid.min(),building['ground'])-1),2) if len(valid) else building['ground']-5
    for road in features['roads']:
        points=np.array(road['points']);z=display_ground(points[:,0],points[:,1])
        if road['bridge']:z=np.linspace(z[0],z[-1],len(z))+0.5
        points[:,2]=z+0.3
        road['points']=np.round(points,2).tolist() if np.isfinite(points).all() else []
    features['roads']=[r for r in features['roads'] if r['points']]
    for tree in features['trees']:
        tree[2]=round(float(display_ground(tree[0],tree[1])),2)
    features['trees']=[t for t in features['trees'] if np.isfinite(t).all()]
    (CACHE/'base-features.json').write_text(json.dumps(features,separators=(',',':'),allow_nan=False))
    (OUT/'features.json').write_text(json.dumps(features,separators=(',',':'),allow_nan=False))
    tiles=[]
    (OUT/'tiles').mkdir(exist_ok=True)
    with rasterio.open(imagery_path) as img:
        for row in range(10):
            for col in range(10):
                id=f'{col}-{row}'
                heights=terrain[row*100:row*100+101,col*100:col*100+101].astype('<f4')
                heights.tofile(OUT/'tiles'/f'{id}.f32')
                # Tile images are exactly on the same east/north grid as geometry.
                rgb=img.read([1,2,3],window=rasterio.windows.Window(col*1000,row*1000,1000,1000))
                Image.fromarray(np.moveaxis(rgb,0,-1)).save(OUT/'tiles'/f'{id}.webp',quality=87,method=4)
                tiles.append({'id':id,'col':col,'row':row,'x':col*1000-HALF,'north':HALF-row*1000,
                              'heights':f'tiles/{id}.f32','imagery':f'tiles/{id}.webp',
                              'minHeight':round(float(np.nanmin(heights)),2),'maxHeight':round(float(np.nanmax(heights)),2),
                              'missingSamples':int(np.isnan(heights).sum())})
        overview=img.read([1,2,3],out_shape=(3,1000,1000),resampling=Resampling.average)
        Image.fromarray(np.moveaxis(overview,0,-1)).save(OUT/'overview.webp',quality=85)
    np.nan_to_num(terrain,nan=-9999).astype('<f4').tofile(OUT/'elevation.f32')
    roof_counts={k:sum(b['roof']['source']==k for b in features['buildings']) for k in ['dsm','osm','default']}
    manifest={'version':1,'name':'Lyttelton / Whakaraupō','center':CONFIG['center'],
              'crs':'EPSG:2193','verticalDatum':'NZVD2016','origin':[CX,CY],'bounds':list(BOUNDS),
              'extentMeters':10000,'tileMeters':1000,'terrainSpacing':10,'terrainSamples':1001,'imagerySpacing':1,
              'tiles':tiles,'features':'features.json','elevation':'elevation.f32','overview':'overview.webp',
              'generatedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
              'osmTimestamp':osm.get('osm3s',{}).get('timestamp_osm_base'),
              'sources':list(SURVEYS.values()),'missingLandPixels2m':missing_count,
              'stats':{'buildings':len(features['buildings']),'roads':len(features['roads']),'trees':len(features['trees']),
                       'roofSources':roof_counts,'fittedGables':sum(b['roof']['kind']=='gable' for b in features['buildings'])},
              'approximations':['Building facades are untextured procedural walls.','Roof fits use a 2 m resampling of the 1 m DSM; unsupported forms use measured flat roofs.',
                 'Tree positions are deterministic samples inside OSM woodland; heights use DSM where supported.',
                 'Road widths without OSM measurements use class defaults. Bridges use endpoint interpolation; tunnels are omitted.',
                 'Water is a flat coastline-constrained surface at 0 m NZVD2016, not a tide model.']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False))
    log('Ready:',json.dumps(manifest['stats']))


def main():
    global OFFLINE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--stage',choices=['all','rasters','features'],default='all')
    args=parser.parse_args();OFFLINE=args.offline
    CACHE.mkdir(exist_ok=True)
    stamp=CACHE/'configuration.json'
    raster_config={k:CONFIG[k] for k in ['center','extentMeters','tileMeters','terrainSpacing','imagerySpacing','elevationCollections','imageryCollections']}
    if stamp.exists() and json.loads(stamp.read_text()) != raster_config:
        raise RuntimeError('Raster configuration changed. Move .cache aside before regenerating to avoid reusing stale mosaics.')
    stamp.write_text(json.dumps(raster_config,indent=2))
    log('Centre NZTM:',CX,CY,'bounds:',BOUNDS)
    # Save collection metadata even when cached mosaics already exist.
    catalog=cached_json('https://nz-imagery.s3-ap-southeast-2.amazonaws.com/catalog.json')
    available={l['href'].removeprefix('./').removesuffix('/rgb/2193/collection.json') for l in catalog['links'] if '/rgb/2193/' in l.get('href','')}
    imagery_slugs=[s for s in CONFIG['imageryCollections'] if s in available]
    if not imagery_slugs:raise RuntimeError('None of the configured imagery surveys exist in LINZ catalog.')
    selections={}
    for kind,product in [('dem','dem_1m'),('dsm','dsm_1m'),('imagery','rgb')]:
        bucket='nz-imagery' if kind=='imagery' else 'nz-elevation'
        slugs=imagery_slugs if kind=='imagery' else CONFIG['elevationCollections']
        assets=[selected_assets(bucket,s,product) for s in slugs]
        selections[kind]=assets
        log('Prepare',kind)
        build_raster(kind,assets)
    (CACHE/'sources.json').write_text(json.dumps(SURVEYS))
    if args.stage!='rasters':
        osm=get_osm()
        (CACHE/'osm.json').write_text(json.dumps(osm))
        write_world(CACHE/'dem.tif',CACHE/'dsm.tif',CACHE/'imagery.tif',osm)
        from surfaces import prepare_surfaces
        prepare_surfaces()

if __name__=='__main__':
    try:main()
    except Exception as exc:
        log('Preparation failed:',exc)
        raise
