#!/usr/bin/env python3
"""A street corridor with kerbs, gutters and footpaths, built in Blender from the city kit's surfaces.

The OSM road ribbon has no kerbs or footpaths. For a street with a street inventory
(tools/street_inventory.py), this measures the cross-section every 0.95 m along the centreline:

- **Kerb lines** from evidence in the 7.5 cm aerial: each parking run's cars stand against the kerb, so the
  kerb is the run's car-centre offset plus half the car's depth across the street at its parking angle
  (parallel, angle or perpendicular) plus a 0.2-0.35 m gap. A zebra crossing runs kerb to kerb, so its
  bars set the kerbs at the crossing (London Street's crossings sit on build-outs). Between evidence the
  kerb is interpolated, which tapers the kerb into and out of crossing build-outs.
- **Footpaths** from the kerb back to the building line: the LiDAR-registered facades of modelled
  buildings (tools/street_buildings.py), else OSM footprints, else a 3 m footpath.
- **Parking lanes** where the runs are, so they can be surfaced apart from the traffic lanes.

Blender (tools/blender_street_corridor.py) builds the carriageway, parking lanes, gutters, kerbs (lowered at
crossings) and footpaths as one mesh in local metres, height above the ground in z, textured with surfaces
cropped from the "modular kit city builder starter kit" atlas (Pieter Ferreira, CC BY 4.0): asphalt,
concrete and pavers. The viewer drapes it onto the terrain, under the inventory's measured paint.

  npm run street -- --name london              measure and build public/streets/<name>.glb
  npm run street -- --name london --measure    print the cross-sections only
"""
import argparse,json,math,subprocess,sys
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import LineString,Point,Polygon,shape
from shapely.ops import linemerge
sys.path.insert(0,str(Path(__file__).resolve().parent))
import prepare as P
from street_buildings import blender
import os
KIT=Path(os.environ.get('CITY_KIT',P.ROOT/'modular-kit-city-builder-starter-kit'))

STREETS={'london':'London Street'}
STEP=.95                                       # station spacing (m)
CAR_LENGTH,CAR_WIDTH=4.5,1.8
GAP={'parallel':.35,'angle':.2,'perpendicular':.2}
END_CLEAR=1.                                   # stop this far short of the cross street's kerb
KERB=.15;KERB_LOW=.02                          # kerb height, and at crossings (a kerb ramp)
# Kit atlas regions (u0, u1, v0, v1) cropped as tileable surfaces, with the metres one crop covers.
ATLAS={'asphalt':((.683,.765,.064,.115),7.71),'concrete':((.299,.383,.362,.448),5.7),'pavers':((.805,.871,.347,.437),2.85)}
PUBLIC=P.ROOT/'public/streets'


def street_line(features,name):
    """The street's centreline, merged from its OSM ways, running west to east."""
    parts=[LineString([(p[0],p[1]) for p in r['points']]) for r in features['roads'] if r.get('name')==name and len(r['points'])>1]
    line=linemerge(parts)
    if line.geom_type!='LineString':line=max(line.geoms,key=lambda g:g.length)
    if line.coords[0][0]>line.coords[-1][0]:line=LineString(line.coords[::-1])
    return line


def frames(line,s0,s1):
    """Stations every STEP metres between chainages s0 and s1: position, unit tangent and left normal."""
    out=[]
    for s in np.arange(s0,s1+1e-6,STEP):
        a=line.interpolate(max(0,s-.5));b=line.interpolate(min(line.length,s+.5));p=line.interpolate(s)
        t=np.array([b.x-a.x,b.y-a.y]);t/=np.linalg.norm(t)
        out.append(dict(s=round(float(s),2),x=p.x,y=p.y,t=t,n=np.array([-t[1],t[0]])))
    return out


def evidence(name,line):
    """Kerb samples per side: (chainage from, chainage to, offset, kind) from parking runs and zebra crossings."""
    data=json.loads((P.ROOT/f'public/inventory/{name}/objects.geojson').read_text())
    import shapely
    local=lambda g:shapely.transform(shape(g),lambda xy:xy-[P.CX,P.CY])
    samples={1:[],-1:[]};runs={1:[],-1:[]}
    def side_of(pt):
        s=line.project(pt);q=line.interpolate(s);a=line.interpolate(max(0,s-.5));b=line.interpolate(min(line.length,s+.5))
        t=np.array([b.x-a.x,b.y-a.y]);n=np.array([-t[1],t[0]])/np.linalg.norm(t)
        return s,float(np.dot([pt.x-q.x,pt.y-q.y],n))
    for f in data['features']:
        p=f['properties']
        if p.get('kind')=='parking-run' and p.get('place') and p.get('road')==STREETS[name]:
            g=local(f['geometry']);s0,o0=side_of(Point(g.coords[0]));s1,o1=side_of(Point(g.coords[-1]))
            off=abs((o0+o1)/2);side=1 if o0+o1>0 else -1;mode=p['mode']
            th=math.radians(90 if mode=='perpendicular' else abs(p.get('angle',0)) if mode=='angle' else 0)
            depth=CAR_LENGTH*math.sin(th)+CAR_WIDTH*math.cos(th)
            kerb=off+depth/2+GAP[mode];lo,hi=sorted((s0,s1));lo-=p.get('pitch',6)/2;hi+=p.get('pitch',6)/2
            samples[side].append((lo,hi,kerb,f"{mode} parking run {p['id']}"))
            runs[side].append(dict(s0=round(lo,2),s1=round(hi,2),inner=round(off-depth/2,2),mode=mode))
        if p.get('kind')=='zebra' and p.get('place') and p.get('road')==STREETS[name]:
            g=local(f['geometry']);c=g.centroid;s,o=side_of(c);half=p['bars']*p['pitch']/2
            w=p['barLength']/2
            for side in (1,-1):samples[side].append((s-w,s+w,round(side*o+half,2),'zebra crossing'))
    return samples,runs


def kerb_profile(stations,samples):
    """Kerb offset at each station: evidence spans hold their offset (zebras, applied last, win where they
    overlap parking); between spans it is interpolated."""
    s=np.array([st['s'] for st in stations]);out=np.full(len(s),np.nan);source=['interpolated']*len(s)
    for lo,hi,off,kind in sorted(samples,key=lambda e:e[3]!='zebra crossing'):
        inside=(s>=lo)&(s<=hi)&(np.isnan(out) if kind!='zebra crossing' else True);out[inside]=off
        for i in np.where(inside)[0]:source[i]=kind
    # Fill gaps linearly between evidence (zebras override parking where they overlap).
    known=~np.isnan(out)
    if known.sum()==0:return out,source
    filled=np.interp(s,s[known],out[known])
    return filled,source


def facades(name):
    """Registered facade lines of modelled buildings, else none (OSM footprints are used as well)."""
    job=P.CACHE/'buildings-london-job.json'
    if not job.exists():return []
    return [LineString([m['facade']['a'],m['facade']['b']]) for m in json.loads(job.read_text())['measured']]


def footpath_edge(st,side,kerb,walls,footprints):
    """Distance from the centreline to the building line along the normal, beyond the kerb (else kerb + 3 m)."""
    o=np.array([st['x'],st['y']]);n=st['n']*side;ray=LineString([o+n*(kerb+.3),o+n*(kerb+7)])
    hits=[ray.intersection(g) for g in walls+footprints if ray.intersects(g)]
    d=[Point(o).distance(h) for h in hits if not h.is_empty]
    return min(d) if d else kerb+3.


def measure(name):
    features=json.loads((P.OUT/'features.json').read_text());line=street_line(features,STREETS[name])
    samples,runs=evidence(name,line)
    bounds=json.loads((P.ROOT/f'public/inventory/{name}/objects.geojson').read_text())['metadata']['bounds']
    # The corridor: the street within the inventory, stopping short of the cross streets' kerbs.
    others=[(LineString([(p[0],p[1]) for p in r['points']]),r['width']) for r in features['roads']
            if r.get('name')!=STREETS[name] and r['kind'] not in('footway','path','steps','track','cycleway','service') and len(r['points'])>1]
    inside=[s for s in np.arange(0,line.length,STEP) if bounds[0]<=line.interpolate(s).x<=bounds[2] and bounds[1]<=line.interpolate(s).y<=bounds[3]]
    clear=[s for s in inside if all(l.distance(line.interpolate(s))>w/2+END_CLEAR+6 for l,w in others)]
    s0,s1=min(clear),max(clear)
    stations=frames(line,s0,s1)
    walls=facades(name);fps=[Polygon(b['ring']) for b in features['buildings'] if Polygon(b['ring']).distance(line)<30]
    sides={}
    for side in (1,-1):
        kerb,source=kerb_profile(stations,samples[side])
        edge=np.array([footpath_edge(st,side,k,walls,fps) for st,k in zip(stations,kerb)])
        # Footpaths never narrower than 1.5 m (a wall in the kit sense would be a building, not a footpath edge).
        edge=np.maximum(edge,kerb+1.5)
        low=[source[i]=='zebra crossing' for i in range(len(stations))]
        sides[side]=dict(kerb=kerb.round(2).tolist(),edge=edge.round(2).tolist(),low=low,source=source,runs=runs[side])
    return dict(name=name,street=STREETS[name],stations=[dict(s=st['s'],x=round(st['x'],3),y=round(st['y'],3),n=[round(float(v),5) for v in st['n']]) for st in stations],
                sides={'left':sides[1],'right':sides[-1]},kerbHeight=KERB,kerbLow=KERB_LOW)


def textures():
    """Tileable surfaces cropped from the kit atlas."""
    out=P.CACHE/'street-textures';out.mkdir(exist_ok=True);Image.MAX_IMAGE_PIXELS=None;atlas=None
    for name,((u0,u1,v0,v1),_) in ATLAS.items():
        path=out/f'{name}.jpg'
        if path.exists():continue
        atlas=atlas or Image.open(KIT/'textures/modularkit.png').convert('RGB');W,H=atlas.size
        crop=atlas.crop((int(u0*W)+2,int((1-v1)*H)+2,int(u1*W)-2,int((1-v0)*H)-2))
        # London Street's pavers are grey (Wikimedia Commons photos); the kit's are pink, so keep only their pattern.
        if name=='pavers':crop=crop.convert('L').convert('RGB')
        crop.save(path,quality=92)
    return out


def report(c):
    for key in ('left','right'):
        sd=c['sides'][key];k=np.array(sd['kerb']);e=np.array(sd['edge'])
        P.log(f"  {key:<5} kerb {k.min():4.1f}-{k.max():4.1f} m (median {np.median(k):4.1f}) · footpath {np.median(e-k):3.1f} m median · "
              f"{sum(sd['low'])} stations at crossings · runs {[(r['mode'],r['s0'],r['s1']) for r in sd['runs']]}")


def main():
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--name',default='london',choices=sorted(STREETS));ap.add_argument('--measure',action='store_true')
    args=ap.parse_args()
    if not (P.ROOT/f'public/inventory/{args.name}/objects.geojson').exists():sys.exit(f'Run npm run inventory -- --name {args.name} first')
    c=measure(args.name);P.log('Street corridor',c['street'],f"{len(c['stations'])} stations, {c['stations'][-1]['s']-c['stations'][0]['s']:.0f} m");report(c)
    if args.measure:return
    PUBLIC.mkdir(parents=True,exist_ok=True);glb=PUBLIC/f'{args.name}.glb';blend=P.ROOT/f'streets/{args.name}.blend';blend.parent.mkdir(exist_ok=True)
    job=dict(corridor=c,textures=str(textures()),tiles={k:v[1] for k,v in ATLAS.items()},glb=str(glb),blend=str(blend))
    path=P.CACHE/f'street-{args.name}-job.json';path.write_text(json.dumps(job))
    r=subprocess.run([blender(),'-b','--factory-startup','--python',str(Path(__file__).with_name('blender_street_corridor.py')),'--',str(path)],capture_output=True,text=True)
    for l in r.stdout.splitlines():
        if l.startswith('STREET'):P.log(' ',l[7:])
    if r.returncode or not glb.exists():sys.stderr.write(r.stdout[-3000:]+r.stderr[-3000:]);sys.exit('Blender failed')
    P.log('  wrote',glb.relative_to(P.ROOT),f'{glb.stat().st_size/1e6:.1f} MB')


if __name__=='__main__':main()
