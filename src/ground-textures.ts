import * as THREE from 'three';
export interface GroundTextures {grass:{color:THREE.Texture;normal:THREE.Texture;roughness:THREE.Texture};forest:{color:THREE.Texture;normal:THREE.Texture;roughness:THREE.Texture}}
export async function loadGroundTextures(anisotropy:number):Promise<GroundTextures>{
  const loader=new THREE.TextureLoader();
  async function surface(name:string){
    const [color,normal,roughness]=await Promise.all(['Diffuse','nor_gl','Rough'].map(channel=>loader.loadAsync(`/materials/${name}-${channel}.jpg`)));
    for(const t of [color,normal,roughness]){t.wrapS=t.wrapT=THREE.RepeatWrapping;t.anisotropy=anisotropy;}
    color.colorSpace=THREE.SRGBColorSpace;
    return{color,normal,roughness};
  }
  const [grass,forest]=await Promise.all([surface('grass_ground'),surface('forest_floor')]);return{grass,forest};
}
export function disposeGroundTextures(maps:GroundTextures){for(const set of [maps.grass,maps.forest])for(const map of [set.color,set.normal,set.roughness])map.dispose();}
