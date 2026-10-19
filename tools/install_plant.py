#!/usr/bin/env python3
"""Validate and install a self-contained, openly licensed static GLB plant."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
ROOT=Path(__file__).resolve().parents[1]

def inspect_glb(data):
    if len(data)<20 or len(data)>40_000_000:raise ValueError('Expected GLB under 40 MB')
    magic,version,total=struct.unpack_from('<III',data)
    if magic!=0x46546C67 or version!=2 or total!=len(data):raise ValueError('Invalid GLB 2 header')
    size,kind=struct.unpack_from('<II',data,12)
    if kind!=0x4E4F534A or 20+size>len(data):raise ValueError('Invalid GLB JSON chunk')
    doc=json.loads(data[20:20+size]);triangles=0;parts=0
    if doc.get('skins') or doc.get('animations'):raise ValueError('Static plant meshes required')
    if any(x in doc.get('extensionsRequired',[]) for x in ['KHR_draco_mesh_compression','KHR_texture_basisu','EXT_meshopt_compression']):raise ValueError('Export without compressed geometry or KTX textures first')
    for resource in doc.get('images',[])+doc.get('buffers',[]):
        if 'uri' in resource and not resource['uri'].startswith('data:'):raise ValueError('All images and buffers must be embedded in the GLB')
    for mesh in doc.get('meshes',[]):
        for p in mesh['primitives']:
            if p.get('mode',4)!=4:raise ValueError('Triangle meshes required')
            a=doc['accessors'][p.get('indices',p['attributes']['POSITION'])]
            triangles+=a['count']//3;parts+=1
    if not 0<parts<=16 or not 0<triangles<=250000:raise ValueError('Model exceeds 16 parts / 250,000 triangles or is empty')
    return{'bytes':len(data),'triangles':triangles,'parts':parts,'sha256':hashlib.sha256(data).hexdigest()}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['file','id','species','author','source','license','kind']:p.add_argument('--'+name,required=True)
    p.add_argument('--min-height',type=float,required=True);p.add_argument('--max-height',type=float,required=True)
    p.add_argument('--density',type=float,default=.025);p.add_argument('--ignore-vertex-colors',action='store_true')
    a=p.parse_args()
    if not re.fullmatch('[a-z0-9-]+',a.id):p.error('id must use lowercase letters, digits and hyphens')
    if a.license not in ['CC-BY-4.0','CC0-1.0']:p.error('Only verified CC BY 4.0 or CC0 files supported by this free-asset installer')
    if a.kind not in ['tree','shrub'] or not 0<a.min_height<=a.max_height<=60 or not 0<a.density<=1:p.error('Invalid plant kind, heights or density')
    if not a.source.startswith('https://'):p.error('Source must be a public HTTPS attribution URL')
    file=Path(a.file).expanduser().resolve();report=inspect_glb(file.read_bytes())
    folder=ROOT/'public/plants';target=folder/'cc-by'/f'{a.id}.glb';target.parent.mkdir(parents=True,exist_ok=True)
    if file!=target.resolve():shutil.copyfile(file,target)
    catalog=json.loads((folder/'catalog.json').read_text());catalog['models']=[m for m in catalog['models'] if m['id']!=a.id]
    catalog['models'].append({'id':a.id,'species':a.species,'url':f'/plants/cc-by/{a.id}.glb','author':a.author,'license':a.license,'source':a.source,'kind':a.kind,'minHeight':a.min_height,'maxHeight':a.max_height,'density':a.density,'ignoreVertexColors':a.ignore_vertex_colors})
    (folder/'catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    (target.with_suffix('.credit.json')).write_text(json.dumps({'title':a.species,'author':a.author,'source':a.source,'license':a.license,'changes':'Runtime origin/height normalization, instancing and scaling; vertex colours may be disabled per catalog. Species placement is inferred, not surveyed.','file':report},indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
