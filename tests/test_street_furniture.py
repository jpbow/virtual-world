import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import street_furniture as F


def roads():
    # An eastbound street along y = 0 (points ordered west to east), 8 m kerb to kerb.
    return F.Roads({'roads':[{'kind':'residential','width':8.,'points':[[-50,0,0],[50,0,0]]}]})


class KerbSignTests(unittest.TestCase):
    def test_forward_sign_stands_at_the_left_kerb_facing_traffic(self):
        x,y,heading=roads().kerb_sign(10,0,'forward')
        # Eastbound traffic keeps left (north side); the sign faces west, toward it.
        self.assertAlmostEqual(x,10,places=6);self.assertAlmostEqual(y,4.6,places=6);self.assertAlmostEqual(heading,270,places=6)

    def test_backward_sign_is_on_the_other_kerb(self):
        x,y,heading=roads().kerb_sign(10,0,'backward')
        self.assertAlmostEqual(y,-4.6,places=6);self.assertAlmostEqual(heading,90,places=6)


class FacingTests(unittest.TestCase):
    def test_items_face_the_nearest_road(self):
        self.assertAlmostEqual(roads().facing(0,6),180,places=6)
        self.assertAlmostEqual(roads().facing(0,-6),0,places=6)


class MapillaryTests(unittest.TestCase):
    def model(self,value):
        import re
        return next((m for pattern,m in F.MAPILLARY_KIT if re.search(pattern,value)),None)

    def test_values_map_to_prefabs(self):
        self.assertEqual(self.model('object--trash-can'),'bin-compass')
        self.assertEqual(self.model('regulatory--stop--g1'),'sign-stop')
        self.assertEqual(self.model('information--parking--g3'),'sign-parking')
        self.assertEqual(self.model('regulatory--no-stopping--g15'),'sign-no-stopping')
        self.assertIsNone(self.model('object--manhole'))

    def test_carriageway_detections_move_to_the_kerb(self):
        x,y=roads().to_kerb(5,2)                                   # 2 m from the centreline of an 8 m street
        self.assertAlmostEqual(x,5,places=6);self.assertAlmostEqual(y,4.6,places=6)
        self.assertEqual(roads().to_kerb(5,6),(5,6))               # already on the footpath


if __name__=='__main__':unittest.main()
