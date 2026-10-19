import * as THREE from 'three';
import type {Road} from './types';

/** Road, footpath and track ribbons draped on the displayed terrain.
 * Surfaces use CC0 Poly Haven scans at their recorded physical scale. Lane
 * markings are generated from OSM class and width: they are conventions, not
 * surveyed paint.
 */
export type RoadSurface='road'|'footpath'|'track';
const FOOTPATH=new Set(['footway','pedestrian','steps','cycleway','platform','corridor']);
const TRACK=new Set(['path','track','bridleway','via_ferrata']);
const SKIP=new Set(['proposed','construction','abandoned','razed','raceway']);
const SEALED=new Set(['asphalt','paved','concrete','concrete:plates','concrete:lanes','paving_stones','sett','chipseal','metal','wood']);
const UNSEALED=new Set(['gravel','fine_gravel','unpaved','compacted','ground','dirt','earth','grass','sand','mud','pebblestone','woodchips','rock']);
const PRIORITY:Record<string,number>={trunk:9,trunk_link:9,primary:8,primary_link:8,secondary:7,secondary_link:7,tertiary:6,tertiary_link:6,unclassified:5,residential:5,busway:4,service:3,living_street:2,track:2};
const CENTRE_LINE=new Set(['trunk','primary','secondary','tertiary','residential','unclassified','trunk_link','primary_link','secondary_link','tertiary_link']);
const EDGE_LINES=new Set(['trunk','primary','secondary','trunk_link','primary_link','secondary_link']);

// Physical tile sizes are recorded in public/materials/sources.json. Linear
// tints rescale each scan's mean colour to the median aerial colour sampled
// along mapped centrelines (about 112,116,112 sRGB for sealed roads).
const SURFACES:Record<RoadSurface,{slug:string;tile:number;tint:[number,number,number];roughness:number}>={
  road:{slug:'tarred_gravel',tile:2.2,tint:[3.45,4.29,4.94],roughness:.92},
  footpath:{slug:'asphalt_floor',tile:2.35,tint:[.72,.97,1.2],roughness:.9},
  track:{slug:'gravel_road',tile:2,tint:[1.13,1.69,2.15],roughness:1},
};

/** OSM surface tags override the class default, e.g. sealed paths, gravel lanes. */
export function surfaceOf(road:Road):RoadSurface|null {
  const kind=road.kind,surface=road.surface??'';
  if(SKIP.has(kind))return null;
  if(road.crossing)return 'road';
  if(UNSEALED.has(surface))return 'track';
  if(SEALED.has(surface)&&TRACK.has(kind))return 'footpath';
  return FOOTPATH.has(kind)?'footpath':TRACK.has(kind)?'track':'road';
}

interface Segment {road:number;ax:number;ay:number;bx:number;by:number}
/** Endpoints that meet another road: markings stop short of the junction. */
function junctionCuts(roads:Road[]):Map<Road,[number,number]> {
  const cell=8,grid=new Map<string,Segment[]>(),cuts=new Map<Road,[number,number]>();
  roads.forEach((road,index)=>{
    for(let i=0;i<road.points.length-1;i++){
      const [ax,ay]=road.points[i],[bx,by]=road.points[i+1],segment={road:index,ax,ay,bx,by};
      for(let cx=Math.floor(Math.min(ax,bx)/cell);cx<=Math.floor(Math.max(ax,bx)/cell);cx++)
        for(let cy=Math.floor(Math.min(ay,by)/cell);cy<=Math.floor(Math.max(ay,by)/cell);cy++){
          const key=`${cx},${cy}`;if(!grid.has(key))grid.set(key,[]);grid.get(key)!.push(segment);
        }
    }
  });
  const cutAt=(index:number,x:number,y:number)=>{
    let cut=0;
    for(let cx=Math.floor(x/cell)-1;cx<=Math.floor(x/cell)+1;cx++)for(let cy=Math.floor(y/cell)-1;cy<=Math.floor(y/cell)+1;cy++)
      for(const s of grid.get(`${cx},${cy}`)??[]){
        if(s.road===index)continue;
        const dx=s.bx-s.ax,dy=s.by-s.ay,t=THREE.MathUtils.clamp(((x-s.ax)*dx+(y-s.ay)*dy)/Math.max(dx*dx+dy*dy,1e-6),0,1);
        if(Math.hypot(s.ax+dx*t-x,s.ay+dy*t-y)<1.5)cut=Math.max(cut,roads[s.road].width/2+4);
      }
    return cut;
  };
  roads.forEach((road,index)=>{
    const a=road.points[0],b=road.points[road.points.length-1];
    cuts.set(road,[cutAt(index,a[0],a[1]),cutAt(index,b[0],b[1])]);
  });
  return cuts;
}

export function roadGeometry(roads:Road[],surface:RoadSurface,heightAt:(x:number,z:number)=>number):THREE.BufferGeometry {
  // Junction cuts consider every carriageway, including other surface types.
  const vehicle=roads.filter(r=>surfaceOf(r)==='road'&&!r.crossing);
  const cuts=junctionCuts(vehicle);
  const priority=(r:Road)=>r.crossing?10:PRIORITY[r.kind]??1;
  const selected=roads.filter(r=>surfaceOf(r)===surface&&r.points.length>1).sort((a,b)=>priority(a)-priority(b));
  const position:number[]=[],uv:number[]=[],mark:number[]=[],info:number[]=[],index:number[]=[];
  const tile=SURFACES[surface].tile;
  for(const road of selected){
    // Painted crossings are drawn as a 3 m band over the carriageway.
    const width=road.crossing?3:road.width,p=road.points,half=width/2,rank=priority(road);
    const marking=road.crossing?(road.crossing==='zebra'?3:4):surface!=='road'||width<5.5?0:EDGE_LINES.has(road.kind)?2:CENTRE_LINE.has(road.kind)?1:0;
    const [startCut,endCut]=cuts.get(road)??[0,0];
    let length=0;for(let i=1;i<p.length;i++)length+=Math.hypot(p[i][0]-p[i-1][0],p[i][1]-p[i-1][1]);
    const base=position.length/3;let distance=0;
    for(let i=0;i<p.length;i++){
      if(i>0)distance+=Math.hypot(p[i][0]-p[i-1][0],p[i][1]-p[i-1][1]);
      const prev=p[Math.max(0,i-1)],next=p[Math.min(p.length-1,i+1)];
      let tx=next[0]-prev[0],ty=next[1]-prev[1];const tl=Math.hypot(tx,ty)||1;tx/=tl;ty/=tl;
      // Mitre joins keep the ribbon width constant through bends.
      let miter=1;
      if(i>0&&i<p.length-1){
        const sx=p[i+1][0]-p[i][0],sy=p[i+1][1]-p[i][1],sl=Math.hypot(sx,sy)||1;
        miter=1/Math.max(.55,(tx*sx+ty*sy)/sl);
      }
      const nx=-ty*half*miter,ny=tx*half*miter;
      for(const side of [-1,0,1]){
        const x=p[i][0]+nx*side,north=p[i][1]+ny*side;
        // Drape each cross-section point; bridges keep their interpolated deck.
        const y=road.bridge?p[i][2]:Math.max(heightAt(x,-north),side===0?p[i][2]-.3:-Infinity)+.18;
        position.push(x,y,-north);
        uv.push(side*half*miter/tile,distance/tile);
        mark.push(side*half,distance,width,length);
        info.push(marking,rank,startCut,endCut);
      }
      if(i>0){
        const a=base+(i-1)*3,b=base+i*3;
        index.push(a,b,a+1,a+1,b,b+1,a+1,b+1,a+2,a+2,b+1,b+2);
      }
    }
  }
  const g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.Float32BufferAttribute(position,3));
  g.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));
  g.setAttribute('aMark',new THREE.Float32BufferAttribute(mark,4));
  g.setAttribute('aInfo',new THREE.Float32BufferAttribute(info,4));
  g.setIndex(index);g.computeVertexNormals();g.computeBoundingSphere();
  return g;
}

export interface RoadTextures {map:THREE.Texture;normal:THREE.Texture}
export async function loadRoadTextures(anisotropy:number):Promise<Record<RoadSurface,RoadTextures>> {
  const loader=new THREE.TextureLoader();
  const entries=await Promise.all((Object.keys(SURFACES) as RoadSurface[]).map(async surface=>{
    const slug=SURFACES[surface].slug;
    const [map,normal]=await Promise.all(['Diffuse','nor_gl'].map(channel=>loader.loadAsync(`/materials/${slug}-${channel}.jpg`)));
    for(const t of [map,normal]){t.wrapS=t.wrapT=THREE.RepeatWrapping;t.anisotropy=anisotropy;}
    map.colorSpace=THREE.SRGBColorSpace;
    return [surface,{map,normal}] as const;
  }));
  return Object.fromEntries(entries) as Record<RoadSurface,RoadTextures>;
}

export function makeRoadSurfaceMaterial(surface:RoadSurface,textures:RoadTextures):THREE.MeshStandardMaterial {
  const spec=SURFACES[surface];
  const material=new THREE.MeshStandardMaterial({map:textures.map,normalMap:textures.normal,normalScale:new THREE.Vector2(.8,.8),color:new THREE.Color().setRGB(...spec.tint),roughness:spec.roughness,side:THREE.DoubleSide});
  material.customProgramCacheKey=()=>`world-road-surface-v1-${surface}`;
  material.onBeforeCompile=shader=>{
    shader.vertexShader=shader.vertexShader
      .replace('#include <common>','#include <common>\nattribute vec4 aMark;\nattribute vec4 aInfo;\nvarying vec4 vMark;\nvarying vec4 vInfo;')
      .replace('#include <project_vertex>',`#include <project_vertex>
        vMark=aMark;vInfo=aInfo;
        // Pull draped ribbons slightly toward the camera so coarser terrain
        // levels of detail cannot cover them; higher classes win overlaps.
        mvPosition.xyz*=1.0-(0.0012+aInfo.y*0.00006);
        gl_Position=projectionMatrix*mvPosition;`);
    shader.fragmentShader=shader.fragmentShader
      .replace('#include <common>','#include <common>\nvarying vec4 vMark;\nvarying vec4 vInfo;')
      .replace('#include <map_fragment>',`#include <map_fragment>
        float across=vMark.x,along=vMark.y,width=vMark.z,total=vMark.w,edge=width*0.5-abs(across);
        float aa=max(fwidth(across),0.002),sa=max(fwidth(along),0.002);
        ${surface==='track'?`
        // Worn wheel ruts and a grassy crown on unsealed tracks.
        diffuseColor.rgb*=mix(1.0,0.86,smoothstep(0.5,0.0,abs(abs(across)-width*0.22)));
        diffuseColor.rgb=mix(diffuseColor.rgb,vec3(0.36,0.39,0.25),0.35*smoothstep(0.35,0.05,abs(across))*step(2.0,width));
        diffuseColor.rgb=mix(diffuseColor.rgb,vec3(0.42,0.43,0.3),0.4*smoothstep(0.35,0.0,edge));`:`
        // Darker gutters at the edges; slightly lighter wheel paths.
        diffuseColor.rgb*=mix(0.8,1.0,smoothstep(0.0,0.45,edge));
        diffuseColor.rgb*=1.0+0.05*smoothstep(1.2,0.3,abs(abs(across)-width*0.25))*step(4.0,width);`}
        float visible=1.0-smoothstep(0.06,0.18,aa);
        float marked=step(vInfo.z,along)*step(along,total-vInfo.w)*step(0.5,vInfo.x)*step(vInfo.x,2.5);
        float centre=(1.0-smoothstep(0.05,0.05+aa,abs(across)))*smoothstep(0.0,sa,(0.15-abs(fract(along/10.0)-0.15))*10.0); // 3 m dashes, 7 m gaps
        float edges=step(1.5,vInfo.x)*(1.0-smoothstep(0.05,0.05+aa,abs(edge-0.35)));
        // Zebra bars lie along the traffic direction and alternate along the
        // walking line (0.6 m white, 0.6 m gaps); signalised crossings get two lines.
        float ends=step(0.6,along)*step(along,total-0.6);
        float zebra=step(2.5,vInfo.x)*step(vInfo.x,3.5)*smoothstep(0.0,sa,(0.25-abs(fract(along/1.2)-0.5))*1.2)*step(0.3,edge)*ends;
        zebra=max(zebra,step(3.5,vInfo.x)*(1.0-smoothstep(0.1,0.1+aa,abs(edge-0.15)))*ends);
        diffuseColor.rgb=mix(diffuseColor.rgb,vec3(0.86,0.86,0.82),clamp(max(max(centre,edges)*marked,zebra)*visible,0.0,1.0)*0.92);`);
  };
  return material;
}
