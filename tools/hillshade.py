#!/usr/bin/env python3
"""Cache LINZ's published 1m DEM hillshade over this world (2m sampling)."""
from pathlib import Path
import json
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from rasterio.transform import from_origin
from urllib.parse import urljoin
from prepare import CACHE,OUT,BOUNDS,selected_assets,cached_json,SURVEYS

def fetch_hillshade():
    path=CACHE/'hillshade.tif'
    assets=selected_assets('nz-elevation','new-zealand/new-zealand','dem-hillshade_1m')
    if len(assets)!=1:raise RuntimeError('Expected one verified BX24 hillshade sheet')
    item_url,_=assets[0];item=cached_json(item_url);href=urljoin(item_url,item['assets']['visual']['href'])
    if not path.exists():
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tiff,.tif',GDAL_HTTP_TIMEOUT=90):
            with rasterio.open(href) as src:
                if src.crs.to_epsg()!=2193:raise RuntimeError('Unexpected hillshade CRS')
                data=src.read(1,window=from_bounds(*BOUNDS,src.transform),out_shape=(5000,5000),resampling=Resampling.average,masked=True).filled(0)
        with rasterio.open(path,'w',driver='GTiff',height=5000,width=5000,count=1,dtype='uint8',crs='EPSG:2193',transform=from_origin(BOUNDS[0],BOUNDS[3],2,2),nodata=0,compress='deflate',tiled=True) as dst:dst.write(data,1)
    source=next(iter(SURVEYS.values()));source['role']='terrain-detail hillshade'
    (CACHE/'hillshade-source.json').write_text(json.dumps(source,indent=2)+'\n')
    print('Cached published LINZ hillshade:',path)
if __name__=='__main__':fetch_hillshade()
