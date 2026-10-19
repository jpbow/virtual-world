#!/usr/bin/env python3
"""Compare generated crown coverage with the detected canopy footprint."""
import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def measure(features,labels,spacing=10,terrain=None):
    data=np.asarray(features['trees'],dtype='float64')
    covered=np.zeros(labels.shape,dtype=bool)
    if len(data):
        # Stamp all circles in vectorized pixel batches. This keeps the real-
        # world regression check fast even with hundreds of thousands of plants.
        radius=data[:,5]*.70 if data.shape[1]>5 else data[:,3]*.34*.85
        if terrain is not None and data.shape[1]>6:
            # Low vegetation follows the slope. Its conservative projected
            # radius shrinks with the ground normal's vertical component.
            dz,dx=np.gradient(terrain,10)
            gc=np.clip(((data[:,0]+5000)/10).astype(int),0,1000);gr=np.clip(((5000-data[:,1])/10).astype(int),0,1000)
            normal_y=1/np.sqrt(1+dx[gr,gc]**2+dz[gr,gc]**2)
            radius=np.where(data[:,6]==1,radius*normal_y,radius)
        x=(data[:,0]+5000)/spacing-.5;y=(5000-data[:,1])/spacing-.5
        bx=np.floor(x).astype(int);by=np.floor(y).astype(int)
        limit=int(np.ceil(radius.max()/spacing))+1
        rr=(radius/spacing)**2
        for dy in range(-limit,limit+1):
            for dx in range(-limit,limit+1):
                c=bx+dx;r=by+dy
                valid=(c>=0)&(c<labels.shape[1])&(r>=0)&(r<labels.shape[0])&((c-x)**2+(r-y)**2<=rr)
                covered[r[valid],c[valid]]=True
    evidence=labels==4
    return {'vegetationInstances':len(features['trees']),'canopyEvidenceKm2':round(float(evidence.sum()*spacing**2/1e6),3),
            'crownCoverageFraction':round(float(covered[evidence].mean()) if evidence.any() else 0,4)}

def main():
    out=ROOT/'public/world';m=json.loads((out/'manifest.json').read_text());f=json.loads((out/'features.json').read_text())
    labels=np.fromfile(out/m['surface']['index'],dtype='uint8').reshape(1000,1000)
    terrain=np.fromfile(out/m['elevation'],dtype='<f4').reshape(1001,1001)
    report=measure(f,labels,terrain=terrain)
    print(json.dumps(report,indent=2))
    assert report['crownCoverageFraction']>=.8,'Detected canopy is mostly bare in the generated scene.'
if __name__=='__main__':main()
