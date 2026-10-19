import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {terrainGeometry,buildingGeometry,roadsGeometry,waterGeometry} from './geometry';
import type {Manifest,Features,TileInfo,Building} from './types';
import {makeTerrainMaterial,setTerrainReference,makeRoadMaterial,makeLeafMaterial} from './materials';
import './style.css';
import {NativePlants} from './native-plants';
import {loadGroundTextures,disposeGroundTextures,type GroundTextures} from './ground-textures';
import {choosePlantView} from './plant-view';

const el=<T extends HTMLElement=HTMLElement>(id:string)=>document.getElementById(id) as T;
const canvas=el<HTMLCanvasElement>('world'),loading=el('loading'),detail=el('loading-detail');
let renderer:THREE.WebGLRenderer;
try{renderer=new THREE.WebGLRenderer({canvas,antialias:true,powerPreference:'high-performance'});}
catch{el('loading-title').textContent='3D graphics are unavailable';detail.textContent='Enable hardware acceleration in your browser, then reload.';loading.classList.add('error');throw new Error('WebGL initialization failed');}
renderer.setPixelRatio(Math.min(devicePixelRatio,1.75));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.12;
const scene=new THREE.Scene();scene.background=new THREE.Color('#b8cbcf');scene.fog=new THREE.Fog('#b8cbcf',9500,19000);
const camera=new THREE.PerspectiveCamera(48,1,1,35000);camera.position.set(2400,2300,4400);
const controls=new OrbitControls(camera,canvas);controls.target.set(-200,100,-100);controls.enableDamping=true;controls.dampingFactor=.085;controls.maxPolarAngle=Math.PI*.49;controls.minDistance=12;controls.maxDistance=13000;controls.zoomSpeed=.85;controls.listenToKeyEvents(canvas);
scene.add(new THREE.HemisphereLight('#f3f5eb','#8b9a82',2));const sun=new THREE.DirectionalLight('#fff2d2',2.1);sun.position.set(-5000,8000,-4000);scene.add(sun);
const buildingsGroup=new THREE.Group(),roadsGroup=new THREE.Group(),vegetationGroup=new THREE.Group(),terrainGroup=new THREE.Group();scene.add(buildingsGroup,roadsGroup,vegetationGroup,terrainGroup);
const nativePlants=new NativePlants(heightAt);vegetationGroup.add(nativePlants.group);
const pickMeshes:THREE.Mesh[]=[];
let manifest:Manifest,features:Features,elevation:Float32Array;
let imagery=false,wireframe=false,fly=false,flySpeed=100,loaded=0,activeLoads=0,failedTiles=0,disposed=false,worldInitialized=false;
let selectedBuilding:Building|null=null,selectionOutline:THREE.LineLoop|null=null;
const clock=new THREE.Clock(),keys=new Set<string>(),flyEuler=new THREE.Euler(0,0,0,'YXZ'),move=new THREE.Vector3(),direction=new THREE.Vector3();
let dragging=false,startX=0,startY=0,lastX=0,lastY=0;
const textureLoader=new THREE.TextureLoader();
const fallbackTiles=new Map<string,THREE.Mesh>();
let fallbackMaterial:THREE.MeshStandardMaterial,overviewTexture:THREE.Texture,overviewMask:THREE.Texture,landscapeControls:THREE.Texture,terrainRelief:THREE.Texture,groundTextures:GroundTextures;
const tileStates=new Map<string,{info:TileInfo;mesh:THREE.Mesh;heights:Float32Array;texture:THREE.Texture;mask:THREE.Texture;step:number}>(),pending=new Set<string>(),failedIds=new Set<string>();
const debug={ready:false,manifest:null as Manifest|null,renderer,scene,camera,controls,tiles:tileStates,nativePlants:nativePlants.status,get selectedBuilding(){return selectedBuilding;},get fly(){return fly;}};
(window as unknown as {__world:typeof debug}).__world=debug;
function resize(){const w=canvas.clientWidth,h=canvas.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();}window.addEventListener('resize',resize);resize();
function setMessage(title:string,message:string,error=false){loading.hidden=false;loading.classList.toggle('error',error);el('loading-title').textContent=title;detail.textContent=message;el('retry').hidden=!error;}
el('retry').addEventListener('click',()=>location.reload());
async function get<T>(path:string):Promise<T>{const r=await fetch(`/world/${path}`);if(!r.ok||r.headers.get('content-type')?.includes('text/html'))throw new Error(`Missing local data: ${path} (HTTP ${r.status})`);return r.json() as Promise<T>;}
async function getFloats(path:string):Promise<Float32Array>{const r=await fetch(`/world/${path}`);if(!r.ok||r.headers.get('content-type')?.includes('text/html'))throw new Error(`Missing height data: ${path}`);return new Float32Array(await r.arrayBuffer());}
function heightAt(x:number,z:number){
  if(!elevation)return 0;
  const col=THREE.MathUtils.clamp((x+5000)/10,0,1000),row=THREE.MathUtils.clamp((z+5000)/10,0,1000),c=Math.floor(col),r=Math.floor(row),c1=Math.min(1000,c+1),r1=Math.min(1000,r+1),fx=col-c,fy=row-r;
  const v=elevation[r*1001+c]*(1-fx)*(1-fy)+elevation[r*1001+c1]*fx*(1-fy)+elevation[r1*1001+c]*(1-fx)*fy+elevation[r1*1001+c1]*fx*fy;return Number.isFinite(v)&&v>-1000?v:0;
}
function stepFor(i:TileInfo){const d=Math.hypot(i.x+500-camera.position.x,-i.north+500-camera.position.z,camera.position.y);return d<2600?1:d<5200?2:4;}
async function loadTile(info:TileInfo){
  pending.add(info.id);activeLoads++;let texture:THREE.Texture|undefined,mask:THREE.Texture|undefined;
  try{
    const [heightResult,textureResult,maskResult]=await Promise.allSettled([getFloats(info.heights),textureLoader.loadAsync(`/world/${info.imagery}`),textureLoader.loadAsync(`/world/${info.surface}`)]);
    if(heightResult.status==='rejected'||textureResult.status==='rejected'||maskResult.status==='rejected'){
      if(textureResult.status==='fulfilled')textureResult.value.dispose();
      if(maskResult.status==='fulfilled')maskResult.value.dispose();
      throw new Error('A tile height buffer or image could not be loaded');
    }
    const heights=heightResult.value;texture=textureResult.value;mask=maskResult.value;
    if(heights.length!==10201)throw new Error('Unexpected tile height count');if(disposed){texture.dispose();mask.dispose();return;}
    texture.colorSpace=THREE.SRGBColorSpace;texture.anisotropy=Math.min(4,renderer.capabilities.getMaxAnisotropy());const step=stepFor(info);
    const material=makeTerrainMaterial(mask,texture,imagery,wireframe,landscapeControls,terrainRelief,groundTextures);
    const mesh=new THREE.Mesh(terrainGeometry(heights,step),material);mesh.position.set(info.x,0,-info.north);mesh.name=`Terrain ${info.id}`;
    terrainGroup.add(mesh);fallbackTiles.get(info.id)!.visible=false;tileStates.set(info.id,{info,mesh,heights,texture,mask,step});loaded++;if(loaded===1){loading.hidden=failedTiles===0;debug.ready=true;}if(loaded%5===0)updateSummary();
  }catch(error){texture?.dispose();mask?.dispose();failedTiles++;failedIds.add(info.id);console.error('Tile load failed',info.id,error);setMessage('Some terrain could not load',`Tile ${info.id} is unavailable. Run npm run data, then reload.`,true);}
  finally{pending.delete(info.id);activeLoads--;if(!disposed)stream();}
}
function disposeTile(id:string){const s=tileStates.get(id);if(!s)return;terrainGroup.remove(s.mesh);s.mesh.geometry.dispose();(s.mesh.material as THREE.Material).dispose();s.texture.dispose();s.mask.dispose();tileStates.delete(id);fallbackTiles.get(id)!.visible=true;}
function stream(){if(!manifest||!worldInitialized)return;const ordered=manifest.tiles.map(info=>({info,d:Math.hypot(info.x+500-camera.position.x,-info.north+500-camera.position.z)})).sort((a,b)=>a.d-b.d);
  for(const {info,d} of ordered){const s=tileStates.get(info.id);if(s&&d>12500){disposeTile(info.id);continue;}if(s){const step=stepFor(info);if(s.step!==step){s.mesh.geometry.dispose();s.mesh.geometry=terrainGeometry(s.heights,step);s.step=step;}continue;}if(d<11500&&activeLoads<4&&!pending.has(info.id)&&!failedIds.has(info.id))void loadTile(info);}}
function updateSummary(){if(manifest)el('data-summary').textContent=`10 × 10 km · ${manifest.stats.buildings.toLocaleString()} buildings${failedTiles?` · ${failedTiles} missing tiles`:''}`;}
async function makeFallbackTerrain(){
  [overviewTexture,overviewMask]=await Promise.all([textureLoader.loadAsync(`/world/${manifest.overview}`),textureLoader.loadAsync(`/world/${manifest.surface.overview}`)]);overviewTexture.colorSpace=THREE.SRGBColorSpace;
  fallbackMaterial=makeTerrainMaterial(overviewMask,overviewTexture,imagery,wireframe,landscapeControls,terrainRelief,groundTextures,true);
  for(const info of manifest.tiles){
    const heights=new Float32Array(10201);
    for(let r=0;r<=100;r++)for(let c=0;c<=100;c++){const h=elevation[(info.row*100+r)*1001+info.col*100+c];heights[r*101+c]=h>-1000?h:NaN;}
    const geometry=terrainGeometry(heights,4),uv=geometry.getAttribute('uv');
    for(let i=0;i<uv.count;i++)uv.setXY(i,(info.col+uv.getX(i))/10,(9-info.row+uv.getY(i))/10);
    const mesh=new THREE.Mesh(geometry,fallbackMaterial);mesh.position.set(info.x,0,-info.north);mesh.name=`Terrain overview ${info.id}`;terrainGroup.add(mesh);fallbackTiles.set(info.id,mesh);
  }
}
function makeBuildings(){const g=buildingGeometry(features.buildings),m=new THREE.MeshStandardMaterial({vertexColors:true,roughness:.9,side:THREE.DoubleSide});const walls=new THREE.Mesh(g.walls,m),roofs=new THREE.Mesh(g.roofs,m);walls.name='Building walls';roofs.name='Building roofs';walls.userData.owners=g.wallOwners;roofs.userData.owners=g.roofOwners;buildingsGroup.add(walls,roofs);pickMeshes.push(walls,roofs);}
function makeRoads(){const m=makeRoadMaterial();roadsGroup.add(new THREE.Mesh(roadsGeometry(features.roads,false),m),new THREE.Mesh(roadsGeometry(features.roads,true),m));}
function makeTrees(){
  const chunks=new Map<string,number[][]>();
  for(const plant of features.trees){
    const key=`${Math.min(9,Math.max(0,Math.floor((plant[0]+5000)/1000)))}-${Math.min(9,Math.max(0,Math.floor((5000-plant[1])/1000)))}`;
    if(!chunks.has(key))chunks.set(key,[]);chunks.get(key)!.push(plant);
  }
  const fineGeometry=new THREE.IcosahedronGeometry(1,0),farGeometry=new THREE.OctahedronGeometry(1,0);
  const trunkGeometry=new THREE.CylinderGeometry(.2,.32,1,4);
  const leafMaterial=makeLeafMaterial(landscapeControls);
  const trunkMaterial=new THREE.MeshStandardMaterial({color:'#6e6550',roughness:1});
  const object=new THREE.Object3D(),up=new THREE.Vector3(0,1,0),surfaceNormal=new THREE.Vector3();
  for(const [key,plants] of chunks){
    const [col,row]=key.split('-').map(Number),cx=-4500+col*1000,north=4500-row*1000;
    const tallCount=plants.filter(t=>t[6]!==1&&t[3]>=4).length;
    const crowns=new THREE.InstancedMesh(fineGeometry,leafMaterial,plants.length);
    const farCrowns=new THREE.InstancedMesh(farGeometry,leafMaterial,plants.length);
    const trunks=new THREE.InstancedMesh(trunkGeometry,trunkMaterial,tallCount);
    let trunkIndex=0;const trunkIndices=new Int32Array(plants.length).fill(-1);
    plants.forEach((plant,i)=>{
      const [x,n,z,h,rotation]=plant,shrub=plant[6]===1,radius=plant[5]??h*.34;
      object.rotation.set(0,rotation,0);
      if(!shrub&&h>=4){object.position.set(x-cx,z+h*.25,-n+north);object.scale.set(1,h*.5,1);object.updateMatrix();trunkIndices[i]=trunkIndex;trunks.setMatrixAt(trunkIndex++,object.matrix);}
      if(shrub){
        const worldZ=-n;
        surfaceNormal.set(heightAt(x-4,worldZ)-heightAt(x+4,worldZ),8,heightAt(x,worldZ-4)-heightAt(x,worldZ+4)).normalize();
        object.quaternion.setFromUnitVectors(up,surfaceNormal);object.rotateY(rotation);
        const halfHeight=h*.5*surfaceNormal.y;
        object.position.set(x-cx+surfaceNormal.x*halfHeight,z+surfaceNormal.y*halfHeight,-n+north+surfaceNormal.z*halfHeight);
        object.scale.set(radius,halfHeight,radius);
      }else{
        object.position.set(x-cx,z+h*.63,-n+north);object.scale.set(radius,h*.4,radius);
      }
      object.updateMatrix();crowns.setMatrixAt(i,object.matrix);
      crowns.setColorAt(i,plant[7]!==undefined?new THREE.Color(plant[7]):new THREE.Color().setHSL(.24+(i%7)*.008,.17+(i%5)*.025,.19+(i%9)*.012));
    });
    crowns.name='Vegetation canopy';trunks.name='Vegetation trunks';farCrowns.name='Distant vegetation canopy';
    crowns.instanceMatrix.needsUpdate=true;trunks.instanceMatrix.needsUpdate=true;
    farCrowns.instanceMatrix=crowns.instanceMatrix;farCrowns.instanceColor=crowns.instanceColor;
    crowns.computeBoundingSphere();farCrowns.computeBoundingSphere();trunks.computeBoundingSphere();
    const near=new THREE.Group();near.add(crowns,trunks);
    const lod=new THREE.LOD();lod.name=`Vegetation ${key}`;lod.position.set(cx,0,-north);lod.addLevel(near,0);lod.addLevel(farCrowns,1800);vegetationGroup.add(lod);
    nativePlants.register({plants,crowns,trunks,trunkIndices,cx,north});
  }
}
function makeWater(){const mesh=new THREE.Mesh(waterGeometry(features.water),new THREE.MeshStandardMaterial({color:'#457c80',roughness:.38,metalness:.14,side:THREE.DoubleSide}));mesh.name='Whakaraupō water';scene.add(mesh);}
function fillSources(){for(const s of manifest.sources.filter(s=>s.title.includes('DEM')||s.title.includes('Aerial'))){const a=document.createElement('a');a.href=s.url;a.target='_blank';a.rel='noopener';a.textContent=s.title;el('survey-info').append(a,document.createElement('br'));}
  const providers=document.createElement('p');providers.textContent='Survey providers: '+[...new Set(manifest.sources.flatMap(s=>s.providers.map(p=>p.name)))].join('; ')+'.';el('survey-info').append(providers);
  const surfaceNote=document.createElement('p');surfaceNote.textContent=`Ground: generated grass, rock, soil and paving materials. ${manifest.surface.canopyPeaks.toLocaleString()} canopy peaks plus ${manifest.surface.canopyFillInstances?.toLocaleString()??'0'} coverage clusters reconstruct vegetation; ${manifest.surface.roofColors.toLocaleString()} roofs use sampled colours. Classification uses RGB/height rules, with OSM geometry constraints; it is not a trained semantic model.`;el('sources').append(surfaceNote);
  const c=manifest.stats.roofSources;el('roof-info').textContent=`${c.dsm.toLocaleString()} buildings use measured surface heights; ${manifest.stats.fittedGables.toLocaleString()} have fitted gable roofs. ${c.osm.toLocaleString()} use OSM heights and ${c.default.toLocaleString()} use a 6 m default. Terrain: 10 m. Imagery: 1 m.`;
  for(const text of manifest.approximations){const li=document.createElement('li');li.textContent=text;el('limitations').append(li);}if(manifest.missingLandPixels2m){const p=document.createElement('p');p.textContent=`${(manifest.missingLandPixels2m*4).toLocaleString()} m² lacks land elevation; affected terrain triangles are omitted.`;el('sources').append(p);}}
const viewpoints:Record<string,{position:number[];target:number[]}>= {harbour:{position:[2400,2300,4400],target:[-200,100,-100]},town:{position:[650,470,650],target:[-140,90,-230]},hills:{position:[-1100,1250,-2500],target:[-1600,420,-700]},diamond:{position:[900,1100,4100],target:[-100,80,2900]}};
let flight:{from:THREE.Vector3;to:THREE.Vector3;targetFrom:THREE.Vector3;targetTo:THREE.Vector3;t:number}|null=null;
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
function setMode(value:boolean){fly=value;flight=null;controls.enabled=!fly;keys.clear();el('orbit').setAttribute('aria-pressed',String(!fly));el('fly').setAttribute('aria-pressed',String(fly));el('navigation-help').innerHTML=fly?'Drag to look · W A S D to move<br>Q / E down / up · Shift to speed up':'Drag to orbit · scroll to zoom<br>Right-drag to pan';if(fly){flyEuler.setFromQuaternion(camera.quaternion);canvas.focus();}else{camera.getWorldDirection(direction);controls.target.copy(camera.position).addScaledVector(direction,Math.max(100,camera.position.y*.8));controls.update();}}
function goTo(name:string){const view=viewpoints[name];if(!view)return;setMode(false);closeSelection();const to=new THREE.Vector3(...view.position as [number,number,number]),targetTo=new THREE.Vector3(...view.target as [number,number,number]);if(reducedMotion){camera.position.copy(to);controls.target.copy(targetTo);controls.update();}else flight={from:camera.position.clone(),to,targetFrom:controls.target.clone(),targetTo,t:0};document.querySelectorAll<HTMLButtonElement>('[data-view]').forEach(b=>{b.classList.toggle('selected',b.dataset.view===name);b.setAttribute('aria-pressed',String(b.dataset.view===name));});}
el('orbit').addEventListener('click',()=>setMode(false));el('fly').addEventListener('click',()=>setMode(true));el('reset').addEventListener('click',()=>goTo('harbour'));document.querySelectorAll<HTMLButtonElement>('[data-view]').forEach(b=>b.addEventListener('click',()=>goTo(b.dataset.view!)));
for(const [id,group] of [['buildings',buildingsGroup],['roads',roadsGroup],['vegetation',vegetationGroup]] as const)el<HTMLInputElement>(id).addEventListener('change',e=>{group.visible=(e.target as HTMLInputElement).checked;if(id==='buildings'&&!group.visible)closeSelection();});
el<HTMLInputElement>('imagery').addEventListener('change',e=>{imagery=(e.target as HTMLInputElement).checked;if(fallbackMaterial)setTerrainReference(fallbackMaterial,imagery);for(const s of tileStates.values()){setTerrainReference(s.mesh.material as THREE.MeshStandardMaterial,imagery);}});
el<HTMLInputElement>('wireframe').addEventListener('change',e=>{wireframe=(e.target as HTMLInputElement).checked;if(fallbackMaterial)fallbackMaterial.wireframe=wireframe;for(const s of tileStates.values())(s.mesh.material as THREE.MeshStandardMaterial).wireframe=wireframe;});
el('panel-toggle').addEventListener('click',()=>{const content=el('panel-content');content.hidden=!content.hidden;el('panel-toggle').setAttribute('aria-expanded',String(!content.hidden));});el('sources-toggle').addEventListener('click',()=>{el('sources').hidden=!el('sources').hidden;el('sources-toggle').setAttribute('aria-expanded',String(!el('sources').hidden));});
if(innerWidth<700){el('panel-content').hidden=true;el('panel-toggle').setAttribute('aria-expanded','false');}
function closeSelection(){selectedBuilding=null;el('inspector').hidden=true;if(selectionOutline){scene.remove(selectionOutline);selectionOutline.geometry.dispose();(selectionOutline.material as THREE.Material).dispose();selectionOutline=null;}}
el('close-inspector').addEventListener('click',closeSelection);
function selectBuilding(b:Building){closeSelection();selectedBuilding=b;el('building-title').textContent=b.name||'Lyttelton building';const source={dsm:'Measured DSM',osm:'OSM attribute',default:'Procedural default'}[b.roof.source];const rows=[['Height',`${b.roof.height.toFixed(1)} m`],['Roof',b.roof.kind==='gable'?'Fitted gable':'Flat approximation'],['Height source',source],['Roof fit',b.roof.error===null?'Not measured':`${b.roof.error.toFixed(2)} m RMSE`]];el('building-details').replaceChildren();for(const [term,value] of rows){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=term;dd.textContent=value;el('building-details').append(dt,dd);}
  const a=document.createElement('a');a.href=`https://www.openstreetmap.org/${b.id}`;a.target='_blank';a.rel='noopener';a.textContent='View OSM feature';const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent='Footprint';dd.append(a);el('building-details').append(dt,dd);el('inspector').hidden=false;selectionOutline=new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(b.ring.map(p=>new THREE.Vector3(p[0],b.ground+b.roof.height+1,-p[1]))),new THREE.LineBasicMaterial({color:'#f3c45e',depthTest:false}));selectionOutline.renderOrder=10;scene.add(selectionOutline);}
const raycaster=new THREE.Raycaster();
canvas.addEventListener('pointerdown',e=>{canvas.focus();dragging=true;startX=lastX=e.clientX;startY=lastY=e.clientY;if(fly)canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener('pointermove',e=>{if(fly&&dragging){flyEuler.y-=(e.clientX-lastX)*.003;flyEuler.x=THREE.MathUtils.clamp(flyEuler.x-(e.clientY-lastY)*.003,-Math.PI*.48,Math.PI*.48);camera.quaternion.setFromEuler(flyEuler);}lastX=e.clientX;lastY=e.clientY;});
canvas.addEventListener('pointerup',e=>{dragging=false;if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);if(fly||Math.hypot(e.clientX-startX,e.clientY-startY)>5||!features||!buildingsGroup.visible)return;const r=canvas.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),camera);const hit=raycaster.intersectObjects([...pickMeshes,...terrainGroup.children.filter(m=>m.visible)],false)[0];if(hit?.object.userData.owners&&hit.faceIndex!==undefined&&hit.faceIndex!==null)selectBuilding(features.buildings[hit.object.userData.owners[hit.faceIndex]]);else closeSelection();});
canvas.addEventListener('pointercancel',()=>dragging=false);canvas.addEventListener('wheel',e=>{if(fly){e.preventDefault();flySpeed=THREE.MathUtils.clamp(flySpeed*Math.exp(-e.deltaY*.001),10,1200);}},{passive:false});canvas.addEventListener('contextmenu',e=>e.preventDefault());
canvas.addEventListener('keydown',e=>{if(['KeyW','KeyA','KeyS','KeyD','KeyQ','KeyE','ShiftLeft','ShiftRight','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.code)){keys.add(e.code);if(fly)e.preventDefault();}if(e.code==='Escape')closeSelection();});window.addEventListener('keyup',e=>keys.delete(e.code));window.addEventListener('blur',()=>{keys.clear();dragging=false;});canvas.addEventListener('blur',()=>keys.clear());controls.addEventListener('start',()=>flight=null);
let streamTimer=0,footerTimer=0,plantTimer=0;
function frame(){if(disposed)return;const elapsed=clock.getDelta(),dt=Math.min(elapsed,.05);if(flight){flight.t=Math.min(1,flight.t+elapsed/.95);const t=1-Math.pow(1-flight.t,4);camera.position.lerpVectors(flight.from,flight.to,t);controls.target.lerpVectors(flight.targetFrom,flight.targetTo,t);if(flight.t===1)flight=null;}
  if(fly){move.set(Number(keys.has('KeyD')||keys.has('ArrowRight'))-Number(keys.has('KeyA')||keys.has('ArrowLeft')),0,Number(keys.has('KeyS')||keys.has('ArrowDown'))-Number(keys.has('KeyW')||keys.has('ArrowUp')));if(move.lengthSq()>0)move.normalize().applyQuaternion(camera.quaternion);move.y+=Number(keys.has('KeyE'))-Number(keys.has('KeyQ'));camera.position.addScaledVector(move,flySpeed*(keys.has('ShiftLeft')||keys.has('ShiftRight')?4:1)*dt);camera.position.x=THREE.MathUtils.clamp(camera.position.x,-7500,7500);camera.position.z=THREE.MathUtils.clamp(camera.position.z,-7500,7500);camera.position.y=THREE.MathUtils.clamp(camera.position.y,Math.max(4,heightAt(camera.position.x,camera.position.z)+4),9500);}else controls.update();
  plantTimer+=elapsed;if(plantTimer>.5){plantTimer=0;nativePlants.update(camera);}
  streamTimer+=elapsed;if(streamTimer>.35){streamTimer=0;stream();}footerTimer+=elapsed;if(footerTimer>.25){footerTimer=0;el('camera-height').textContent=`${Math.round(camera.position.y).toLocaleString()} m elevation`;camera.getWorldDirection(direction);el('north-arrow').style.transform=`rotate(${Math.atan2(direction.x,-direction.z)*180/Math.PI}deg)`;}renderer.render(scene,camera);requestAnimationFrame(frame);}
async function start(){try{manifest=await get<Manifest>('manifest.json');debug.manifest=manifest;if(manifest.version!==1||manifest.extentMeters!==10000||!manifest.surface)throw new Error('Unsupported world manifest');detail.textContent='Loading measured terrain and generated scenery…';[features,elevation]=await Promise.all([get<Features>(manifest.features),getFloats(manifest.elevation)]);if(elevation.length!==1002001)throw new Error('Unexpected world elevation size');landscapeControls=await textureLoader.loadAsync(`/world/${manifest.surface.landscapeControls}`);landscapeControls.colorSpace=THREE.NoColorSpace;terrainRelief=await textureLoader.loadAsync(`/world/${manifest.surface.terrainRelief}`);terrainRelief.colorSpace=THREE.NoColorSpace;groundTextures=await loadGroundTextures(Math.min(8,renderer.capabilities.getMaxAnisotropy()));await makeFallbackTerrain();makeWater();makeBuildings();makeRoads();makeTrees();fillSources();updateSummary();worldInitialized=true;stream();void nativePlants.load(()=>{
      const p=document.createElement('p');p.id='native-plant-info';
      p.textContent=nativePlants.status.loaded?'Nearby vegetation uses detailed tree and scrub models within a bounded rendering budget. The cabbage tree is a named species; broadleaf tree and scrub assets are representative foliage, not verified NZ species. Species placement is illustrative, inferred from height and vegetation class; individual species are not identified in the aerial data.':'Detailed native plant assets have not been installed. Vegetation uses approximate generated crowns and scrub.';el('sources').append(p);
      const surfaceCredit=document.createElement('p'),surfaceLink=document.createElement('a');surfaceLink.href='https://polyhaven.com';surfaceLink.target='_blank';surfaceLink.rel='noopener';surfaceLink.textContent='Ground scans and representative foliage: Powered by Poly Haven · CC0';surfaceCredit.append(surfaceLink);el('sources').append(surfaceCredit);
      for(const credit of nativePlants.credits){const p=document.createElement('p'),a=document.createElement('a');a.href=credit.source;a.target='_blank';a.rel='noopener';a.textContent=`${credit.species} — ${credit.author} (${credit.license})`;p.append(a);el('sources').append(p);}
      if(nativePlants.status.species.length){const button=document.createElement('button');button.textContent='Native plants';button.id='native-plant-view';button.addEventListener('click',()=>{const view=choosePlantView(nativePlants.previewOptions(),p=>nativePlants.neighbours(p),features.buildings,heightAt,THREE.MathUtils.degToRad(camera.fov),camera.aspect);if(!view)return;setMode(false);closeSelection();document.querySelectorAll<HTMLButtonElement>('[data-view]').forEach(b=>{b.classList.remove('selected');b.setAttribute('aria-pressed','false');});camera.position.copy(view.position);controls.target.copy(view.target);controls.update();nativePlants.update(camera);});document.querySelector('.views')!.append(button);}
    });}catch(error){console.error(error);setMessage('Local world data is not ready','Run npm run data in lyttelton-world, then reload. Details: '+(error instanceof Error?error.message:String(error)),true);}}
window.addEventListener('beforeunload',()=>{disposed=true;for(const id of tileStates.keys())disposeTile(id);for(const mesh of fallbackTiles.values())mesh.geometry.dispose();fallbackMaterial?.dispose();overviewTexture?.dispose();overviewMask?.dispose();landscapeControls?.dispose();terrainRelief?.dispose();nativePlants.dispose();if(groundTextures)disposeGroundTextures(groundTextures);controls.dispose();renderer.dispose();});frame();void start();
