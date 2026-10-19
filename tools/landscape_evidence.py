"""Non-photographic landscape controls from classes and measured elevation."""
import numpy as np
from PIL import Image

def terrain_visibility(ground,spacing=20,sun=(-5000,8000,4000)):
    """Horizon-based sky openness and fixed-sun visibility; no image pixels."""
    h=np.where(np.isfinite(ground)&(ground>-1000),ground,0).astype('float32')
    rows,cols=np.indices(h.shape);openness=np.zeros(h.shape,dtype='float32')
    directions=[(-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1)]
    for dr,dc in directions:
        horizon=np.zeros_like(h)
        for distance in [1,2,4,8,16,32]:
            rr=rows+dr*distance;cc=cols+dc*distance
            valid=(rr>=0)&(rr<h.shape[0])&(cc>=0)&(cc<h.shape[1])
            rise=h[np.clip(rr,0,h.shape[0]-1),np.clip(cc,0,h.shape[1]-1)]-h
            horizon=np.maximum(horizon,np.where(valid,rise/(distance*spacing*np.hypot(dr,dc)),0))
        openness+=1/(1+horizon*horizon)/len(directions)
    sx,sy,sn=sun;horizontal=np.hypot(sx,sn);sun_slope=sy/horizontal
    horizon=np.zeros_like(h)
    for distance in [1,2,4,8,16,32,64]:
        rr=rows+int(round(-sn/horizontal*distance));cc=cols+int(round(sx/horizontal*distance))
        valid=(rr>=0)&(rr<h.shape[0])&(cc>=0)&(cc<h.shape[1])
        rise=h[np.clip(rr,0,h.shape[0]-1),np.clip(cc,0,h.shape[1]-1)]-h
        horizon=np.maximum(horizon,np.where(valid,rise/(distance*spacing),0))
    sunlight=np.clip((sun_slope-horizon)*12+.5,0,1)
    return openness,sunlight

def landscape_controls(rgb,labels,ground,size=2000,gardens=None):
    """RGBA = canopy occupancy, grass condition, sky openness, sun visibility.

    Grass condition: 0 dry pasture, 128 green growing pasture, 255 garden lawn.

    The first two channels are categorical; the last two derive only from DEM.
    No photographic colour or photograph-shaped lighting survives.
    """
    r,g,b=rgb.astype('float32')
    strong=(g>r*1.08)&(g>b*1.14)&((2*g-r-b)>15)
    growing=strong&(labels==0)
    lawn=np.zeros_like(growing)
    if gardens is not None:
        # Grass around houses is mown garden lawn, not dry pasture, unless
        # the photograph is clearly brown. Shade and survey season make many
        # lawns read olive or grey, so greenness alone misses them.
        dry=(r>g*1.12)&(r>b*1.3)
        # Garden trees and shrubs stand over lawn too, not forest litter.
        lawn=gardens&((labels==0)|(labels==4))&~dry
    channels=[]
    condition=np.where(lawn,255,np.where(growing,128,0)).astype('uint8')
    for a in [(labels==4).astype('uint8')*255,condition]:
        channels.append(np.array(Image.fromarray(a).resize((size,size),Image.Resampling.BOX)))
    sky,sun=terrain_visibility(ground[5::10,5::10],20)
    for a in [sky,sun]:
        channels.append(np.array(Image.fromarray(np.round(a*255).astype('uint8')).resize((size,size),Image.Resampling.BILINEAR)))
    return np.stack(channels,axis=-1)

def relief_detail(hillshade,size=2000):
    """Keep only sub-mesh relief; remove broad fixed-direction hillshade."""
    from PIL import ImageFilter
    image=Image.fromarray(hillshade.astype('uint8'))
    broad=np.array(image.filter(ImageFilter.GaussianBlur(6))).astype('float32')
    ratio=(hillshade.astype('float32')+24)/(broad+24)
    detail=np.where(hillshade>0,np.clip(ratio,.65,1.35),1)
    encoded=np.round(128+(detail-1)*300).astype('uint8')
    return Image.fromarray(encoded).resize((size,size),Image.Resampling.BOX)

def write_relief(cache,out,manifest):
    import json
    import rasterio
    if (cache/'hillshade.tif').exists():
        with rasterio.open(cache/'hillshade.tif') as src:hillshade=src.read(1)
        relief_detail(hillshade).save(out/'terrain-relief.png',optimize=True)
        source=json.loads((cache/'hillshade-source.json').read_text())
        if not any(s['url']==source['url'] for s in manifest['sources']):manifest['sources'].append(source)
        method='LINZ published 1m DEM hillshade, sampled at 2m; local ratio removes broad fixed-direction lighting, resampled to 5m'
    else:
        Image.new('L',(1,1),128).save(out/'terrain-relief.png')
        method='Neutral detail; optional published hillshade has not been cached'
    manifest['surface']['terrainRelief']='terrain-relief.png'
    manifest['surface']['reliefMethod']=method
