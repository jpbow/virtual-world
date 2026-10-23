import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import type {Road} from './types';

/** Street corridors (tools/street_corridor.py): traffic and parking lanes, gutters, kerbs and footpaths built in
 * Blender from measured kerb lines, with the city kit's surfaces.
 *
 * The GLB is in local metres with y the height above the ground, so each vertex is draped onto the terrain.
 * The whole corridor draws a little nearer than the OSM road ribbons it covers and a little farther than the
 * inventory's measured paint, which stays visible on top.
 */
export interface StreetCorridor {group:THREE.Group;street:string;surfaceAt:(x:number,z:number)=>number|null}

// Above the OSM road ribbons it covers (draped 0.12 m above the terrain, roads.ts) and under the inventory's
// paint (0.14 m), so the ribbon cannot show through up close where the depth bias is only millimetres.
const LIFT=0.13;

export async function loadStreetCorridor(name:string,heightAt:(x:number,z:number)=>number):Promise<StreetCorridor|null>{
  let scene:THREE.Group;
  try{
    const response=await fetch(`/streets/${name}.glb`,{method:'HEAD'});
    if(!response.ok||!(response.headers.get('content-type')??'').includes('gltf'))return null;
    scene=(await new GLTFLoader().loadAsync(`/streets/${name}.glb`)).scene;
  }catch{return null;}
  scene.updateMatrixWorld(true);
  const group=new THREE.Group();group.name=`Street corridor ${name}`;let street=name;
  scene.traverse(o=>{
    if(o.userData.street)street=o.userData.street;
    if(!(o instanceof THREE.Mesh))return;
    const geometry=(o.geometry as THREE.BufferGeometry).clone().applyMatrix4(o.matrixWorld),position=geometry.attributes.position as THREE.BufferAttribute;
    for(let i=0;i<position.count;i++)position.setY(i,heightAt(position.getX(i),position.getZ(i))+LIFT+position.getY(i));
    geometry.computeVertexNormals();geometry.computeBoundingSphere();
    const materials=(Array.isArray(o.material)?o.material:[o.material]).map(m=>{
      const material=(m as THREE.MeshStandardMaterial).clone();
      material.customProgramCacheKey=()=>'street-corridor-v1';
      material.onBeforeCompile=shader=>{
        shader.vertexShader=shader.vertexShader.replace('#include <project_vertex>',`#include <project_vertex>
          // Over the road ribbons (0.9982+, roads.ts), under measured paint (0.9975).
          mvPosition.xyz*=0.998;gl_Position=projectionMatrix*mvPosition;`);
      };
      return material;
    });
    const mesh=new THREE.Mesh(geometry,materials.length===1?materials[0]:materials);mesh.name=o.name;group.add(mesh);
  });
  // The corridor's top surface (footpath, kerb or road) under a point, so props stand on the footpath.
  group.updateMatrixWorld(true);
  const ray=new THREE.Raycaster(),down=new THREE.Vector3(0,-1,0),from=new THREE.Vector3();
  const surfaceAt=(x:number,z:number)=>{from.set(x,1e4,z);ray.set(from,down);const hit=ray.intersectObject(group,true)[0];return hit?hit.point.y:null;};
  return {group,street,surfaceAt};
}

/** Outlines written beside the corridor (public/streets/<name>.json): `road` is the carriageway kerb to kerb with
 * its junctions, `surface` the corridor's stretch kerb to kerb, and `ribbon` the street's OSM road ribbon over
 * that stretch, widened per point to the measured kerbs. */
export interface StreetOutline {road:number[][][];surface:number[][][];ribbon:Road|null}

export async function streetOutline(name:string):Promise<StreetOutline|null>{
  try{
    const response=await fetch(`/streets/${name}.json`);
    if(!response.ok||!(response.headers.get('content-type')??'').includes('json'))return null;
    const data=await response.json();return {road:data.road??[],surface:data.surface??[],ribbon:data.ribbon??null};
  }catch{return null;}
}

function within(rings:number[][][]){
  const boxes=rings.map(r=>[Math.min(...r.map(p=>p[0])),Math.min(...r.map(p=>p[1])),Math.max(...r.map(p=>p[0])),Math.max(...r.map(p=>p[1]))]);
  const inRing=(x:number,y:number,ring:number[][])=>{let c=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const [xi,yi]=ring[i],[xj,yj]=ring[j];if((yi>y)!==(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)c=!c;}return c;};
  return (x:number,y:number)=>rings.some((ring,k)=>x>=boxes[k][0]&&x<=boxes[k][2]&&y>=boxes[k][1]&&y<=boxes[k][3]&&inRing(x,y,ring));
}

/** Vegetation without the plants that the canopy detection put on the carriageway: there it is parked cars,
 * umbrellas or awnings, not planting. Footpath planting stays. */
export function treesOutside(trees:number[][],outline:StreetOutline){
  const inside=within(outline.road);return trees.filter(([x,y])=>!inside(x,y));
}

/** Road ribbons with the corridor's stretch cut out and the street's widened ribbon in its place. Each cut
 * reaches 5 cm under the widened ribbon, so no gap shows. */
export function roadsWithStreet(roads:Road[],outline:StreetOutline):Road[]{
  return outline.ribbon?[...roadsOutside(roads,outline),outline.ribbon]:roads;
}

function roadsOutside<R extends {points:number[][]}>(roads:R[],outline:StreetOutline):R[]{
  const inside=within(outline.surface),out:R[]=[];
  const lerp=(a:number[],b:number[],t:number)=>a.map((v,i)=>v+(b[i]-v)*t);
  // Where segment a-b (a outside, b inside) crosses into the surface, then 0.5 m further in.
  const entry=(a:number[],b:number[])=>{let lo=0,hi=1;for(let k=0;k<14;k++){const m=(lo+hi)/2;if(inside(...lerp(a,b,m).slice(0,2) as [number,number]))hi=m;else lo=m;}
    const len=Math.hypot(b[0]-a[0],b[1]-a[1]);return lerp(a,b,Math.min(1,hi+.05/Math.max(len,1e-6)));};
  for(const road of roads){
    const flags=road.points.map(p=>inside(p[0],p[1]));
    if(!flags.some(Boolean)){out.push(road);continue;}
    let run:number[][]=[];
    road.points.forEach((p,i)=>{
      if(!flags[i]){if(!run.length&&i>0)run.push(entry(p,road.points[i-1]));run.push(p);return;}
      if(run.length){run.push(entry(road.points[i-1],p));if(run.length>1)out.push({...road,points:run});run=[];}
    });
    if(run.length>1)out.push({...road,points:run});
  }
  return out;
}
