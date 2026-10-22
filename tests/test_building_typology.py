import math
import sys
import unittest
from pathlib import Path
from shapely.geometry import Point,Polygon

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import building_typology as T


def box(w,h):return Polygon([(0,0),(w,0),(w,h),(0,h)])


class ClassifyTests(unittest.TestCase):
    def test_tags_win(self):
        self.assertEqual(T.classify({'building':'garage'},box(10,10),None,False)[0],'outbuilding')
        self.assertEqual(T.classify({'building':'yes','amenity':'cafe'},box(10,10),None,False)[0],'shop')
        self.assertIsNone(T.classify({'building':'demolished'},box(10,10),None,False)[0])

    def test_footprint_rules_for_untyped_buildings(self):
        self.assertEqual(T.classify({'building':'yes'},Point(0,0).buffer(8,32),None,False)[0],'tank')
        self.assertEqual(T.classify({'building':'yes'},box(4,5),None,False)[0],'outbuilding')
        self.assertEqual(T.classify({'building':'yes'},box(20,15),None,True)[0],'industrial')
        self.assertEqual(T.classify({'building':'yes'},box(12,9),None,False)[0],'house')


class SpecTests(unittest.TestCase):
    def measured(self,eave,length=10.):
        return {'facade':{'length':length},'floor':20.,'groundInside':20.,'blocks':[{'kind':'hip','eave':eave,'ring':[[0,0]]}]}

    def test_storeys_and_windows_follow_the_measurements(self):
        one=T.spec('way/1','house','test',self.measured(3.2),{});two=T.spec('way/1','house','test',self.measured(6.),{})
        self.assertEqual(one['storeys'],1);self.assertNotIn('upper',one)
        self.assertEqual(two['storeys'],2);self.assertEqual(two['upper']['windows'],two['lower']['windows'])
        self.assertEqual(one['lower']['windows'],round((10-1.2)/2.7))

    def test_colours_are_stable_per_building(self):
        self.assertEqual(T.spec('way/7','house','t',self.measured(3),{})['wall'],T.spec('way/7','house','t',self.measured(3),{})['wall'])
        self.assertIn('not observed',T.spec('way/7','house','t',self.measured(3),{})['evidence'])


if __name__=='__main__':unittest.main()
