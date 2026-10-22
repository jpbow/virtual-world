"""Facade specs for buildings with no photo notes, from their type and their LiDAR measurements.

The type comes from OSM tags (building=*, shop/amenity/office on the building), else from the footprint:
round footprints are tanks, small ones outbuildings, large or port-side ones industrial, the rest houses.
Storeys come from the measured eave height above the building's own ground. Window and door counts follow
the measured facade length. Cladding follows the type; wall colours are drawn, per building, from a
palette of colours common in Lyttelton. Everything here is typical, not observed, and the evidence line
says so; measured roofs, heights and footprints are unchanged.
"""
import hashlib,math

HOUSE={'house','detached','residential','semidetached_house','terrace','bungalow','apartments','dormitory','farm'}
OUTBUILDING={'garage','garages','shed','carport','hut','cabin','greenhouse','kiosk','toilets','bunker'}
SHOP={'commercial','retail','office','hotel','supermarket'}
INDUSTRIAL={'industrial','warehouse','service','utility','storage_tank','manufacture','hangar','transportation','train_station'}
CIVIC={'civic','school','church','chapel','public','hospital','pavilion','clubhouse','government','fire_station','sports_centre','community_centre'}
BUSINESS_AMENITY={'cafe','restaurant','pub','bar','fast_food','bank','pharmacy','library','post_office','marketplace','ice_cream','theatre','arts_centre'}

# Lyttelton's painted weatherboards: (colour, weight). Mostly whites and creams, with its well-known
# blues, greens, yellows and reds.
HOUSE_PALETTE=[('#f2efe6',24),('#e9dfc0',14),('#e6d38a',7),('#a9c1d6',9),('#7f9fb8',5),('#b9cdb0',8),('#7e9c8a',5),
               ('#d8a49a',5),('#c97a5c',3),('#9aa1a6',8),('#4a5157',6),('#3a3f44',3),('#e8e2d6',3)]
SHED_PALETTE=[('#9a9fa3',30),('#6f7a72',15),('#a24b3c',10),('#e9e6de',15),('#4e5a63',15),('#c7c2b4',15)]
INDUSTRIAL_PALETTE=[('#d9dcdc',35),('#a9b1b5',25),('#7d8b95',15),('#3f5d78',10),('#e7e3d6',15)]
SHOP_PALETTE=[('#efede6',35),('#e3dccb',20),('#b9c3c2',15),('#d8cfae',15),('#3b3f43',8),('#8fa7b0',7)]
CONTAINER_PALETTE=[('#a2432f',30),('#2f5a8a',25),('#4b6b3a',20),('#c9a13a',15),('#7a7f84',10)]
DOOR_COLOURS=['#7a3a2a','#2f4a35','#1f3350','#e9e9e6','#c8262c','#3a3f44','#e8c440']


def _pick(palette,seed):
    total=sum(w for _,w in palette);r=seed%total
    for colour,w in palette:
        if r<w:return colour
        r-=w
    return palette[0][0]


def _seed(osm_id,salt=''):return int(hashlib.sha1((osm_id+salt).encode()).hexdigest()[:8],16)


def classify(tags,poly,centroid,port):
    """(type, reason) for a building from its OSM tags and footprint."""
    b=tags.get('building','yes')
    if b in('demolished','construction','ruins','no'):return None,f'building={b}'
    if b=='roof':return 'canopy','building=roof'
    if b=='container':return 'container','building=container'
    if b in HOUSE:return 'house',f'building={b}'
    if b in OUTBUILDING:return 'outbuilding',f'building={b}'
    if b in INDUSTRIAL:return 'industrial',f'building={b}'
    if b in CIVIC or tags.get('amenity') in('school','place_of_worship','townhall','community_centre','fire_station','police'):return 'civic',f"building={b}"
    if b in SHOP or 'shop' in tags or 'office' in tags or tags.get('amenity') in BUSINESS_AMENITY or tags.get('tourism') in('hotel','motel','hostel','museum'):
        key=next((k for k in ('shop','office','amenity','tourism') if k in tags),None)
        return 'shop',f"building={b}"+(f", {key}={tags[key]}" if key else '')
    area=poly.area;round_=4*math.pi*area/max(1e-6,poly.length**2)
    if round_>.88 and area>40:return 'tank','round footprint'
    if area<28:return 'outbuilding',f'small footprint ({area:.0f} m²)'
    if port and area>120:return 'industrial','port land, large footprint'
    if area>650:return 'industrial',f'large footprint ({area:.0f} m²)'
    if port:return 'outbuilding','port land'
    return 'house','unspecified building, residential area'


def spec(osm_id,kind,reason,m,tags):
    """A facade spec for the builder from the type and the measurements m (see street_buildings.measure_one)."""
    s=_seed(osm_id);L=m['facade']['length'];main=m['blocks'][0]
    eave=m['floor']+main.get('eave',main.get('top',3))-m['groundInside']
    storeys=1 if eave<4.6 else 2 if eave<7.6 else 3
    pitched=main['kind'] in('hip','gable','gable-end')
    address=f"{tags['addr:housenumber']} {tags.get('addr:street','')}".strip() if tags.get('addr:housenumber') else None
    out=dict(id=osm_id,auto=True,type=kind,storeys=min(storeys,2) if kind!='civic' else storeys,name=tags.get('name') or address)
    door=lambda:DOOR_COLOURS[s%len(DOOR_COLOURS)]
    windows=max(1,round((L-1.2)/2.7))
    if kind=='house':
        cladding='board' if s%10==0 else 'weatherboard';colour=_pick(HOUSE_PALETTE,s)
        trim='#f4f3ee' if colour not in('#f2efe6','#e8e2d6','#e9dfc0') or s%3 else '#3a3f44'
        out.update(wall=dict(cladding=cladding,colour=colour),trim=trim,eaves=.35 if pitched else 0,
                   lower=dict(windows=windows,type='sash' if s%3==0 else 'single' if s%3==1 else 'pair',door=.5 if L<7 else (.28 if s%2 else .72),doorColour=door()))
        if out['storeys']>=2:out['upper']=dict(windows=windows,type=out['lower']['type'])
    elif kind=='outbuilding':
        out.update(wall=dict(cladding='corrugated' if s%2 else 'weatherboard',colour=_pick(SHED_PALETTE,s)),trim='#e9e9e6',eaves=.15 if pitched else 0,storeys=1)
        # A garage door where the tags say garage, or the shed faces a road within 12 m.
        if L>=3.2 and (reason.startswith(('building=garage','building=carport')) or m.get('roadDistance',99)<12):
            out['garages']=[dict(at=.5,width=min(2.6,L-.7),height=2.1,colour=_pick(SHED_PALETTE,s+1))]
        else:out['lower']=dict(door=.5,doorColour=door())
    elif kind=='shop':
        out.update(wall=dict(cladding='render' if s%2 else 'weatherboard',colour=_pick(SHOP_PALETTE,s)),trim='#e6e5df',eaves=.3 if pitched else 0,
                   shopfront=dict(bays=max(1,round(L/2.6)),door=.5,frame='#3a3d40',stall='#d8d6d0'))
        if not pitched:out['parapet']=dict(shape='flat',above=.5)
        if m.get('verandah'):out['verandah']=dict(type='flat',posts=False,fascia='#2d2f31',fasciaHeight=.35)
        if out['storeys']>=2:out['upper']=dict(windows=windows,type='single')
    elif kind=='industrial':
        out.update(wall=dict(cladding='corrugated',colour=_pick(INDUSTRIAL_PALETTE,s)),trim='#8a8f93',eaves=.2 if pitched else 0,storeys=1)
        h=max(2.4,min(4.5,eave-.8));n=max(1,min(4,int(L/11)))
        out['garages']=[dict(at=(i+.5)/n,width=min(4.,L/n-1.2),height=h,colour='#c9cdcf') for i in range(n)] if L>=4 else []
        out['lower']=dict(door=.06 if L>8 else .5,doorColour='#3a3f44')
    elif kind=='civic':
        out.update(wall=dict(cladding='render' if s%2 else 'weatherboard',colour=_pick(SHOP_PALETTE,s+3)),trim='#f2f2ee',eaves=.35 if pitched else 0,
                   lower=dict(windows=windows,type='pair',door=.5,doorColour=door()))
        if out['storeys']>=2:out['upper']=dict(windows=windows,type='pair')
    elif kind=='tank':
        out.update(wall=dict(cladding='render',colour='#ecebe6'),trim='#d8d7d2',storeys=1,tank=True)
    elif kind=='container':
        out.update(wall=dict(cladding='corrugated',colour=_pick(CONTAINER_PALETTE,s)),trim='#5a5e62',storeys=1)
    elif kind=='canopy':
        out.update(open=True,trim='#6b6f73')
    out['evidence']=(f"Type: {kind} ({reason}). Roof, heights and footprint from LINZ 1 m LiDAR and OSM; "
                     f"{out['storeys']} storey{'s' if out['storeys']>1 else ''} from the eave height. Facade layout and colours are typical for the type, not observed.")
    return out
