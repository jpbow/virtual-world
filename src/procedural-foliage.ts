import * as THREE from 'three';
import type {PlantAsset,PlantModel} from './native-plants';

/** Representative close-range trees and bushes generated with EZ-Tree (MIT).
 * Geometry is generated once in the browser, normalized to unit height and
 * instanced. These are representative forms, not identified species.
 */
interface Variant {
  id:string;preset:string;kind:'tree'|'shrub';seed:number;minHeight:number;maxHeight:number;density?:number;range:number;
  // Presets are sparse ornamental trees; Lyttelton gardens and bush are dense.
  leafCount:number;leafSize:number;leafType?:'ash'|'oak';simplify?:boolean;
}
const VARIANTS:Variant[]=[
  {id:'broadleaf-oak-a',preset:'Oak Small',kind:'tree',seed:1201,minHeight:3.5,maxHeight:14,range:150,leafCount:1.6,leafSize:2.2,simplify:true},
  {id:'broadleaf-oak-b',preset:'Oak Small',kind:'tree',seed:5417,minHeight:3.5,maxHeight:14,range:150,leafCount:1.8,leafSize:2.3,simplify:true},
  {id:'broadleaf-ash',preset:'Ash Small',kind:'tree',seed:2203,minHeight:3.5,maxHeight:14,range:150,leafCount:1.1,leafSize:2,simplify:true},
  {id:'broadleaf-slender',preset:'Aspen Small',kind:'tree',seed:3307,minHeight:5,maxHeight:16,range:150,density:.5,leafCount:2,leafSize:1.8,leafType:'ash',simplify:true},
  {id:'broadleaf-oak-tall',preset:'Oak Medium',kind:'tree',seed:4409,minHeight:9,maxHeight:60,range:170,leafCount:1.3,leafSize:2.1,simplify:true},
  {id:'broadleaf-ash-tall',preset:'Ash Medium',kind:'tree',seed:6619,minHeight:9,maxHeight:60,range:170,leafCount:1,leafSize:2.2,simplify:true},
  {id:'conifer-tall',preset:'Pine Medium',kind:'tree',seed:7727,minHeight:12,maxHeight:60,range:170,density:.45,leafCount:1.2,leafSize:1.7,simplify:true},
  {id:'bush-a',preset:'Bush 1',kind:'shrub',seed:811,minHeight:.5,maxHeight:3.5,range:75,leafCount:.8,leafSize:2.5,simplify:true},
  {id:'bush-b',preset:'Bush 1',kind:'shrub',seed:1913,minHeight:.5,maxHeight:3.5,range:75,leafCount:.8,leafSize:2.4,leafType:'oak',simplify:true},
  {id:'bush-c',preset:'Bush 2',kind:'shrub',seed:2917,minHeight:.5,maxHeight:3.5,range:75,leafCount:2,leafSize:2,leafType:'oak',simplify:true},
];
const SOURCE='https://github.com/dgreenheck/ez-tree';

function standardFrom(source:THREE.Material,options:THREE.MeshStandardMaterialParameters):THREE.MeshStandardMaterial {
  const s=source as THREE.MeshPhongMaterial;
  return new THREE.MeshStandardMaterial({map:s.map,normalMap:s.normalMap,color:s.color,...options});
}

/** Point leaf normals away from the crown centre so cards shade as one mass. */
function crownNormals(geometry:THREE.BufferGeometry){
  geometry.computeBoundingBox();
  const box=geometry.boundingBox!,center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());
  const position=geometry.getAttribute('position'),normal=geometry.getAttribute('normal') as THREE.BufferAttribute,v=new THREE.Vector3(),n=new THREE.Vector3();
  for(let i=0;i<position.count;i++){
    v.fromBufferAttribute(position,i).sub(center).divide(size);
    n.fromBufferAttribute(normal,i);
    v.y+=.2;v.normalize().multiplyScalar(.8).addScaledVector(n,.2).normalize();
    normal.setXYZ(i,v.x,v.y,v.z);
  }
  normal.needsUpdate=true;
}

export async function generateFoliage(limit:number):Promise<PlantModel[]>{
  const {Tree}=await import('@dgreenheck/ez-tree');
  const models:PlantModel[]=[];
  const leafMaterials=new Map<THREE.Texture,THREE.MeshStandardMaterial>(),barkMaterials=new Map<THREE.Texture|null,THREE.MeshStandardMaterial>();
  for(const variant of VARIANTS){
    const tree=new Tree();
    tree.loadPreset(variant.preset);
    tree.options.seed=variant.seed;
    const options=tree.options;
    options.leaves.count=Math.round(options.leaves.count*variant.leafCount);
    options.leaves.size*=variant.leafSize;
    options.leaves.tint=0xffffff;
    if(variant.leafType)options.leaves.type=variant.leafType;
    if(variant.simplify){
      // Fine branches are hidden by foliage; fewer sides save triangles.
      const branch=options.branch as unknown as {segments:Record<number,number>;sections:Record<number,number>};
      branch.segments[0]=Math.min(branch.segments[0],6);
      for(const level of [1,2,3]){branch.segments[level]=Math.min(branch.segments[level],level>1?3:4);branch.sections[level]=Math.max(2,Math.ceil(branch.sections[level]*.5));}
    }
    tree.generate();
    const branches=tree.branchesMesh.geometry,leaves=tree.leavesMesh.geometry;
    leaves.computeVertexNormals();crownNormals(leaves);
    branches.computeBoundingBox();leaves.computeBoundingBox();
    const bounds=branches.boundingBox!.clone().union(leaves.boundingBox!),size=bounds.getSize(new THREE.Vector3()),center=bounds.getCenter(new THREE.Vector3());
    const normalize=new THREE.Matrix4().makeScale(1/size.y,1/size.y,1/size.y).multiply(new THREE.Matrix4().makeTranslation(-center.x,-bounds.min.y,-center.z));
    branches.applyMatrix4(normalize);leaves.applyMatrix4(normalize);
    const leafSource=tree.leavesMesh.material as THREE.MeshPhongMaterial,barkSource=tree.branchesMesh.material as THREE.MeshPhongMaterial;
    let leafMaterial=leafMaterials.get(leafSource.map!);
    if(!leafMaterial){
      // Alpha to coverage keeps distant leaves from thinning out as mipmaps blur alpha.
      leafMaterial=standardFrom(leafSource,{color:'#ffffff',alphaTest:.4,alphaToCoverage:true,side:THREE.DoubleSide,roughness:.85});
      leafMaterial.map!.colorSpace=THREE.SRGBColorSpace;leafMaterials.set(leafSource.map!,leafMaterial);
    }
    let barkMaterial=barkMaterials.get(barkSource.map);
    if(!barkMaterial){
      barkMaterial=standardFrom(barkSource,{color:'#8a8278',roughness:.95});
      if(barkMaterial.map)barkMaterial.map.colorSpace=THREE.SRGBColorSpace;barkMaterials.set(barkSource.map,barkMaterial);
    }
    const bark=new THREE.InstancedMesh(branches,barkMaterial,limit),foliage=new THREE.InstancedMesh(leaves,leafMaterial,limit);
    // Bush stems are hidden by foliage; only leaves are submitted.
    const parts=variant.kind==='shrub'?[foliage]:[bark,foliage];
    if(variant.kind==='shrub')branches.dispose();
    bark.count=foliage.count=0;bark.name=`Representative foliage bark: ${variant.id}`;foliage.name=`Representative foliage leaves: ${variant.id}`;
    // Allocate per-instance tint so leaves can follow sampled crown colour.
    foliage.setColorAt(0,new THREE.Color(1,1,1));
    leafSource.dispose();barkSource.dispose();
    const asset:PlantAsset={id:variant.id,species:`Representative ${variant.kind==='tree'?'tree':'bush'} (${variant.preset})`,url:'',author:'EZ-Tree, Daniel Greenheck',license:'MIT',source:SOURCE,kind:variant.kind,role:'representative',minHeight:variant.minHeight,maxHeight:variant.maxHeight,density:variant.density??1,range:variant.range};
    models.push({asset,parts,foliage,width:size.x/size.y,depth:size.z/size.y,triangles:parts.reduce((sum,part)=>sum+(part.geometry.index?.count??0)/3,0)});
    // Yield so generation never blocks interaction for long.
    await new Promise(resolve=>setTimeout(resolve,0));
  }
  return models;
}
