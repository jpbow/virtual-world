import * as THREE from 'three';
import type {GroundTextures} from './ground-textures';

interface TerrainState {
  reference: THREE.Texture;
  mask: THREE.Texture;
  referenceMode: {value:number};
}

// Generated material detail is evaluated in world metres. Tile boundaries and
// distance levels therefore never restart or stretch the pattern.
const noiseFunctions=/* glsl */`
float groundHash(vec2 p) {
  vec3 q=fract(vec3(p.xyx)*0.1031);
  q+=dot(q,q.yzx+33.33);
  return fract((q.x+q.y)*q.z);
}
float groundNoise(vec2 p) {
  vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);
  return mix(mix(groundHash(i),groundHash(i+vec2(1,0)),f.x),
             mix(groundHash(i+vec2(0,1)),groundHash(i+vec2(1,1)),f.x),f.y);
}
float groundFbm(vec2 p) {
  return 0.55*groundNoise(p)+0.27*groundNoise(p*2.07+7.3)+0.13*groundNoise(p*4.19+21.7)+0.05*groundNoise(p*8.31);
}
`;

export function makeTerrainMaterial(mask:THREE.Texture,reference:THREE.Texture,referenceMode:boolean,wireframe:boolean,evidence:THREE.Texture,relief:THREE.Texture,ground:GroundTextures,overview=false):THREE.MeshStandardMaterial {
  mask.colorSpace=THREE.NoColorSpace;mask.minFilter=THREE.LinearMipmapLinearFilter;mask.magFilter=THREE.LinearFilter;
  const state:TerrainState={reference,mask,referenceMode:{value:Number(referenceMode)}};
  const material=new THREE.MeshStandardMaterial({map:referenceMode?reference:null,roughness:1,side:THREE.DoubleSide,wireframe});
  material.userData.terrainState=state;
  material.customProgramCacheKey=()=>`world-ground-v3-${overview?'overview':'tile'}`;
  material.onBeforeCompile=shader=>{
    for(const [name,set] of Object.entries(ground)){
      const prefix=name==='grass'?'uGrass':'uForest';
      shader.uniforms[prefix+'Scan']={value:set.color};shader.uniforms[prefix+'Normal']={value:set.normal};shader.uniforms[prefix+'Rough']={value:set.roughness};
    }
    shader.uniforms.uRelief={value:relief};shader.uniforms.uLandscape={value:evidence};shader.uniforms.uSurfaceMap={value:mask};shader.uniforms.uReferenceMode=state.referenceMode;
    shader.uniforms.uSurfaceScale={value:overview?1:500/502};shader.uniforms.uSurfaceOffset={value:overview?0:1/502};
    shader.uniforms.uGrassA={value:new THREE.Color('#71765b')};shader.uniforms.uGrassB={value:new THREE.Color('#99977b')};
    shader.uniforms.uRock={value:new THREE.Color('#8d8b7c')};shader.uniforms.uSoil={value:new THREE.Color('#846b4d')};shader.uniforms.uPaving={value:new THREE.Color('#747b7a')};
    shader.vertexShader=shader.vertexShader.replace('#include <common>','#include <common>\nvarying vec2 vGroundUv;\nvarying vec3 vGroundPosition;');
    shader.vertexShader=shader.vertexShader.replace('#include <worldpos_vertex>','#include <worldpos_vertex>\nvGroundUv=uv;\nvGroundPosition=(modelMatrix*vec4(transformed,1.0)).xyz;');
    shader.fragmentShader=shader.fragmentShader.replace('#include <common>',`#include <common>
      uniform sampler2D uSurfaceMap,uLandscape,uRelief;
      uniform sampler2D uGrassScan,uGrassNormal,uGrassRough,uForestScan,uForestNormal,uForestRough;
      uniform float uReferenceMode,uSurfaceScale,uSurfaceOffset;
      uniform vec3 uGrassA,uGrassB,uRock,uSoil,uPaving;
      varying vec2 vGroundUv;
      varying vec3 vGroundPosition;
      float groundRelief,groundDetail,forestMix,scanWeight;
      vec2 grassUv,forestUv;
      ${noiseFunctions}`);
    shader.fragmentShader=shader.fragmentShader.replace('#include <map_fragment>',/* glsl */`
      if(uReferenceMode>0.5) {
        #include <map_fragment>
        groundRelief=0.0;groundDetail=0.0;scanWeight=0.0;forestMix=0.0;
      } else {
        vec2 p=vGroundPosition.xz;
        vec3 stored=texture2D(uSurfaceMap,vGroundUv*uSurfaceScale+uSurfaceOffset).rgb;
        vec4 weights=vec4(stored,max(0.0,1.0-stored.r-stored.g-stored.b));
        weights/=max(0.001,dot(weights,vec4(1.0)));
        float macro=groundFbm(p*0.012);
        float middle=groundFbm(p*0.31);
        float footprint=max(length(dFdx(p)),length(dFdy(p)));
        float closeDetail=1.0-smoothstep(0.15,1.5,footprint);
        float grain=mix(0.5,groundNoise(p*9.0),closeDetail);
        float blades=mix(0.5,groundNoise(p*vec2(11.0,2.6)+groundNoise(p*0.4)),closeDetail);
        vec4 evidence=texture2D(uLandscape,vec2(p.x+5000.0,5000.0-p.y)/10000.0);
        vec3 grass=mix(uGrassA,uGrassB,smoothstep(0.22,0.78,macro))*(0.82+0.28*middle+0.16*(blades-0.5));
        grass=mix(grass,vec3(0.15,0.20,0.09)*(0.9+0.2*middle),evidence.g*0.65);
        grass=mix(grass,vec3(0.075,0.095,0.055),evidence.r*0.7);
        float fractures=smoothstep(0.40,0.49,abs(groundNoise(p*0.65)-0.5));
        vec3 rock=uRock*(0.72+0.45*groundFbm(p*1.7)+0.12*grain-0.12*fractures);
        vec3 soil=uSoil*(0.74+0.44*middle+0.16*grain);
        vec3 paving=uPaving*(0.89+0.15*groundNoise(p*0.12)+0.13*(grain-0.5));
        groundDetail=1.0-smoothstep(65.0,220.0,length(vViewPosition));
        forestMix=smoothstep(0.08,0.85,evidence.r);
        grassUv=p/2.51;forestUv=p/2.14;
        vec3 grassScan=texture2D(uGrassScan,grassUv).rgb;
        vec3 litterScan=texture2D(uForestScan,forestUv).rgb;
        litterScan=mix(vec3(dot(litterScan,vec3(0.2126,0.7152,0.0722))),litterScan,0.5)*0.66;
        vec3 scanned=mix(grassScan,litterScan,forestMix);
        scanned*=0.84+0.24*macro;
        grass=mix(grass,scanned,groundDetail*0.88);
        soil=mix(soil,litterScan*vec3(1.05,0.83,0.65),groundDetail*0.65);
        scanWeight=clamp(weights.r+weights.b*0.65,0.0,1.0);
        diffuseColor.rgb*=grass*weights.r+rock*weights.g+soil*weights.b+paving*weights.a;
        groundRelief=closeDetail*((blades-0.5)*0.002*weights.r+(groundNoise(p*3.0)-0.5)*0.16*weights.g+(grain-0.5)*(0.002*weights.b+0.008*weights.a));
      }
    `);
    shader.fragmentShader=shader.fragmentShader.replace('#include <lights_fragment_end>',`#include <lights_fragment_end>
      if(uReferenceMode<0.5){
        vec4 visibility=texture2D(uLandscape,vec2(vGroundPosition.x+5000.0,5000.0-vGroundPosition.z)/10000.0);
        reflectedLight.indirectDiffuse*=mix(0.35,1.0,visibility.b*visibility.b);
        float relief=1.0+(texture2D(uRelief,vec2(vGroundPosition.x+5000.0,5000.0-vGroundPosition.z)/10000.0).r-128.0/255.0)*255.0/300.0;
        reflectedLight.directDiffuse*=visibility.a*relief;
      }
    `);
    shader.fragmentShader=shader.fragmentShader.replace('#include <roughnessmap_fragment>',`#include <roughnessmap_fragment>
      if(uReferenceMode<0.5){
        float scannedRough=mix(texture2D(uGrassRough,grassUv).r,texture2D(uForestRough,forestUv).r,forestMix);
        roughnessFactor=mix(roughnessFactor,max(0.7,scannedRough),groundDetail*scanWeight);
      }
    `);
    shader.fragmentShader=shader.fragmentShader.replace('#include <normal_fragment_maps>',/* glsl */`
      #include <normal_fragment_maps>
      if(uReferenceMode<0.5) {
        vec3 sx=dFdx(-vViewPosition),sy=dFdy(-vViewPosition);
        vec3 rx=cross(sy,normal),ry=cross(normal,sx);
        float determinant=dot(sx,rx);
        vec3 gradient=sign(determinant)*(dFdx(groundRelief)*rx+dFdy(groundRelief)*ry);
        normal=normalize(max(abs(determinant),0.00000001)*normal-gradient);
        vec3 grassN=texture2D(uGrassNormal,grassUv).xyz*2.0-1.0;
        vec3 forestN=texture2D(uForestNormal,forestUv).xyz*2.0-1.0;
        vec3 mapN=normalize(mix(grassN,forestN,forestMix));
        mapN.xy*=groundDetail*scanWeight*0.75;
        vec2 uv0=dFdx(vGroundPosition.xz),uv1=dFdy(vGroundPosition.xz);
        vec3 tangent=cross(sy,normal)*uv0.x+cross(normal,sx)*uv1.x;
        vec3 bitangent=cross(sy,normal)*uv0.y+cross(normal,sx)*uv1.y;
        float basis=inversesqrt(max(max(dot(tangent,tangent),dot(bitangent,bitangent)),0.00000001));
        normal=normalize(tangent*mapN.x*basis+bitangent*mapN.y*basis+normal*mapN.z);
      }
    `);
  };
  return material;
}

export function setTerrainReference(material:THREE.MeshStandardMaterial,value:boolean){
  const state=material.userData.terrainState as TerrainState;
  state.referenceMode.value=Number(value);material.map=value?state.reference:null;material.needsUpdate=true;
}

// Clip low scrub to measured vegetation occupancy. Tall crowns may overhang.
// Crowns are shaded as foliage masses: world-space leaf clumps, darker
// undersides and interior gaps, instead of flat faceted polygons.
export function makeLeafMaterial(evidence:THREE.Texture):THREE.MeshStandardMaterial {
  const material=new THREE.MeshStandardMaterial({color:'#ffffff',roughness:.92});
  material.customProgramCacheKey=()=> 'evidence-scrub-v2';
  material.onBeforeCompile=shader=>{
    shader.uniforms.uLandscape={value:evidence};
    shader.vertexShader=shader.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vPlantWorld;\nvarying float vLowScrub;\nvarying float vCrownY;');
    shader.vertexShader=shader.vertexShader.replace('#include <worldpos_vertex>', `#include <worldpos_vertex>
      vec4 plant=vec4(transformed,1.0);
      vCrownY=transformed.y;
      #ifdef USE_INSTANCING
        plant=instanceMatrix*plant;
        vLowScrub=step(length(instanceMatrix[1].xyz),1.8);
      #else
        vLowScrub=0.0;
      #endif
      vPlantWorld=(modelMatrix*plant).xyz;
    `);
    shader.fragmentShader=shader.fragmentShader.replace('#include <common>',`#include <common>\nuniform sampler2D uLandscape;\nvarying vec3 vPlantWorld;\nvarying float vLowScrub;\nvarying float vCrownY;\n${noiseFunctions}`);
    shader.fragmentShader=shader.fragmentShader.replace('#include <clipping_planes_fragment>',`#include <clipping_planes_fragment>
      if(vLowScrub>0.5 && texture2D(uLandscape,vec2(vPlantWorld.x+5000.0,5000.0-vPlantWorld.z)/10000.0).r<0.3)discard;
    `);
    shader.fragmentShader=shader.fragmentShader.replace('#include <color_fragment>',`#include <color_fragment>
      vec3 leafP=vPlantWorld*vec3(1.0,1.35,1.0);
      float leafScale=max(length(dFdx(leafP)),length(dFdy(leafP)));
      float fine=1.0-smoothstep(0.25,1.6,leafScale);
      float clumps=groundNoise(leafP.xz*0.55+leafP.y*0.7)*0.6+groundNoise(leafP.zx*1.3-leafP.y*1.1)*0.4;
      float leaves=groundNoise(leafP.xz*4.1+leafP.y*3.3)*0.6+groundNoise(leafP.zx*9.3-leafP.y*7.1)*0.4;
      float shade=mix(0.6,1.08,smoothstep(-0.95,0.85,vCrownY));
      diffuseColor.rgb*=shade*(0.84+0.3*clumps)*(1.0+fine*0.5*(leaves-0.5));
      diffuseColor.rgb*=mix(1.0,0.82,fine*smoothstep(0.62,0.82,1.0-clumps));
      // Low scrub masses are many small bushes: mottle them at bush scale.
      float bushes=groundNoise(vPlantWorld.xz*0.75)*0.65+groundNoise(vPlantWorld.zx*1.9+3.1)*0.35;
      diffuseColor.rgb*=mix(1.0,0.5+0.75*smoothstep(0.25,0.75,bushes),vLowScrub);
    `);
    shader.fragmentShader=shader.fragmentShader.replace('#include <normal_fragment_maps>',`#include <normal_fragment_maps>
      vec2 leafTilt=vec2(groundNoise(vPlantWorld.xz*0.9+vPlantWorld.y),groundNoise(vPlantWorld.zx*0.9-vPlantWorld.y+7.0))-0.5;
      normal=normalize(normal+vec3(leafTilt,0.0)*0.9);
    `);
  };
  return material;
}
