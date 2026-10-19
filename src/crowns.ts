import * as THREE from 'three';

/** A lumpy unit crown (radius ~1) with smooth, outward-facing normals.
 * Spherical normals keep low-polygon crowns soft instead of faceted; the
 * foliage shader adds leaf-clump shading in world metres.
 */
export function crownGeometry(detail:number,lumpiness=.14):THREE.BufferGeometry {
  // Detail -1 is an octahedron for distant crowns.
  const g=detail<0?new THREE.OctahedronGeometry(1,0):new THREE.IcosahedronGeometry(1,detail);
  const position=g.getAttribute('position'),normal=new Float32Array(position.count*3),v=new THREE.Vector3();
  for(let i=0;i<position.count;i++){
    v.fromBufferAttribute(position,i).normalize();
    // Deterministic, direction-based lumps so shared vertices stay welded.
    const lump=Math.sin(v.x*5.1+v.y*1.7)*Math.sin(v.z*4.3-v.y*2.9)+.5*Math.sin(v.x*9.7-v.z*8.3+v.y*6.1);
    const r=1+lumpiness*lump;
    // Crowns are slightly flattened underneath, where foliage thins.
    position.setXYZ(i,v.x*r,v.y<0?v.y*r*.82:v.y*r,v.z*r);
    const n=v.clone().setY(v.y+.25).normalize();
    normal[i*3]=n.x;normal[i*3+1]=n.y;normal[i*3+2]=n.z;
  }
  g.setAttribute('normal',new THREE.Float32BufferAttribute(normal,3));
  g.computeBoundingSphere();
  return g;
}

const hsl={h:0,s:0,l:0};
/** Crown colour from the aerial sample. Samples often fall on the shaded side
 * of a crown, which reads blue-black; lift them toward sunlit foliage, as the
 * renderer applies its own lighting and shading.
 */
export function crownColour(packed:number|undefined,index:number,target:THREE.Color):THREE.Color {
  if(packed===undefined)return target.setHSL(.24+(index%7)*.008,.3+(index%5)*.025,.3+(index%9)*.012,THREE.SRGBColorSpace);
  target.setHex(packed).getHSL(hsl,THREE.SRGBColorSpace);
  const h=hsl.s<.06?.23:THREE.MathUtils.lerp(hsl.h,.24,THREE.MathUtils.smoothstep(hsl.h,.3,.5)*.85);
  const s=THREE.MathUtils.clamp(hsl.s*1.15,.18,.45),l=THREE.MathUtils.clamp(hsl.l*1.05+.02,.22,.4);
  return target.setHSL(h,s,l,THREE.SRGBColorSpace);
}
