"""Blender side of tools/street_buildings.py (run inside Blender, not the venv).

Build mode turns the measured blocks (walls, fitted roof planes, parapets) and the photo notes
(cladding, colours, shopfronts, windows, signs, verandahs) into one mesh per building, saves
buildings/<name>.blend for hand editing, and exports the GLB. Export mode re-exports the .blend.

Scene units are local metres: x east, y north, z NZVD2016 elevation (the GLB is y-up, so the
viewer reads east, elevation, south directly). Facade details are placed in a facade frame:
s runs left to right as seen from the street, k outward from the facade, z up.
"""
import bpy,json,math,sys
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

job=json.loads(sys.argv[sys.argv.index('--')+1])
if 'job' in job:job=json.load(open(job['job']))
TILES={'weatherboard':1.2,'board':1.2,'corrugated':.762,'render':2.0,'tile':.6,'seam':1.6,'timber':1.0}
GLASS='#34404a'
LIGHT=bool(job.get('light'))                                     # lighter windows for typed (photo-less) buildings


def log(*parts):print('BUILDINGS',*parts,flush=True)


def export():
    bpy.ops.object.select_all(action='DESELECT')
    objects=[o for o in bpy.data.objects if o.type=='MESH' and (o.get('osm_id') or o.get('chunk'))]
    for o in objects:o.hide_set(False);o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=job['glb'],export_format='GLB',use_selection=True,export_yup=True,export_apply=True,
                              export_extras=True,export_image_format='AUTO',export_attributes=True,
                              **({'export_vertex_color':'ACTIVE'} if LIGHT else {}))
    log(f'exported {len(objects)} buildings')


# --- Materials ------------------------------------------------------------------

def linear(hexcolour):
    c=[int(hexcolour[i:i+2],16)/255 for i in (1,3,5)]
    return [x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in c]+[1]


_images={};_materials={}
def image(name,colour_data=True):
    if name not in _images:
        img=bpy.data.images.load(f"{job['textures']}/{name}.png");img.colorspace_settings.name='sRGB' if colour_data else 'Non-Color';_images[name]=img
    return _images[name]


class Tint:
    """A shared surface material plus this face's colour, carried as a vertex colour (glTF COLOR_0 multiplies
    the base colour), so merged chunks need one material per surface rather than one per colour."""
    def __init__(self,mat,colour):self.mat=mat;self.colour=tuple(linear(colour)[:3])
    def __getitem__(self,key):return self.mat[key]


def material(colour,texture=None,roughness=.85,metallic=0.):
    """A Principled material; a texture is a greyscale albedo multiplied by the colour (exported as glTF baseColorFactor)."""
    if LIGHT and colour!='#ffffff':return Tint(material('#ffffff',texture,roughness,metallic),colour)
    key=(colour,texture,roughness,metallic)
    if key in _materials:return _materials[key]
    m=bpy.data.materials.new(f"{texture or 'plain'} {colour}");m.use_nodes=True
    nodes=m.node_tree.nodes;links=m.node_tree.links;bsdf=nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value=roughness;bsdf.inputs['Metallic'].default_value=metallic
    if texture:
        tex=nodes.new('ShaderNodeTexImage');tex.image=image(texture)
        mix=nodes.new('ShaderNodeMix');mix.data_type='RGBA';mix.blend_type='MULTIPLY';mix.inputs['Factor'].default_value=1
        mix.inputs[7].default_value=linear(colour);links.new(tex.outputs['Color'],mix.inputs[6]);links.new(mix.outputs[2],bsdf.inputs['Base Color'])
        ntex=nodes.new('ShaderNodeTexImage');ntex.image=image(texture+'-normal',False)
        nmap=nodes.new('ShaderNodeNormalMap');links.new(ntex.outputs['Color'],nmap.inputs['Color']);links.new(nmap.outputs['Normal'],bsdf.inputs['Normal'])
    else:bsdf.inputs['Base Color'].default_value=linear(colour)
    m.diffuse_color=linear(colour);m['tile']=TILES.get(texture,1.);_materials[key]=m
    return m


# --- Geometry accumulator ---------------------------------------------------------

class Mesh:
    """Faces with per-face materials; UVs are world-metre projections scaled by the material's tile size."""
    def __init__(self):self.verts=[];self.faces=[];self.mats=[];self.matlist=[];self.uvs=[];self.tags=[];self.tag=0;self.cols=[]

    def face(self,pts,mat,flip=False):
        colour=(1.,1.,1.)
        if isinstance(mat,Tint):colour=mat.colour;mat=mat.mat
        pts=[Vector(p) for p in pts]
        if flip:pts=pts[::-1]
        if len(pts)<3:return
        nrm=Vector((0,0,0))
        for a,b in zip(pts,pts[1:]+pts[:1]):nrm+=Vector(((a.y-b.y)*(a.z+b.z),(a.z-b.z)*(a.x+b.x),(a.x-b.x)*(a.y+b.y)))
        if nrm.length<1e-9:return
        nrm.normalize();tile=mat['tile']
        if abs(nrm.z)<.7:h=Vector((0,0,1)).cross(nrm).normalized();uv=[(p.dot(h)/tile,p.z/tile) for p in pts]
        elif abs(nrm.z)>.999:uv=[(p.x/tile,p.y/tile) for p in pts]
        else:h=nrm.cross(Vector((0,0,1))).normalized();d=h.cross(nrm).normalized();uv=[(p.dot(h)/tile,p.dot(d)/tile) for p in pts]
        i=len(self.verts);self.verts+=[tuple(p) for p in pts];self.faces.append(list(range(i,i+len(pts))));self.uvs+=uv;self.tags+=[self.tag]*len(pts);self.cols+=[colour]*len(pts)
        if mat not in self.matlist:self.matlist.append(mat)
        self.mats.append(self.matlist.index(mat))

    def box(self,corner,s0,s1,k0,k1,z0,z1,mat,skip=()):
        """An axis-aligned box in a local frame; corner(s, k, z) maps to world. Faces are wound outward."""
        c=Vector(corner((s0+s1)/2,(k0+k1)/2,(z0+z1)/2))
        quads={'front':[(s0,k1,z0),(s1,k1,z0),(s1,k1,z1),(s0,k1,z1)],'back':[(s0,k0,z0),(s1,k0,z0),(s1,k0,z1),(s0,k0,z1)],
               'left':[(s0,k0,z0),(s0,k1,z0),(s0,k1,z1),(s0,k0,z1)],'right':[(s1,k0,z0),(s1,k1,z0),(s1,k1,z1),(s1,k0,z1)],
               'top':[(s0,k0,z1),(s1,k0,z1),(s1,k1,z1),(s0,k1,z1)],'bottom':[(s0,k0,z0),(s1,k0,z0),(s1,k1,z0),(s0,k1,z0)]}
        for name,q in quads.items():
            if name in skip:continue
            pts=[Vector(corner(*p)) for p in q];self.oriented(pts,c,mat)

    def oriented(self,pts,centre,mat,inward=False):
        """Add a face wound so its normal points away from `centre` (or toward it)."""
        n=(pts[1]-pts[0]).cross(pts[2]-pts[0])
        if n.length<1e-12 and len(pts)>3:n=(pts[2]-pts[0]).cross(pts[3]-pts[0])
        mid=sum(pts,Vector())/len(pts);self.face(pts,mat,flip=(n.dot(mid-centre)<0)!=inward)

    def build(self,name,collection):
        me=bpy.data.meshes.new(name);me.from_pydata(self.verts,[],self.faces);me.update()
        layer=me.uv_layers.new(name='UVMap')
        for poly in me.polygons:
            for li in poly.loop_indices:layer.data[li].uv=self.uvs[me.loops[li].vertex_index]
        for m in self.matlist:me.materials.append(m)
        me.polygons.foreach_set('material_index',self.mats)
        # Which building each vertex belongs to, in a merged chunk (exported as the glTF attribute _BUILDING).
        if any(self.tags):me.attributes.new('_building','FLOAT','POINT').data.foreach_set('value',[float(t) for t in self.tags])
        if LIGHT:
            col=me.color_attributes.new('Col','FLOAT_COLOR','POINT');col.data.foreach_set('color',[c for rgb in self.cols for c in (*rgb,1.)])
            me.color_attributes.active_color=col
        me.validate();me.update()
        ob=bpy.data.objects.new(name,me);collection.objects.link(ob);return ob


# --- Text -----------------------------------------------------------------------

_glyphs={}
def text_polygons(body):
    """Letter outlines of `body` in Blender's built-in font, centred on the origin, 1 unit cap size."""
    if body not in _glyphs:
        cu=bpy.data.curves.new('sign','FONT');cu.body=body;cu.align_x='CENTER';cu.align_y='CENTER';cu.size=1;cu.fill_mode='FRONT'
        ob=bpy.data.objects.new('sign',cu);bpy.context.scene.collection.objects.link(ob)
        ev=ob.evaluated_get(bpy.context.evaluated_depsgraph_get());me=bpy.data.meshes.new_from_object(ev)
        polys=[[tuple(me.vertices[i].co)[:2] for i in p.vertices] for p in me.polygons]
        bpy.data.objects.remove(ob);bpy.data.curves.remove(cu);bpy.data.meshes.remove(me);_glyphs[body]=polys
    return _glyphs[body]


def text(mesh,F,body,s,z,width,height,k,mat):
    """Flat lettering centred at (s, z) on the facade plane at offset k, fitted inside width x height."""
    polys=text_polygons(body)
    if not polys:return
    xs=[p[0] for q in polys for p in q];ys=[p[1] for q in polys for p in q]
    scale=min(width*.92/max(1e-6,max(xs)-min(xs)),height*.72/max(1e-6,max(ys)-min(ys)))
    cx=(max(xs)+min(xs))/2;cy=(max(ys)+min(ys))/2
    for q in polys:mesh.face([F.at(s+(x-cx)*scale,k,z+(y-cy)*scale) for x,y in q],mat)


# --- Facade frame -----------------------------------------------------------------

class Facade:
    def __init__(self,f,floor):
        self.a=Vector((*f['a'],0));self.t=Vector((*f['t'],0));self.n=Vector((*f['n'],0));self.L=f['length'];self.floor=floor
    def at(self,s,k,z):p=self.a+self.t*s+self.n*k;return (p.x,p.y,z)
    def s_of(self,x,y):return (Vector((x,y,0))-self.a).dot(self.t)
    def k_of(self,x,y):return (Vector((x,y,0))-self.a).dot(self.n)


def wall_with_openings(mesh,F,top,z0,openings,mat,reveal_mat,depth=.12):
    """The facade surface from z0 up to the top profile [(s, z)], with rectangular openings (s0, s1, z0, z1)
    cut out and lined with reveals. Openings must not overlap."""
    L=F.L;openings=sorted(o for o in openings if o[1]-o[0]>.02 and o[3]-o[2]>.02)
    zs=sorted({z0}|{o[2] for o in openings}|{o[3] for o in openings})
    zt=min(z for _,z in top)
    zs=[z for z in zs if z<zt]+[zt]
    for za,zb in zip(zs,zs[1:]):
        cuts=sorted((o[0],o[1]) for o in openings if o[2]<=za+1e-6 and o[3]>=zb-1e-6)
        x=0.
        for c0,c1 in cuts+[(L,L)]:
            if c0-x>1e-4:mesh.face([F.at(x,0,za),F.at(c0,0,za),F.at(c0,0,zb),F.at(x,0,zb)],mat)
            x=max(x,c1)
    # Above the highest flat line: the profile itself (a shaped parapet or a sloping eave).
    pts=[F.at(0,0,zt),F.at(L,0,zt)]+[F.at(s,0,z) for s,z in reversed(top)]
    mesh.face(pts,mat)
    for s0,s1,a,b in openings:
        c=Vector(F.at((s0+s1)/2,-depth/2,(a+b)/2))
        for q in ([(s0,a),(s1,a)],[(s1,a),(s1,b)],[(s1,b),(s0,b)],[(s0,b),(s0,a)]):
            (sa,za),(sb,zb)=q;mesh.oriented([Vector(F.at(sa,0,za)),Vector(F.at(sb,0,zb)),Vector(F.at(sb,-depth,zb)),Vector(F.at(sa,-depth,za))],c,reveal_mat,inward=True)
    return openings


def top_at(top,s):
    """Height of a parapet top line [(s, z)] at s; at a vertical step, the lower side."""
    for (sa,za),(sb,zb) in zip(top,top[1:]):
        if sa<=s<=sb:return min(za,zb) if sb-sa<1e-3 else za+(zb-za)*(s-sa)/(sb-sa)
    return top[-1][1] if s>top[-1][0] else top[0][1]


def profile(shape,L,base,spec):
    """Parapet top line [(s, z)] for a facade segment of width L whose straight top is at `base`."""
    if shape=='arch':
        rise=spec.get('rise',.8);w=L*.44;s1=(L-w)/2;s2=s1+w;step=.22;pts=[(0,base),(s1-.15,base),(s1-.15,base+step)]
        for i in range(13):
            u=i/12;pts.append((s1+w*u,base+step+(rise-step)*math.sin(math.pi*u)))
        return pts+[(s2+.15,base+step),(s2+.15,base),(L,base)]
    if shape=='gable':
        rise=L/2*math.tan(math.radians(spec.get('pitch',40)));return [(0,base),(L/2,base+rise),(L,base)]
    if shape=='stepped':return [(0,base),(L*.3,base),(L*.3,base+.35),(L*.7,base+.35),(L*.7,base),(L,base)]
    return [(0,base),(L,base)]


# --- Buildings --------------------------------------------------------------------

def blocks(mesh,m,b,F,mats,facade_open):
    """Walls (except the street facade, built with its openings), roofs and parapets of each block."""
    found=m['foundation']
    for bi,blk in enumerate(m['blocks']):
        wall=blk['wall'];par=blk.get('parapet') or 0
        if b.get('open'):
            # Open-sided canopy: a roof slab on corner posts.
            z=wall[0][2]
            for x,y in blk['ring']:
                mesh.box(lambda s,k,zz,x=x,y=y:(x+s,y+k,zz),-.06,.06,-.06,.06,found,z-.12,mats['trim'])
            ring=[(x,y,z) for x,y in blk['ring']];mesh.face(ring,mats['roof'])
            mesh.face([(x,y,z-.12) for x,y in blk['ring']],mats['soffit'],flip=True)
            continue
        n=len(wall)
        for i in range(n):
            p,q=wall[i],wall[(i+1)%n]
            if abs(F.k_of(p[0],p[1]))<.06 and abs(F.k_of(q[0],q[1]))<.06:continue   # the facade, built with its openings
            mesh.face([(p[0],p[1],found),(q[0],q[1],found),(q[0],q[1],q[2]+par),(p[0],p[1],p[2]+par)],mats['wall'])
        if blk['kind']=='dsm':
            ring=[(p[0],p[1]) for p in wall];pts=[(p[0],p[1]) for p in blk['points']];zs=[p[2] for p in wall]+[p[2] for p in blk['points']]
            out=delaunay_2d_cdt([Vector(v) for v in ring+pts],[],[list(range(len(ring)))],1,1e-5,True)
            verts,_,faces,orig,_,_=out
            for f in faces:
                tri=[]
                for vi in f:
                    o=[i for i in orig[vi] if i<len(zs)];tri.append((verts[vi].x,verts[vi].y,zs[o[0]] if o else zs[0]))
                mesh.face(tri,mats['roof'])
            continue
        if blk['kind']=='flat' and par:
            z=blk['roof'][0][0][2];outer=[(x,y) for x,y in blk['ring']];inner=blk.get('inner') or outer
            mesh.face([(x,y,z) for x,y in inner],mats['flatroof'])
            top=z+par
            for i in range(len(inner)):
                p,q=inner[i],inner[(i+1)%len(inner)];mesh.face([(q[0],q[1],z),(p[0],p[1],z),(p[0],p[1],top),(q[0],q[1],top)],mats['wall'])
            for i in range(len(outer)):
                # The parapet cap: approximate by matching each outer edge to the nearest inner edge direction.
                p,q=outer[i],outer[(i+1)%len(outer)]
                cx,cy=sum(v[0] for v in inner)/len(inner),sum(v[1] for v in inner)/len(inner)
                def inset(v):dx,dy=cx-v[0],cy-v[1];d=math.hypot(dx,dy) or 1;return (v[0]+dx/d*.2,v[1]+dy/d*.2)
                pi,qi=inset(p),inset(q);mesh.face([(p[0],p[1],top),(q[0],q[1],top),(qi[0],qi[1],top),(pi[0],pi[1],top)],mats['cap'])
            continue
        roof_mat=mats['flatroof'] if blk['kind'] in('flat','shed') else mats['roof']
        edges={}
        for face in blk['roof']:
            mesh.face(face,roof_mat)
            for p,q in zip(face,face[1:]+face[:1]):
                key=tuple(sorted([(round(p[0],2),round(p[1],2)),(round(q[0],2),round(q[1],2))]));edges[key]=edges.get(key,[])+[(p,q)]
        overhang=any(F.k_of(*p[:2])>.05 for face in blk['roof'] for p in face) or blk['kind'] in PITCHED
        if overhang:
            for face in blk['roof']:mesh.face([(x,y,z-.14) for x,y,z in face],mats['soffit'],flip=True)
            for key,es in edges.items():
                if len(es)==1:
                    p,q=es[0];mesh.face([(p[0],p[1],p[2]-.14),(q[0],q[1],q[2]-.14),(q[0],q[1],q[2]),(p[0],p[1],p[2])],mats['fascia'])
PITCHED=('hip','gable','gable-end')


def front_top(m,F):
    """The wall-top line along the facade [(s, z)] of every block that reaches it, plus parapets."""
    pts=sorted((F.s_of(p[0],p[1]),p[2]+(blk.get('parapet') or 0)) for blk in m['blocks'] for p in blk['wall'] if abs(F.k_of(p[0],p[1]))<.06)
    if len(pts)<2:blk=m['blocks'][0];z=max(p[2] for p in blk['wall'])+(blk.get('parapet') or 0);return [(0,z),(F.L,z)]
    pts=[(max(0,min(F.L,s)),z) for s,z in pts];pts[0]=(0,pts[0][1]);pts[-1]=(F.L,pts[-1][1])
    out=[]
    for p in pts:
        if not out or p[0]-out[-1][0]>.01:out.append(p)
    return out


def build_building(b,m,collection,mesh=None):
    F=Facade(m['facade'],m['floor']);zg=m['floor'];L=F.L;found=m['foundation']
    if not b.get('shopfront') and not b.get('open'):
        # Houses and service buildings sit at their own ground level (above a retaining wall or below the street),
        # with at least 2.5 m under the eave.
        zg=min(m.get('groundInside',zg),min(z for _,z in front_top(m,F))-(m['blocks'][0].get('parapet') or 0)-2.5)
    wall_spec=b.get('wall',{'cladding':'render','colour':'#d8d6d0'});trim=b.get('trim','#efefea')
    roof_colour=b.get('roofColour') or m.get('roofColour') or '#8a8d8c'
    mats=dict(wall=material(wall_spec['colour'],wall_spec.get('cladding','render'),.85),trim=material(trim,None,.6),
              roof=material(roof_colour,b.get('roofMaterial','corrugated'),.55,.25),flatroof=material(roof_colour,'corrugated',.6,.2),
              soffit=material('#e6e4de',None,.8),fascia=material(trim,None,.6),cap=material(wall_spec['colour'],None,.7),
              glass=material(GLASS,None,.08,.1),dark=material('#1d1f22',None,.7))
    own=mesh is None;mesh=mesh or Mesh();blocks(mesh,m,b,F,mats,False)
    if b.get('open'):return mesh.build(f"{b['id']} {b.get('name','')}"[:60],collection) if own else None
    ver=m.get('verandah') if b.get('verandah') else None
    vh=zg+(ver['height'] if ver else 3.2)
    # --- facade top: wall line, false front or deck ---
    base_top=front_top(m,F);segments=b.get('segments') or [dict(width=1,parapet=b.get('parapet'))]
    has_false=any(sg.get('parapet') for sg in segments)
    top=base_top
    if b.get('deck'):top=[(0,zg+3.85),(L,zg+3.85)]
    elif has_false:
        eave_front=min(z for _,z in base_top)-(m['blocks'][0].get('parapet') or 0)
        top=[];s=0.
        for sg in segments:
            w=sg['width']*L;p=sg.get('parapet') or {'shape':'flat','above':.4}
            if p.get('shape')=='gable':h=eave_front+.6
            else:h=max(zg+m['parapetTop'],eave_front+p.get('above',.4)) if p.get('above',.4)>.5 else eave_front+p.get('above',.4)
            for ps,pz in profile(p.get('shape','flat'),w,h,p):top.append((s+ps,pz))
            s+=w
        clean=[]
        for p in top:
            if not clean or abs(p[0]-clean[-1][0])>1e-3 or abs(p[1]-clean[-1][1])>1e-3:clean.append(p)
        top=clean
    # --- openings: shopfront and upper windows ---
    openings=[];details=[]
    sf=b.get('shopfront');ground_top=zg+min(3.6,(vh-zg)+.5)
    if sf:
        frame=material(sf.get('frame','#d9d9d6'),None,.5);stall=material(sf.get('stall',wall_spec['colour']),sf.get('stallMaterial'),.6)
        head=zg+min(2.75,vh-zg-.35) if ver else zg+(sf.get('glazed') and 3.2 or 2.75);sill=zg+.5
        d0=max(.35,min(L-1.35,sf.get('door',.5)*L-.5));d1=d0+1.0
        x0,x1=.3,L-.3
        if x1-x0<2.2:d0,d1=x0,x0+.95
        parts=[(x0,d0,sill,head),(d0,d1,zg,head),(d1,x1,sill,head)]
        for s0,s1,a,c in parts:
            if s1-s0<.25:continue
            openings.append((s0,s1,a,c))
            mesh.face([F.at(s0,-.1,a),F.at(s1,-.1,a),F.at(s1,-.1,c),F.at(s0,-.1,c)],mats['glass'] if a==sill else material('#2a2f33',None,.25))
            mesh.box(F.at,s0,s1,-.1,.02,c-.07,c,frame);mesh.box(F.at,s0,s0+.07,-.1,.02,a,c,frame);mesh.box(F.at,s1-.07,s1,-.1,.02,a,c,frame)
            if a==sill:mesh.box(F.at,s0,s1,-.1,.02,a,a+.07,frame)
            if a==zg:mesh.box(F.at,s0+.45,s0+.53,-.1,.0,zg,zg+2.15,frame);mesh.box(F.at,s0,s1,-.1,.02,zg+2.15,zg+2.22,frame)
            if a==sill:
                bays=max(1,round((s1-s0)/max(.8,(x1-x0)/sf.get('bays',3))))
                for i in range(1,bays):x=s0+(s1-s0)*i/bays;mesh.box(F.at,x-.035,x+.035,-.1,.02,a,c,frame)
                if sf.get('transom') or c-a>2.3:mesh.box(F.at,s0,s1,-.1,.02,c-.55,c-.48,frame)
            if a==sill:mesh.box(F.at,s0,s1,0,.03,zg-.3,sill,stall)
    # Houses and service buildings: ground-floor windows, a front door and garage or roller doors, at the
    # building's own ground level (houses can sit above a retaining wall or below the street), under the eave.
    taken=[(g['at']*L-g.get('width',2.6)/2-.2,g['at']*L+g.get('width',2.6)/2+.2) for g in b.get('garages',[])]
    for g in b.get('garages',[]):
        c=g['at']*L;w=g.get('width',2.6);h=g.get('height',2.4);door=material(g.get('colour','#d9d9d6'),None,.5)
        openings.append((c-w/2,c+w/2,zg,zg+h));mesh.face([F.at(c-w/2,-.12,zg-.3),F.at(c+w/2,-.12,zg-.3),F.at(c+w/2,-.12,zg+h),F.at(c-w/2,-.12,zg+h)],door)
        z=zg+.3
        while z<zg+h-.1:mesh.box(F.at,c-w/2,c+w/2,-.12,-.1,z,z+.03,door);z+=.32
        if g.get('windows'):mesh.face([F.at(c-w/2+.15,-.095,zg+h-.75),F.at(c+w/2-.15,-.095,zg+h-.75),F.at(c+w/2-.15,-.095,zg+h-.45),F.at(c-w/2+.15,-.095,zg+h-.45)],mats['glass'])
        mesh.box(F.at,c-w/2-.1,c+w/2+.1,0,.05,zg+h,zg+h+.12,mats['trim'])
    low=b.get('lower')
    if low:
        if low.get('door') is not None:
            c=low['door']*L;taken.append((c-.65,c+.65));openings.append((c-.45,c+.45,zg+.05,zg+2.1))
            dc=material(low.get('doorColour',trim),None,.5);mesh.face([F.at(c-.45,-.1,zg),F.at(c+.45,-.1,zg),F.at(c+.45,-.1,zg+2.1),F.at(c-.45,-.1,zg+2.1)],dc)
            mesh.box(F.at,c-.55,c+.55,0,.05,zg+2.1,zg+2.22,mats['trim']);mesh.box(F.at,c-.55,c-.45,0,.05,zg,zg+2.1,mats['trim']);mesh.box(F.at,c+.45,c+.55,0,.05,zg,zg+2.1,mats['trim'])
        k=low.get('windows',0);kind=low.get('type','single');w={'pair':1.75,'single':1.0}.get(kind,.85)
        for i in range(k):
            c=L*(i+.5)/k
            for a_,b_ in taken:                                        # slide clear of doors
                if c+w/2>a_ and c-w/2<b_:c=a_-w/2-.1 if c<(a_+b_)/2 else b_+w/2+.1
            if c-w/2<.3 or c+w/2>L-.3:continue
            openings.append((c-w/2,c+w/2,zg+.9,zg+2.2));details.append((c-w/2,c+w/2,zg+.9,zg+2.2,kind,low.get('hood')))
    upper=b.get('upper');storeys=b.get('storeys',1)
    wins=[]
    if storeys>=2:
        lo=max(ground_top,zg+3.4)+.75;eave=min(z for _,z in base_top)-(m['blocks'][0].get('parapet') or 0)
        # Windows stay under the eave: under a low eave the sill drops toward the verandah and the window shortens.
        hi=min(lo+1.55,eave-(.75 if b.get('frieze') else .35))
        if hi-lo<1.:lo=max(hi-1.,(vh+.3) if ver else zg+3.)
        if hi-lo<.6:hi=lo                                            # no room: no upper windows
        if b.get('segments'):
            s=0.
            for sg in b['segments']:
                w=sg['width']*L;k=sg.get('windows',0)
                for i in range(k):wins.append((s+w*(i+.5)/k,lo,hi,sg.get('windowType','sash'),sg.get('hood')))
                s+=w
        elif upper:
            k=upper['windows']
            for i in range(k):wins.append((L*(i+.5)/k,lo,hi,'pair' if i in upper.get('pairs',[]) else upper.get('type','sash'),upper.get('hood')))
    for sc,lo,hi,kind,hood in wins:
        if hi-lo<.6 or (sc-.5<.25 or sc+.5>L-.25):continue
        w={'pair':1.75,'louvre':1.5,'single':1.0}.get(kind,.85);s0,s1=sc-w/2,sc+w/2
        openings.append((s0,s1,lo,hi));details.append((s0,s1,lo,hi,kind,hood))
    reveal=material(trim,None,.6)
    wall_with_openings(mesh,F,top,found,openings,mats['wall'],reveal)
    # False-front back, ends and cap; or the deck's railing and canopy posts.
    if has_false or b.get('deck'):
        back=[F.at(0,-.22,found),F.at(L,-.22,found)]+[F.at(s,-.22,z) for s,z in reversed(top)]
        mesh.face(back,mats['wall'],flip=True)
        mesh.face([F.at(0,-.22,found),F.at(0,0,found),F.at(0,0,top[0][1]),F.at(0,-.22,top[0][1])],mats['wall'])
        mesh.face([F.at(L,0,found),F.at(L,-.22,found),F.at(L,-.22,top[-1][1]),F.at(L,0,top[-1][1])],mats['wall'])
    # A cap along the facade top, for parapets and false fronts (an eaved roof covers the wall top itself).
    eaved=any(blk['kind'] in PITCHED or blk['kind']=='dsm' for blk in m['blocks']) and not has_false and not b.get('deck')
    for (sa,za),(sb,zb) in ([] if eaved else zip(top,top[1:])):
        if sb-sa<1e-3:continue                                       # vertical steps of a shaped parapet
        pts=[Vector(F.at(sa,.09,za-.16)),Vector(F.at(sb,.09,zb-.16)),Vector(F.at(sb,.09,zb+.06)),Vector(F.at(sa,.09,za+.06))]
        mesh.face(pts,mats['cap'])
        mesh.face([F.at(sa,-.25,za+.06),F.at(sa,.09,za+.06),F.at(sb,.09,zb+.06),F.at(sb,-.25,zb+.06)][::-1],mats['cap'],flip=True)
        mesh.face([F.at(sa,0,za-.16),F.at(sb,0,zb-.16),F.at(sb,.09,zb-.16),F.at(sa,.09,za-.16)],mats['cap'])
    # Barge boards on gable-shaped parapets.
    s=0.
    for sg in segments:
        w=sg['width']*L;p=sg.get('parapet') or {}
        if p.get('shape')=='gable':
            barge=material(p.get('barge',trim),None,.6);pr=[pt for pt in top if s-1e-3<=pt[0]<=s+w+1e-3]
            for (sa,za),(sb,zb) in zip(pr,pr[1:]):
                mesh.face([F.at(sa,.12,za-.3),F.at(sb,.12,zb-.3),F.at(sb,.12,zb+.05),F.at(sa,.12,za+.05)],barge)
            mesh.box(F.at,s+w/2-.05,s+w/2+.05,0,.14,max(z for _,z in pr)-1.1,max(z for _,z in pr)-.2,barge)
        s+=w
    # Pilasters at the facade ends of two-storey and timber buildings.
    if (storeys>=2 or wall_spec.get('cladding') in('weatherboard','corrugated')) and not LIGHT:
        for s0,s1 in ((0,.22),(L-.22,L)):
            z1=min(z for _,z in top)-.18
            mesh.box(F.at,s0,s1,0,.06,found,z1,mats['trim'])
    # Upper windows.
    for s0,s1,lo,hi,kind,hood in details:
        mesh.box(F.at,s0-.12,s1+.12,0,.09,lo-.08,lo,mats['trim'],skip=('back',))
        if LIGHT:                                                    # typical windows: glass, sill and a centre rail
            mesh.face([F.at(s0,-.1,lo),F.at(s1,-.1,lo),F.at(s1,-.1,hi),F.at(s0,-.1,hi)],mats['glass'])
            mid=(lo+hi)/2;mesh.face([F.at(s0,-.09,mid-.03),F.at(s1,-.09,mid-.03),F.at(s1,-.09,mid+.03),F.at(s0,-.09,mid+.03)],mats['trim']);continue
        mesh.box(F.at,s0-.09,s1+.09,0,.04,hi,hi+.12,mats['trim'])
        mesh.box(F.at,s0-.09,s0,0,.04,lo,hi,mats['trim']);mesh.box(F.at,s1,s1+.09,0,.04,lo,hi,mats['trim'])
        if kind=='louvre':
            lv=material(b['upper'].get('colour','#6b4f3a'),None,.7);mesh.face([F.at(s0,-.1,lo),F.at(s1,-.1,lo),F.at(s1,-.1,hi),F.at(s0,-.1,hi)],lv)
            z=lo+.08
            while z<hi-.08:mesh.box(F.at,s0,s1,-.1,-.02,z,z+.04,lv);z+=.14
        else:
            mesh.face([F.at(s0,-.1,lo),F.at(s1,-.1,lo),F.at(s1,-.1,hi),F.at(s0,-.1,hi)],mats['glass'])
            mid=(lo+hi)/2;mesh.box(F.at,s0,s1,-.1,-.03,mid-.03,mid+.03,mats['trim'])
            if kind=='pair':c=(s0+s1)/2;mesh.box(F.at,c-.05,c+.05,-.1,-.01,lo,hi,mats['trim'])
        if hood:mesh.box(F.at,s0-.15,s1+.15,0,.3,hi+.12,hi+.2,mats['trim'])
    # Brackets under the eaves.
    if b.get('brackets'):
        eave=min(z for _,z in base_top);x=.4
        while x<L-.3:mesh.box(F.at,x-.06,x+.06,0,.4,eave-.32,eave-.02,mats['trim']);x+=.9
    # Frieze lettering under the eave.
    if b.get('frieze'):
        eave=min(z for _,z in base_top);fz=b['frieze']
        mesh.box(F.at,.3,L-.3,0,.03,eave-.62,eave-.12,mats['trim'])
        text(mesh,F,fz['text'],L/2,eave-.37,L-.9,.5,.035,material(fz.get('textColour','#2b2b2b'),None,.6))
    # A painted mural (a watermelon slice: red flesh, green rind).
    if b.get('mural'):
        mu=b['mural'];sc=L*mu.get('at',.25);zc=(details[0][2]+details[0][3])/2+.45 if details else zg+4.6;r=.95
        rind=[F.at(sc+r*math.cos(math.pi+math.pi*i/16),.02,zc+r*math.sin(math.pi+math.pi*i/16)) for i in range(17)]
        mesh.face(rind,material(mu.get('rind','#3f8a3a'),None,.7))
        flesh=[F.at(sc+(r-.14)*math.cos(math.pi+math.pi*i/16),.03,zc-.0+(r-.14)*math.sin(math.pi+math.pi*i/16)) for i in range(17)]
        mesh.face(flesh,material(mu.get('colour','#d8494a'),None,.7))
        for i in range(5):mesh.box(F.at,sc-.5+i*.25-.03,sc-.5+i*.25+.03,.03,.04,zc-.45,zc-.35,mats['dark'])
    # Facade signs.
    signs=[]
    if b.get('sign'):signs.append((0,L,b['sign']))
    s=0.
    for sg in b.get('segments') or []:
        w=sg['width']*L
        if sg.get('sign'):signs.append((s,s+w,sg['sign']))
        s+=w
    for s0,s1,sg in signs:
        w=(s1-s0)*sg.get('width',.86);c=(s0+s1)/2
        z0=(vh+.25) if ver else zg+2.85;z1=min(z0+.75,min(z for _,z in top)-.25)
        if z1-z0<.3:z0,z1=zg+2.8,zg+3.25
        board=material(sg.get('colour','#f2f2ee'),None,.5);mesh.box(F.at,c-w/2,c+w/2,0,.05,z0,z1,board)
        text(mesh,F,sg['text'],c,(z0+z1)/2,w-.2,z1-z0,.056,material(sg.get('textColour','#222222'),None,.5))
    # Lettering on the false front.
    s=0.
    for sg in segments:
        w=sg['width']*L;p=sg.get('parapet') or {}
        if p.get('text'):
            colour=material(p.get('textColour','#f2f2f0'),None,.5);lo_t=vh+.35 if ver else zg+3.
            heads=[d_[3] for d_ in details if d_[1]>s and d_[0]<s+w]
            if heads:lo_t=max(heads)+.3
            # Lettering stays under the parapet across its whole width (an arch rises only in the middle).
            hi_t=min(top_at(top,s+w*(.075+.85*i/20)) for i in range(21))-.25
            if hi_t-lo_t<.5:lo_t=hi_t-.5
            if p.get('text2'):
                mid=(lo_t+hi_t)/2;text(mesh,F,p['text'],s+w/2,(mid+hi_t)/2,w*.82,hi_t-mid,.03,colour);text(mesh,F,p['text2'],s+w/2,(lo_t+mid)/2,w*.82,mid-lo_t,.03,colour)
            else:text(mesh,F,p['text'],s+w/2,(lo_t+hi_t)/2,w*.85,min(1.1,hi_t-lo_t),.03,colour)
        s+=w
    # Deck: a balustrade along the front and posts carrying the canopy (the block roof).
    if b.get('deck'):
        dk=b['deck'];rail=material(dk.get('railing','#222222'),None,.5);fl=zg+3.85;canopy=min(z for z in [p[2] for p in m['blocks'][0]['wall']])
        mesh.box(F.at,0,L,-.05,.0,fl+.95,fl+1.,rail);x=0.
        while x<=L:mesh.box(F.at,max(0,x-.03),min(L,x+.03),-.05,0,fl,fl+1.,rail);x+=1.2
        mesh.face([F.at(0,-.03,fl),F.at(L,-.03,fl),F.at(L,-.03,fl+.95),F.at(0,-.03,fl+.95)],material('#2c2c2c',None,.6))
        for x in (.12,L/2,L-.12):mesh.box(F.at,x-.06,x+.06,-.3,-.18,fl,canopy-.1,rail)
        ring=m['blocks'][0]['ring'];mesh.face([(x,y,fl) for x,y in ring],material('#8a6a4a','timber',.8))
    # Verandah.
    if ver:
        vb=b['verandah'];d=ver['depth'];fascia=material(vb.get('fascia','#efefea'),None,.6);fh=vb.get('fasciaHeight',.3)
        under=material('#ecebe6',None,.8)
        if vb.get('type')=='sloped':
            roofm=material(vb.get('colour','#b5b8b6'),'corrugated',.5,.3);hin=vh+.5
            mesh.face([F.at(0,0,hin),F.at(0,d,vh),F.at(L,d,vh),F.at(L,0,hin)],roofm)
            mesh.face([F.at(0,0,hin-.06),F.at(L,0,hin-.06),F.at(L,d,vh-.06),F.at(0,d,vh-.06)],under)
            mesh.box(F.at,0,L,d-.05,d+.05,vh-fh,vh+.02,fascia)
            for s0 in (0,L):mesh.face([F.at(s0,0,hin),F.at(s0,d,vh),F.at(s0,d,vh-.06),F.at(s0,0,hin-.06)],fascia)
        else:
            mesh.box(F.at,0,L,0,d,vh-.15,vh,under,skip=('back',))
            mesh.box(F.at,0,L,d-.04,d+.04,vh-fh*.7,vh+fh*.3,fascia)
        under_z=vh-(.06 if vb.get('type')=='sloped' else .15)
        if vb.get('text'):
            text(mesh,F,vb['text'],L/2,vh-fh*.7+fh/2 if vb.get('type')!='sloped' else vh-fh/2,L*.9,fh,d+(.045 if vb.get('type')!='sloped' else .056),material(vb.get('textColour','#ffffff'),None,.5))
        for pnl in vb.get('panels',[]):
            c=L*(pnl['at']+pnl['width']/2);w=L*pnl['width'];z0=vh-fh*.7+.04;z1=vh+fh*.3-.04
            mesh.box(F.at,c-w/2,c+w/2,d+.04,d+.06,z0,z1,material(pnl['colour'],None,.5))
            text(mesh,F,pnl['text'],c,(z0+z1)/2,w-.1,z1-z0,d+.065,material(pnl.get('textColour','#ffffff'),None,.5))
        post=material(vb.get('post','#efefea'),None,.6)
        for x,y,z in m.get('posts',[]):
            s_=F.s_of(x,y);kk=F.k_of(x,y);mesh.box(F.at,s_-.05,s_+.05,kk-.05,kk+.05,z-.4,under_z,post)
            if vb.get('brackets'):
                for sgn in (-1,1):mesh.box(F.at,s_+sgn*.05-(.25 if sgn<0 else 0),s_+sgn*.05+(.25 if sgn>0 else 0),kk-.03,kk+.03,under_z-.12,under_z,post)
    return mesh.build(f"{b['id']} {b.get('name','')}"[:60],collection) if own else None


def build_chunks(root):
    """Typed buildings merged into one mesh per chunk; a vertex attribute says which building it belongs to."""
    measured={m['id']:m for m in job['measured']};specs={b['id']:b for b in job['spec']['buildings']};total=0
    for chunk in job['chunks']:
        mesh=Mesh();ids=[]
        for bid in chunk['ids']:
            mesh.tag=len(ids)+1;b=specs[bid]                        # 0 is reserved for "no building"
            try:build_building(b,measured[bid],None,mesh);ids.append(bid)
            except Exception as error:
                log(f'{bid} not built: {type(error).__name__} {str(error)[:80]}')
                # Drop its partial geometry (vertices stay, unreferenced, and are removed by validate()).
                keep=[k for k,f in enumerate(mesh.faces) if mesh.tags[f[0]]!=mesh.tag]
                mesh.faces=[mesh.faces[k] for k in keep];mesh.mats=[mesh.mats[k] for k in keep]
        if not mesh.faces:continue
        ob=mesh.build(chunk['name'],root);ob['chunk']=chunk['name']
        ob['ids']=json.dumps(ids);ob['types']=json.dumps([specs[i].get('type','') for i in ids])
        ob['storeys']=json.dumps([specs[i].get('storeys',1) for i in ids]);ob['names']=json.dumps([specs[i].get('name') or '' for i in ids])
        ob['replaces']=','.join(r for i in ids for r in [i]+specs[i].get('replaces',[]));total+=len(ids)
        log(f"{chunk['name']:<14} {len(ids):4d} buildings {len(ob.data.polygons):7d} faces")
    return total


def build():
    for o in list(bpy.data.objects):bpy.data.objects.remove(o)
    measured={m['id']:m for m in job['measured']};root=bpy.data.collections.new('Street buildings');bpy.context.scene.collection.children.link(root)
    count=build_chunks(root) if job.get('chunks') else 0
    for b in ([] if job.get('chunks') else job['spec']['buildings']):
        m=measured.get(b['id'])
        if not m:continue
        col=bpy.data.collections.new((b.get('name') or b['id'])[:60]);root.children.link(col)
        ob=build_building(b,m,col);ob['osm_id']=b['id'];ob['replaces']=','.join([b['id']]+b.get('replaces',[]));ob['name']=b.get('name','')
        ob['evidence']=b.get('evidence','');count+=1
        log(f"{b['id']:<18} {len(ob.data.polygons):5d} faces  {b.get('name','')}")
    bpy.ops.file.pack_all()                                       # the .blend carries its textures
    bpy.ops.wm.save_as_mainfile(filepath=job['blend'])
    log(f'built {count} buildings -> {job["blend"]}')


if job['mode']=='build':build()
else:bpy.ops.wm.open_mainfile(filepath=job['blend'])
export()
