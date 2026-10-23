import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import street_buildings as S
from shapely.geometry import LineString,Polygon


class Grid(S.Grid):
    """A synthetic 1 m DSM from a height function of local (x, y)."""
    def __init__(self,fn,bounds=(-20,-20,40,40)):
        l,b,r,t=bounds;xs=np.arange(l,r)+.5;ys=t-.5-np.arange(t-b)
        super().__init__(np.array([[fn(x,y) for x in xs] for y in ys],'float32'),l,t)


class FrontageTests(unittest.TestCase):
    def test_finds_the_street_edge_and_outward_normal(self):
        # A 10 x 15 m building whose south edge (y = 0) faces a street along y = -8.
        f=S.frontage([(0,0),(10,0),(10,15),(0,15)],[LineString([(-50,-8),(50,-8)])])
        self.assertAlmostEqual(f['length'],10,places=6)
        np.testing.assert_allclose(f['n'],[0,-1],atol=1e-9)
        self.assertAlmostEqual(f['a'][1],0,places=6)


class RoofTests(unittest.TestCase):
    def setUp(self):
        self.poly=Polygon([(0,0),(10,0),(10,8),(0,8)])
        self.fr=S.frame(self.poly,[1,0],[0,-1])                       # facade on y = 0, building to the north

    def test_planes_match_the_rise_coordinate(self):
        x,y=np.meshgrid(np.linspace(0,10,11),np.linspace(0,8,9));x=x.ravel();y=y.ravel()
        for kind in ('flat','shed','gable','gable-end','hip'):
            planes=S.roof_planes(kind,self.fr,5.,.4)
            np.testing.assert_allclose(S.roof_z(planes,x,y),5+.4*S.roof_distance(kind,self.fr,x,y),atol=1e-9,err_msg=kind)

    def test_fit_recovers_a_hip_roof(self):
        planes=S.roof_planes('hip',self.fr,24.,.55)
        dsm=Grid(lambda x,y:float(S.roof_z(planes,x,y)) if 0<=x<=10 and 0<=y<=8 else 18.)
        best=S.fit_roof(self.poly,self.fr,dsm,18.,['flat','shed','gable','hip'])[0]
        self.assertEqual(best['kind'],'hip');self.assertAlmostEqual(best['eave'],24,delta=.05);self.assertAlmostEqual(best['slope'],.55,delta=.02)

    def test_gable_walls_reach_the_ridge(self):
        planes=S.roof_planes('gable-end',self.fr,24.,.5)
        faces,wall=S.roof_geometry(self.poly,'gable-end',planes,0.)
        self.assertEqual(len(faces),2)
        # The facade (y = 0) gets a vertex at the ridge, mid-way along it, 2.5 m above the eave.
        ridge=[p for p in wall if abs(p[1])<1e-6 and abs(p[0]-5)<1e-6]
        self.assertTrue(ridge);self.assertAlmostEqual(ridge[0][2],26.5,places=6)


class RegistrationTests(unittest.TestCase):
    def test_roof_edge_ignores_the_verandah_step(self):
        # Street at 18 m; a 3.2 m verandah from 3 m out; the two-storey roof edge 1 m in front of the mapped facade.
        def h(x,y):
            if y<-1:return 21.2 if y>=-3 else 18.
            return 24.5
        f=dict(a=[0.,0.],b=[10.,0.],t=[1.,0.],n=[0.,-1.],length=10.)
        edge=S.roof_edge(f,Grid(h),18.)
        self.assertIsNotNone(edge);self.assertAlmostEqual(edge,-1,delta=.5)


class ScaffoldTests(unittest.TestCase):
    def test_photo_point_faces_the_facade_from_across_the_street(self):
        # A facade on y = 8 facing south onto a street along y = 0: shoot from 3 m past the centreline, heading north.
        f=dict(a=[0.,8.],b=[10.,8.],t=[1.,0.],n=[0.,-1.],length=10.)
        p=S.photo_point(f,[LineString([(-50,0),(50,0)])],None)
        self.assertEqual(p['heading'],0);self.assertIn('mapillary.com',p['mapillary'])


if __name__=='__main__':unittest.main()
