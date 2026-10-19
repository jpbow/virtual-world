import json
import struct
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from install_plant import inspect_glb

def glb(doc):
    raw=json.dumps(doc).encode();raw+=b' '*((-len(raw))%4)
    return struct.pack('<III',0x46546C67,2,20+len(raw))+struct.pack('<II',len(raw),0x4E4F534A)+raw
class PlantImportTests(unittest.TestCase):
    def model(self):return {'accessors':[{'count':6}], 'meshes':[{'primitives':[{'attributes':{'POSITION':0}}]}]}
    def test_external_textures_rejected(self):
        d=self.model();d['images']=[{'uri':'https://example.com/leaf.png'}]
        with self.assertRaisesRegex(ValueError,'embedded'):inspect_glb(glb(d))
    def test_oversized_geometry_rejected(self):
        d=self.model();d['accessors'][0]['count']=900000
        with self.assertRaisesRegex(ValueError,'exceeds'):inspect_glb(glb(d))
    def test_actual_credited_cabbage_tree_is_supported(self):
        p=Path(__file__).resolve().parents[1]/'public/plants/cc-by/cordyline-australis.glb'
        report=inspect_glb(p.read_bytes());self.assertEqual(report['triangles'],85160);self.assertEqual(report['parts'],10)
    def test_invalid_header_rejected(self):
        with self.assertRaises(ValueError):inspect_glb(b'bad')
