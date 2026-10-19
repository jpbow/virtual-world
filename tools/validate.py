#!/usr/bin/env python3
"""Check prepared data for extent, shared edges, geography and valid geometry."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from pyproj import Transformer
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'public/world'

def main():
    m=json.loads((OUT/'manifest.json').read_text())
    f=json.loads((OUT/'features.json').read_text())
    assert m['version']==1 and m['crs']=='EPSG:2193'
    x0,y0,x1,y1=m['bounds'];assert abs(x1-x0-10000)<1e-6 and abs(y1-y0-10000)<1e-6
    assert len(m['tiles'])==100
    tiles={t['id']:np.fromfile(OUT/t['heights'],dtype='<f4').reshape(101,101) for t in m['tiles']}
    edge_checks=0
    for t in m['tiles']:
        g=tiles[t['id']];c,r=t['col'],t['row']
        assert t['missingSamples']==int(np.isnan(g).sum())
        assert (OUT/t['imagery']).stat().st_size>100
        if c<9:np.testing.assert_array_equal(g[:,-1],tiles[f'{c+1}-{r}'][:,0]);edge_checks+=1
        if r<9:np.testing.assert_array_equal(g[-1,:],tiles[f'{c}-{r+1}'][0,:]);edge_checks+=1
    heights=np.fromfile(OUT/m['elevation'],dtype='<f4').reshape(1001,1001)
    transform=Transformer.from_crs(4326,2193,always_xy=True)
    def sample(lon,lat):
        x,y=transform.transform(lon,lat);c=round((x-x0)/10);r=round((y1-y)/10)
        return float(heights[r,c]),(x-m['origin'][0],y-m['origin'][1])
    hill,_=sample(172.7156,-43.5892);assert 250<hill<650,('Port Hills elevation implausible',hill)
    town,_=sample(172.719,-43.602);assert 0<town<180,('Town elevation implausible',town)
    ocean,pt=sample(172.72,-43.62)
    water=unary_union([Polygon(p['ring'],p['holes']) for p in f['water']]);assert water.covers(Point(*pt)) and ocean<=0
    assert 1e6<water.area<9e7
    polys=[]
    for b in f['buildings']:
        p=Polygon(b['ring'],b['holes']);assert p.is_valid and p.area>0
        assert np.isfinite(b['ground']) and 2<=b['roof']['height']<=100
        if b['roof']['kind']=='gable':
            assert b['roof']['source']=='dsm' and b['roof']['slope']<0 and b['roof']['error']<=1.2
        polys.append(p.buffer(.99))
    roads=[__import__('shapely').geometry.LineString([(p[0],p[1]) for p in r['points']]).buffer(r['width']/2+.74) for r in f['roads']]
    exclusions=STRtree(polys+roads)
    for tree in f['trees']:
        x,y,z,h,angle=tree[:5]
        point=Point(x,y);assert not water.covers(point)
        assert len(exclusions.query(point,predicate='intersects'))==0
        assert np.isfinite(z) and .7<=h<=60
    for r in f['roads']:
        assert r['width']>0 and len(r['points'])>=2 and np.isfinite(r['points']).all()
    # Surface tiles encode classes, never aerial RGB. Gutter samples must
    # match neighbouring interior pixels so material blending has no seams.
    assert m['surface']['method'] and sum(m['surface']['areaKm2'].values()) > 99.9
    controls=Image.open(OUT/m['surface']['landscapeControls']);assert controls.mode=='RGBA' and controls.size==(2000,2000)
    relief=Image.open(OUT/m['surface']['terrainRelief']);assert relief.mode=='L' and relief.size in [(2000,2000),(1,1)]
    masks={}
    for t in m['tiles']:
        image=Image.open(OUT/t['surface']);assert image.mode=='RGB' and image.size==(502,502)
        mask=np.array(image);assert np.isin(mask,[0,255]).all()
        assert np.isin(mask.astype('uint16').sum(axis=2),[0,255]).all()
        masks[t['id']]=mask
    for t in m['tiles']:
        c,r=t['col'],t['row'];mask=masks[t['id']]
        if c<9:
            np.testing.assert_array_equal(mask[1:501,501],masks[f'{c+1}-{r}'][1:501,1])
            np.testing.assert_array_equal(mask[1:501,500],masks[f'{c+1}-{r}'][1:501,0])
        if r<9:
            np.testing.assert_array_equal(mask[501,1:501],masks[f'{c}-{r+1}'][1,1:501])
            np.testing.assert_array_equal(mask[500,1:501],masks[f'{c}-{r+1}'][0,1:501])
    assert (OUT/m['surface']['index']).stat().st_size==1000000
    assert sum('roofColor' in b for b in f['buildings'])==m['surface']['roofColors']
    counts=m['stats']['roofSources'];assert sum(counts.values())==len(f['buildings'])
    assert counts['dsm']>0 and len(f['roads'])>0 and len(f['trees'])>0
    print(json.dumps({'result':'pass','extentMeters':10000,'sharedEdgesChecked':edge_checks,
                      'PortHillsHeight':hill,'townHeight':town,'waterAreaKm2':round(water.area/1e6,2),
                      'stats':m['stats'],'missingLandAreaM2':m['missingLandPixels2m']*4},indent=2))

if __name__=='__main__':main()
