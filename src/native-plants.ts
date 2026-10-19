import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';

interface PlantAsset {
  id:string;species:string;url:string;author:string;license:string;source:string;
  kind:'tree'|'shrub';minHeight:number;maxHeight:number;density?:number;ignoreVertexColors?:boolean;role?:'representative'|'species';range?:number;
}
interface Chunk {
  plants:number[][];crowns:THREE.InstancedMesh;trunks:THREE.InstancedMesh;
  trunkIndices:Int32Array;cx:number;north:number;
}
interface Model {asset:PlantAsset;parts:THREE.InstancedMesh[];width:number;depth:number;triangles:number}
interface Selection {chunk:Chunk;index:number;model:Model;distance:number}
interface Hidden {mesh:THREE.InstancedMesh;index:number;matrix:THREE.Matrix4}
const LIMIT=512,RANGE=180,TRIANGLE_BUDGET=4_000_000;

export function localPlantUrl(path:string):boolean {
  return /^\/plants\/[a-zA-Z0-9_./-]+\.glb$/.test(path)&&!path.includes('..');
}

/** Detailed local models replace nearby evidence-guided mass proxies only.
 * Species assignment is illustrative: LiDAR heights do not identify species.
 */
export class NativePlants {
  readonly group=new THREE.Group();
  readonly status={loaded:0,active:0,failed:0,state:'loading',species:[] as string[],representativeModels:0,nativeActive:0,triangles:0};
  private chunks:Chunk[]=[];
  private models:Model[]=[];
  private hidden:Hidden[]=[];
  private lastPosition=new THREE.Vector3(Infinity,Infinity,Infinity);
  private disposed=false;
  constructor(private heightAt:(x:number,z:number)=>number){this.group.name='Native plant models';}
  get credits(){return this.models.map(m=>m.asset);}
  private eligible(plant:number[],index:number){
    const hash=((Math.round(plant[0]*100)*73856093)^(Math.round(plant[1]*100)*19349663)^index)>>>0;
    const matching=this.models.filter(({asset})=>(asset.kind==='shrub')===(plant[6]===1)&&plant[3]>=asset.minHeight&&plant[3]<=asset.maxHeight&&hash/4294967296<(asset.density??1));
    const species=matching.filter(m=>m.asset.role!=='representative');
    return species.length?species:matching;

  }
  previewOptions(){
    const options:{plant:number[];width:number;depth:number;distance:number}[]=[];
    for(const chunk of this.chunks)chunk.plants.forEach((plant,index)=>{const models=this.eligible(plant,index).filter(m=>m.asset.role!=='representative');if(models.length){const m=models[(index*31+Math.abs(Math.round(plant[0]+plant[1])))%models.length];options.push({plant,width:m.width*plant[3],depth:m.depth*plant[3],distance:Math.hypot(plant[0],plant[1])});}});
    return options.sort((a,b)=>a.distance-b.distance).slice(0,80);
  }
  neighbours(plant:number[]){
    const nearby:number[][]=[];
    for(const chunk of this.chunks){if(Math.abs(plant[0]-chunk.cx)>550||Math.abs(plant[1]-chunk.north)>550)continue;for(const p of chunk.plants)if(Math.hypot(p[0]-plant[0],p[1]-plant[1])<45)nearby.push(p);}
    return nearby;
  }
  register(chunk:Chunk){this.chunks.push(chunk);}
  async load(onStatus:()=>void){
    try{
      const response=await fetch('/plants/catalog.json');
      if(!response.ok)throw new Error('Plant catalog unavailable');
      const catalog=await response.json();
      if(catalog.version!==1||!Array.isArray(catalog.models)||catalog.models.length>12)throw new Error('Invalid plant catalog');
      for(const asset of catalog.models as PlantAsset[]){
        if(!localPlantUrl(asset.url)||!asset.species||!asset.author||!asset.license||!/^https:\/\//.test(asset.source)||!['tree','shrub'].includes(asset.kind)||!(asset.minHeight>0&&asset.maxHeight>=asset.minHeight)){
          this.status.failed++;continue;
        }
        try{this.models.push(await this.loadModel(asset));}catch{this.status.failed++;}
      }
      this.status.loaded=this.models.length;
      this.status.species=this.models.filter(m=>m.asset.role!=='representative').map(m=>m.asset.species);
      this.status.representativeModels=this.models.filter(m=>m.asset.role==='representative').length;
      this.status.state=this.models.length?'ready':this.status.failed?'unavailable':'awaiting-assets';
    }catch{this.status.state='unavailable';this.status.failed++;}
    if(!this.disposed)onStatus();
  }
  private async loadModel(asset:PlantAsset):Promise<Model>{
    // Only self-contained GLBs are accepted by the installer. Disable remote
    // resources as well, including for manually edited catalogs.
    const manager=new THREE.LoadingManager();
    manager.setURLModifier(url=>{
      if(url.startsWith('blob:')||url.startsWith('data:')||url===asset.url||url.startsWith(location.origin+'/plants/'))return url;
      throw new Error('Plant resources must be local');
    });
    const gltf=await new GLTFLoader(manager).loadAsync(asset.url);
    if(this.disposed)throw new Error('Disposed');
    gltf.scene.updateMatrixWorld(true);
    const bounds=new THREE.Box3().setFromObject(gltf.scene),size=bounds.getSize(new THREE.Vector3());
    if(!Number.isFinite(size.y)||size.y<=0)throw new Error('Empty model');
    const center=bounds.getCenter(new THREE.Vector3());
    const normalize=new THREE.Matrix4().makeScale(1/size.y,1/size.y,1/size.y).multiply(new THREE.Matrix4().makeTranslation(-center.x,-bounds.min.y,-center.z));
    const parts:THREE.InstancedMesh[]=[];let triangles=0;
    gltf.scene.traverse(object=>{
      if(!(object instanceof THREE.Mesh))return;
      if(object instanceof THREE.SkinnedMesh)throw new Error('Static plant meshes required');
      const geometry=object.geometry.clone().applyMatrix4(new THREE.Matrix4().multiplyMatrices(normalize,object.matrixWorld));
      triangles+=(geometry.index?.count??geometry.getAttribute('position').count)/3;
      const material=Array.isArray(object.material)?object.material.map(m=>m.clone()):object.material.clone();
      for(const m of Array.isArray(material)?material:[material]){
        // Leaves are normally alpha-masked; preserve authored transparency.
        m.side=THREE.DoubleSide;
        if(asset.ignoreVertexColors&&'vertexColors' in m)m.vertexColors=false;
      }
      const mesh=new THREE.InstancedMesh(geometry,material,LIMIT);mesh.count=0;
      mesh.name=`${asset.role==='representative'?'Representative foliage':'Native plant'}: ${asset.species}`;parts.push(mesh);
    });
    if(!parts.length||parts.length>16||triangles>250000){
      for(const p of parts){p.geometry.dispose();for(const m of Array.isArray(p.material)?p.material:[p.material])m.dispose();}
      throw new Error('Plant model exceeds real-time budget');
    }
    for(const part of parts)this.group.add(part);
    return{asset,parts,width:size.x/size.y,depth:size.z/size.y,triangles};
  }
  update(camera:THREE.Camera){
    if(!this.models.length||camera.position.distanceToSquared(this.lastPosition)<25)return;
    this.lastPosition.copy(camera.position);
    for(const item of this.hidden){item.mesh.setMatrixAt(item.index,item.matrix);item.mesh.instanceMatrix.needsUpdate=true;}
    this.hidden=[];
    const candidates:Selection[]=[];
    for(const chunk of this.chunks){
      if(Math.abs(camera.position.x-chunk.cx)>500+RANGE||Math.abs(camera.position.z+chunk.north)>500+RANGE)continue;
      chunk.plants.forEach((plant,index)=>{
        const [x,n,z,h]=plant;
        const distance=Math.hypot(camera.position.x-x,camera.position.y-(z+h*.5),camera.position.z+n);
        if(distance>RANGE)return;
        const eligible=this.eligible(plant,index);
        if(!eligible.length)return;
        const model=eligible[(index*31+Math.abs(Math.round(x+n)))%eligible.length];
        if(distance>(model.asset.range??180))return;
        candidates.push({chunk,index,model,distance});
      });
    }
    candidates.sort((a,b)=>a.distance-b.distance);
    const counts=new Map<Model,number>(),matrix=new THREE.Matrix4(),object=new THREE.Object3D();
    const hide=(mesh:THREE.InstancedMesh,index:number)=>{
      if(index<0)return;
      const original=new THREE.Matrix4();mesh.getMatrixAt(index,original);this.hidden.push({mesh,index,matrix:original});
      mesh.setMatrixAt(index,new THREE.Matrix4().makeScale(0,0,0));mesh.instanceMatrix.needsUpdate=true;
    };
    let total=0,rendered=0,nativeActive=0;
    for(const {chunk,index,model} of candidates){
      const representative=model.asset.role==='representative';
      if(rendered>=LIMIT||total+model.triangles>TRIANGLE_BUDGET||(!representative&&nativeActive>=48))continue;
      const plant=chunk.plants[index],slot=counts.get(model)??0;
      object.position.set(plant[0],plant[2],-plant[1]);object.rotation.set(0,plant[4],0);object.scale.setScalar(plant[3]);
      if(representative){const diameter=2*(plant[5]??plant[3]*.34);object.scale.set(diameter/model.width,plant[3],diameter/model.depth);}
      if(representative&&plant[6]===1){
        const x=plant[0],z=-plant[1],normal=new THREE.Vector3(this.heightAt(x-4,z)-this.heightAt(x+4,z),8,this.heightAt(x,z-4)-this.heightAt(x,z+4)).normalize();
        object.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),normal);object.rotateY(plant[4]);
      }
      object.updateMatrix();matrix.copy(object.matrix);
      for(const part of model.parts)part.setMatrixAt(slot,matrix);
      total+=model.triangles;rendered++;if(!representative)nativeActive++;
      counts.set(model,slot+1);hide(chunk.crowns,index);hide(chunk.trunks,chunk.trunkIndices[index]);
    }
    for(const model of this.models)for(const part of model.parts){part.count=counts.get(model)??0;part.instanceMatrix.needsUpdate=true;part.computeBoundingSphere();}
    this.status.active=rendered;this.status.nativeActive=nativeActive;this.status.triangles=total;
  }
  dispose(){
    this.disposed=true;
    for(const model of this.models)for(const part of model.parts){part.geometry.dispose();for(const m of Array.isArray(part.material)?part.material:[part.material]){
      for(const value of Object.values(m))if(value instanceof THREE.Texture)value.dispose();m.dispose();
    }}
    this.chunks=[];this.models=[];this.hidden=[];
  }
}
