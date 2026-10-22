import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import type {Building} from './types';

/** Detailed street-front buildings (tools/street_buildings.py): one mesh per building, modelled in Blender from
 * OSM footprints, 1 m LiDAR heights and roof fits, and street-photo notes on facades, verandahs and signs.
 *
 * The GLB is already in world coordinates (east, elevation, south). Each node's extras name the OSM building it
 * models and any footprints it replaces; those are dropped from the generic extruded buildings.
 */
export interface StreetBuildings {group:THREE.Group;meshes:THREE.Mesh[];replaced:Set<string>;models:Map<string,{name:string;evidence:string}>}

export async function loadStreetBuildings(name:string,buildings:Building[]):Promise<StreetBuildings|null>{
  let scene:THREE.Group;
  try{
    const response=await fetch(`/buildings/${name}.glb`,{method:'HEAD'});
    if(!response.ok||!(response.headers.get('content-type')??'').includes('gltf'))return null;
    scene=(await new GLTFLoader().loadAsync(`/buildings/${name}.glb`)).scene;
  }catch{return null;}
  const index=new Map(buildings.map((b,i)=>[b.id,i]));
  const replaced=new Set<string>(),models=new Map<string,{name:string;evidence:string}>(),meshes:THREE.Mesh[]=[];
  scene.traverse(o=>{
    // A node with several materials loads as a group of meshes; the extras sit on the group.
    const data=o.userData.osm_id?o.userData:o.parent?.userData;
    if(o.userData.osm_id){
      models.set(o.userData.osm_id,{name:o.userData.name??'',evidence:o.userData.evidence??''});
      for(const id of String(o.userData.replaces??o.userData.osm_id).split(','))replaced.add(id);
    }
    if(!(o instanceof THREE.Mesh)||!data?.osm_id)return;
    const owner=index.get(data.osm_id);if(owner===undefined)return;
    const geometry=o.geometry as THREE.BufferGeometry,triangles=(geometry.index?.count??geometry.attributes.position.count)/3;
    o.userData.owners=new Array(triangles).fill(owner);meshes.push(o);
  });
  scene.name='Detailed street buildings';
  return {group:scene,meshes,replaced,models};
}
