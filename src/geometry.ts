import * as THREE from 'three';
import type {Building, Road, WaterPolygon} from './types';

export function terrainGeometry(heights:Float32Array,step:number):THREE.BufferGeometry {
  const segments=100/step, side=segments+1, vertices:number[]=[],uvs:number[]=[],indices:number[]=[];
  for(let r=0;r<=segments;r++)for(let c=0;c<=segments;c++){
    const h=heights[r*step*101+c*step];
    vertices.push(c*step*10,Number.isFinite(h)?h:-100, r*step*10);
    uvs.push(c/segments,1-r/segments);
  }
  for(let r=0;r<segments;r++)for(let c=0;c<segments;c++){
    const a=r*side+c,b=a+1,d=a+side+1,e=a+side;
    const samples=[heights[r*step*101+c*step],heights[r*step*101+(c+1)*step],heights[(r+1)*step*101+c*step],heights[(r+1)*step*101+(c+1)*step]];
    if(samples.every(Number.isFinite))indices.push(a,e,b,b,e,d);
  }
  // Short skirts conceal T-junctions between terrain levels of detail.
  const perimeter:number[]=[];
  for(let c=0;c<=segments;c++)perimeter.push(c);
  for(let r=1;r<=segments;r++)perimeter.push(r*side+segments);
  for(let c=segments-1;c>=0;c--)perimeter.push(segments*side+c);
  for(let r=segments-1;r>0;r--)perimeter.push(r*side);
  const skirtStart=vertices.length/3;
  for(const id of perimeter){vertices.push(vertices[id*3],vertices[id*3+1]-12,vertices[id*3+2]);uvs.push(uvs[id*2],uvs[id*2+1]);}
  for(let i=0;i<perimeter.length;i++){
    const j=(i+1)%perimeter.length;
    indices.push(perimeter[i],skirtStart+i,perimeter[j],perimeter[j],skirtStart+i,skirtStart+j);
  }
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));g.setAttribute('uv',new THREE.Float32BufferAttribute(uvs,2));g.setIndex(indices);g.computeVertexNormals();g.computeBoundingSphere();return g;
}

function roofHeight(b:Building,x:number,north:number):number {
  const r=b.roof;
  return b.ground+r.height+(r.kind==='gable'?r.slope!*Math.abs(x*r.axis![0]+north*r.axis![1]-r.center!):0);
}

function clipHalf(ring:number[][],axis:number[],center:number,sign:number):number[][] {
  const out:number[][]=[];
  for(let i=0;i<ring.length;i++){
    const a=ring[i],b=ring[(i+1)%ring.length];
    const da=(a[0]*axis[0]+a[1]*axis[1]-center)*sign,db=(b[0]*axis[0]+b[1]*axis[1]-center)*sign;
    if(da>=-1e-7)out.push(a);
    if((da>0&&db<0)||(da<0&&db>0)){
      const t=da/(da-db);out.push([a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])]);
    }
  }
  return out;
}

export function buildingGeometry(buildings:Building[]):{walls:THREE.BufferGeometry;roofs:THREE.BufferGeometry;roofOwners:number[];wallOwners:number[]} {
  const walls:number[]=[],roofs:number[]=[],wallColors:number[]=[],roofColors:number[]=[],roofOwners:number[]=[],wallOwners:number[]=[];
  const wallPalette=['#d7cfb7','#c8c0aa','#c4c3b6','#dbd7c8','#b9b3a1'];
  const roofPalette=['#707b77','#77756b','#586c69','#8b7569','#9c9380'];
  function tri(dest:number[],colors:number[],owners:number[],points:number[][],color:THREE.Color,owner:number){
    for(const p of points){dest.push(...p);colors.push(color.r,color.g,color.b);}owners.push(owner);
  }
  buildings.forEach((b,owner)=>{
    const hash=b.id.split('').reduce((a,c)=>(a*31+c.charCodeAt(0))>>>0,0);
    const wc=new THREE.Color(wallPalette[hash%wallPalette.length]);const rc=new THREE.Color(b.roofColor??roofPalette[hash%roofPalette.length]);
    for(const ring of [b.ring,...b.holes])for(let i=0;i<ring.length;i++){
      const a=ring[i],d=ring[(i+1)%ring.length];
      // Split walls where a gable ridge crosses an edge, preserving its peak.
      let edges=[a,d];
      if(b.roof.kind==='gable'){
        const axis=b.roof.axis!,center=b.roof.center!;
        const da=a[0]*axis[0]+a[1]*axis[1]-center,dd=d[0]*axis[0]+d[1]*axis[1]-center;
        if(da*dd<0){const t=da/(da-dd);edges=[a,[a[0]+(d[0]-a[0])*t,a[1]+(d[1]-a[1])*t],d];}
      }
      for(let j=0;j<edges.length-1;j++){
        const p=edges[j],q=edges[j+1];
        const p0=[p[0],b.foundation??(b.ground-5),-p[1]],q0=[q[0],b.foundation??(b.ground-5),-q[1]],p1=[p[0],roofHeight(b,...p as [number,number]),-p[1]],q1=[q[0],roofHeight(b,...q as [number,number]),-q[1]];
        tri(walls,wallColors,wallOwners,[p0,q0,p1],wc,owner);tri(walls,wallColors,wallOwners,[q0,q1,p1],wc,owner);
      }
    }
    const halves=b.roof.kind==='gable'&&b.holes.length===0?[clipHalf(b.ring,b.roof.axis!,b.roof.center!,1),clipHalf(b.ring,b.roof.axis!,b.roof.center!,-1)]:[b.ring];
    for(const ring of halves){
      if(ring.length<3)continue;
      const outer=ring.map(p=>new THREE.Vector2(p[0],p[1]));
      const holes=(halves.length===1?b.holes:[]).map(h=>h.map(p=>new THREE.Vector2(p[0],p[1])));
      const flattened=[...ring,...(halves.length===1?b.holes.flat():[])];
      for(const t of THREE.ShapeUtils.triangulateShape(outer,holes)){
        const points=t.map(i=>{const p=flattened[i];return[p[0],roofHeight(b,p[0],p[1]),-p[1]];});
        tri(roofs,roofColors,roofOwners,points,rc,owner);
      }
    }
  });
  function geometry(p:number[],c:number[]){const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(p,3));g.setAttribute('color',new THREE.Float32BufferAttribute(c,3));g.computeVertexNormals();g.computeBoundingSphere();return g;}
  return{walls:geometry(walls,wallColors),roofs:geometry(roofs,roofColors),roofOwners,wallOwners};
}

export function roadsGeometry(roads:Road[],paths:boolean):THREE.BufferGeometry {
  const p:number[]=[],colors:number[]=[];
  for(const road of roads){
    const isPath=['footway','path','steps','cycleway','track','bridleway'].includes(road.kind);
    if(isPath!==paths)continue;
    const color=new THREE.Color(road.bridge?'#bba680':isPath?'#b5ad87':'#767b73');
    for(let i=0;i<road.points.length-1;i++){
      const a=road.points[i],b=road.points[i+1],dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy);
      if(len<.01)continue;
      const ox=-dy/len*road.width/2,oy=dx/len*road.width/2;
      const l=[a[0]+ox,a[2],-a[1]-oy],r=[a[0]-ox,a[2],-a[1]+oy],l2=[b[0]+ox,b[2],-b[1]-oy],r2=[b[0]-ox,b[2],-b[1]+oy];
      p.push(...l,...r,...l2,...r,...r2,...l2);for(let j=0;j<6;j++)colors.push(color.r,color.g,color.b);
    }
  }
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(p,3));g.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));g.computeVertexNormals();g.computeBoundingSphere();return g;
}

export function waterGeometry(polygons:WaterPolygon[]):THREE.BufferGeometry {
  const positions:number[]=[];
  for(const p of polygons){
    const outer=p.ring.map(v=>new THREE.Vector2(v[0],v[1]));const holes=p.holes.map(h=>h.map(v=>new THREE.Vector2(v[0],v[1])));
    const all=[...p.ring,...p.holes.flat()];
    for(const triangle of THREE.ShapeUtils.triangulateShape(outer,holes))for(const id of triangle){positions.push(all[id][0],0,-all[id][1]);}
  }
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));g.computeVertexNormals();return g;
}
