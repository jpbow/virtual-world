import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('surfaces',Path(__file__).resolve().parents[1]/'tools/surfaces.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

class VegetationCoverageTests(unittest.TestCase):
    def test_continuous_canopy_is_filled_between_detected_peaks(self):
        heights=np.full((100,100),8.,dtype='float32');eligible=np.ones((100,100),bool)
        points,coverage=s.populate_canopy(heights,eligible)
        self.assertGreaterEqual(coverage[eligible].mean(),.9)
        self.assertGreater(len(points),20)
        self.assertEqual(points,s.populate_canopy(heights,eligible)[0])
    def test_excluded_water_and_buildings_receive_no_centres(self):
        heights=np.full((80,80),12.,dtype='float32');eligible=np.zeros((80,80),bool);eligible[20:60,20:60]=True
        points,coverage=s.populate_canopy(heights,eligible)
        self.assertTrue(all(eligible[int(p[3]),int(p[4])] for p in points))
    def test_low_scrub_and_shaded_woodland_are_retained(self):
        rgb=np.full((3,8,8),32,dtype='uint8');ground=np.zeros((8,8),dtype='float32');height=np.full((8,8),1.5,dtype='float32');empty=np.zeros((8,8),bool)
        labels,veg=s.classify(rgb,ground,height,empty,empty,empty,empty,woodland=np.ones((8,8),bool))
        self.assertTrue(veg.all());self.assertTrue((labels==4).all())

if __name__=='__main__':unittest.main()
