"""Blender side of tools/street_furniture.py (run inside Blender, not the venv).

Builds the reusable street-furniture kit: one object per prefab, named `kit:<name>`, standing on its
origin with its front (the side a person faces it from) toward Blender -Y, which the viewer turns to
the placement's compass heading. Saves street-kit/street-kit.blend and exports the GLB.

Styles follow London Street photos: black ornamental lamps, black pedestal litter bins with a
compass emblem, timber benches on black cast ends. Sizes are typical, not measured.
"""
import bpy,bmesh,json,math,sys
from mathutils import Vector,Matrix

job=json.loads(sys.argv[sys.argv.index('--')+1])


def log(*parts):print('KIT',*parts,flush=True)


def linear(h):
    c=[int(h[i:i+2],16)/255 for i in (1,3,5)];return [x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in c]+[1]


_mats={}
def mat(name,colour,rough=.6,metal=0.,emit=None):
    if name in _mats:return _mats[name]
    m=bpy.data.materials.new(name);m.use_nodes=True;b=m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value=linear(colour);b.inputs['Roughness'].default_value=rough;b.inputs['Metallic'].default_value=metal
    if emit:b.inputs['Emission Color'].default_value=linear(emit);b.inputs['Emission Strength'].default_value=1.5
    m.diffuse_color=linear(colour);_mats[name]=m;return m


class Part:
    """Accumulates bmesh geometry for one prefab, with a material per face."""
    def __init__(self,name):self.name=name;self.bm=bmesh.new();self.mats=[]

    def _m(self,m):
        if m not in self.mats:self.mats.append(m)
        return self.mats.index(m)

    def _tag(self,faces,m):
        i=self._m(m)
        for f in faces:f.material_index=i

    def box(self,c,size,m,rot=0.):
        r=bmesh.ops.create_cube(self.bm,size=1.,matrix=Matrix.Translation(c)@Matrix.Rotation(rot,4,'Z')@Matrix.Diagonal((*size,1)))
        self._tag({f for v in r['verts'] for f in v.link_faces},m)

    def lathe(self,profile,m,seg=16,at=(0,0,0),scale_y=1.):
        """Revolve [(r, z)] around Z (closed at the ends when r = 0)."""
        rings=[]
        for r,z in profile:
            rings.append([self.bm.verts.new((at[0]+r*math.cos(2*math.pi*i/seg),at[1]+scale_y*r*math.sin(2*math.pi*i/seg),at[2]+z)) for i in range(seg)])
        faces=[]
        for a,b in zip(rings,rings[1:]):
            for i in range(seg):
                q=[a[i],a[(i+1)%seg],b[(i+1)%seg],b[i]]
                q=[v for k,v in enumerate(q) if all((v.co-w.co).length>1e-6 for w in q[:k])]
                if len(q)>=3:faces.append(self.bm.faces.new(q))
        if profile[0][0]>1e-6:faces.append(self.bm.faces.new(rings[0][::-1]))
        if profile[-1][0]>1e-6:faces.append(self.bm.faces.new(rings[-1]))
        self._tag(faces,m)

    def cyl(self,r,z0,z1,m,seg=16,at=(0,0)):self.lathe([(r,z0),(r,z1)],m,seg,(at[0],at[1],0))

    def plane(self,pts,m):self._tag([self.bm.faces.new([self.bm.verts.new(p) for p in pts])],m)

    def text(self,body,c,height,m,width=None,facing=-1):
        """Flat lettering centred at c on a vertical plane facing -Y (or +Y), cap height `height`."""
        cu=bpy.data.curves.new('t','FONT');cu.body=body;cu.align_x='CENTER';cu.align_y='CENTER';cu.size=1
        ob=bpy.data.objects.new('t',cu);bpy.context.scene.collection.objects.link(ob)
        me=bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        xs=[v.co.x for v in me.vertices] or [0];ys=[v.co.y for v in me.vertices] or [0]
        s=height/max(1e-6,max(ys)-min(ys))
        if width:s=min(s,width/max(1e-6,max(xs)-min(xs)))
        cx=(max(xs)+min(xs))/2;cy=(max(ys)+min(ys))/2
        for p in me.polygons:
            pts=[me.vertices[i].co for i in p.vertices]
            # x along the sign, y up; facing -Y reads left to right from the front.
            pts=[(c[0]+(v.x-cx)*s*(-facing),c[1],c[2]+(v.y-cy)*s) for v in pts]
            self.plane(pts if facing<0 else pts[::-1],m)
        bpy.data.objects.remove(ob);bpy.data.curves.remove(cu);bpy.data.meshes.remove(me)

    def build(self,col):
        me=bpy.data.meshes.new(self.name);self.bm.normal_update();self.bm.to_mesh(me);self.bm.free()
        for m in self.mats:me.materials.append(m)
        for p in me.polygons:p.use_smooth=False
        ob=bpy.data.objects.new(f'kit:{self.name}',me);col.objects.link(ob);return ob


BLACK=dict(name='cast black',colour='#1c1d1f',rough=.45,metal=.6)
GREY=dict(name='galvanised',colour='#9aa0a4',rough=.4,metal=.8)
TIMBER=dict(name='timber',colour='#8a6440',rough=.75)


def lamp_ornamental():
    """Black heritage lamp: fluted base, tapering column, collar and a six-sided lantern (4.3 m)."""
    p=Part('lamp-ornamental');k=mat(**BLACK);glass=mat('lamp glass','#f6ecd0',.15,0,'#ffe6b0')
    p.lathe([(.2,0),(.2,.08),(.16,.12),(.15,.6),(.11,.7),(.09,.75),(.075,3.3),(.1,3.35),(.1,3.42),(.07,3.46),(.07,3.6)],k,16)
    p.lathe([(.12,3.6),(.17,3.62),(.17,3.66)],k,6)
    p.lathe([(.14,3.66),(.2,4.1)],glass,6)
    p.lathe([(.24,4.1),(.24,4.14),(.12,4.3),(.03,4.42),(0,4.5)],k,6)
    for i in range(6):a=2*math.pi*i/6;p.box((.17*math.cos(a)*1.12,.17*math.sin(a)*1.12,3.88),(.025,.025,.45),k,a)
    return p


def lamp_park():
    """Modern park light pole with a flat LED head (4.5 m)."""
    p=Part('lamp-park');g=mat('park grey','#4a4f54',.4,.7);led=mat('led','#f4f6f8',.2,0,'#ffffff')
    p.cyl(.07,0,4.4,g,12);p.box((0,-.25,4.45),(.18,.6,.08),g);p.box((0,-.32,4.405),(.14,.4,.01),led)
    return p


def bin_compass():
    """London Street litter bin: black ribbed pedestal drum, domed lid, silver compass emblem on the front."""
    p=Part('bin-compass');k=mat(**BLACK);s=mat('emblem','#c9ccce',.3,.8);d=mat('emblem dark','#2b2e33',.4,.3)
    p.lathe([(.2,0),(.2,.05),(.16,.08),(.16,.14),(.29,.16),(.29,.9),(.31,.92),(.31,.95)],k,20)
    p.lathe([(.31,.95),(.26,1.02),(.14,1.07),(0,1.09)],k,20)
    for i in range(12):a=2*math.pi*(i+.5)/12;p.box((.295*math.cos(a),.295*math.sin(a),.53),(.03,.03,.72),k,a)
    # The emblem: a disc on the front with an eight-point compass star.
    p.plane([(.14*math.cos(2*math.pi*i/24),-.322,.62+.14*math.sin(2*math.pi*i/24)) for i in range(24)],s)
    star=[]
    for i in range(16):r=.12 if i%2==0 else .035;a=math.pi/2+2*math.pi*i/16;star.append((r*math.cos(a),-.326,.62+r*math.sin(a)))
    p.plane(star,d)
    return p


def bin_bigbelly():
    """Big Belly solar compactor (the council's Albion Square bin): grey body, solar panel on top."""
    p=Part('bin-bigbelly');g=mat('bigbelly grey','#8f969a',.4,.6);dk=mat('bigbelly dark','#2f3337',.5,.3);pv=mat('solar','#1d2a44',.15,.4)
    p.box((0,0,.62),(.64,.66,1.24),g);p.box((0,-.335,.85),(.4,.02,.25),dk);p.box((0,0,1.27),(.6,.62,.06),dk);p.box((0,.02,1.31),(.5,.5,.02),pv)
    return p


def bench(name,back=True,length=1.8):
    """Timber slatted bench on black cast ends, the seated person facing -Y."""
    p=Part(name);k=mat(**BLACK);t=mat(**TIMBER)
    for x in (-length/2+.12,length/2-.12):
        p.box((x,0,.22),(.06,.5,.44),k)
        if back:p.box((x,.24,.65),(.06,.06,.5),k,0)
    for j in range(4):p.box((0,-.2+j*.13,.46),(length,.11,.035),t)
    if back:
        for j in range(3):p.box((0,.28,.62+j*.13),(length,.035,.1),t)
    return p


def picnic_table():
    p=Part('picnic-table');t=mat(**TIMBER)
    p.box((0,0,.74),(1.8,.8,.05),t)
    for y in (-.62,.62):p.box((0,y,.45),(1.8,.3,.045),t)
    for x in (-.7,.7):
        for s in (-1,1):p.box((x,s*.3,.37),(.08,.08,.75),t,0)
        p.box((x,0,.43),(.08,1.55,.08),t)
    return p


def bollard():
    p=Part('bollard');k=mat(**BLACK);p.lathe([(.09,0),(.09,.9),(.1,.92),(.1,.96),(.05,1.0),(0,1.01)],k,12);return p


def bike_hoop():
    """Two stainless inverted-U hoops, 0.8 m apart."""
    p=Part('bike-hoop');g=mat(**GREY)
    for x in (-.4,.4):
        p.box((x,-.35,.28),(.05,.05,.56),g);p.box((x,.35,.28),(.05,.05,.56),g);p.box((x,0,.6),(.05,.75,.05),g)
    return p


def drinking_fountain():
    p=Part('drinking-fountain');g=mat(**GREY);c=mat('concrete','#b9b6ae',.9)
    p.box((0,0,.42),(.3,.3,.84),c);p.lathe([(0,.84),(.2,.84),(.2,.88),(.16,.92),(0,.92)],g,16);p.cyl(.015,.92,1.0,g,6);return p


def post_box(name,colour,label):
    """A pedestal post box with its operator's colour and name on the front."""
    p=Part(name);b=mat(f'{name} body',colour,.4,.2);w=mat('post label','#f5f5f2',.4);k=mat(**BLACK)
    p.cyl(.05,0,.6,k,10);p.box((0,0,.95),(.5,.4,.7),b);p.lathe([(.25,1.3),(.25,1.32),(0,1.4)],b,4);p.box((0,-.205,1.15),(.3,.01,.03),k)
    p.text(label,(0,-.207,.9),.09,w,width=.42)
    return p


def payphone():
    p=Part('payphone');g=mat('payphone grey','#c8ccd0',.4,.5);d=mat('payphone dark','#2a2e33',.5,.2);s=mat('spark purple','#5b2a86',.5)
    p.box((0,0,1.0),(.12,.12,2.0),g);p.box((0,-.12,1.2),(.45,.12,.6),d);p.box((0,-.14,2.05),(.6,.4,.06),g);p.box((0,-.33,2.0),(.6,.02,.12),s);return p


def sign_stop():
    """NZ Stop sign: red octagon with a white border and STOP, 750 mm, on a galvanised post."""
    p=Part('sign-stop');g=mat(**GREY);r=mat('sign red','#c8102e',.5);w=mat('sign white','#f7f7f5',.5);back=mat('sign back','#a7adb1',.5,.6)
    p.cyl(.03,0,2.55,g,8)
    oct_=lambda R,y:[(R*math.cos(math.pi/8+i*math.pi/4),y,2.15+R*math.sin(math.pi/8+i*math.pi/4)) for i in range(8)]
    p.plane(oct_(.375,-.04),w);p.plane(oct_(.34,-.045),r);p.plane(oct_(.375,-.035)[::-1],back)
    p.text('STOP',(0,-.05,2.15),.2,w,width=.5)
    return p


def sign_parking(minutes):
    """Time-limited parking sign: blue panel, white P and the limit in minutes."""
    p=Part(f'sign-parking-p{minutes}');g=mat(**GREY);b=mat('parking blue','#1f4fa0',.5);w=mat('sign white','#f7f7f5',.5);back=mat('sign back','#a7adb1',.5,.6)
    p.cyl(.03,0,2.6,g,8);p.plane([(-.2,-.04,2.0),(.2,-.04,2.0),(.2,-.04,2.55),(-.2,-.04,2.55)],b)
    p.plane([(-.2,-.035,2.55),(.2,-.035,2.55),(.2,-.035,2.0),(-.2,-.035,2.0)],back)
    p.text('P',(0,-.045,2.36),.26,w);p.text(str(minutes),(0,-.045,2.1),.11,w)
    return p


def sign_no_stopping():
    p=Part('sign-no-stopping');g=mat(**GREY);r=mat('sign red','#c8102e',.5);bl=mat('no-stop blue','#1f4fa0',.5);back=mat('sign back','#a7adb1',.5,.6)
    p.cyl(.03,0,2.6,g,8);ring=lambda R,y:[(R*math.cos(2*math.pi*i/24),y,2.3+R*math.sin(2*math.pi*i/24)) for i in range(24)]
    p.plane(ring(.225,-.04),r);p.plane(ring(.18,-.045),bl);p.plane(ring(.225,-.035)[::-1],back)
    for s in (1,-1):p.plane([(-.16,-.05,2.3-.16*s-.02),(.16,-.05,2.3+.16*s-.02),(.16,-.05,2.3+.16*s+.02),(-.16,-.05,2.3-.16*s+.02)][::(-1 if s>0 else 1)],r)
    return p


def bus_stop():
    p=Part('bus-stop');g=mat(**GREY);b=mat('metro blue','#18326b',.5);y=mat('metro yellow','#f2c230',.5)
    p.cyl(.04,0,2.8,g,8);p.box((0,-.03,2.45),(.45,.02,.6),b);p.text('BUS',(0,-.042,2.55),.12,y);p.text('STOP',(0,-.042,2.35),.1,y);return p


def flagpole():
    p=Part('flagpole');w=mat('flagpole white','#eceeef',.4,.3);p.lathe([(.07,0),(.035,8.0),(.06,8.05),(0,8.12)],w,10);return p


PREFABS=[lamp_ornamental,lamp_park,bin_compass,bin_bigbelly,lambda:bench('bench'),lambda:bench('bench-backless',back=False),picnic_table,bollard,bike_hoop,
         drinking_fountain,lambda:post_box('post-box','#d2232a','NZ Post'),lambda:post_box('post-box-dx','#14325a','DX Mail'),payphone,sign_stop,
         *[(lambda m:lambda:sign_parking(m))(m) for m in (5,10,30,60,120)],sign_no_stopping,bus_stop,flagpole]


def build():
    for o in list(bpy.data.objects):bpy.data.objects.remove(o)
    col=bpy.data.collections.new('Street kit');bpy.context.scene.collection.children.link(col)
    for i,make in enumerate(PREFABS):
        ob=make().build(col);ob.location.x=(i%8)*2.5;ob.location.y=(i//8)*3.   # laid out in a grid for editing
        log(f'{ob.name:<26} {len(ob.data.polygons):5d} faces')
    bpy.ops.wm.save_as_mainfile(filepath=job['blend'])


def export():
    objs=[o for o in bpy.data.objects if o.name.startswith('kit:')]
    saved=[(o,o.location.copy()) for o in objs]
    for o in objs:o.location=(0,0,0)                                  # prefabs export standing on their origin
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:o.hide_set(False);o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=job['glb'],export_format='GLB',use_selection=True,export_yup=True,export_apply=True)
    for o,l in saved:o.location=l
    log(f'exported {len(objs)} prefabs')


if job['mode']=='build':build()
else:bpy.ops.wm.open_mainfile(filepath=job['blend'])
export()
