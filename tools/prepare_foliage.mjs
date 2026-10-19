import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {MeshoptSimplifier} from 'meshoptimizer';
await MeshoptSimplifier.ready;
const output='public/plants/cc0';await mkdir(output,{recursive:true});
for(const [slug,id,nodeId,target] of [['tree_small_02','broadleaf-tree',0,12000],['shrub_02','broadleaf-shrub-a',0,4500],['shrub_02','broadleaf-shrub-b',1,4500]]){
  const folder=`.cache/material-assets/${slug}`,source=JSON.parse(await readFile(`${folder}/model.gltf`,'utf8'));
  const binary=await readFile(`${folder}/${source.buffers[0].uri}`),node=source.nodes[nodeId],mesh=source.meshes[node.mesh];
  const doc={asset:{version:'2.0',generator:'Lyttelton meshoptimizer foliage preparation'},scene:0,scenes:[{nodes:[0]}],nodes:[{...node,mesh:0}],meshes:[{primitives:[]}],materials:source.materials,textures:source.textures,samplers:source.samplers,images:[],accessors:[],bufferViews:[],buffers:[{byteLength:0}]};
  const pieces=[];let byteLength=0,triangles=0,sourceTriangles=0;
  const append=(data,target)=>{const b=Buffer.from(data.buffer,data.byteOffset,data.byteLength),index=doc.bufferViews.length;doc.bufferViews.push({buffer:0,byteOffset:byteLength,byteLength:b.length,...(target?{target}:{})});pieces.push(b);byteLength+=b.length;const pad=(-byteLength)&3;if(pad){pieces.push(Buffer.alloc(pad));byteLength+=pad;}return index;};
  const readAccessor=id=>{
    const a=source.accessors[id],v=source.bufferViews[a.bufferView],components={SCALAR:1,VEC2:2,VEC3:3,VEC4:4}[a.type],bytes={5126:4,5125:4,5123:2,5121:1}[a.componentType];
    const out=a.componentType===5126?new Float32Array(a.count*components):new Uint32Array(a.count*components);
    const view=new DataView(binary.buffer,binary.byteOffset,binary.byteLength),start=(v.byteOffset??0)+(a.byteOffset??0),stride=v.byteStride??components*bytes;
    for(let i=0;i<a.count;i++)for(let c=0;c<components;c++){const p=start+i*stride+c*bytes;out[i*components+c]=a.componentType===5126?view.getFloat32(p,true):bytes===4?view.getUint32(p,true):bytes===2?view.getUint16(p,true):view.getUint8(p);}
    return out;
  };
  const counts=mesh.primitives.map(p=>source.accessors[p.indices].count/3),total=counts.reduce((a,b)=>a+b,0);
  for(const [pi,primitive] of mesh.primitives.entries()){
    const position=readAccessor(primitive.attributes.POSITION),uv=readAccessor(primitive.attributes.TEXCOORD_0),indices=readAccessor(primitive.indices);
    const wanted=Math.max(300,Math.round(target*counts[pi]/total));
    const [result,error]=MeshoptSimplifier.simplifyWithAttributes(indices,position,3,uv,2,[.03,.03],null,wanted*3,.12,['Prune','Permissive']);
    const [remap,count]=MeshoptSimplifier.compactMesh(result);
    const attrs={};
    for(const [semantic,ai] of Object.entries(primitive.attributes)){
      if(!['POSITION','NORMAL','TEXCOORD_0'].includes(semantic))continue;
      const original=readAccessor(ai),n=semantic==='TEXCOORD_0'?2:3,array=new Float32Array(count*n);
      for(let i=0;i<remap.length;i++)if(remap[i]<count)for(let c=0;c<n;c++)array[remap[i]*n+c]=original[i*n+c];
      const accessor={bufferView:append(array,34962),componentType:5126,count,type:n===2?'VEC2':'VEC3'};
      if(semantic==='POSITION'){accessor.min=[Infinity,Infinity,Infinity];accessor.max=[-Infinity,-Infinity,-Infinity];for(let i=0;i<count;i++)for(let c=0;c<3;c++){accessor.min[c]=Math.min(accessor.min[c],array[i*3+c]);accessor.max[c]=Math.max(accessor.max[c],array[i*3+c]);}}
      attrs[semantic]=doc.accessors.push(accessor)-1;
    }
    const indexAccessor=doc.accessors.push({bufferView:append(result,34963),componentType:5125,count:result.length,type:'SCALAR'})-1;
    doc.meshes[0].primitives.push({...primitive,attributes:attrs,indices:indexAccessor});triangles+=result.length/3;sourceTriangles+=indices.length/3;
    console.log(id,pi,indices.length/3,'→',result.length/3,'error',error.toFixed(4));
  }
  for(const img of source.images){const data=await readFile(`${folder}/${img.uri}`);doc.images.push({bufferView:append(data),mimeType:img.uri.endsWith('.png')?'image/png':'image/jpeg'});}
  doc.buffers[0].byteLength=byteLength;
  let json=Buffer.from(JSON.stringify(doc));json=Buffer.concat([json,Buffer.alloc((-json.length)&3,32)]);
  const bin=Buffer.concat(pieces),header=Buffer.alloc(12),jh=Buffer.alloc(8),bh=Buffer.alloc(8);header.writeUInt32LE(0x46546c67);header.writeUInt32LE(2,4);header.writeUInt32LE(12+8+json.length+8+bin.length,8);jh.writeUInt32LE(json.length);jh.writeUInt32LE(0x4e4f534a,4);bh.writeUInt32LE(bin.length);bh.writeUInt32LE(0x004e4942,4);
  await writeFile(`${output}/${id}.glb`,Buffer.concat([header,jh,json,bh,bin]));
  await writeFile(`${output}/${id}.credit.json`,JSON.stringify({source:`https://polyhaven.com/a/${slug}`,license:'CC0-1.0',id,sourceTriangles,triangles,changes:'Selected source variant; reduced geometry with meshoptimizer, embedded original 1K textures. Representative foliage, not an identification of NZ species.'},null,2)+'\n');
}
