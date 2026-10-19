#!/usr/bin/env python3
"""Convert cached imagery + LiDAR + OSM features into generated-world evidence.

This is a conservative RGB/height/rule classifier, not a trained semantic model.
Aerial RGB never becomes a generated terrain texture: only class weights and
robust per-roof colours survive this stage.
"""
from __future__ import annotations
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image,ImageFilter
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import Polygon,LineString,Point,mapping
from shapely.strtree import STRtree
from shapely import contains_xy
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[1]
CLASS_NAMES=['grass','rock','soil','paving','canopy','water']


def box_count(mask,radius):
    """Count true cells in each (2r+1)² window; edges count only real cells."""
    size=2*radius+1
    total=np.zeros((mask.shape[0]+size,mask.shape[1]+size),dtype='int32')
    total[1:,1:]=np.pad(mask,radius).astype('int32').cumsum(0).cumsum(1)
    return total[size:,size:]-total[:-size,size:]-total[size:,:-size]+total[:-size,:-size]


def classify(rgb,ground,canopy,buildings,roads,urban,water,woodland=None):
    """Return labels at 2 m. Mapped geometry overrides ambiguous RGB evidence."""
    r,g,b=[rgb[i].astype('float32')/255 for i in range(3)]
    brightness=(r+g+b)/3
    chroma=np.maximum(np.maximum(r,g),b)-np.minimum(np.minimum(r,g),b)
    green=(g>r*.98)&(g>b*1.10)&((2*g-r-b)>.025)
    valid=(ground>-1000)&np.isfinite(ground)
    safe=np.where(valid,ground,0)
    dy,dx=np.gradient(safe,2)
    slope=np.sqrt(dx*dx+dy*dy)
    labels=np.zeros(ground.shape,dtype='uint8')
    # Exposed rock: steep, non-green surfaces. Pale neutral patches on hills
    # are also rock candidates. Colour alone cannot distinguish rock/concrete.
    rock=(~green)&((slope>.9)|((slope>.5)&(brightness>.30)&(chroma<.16)))
    labels[rock]=1
    soil=(r>g*1.12)&(g>b*1.12)&(brightness>.15)&(slope<.9)
    labels[soil]=2
    # Concrete and asphalt keep blue close to red/green in this survey; lawns,
    # dry grass and gardens are blue-deficient, and cast shadows are blue-green.
    # Only neutral grey counts as hard surface. Lone grey pixels inside
    # gardens (sheds, paths, bins) stay grass unless neighbours support them.
    neutral=((r+g)*.5<b*1.10)&(g<r*1.12)&(chroma<.16)
    hardstanding_context=urban|((slope<.15)&(brightness>.22))
    open_ground=valid&~buildings&~roads&~water&(canopy<2.5)
    hard=open_ground&hardstanding_context&neutral&(~green)&(brightness>.13)&(slope<.65)
    hard&=box_count(hard|roads,1)>=4
    # Shadows are not evidence of a surface. They follow the lit ground
    # around them: hardstand shadows stay paving, garden shadows stay grass.
    # Inside extensive hardstand, tinted gravel, log yards and stains are
    # paving too, as are raised non-green objects such as log stacks and
    # containers; the same tints among gardens remain grass.
    shadow=open_ground&(brightness<.26)&~green&~neutral&(slope<.65)&hardstanding_context
    lit=open_ground&~shadow
    paved_share=box_count(hard,6)/np.maximum(box_count(lit,6),1)
    infill=valid&~buildings&~roads&~water&hardstanding_context&~green&(slope<.65)&(paved_share>.6)
    hard|=(shadow&(paved_share>.5))|infill
    labels[hard]=3
    # Roofs hide the ground and must never be classified from their own
    # photograph. Footprints take the surrounding ground class so that
    # distance mip levels match the gardens or hardstand around them; the
    # interiors of large sheds, with no ground nearby, stay paving.
    ground_near=box_count(lit,8)
    labels[buildings]=np.where(box_count(hard&lit,8)[buildings]*2>=ground_near[buildings],3,0)
    # Preserve shaded/desaturated crowns connected to strong green evidence,
    # and trust mapped woodland where colour alone loses dark foliage.
    near_green=np.array(Image.fromarray(green.astype('uint8')*255).filter(ImageFilter.MaxFilter(7)))>0
    compatible=(g>r*.86)&(g>b*.95)&((2*g-r-b)>0)
    woodland=np.zeros_like(green) if woodland is None else woodland
    vegetation=(green|woodland|(near_green&compatible))&(canopy>.7)&(canopy<60)&valid&~buildings&~roads&~water
    labels[vegetation]=4
    labels[roads]=3
    labels[water]=5
    return labels,vegetation


def canopy_candidates(height,eligible,spacing=2):
    """Local canopy peaks, with a deterministic spatial nonmaximum suppression."""
    # Coarse 6 m sampling limits the number of rendered canopy instances.
    h=height[1::3,1::3];mask=eligible[1::3,1::3]
    padded=np.pad(h,1,constant_values=-9999)
    maxima=np.ones(h.shape,dtype=bool)
    for dr in range(3):
        for dc in range(3):
            if dr==1 and dc==1:continue
            maxima &= h>=padded[dr:dr+h.shape[0],dc:dc+h.shape[1]]
    rr,cc=np.where(maxima&mask&(h>3)&(h<40))
    # Height first; raster coordinates break ties reproducibly.
    order=np.lexsort((cc,rr,-h[rr,cc]))
    cells={};result=[]
    for i in order:
        r,c=int(rr[i]),int(cc[i]);x=(c*3+1+.5)*spacing-5000;y=5000-(r*3+1+.5)*spacing
        key=(int((x+5000)//7),int((y+5000)//7))
        nearby=[q for a in range(key[0]-1,key[0]+2) for b in range(key[1]-1,key[1]+2) for q in cells.get((a,b),[])]
        if any((x-q[0])**2+(y-q[1])**2<49 for q in nearby):continue
        result.append((x,y,float(h[r,c]),r*3+1,c*3+1));cells.setdefault(key,[]).append((x,y))
    return result


def populate_canopy(height, eligible, spacing=2):
    """Fill measured vegetation footprints, preserving peaks but not only peaks.

    Crown radii represent approximate crowns/low-scrub clusters. A conservative
    interior footprint is marked so neighbouring crowns overlap naturally.
    """
    covered=np.zeros(eligible.shape,dtype=bool)
    points=[]
    def add(r,c,is_peak):
        r=int(r);c=int(c)
        if covered[r,c] or not eligible[r,c]:return
        h=float(height[r,c])
        if not .7<h<60:return
        kind=int(h<3.5)
        radius=float(np.clip(4.5+h*.25 if kind else h*.55,4.8,9.0))
        pixels=radius*.84/spacing
        extent=int(np.ceil(pixels))
        r0=max(0,r-extent);r1=min(eligible.shape[0],r+extent+1)
        c0=max(0,c-extent);c1=min(eligible.shape[1],c+extent+1)
        dy=np.arange(r0,r1)-r;dx=np.arange(c0,c1)-c
        covered[r0:r1,c0:c1] |= dy[:,None]**2+dx[None,:]**2<=pixels*pixels
        points.append(((c+.5)*spacing-5000,5000-(r+.5)*spacing,h,r,c,radius,kind,int(is_peak)))
    for _,_,_,r,c in canopy_candidates(height,eligible,spacing):add(r,c,True)
    # A staggered 6m lattice fills stands without the excessive overlap of
    # raster-order pixel filling. Larger crowns skip covered lattice centres.
    for r in range(0,eligible.shape[0],3):
        offset=(r//3)%2
        cc=np.arange(offset,eligible.shape[1],3)
        cc=cc[eligible[r,cc]&~covered[r,cc]]
        for c in cc:add(r,c,False)
    # Retain narrow hedges and boundary fragments missed by the coarse passes.
    rr,cc=np.where(eligible&~covered)
    for r,c in zip(rr,cc):add(r,c,False)
    return points,covered


def prepare_surfaces():
    out=ROOT/'public/world';cache=ROOT/'.cache'
    manifest=json.loads((out/'manifest.json').read_text())
    base=cache/'base-features.json'
    if not base.exists():base.write_text((out/'features.json').read_text())
    features=json.loads(base.read_text())
    print('Classifying surfaces from cached imagery, elevation and mapped geometry…',flush=True)
    with rasterio.open(cache/'imagery.tif') as src:
        rgb=src.read([1,2,3],out_shape=(3,5000,5000),resampling=Resampling.average)
    with rasterio.open(cache/'dem.tif') as src:ground=src.read(1)
    with rasterio.open(cache/'dsm.tif') as src:surface=src.read(1)
    canopy=surface-ground
    transform=from_origin(-5000,5000,2,2)
    polys=[Polygon(b['ring'],b['holes']) for b in features['buildings']]
    roads=[LineString([(p[0],p[1]) for p in r['points']]).buffer(r['width']/2+.75) for r in features['roads']]
    waters=[Polygon(p['ring'],p['holes']) for p in features['water']]
    def burn(geometries):
        if not geometries:return np.zeros((5000,5000),dtype=bool)
        return rasterize([(mapping(g),1) for g in geometries],out_shape=(5000,5000),transform=transform,dtype='uint8').astype(bool)
    building_mask=burn([p.buffer(1) for p in polys])
    road_mask=burn(roads)
    urban=burn([p.buffer(35) for p in polys]+[p.buffer(18) for p in roads])
    water=burn(waters)
    # These polygons are already cached from the original OSM acquisition.
    # No new network request is needed to restore shaded stands.
    from prepare import osm_polygon,polygons
    osm=json.loads((cache/'osm.json').read_text())
    wood=[]
    for element in osm['elements']:
        tags=element.get('tags',{})
        if tags.get('natural')=='wood' or tags.get('landuse')=='forest':wood.extend(polygons(osm_polygon(element)))
    woodland=burn(wood)
    labels,vegetation=classify(rgb,ground,canopy,building_mask,road_mask,urban,water,woodland)
    counts=np.bincount(labels.ravel(),minlength=6)
    from landscape_evidence import landscape_controls
    # Gardens: ground within 30 m of a building (town sections, farmhouse lawns).
    gardens=burn([p.buffer(30) for p in polys])
    Image.fromarray(landscape_controls(rgb,labels,ground,gardens=gardens)).save(out/'landscape-controls.png',optimize=True)
    # Three stored weights plus implicit paving weight (1 - sum RGB). Canopy gets grass/forest litter below
    # independently instantiated trees. Water geometry covers its ground.
    weights=np.zeros((5000,5000,3),dtype='uint8')
    weights[:,:,0]=np.where((labels==0)|(labels==4)|(labels==5),255,0)
    for label,channel in [(1,1),(2,2)]:weights[:,:,channel]=np.where(labels==label,255,0)
    (out/'surfaces').mkdir(exist_ok=True)
    padded=np.pad(weights,((1,1),(1,1),(0,0)),mode='edge')
    for tile in manifest['tiles']:
        r=tile['row']*500;c=tile['col']*500
        path=f'surfaces/{tile["id"]}.png'
        Image.fromarray(padded[r:r+502,c:c+502]).save(out/path,optimize=True)
        tile['surface']=path
    Image.fromarray(weights).resize((1000,1000),Image.Resampling.BOX).save(out/'surface-overview.png',optimize=True)
    # Compact labels for close-range generated ground clutter and inspection.
    labels[2::5,2::5].astype('uint8').tofile(out/'surface-index.u8')
    grid=np.fromfile(out/'elevation.f32',dtype='<f4').reshape(1001,1001)
    def display_ground(x,y):
        c=np.clip((np.asarray(x)+5000)/10,0,1000);r=np.clip((5000-np.asarray(y))/10,0,1000)
        x0=np.floor(c).astype(int);y0=np.floor(r).astype(int);x1=np.minimum(x0+1,1000);y1=np.minimum(y0+1,1000)
        fx=c-x0;fy=r-y0
        return grid[y0,x0]*(1-fx)*(1-fy)+grid[y0,x1]*fx*(1-fy)+grid[y1,x0]*(1-fx)*fy+grid[y1,x1]*fx*fy
    # Preserve canopy peaks, then fill the measured footprint between them.
    # Instances represent crowns or low-scrub clusters, not counted real trees.
    trees=[];peak_count=0;fill_count=0
    exclusions=STRtree([p.buffer(1) for p in polys]+roads)
    canopy_points,_=populate_canopy(canopy,vegetation)
    print('Placing',len(canopy_points),'canopy/low-vegetation instances…',flush=True)
    if canopy_points:
        rr=np.array([p[3] for p in canopy_points]);cc=np.array([p[4] for p in canopy_points])
        samples=np.stack([rgb[:,np.clip(rr+dr,0,4999),np.clip(cc+dc,0,4999)] for dr,dc in [(-1,-1),(-1,1),(0,0),(1,-1),(1,1)]])
        colours=np.median(samples,axis=0).T.astype('float32')
        light=colours.mean(axis=1)
        colours=np.clip(colours*(np.clip(light,48,100)/np.maximum(light,1))[:,None],20,160).astype('uint8')
    for index,(x,y,h,r,c,radius,kind,is_peak) in enumerate(canopy_points):
        if len(exclusions.query(Point(x,y),predicate='intersects')):continue
        z=float(display_ground(x,y))
        if z<-1000 or not np.isfinite(z):continue
        rotation=((r*73856093+c*19349663)%6283)/1000
        color=colours[index];packed=int(color[0])*65536+int(color[1])*256+int(color[2])
        trees.append([round(x,2),round(y,2),round(z,2),round(h,2),rotation,round(radius,2),kind,packed])
        peak_count+=is_peak;fill_count+=1-is_peak
    features['trees']=trees
    print('Sampling roof colours and surface material evidence…',flush=True)
    for b,p in zip(features['buildings'],polys):
        minx,miny,maxx,maxy=p.bounds
        c0=max(0,int((minx+5000)/2));c1=min(5000,int((maxx+5000)/2)+1)
        r0=max(0,int((5000-maxy)/2));r1=min(5000,int((5000-miny)/2)+1)
        if c1<=c0 or r1<=r0:continue
        x=-5000+(np.arange(c0,c1)+.5)*2;y=5000-(np.arange(r0,r1)+.5)*2
        xx,yy=np.meshgrid(x,y);inside=contains_xy(p.buffer(-.6),xx,yy)
        pixels=np.moveaxis(rgb[:,r0:r1,c0:c1],0,-1)[inside]
        if len(pixels)<3:continue
        brightness=pixels.mean(axis=1);pixels=pixels[(brightness>=np.percentile(brightness,20))&(brightness<=np.percentile(brightness,90))]
        if len(pixels)<2:continue
        color=np.median(pixels,axis=0).astype(int)
        b['roofColor']='#'+''.join(f'{v:02x}' for v in color)
        b['roofColorSource']='aerial-median'
    (out/'features.json').write_text(json.dumps(features,separators=(',',':'),allow_nan=False))
    manifest['surface']={'version':1,'spacing':2,'classes':CLASS_NAMES,'overview':'surface-overview.png',
                         'index':'surface-index.u8','indexSamples':1000,'maskGutterPixels':1,'landscapeControls':'landscape-controls.png',
                         'landscapeChannels':['canopy occupancy','growing grass category','DEM sky openness','DEM sun visibility'],
                         'method':'RGB/height rules constrained by OSM buildings, roads and coastlines; not a trained semantic model',
                         'areaKm2':{name:round(int(counts[i])*4/1e6,3) for i,name in enumerate(CLASS_NAMES)},
                         'canopyPeaks':peak_count,'woodlandFallbackTrees':0,'canopyFillInstances':fill_count,
                         'lowVegetationInstances':sum(t[6]==1 for t in trees),
                         'placementMethod':'Canopy peaks plus footprint coverage fill; broad crowns and low-scrub clusters approximate vegetation mass',
                         'roofColors':sum('roofColor' in b for b in features['buildings'])}
    from landscape_evidence import write_relief
    write_relief(cache,out,manifest)
    manifest['stats']['trees']=len(trees)
    from vegetation_coverage import measure
    manifest['surface']['coverage']=measure(features,labels[2::5,2::5],terrain=grid)
    manifest['approximations']=[a for a in manifest['approximations'] if not a.startswith(('Tree positions','Tree locations','Ground classes'))]
    manifest['approximations'] += ['Ground classes use RGB/height heuristics and OSM masks. Paving needs neutral grey imagery; shadows and ground under roofs take the surrounding class. Narrow driveways, tinted gravel and survey-date differences can still be misclassified.',
          'Generated ground materials contain no aerial RGB. Grass, rock, soil and paving are procedural material families.',
          'Vegetation instances combine measured canopy peaks with coverage fill and low-scrub clusters. Mapped woodland supports shaded foliage; species and crown widths remain approximate.',
          'Ground vegetation condition and canopy occupancy are categorical image estimates. DEM horizons shade terrain, and optional LINZ hillshade contributes only local fine-relief lighting; the terrain mesh remains 10 m at its finest level.',
          'Roof colours are robust aerial RGB samples and can retain lighting bias; facade materials are inferred.']
    manifest['approximations']=list(dict.fromkeys(manifest['approximations']))
    manifest['surface']['generatedAt']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False))
    print('Surface evidence ready:',json.dumps(manifest['surface']),flush=True)
    return manifest

if __name__=='__main__':prepare_surfaces()
