#!/usr/bin/env python3
"""Detailed street-front buildings: OSM footprints + 1 m LiDAR + street-level photo notes, built in Blender.

buildings/<name>.json lists the buildings to model and what the street photos show of each
(storeys, cladding, colours, parapet, windows, verandah, signs) with the photo it came from.
This tool measures everything the photos cannot: the footprint and frontage (OSM), the
footpath level and foundation (1 m DEM), the eave, ridge and parapet heights and roof pitch
(1 m DSM, Christchurch 2024-25 LiDAR), and verandah depth and height (DSM over the footpath).
Blender (tools/blender_street_buildings.py) turns the result into meshes, saved to
buildings/<name>.blend for editing and exported to public/buildings/<name>.glb for the viewer.

  npm run buildings -- --name london              measure, build and export
  npm run buildings -- --name london --measure    print measurements only
  npm run buildings -- --name london --export     re-export buildings/london.blend (keeps hand edits)

Blender is found from $BLENDER, /Applications/Blender.app or PATH.
"""
import argparse,json,math,subprocess,sys
from pathlib import Path
from urllib.parse import urljoin
import numpy as np
from PIL import Image
from shapely.geometry import Polygon,LineString,Point
from shapely import contains_xy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import prepare as P

SPECS=P.ROOT/'buildings';PUBLIC=P.ROOT/'public/buildings'
LIDAR='canterbury/christchurch_2024-2025'          # 1 m DEM/DSM covering the town centre
MARGIN=40                                           # metres of LiDAR beyond the outermost footprint


def blender():
    import os,shutil
    for c in (os.environ.get('BLENDER'),'/Applications/Blender.app/Contents/MacOS/Blender',shutil.which('blender')):
        if c and Path(c).exists():return c
    sys.exit('Blender not found: install it or set BLENDER=/path/to/blender')


# --- 1 m LiDAR -------------------------------------------------------------------

class Grid:
    """A 1 m raster window in local east/north metres (pixel centres at half metres)."""
    def __init__(self,data,left,top):self.data=data;self.left=left;self.top=top

    def __call__(self,x,y):
        """Bilinear sample at local (x, y)."""
        col=np.clip(np.asarray(x,float)-self.left-.5,0,self.data.shape[1]-1);row=np.clip(self.top-np.asarray(y,float)-.5,0,self.data.shape[0]-1)
        c=np.floor(col).astype(int);r=np.floor(row).astype(int);c1=np.minimum(c+1,self.data.shape[1]-1);r1=np.minimum(r+1,self.data.shape[0]-1)
        fx=col-c;fy=row-r;d=self.data
        return d[r,c]*(1-fx)*(1-fy)+d[r,c1]*fx*(1-fy)+d[r1,c]*(1-fx)*fy+d[r1,c1]*fx*fy

    def pixels(self,poly):
        """(x, y, value) of pixel centres inside a polygon."""
        x0,y0,x1,y1=poly.bounds
        xs=np.arange(math.floor(x0-self.left),math.ceil(x1-self.left))+self.left+.5
        ys=self.top-.5-np.arange(math.floor(self.top-y1),math.ceil(self.top-y0))
        gx,gy=np.meshgrid(xs,ys);gx=gx.ravel();gy=gy.ravel();keep=contains_xy(poly,gx,gy)
        return gx[keep],gy[keep],self(gx[keep],gy[keep])


def lidar(name,bounds):
    """1 m DEM and DSM windows for local bounds, read from the LINZ COGs once and cached."""
    import rasterio
    from rasterio.windows import from_bounds
    left,bottom,right,top=(math.floor(bounds[0]),math.floor(bounds[1]),math.ceil(bounds[2]),math.ceil(bounds[3]))
    cache=P.CACHE/f'buildings-{name}-lidar-{left}_{bottom}_{right}_{top}.npz'
    if cache.exists():
        d=np.load(cache);return Grid(d['dem'],left,top),Grid(d['dsm'],left,top)
    out={}
    for product in ('dem','dsm'):
        url=f'https://nz-elevation.s3-ap-southeast-2.amazonaws.com/{LIDAR}/{product}_1m/2193/collection.json'
        grid=np.full((top-bottom,right-left),np.nan,'float32')
        for link in P.cached_json(url)['links']:
            if link['rel']!='item':continue
            item_url=urljoin(url,link['href']);item=P.cached_json(item_url)
            asset=item['assets'].get('visual') or next(a for a in item['assets'].values() if 'tiff' in a.get('type',''))
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR'),rasterio.open(urljoin(item_url,asset['href'])) as src:
                b=src.bounds;L,B,R,T=left+P.CX,bottom+P.CY,right+P.CX,top+P.CY
                if b.left>=R or b.right<=L or b.bottom>=T or b.top<=B:continue
                block=src.read(1,window=from_bounds(L,B,R,T,src.transform),boundless=True,fill_value=-9999).astype('float32')
                valid=block>-1000;grid[valid]=block[valid]
        if np.isnan(grid).any():sys.exit(f'{LIDAR} {product} does not cover {name} buildings')
        out[product]=grid
    np.savez_compressed(cache,**out)
    return Grid(out['dem'],left,top),Grid(out['dsm'],left,top)


# --- Frontage -------------------------------------------------------------------

def street_lines(features,street):
    return [LineString([(p[0],p[1]) for p in r['points']]) for r in features['roads'] if r.get('name')==street and len(r['points'])>1]


def frontage(ring,lines):
    """The footprint edges facing the street: outward-facing, within 1.5 m of the closest edge, at least 1.5 m long.

    Returns ring-ordered edges (start, end, outward normal) merged into one facade line when consecutive."""
    poly=Polygon(ring);ccw=poly.exterior.is_ccw;pts=np.array(poly.exterior.coords)
    edges=[]
    for a,b in zip(pts[:-1],pts[1:]):
        d=b-a;L=float(np.hypot(*d))
        if L<.3:continue
        t=d/L;n=np.array([t[1],-t[0]]) if ccw else np.array([-t[1],t[0]])
        mid=(a+b)/2;near=min(lines,key=lambda l:l.distance(Point(mid)))
        q=near.interpolate(near.project(Point(mid)));to=np.array([q.x,q.y])-mid
        edges.append(dict(a=a,b=b,length=L,normal=n,dist=float(np.hypot(*to)),facing=float(n@to/max(1e-6,np.hypot(*to)))))
    facing=[e for e in edges if e['facing']>.5]
    if not facing:return None
    nearest=min(e['dist'] for e in facing if e['length']>=1.5) if any(e['length']>=1.5 for e in facing) else min(e['dist'] for e in facing)
    front=[e for e in facing if e['dist']<=nearest+1.5]
    # The facade line: from the first to the last front vertex, along the length-weighted mean direction.
    t=sum((e['b']-e['a']) for e in front);t=t/np.hypot(*t);n=sum(e['normal']*e['length'] for e in front);n=n/np.hypot(*n)
    # Snap the facade normal perpendicular to its direction (outward).
    n=np.array([t[1],-t[0]]) if np.dot([t[1],-t[0]],n)>0 else np.array([-t[1],t[0]])
    verts=np.array([v for e in front for v in (e['a'],e['b'])]);along=verts@t;offset=float(np.max(verts@n))
    a=t*along.min()+n*offset;b=t*along.max()+n*offset
    return dict(a=a.tolist(),b=b.tolist(),t=t.tolist(),n=n.tolist(),length=float(along.max()-along.min()),edges=len(front))


# --- Roofs ----------------------------------------------------------------------

def frame(poly,t,n):
    """Facade-aligned rectangle around a polygon: u along the street, v into the building."""
    t=np.asarray(t);n=np.asarray(n);pts=np.array(poly.exterior.coords);u=pts@t;v=-(pts@n)
    return dict(t=t.tolist(),n=n.tolist(),u0=float(u.min()),u1=float(u.max()),v0=float(v.min()),v1=float(v.max()))


def roof_distance(kind,fr,x,y):
    """The rise coordinate of each roof kind: height = eave + slope * distance (gable: ridge parallel to the street;
    gable-end: ridge perpendicular, the gable faces the street; hip: equal pitch on all four sides)."""
    t=np.array(fr['t']);n=np.array(fr['n']);p=np.c_[np.ravel(x),np.ravel(y)];u=p@t;v=-(p@n)
    if kind=='flat':return np.zeros(len(p))
    if kind=='shed':return v-fr['v0']
    across=np.minimum(v-fr['v0'],fr['v1']-v);along=np.minimum(u-fr['u0'],fr['u1']-u)
    return {'gable':across,'gable-end':along,'hip':np.minimum(across,along)}[kind]


def roof_planes(kind,fr,eave,slope):
    """The same roof as planes [a, b, c] (z = a x + b y + c); the roof surface is their minimum."""
    t=np.array(fr['t']);w=-np.array(fr['n'])
    def plane(d,origin):return [slope*d[0],slope*d[1],eave-slope*origin]
    sides=[plane(w,fr['v0']),plane(-w,-fr['v1'])];ends=[plane(t,fr['u0']),plane(-t,-fr['u1'])]
    return {'flat':[[0.,0.,eave]],'shed':sides[:1],'gable':sides,'gable-end':ends,'hip':sides+ends}[kind]


def roof_z(planes,x,y):
    return np.min([a*np.asarray(x)+b*np.asarray(y)+c for a,b,c in planes],axis=0)


def fit_roof(poly,fr,dsm,floor,kinds):
    """Least-squares eave height and pitch of each roof kind on DSM pixels at least 0.8 m inside the polygon.

    Outliers (vents, trees, gaps) are trimmed over three refits. Returns the kinds ranked by RMS error,
    with a small preference for simpler roofs."""
    for inset in (.8,.4,0):                                       # small footprints: closer to the walls
        x,y,z=dsm.pixels(poly.buffer(-inset) if inset else poly)
        keep=z>floor+1.8;x,y,z=x[keep],y[keep],z[keep]
        if len(z)>=6:break
    if len(z)<6:return []
    results=[]
    for kind in kinds:
        d=roof_distance(kind,fr,x,y);use=np.abs(z-np.median(z))<.6 if kind=='flat' else np.ones(len(z),bool)
        for _ in range(3):
            A=np.c_[np.ones(use.sum()),d[use]] if kind!='flat' else np.ones((use.sum(),1))
            coef=np.linalg.lstsq(A,z[use],rcond=None)[0];pred=coef[0]+(coef[1]*d if kind!='flat' else 0)
            res=z-pred;use=np.abs(res)<max(.35,2.5*np.sqrt(np.mean(res[use]**2)))
            if use.sum()<6:break
        slope=float(coef[1]) if kind!='flat' else 0.
        if kind in('gable','hip','gable-end') and not .08<slope<1.6:continue
        if kind=='shed' and not -.6<slope<.6:continue
        rmse=float(np.sqrt(np.mean(res[use]**2)))
        results.append(dict(kind=kind,eave=round(float(coef[0]),2),slope=round(slope,3),rmse=round(rmse,2),ridge=round(float(coef[0]+slope*d.max()-floor),2)))
    return sorted(results,key=lambda r:r['rmse']+{'flat':0,'shed':.05}.get(r['kind'],.1))


# --- Facade registration, parapets and verandahs ----------------------------------------

def stations(f,spacing=1.):
    a=np.array(f['a']);t=np.array(f['t']);L=f['length']
    return a[None]+np.linspace(min(.5,L/3),L-min(.5,L/3),max(3,int(L/spacing)))[:,None]*t[None]


def profile(f,grid,ks):
    """Median height along the facade at offsets k (metres into the building; negative is over the footpath)."""
    s=stations(f);n=np.array(f['n'])
    return np.array([np.median(grid(*(s-k*n[None]).T)) for k in ks])


def roof_edge(f,dsm,floor):
    """Offset of the street-side roof edge from the mapped frontage, for buildings of two storeys or more.

    The 1 m DSM blurs the step from verandah or street up to the roof; its steepest metre is the edge.
    None when the roof is too low to separate from a verandah, or no clear step is found."""
    ks=np.arange(-4,4.01,.25);z=profile(f,dsm,ks)-floor
    if z[(ks>=.5)&(ks<=4)].max()<5.5:return None
    # Only steps whose top clears verandah height (the street-to-verandah step is often as steep).
    rise=np.full(len(ks),-9.);rise[2:-2]=np.where(z[4:]>=4.5,z[4:]-z[:-4],-9)
    i=int(np.argmax(np.where((ks>=-3.5)&(ks<=2.5),rise,-9)))
    return float(ks[i]) if rise[i]>=1. else None


def halfplane(t,n,vmin=None,vmax=None):
    """The region vmin <= v <= vmax of a facade frame (v = -p.n), as a large polygon."""
    t=np.asarray(t);w=-np.asarray(n);lo=-1e4 if vmin is None else vmin;hi=1e4 if vmax is None else vmax
    return Polygon([t*-1e4+w*lo,t*1e4+w*lo,t*1e4+w*hi,t*-1e4+w*hi])


def verandah(f,dsm,dem):
    """A verandah reads as a 2.4-5.2 m high surface over the footpath along most of the facade.

    Depth is the farthest 0.25 m offset still covered at most stations; height is the median top there."""
    if f['length']<2:return None
    s=stations(f);n=np.array(f['n']);depth=0;tops=[]
    for k in np.arange(.5,5.01,.25):
        p=s+k*n[None];top=dsm(*p.T);h=top-dem(*p.T);cover=(h>2.4)&(h<5.2)
        if cover.mean()<.55:break
        depth=float(k);tops.append(float(np.median(h[cover])))
    if depth<1.5:return None
    return dict(depth=round(depth+.15,2),height=round(float(np.median(tops)),2))


# --- Measurement ------------------------------------------------------------------

def facade_line(f,shift):
    """The frontage moved `shift` metres into the building, with left and right as seen from the street."""
    a=np.array(f['a']);b=np.array(f['b']);n=np.array(f['n']);a=a-shift*n;b=b-shift*n
    right=np.array([-n[1],n[0]])
    if (b-a)@right<0:a,b=b,a
    t=(b-a)/np.hypot(*(b-a))
    return dict(a=a.tolist(),b=b.tolist(),t=t.tolist(),n=n.tolist(),length=float(np.hypot(*(b-a))))


def roof_geometry(poly,kind,planes,overhang):
    """Roof faces (one per plane, clipped to where that plane is lowest) and the wall-top line, from roof planes.

    Each wall edge gets extra vertices where it crosses a ridge or hip, so gable ends reach the ridge."""
    roof=poly.buffer(overhang,join_style=2) if overhang>0 else poly
    faces=[]
    for i,(a,b,c) in enumerate(planes):
        region=roof
        for j,(a2,b2,c2) in enumerate(planes):
            if i==j:continue
            # a x + b y + c <= a2 x + b2 y + c2  ->  (a-a2) x + (b-b2) y <= c2-c
            da,db,dc=a-a2,b-b2,c2-c;L=math.hypot(da,db)
            if L<1e-9:
                if dc<0 or (dc==0 and j<i):region=Polygon()
                continue
            nrm=np.array([da,db])/L;off=dc/L;tan=np.array([-nrm[1],nrm[0]])
            region=region.intersection(Polygon([tan*-1e4+nrm*off,tan*1e4+nrm*off,tan*1e4+nrm*(off-2e4),tan*-1e4+nrm*(off-2e4)]))
        for g in getattr(region,'geoms',[region]):
            if g.geom_type=='Polygon' and g.area>.05:
                pts=np.array(g.exterior.coords)[:-1];faces.append([[float(x),float(y),float(a*x+b*y+c)] for x,y in pts])
    ring=np.array(poly.exterior.coords);wall=[]
    for p,q in zip(ring[:-1],ring[1:]):
        ts=[0.]
        for i in range(len(planes)):
            for j in range(i+1,len(planes)):
                (a,b,c),(a2,b2,c2)=planes[i],planes[j];fp=(a-a2)*p[0]+(b-b2)*p[1]+(c-c2);fq=(a-a2)*q[0]+(b-b2)*q[1]+(c-c2)
                if fp*fq<0:ts.append(fp/(fp-fq))
        for t_ in sorted(set(ts)):
            x,y=p+(q-p)*t_;wall.append([float(x),float(y),float(roof_z(planes,x,y))])
    return faces,wall


def heightfield(poly,dsm,spacing=.75):
    """A roof surface straight from the DSM (for roofs no plane model fits), sampled 0.9 m inside the walls
    so the edge does not droop into the 1 m pixels that straddle them, and lightly smoothed."""
    from shapely.ops import nearest_points
    inner=poly.buffer(-.9)
    def z(x,y):
        p=Point(x,y);p=p if inner.contains(p) else nearest_points(inner,p)[0]
        return float(np.mean([dsm(p.x+dx,p.y+dy) for dx,dy in ((0,0),(.5,0),(-.5,0),(0,.5),(0,-.5))]))
    x0,y0,x1,y1=poly.bounds
    pts=[[float(x),float(y),z(x,y)] for x in np.arange(x0+spacing/2,x1,spacing) for y in np.arange(y0+spacing/2,y1,spacing) if poly.buffer(-.3).contains(Point(x,y))]
    ring=[];c=np.array(poly.exterior.coords)
    for p,q in zip(c[:-1],c[1:]):
        k=max(1,int(np.hypot(*(q-p))/spacing))
        for i in range(k):x,y=p+(q-p)*i/k;ring.append([float(x),float(y),z(x,y)])
    return pts,ring


def block(poly,kind,fit,fr,floor,overhang,parapet,dsm=None):
    """Walls, roof faces and parapet of one block (the main building or a lower rear section)."""
    out=dict(ring=[[round(x,3),round(y,3)] for x,y in np.array(poly.exterior.coords)[:-1]],kind=kind,parapet=parapet)
    if kind=='dsm':
        out['points'],out['wall']=heightfield(poly,dsm);out['top']=round(max(p[2] for p in out['points'])-floor,2);return out
    planes=roof_planes(kind,fr,fit['eave'],fit['slope'])
    out['roof'],out['wall']=roof_geometry(poly,kind,planes,overhang)
    if kind=='flat' and parapet:out['inner']=[[round(x,3),round(y,3)] for x,y in np.array(poly.buffer(-.2,join_style=2).exterior.coords)[:-1]]
    out.update(eave=round(fit['eave']-floor,2),slope=fit['slope'],rmse=fit['rmse'],top=round(max(p[2] for p in out['wall'])-floor+(parapet or 0),2))
    return out


PITCHED=('hip','gable')


def measure(name):
    spec=json.loads((SPECS/f'{name}.json').read_text())
    features=json.loads((P.OUT/'features.json').read_text())
    by_id={b['id']:b for b in features['buildings']}
    missing=[b['id'] for b in spec['buildings'] if b['id'] not in by_id]
    if missing:sys.exit(f'Not in features.json: {missing}')
    xs=[p[0] for b in spec['buildings'] for p in by_id[b['id']]['ring']];ys=[p[1] for b in spec['buildings'] for p in by_id[b['id']]['ring']]
    dem,dsm=lidar(name,(min(xs)-MARGIN,min(ys)-MARGIN,max(xs)+MARGIN,max(ys)+MARGIN))
    out=[]
    for b in spec['buildings']:
        feature=by_id[b['id']];poly=Polygon(feature['ring']).buffer(0)
        f=frontage(feature['ring'],street_lines(features,b.get('street','London Street')))
        if f is None:P.log(' ',b['id'],'has no edge facing',b.get('street','London Street'));continue
        t,n=np.array(f['t']),np.array(f['n'])
        floor=float(np.median(dem(*(stations(f)+1.5*n[None]).T)))       # footpath level in front
        kinds=[b['roof']] if b.get('roof') and b['roof']!='dsm' else ['flat','shed','gable','gable-end','hip']
        fr=frame(poly,t,n);fits=fit_roof(poly,fr,dsm,floor,kinds);kind=b.get('roof') or (fits[0]['kind'] if fits else 'flat')
        false_front=bool(b.get('parapet') or b.get('segments'))
        overhang=0. if false_front or kind in('flat','shed','dsm') else b.get('eaves',.3)
        # Register the facade on the LiDAR roof edge (pitched roofs with eaves: the edge is the eave line).
        edge=roof_edge(f,dsm,floor);shift=b.get('facadeShift')
        if shift is None:shift=round(edge+overhang,2) if edge is not None and abs(edge+overhang)>=.5 and not false_front else 0.
        shift=float(np.clip(shift,-3,2.5));v_face=fr['v0']+shift
        main=poly.intersection(halfplane(t,n,vmin=v_face))
        if shift<0:
            ua,ub=sorted([np.dot(f['a'],t),np.dot(f['b'],t)])
            main=main.union(Polygon([t*ua-n*-v_face,t*ub-n*-v_face,t*ub-n*-fr['v0'],t*ua-n*-fr['v0']]).buffer(0))
        main=max(getattr(main,'geoms',[main]),key=lambda g:g.area).buffer(0)
        rear=None
        if kind in PITCHED:
            # A hip or gable spanning less than the footprint depth: the rest is a lower rear section.
            ks=np.arange(shift+1.5,shift+10.01,.25);z=profile(f,dsm,ks);ridge=float(ks[int(np.argmax(z))])
            depth=2*(ridge-shift)-overhang
            if depth<fr['v1']-v_face-1.5:
                rest=poly.intersection(halfplane(t,n,vmin=v_face+depth));main=main.intersection(halfplane(t,n,vmax=v_face+depth))
                main=max(getattr(main,'geoms',[main]),key=lambda g:g.area)
                rest=max(getattr(rest,'geoms',[rest]),key=lambda g:g.area)
                if rest.area>4:rear=rest
        fr=frame(main,t,n);facade=facade_line(f,shift)
        fit=next(iter(fit_roof(main,fr,dsm,floor,[kind])),None) if kind!='dsm' else None
        if kind!='dsm' and fit is None:kind='flat';fit=fit_roof(main,fr,dsm,floor,['flat'])[0]
        parapet=None
        # Side and rear parapets; a taller false front is built separately on the facade.
        if kind=='flat' and not b.get('open'):parapet=min(.4,(b.get('parapet') or {}).get('above',.4))
        # Parts drawn from the DSM (a tower, a gabled wing) with their own roofs, cut from the main block.
        parts=[]
        for part in b.get('parts',[]):
            from shapely.geometry import box as rect
            pp=poly.intersection(rect(*part['box']));pp=max(getattr(pp,'geoms',[pp]),key=lambda g:g.area)
            pf=frame(pp,t,n);pfit=fit_roof(pp,pf,dsm,floor,[part['roof']])
            if pfit:parts.append(block(pp,part['roof'],pfit[0],pf,floor,0.,.25 if part['roof']=='flat' else None));main=main.difference(pp.buffer(.01))
        main=max(getattr(main,'geoms',[main]),key=lambda g:g.area)
        if parts:fr=frame(main,t,n);fit=fit_roof(main,fr,dsm,floor,[kind])[0]
        blocks=[block(main,kind,fit,fr,floor,overhang,parapet,dsm)]+parts
        if rear is not None:
            rf=frame(rear,t,n);rfits=fit_roof(rear,rf,dsm,floor,['flat','shed'])
            if rfits:blocks.append(block(rear,rfits[0]['kind'],rfits[0],rf,floor,0.,.3 if rfits[0]['kind']=='flat' else None))
        # The parapet line: the highest DSM within 0.75 m behind the facade.
        fz=float(np.percentile(np.max([dsm(*(stations(facade)-k*n[None]).T) for k in (.25,.5,.75)],axis=0),80))-floor
        ver=verandah(facade,dsm,dem);posts=[]
        spec_v=b.get('verandah')
        if spec_v:
            ver=dict(depth=spec_v.get('depth',ver['depth'] if ver else 2.4),height=spec_v.get('height',ver['height'] if ver else 3.1),measured=ver is not None)
            if spec_v.get('posts'):
                L=facade['length'];k=max(2,round(L/3.2)+1);a=np.array(facade['a']);tt=np.array(facade['t'])
                for s in np.linspace(.2,L-.2,k):
                    p=a+s*tt+(ver['depth']-.25)*n;posts.append([round(float(p[0]),3),round(float(p[1]),3),round(float(dem(*p)),2)])
        fs=stations(facade);foot=dem(*(fs+1.5*n[None]).T)
        out.append(dict(id=b['id'],name=b.get('name'),floor=round(floor,2),floorLeft=round(float(foot[0]),2),floorRight=round(float(foot[-1]),2),
                        foundation=round(float(min(dem.pixels(poly)[2].min(),foot.min()))-.6,2),facade=facade,shift=shift,edge=edge,
                        blocks=blocks,parapetTop=round(fz,2),verandah=ver,posts=posts,fits=fits[:3],roofColour=feature.get('roofColor')))
    return spec,out


def report(measured):
    for m in measured:
        main=m['blocks'][0];alt=' / '.join(f"{x['kind']} {x['rmse']}" for x in m['fits'][1:])
        roof=f"{main['kind']} eave +{main.get('eave',0):4.1f} pitch {math.degrees(math.atan(abs(main.get('slope',0)))):4.1f}° rms {main.get('rmse','-')}" if main['kind']!='dsm' else 'heightfield'
        rear=f" · rear {m['blocks'][1]['kind']} +{m['blocks'][1]['top']:.1f}" if len(m['blocks'])>1 else ''
        P.log(f"  {m['id']:<18} {str(m['name'])[:26]:<26} facade {m['facade']['length']:5.1f} m shift {m['shift']:+.2f} · {roof} top +{main['top']:4.1f} ({alt}){rear}"
              f" · parapet +{m['parapetTop']:.1f} · verandah {m['verandah']}")


def main():
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--name',default='london');ap.add_argument('--measure',action='store_true',help='print measurements only')
    ap.add_argument('--export',action='store_true',help='export buildings/<name>.blend without rebuilding (keeps hand edits)')
    args=ap.parse_args()
    source=SPECS/f'{args.name}.blend';glb=PUBLIC/f'{args.name}.glb';PUBLIC.mkdir(parents=True,exist_ok=True)
    job={'mode':'export','blend':str(source),'glb':str(glb)}
    if not args.export:
        spec,measured=measure(args.name);report(measured)
        if args.measure:return
        out=P.CACHE/f'buildings-{args.name}-job.json'
        job.update(mode='build',spec=spec,measured=measured,textures=str(textures()))
        out.write_text(json.dumps(job));job={'job':str(out)}
    elif not source.exists():sys.exit(f'{source.relative_to(P.ROOT)} does not exist: build it first')
    P.log('Street buildings',args.name,'build' if not args.export else 'export','->',glb.relative_to(P.ROOT))
    r=subprocess.run([blender(),'-b','--factory-startup','--python',str(Path(__file__).with_name('blender_street_buildings.py')),'--',json.dumps(job)],capture_output=True,text=True)
    for line in r.stdout.splitlines():
        if line.startswith('BUILDINGS'):P.log(' ',line[10:])
    if r.returncode or not glb.exists():
        sys.stderr.write(r.stdout[-4000:]+r.stderr[-4000:]);sys.exit('Blender failed')
    P.log('  wrote',glb.relative_to(P.ROOT),f'{glb.stat().st_size/1e6:.1f} MB')


# --- Material textures --------------------------------------------------------------

TEXTURES={  # name: tile size in metres (the image covers one tile)
    'weatherboard':1.2,'board':1.2,'corrugated':.762,'render':2.0,'tile':.6,'seam':1.6,'timber':1.0}


def gaussian_filter(a,sigma,mode='wrap'):
    """Periodic Gaussian blur (FFT), so the textures tile."""
    k=np.fft.fftfreq(a.shape[0]);g=np.exp(-2*(np.pi*sigma)**2*(k[:,None]**2+k[None]**2))
    return np.real(np.fft.ifft2(np.fft.fft2(a)*g))


def textures():
    """Greyscale albedo and tangent-space normal maps, tiling, drawn at ~430 px/m; colour comes from each material."""
    out=P.CACHE/'buildings-textures';out.mkdir(exist_ok=True)
    rng=np.random.default_rng(7);N=512
    y,x=np.mgrid[0:N,0:N]/N
    for name,size in TEXTURES.items():
        if (out/f'{name}.png').exists() and (out/f'{name}-normal.png').exists():continue
        noise=rng.normal(0,1,(N,N))
        fine=gaussian_filter(noise,1.2,mode='wrap');broad=gaussian_filter(noise,24,mode='wrap');broad/=np.abs(broad).max()+1e-6
        if name=='weatherboard':      # 8 bevel-back boards of 150 mm: each lower edge casts a shadow line
            p=(y*8)%1;h=p*.6;alb=.86+.08*p-.25*(p>.94)+.02*fine
        elif name=='board':           # vertical board and batten, 300 mm
            p=(x*4)%1;bat=(p<.12);h=bat*1.;alb=.85-.12*((p>.12)&(p<.15))+.03*bat+.02*fine
        elif name=='corrugated':      # 76 mm corrugations
            h=.5+.5*np.sin(x*10*2*np.pi);alb=.82+.1*h+.02*fine+.03*broad
        elif name=='render':
            h=gaussian_filter(noise,2,mode='wrap')*.6;alb=.86+.02*fine+.03*broad
        elif name=='tile':            # white tiles 150 x 75 mm, running bond
            row=np.floor(y*8);p=(x*4+.5*(row%2))%1;q=(y*8)%1;grout=(p<.04)|(q<.07);h=1.-grout*1.;alb=.92-.22*grout+.015*fine
        elif name=='seam':            # standing seam pans of 530 mm
            p=(x*3)%1;h=np.exp(-((p-.5)/.015)**2);alb=.84+.06*h+.02*fine+.03*broad
        else:                         # timber
            alb=.8+.06*np.sin(y*40+fine*2)+.03*fine;h=fine*.3
        Image.fromarray((np.clip(alb,0,1)*255).astype('uint8')).save(out/f'{name}.png')
        gy,gx=np.gradient(h*{'corrugated':3,'weatherboard':2.5,'seam':1.5,'tile':1.2,'board':1.5,'render':.2}.get(name,.6))
        nrm=np.dstack([-gx*N/40,gy*N/40,np.ones_like(gx)]);nrm/=np.linalg.norm(nrm,axis=2,keepdims=True)
        Image.fromarray(((nrm*.5+.5)*255).astype('uint8')).save(out/f'{name}-normal.png')
    return out


if __name__=='__main__':main()
