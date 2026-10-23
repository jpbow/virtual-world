#!/usr/bin/env python3
"""Street furniture: a reusable Blender kit, placed wherever evidence records an item.

The kit (tools/blender_street_kit.py) holds one prefab per kind of item: ornamental and park lamps,
litter bins, benches, picnic tables, bollards, bike hoops, drinking fountains, post boxes, a payphone,
bus stop, stop, parking and no-stopping signs, and a flagpole. Placements come from evidence sources,
each mapped to a prefab, and are written to public/street-kit/<name>.json:

- OpenStreetMap nodes (ODbL): amenity=bench / waste_basket / post_box / telephone / drinking_water /
  bicycle_parking, leisure=picnic_table, highway=street_lamp / stop / bus_stop, barrier=bollard,
  man_made=flagpole. Bench `direction` tags set which way benches face; a stop sign stands at the left
  kerb of its approach (traffic keeps left), facing oncoming traffic.
- Christchurch City Council park asset registers (CC BY 4.0): seats, bins (style picks the prefab),
  bollards and light poles.
- Mapillary map features (CC BY-SA 4.0), detected in street-level photos and triangulated: litter bins,
  benches, bike racks, mailboxes, street lights, and stop, give way, parking and no-parking/no-stopping signs.
  Needs a free access token as MAPILLARY_TOKEN (environment or .env.local); without one it is skipped.
  Detections in the carriageway move to the kerb; signs face their mapped `aligned_direction`.
- The street inventory's placed street lights are left to it (tools/street_inventory.py); evidence within
  6 m of one is not placed twice.

Items of one kind from different sources within 2.5 m (4 m for Mapillary's triangulated positions) are the same
item; earlier sources win. Anything else faces the nearest mapped road.

  npm run furniture -- --name london              gather evidence, place, and build the kit if missing
  npm run furniture -- --name london --kit        rebuild the kit from tools/blender_street_kit.py
"""
import argparse,json,math,os,re,subprocess,sys
from pathlib import Path
import numpy as np
import requests
from shapely.geometry import LineString,Point
sys.path.insert(0,str(Path(__file__).resolve().parent))
import prepare as P
from street_buildings import blender

KIT=P.ROOT/'street-kit';PUBLIC=P.ROOT/'public/street-kit'
UA={'User-Agent':'lyttelton-world/0.1 (local 3D prototype)'}
AREAS={'london':(-280,-80,270,220)}                    # local metres: London Street and its corners
OVERPASS=['https://overpass-api.de/api/interpreter','https://overpass.private.coffee/api/interpreter','https://overpass.kumi.systems/api/interpreter']
CCC='https://gis.ccc.govt.nz/server/rest/services/OpenData/{}/query'
CCC_LAYERS={'seat':'Furniture/FeatureServer/19','bin':'Furniture/FeatureServer/2','bollard':'Structure/FeatureServer/10','lightpole':'Furniture/FeatureServer/8'}
SAME=2.5;LAMP_CLEAR=6.
MAPILLARY='https://graph.mapillary.com/map_features'
# Mapillary object values (first match wins) to kit prefabs. Parking signs carry no time limit, so they
# use the plain P sign.
MAPILLARY_KIT=[(r'^object--trash-can$','bin-compass'),(r'^object--bench$','bench'),(r'^object--bike-rack$','bike-hoop'),
               (r'^object--mailbox$','post-box'),(r'^object--phone-booth$','payphone'),(r'^object--street-light$','lamp-ornamental'),
               (r'^regulatory--stop--','sign-stop'),(r'^regulatory--yield--','sign-give-way'),(r'^information--parking--','sign-parking'),
               (r'^regulatory--no-(parking|stopping)','sign-no-stopping')]


def cached(path,fetch):
    if path.exists():return json.loads(path.read_text())
    data=fetch();path.write_text(json.dumps(data));return data


def osm_nodes(name,bounds):
    lon0,lat0=P.INVERSE.transform(bounds[0]+P.CX,bounds[1]+P.CY);lon1,lat1=P.INVERSE.transform(bounds[2]+P.CX,bounds[3]+P.CY);bb=f'{lat0},{lon0},{lat1},{lon1}'
    keys=['highway','amenity','leisure','barrier','man_made']
    query=f'[out:json][timeout:60];({"".join(f"node({bb})[{k}];" for k in keys)});out;'
    def fetch():
        for endpoint in OVERPASS:
            try:
                r=requests.post(endpoint,data={'data':query},headers={**UA,'Accept':'application/json'},timeout=90)
                if r.ok and r.text.lstrip().startswith('{'):return r.json()
            except requests.RequestException:pass
        sys.exit('Overpass unavailable: try again later')
    return cached(P.CACHE/f'street-furniture-{name}-osm.json',fetch)['elements']


def ccc_assets(name,bounds):
    env=f'{bounds[0]+P.CX},{bounds[1]+P.CY},{bounds[2]+P.CX},{bounds[3]+P.CY}';out={}
    for kind,layer in CCC_LAYERS.items():
        def fetch(layer=layer):
            r=requests.get(CCC.format(layer),params=dict(geometry=env,geometryType='esriGeometryEnvelope',inSR=2193,outSR=2193,spatialRel='esriSpatialRelIntersects',
                                                          outFields='*',f='json'),headers=UA,timeout=60)
            r.raise_for_status();return r.json()
        out[kind]=cached(P.CACHE/f'street-furniture-{name}-ccc-{kind}.json',fetch).get('features',[])
    return out


def mapillary_token():
    if os.environ.get('MAPILLARY_TOKEN'):return os.environ['MAPILLARY_TOKEN'].strip()
    env=P.ROOT/'.env.local'
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith('MAPILLARY_TOKEN=') and line.split('=',1)[1].strip():return line.split('=',1)[1].strip().strip('"\'')
    return None


def mapillary_features(name,bounds):
    """Point features and traffic signs Mapillary has detected and triangulated in the area (cached)."""
    token=mapillary_token();path=P.CACHE/f'street-furniture-{name}-mapillary.json'
    if not token and not path.exists():P.log('  Mapillary skipped: set MAPILLARY_TOKEN in .env.local');return []
    lon0,lat0=P.INVERSE.transform(bounds[0]+P.CX,bounds[1]+P.CY);lon1,lat1=P.INVERSE.transform(bounds[2]+P.CX,bounds[3]+P.CY)
    def fetch():
        out=[];url=MAPILLARY;params=dict(fields='id,object_value,object_type,geometry,aligned_direction,first_seen_at,last_seen_at',bbox=f'{lon0},{lat0},{lon1},{lat1}',limit=2000)
        while url:
            r=requests.get(url,params=params,headers={**UA,'Authorization':f'OAuth {token}'},timeout=60)
            if not r.ok:sys.exit(f'Mapillary request failed ({r.status_code}): check MAPILLARY_TOKEN')
            d=r.json();out+=d.get('data',[]);url=d.get('paging',{}).get('next');params=None
        return out
    return cached(path,fetch)


def bearing(dx,dy):return math.degrees(math.atan2(dx,dy))%360


class Roads:
    def __init__(self,features):
        self.roads=[(r,LineString([(p[0],p[1]) for p in r['points']])) for r in features['roads'] if len(r['points'])>1 and r['kind'] not in('footway','path','steps','track','cycleway','pedestrian')]

    def nearest(self,x,y):
        return min(self.roads,key=lambda rl:rl[1].distance(Point(x,y)))

    def facing(self,x,y):
        """Compass bearing from (x, y) toward the nearest road."""
        _,line=self.nearest(x,y);q=line.interpolate(line.project(Point(x,y)))
        return bearing(q.x-x,q.y-y) if Point(x,y).distance(q)>.05 else 0.

    def kerb_sign(self,x,y,direction):
        """A sign for traffic approaching a node on a road: at the left kerb, facing the traffic."""
        road,line=self.nearest(x,y);s=line.project(Point(x,y));a=line.interpolate(max(0,s-1));b=line.interpolate(min(line.length,s+1))
        t=np.array([b.x-a.x,b.y-a.y]);t/=np.linalg.norm(t)
        if direction=='backward':t=-t
        left=np.array([-t[1],t[0]]);q=line.interpolate(s);p=np.array([q.x,q.y])+left*(road['width']/2+.6)
        return float(p[0]),float(p[1]),bearing(-t[0],-t[1])

    def to_kerb(self,x,y):
        """A footpath item detected in the carriageway, moved out to 0.6 m beyond the kerb."""
        road,line=self.nearest(x,y);q=line.interpolate(line.project(Point(x,y)));d=Point(x,y).distance(q);half=road['width']/2
        if d>=half+.3:return x,y
        if d<.05:return x,y
        k=(half+.6)/d;return q.x+(x-q.x)*k,q.y+(y-q.y)*k


def gather(name):
    bounds=AREAS[name];features=json.loads((P.OUT/'features.json').read_text());roads=Roads(features)
    items=[]
    def add(kind,x,y,source,licence,ref,heading=None,**extra):
        items.append(dict(model=kind,x=round(x,2),y=round(y,2),heading=round(roads.facing(x,y) if heading is None else heading,1),source=source,licence=licence,ref=ref,**extra))
    for e in osm_nodes(name,bounds):
        t=e.get('tags',{});x,y=P.FORWARD.transform(e['lon'],e['lat']);x-=P.CX;y-=P.CY;ref=f"node/{e['id']}";osm=('OpenStreetMap','ODbL-1.0')
        try:direction=float(t.get('direction','x'))
        except ValueError:direction=None
        a=t.get('amenity');h=t.get('highway')
        if a=='bench':add('bench-backless' if t.get('backrest')=='no' else 'bench',x,y,*osm,ref,direction)
        elif a=='waste_basket':add('bin-compass',x,y,*osm,ref)
        elif a=='post_box':add('post-box-dx' if 'DX' in t.get('operator','') else 'post-box',x,y,*osm,ref)
        elif a=='telephone':add('payphone',x,y,*osm,ref)
        elif a=='drinking_water':add('drinking-fountain',x,y,*osm,ref)
        elif a=='bicycle_parking':add('bike-hoop',x,y,*osm,ref)
        elif t.get('leisure')=='picnic_table':add('picnic-table',x,y,*osm,ref)
        elif t.get('barrier')=='bollard':add('bollard',x,y,*osm,ref)
        elif t.get('man_made')=='flagpole':add('flagpole',x,y,*osm,ref)
        elif h=='street_lamp':add('lamp-ornamental' if t.get('support')=='ornamental' else 'lamp-park',x,y,*osm,ref)
        elif h=='bus_stop':add('bus-stop',x,y,*osm,ref)
        elif h=='stop':sx,sy,hd=roads.kerb_sign(x,y,t.get('direction','forward'));add('sign-stop',sx,sy,*osm,ref,hd)
    ccc=('Christchurch City Council','CC-BY-4.0')
    for kind,feats in ccc_assets(name,bounds).items():
        for f in feats:
            a=f['attributes'];g=f['geometry'];x,y=g['x']-P.CX,g['y']-P.CY
            if a.get('ServiceStatus') not in (None,'In Service'):continue
            if kind=='seat':add('bench',x,y,*ccc,f"Seat {a['SeatID']}",length=a.get('Length'))
            elif kind=='bin':add('bin-bigbelly' if a.get('Style')=='Big Belly' else 'bin-compass',x,y,*ccc,f"Bin {a['BinID']}")
            elif kind=='bollard':add('bollard',x,y,*ccc,f"Bollard {a['BollardID']}")
            elif kind=='lightpole':add('lamp-park',x,y,*ccc,f"LightPole {a['LightPoleID']}",height=a.get('Height'))
    mly=('Mapillary','CC-BY-SA-4.0');unmatched={}
    for f in mapillary_features(name,bounds):
        value=f.get('object_value','');model=next((m for pattern,m in MAPILLARY_KIT if re.search(pattern,value)),None)
        if not model:unmatched[value]=unmatched.get(value,0)+1;continue
        lon,lat=f['geometry']['coordinates'][:2];x,y=P.FORWARD.transform(lon,lat);x,y=roads.to_kerb(x-P.CX,y-P.CY)
        heading=f.get('aligned_direction') if model.startswith('sign') and f.get('aligned_direction') is not None else None
        add(model,x,y,*mly,f"map_feature/{f['id']}",heading,tolerance=4.,lastSeen=f.get('last_seen_at'))
    if unmatched:P.log('  Mapillary values without a prefab:',', '.join(f'{v} ({n})' for v,n in sorted(unmatched.items(),key=lambda kv:-kv[1])))
    # One item per kind within SAME metres (OSM, then the council register, then Mapillary); lamps clear of inventory lamps.
    lamps=[]
    inventory=P.ROOT/f'public/inventory/{name}/objects.geojson'
    if inventory.exists():
        lamps=[(f['properties']['x'],f['properties']['y']) for f in json.loads(inventory.read_text())['features'] if f['properties'].get('kind')=='streetlight' and f['properties'].get('place')]
    out=[]
    for it in items:
        if it['model'].startswith('lamp') and any(math.hypot(it['x']-x,it['y']-y)<LAMP_CLEAR for x,y in lamps):continue
        tol=max(SAME,it.pop('tolerance',SAME))
        dup=next((o for o in out if o['model']==it['model'] and math.hypot(o['x']-it['x'],o['y']-it['y'])<tol),None)
        if dup:dup.setdefault('alsoIn',[]).append(f"{it['source']} {it['ref']}");continue
        out.append(it)
    return out


def build_kit(rebuild):
    KIT.mkdir(exist_ok=True);PUBLIC.mkdir(parents=True,exist_ok=True)
    blend=KIT/'street-kit.blend';glb=PUBLIC/'street-kit.glb'
    if glb.exists() and blend.exists() and not rebuild:return glb
    job=dict(mode='build' if rebuild or not blend.exists() else 'export',blend=str(blend),glb=str(glb))
    r=subprocess.run([blender(),'-b','--factory-startup','--python',str(Path(__file__).with_name('blender_street_kit.py')),'--',json.dumps(job)],capture_output=True,text=True)
    for line in r.stdout.splitlines():
        if line.startswith('KIT'):P.log(' ',line[4:])
    if r.returncode or not glb.exists():sys.stderr.write(r.stdout[-3000:]+r.stderr[-3000:]);sys.exit('Blender failed')
    return glb


def main():
    ap=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--name',default='london',choices=sorted(AREAS));ap.add_argument('--kit',action='store_true',help='rebuild the kit .blend from the script')
    args=ap.parse_args()
    glb=build_kit(args.kit)
    placements=gather(args.name)
    from collections import Counter
    for (model,source),n in sorted(Counter((p['model'],p['source']) for p in placements).items()):P.log(f'  {model:<20} {n:3d}  {source}')
    out=PUBLIC/f'{args.name}.json'
    out.write_text(json.dumps(dict(name=args.name,kit='street-kit.glb',sources={'OpenStreetMap':'© OpenStreetMap contributors, ODbL','Mapillary':'Mapillary map features, CC BY-SA 4.0',
                    'Christchurch City Council':'Christchurch City Council park asset registers, CC BY 4.0'},placements=placements),indent=1))
    P.log('Street furniture',args.name,len(placements),'placements ->',out.relative_to(P.ROOT),'· kit',glb.relative_to(P.ROOT))


if __name__=='__main__':main()
