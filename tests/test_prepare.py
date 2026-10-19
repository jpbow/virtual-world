import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from shapely.geometry import Polygon,Point

spec=importlib.util.spec_from_file_location('prepare',Path(__file__).resolve().parents[1]/'tools/prepare.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class SamplingTests(unittest.TestCase):
    def test_pixel_centers_and_interpolation(self):
        g=np.array([[10.,20.],[30.,40.]])
        self.assertEqual(p.sample_grid(g,-4999,4999),10)
        self.assertEqual(p.sample_grid(g,-4998,4998),25)
        self.assertEqual(p.sample_grid(g,-4997,4997),40)
    def test_no_data_remains_missing(self):
        g=np.array([[np.nan,2.],[3.,4.]])
        self.assertTrue(np.isnan(p.sample_grid(g,-4998,4998)))

class RoofTests(unittest.TestCase):
    poly=Polygon([(-12,-10),(12,-10),(12,10),(-12,10)])
    ground=object();surface=object()
    def fit(self,func,tags=None):
        def sample(grid,x,y):return np.full(np.asarray(x).shape,10.) if grid is self.ground else func(np.asarray(x),np.asarray(y))
        with patch.object(p,'sample_grid',side_effect=sample):return p.building_roof(self.poly,self.ground,self.surface,tags or {})
    def test_measured_flat_roof(self):
        ground,roof=self.fit(lambda x,y:np.full(x.shape,18.))
        self.assertEqual(ground,10);self.assertEqual(roof['source'],'dsm');self.assertEqual(roof['kind'],'flat');self.assertEqual(roof['height'],8)
    def test_two_plane_gable_is_recovered(self):
        ground,roof=self.fit(lambda x,y:22-.5*np.abs(x))
        self.assertEqual(roof['kind'],'gable');self.assertAlmostEqual(roof['height'],12,places=1);self.assertLess(roof['error'],.05)
    def test_invalid_surface_uses_osm_then_default(self):
        _,r=self.fit(lambda x,y:np.full(x.shape,-9999.),{'building:levels':'3'})
        self.assertEqual(r['height'],9);self.assertEqual(r['source'],'osm')
        _,r=self.fit(lambda x,y:np.full(x.shape,-9999.))
        self.assertEqual(r['height'],6);self.assertEqual(r['source'],'default')

class CoastlineTests(unittest.TestCase):
    def test_directed_coastline_leaves_sea_on_right(self):
        # Southbound coastline: east/left is land, west/right is sea.
        ll=[p.INVERSE.transform(p.CX,p.CY+6000),p.INVERSE.transform(p.CX,p.CY-6000)]
        element={'type':'way','id':1,'tags':{'natural':'coastline'},'geometry':[{'lon':lon,'lat':lat} for lon,lat in ll]}
        water=p.water_polygons([element])
        self.assertTrue(water.covers(Point(-1000,0)));self.assertFalse(water.covers(Point(1000,0)))
    def test_no_coastline_is_an_explicit_error(self):
        with self.assertRaisesRegex(RuntimeError,'No OSM coastline'):p.water_polygons([])

if __name__=='__main__':unittest.main()
