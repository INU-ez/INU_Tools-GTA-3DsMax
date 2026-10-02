"""Animated map-object rigs use ordinary Max helpers and rotation keys."""
import math
import os

from inu_gta_core.ifp import IFPFile,read_ifp,write_ifp,merge_ifp
from ..adapter import selection as S,anim as A
from .. import settings
from .anim_tools import sample_animation


def add_pivot(mesh=None):
    import pymxs
    rt=S._rt()
    root=A.rig_of(S.active_node()) or A.find_rig()
    if root is None:
        raise ValueError('Create an animated object rig first')
    name=settings.get('pv_name','pivot')
    axis=settings.get('pv_axis','Z')
    turns=int(settings.get('pv_turns',1))
    duration=int(settings.get('pv_duration',60))
    if duration<=0 or turns<=0:
        raise ValueError('Pivot duration and turns must be positive')
    nodes=[root]+A.pivots(root)
    ids={S.get_field(n,'bone_id',-1) for n in nodes}
    bone_id=next(i for i in range(1,100000) if i not in ids)
    with S.undo_block('INU: Add Animated Pivot'):
        pivot=rt.Point(name=rt.uniqueName(str(root.name)+'_'+name),size=2,box=True)
        pivot.parent=root
        pivot.pos=rt.copy(mesh.pos) if mesh is not None else rt.copy(root.pos)
        for key,value in dict(animobj_empty_pivot=True,bone_id=bone_id,axis=axis,
            auto_mode=True,turns_per_cycle=turns,duration_frames=duration,anim_name=name).items():
            S.put_field([pivot],key,value)
        regenerate_pivot(pivot)
        if mesh is not None and settings.get('pv_parent_mesh',True):
            world=rt.copy(mesh.transform)
            mesh.parent=pivot
            mesh.transform=world
        S.put_field([root],'ifp_start',0.0)
        S.put_field([root],'ifp_end',float(duration))
        S.put_field([root],'ifp_current',name)
        rt.animationRange=rt.Interval(0,duration)
        rt.select(pivot)
    return pivot


def regenerate_pivot(pivot):
    import pymxs
    rt = S._rt()
    if not S.get_field(pivot, 'auto_mode', True):
        return
    axis = S.get_field(pivot, 'axis', 'Z')
    duration = int(S.get_field(pivot, 'duration_frames', 60))
    turns = int(S.get_field(pivot, 'turns_per_cycle', 1))
    segments = max(duration, turns * 8)
    if axis not in 'XYZ' or duration <= 0 or turns <= 0 or segments > 100000:
        raise ValueError('Invalid pivot cycle settings')
    direction = -1 if S.get_field(pivot, 'reverse', False) else 1
    from .anim_tools import keyed_controllers
    with S.undo_block('INU: Pivot Cycle'):
        controller = rt.getPropertyController(pivot, rt.Name('rotation'))
        for track, count in keyed_controllers(controller):
            if count:
                rt.deleteKeys(track, rt.Name('allKeys'))
        for i in range(segments + 1):
            with pymxs.animate(True), pymxs.attime(duration * i / segments):
                local = rt.copy(pivot.transform)
                if pivot.parent is not None:
                    local *= rt.inverse(pivot.parent.transform)
                tm = rt.Matrix3(rt.Quat(direction * 360 * turns * i / segments,
                    rt.Point3(*(1 if a == axis else 0 for a in 'XYZ'))))
                tm.row4 = local.row4
                pivot.transform = tm * pivot.parent.transform if pivot.parent is not None else tm
        root = A.rig_of(pivot)
        if root is not None:
            S.put_field([root], 'ifp_end', float(duration))
        rt.animationRange = rt.Interval(0, duration)


def animobj_add_pivot():
    node=add_pivot(S.active_node() if S.node_kind(S.active_node())=='MESH' else None)
    return 'INFO','Created '+str(node.name)


def animobj_pick(target=None):
    rt=S._rt()
    mesh=rt.pickObject(prompt='INU: Pick the animated mesh')
    if mesh is None:
        return 'INFO','Mesh picking cancelled'
    if S.node_kind(mesh)!='MESH':
        raise ValueError('Pick a mesh object')
    root=A.find_rig()
    with S.undo_block('INU: Animated Object Rig'):
        if root is None:
            root=rt.Point(name=rt.uniqueName(str(mesh.name)+'_rig'),size=3,box=True,pos=rt.copy(mesh.pos))
            S.put_field([root],'animobj_empty_root',True)
            S.put_field([root],'bone_id',0)
        world=rt.copy(mesh.transform)
        rt.select(root)
        choice=target or settings.get('animobj_picker_target','NEW_PIVOT')
        if choice=='NEW_PIVOT':
            pivot=add_pivot(mesh)
            mesh.parent=pivot
        elif choice=='PIVOT':
            pivot=A.first_pivot(root)
            if pivot is None:
                raise ValueError('Rig has no existing pivot')
            mesh.parent=pivot
        else:
            mesh.parent=root
        mesh.transform=world
        rt.select(mesh)
    return 'INFO','Attached '+str(mesh.name)+' to '+str(root.name)


def animobj_attach_mesh():
    root=A.find_rig()
    if root is None:
        raise ValueError('No animated object rig')
    return animobj_pick(S.get_field(root,'attach_target','NEW_PIVOT'))


def animobj_validate():
    root=A.rig_of(S.active_node()) or A.find_rig()
    if root is None:
        return 'ERROR','No animated object rig'
    pivots=A.pivots(root)
    issues=[]
    ids=[S.get_field(n,'bone_id',-1) for n in [root]+pivots]
    if not pivots:
        issues.append('No animated pivots')
    if S.get_field(root,'bone_id',-1)!=0:
        issues.append('Root BoneID must be 0')
    if len(set(ids))!=len(ids) or any(i<0 for i in ids):
        issues.append('BoneIDs must be unique and non-negative')
    if A.first_mesh(root) is None:
        issues.append('Rig has no mesh children')
    from .anim_tools import keyed_controllers
    for pivot in pivots:
        controller=S._rt().getPropertyController(pivot,S._rt().Name('rotation'))
        if len({float(S._rt().getKeyTime(track, i).frame) for track, count in keyed_controllers(controller) for i in range(1, count + 1)}) < 2:
            issues.append(str(pivot.name)+': needs at least two rotation keys')
    return ('ERROR' if issues else 'INFO'),'\n'.join(issues) if issues else 'Animated object rig is valid'


def _write_anim_ide(path,model_id,name,txd,ifp,draw):
    from inu_gta_core.ide import read_ide
    if os.path.isfile(path):
        doc=read_ide(path)
        for entry in list(doc.objects)+list(doc.anims)+list(doc.cars)+list(doc.peds)+list(doc.weaps)+list(doc.hiers):
            if entry.model_id==model_id and entry.model_name.lower()!=name.lower():
                raise ValueError('IDE ID is already occupied: %d'%model_id)
        with open(path,'rb') as stream:
            raw=stream.read()
    else:
        raw=b''
    lines=raw.splitlines(keepends=True)
    ending=b'\r\n' if b'\r\n' in raw else b'\n'
    entry=('%d, %s, %s, %s, %g, 0'%(model_id,name,txd,ifp,draw)).encode('ascii')+ending
    section=''
    insert=None
    replaced=False
    for i,line in enumerate(lines):
        text=line.strip().decode('ascii',errors='ignore')
        if text.lower() in ('anim', 'objs', 'tobj'):
            section=text.lower()
        elif text.lower()=='end':
            if section=='anim':
                insert=i
            section=''
        elif section in ('anim', 'objs', 'tobj') and ',' in text:
            values=text.split(',')
            if values[0].strip()==str(model_id) or (len(values)>1 and values[1].strip().lower()==name.lower()):
                lines[i]=entry if section == 'anim' else b''
                replaced = replaced or section == 'anim'
    if not replaced:
        if insert is not None:
            lines.insert(insert,entry)
        else:
            if lines and not lines[-1].endswith((b'\n',b'\r')):
                lines[-1]+=ending
            lines.extend([b'anim'+ending,entry,b'end'+ending])
    with open(path,'wb') as stream:
        stream.write(b''.join(lines))


def animobj_export():
    from . import dff_export as D
    root=A.rig_of(S.active_node()) or A.find_rig()
    level,text=animobj_validate()
    if level=='ERROR':
        return level,text
    folder=settings.get('ao_directory','')
    name=settings.get('ao_base_name','').strip()
    if not folder or not name or any(c in name for c in '/\\:\x00'):
        raise ValueError('Choose an export folder and valid base name')
    model_id=int(settings.get('ao_model_id',0))
    if model_id<=0:
        raise ValueError('Animated object needs a positive Model ID')
    txd=settings.get('ao_txd_name','') or name
    clip=sample_animation(root,name)
    ifp_name=settings.get('ao_ifp_name','') or name
    existing=settings.get('ao_existing_ifp','')
    ifp_path=existing or os.path.join(folder,ifp_name+'.ifp')
    ifp_name=os.path.splitext(os.path.basename(ifp_path))[0]
    mode=settings.get('ao_ifp_mode','APPEND')
    if mode=='UPDATE':
        original=read_ifp(ifp_path)
        if clip.name.lower() not in {a.name.lower() for a in original.animations}:
            raise ValueError('Refresh matches: animation is absent from the target IFP')
    opts=D._opts()
    warnings=[]
    os.makedirs(folder,exist_ok=True)
    with D._sr().full_result():
        export_nodes=D._nodes_for(D._hierarchy(root),opts['pipeline'])
        dff=D.dff_bytes(name,export_nodes,[],opts,warnings)
        meshes=[node for node,_ in S.hierarchy(root)[1] if S.node_kind(node)=='MESH']
        txd_bytes,_=D.txd_data(txd,meshes,opts,warnings)
    import tempfile
    import shutil
    from .file_write import write_batch
    payloads = {os.path.join(folder, name + '.dff'): dff}
    if txd_bytes:
        payloads[os.path.join(folder, txd + '.txd')] = txd_bytes
    fmt = settings.get('ao_ifp_format', 'ANPK')
    with tempfile.TemporaryDirectory(dir=folder, prefix='.inu_anim_') as stage:
        staged_ifp = os.path.join(stage, ifp_name + '.ifp')
        if mode == 'NEW' or not os.path.isfile(ifp_path):
            write_ifp(staged_ifp, IFPFile(ifp_name, [clip]), format=fmt, target=settings.get('game', 'SA'))
        else:
            shutil.copy2(ifp_path, staged_ifp)
            merge_ifp(staged_ifp, [clip], format=fmt, target=settings.get('game', 'SA'))
        read_ifp(staged_ifp)
        with open(staged_ifp, 'rb') as stream:
            payloads[ifp_path] = stream.read()
        if settings.get('ao_write_ide', True):
            ide = settings.get('ide_path', '')
            if not ide:
                raise ValueError('Choose an IDE path before exporting the animated object')
            staged_ide = os.path.join(stage, 'model.ide')
            if os.path.isfile(ide):
                shutil.copy2(ide, staged_ide)
            _write_anim_ide(staged_ide, model_id, name, txd, ifp_name,
                            float(settings.get('ao_draw_distance', 300)))
            with open(staged_ide, 'rb') as stream:
                payloads[ide] = stream.read()
        write_batch(payloads)
    return ('WARNING' if warnings else 'INFO'),'Exported animated DFF, IFP and textures'+('\n'+'\n'.join(warnings) if warnings else '')


OPERATIONS={name:globals()[name] for name in ('animobj_add_pivot','animobj_pick',
    'animobj_attach_mesh','animobj_validate','animobj_export')}
