import * as THREE from 'three';
type Surface={color:THREE.Texture;normal:THREE.Texture;roughness:THREE.Texture};
export interface GroundTextures {grass:Surface;forest:Surface;lawn:Surface;lush:THREE.Texture}
export async function loadGroundTextures(anisotropy:number):Promise<GroundTextures>{
  const loader=new THREE.TextureLoader();
  const load=async(path:string,srgb=false)=>{
    const t=await loader.loadAsync(path);t.wrapS=t.wrapT=THREE.RepeatWrapping;t.anisotropy=anisotropy;
    if(srgb)t.colorSpace=THREE.SRGBColorSpace;return t;
  };
  async function surface(name:string):Promise<Surface>{
    const [color,normal,roughness]=await Promise.all(['Diffuse','nor_gl','Rough'].map(channel=>load(`/materials/${name}-${channel}.jpg`,channel==='Diffuse')));
    return{color,normal,roughness};
  }
  // grass_ground is dry pasture; ambientCG Grass004/001 are mown lawn.
  const [grass,forest,lawn,lush]=await Promise.all([surface('grass_ground'),surface('forest_floor'),surface('grass004'),load('/materials/grass001-Diffuse.jpg',true)]);
  return{grass,forest,lawn,lush};
}
export function disposeGroundTextures(maps:GroundTextures){for(const set of [maps.grass,maps.forest,maps.lawn])for(const map of [set.color,set.normal,set.roughness])map.dispose();maps.lush.dispose();}
