import * as THREE from 'three';
import type {Building} from './types';
interface Option {plant:number[];width:number;depth:number}
interface View {position:THREE.Vector3;target:THREE.Vector3;occlusions:number}

function hitsEllipsoid(a:THREE.Vector3,b:THREE.Vector3,center:THREE.Vector3,radii:THREE.Vector3){
  const origin=a.clone().sub(center).divide(radii),delta=b.clone().sub(a).divide(radii);
  const t=THREE.MathUtils.clamp(-origin.dot(delta)/Math.max(delta.lengthSq(),.00001),0,1);
  return origin.addScaledVector(delta,t).lengthSq()<1;
}

/** Find a real, unobstructed world view; never hide neighbouring scenery. */
export function choosePlantView(options:Option[],neighbours:(plant:number[])=>number[][],buildings:Building[],heightAt:(x:number,z:number)=>number,fov:number,aspect:number):View|null {
  let best:View|null=null;
  for(const {plant,width,depth} of options){
    const [x,n,z,h]=plant,worldZ=-n;
    const target=new THREE.Vector3(x,z+h*.5,worldZ);
    const radius=Math.hypot(width,h,depth)*.5;
    const field=Math.min(fov,2*Math.atan(Math.tan(fov/2)*aspect));
    const distance=radius/Math.sin(field/2)*1.2;
    const nearby=neighbours(plant).filter(p=>p!==plant);
    const boxes:THREE.Box3[]=[];
    for(const b of buildings){
      const xs=b.ring.map(p=>p[0]),zs=b.ring.map(p=>-p[1]);
      const minX=Math.min(...xs),maxX=Math.max(...xs),minZ=Math.min(...zs),maxZ=Math.max(...zs);
      if(x<minX-distance||x>maxX+distance||worldZ<minZ-distance||worldZ>maxZ+distance)continue;
      boxes.push(new THREE.Box3(new THREE.Vector3(minX,b.foundation??b.ground-5,minZ),new THREE.Vector3(maxX,b.ground+b.roof.height+1,maxZ)));
    }
    const samples=[target,new THREE.Vector3(x,z+h*.12,worldZ),new THREE.Vector3(x,z+h*.95,worldZ),new THREE.Vector3(x-width*.45,z+h*.75,worldZ),new THREE.Vector3(x+width*.45,z+h*.75,worldZ),new THREE.Vector3(x,z+h*.75,worldZ-depth*.45),new THREE.Vector3(x,z+h*.75,worldZ+depth*.45)];
    for(const elevation of [.25,.50,.75])for(let angle=0;angle<16;angle++){
      const theta=angle*Math.PI/8;
      const position=target.clone().add(new THREE.Vector3(Math.sin(theta)*distance,Math.sin(elevation)*distance,Math.cos(theta)*distance));
      if(position.y<heightAt(position.x,position.z)+2)continue;
      let occlusions=0;
      for(const sample of samples){
        let blocked=false;
        const direction=sample.clone().sub(position),length=direction.length(),ray=new THREE.Ray(position,direction.normalize());
        for(const box of boxes){const hit=ray.intersectBox(box,new THREE.Vector3());if(hit&&hit.distanceTo(position)<length){blocked=true;break;}}
        if(!blocked)for(const p of nearby){
          const shrub=p[6]===1,r=p[5]??p[3]*.34;
          const center=new THREE.Vector3(p[0],p[2]+p[3]*(shrub?.5:.63),-p[1]);
          if(hitsEllipsoid(position,sample,center,new THREE.Vector3(r,p[3]*(shrub?.5:.4),r))){blocked=true;break;}
        }
        if(!blocked)for(let step=1;step<12;step++){
          const point=position.clone().lerp(sample,step/12);
          if(point.y<heightAt(point.x,point.z)+.1){blocked=true;break;}
        }
        occlusions+=Number(blocked);
      }
      const view={position,target,occlusions};
      if(!best||occlusions<best.occlusions)best=view;
      if(occlusions===0)return view;
    }
  }
  return best;
}
