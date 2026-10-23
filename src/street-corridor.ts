import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';

/** Street corridors (tools/street_corridor.py): traffic and parking lanes, gutters, kerbs and footpaths built in
 * Blender from measured kerb lines, with the city kit's surfaces.
 *
 * The GLB is in local metres with y the height above the ground, so each vertex is draped onto the terrain.
 * The whole corridor draws a little nearer than the OSM road ribbons it covers and a little farther than the
 * inventory's measured paint, which stays visible on top.
 */
export interface StreetCorridor {group:THREE.Group;street:string}

// Above the displayed terrain (whose triangles can sit a few centimetres above the sampled height) and under
// the inventory's paint, which is lifted 0.14 m.
const LIFT=0.06;

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
  return {group,street};
}
