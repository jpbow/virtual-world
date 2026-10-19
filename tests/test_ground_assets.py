import hashlib
import json
from pathlib import Path
import unittest
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]/'public'
class GroundAssetsTests(unittest.TestCase):
    def test_scanned_maps_match_recorded_source_checksums(self):
        sources=json.loads((ROOT/'materials/sources.json').read_text())
        for asset in sources['assets']:
            if 'tileMeters' not in asset:continue
            self.assertGreater(asset['tileMeters'],1);self.assertLess(asset['tileMeters'],5)
            for entry in asset['files'].values():
                file=ROOT/entry['path'];self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),entry['sha256'])
                with Image.open(file) as image:self.assertEqual(image.size,(1024,1024))
