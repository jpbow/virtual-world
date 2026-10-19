import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('surfaces',Path(__file__).resolve().parents[1]/'tools/surfaces.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.rgb=np.zeros((3,8,8),dtype='uint8');self.rgb[:]=np.array([70,120,45],dtype='uint8')[:,None,None]
        self.ground=np.zeros((8,8),dtype='float32');self.canopy=np.zeros((8,8),dtype='float32')
        self.buildings=np.zeros((8,8),bool);self.roads=np.zeros((8,8),bool);self.urban=np.zeros((8,8),bool);self.water=np.zeros((8,8),bool)
    def classify(self):return s.classify(self.rgb,self.ground,self.canopy,self.buildings,self.roads,self.urban,self.water)
    def test_green_ground_is_grass_and_raised_green_is_canopy(self):
        labels,veg=self.classify();self.assertTrue((labels==0).all());self.assertFalse(veg.any())
        self.canopy[3,3]=8
        labels,veg=self.classify();self.assertEqual(labels[3,3],4);self.assertTrue(veg[3,3])
    def test_mapped_roofs_roads_and_water_override_colour(self):
        self.canopy[:]=8;self.buildings[1,1]=True;self.roads[2,2]=True;self.water[3,3]=True
        labels,veg=self.classify()
        self.assertEqual(labels[1,1],3);self.assertEqual(labels[2,2],3);self.assertEqual(labels[3,3],5)
        self.assertFalse(veg[1,1] or veg[2,2] or veg[3,3])
    def test_dark_green_shadow_does_not_become_paving(self):
        self.rgb[:]=np.array([25,42,20],dtype='uint8')[:,None,None];self.urban[:]=True
        labels,_=self.classify();self.assertTrue((labels==0).all())
    def test_neutral_urban_ground_becomes_paving(self):
        self.rgb[:]=100;self.urban[:]=True
        labels,_=self.classify();self.assertTrue((labels==3).all())
    def test_dry_lawn_and_garden_shadow_in_town_stay_grass(self):
        # Straw-coloured lawn: blue-deficient, so not hard surface.
        self.rgb[:]=np.array([118,112,82],dtype='uint8')[:,None,None];self.urban[:]=True
        self.rgb[:,2:4,2:4]=np.array([40,54,50],dtype='uint8')[:,None,None]
        labels,_=self.classify();self.assertTrue((labels==0).all())
    def test_isolated_grey_pixel_in_garden_stays_grass(self):
        self.urban[:]=True;self.rgb[:,4,4]=110
        labels,_=self.classify();self.assertTrue((labels==0).all())
    def test_shadow_and_tinted_gravel_in_hardstand_become_paving(self):
        self.rgb[:]=120;self.urban[:]=True
        self.rgb[:,2:4,2:4]=np.array([40,54,50],dtype='uint8')[:,None,None]
        self.rgb[:,5,5]=np.array([120,100,80],dtype='uint8')
        labels,_=self.classify();self.assertTrue((labels==3).all())
    def test_roof_footprints_take_surrounding_ground_class(self):
        self.urban[:]=True;self.buildings[3:5,3:5]=True;self.rgb[:,3:5,3:5]=180
        labels,_=self.classify();self.assertTrue((labels==0).all())
        self.rgb[:]=120;self.rgb[:,3:5,3:5]=np.array([150,40,30],dtype='uint8')[:,None,None]
        labels,_=self.classify();self.assertTrue((labels==3).all())
    def test_flat_neutral_hardstanding_is_detected_outside_mapped_roads(self):
        self.rgb[:]=130
        labels,_=self.classify();self.assertTrue((labels==3).all())
    def test_canopy_peaks_are_repeatable_and_exclusions_are_respected(self):
        h=np.zeros((30,30),dtype='float32');h[13,13]=12;eligible=h>3
        first=s.canopy_candidates(h,eligible);self.assertEqual(first,s.canopy_candidates(h,eligible));self.assertEqual(len(first),1)
        self.assertEqual(first[0][2],12);self.assertEqual(s.canopy_candidates(h,np.zeros_like(eligible)),[])

if __name__=='__main__':unittest.main()
