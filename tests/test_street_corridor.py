import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import street_corridor as C


def stations(n):return [dict(s=float(i)) for i in range(n)]


class KerbProfileTests(unittest.TestCase):
    def test_parking_spans_hold_and_gaps_interpolate(self):
        kerb,source=C.kerb_profile(stations(21),[(0,5,8.,'angle parking run 1'),(15,20,5.,'parallel parking run 2')])
        self.assertEqual(kerb[3],8.);self.assertEqual(kerb[18],5.);self.assertAlmostEqual(kerb[10],6.5)
        self.assertEqual(source[10],'interpolated')

    def test_a_zebra_build_out_wins_over_parking(self):
        kerb,source=C.kerb_profile(stations(21),[(0,20,8.,'angle parking run 1'),(9,11,4.,'zebra crossing')])
        self.assertEqual(kerb[10],4.);self.assertEqual(source[10],'zebra crossing');self.assertEqual(kerb[5],8.)


class ParkingGeometryTests(unittest.TestCase):
    def test_kerb_offset_from_parked_cars(self):
        # The same formula as evidence(): car centre offset + half the car's depth across the street + a gap.
        import math
        depth=lambda deg:C.CAR_LENGTH*math.sin(math.radians(deg))+C.CAR_WIDTH*math.cos(math.radians(deg))
        self.assertAlmostEqual(4.3+depth(0)/2+C.GAP['parallel'],5.55,places=2)
        self.assertAlmostEqual(5.8+depth(68.5)/2+C.GAP['angle'],8.42,places=2)


class CornerTests(unittest.TestCase):
    def test_offset_polygon_spans_left_and_right_kerbs(self):
        from shapely.geometry import LineString
        poly=C.offset_polygon(LineString([(0,0),(20,0)]),4.,6.,0,20)
        x0,y0,x1,y1=poly.bounds
        self.assertAlmostEqual(y1,4.,places=6);self.assertAlmostEqual(y0,-6.,places=6);self.assertAlmostEqual(poly.area,200.,places=3)

    def test_arm_kerbs_from_a_zebra_on_that_street_only(self):
        from shapely.geometry import LineString,box
        arm=LineString([(0,0),(0,30)]);zebra=box(-4.5,9,5.5,12)       # bars from x -4.5 to 5.5 across the arm
        self.assertEqual(C.arm_kerbs(arm,[('Other Street',zebra)],'Cross Street',10)[2],'OSM width')
        left,right,how=C.arm_kerbs(arm,[('Cross Street',zebra)],'Cross Street',10)
        # Heading north, left is west.
        self.assertEqual(how,'zebra crossing');self.assertAlmostEqual(left,4.5);self.assertAlmostEqual(right,5.5)


if __name__=='__main__':unittest.main()
