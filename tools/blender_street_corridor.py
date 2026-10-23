"""Blender side of tools/street_corridor.py (run inside Blender, not the venv).

Lays the measured cross-sections out as strips between stations, per side of the street: traffic lanes,
parking lanes, a 0.3 m concrete gutter, a 150 mm kerb (lowered to 20 mm at crossings, a kerb ramp), the kerb
top and the footpath up to the building line, which ends in a short skirt into the ground. Coordinates are
local metres with z the height above the ground; the viewer drapes the mesh onto the terrain. Surfaces use
textures cropped from the city kit atlas, tinted per surface. Saves streets/<name>.blend and the GLB.
"""
import bpy,json,sys
from mathutils import Vector

job=json.load(open(sys.argv[sys.argv.index('--')+1]));C=job['corridor'];TILES=job['tiles']


def log(*parts):print('STREET',*parts,flush=True)


def linear(h):
    c=[int(h[i:i+2],16)/255 for i in (1,3,5)];return [x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in c]+[1]


def material(name,texture,tint,rough):
    """A kit surface (texture) multiplied by a tint. Names starting 'road' sit on the road plane in the viewer."""
    m=bpy.data.materials.new(name);m.use_nodes=True;nodes=m.node_tree.nodes;links=m.node_tree.links;b=nodes['Principled BSDF']
    b.inputs['Roughness'].default_value=rough
    tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(f"{job['textures']}/{texture}.jpg")
    mix=nodes.new('ShaderNodeMix');mix.data_type='RGBA';mix.blend_type='MULTIPLY';mix.inputs['Factor'].default_value=1;mix.inputs[7].default_value=linear(tint)
    links.new(tex.outputs['Color'],mix.inputs[6]);links.new(mix.outputs[2],b.inputs['Base Color'])
    m.diffuse_color=linear(tint);m['tile']=TILES[texture];return m


MATS={'lane':material('road asphalt','asphalt','#ffffff',.9),'parking':material('road parking lane','asphalt','#d9d4ca',.9),
      'gutter':material('road gutter','concrete','#b4b2ab',.85),'kerb':material('kerb concrete','concrete','#dcdad3',.8),
      'footpath':material('footpath pavers','pavers','#b8b8b4',.85)}


class Mesh:
    def __init__(self):self.verts=[];self.faces=[];self.mats=[];self.uvs=[];self.matlist=list(MATS.values())

    def quad(self,pts,mat,vertical=False,s=(0,0)):
        """A face; horizontal faces get world-planar UVs, vertical ones run along the street (s) by height."""
        tile=mat['tile'];i=len(self.verts)
        self.verts+=[tuple(p) for p in pts];self.faces.append(list(range(i,i+len(pts))));self.mats.append(self.matlist.index(mat))
        self.uvs+=[(s[k]/tile,p[2]/tile) for k,p in enumerate(pts)] if vertical else [(p[0]/tile,p[1]/tile) for p in pts]

    def build(self,name):
        me=bpy.data.meshes.new(name);me.from_pydata(self.verts,[],self.faces);me.update()
        uv=me.uv_layers.new(name='UVMap')
        for p in me.polygons:
            for li in p.loop_indices:uv.data[li].uv=self.uvs[me.loops[li].vertex_index]
        for m in self.matlist:me.materials.append(m)
        me.polygons.foreach_set('material_index',self.mats);me.validate();me.update()
        ob=bpy.data.objects.new(name,me);bpy.context.scene.collection.objects.link(ob);return ob


def side(mesh,key,sign):
    st=C['stations'];sd=C['sides'][key];H=C['kerbHeight'];LOW=C['kerbLow']
    def at(i,off,z):x,y=st[i]['x']+sign*st[i]['n'][0]*off,st[i]['y']+sign*st[i]['n'][1]*off;return Vector((x,y,z))
    def inner(i):
        s=st[i]['s']
        for r in sd['runs']:
            if r['s0']<=s<=r['s1']:return min(r['inner'],sd['kerb'][i]-.5)
        return None
    for i in range(len(st)-1):
        j=i+1;ka,kb=sd['kerb'][i],sd['kerb'][j];ga,gb=ka-.3,kb-.3;ea,eb=sd['edge'][i],sd['edge'][j]
        ha=LOW if sd['low'][i] else H;hb=LOW if sd['low'][j] else H
        pa,pb=inner(i),inner(j)
        # Traffic lane (to the parking lane where there is one), parking lane, gutter.
        la,lb=(pa if pa is not None else ga),(pb if pb is not None else gb)
        if pa is not None and pb is None:lb=gb
        if pb is not None and pa is None:la=ga
        q=lambda a0,b0,a1,b1,z0,z1:[at(i,a0,z0),at(j,b0,z1),at(j,b1,z1),at(i,a1,z0)]
        flip=lambda pts:pts if sign>0 else pts[::-1]
        mesh.quad(flip(q(0,0,la,lb,0,0)),MATS['lane'])
        if pa is not None or pb is not None:mesh.quad(flip(q(la,lb,ga,gb,0,0)),MATS['parking'])
        mesh.quad(flip(q(ga,gb,ka,kb,0,0)),MATS['gutter'])
        s=(st[i]['s'],st[j]['s'],st[j]['s'],st[i]['s'])
        # Kerb face, kerb top, footpath (2% fall to the kerb), and a skirt into the ground at the building line.
        mesh.quad(flip([at(i,ka,0),at(j,kb,0),at(j,kb,hb),at(i,ka,ha)]),MATS['kerb'],True,s)
        mesh.quad(flip([at(i,ka,ha),at(j,kb,hb),at(j,kb+.15,hb),at(i,ka+.15,ha)]),MATS['kerb'])
        fa,fb=ha+.02*(ea-ka),hb+.02*(eb-kb)
        mesh.quad(flip([at(i,ka+.15,ha),at(j,kb+.15,hb),at(j,eb,fb),at(i,ea,fa)]),MATS['footpath'])
        mesh.quad(flip([at(i,ea,fa),at(j,eb,fb),at(j,eb,-.3),at(i,ea,-.3)]),MATS['kerb'],True,s)
    # End faces of the kerb and footpath where the corridor stops at the cross streets.
    for i,d in ((0,-1),(len(st)-1,1)):
        k=sd['kerb'][i];e=sd['edge'][i];h=LOW if sd['low'][i] else H;f=h+.02*(e-k)
        pts=[at(i,k,0),at(i,e,-.3),at(i,e,f),at(i,k+.15,h),at(i,k,h)]
        mesh.quad(pts if (d>0)==(sign>0) else pts[::-1],MATS['kerb'],True,(0,)*5)


for o in list(bpy.data.objects):bpy.data.objects.remove(o)
mesh=Mesh()
for key,sign in (('left',1),('right',-1)):side(mesh,key,sign)
ob=mesh.build(f"street {C['street']}");ob['street']=C['street']
log(f"{ob.name}: {len(C['stations'])} stations, {len(ob.data.polygons)} faces")
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=job['blend'])
bpy.ops.object.select_all(action='DESELECT');ob.select_set(True)
bpy.ops.export_scene.gltf(filepath=job['glb'],export_format='GLB',use_selection=True,export_yup=True,export_apply=True,export_extras=True)
log('exported',job['glb'])
