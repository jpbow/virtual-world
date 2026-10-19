#!/usr/bin/env python3
"""Cache CC0 Poly Haven ground and road surface scans; no runtime API dependency."""
import hashlib,json
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1];CACHE=ROOT/'.cache/material-assets';OUT=ROOT/'public/materials'
CACHE.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
s=requests.Session();s.headers['User-Agent']='LytteltonWorld/0.1 local asset preparation'
def fetch(meta,path):
    if not path.exists() or hashlib.md5(path.read_bytes()).hexdigest()!=meta['md5']:
        path.parent.mkdir(parents=True,exist_ok=True);r=s.get(meta['url'],timeout=120);r.raise_for_status();data=r.content
        if hashlib.md5(data).hexdigest()!=meta['md5']:raise RuntimeError('Source checksum mismatch')
        path.write_bytes(data)
    return path
report={'license':'CC0-1.0','credit':'Powered by Poly Haven','assets':[]}
# Ground scans keep roughness; road scans need only colour and normal maps.
SURFACES={'grass_ground':['Diffuse','nor_gl','Rough'],'forest_floor':['Diffuse','nor_gl','Rough'],
          'tarred_gravel':['Diffuse','nor_gl'],'asphalt_floor':['Diffuse','nor_gl'],'gravel_road':['Diffuse','nor_gl']}
for slug,channels in SURFACES.items():
    files_path=CACHE/f'{slug}-files.json'
    if not files_path.exists():
        r=s.get(f'https://api.polyhaven.com/files/{slug}',timeout=40);r.raise_for_status();files_path.write_text(json.dumps(r.json()))
    files=json.loads(files_path.read_text());info_path=CACHE/f'{slug}-info.json'
    if not info_path.exists():r=s.get(f'https://api.polyhaven.com/info/{slug}',timeout=40);r.raise_for_status();info_path.write_text(json.dumps(r.json()))
    info=json.loads(info_path.read_text());entry={'id':slug,'source':f'https://polyhaven.com/a/{slug}','authors':info['authors'],'license':'CC0-1.0','files':{}}
    for channel in channels:
        meta=files[channel]['1k']['jpg'];path=OUT/f'{slug}-{channel}.jpg';fetch(meta,path);entry['files'][channel]={'path':str(path.relative_to(ROOT/'public')),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    entry['tileMeters']=info['dimensions'][0]/1000
    report['assets'].append(entry);print('Prepared',slug,flush=True)
(OUT/'sources.json').write_text(json.dumps(report,indent=2)+'\n')
