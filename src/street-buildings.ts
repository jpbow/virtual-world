import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import type {Building} from './types';

/** Detailed buildings (tools/street_buildings.py), modelled in Blender from OSM footprints, 1 m LiDAR heights
 * and roof fits, and facade notes: observed in street photos (one mesh per building, e.g. London Street), or
 * typical for a building type (whole areas merged into chunks, e.g. Lyttelton).
 *
 * The GLBs are in world coordinates (east, elevation, south). A per-building node's extras name the OSM building
 * and any footprints it replaces. A chunk node lists its buildings; its vertices carry a _building attribute
 * (1-based index into that list). Modelled footprints are dropped from the generic extruded buildings.
 */
export interface StreetBuildings {group:THREE.Group;meshes:THREE.Mesh[];replaced:Set<string>;models:Map<string,{name:string;evidence:string}>}

const TYPE_NAMES:Record<string,string>={house:'House',outbuilding:'Garage or shed',industrial:'Industrial building',shop:'Shop or business',civic:'Civic building',
  tank:'Storage tank',container:'Container',canopy:'Canopy'};

async function load(name:string):Promise<THREE.Group|null>{
  try{
    const response=await fetch(`/buildings/${name}.glb`,{method:'HEAD'});
    if(!response.ok||!(response.headers.get('content-type')??'').includes('gltf'))return null;
    return (await new GLTFLoader().loadAsync(`/buildings/${name}.glb`)).scene;
  }catch{return null;}
}

export async function loadStreetBuildings(names:string[],buildings:Building[]):Promise<StreetBuildings|null>{
  const scenes=(await Promise.all(names.map(load))).filter((s):s is THREE.Group=>s!==null);
  if(!scenes.length)return null;
  const index=new Map(buildings.map((b,i)=>[b.id,i]));
  const replaced=new Set<string>(),models=new Map<string,{name:string;evidence:string}>(),meshes:THREE.Mesh[]=[];
  const group=new THREE.Group();group.name='Detailed buildings';
  for(const scene of scenes){
    scene.traverse(o=>{
      for(const id of String(o.userData.replaces??o.userData.osm_id??'').split(','))if(id)replaced.add(id);
      if(o.userData.osm_id)models.set(o.userData.osm_id,{name:o.userData.name??'',evidence:o.userData.evidence??''});
      if(o.userData.chunk){
        const ids:string[]=JSON.parse(o.userData.ids),types:string[]=JSON.parse(o.userData.types),storeys:number[]=JSON.parse(o.userData.storeys),labels:string[]=JSON.parse(o.userData.names);
        ids.forEach((id,i)=>models.set(id,{name:labels[i]||TYPE_NAMES[types[i]]||'Lyttelton building',
          evidence:`Typed by rule as a ${(TYPE_NAMES[types[i]]??types[i]).toLowerCase()}, ${storeys[i]} storey${storeys[i]>1?'s':''}. Roof, heights and footprint from LINZ 1 m LiDAR and OSM; facade layout and colours are typical for the type, not observed.`}));
      }
      if(!(o instanceof THREE.Mesh))return;
      // A node with several materials loads as a group of meshes; the extras sit on the group.
      const data=o.userData.osm_id||o.userData.chunk?o.userData:o.parent?.userData;
      const geometry=o.geometry as THREE.BufferGeometry,triangles=(geometry.index?.count??geometry.attributes.position.count)/3;
      if(data?.chunk){
        const ids:string[]=JSON.parse(data.ids),tag=geometry.getAttribute('_building'),idx=geometry.index;if(!tag)return;
        const owners=new Array(triangles);
        for(let t=0;t<triangles;t++){const v=idx?idx.getX(t*3):t*3;owners[t]=index.get(ids[Math.round(tag.getX(v))-1])??-1;}
        o.userData.owners=owners;meshes.push(o);
      }else if(data?.osm_id){
        const owner=index.get(data.osm_id);if(owner===undefined)return;
        o.userData.owners=new Array(triangles).fill(owner);meshes.push(o);
      }
    });
    group.add(scene);
  }
  return {group,meshes,replaced,models};
}
