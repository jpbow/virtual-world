import * as THREE from 'three';

/** Live LINZ Basemaps aerial tiles for Aerial reference mode.
 *
 * Tiles come from the NZTM2000Quad grid (EPSG:2193, the world's own CRS), so
 * no reprojection is needed. A quadtree splits each tile while its pixels
 * would look coarser than ~1.5 screen pixels, down to zoom 19 (≈7.5 cm).
 * Each leaf is a small terrain patch drawn just in front of the local
 * terrain; a parent stays visible until its children have loaded. Without
 * an API key or network, the local 1 m reference tiles remain.
 */
const ORIGIN_E=-3260586.7284,ORIGIN_N=10438190.1652;
// NZTM2000Quad zoom 0 cell size (scale denominator × 0.28 mm).
const CELL0=139770566.007179*0.00028;
const ROOT_ZOOM=12,MAX_ZOOM=19,MAX_LOADING=8,CACHE_LIMIT=800;
const tileMeters=(z:number)=>256*CELL0/2**z;

interface Node {key:string;z:number;x:number;y:number}
interface Entry {mesh:THREE.Mesh|null;state:'loading'|'ready'|'failed';used:number}

export class BasemapTiles {
  readonly group=new THREE.Group();
  readonly status={enabled:false,configured:false,covering:false,visible:0,loading:0,loaded:0,failed:0,maxZoom:0};
  private frustum=new THREE.Frustum();private box=new THREE.Box3();private matrix=new THREE.Matrix4();
  private cache=new Map<string,Entry>();
  private queue:{node:Node;priority:number}[]=[];
  private loader=new THREE.TextureLoader();
  private frame=0;private disposed=false;

  constructor(private key:string|undefined,private origin:[number,number],private heightAt:(x:number,z:number)=>number,private anisotropy:number){
    this.group.name='LINZ Basemaps aerial';this.status.configured=Boolean(key);
    this.loader.setCrossOrigin('anonymous');
  }

  private url(n:Node){return `https://basemaps.linz.govt.nz/v1/tiles/aerial/NZTM2000Quad/${n.z}/${n.x}/${n.y}.webp?api=${encodeURIComponent(this.key!)}`;}

  /** Local east/north rectangle of a tile, clipped to the 10 km world. */
  private rect(n:Node){
    const t=tileMeters(n.z),[cx,cy]=this.origin;
    const e0=ORIGIN_E+n.x*t-cx,n1=ORIGIN_N-n.y*t-cy;
    return{e0,e1:e0+t,n0:n1-t,n1,clip:[Math.max(-5000,e0),Math.min(5000,e0+t),Math.max(-5000,n1-t),Math.min(5000,n1)] as const};
  }

  update(camera:THREE.Camera,enabled:boolean){
    if(this.disposed)return;
    this.status.enabled=enabled&&Boolean(this.key);
    if(!this.status.enabled){this.group.visible=false;this.queue=[];return;}
    this.group.visible=true;this.frame++;
    const p=camera.position,roots:string[]=[];
    camera.updateMatrixWorld();
    // A widened projection keeps tiles just off-screen ready for small turns.
    const wide=camera instanceof THREE.PerspectiveCamera?new THREE.PerspectiveCamera(Math.min(150,camera.fov*1.35),camera.aspect,camera.near,camera.far):camera;
    if(wide!==camera){wide.position.copy(camera.position);wide.quaternion.copy(camera.quaternion);wide.updateMatrixWorld();}
    this.frustum.setFromProjectionMatrix(this.matrix.multiplyMatrices(wide.projectionMatrix,wide.matrixWorldInverse));
    const t=tileMeters(ROOT_ZOOM),[cx,cy]=this.origin;
    const x0=Math.floor((cx-5000-ORIGIN_E)/t),x1=Math.floor((cx+5000-ORIGIN_E)/t);
    const y0=Math.floor((ORIGIN_N-cy-5000)/t),y1=Math.floor((ORIGIN_N-cy+5000)/t);
    const show=new Set<string>();this.queue=[];
    const key=(n:Node)=>`${n.z}/${n.x}/${n.y}`;
    const ready=(n:Node)=>{const r=this.rect(n).clip;return r[0]>=r[1]||r[2]>=r[3]||this.cache.get(key(n))?.state==='ready';};
    // Tiles the tree still wants (shown or waiting for siblings) stay cached.
    const request=(n:Node,priority:number)=>{const entry=this.cache.get(key(n));if(entry)entry.used=this.frame;else this.queue.push({node:{...n,key:key(n)},priority});};
    // Refine only when all four children are ready, so exactly one level
    // covers each spot and coarse patches never overlap finer ones.
    const visit=(n:Node)=>{
      const r=this.rect(n),[a,b,c,d]=r.clip;if(a>=b||c>=d)return;
      // Distance from the camera to the nearest point of the tile on the ground.
      const qx=THREE.MathUtils.clamp(p.x,a,b),qn=THREE.MathUtils.clamp(-p.z,c,d);
      const distance=Math.max(1,Math.hypot(p.x-qx,p.z+qn,p.y-this.heightAt(qx,-qn)));
      // Only tiles in view are refined; the rest keep a coarse tile.
      const ground=this.heightAt((a+b)/2,-(c+d)/2);
      const relief=n.z<15?400:120;this.box.min.set(a,ground-relief,-d);this.box.max.set(b,ground+relief,-c);
      const inView=n.z===ROOT_ZOOM||this.frustum.intersectsBox(this.box);
      if(inView&&n.z<MAX_ZOOM&&tileMeters(n.z)/256>distance*0.0009){
        const children=[[0,0],[1,0],[0,1],[1,1]].map(([dx,dy])=>({key:'',z:n.z+1,x:n.x*2+dx,y:n.y*2+dy}));
        for(const child of children)request(child,child.z*1e6+distance);
        if(children.every(ready)){for(const child of children)visit(child);return;}
      }
      const entry=this.cache.get(key(n));
      if(entry?.state==='ready'){show.add(key(n));entry.used=this.frame;}
    };
    for(let x=x0;x<=x1;x++)for(let y=y0;y<=y1;y++){
      // Root tiles are always fetched first: together they cover the world.
      const root={key:'',z:ROOT_ZOOM,x,y};roots.push(key(root));request(root,-1);visit(root);
    }
    for(const [k,entry] of this.cache)if(entry.mesh)entry.mesh.visible=show.has(k);
    // Once every root tile is ready the patches cover the whole world.
    this.status.covering=roots.every(k=>this.cache.get(k)?.state==='ready');
    this.queue.sort((a,b)=>a.priority-b.priority);
    this.pump();this.evict();
    this.status.visible=show.size;this.status.maxZoom=Math.max(0,...[...show].map(k=>Number(k.split('/')[0])));
  }

  private pump(){
    let loading=[...this.cache.values()].filter(e=>e.state==='loading').length;
    while(loading<MAX_LOADING&&this.queue.length){
      const {node}=this.queue.shift()!;if(this.cache.has(node.key))continue;
      const entry:Entry={mesh:null,state:'loading',used:this.frame};this.cache.set(node.key,entry);loading++;
      this.loader.load(this.url(node),texture=>{
        if(this.disposed||this.cache.get(node.key)!==entry){texture.dispose();return;}
        texture.colorSpace=THREE.SRGBColorSpace;texture.anisotropy=this.anisotropy;
        texture.wrapS=texture.wrapT=THREE.ClampToEdgeWrapping;
        entry.mesh=this.patch(node,texture);entry.mesh.visible=false;this.group.add(entry.mesh);
        entry.state='ready';this.status.loaded++;this.pump();
      },undefined,()=>{
        entry.state='failed';this.status.failed++;this.pump();
        // Allow a retry later, e.g. after a rate-limit response; the parent tile stays meanwhile.
        setTimeout(()=>{if(this.cache.get(node.key)===entry)this.cache.delete(node.key);},15000);
      });
    }
    this.status.loading=loading;
  }

  private evict(){
    if(this.cache.size<=CACHE_LIMIT)return;
    const old=[...this.cache.entries()].filter(([,e])=>e.state!=='loading'&&e.used<this.frame).sort((a,b)=>a[1].used-b[1].used);
    for(const [key,entry] of old.slice(0,this.cache.size-CACHE_LIMIT)){
      if(entry.mesh){this.group.remove(entry.mesh);entry.mesh.geometry.dispose();const m=entry.mesh.material as THREE.MeshStandardMaterial;m.map?.dispose();m.dispose();}
      this.cache.delete(key);
    }
  }

  /** Terrain-following patch for one tile, with short skirts against cracks. */
  private patch(n:Node,texture:THREE.Texture):THREE.Mesh {
    const r=this.rect(n),[a,b,c,d]=r.clip,size=r.e1-r.e0;
    const cells=THREE.MathUtils.clamp(Math.ceil(Math.max(b-a,d-c)/10),2,48),side=cells+1;
    const position:number[]=[],uv:number[]=[],index:number[]=[];
    const vertex=(e:number,north:number,drop=0)=>{position.push(e,this.heightAt(e,-north)-drop,-north);uv.push((e-r.e0)/size,(north-r.n0)/size);};
    for(let i=0;i<=cells;i++)for(let j=0;j<=cells;j++)vertex(a+(b-a)*j/cells,d-(d-c)*i/cells);
    for(let i=0;i<cells;i++)for(let j=0;j<cells;j++){const q=i*side+j;index.push(q,q+side,q+1,q+1,q+side,q+side+1);}
    const edge:number[]=[];
    for(let j=0;j<=cells;j++)edge.push(j);for(let i=1;i<=cells;i++)edge.push(i*side+cells);
    for(let j=cells-1;j>=0;j--)edge.push(cells*side+j);for(let i=cells-1;i>0;i--)edge.push(i*side);
    const skirt=position.length/3;
    for(const k of edge){position.push(position[k*3],position[k*3+1]-2,position[k*3+2]);uv.push(uv[k*2],uv[k*2+1]);}
    for(let k=0;k<edge.length;k++){const l=(k+1)%edge.length;index.push(edge[k],skirt+k,edge[l],edge[l],skirt+k,skirt+l);}
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(position,3));g.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));
    g.setIndex(index);g.computeVertexNormals();g.computeBoundingSphere();
    const material=new THREE.MeshStandardMaterial({map:texture,roughness:1,side:THREE.DoubleSide});
    // Pull patches toward the camera so they cover the local terrain; finer
    // zooms pull slightly further and win where levels overlap.
    const bias={value:.0009+(n.z-ROOT_ZOOM)*.00006};
    material.customProgramCacheKey=()=>'basemap-patch-v1';
    material.onBeforeCompile=shader=>{
      shader.uniforms.uBias=bias;
      shader.vertexShader=shader.vertexShader.replace('#include <common>','#include <common>\nuniform float uBias;')
        .replace('#include <project_vertex>','#include <project_vertex>\nmvPosition.xyz*=1.0-uBias;gl_Position=projectionMatrix*mvPosition;');
    };
    const mesh=new THREE.Mesh(g,material);mesh.name=`Basemap ${n.key}`;mesh.renderOrder=n.z;
    return mesh;
  }

  dispose(){
    this.disposed=true;
    for(const entry of this.cache.values())if(entry.mesh){entry.mesh.geometry.dispose();const m=entry.mesh.material as THREE.MeshStandardMaterial;m.map?.dispose();m.dispose();}
    this.cache.clear();
  }
}
