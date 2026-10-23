import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';

/** Street furniture (tools/street_furniture.py): one reusable Blender kit of prefabs, instanced at every
 * placement the evidence records (OpenStreetMap, Christchurch City Council asset registers).
 *
 * Prefabs stand on their origin with their front toward +Z; a placement's heading is the compass
 * bearing the front faces. Each prefab part becomes one InstancedMesh, however many placements use it.
 */
export interface StreetKitPlacement {model:string;x:number;y:number;heading:number;source:string;licence:string;ref:string}
export interface StreetKit {group:THREE.Group;placed:number;models:Record<string,number>;sources:Record<string,string>}

export async function loadStreetKit(name:string,heightAt:(x:number,z:number)=>number):Promise<StreetKit|null>{
  let data:{kit:string;sources:Record<string,string>;placements:StreetKitPlacement[]};let kit:THREE.Group;
  try{
    const response=await fetch(`/street-kit/${name}.json`);
    if(!response.ok||!(response.headers.get('content-type')??'').includes('json'))return null;
    data=await response.json();kit=(await new GLTFLoader().loadAsync(`/street-kit/${data.kit}`)).scene;
  }catch{return null;}
  kit.updateMatrixWorld(true);
  // Prefab parts by name: a node with several materials loads as a group of meshes (glTF names drop the ':').
  const prefabs=new Map<string,{geometry:THREE.BufferGeometry;material:THREE.Material}[]>();
  for(const node of kit.children){
    const id=node.name.replace(/^kit:?/,''),parts:{geometry:THREE.BufferGeometry;material:THREE.Material}[]=[];
    const toOrigin=node.matrixWorld.clone().invert();
    node.traverse(o=>{if(o instanceof THREE.Mesh)parts.push({geometry:o.geometry.clone().applyMatrix4(new THREE.Matrix4().multiplyMatrices(toOrigin,o.matrixWorld)),material:o.material as THREE.Material});});
    prefabs.set(id,parts);
  }
  const group=new THREE.Group();group.name='Street furniture';
  const byModel=new Map<string,StreetKitPlacement[]>();
  for(const p of data.placements)if(prefabs.has(p.model)){if(!byModel.has(p.model))byModel.set(p.model,[]);byModel.get(p.model)!.push(p);}
  const o=new THREE.Object3D(),models:Record<string,number>={};
  for(const [model,list] of byModel){
    models[model]=list.length;
    for(const part of prefabs.get(model)!){
      const mesh=new THREE.InstancedMesh(part.geometry,part.material,list.length);mesh.name=`Street furniture ${model}`;
      list.forEach((p,i)=>{
        o.position.set(p.x,heightAt(p.x,-p.y),-p.y);
        // Compass bearing (0 = north, clockwise); three.js yaw is counter-clockwise from +Z.
        o.rotation.set(0,Math.PI-THREE.MathUtils.degToRad(p.heading),0);o.updateMatrix();mesh.setMatrixAt(i,o.matrix);
      });
      mesh.computeBoundingSphere();group.add(mesh);
    }
  }
  return {group,placed:[...byModel.values()].reduce((n,l)=>n+l.length,0),models,sources:data.sources};
}
