"""Native slicing/detaching keeps UV, vertex color and material channels."""
import math
import random

from ..adapter import selection as S


def _bits(rt, indices, count):
    out=rt.BitArray()
    out.count=count
    for i in indices:
        out[int(i)]=True
    return out


def _split(source, xs, ys, cut, name, scatter=None, separate_materials=False, center_origin=False):
    rt=S._rt()
    work=rt.copy(source)
    out=[]
    try:
        rt.convertToMesh(work)
        mesh=work.mesh
        world=[rt.getVert(mesh,i)*work.transform for i in range(1,int(rt.getNumVerts(mesh))+1)]
        if not world:
            return out
        bounds=[(min(getattr(v,a) for v in world),max(getattr(v,a) for v in world)) for a in ('x','y','z')]
        if cut=='EXACT' and not scatter:
            inverse=rt.inverse(work.transform)
            planes=[]
            for axis,step in ((0,xs),(1,ys)):
                lo,hi=bounds[axis]
                for k in range(math.floor(lo/step)+1,math.ceil(hi/step)):
                    if len(planes)>10000:
                        raise ValueError('Grid would create more than 10000 slice planes')
                    if axis==0:
                        a,b,c=rt.Point3(k*step,0,0),rt.Point3(k*step,1,0),rt.Point3(k*step,0,1)
                    else:
                        a,b,c=rt.Point3(0,k*step,0),rt.Point3(0,k*step,1),rt.Point3(1,k*step,0)
                    a,b,c=a*inverse,b*inverse,c*inverse
                    normal=rt.normalize(rt.cross(b-a,c-a))
                    planes.append((normal,rt.dot(a,normal)))
            for normal,offset in planes:
                rt.meshop.slice(mesh,_bits(rt,range(1,int(rt.getNumFaces(mesh))+1),int(rt.getNumFaces(mesh))),normal,offset)
            work.mesh=mesh
            rt.update(work)
        seeds=[]
        if scatter:
            count,seed=scatter
            rng=random.Random(seed)
            seeds=[tuple(rng.uniform(lo,hi) for lo,hi in bounds) for _ in range(count)]
        groups={}
        for i in range(1,int(rt.getNumFaces(mesh))+1):
            face=rt.getFace(mesh,i)
            pts=[rt.getVert(mesh,int(j))*work.transform for j in (face.x,face.y,face.z)]
            center=tuple(sum(getattr(p,a) for p in pts)/3 for a in ('x','y','z'))
            key=(min(range(len(seeds)),key=lambda j:sum((a-b)**2 for a,b in zip(center,seeds[j]))),) if seeds else (math.floor(center[0]/xs),math.floor(center[1]/ys))
            groups.setdefault(key,[]).append(i)
        for key,faces in groups.items():
            fragment=rt.meshop.detachFaces(mesh,_bits(rt,faces,int(rt.getNumFaces(mesh))),delete=False,asMesh=True)
            try:
                node=rt.Editable_mesh(name=rt.uniqueName(name+'_'+'_'.join(str(v) for v in key)))
                node.mesh=fragment
                node.transform=rt.copy(source.transform)
                node.material=rt.copy(source.material) if separate_materials and source.material is not None else source.material
                for prop,value in S.get_flags(source).items():
                    S.set_flag([node],prop,value)
                S.put_field([node],'type',S.get_field(source,'type','OBJ'))
                if center_origin:
                    rt.centerPivot(node)
                rt.update(node)
                out.append(node)
            finally:
                rt.delete(fragment)
        return out
    finally:
        rt.delete(work)


def fragment_mesh(mode='GRID', xstep=2, ystep=2, count=10, seed=0, name='model_frag', delete_original=True):
    rt=S._rt()
    nodes=S.selected_meshes()
    if xstep<=0 or ystep<=0 or count<2:
        raise ValueError('Fragment step must be positive and cluster count at least 2')
    if any(list(node.modifiers) for node in nodes):
        raise ValueError('Collapse modifier stacks before fragmenting meshes')
    created=[]
    with S.undo_block('INU: Fragment Mesh'):
        for node in nodes:
            parts=_split(node,xstep,ystep,'EXACT',name,scatter=(count,seed) if mode=='SCATTER' else None)
            created.extend(parts)
            if parts and delete_original:
                rt.delete(node)
        if created:
            rt.select(rt.Array(*created))
    rt.redrawViews()
    return 'INFO','Created %d mesh fragments' % len(created)


def chunk_map(size=180, cut='EXACT', separate_materials=False, center_origin=True, hide_original=True):
    rt=S._rt()
    if size<=0:
        raise ValueError('Chunk size must be positive')
    created=[]
    with S.undo_block('INU: Split Map Chunks'):
        for node in S.selected_meshes():
            parts=_split(node,size,size,cut,str(node.name)+'_Chunk',separate_materials=separate_materials,center_origin=center_origin)
            created.extend(parts)
            if parts and hide_original:
                node.isHidden=True
        if created:
            rt.select(rt.Array(*created))
    rt.redrawViews()
    return 'INFO','Created %d map chunks' % len(created)


OPERATIONS={'fragment_mesh':fragment_mesh,'chunk_map':chunk_map}
