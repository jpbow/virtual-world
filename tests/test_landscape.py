import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from landscape_evidence import terrain_visibility,landscape_controls,relief_detail

class LandscapeEvidenceTests(unittest.TestCase):
    def test_flat_land_has_open_sky_and_sun(self):
        sky,sun=terrain_visibility(np.zeros((30,30)))
        np.testing.assert_allclose(sky,1);np.testing.assert_allclose(sun,1)
    def test_ridge_occludes_valley_without_darkening_ridge(self):
        h=np.zeros((80,80));h[:,30:35]=800
        sky,sun=terrain_visibility(h,sun=(-1,1,0))
        self.assertLess(sky[40,40],sky[40,32]);self.assertLess(sun[40,40],sun[40,32])
    def test_controls_are_categories_not_photographic_rgb(self):
        rgb=np.zeros((3,100,100),dtype='uint8');rgb[1]=180
        labels=np.zeros((100,100),dtype='uint8');labels[:50]=4
        a=landscape_controls(rgb,labels,np.zeros((100,100)),size=20)
        self.assertTrue((a[:10,:,0]==255).all());self.assertTrue((a[10:,:,0]==0).all())
        self.assertTrue((a[:10,:,1]==0).all());self.assertTrue((a[10:,:,1]==128).all())
        self.assertTrue((a[:,:,2:]==255).all())
    def test_shaded_garden_grass_beside_shrubs_is_growing_only_in_town(self):
        rgb=np.zeros((3,100,100),dtype='uint8');rgb[:]=np.array([120,112,80],dtype='uint8')[:,None,None]
        labels=np.zeros((100,100),dtype='uint8');labels[:,::2]=4
        town=np.zeros((100,100),bool);town[:50]=True
        a=landscape_controls(rgb,labels,np.zeros((100,100)),size=100,gardens=town)
        self.assertTrue((a[10:40,11:89:2,1]==255).all());self.assertTrue((a[60:90,11::2,1]==0).all())
    def test_garden_ground_is_lawn_unless_clearly_dry(self):
        rgb=np.zeros((3,100,100),dtype='uint8');rgb[:]=np.array([110,112,90],dtype='uint8')[:,None,None]
        rgb[:,:,50:]=np.array([150,120,85],dtype='uint8')[:,None,None]
        labels=np.zeros((100,100),dtype='uint8');labels[20:30]=4
        town=np.zeros((100,100),bool);town[:50]=True
        a=landscape_controls(rgb,labels,np.zeros((100,100)),size=100,gardens=town)
        # Lawn continues under garden trees.
        self.assertTrue((a[5:45,5:45,1]==255).all())
        self.assertTrue((a[5:45,55:95,1]==0).all());self.assertTrue((a[55:95,:,1]==0).all())

    def test_constant_hillshade_has_neutral_detail(self):
        a=np.array(relief_detail(np.full((100,100),180,dtype='uint8'),size=20))
        self.assertTrue((a==128).all())
    def test_missing_hillshade_does_not_create_false_shadow(self):
        a=np.array(relief_detail(np.zeros((100,100),dtype='uint8'),size=20))
        self.assertTrue((a==128).all())
