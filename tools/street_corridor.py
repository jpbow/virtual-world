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
    corner,road=corners(name,features,line,stations,{'left':sides[1],'right':sides[-1]})
    return dict(name=name,street=STREETS[name],corners=corner,road=road,stations=[dict(s=st['s'],x=round(st['x'],3),y=round(st['y'],3),n=[round(float(v),5) for v in st['n']]) for st in stations],
                sides={'left':sides[1],'right':sides[-1]},kerbHeight=KERB,kerbLow=KERB_LOW)


# --- Junction corners ---------------------------------------------------------------

CORNER_RADIUS=5.;CORNER_REACH=24.;CORNER_FOOTPATH=3.


def offset_polygon(line,left,right,s0,s1,step=1.):
    """The area between offsets `left` (to the left of the line's direction) and `right` (to its right)."""
    L,R=[],[]
    for s in np.arange(s0,s1+1e-6,step):
        a=line.interpolate(max(0,s-.5));b=line.interpolate(min(line.length,s+.5));p=line.interpolate(min(max(s,0),line.length))
        t=np.array([b.x-a.x,b.y-a.y]);t/=np.linalg.norm(t);n=np.array([-t[1],t[0]])
        # Beyond the line's ends, keep going straight.
        base=np.array([p.x,p.y])+t*(s-min(max(s,0),line.length))
        L.append(base+n*left);R.append(base-n*right)
    return Polygon(L+R[::-1]).buffer(0)


def arm_kerbs(arm,zebras,street,width):
    """Kerb offsets (left, right) of a cross-street arm: from a zebra across it (kerb to kerb), else half its width."""
    for road,z in zebras:
        if road==street and z.centroid.distance(arm)<4:
            offs=[]
            for x,y in np.array(z.exterior.coords):
                s=arm.project(Point(x,y));q=arm.interpolate(s);a=arm.interpolate(max(0,s-.5));b=arm.interpolate(min(arm.length,s+.5))
                t=np.array([b.x-a.x,b.y-a.y]);n=np.array([-t[1],t[0]])/np.linalg.norm(t);offs.append(float(np.dot([x-q.x,y-q.y],n)))
            if max(offs)>1 and min(offs)<-1:return max(offs),-min(offs),'zebra crossing'
    return width/2,width/2,'OSM width'


def corners(name,features,line,stations,sides):
    """Kerbed corners where the corridor meets its cross streets: the carriageways (London Street at its end
    kerbs, each cross-street arm at kerbs from its zebra) are merged and their inside corners rounded to
    CORNER_RADIUS; a CORNER_FOOTPATH band around them, clear of the corridor's own footpaths and of buildings,
    is the footpath. Only the corners on the corridor's side of the cross street are built.
    Returns triangles and lines for Blender, per corner."""
    import shapely
    from shapely.ops import unary_union,linemerge
    inv=json.loads((P.ROOT/f'public/inventory/{name}/objects.geojson').read_text())
    zebras=[(f['properties'].get('road'),shapely.transform(shape(f['geometry']),lambda xy:xy-[P.CX,P.CY])) for f in inv['features'] if f['properties'].get('kind')=='zebra']
    # Each zebra as one rectangle: the hull of its bars.
    zebras=[(road,z.convex_hull) for road,z in zebras]
    vehicles=[(r,LineString([(p[0],p[1]) for p in r['points']])) for r in features['roads']
              if r.get('name')!=STREETS[name] and r['kind'] not in('footway','path','steps','track','cycleway','service','pedestrian') and len(r['points'])>1]
    def strip(key,sign,outer):
        sd=sides[key];pts_in=[];pts_out=[]
        for st,k,e in zip(stations,sd['kerb'],sd['edge']):
            o=np.array([st['x'],st['y']]);n=np.array(st['n'])*sign;pts_in.append(o+n*(0 if outer=='lane' else k));pts_out.append(o+n*(k if outer=='lane' else e))
        return Polygon(pts_in+pts_out[::-1]).buffer(0)
    lanes=unary_union([strip('left',1,'lane'),strip('right',-1,'lane')]);paths=unary_union([strip('left',1,'path'),strip('right',-1,'path')])
    walls=unary_union([Polygon(b['ring']).buffer(0) for b in features['buildings'] if Polygon(b['ring']).distance(line)<60])
    out=[];road=[lanes]
    for end in (0,-1):
        st=stations[end];P0=Point(st['x'],st['y']);sign=-1 if end==0 else 1        # toward the junction along the line
        s_end=st['s'];probe=LineString([line.interpolate(s_end),line.interpolate(min(line.length,max(0,s_end+sign*30)))])
        cross=[(r,l) for r,l in vehicles if l.intersects(probe)]
        if not cross:continue
        J=min((probe.intersection(l) for _,l in cross),key=lambda g:g.distance(P0));J=J if J.geom_type=='Point' else J.centroid
        # The corridor's carriageway, from 12 m back to 8 m past the junction, at its end kerbs.
        kL,kR=sides['left']['kerb'][end],sides['right']['kerb'][end]
        sJ=line.project(J);parts=[offset_polygon(line,kL,kR,min(s_end-sign*12,sJ+sign*8),max(s_end-sign*12,sJ+sign*8))]
        names=[]
        for r,l in cross:
            if l.distance(J)>3:continue
            for arm in (l.intersection(J.buffer(30)),):
                for piece in getattr(arm,'geoms',[arm]):
                    if piece.length<2:continue
                    a,b_,how=arm_kerbs(piece,zebras,r.get('name'),r['width']);names.append(f"{r['name']} ({how}: {a:.1f}/{b_:.1f} m)")
                    parts.append(offset_polygon(piece,a,b_,-3,piece.length+3))
        carriage=unary_union(parts).buffer(CORNER_RADIUS,join_style=1).buffer(-CORNER_RADIUS,join_style=1)
        zone=J.buffer(CORNER_REACH);road.append(carriage.intersection(zone))
        # The corridor's side of the junction: toward the end station.
        u=np.array([P0.x-J.x,P0.y-J.y]);u/=np.linalg.norm(u)
        side=Polygon([np.array([J.x,J.y])+u*-1+np.array([-u[1],u[0]])*k for k in (-1e3,1e3)]+[np.array([J.x,J.y])+u*1e3+np.array([-u[1],u[0]])*k for k in (1e3,-1e3)])
        keep=zone.intersection(side)
        foot=carriage.buffer(CORNER_FOOTPATH,join_style=1).difference(carriage).intersection(keep).difference(paths.buffer(.02)).difference(walls)
        gutter=carriage.difference(carriage.buffer(-.3)).intersection(keep).difference(lanes.buffer(.05))
        kerb=carriage.boundary.intersection(keep).difference(lanes.union(paths).buffer(.05))
        skirt=foot.boundary.difference(carriage.buffer(.05))
        tris=lambda g:[[[round(x,3),round(y,3)] for x,y in np.array(t.exterior.coords)[:3]] for t in shapely.constrained_delaunay_triangles(g).geoms] if not g.is_empty else []
        lines=lambda g:[[[round(x,3),round(y,3)] for x,y in l.coords] for l in getattr(linemerge(g) if g.geom_type=='MultiLineString' else g,'geoms',[g]) if l.geom_type=='LineString' and l.length>.2] if not g.is_empty else []
        polys=lambda g:[q for q in getattr(g,'geoms',[g]) if q.geom_type=='Polygon' and q.area>.05]
        kerbs=[]
        for k in lines(kerb):
            # Orient each kerb line with the footpath on its left.
            a,b_=np.array(k[0]),np.array(k[1]);m=(a+b_)/2;t=(b_-a)/np.linalg.norm(b_-a);left=m+np.array([-t[1],t[0]])*.2
            kerbs.append(k if not carriage.contains(Point(*left)) else k[::-1])
        out.append(dict(end='west' if end==0 else 'east',junction=[round(J.x,2),round(J.y,2)],streets=names,
                        footpath=[t for q in polys(foot) for t in tris(q)],gutter=[t for q in polys(gutter) for t in tris(q)],
                        kerbs=kerbs,skirts=lines(skirt),area=round(foot.area,1)))
    road=unary_union(road)
    return out,[[[round(x,2),round(y,2)] for x,y in q.exterior.coords] for q in getattr(road,'geoms',[road]) if q.geom_type=='Polygon']


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
    for k in c['corners']:P.log(f"  {k['end']} corners at {', '.join(k['streets'])}: {k['area']} m² footpath, {len(k['kerbs'])} kerb lines")


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
    # The carriageway outline (kerb to kerb, and the junctions), so the viewer can keep vegetation off the road.
    (PUBLIC/f'{args.name}.json').write_text(json.dumps(dict(street=c['street'],road=c['road'])))
    r=subprocess.run([blender(),'-b','--factory-startup','--python',str(Path(__file__).with_name('blender_street_corridor.py')),'--',str(path)],capture_output=True,text=True)
    for l in r.stdout.splitlines():
        if l.startswith('STREET'):P.log(' ',l[7:])
    if r.returncode or not glb.exists():sys.stderr.write(r.stdout[-3000:]+r.stderr[-3000:]);sys.exit('Blender failed')
    P.log('  wrote',glb.relative_to(P.ROOT),f'{glb.stat().st_size/1e6:.1f} MB')


if __name__=='__main__':main()
