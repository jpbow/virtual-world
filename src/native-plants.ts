import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {crownColour} from './crowns';

export interface PlantAsset {
  id:string;species:string;url:string;author:string;license:string;source:string;
  kind:'tree'|'shrub';minHeight:number;maxHeight:number;density?:number;ignoreVertexColors?:boolean;role?:'representative'|'species';range?:number;
}
interface Chunk {
  plants:number[][];crowns:THREE.InstancedMesh;trunks:THREE.InstancedMesh;
  trunkIndices:Int32Array;cx:number;north:number;
}
export interface PlantModel {asset:PlantAsset;parts:THREE.InstancedMesh[];foliage?:THREE.InstancedMesh;width:number;depth:number;triangles:number}
type Model=PlantModel;
interface Selection {chunk:Chunk;index:number;model:Model;distance:number}
interface Hidden {mesh:THREE.InstancedMesh;index:number;matrix:THREE.Matrix4}
// Capacity per model, total instance limit and submitted-triangle budget.
export const MODEL_CAPACITY=1200;
const LIMIT=2000,RANGE=180,TRIANGLE_BUDGET=6_000_000,NATIVE_LIMIT=48;

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
  private lastDirection=new THREE.Vector3();
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
  /** Add generated models that need no catalog entry or download. */
  addModels(models:Model[]){
    if(this.disposed){for(const m of models)for(const p of m.parts)p.geometry.dispose();return;}
    for(const model of models){this.models.push(model);for(const part of model.parts)this.group.add(part);}
    this.status.representativeModels=this.models.filter(m=>m.asset.role==='representative').length;
    this.status.loaded=this.models.length;
    if(this.models.length)this.status.state='ready';
    this.lastPosition.set(Infinity,Infinity,Infinity);
  }
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
      this.status.representativeModels=this.models.filter(m=>m.asset.role==='representative').length;
      this.status.species=this.models.filter(m=>m.asset.role!=='representative').map(m=>m.asset.species);
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
      const mesh=new THREE.InstancedMesh(geometry,material,NATIVE_LIMIT);mesh.count=0;
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
    const forward=camera.getWorldDirection(new THREE.Vector3());
    if(!this.models.length||(camera.position.distanceToSquared(this.lastPosition)<25&&forward.dot(this.lastDirection)>.996))return;
    this.lastPosition.copy(camera.position);this.lastDirection.copy(forward);
    // Only spend the detail budget on plants inside a widened view cone.
    let cone=.35;
    if(camera instanceof THREE.PerspectiveCamera){
      const half=THREE.MathUtils.degToRad(camera.fov/2),diagonal=Math.atan(Math.tan(half)*Math.hypot(1,camera.aspect));
      cone=Math.cos(Math.min(Math.PI*.95,diagonal+THREE.MathUtils.degToRad(18)));
    }
    const toPlant=new THREE.Vector3();
    for(const item of this.hidden){item.mesh.setMatrixAt(item.index,item.matrix);item.mesh.instanceMatrix.needsUpdate=true;}
    this.hidden=[];
    const candidates:Selection[]=[];
    for(const chunk of this.chunks){
      if(Math.abs(camera.position.x-chunk.cx)>500+RANGE||Math.abs(camera.position.z+chunk.north)>500+RANGE)continue;
      chunk.plants.forEach((plant,index)=>{
        const [x,n,z,h]=plant;
        const distance=Math.hypot(camera.position.x-x,camera.position.y-(z+h*.5),camera.position.z+n);
        if(distance>RANGE)return;
        if(distance>h+12&&toPlant.set(x-camera.position.x,z+h*.5-camera.position.y,-n-camera.position.z).normalize().dot(forward)<cone)return;
        const eligible=this.eligible(plant,index);
        if(!eligible.length)return;
        const model=eligible[(index*31+Math.abs(Math.round(x+n)))%eligible.length];
        if(distance>(model.asset.range??180))return;
        candidates.push({chunk,index,model,distance});
      });
    }
    candidates.sort((a,b)=>a.distance-b.distance);
    const counts=new Map<Model,number>(),object=new THREE.Object3D(),tint=new THREE.Color(),up=new THREE.Vector3(0,1,0),normal=new THREE.Vector3();
    const hide=(mesh:THREE.InstancedMesh,index:number)=>{
      if(index<0)return;
      const original=new THREE.Matrix4();mesh.getMatrixAt(index,original);this.hidden.push({mesh,index,matrix:original});
      mesh.setMatrixAt(index,new THREE.Matrix4().makeScale(0,0,0));mesh.instanceMatrix.needsUpdate=true;
    };
    const place=(model:Model,plant:number[])=>{
      const slot=counts.get(model)??0;
      if(slot>=(model.asset.role==='representative'?MODEL_CAPACITY:NATIVE_LIMIT))return false;
      object.updateMatrix();
      for(const part of model.parts)part.setMatrixAt(slot,object.matrix);
      if(model.foliage)model.foliage.setColorAt(slot,foliageTint(plant[7],tint));
      counts.set(model,slot+1);return true;
    };
    let total=0,rendered=0,nativeActive=0;
    for(const {chunk,index,model} of candidates){
      const representative=model.asset.role==='representative';
      if(rendered>=LIMIT||total+model.triangles>TRIANGLE_BUDGET||(!representative&&nativeActive>=NATIVE_LIMIT))continue;
      const plant=chunk.plants[index],[x,n,ground,h,rotation]=plant,radius=plant[5]??h*.34;
      let placed=0;
      if(representative&&plant[6]===1){
        // A low-scrub instance is a measured cluster, not one plant: fill it
        // with several naturally proportioned bushes instead of stretching one.
        const bushes=this.models.filter(m=>m.asset.role==='representative'&&m.asset.kind==='shrub');
        const count=Math.min(9,Math.max(2,Math.round(radius*radius*.9/Math.max(1,h*h*2.4))));
        const seed=hashPlant(plant,index);
        for(let i=0;i<count&&rendered<LIMIT;i++){
          const bush=bushes[(seed+i*7)%bushes.length];
          if(total+bush.triangles>TRIANGLE_BUDGET)break;
          const angle=rotation+i*2.39996,distance=i===0?0:radius*.62*Math.sqrt((i+.35*unit(seed,i))/count);
          const bx=x+Math.cos(angle)*distance,bz=-n+Math.sin(angle)*distance;
          const height=h*(.72+.38*unit(seed,i+11)),spread=Math.min(4.5,height*(1.6+unit(seed,i+23)));
          normal.set(this.heightAt(bx-3,bz)-this.heightAt(bx+3,bz),6,this.heightAt(bx,bz-3)-this.heightAt(bx,bz+3)).normalize().lerp(up,.5).normalize();
          object.quaternion.setFromUnitVectors(up,normal);object.rotateY(angle*3.1);
          object.position.set(bx,this.heightAt(bx,bz)-height*.08,bz);
          object.scale.set(spread/bush.width,height,spread/bush.depth);
          if(place(bush,plant)){total+=bush.triangles;rendered++;placed++;}
        }
      }else{
        object.position.set(x,ground-.15,-n);object.rotation.set(0,rotation,0);object.scale.setScalar(h);
        if(representative){
          // Keep natural proportions; follow measured crown width only loosely.
          const diameter=2*radius,stretch=THREE.MathUtils.clamp(diameter/(model.width*h),.8,1.3);
          object.scale.set(h*stretch,h,h*stretch);
        }
        if(place(model,plant)){total+=model.triangles;rendered++;placed++;if(!representative)nativeActive++;}
      }
      if(placed){hide(chunk.crowns,index);hide(chunk.trunks,chunk.trunkIndices[index]);}
    }
    for(const model of this.models)for(const part of model.parts){part.count=counts.get(model)??0;part.instanceMatrix.needsUpdate=true;if(part.instanceColor)part.instanceColor.needsUpdate=true;part.computeBoundingSphere();}
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

function hashPlant(plant:number[],index:number){
  return ((Math.round(plant[0]*100)*73856093)^(Math.round(plant[1]*100)*19349663)^index)>>>0;
}
function unit(seed:number,i:number){
  const v=Math.sin(seed*.0001+i*12.9898)*43758.5453;return v-Math.floor(v);
}
/** Leaf tint: follow the aerial-sampled crown hue, keep texture brightness. */
function foliageTint(packed:number|undefined,target:THREE.Color){
  crownColour(packed,0,target);
  const luminance=Math.max(.002,target.r*.2126+target.g*.7152+target.b*.0722);
  target.multiplyScalar(1/luminance);
  return target.setRGB(.5+.5*Math.min(1.6,target.r),.5+.5*Math.min(1.6,target.g),.5+.5*Math.min(1.6,target.b)).multiplyScalar(.82);
}
