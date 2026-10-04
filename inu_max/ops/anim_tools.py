"""Native Max skeletal animation operations backed by the shared IFP codec."""
import os
import math
import tempfile

from inu_gta_core.ifp import read_ifp, write_ifp, merge_ifp, IFPFile, Animation, AnimBone, KeyFrame, HAS_ROT, HAS_TRANS
from ..adapter import selection as S, anim as A
from .. import settings


def _rig():
    root = A.rig_of(S.active_node()) or A.skeleton_root(S.active_node())
    if root is None:
        raise ValueError('Select a skeleton first')
    return root


def _descendants(root):
    pending = [(root, 0)]
    while pending:
        node, depth = pending.pop()
        yield node, depth
        pending.extend((child, depth + 1) for child in reversed(list(node.children)))


def _bones(root):
    return [node for node, _ in _descendants(root)
            if S.node_kind(node) == 'BONE' or S.get_field(node, 'bone_id', -1) >= 0]


def keyed_controllers(controller):
    """Walk compound controllers such as Euler XYZ to their keyed tracks."""
    rt = S._rt()
    if controller is None:
        return
    children = []
    for index in range(1, int(getattr(controller,'numSubs',0)) + 1):
        child = rt.getSubAnim(controller, index).controller
        if child is not None:
            children.append(child)
    if children:
        for child in children:
            yield from keyed_controllers(child)
    else:
        count = int(rt.numKeys(controller))
        if count >= 0:
            yield controller, count


def _clip(name):
    for entry in A.library():
        if name in entry.get('anims', []):
            for clip in read_ifp(entry['path']).animations:
                if clip.name == name:
                    return clip
    raise ValueError('Animation not found in the IFP library: ' + name)


def apply_clip(clip, root, start=0, replace=True):
    import pymxs
    rt = S._rt()
    bones = _bones(root)
    rt.execute('global inuAnimQuatTM; fn inuAnimQuatTM q = (q as matrix3)')
    by_id = {S.get_field(n, 'bone_id', -1): n for n in bones if S.get_field(n, 'bone_id', -1) >= 0}
    by_name = {str(n.name).strip().casefold(): n for n in bones}
    matched, missing = [], []
    for bone in clip.bones:
        node = by_id.get(bone.bone_id) if bone.bone_id >= 0 else None
        node = node if node is not None else by_name.get(bone.name.strip().casefold())
        if node is None:
            missing.append(bone.name)
        else:
            matched.append((node, bone))
    if not matched:
        raise ValueError('No IFP bones match the selected skeleton')
    # Parent animation must be evaluated before computing each child's world TM.
    depths = {int(rt.getHandleByAnim(n)): d for n, d in _descendants(root)}
    matched.sort(key=lambda pair: depths.get(int(rt.getHandleByAnim(pair[0])), 0))
    fps = A.frame_rate()
    end = max((k.time for _, b in matched for k in b.keyframes), default=0) * fps + start
    with S.undo_block('INU: Apply IFP'):
        for node, bone in matched:
            with pymxs.attime(start):
                rest = rt.copy(node.transform)
                if node.parent is not None:
                    rest *= rt.inverse(node.parent.transform)
                if not S.get_field(node, 'ifp_rest_position', ''):
                    S.put_field([node], 'ifp_rest_position', (rest.row4.x, rest.row4.y, rest.row4.z))
            if replace:
                rt.deleteKeys(node.controller, rt.Name('allKeys'))
            for key in bone.keyframes:
                with pymxs.animate(True), pymxs.attime(start + key.time * fps):
                    local = rt.inuAnimQuatTM(rt.Quat(*key.rotation))
                    local.row4 = (rt.Point3(*key.translation) if bone.key_type & HAS_TRANS else rest.row4)
                    node.transform = local * node.parent.transform if node.parent is not None else local
        S.put_field([root], 'ifp_current', clip.name)
        S.put_field([root], 'ifp_start', float(start))
        S.put_field([root], 'ifp_end', float(end))
        rt.animationRange = rt.Interval(start, end)
    rt.redrawViews()
    return len(matched), missing


def apply_ifp():
    name = settings.get('ifp_action', '')
    count, missing = apply_clip(_clip(name), _rig())
    return ('WARNING' if missing else 'INFO'), ('Applied %s to %d bones' % (name, count) +
        ('\nMissing bones: ' + ', '.join(missing) if missing else ''))


def sample_animation(root, name=None):
    import pymxs
    rt = S._rt()
    fps = A.frame_rate()
    start = float(S.get_field(root, 'ifp_start', float(rt.animationRange.start.frame)))
    end = float(S.get_field(root, 'ifp_end', float(rt.animationRange.end.frame)))
    clip = Animation(name=name or S.get_field(root, 'ifp_current', '') or settings.get('ifp_action', '') or 'custom')
    from .dff_build import SA_PED_BONE_IDS
    for node in _bones(root):
        bone_id = S.get_field(node, 'bone_id', SA_PED_BONE_IDS.get(str(node.name).strip(), -1))
        bone = AnimBone(str(node.name), bone_id, HAS_ROT | HAS_TRANS)
        previous = None
        for frame in range(int(start), int(end) + 1):
            with pymxs.attime(frame):
                local = rt.copy(node.transform)
                if node.parent is not None:
                    local *= rt.inverse(node.parent.transform)
                q = local.rotationPart
                quat = (float(q.x), float(q.y), float(q.z), float(q.w))
                if previous and sum(a * b for a, b in zip(previous, quat)) < 0:
                    quat = tuple(-v for v in quat)
                p = local.row4
                bone.keyframes.append(KeyFrame(quat, (p.x, p.y, p.z), time=(frame - start) / fps))
                previous = quat
        clip.bones.append(bone)
    return clip


def export_ifp(path, format=None, merge=False):
    root = _rig()
    clip = sample_animation(root)
    from inu_gta_core.ifp import decimate_animation
    prefix='merge_' if merge else 'ifp_'
    if settings.get(prefix+'decimate',False):
        decimate_animation(clip,float(settings.get(prefix+'tol_rot',.001)),float(settings.get(prefix+'tol_trans',.001)))
    fmt = format or settings.get('ifp_format', 'ANPK')
    if settings.get('game', 'SA') != 'SA' and fmt == 'ANP3':
        fmt = 'ANPK'
    package = settings.get('ifp_package', 'custom')
    clips = [clip]
    if not merge and not settings.get('ifp_active_only', False):
        originals = {}
        for entry in A.library():
            for original in read_ifp(entry['path']).animations:
                originals[original.name] = original
        originals[clip.name] = clip
        clips = list(originals.values())
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, suffix='.ifp')
    os.close(fd)
    try:
        if merge and os.path.isfile(path):
            import shutil
            shutil.copy2(path, tmp)
            merge_ifp(tmp, [clip], package_name=settings.get('merge_package', '') or None,
                      target=settings.get('game', 'SA'))
        else:
            write_ifp(tmp, IFPFile(package, clips), format=fmt)
        checked = read_ifp(tmp)
        if clip.name not in [c.name for c in checked.animations]:
            raise ValueError('Written IFP is missing the exported animation')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return 'INFO', 'Exported %d animations to %s' % (len(checked.animations), path)


def delete_active_action():
    rt = S._rt()
    root = _rig()
    with S.undo_block('INU: Delete Animation'):
        for node in _bones(root):
            rt.deleteKeys(node.controller, rt.Name('allKeys'))
        S.put_field([root], 'ifp_current', '')
    rt.redrawViews()
    return 'INFO', 'Deleted skeleton animation keys'


def ifp_preview_toggle(on=True):
    rt = S._rt()
    if on:
        apply_ifp()
        rt.playAnimation(immediateReturn=True)
    else:
        rt.stopAnimation()
    return 'INFO', 'Animation preview ' + ('started' if on else 'stopped')


def add_ground_plane():
    from . import ik_rig
    rt = S._rt()
    plane = next((n for n in rt.objects if S.get_field(n, 'ik_ground', False)), None)
    with S.undo_block('INU: Ground Plane'):
        if plane is None:
            plane = rt.Plane(name=rt.uniqueName('INU_Ground'), length=10, width=10, lengthsegs=10, widthsegs=10)
            S.put_field([plane], 'preview', True)
            S.put_field([plane], 'type', 'NON')
            S.put_field([plane], 'ik_ground', True)
            plane.wirecolor = rt.Color(100, 100, 100)
        ik_rig.patch_floor()
    rt.redrawViews()
    return 'INFO', 'Ground plane is connected to IK foot controls'


def _ik_pairs(bones):
    names = {' '.join(str(n.name).lower().split()): n for n in bones}
    ids = {int(S.get_field(n, 'bone_id', -1)): n for n in bones
           if S.get_field(n, 'bone_id', -1) >= 0}
    pairs = []
    for label, start_id, end_id, start_name, end_name in (
            ('L_Arm', 32, 34, 'l upperarm', 'l hand'),
            ('R_Arm', 22, 24, 'r upperarm', 'r hand'),
            ('L_Leg', 41, 43, 'l thigh', 'l foot'),
            ('R_Leg', 51, 53, 'r thigh', 'r foot')):
        start = ids.get(start_id, names.get(start_name))
        end = ids.get(end_id, names.get(end_name))
        if start is None or end is None:
            continue
        ancestor = end.parent
        while ancestor is not None and ancestor != start:
            ancestor = ancestor.parent
        if ancestor == start:
            pairs.append((label, start, end))
    return pairs


def add_ik_rig():
    from . import ik_rig
    root = _rig()
    return ik_rig.add(root, _bones(root))


OPERATIONS = {name: globals()[name] for name in ('apply_ifp', 'export_ifp',
    'delete_active_action', 'ifp_preview_toggle', 'add_ground_plane', 'add_ik_rig')}


def bake_ik_rig():
    from . import ik_rig
    root = _rig()
    return ik_rig.bake(root, _bones(root))


def fix_quat_signs():
    rt=S._rt()
    count=0
    with S.undo_block('INU: Quaternion Signs'):
        for node in _bones(_rig()):
            controller=rt.getPropertyController(node,rt.Name('rotation'))
            previous=None
            for i in range(1,int(rt.numKeys(controller))+1):
                key=rt.getKey(controller,i)
                q=key.value
                if not all(hasattr(q,k) for k in ('x','y','z','w')):
                    continue
                values=(q.x,q.y,q.z,q.w)
                norm=sum(v*v for v in values)**.5
                if norm<1e-12:
                    raise ValueError('%s: zero quaternion key' % node.name)
                values=tuple(v/norm for v in values)
                if previous and sum(a*b for a,b in zip(previous,values))<0:
                    values=tuple(-v for v in values)
                    count+=1
                key.value=rt.Quat(*values)
                previous=values
    return 'INFO','Fixed %d quaternion sign transitions' % count


def mirror_anim():
    rt=S._rt()
    root=_rig()
    clip=sample_animation(root)
    names={str(n.name).strip().lower():n for n in _bones(root)}
    for bone in clip.bones:
        name=bone.name.strip()
        twin=('R'+name[1:] if name.startswith('L ') else 'L'+name[1:] if name.startswith('R ') else name)
        target=names.get(twin.lower())
        if target is not None:
            bone.name=str(target.name)
            bone.bone_id=S.get_field(target,'bone_id',bone.bone_id)
        is_root=bone.bone_id==0 or name.lower()=='root'
        for key in bone.keyframes:
            x,y,z,w=key.rotation
            if not is_root or settings.get('mirror_root_rotation',True):
                key.rotation=(x,-y,-z,w)
            tx,ty,tz=key.translation
            key.translation=(-tx,ty,tz)
            if is_root and settings.get('mirror_flip_root_180',True):
                axis=settings.get('mirror_flip_root_axis','X')
                turn=rt.Quat(180,rt.Point3(*(1 if axis==a else 0 for a in 'XYZ')))
                q=rt.Quat(*key.rotation)
                q=q*turn if settings.get('mirror_flip_root_space','GLOBAL')=='LOCAL' else turn*q
                key.rotation=(q.x,q.y,q.z,q.w)
    count,missing=apply_clip(clip,root,S.get_field(root,'ifp_start',0.0))
    return 'INFO','Mirrored animation on %d bones' % count


def smooth_between_anchors():
    import pymxs
    rt=S._rt()
    plans=[]
    mode=settings.get('smooth_axis_mode','ALL')
    for node in list(rt.selection):
        if S.node_kind(node)!='BONE':
            continue
        times=set()
        for controller in (rt.getPropertyController(node,rt.Name('position')),
                           rt.getPropertyController(node,rt.Name('rotation')),
                           rt.getPropertyController(node,rt.Name('scale'))):
            for track, count in keyed_controllers(controller):
                for i in range(1, count + 1):
                    if rt.isKeySelected(track, i):
                        times.add(float(rt.getKeyTime(track, i).frame))
        if len(times)<2:
            continue
        anchors=[]
        for time in sorted(times):
            with pymxs.attime(time):
                world=rt.copy(node.transform)
                local=world*rt.inverse(node.parent.transform) if node.parent is not None else world
                anchors.append((time,world,local))
        plans.append((node,anchors))
    if not plans:
        return 'WARNING','Select at least two anchor keys on selected bones in Track View'
    with S.undo_block('INU: Smooth Animation Anchors'):
        for node,anchors in plans:
            for left,right in zip(anchors,anchors[1:]):
                a,aw,al=left
                b,bw,bl=right
                for frame in range(math.ceil(a),math.floor(b)+1):
                    t=(frame-a)/(b-a)
                    t=t*t*(3-2*t)
                    with pymxs.animate(True),pymxs.attime(frame):
                        if mode=='ALL':
                            q=rt.slerp(al.rotationPart,bl.rotationPart,t)
                            local=rt.Matrix3(q)
                            scale=al.scalePart*(1-t)+bl.scalePart*t
                            local=rt.scaleMatrix(scale)*local
                            local.row4=al.row4*(1-t)+bl.row4*t
                            node.transform=local*node.parent.transform if node.parent is not None else local
                        else:
                            p=rt.copy(node.pos)
                            axis=mode[-1].lower()
                            setattr(p,axis,getattr(aw.row4,axis)*(1-t)+getattr(bw.row4,axis)*t)
                            node.pos=p
    rt.redrawViews()
    return 'INFO','Smoothed %d selected bone tracks' % len(plans)


def handsign_attach():
    rt=S._rt()
    ped,left,right=A.handsign_status()
    if ped is None or (left is None and right is None):
        raise ValueError('Load the ped skeleton and left/right gesture skeletons')
    bones={str(n.name).strip():n for n,_ in S.hierarchy(ped)[1]}
    count=0
    with S.undo_block('INU: Attach Gesture Hands'):
        for hand,side in ((left,'L'),(right,'R')):
            if hand is None or S.get_data(hand, 'handsign_parent', None):
                continue
            target=bones.get(side+' Hand')
            if target is None:
                raise ValueError('Ped is missing '+side+' Hand')
            tm=rt.copy(hand.transform)
            S.put_data([hand],'handsign_parent',dict(parent=int(rt.getHandleByAnim(hand.parent)) if hand.parent else 0,
                matrix=[float(v) for row in (tm.row1,tm.row2,tm.row3,tm.row4) for v in (row.x,row.y,row.z)],side=side))
            hand.parent=target
            hand.transform=tm
            count+=1
    return 'INFO','Attached %d gesture skeletons' % count


def handsign_detach():
    rt=S._rt()
    count=0
    with S.undo_block('INU: Detach Gesture Hands'):
        for node in list(rt.objects):
            data=S.get_data(node,'handsign_parent',None)
            if not data:
                continue
            node.parent=rt.maxOps.getNodeByHandle(data['parent']) if data['parent'] else None
            values=data['matrix']
            node.transform=rt.Matrix3(*[rt.Point3(*values[i:i+3]) for i in range(0,12,3)])
            S.put_data([node],'handsign_parent',None)
            count+=1
    return 'INFO','Detached %d gesture skeletons' % count


OPERATIONS.update({name:globals()[name] for name in ('bake_ik_rig','fix_quat_signs',
    'mirror_anim','smooth_between_anchors','handsign_attach','handsign_detach')})


def batch_ifp(folder):
    rt=S._rt()
    root=_rig()
    prefix=settings.get('batch_prefix','').lower()
    loaded=[]
    for filename in sorted(os.listdir(folder),key=str.lower):
        if not filename.lower().endswith('.ifp'):
            continue
        path=os.path.join(folder,filename)
        data=read_ifp(path)
        selected=[clip for clip in data.animations if clip.name.lower().startswith(prefix)]
        loaded.extend((clip, path, data.name, data.source_format) for clip in selected)
    start=int(settings.get('batch_start',0))
    count=int(settings.get('batch_count',0))
    clips=loaded[start:start+count] if count else loaded[start:]
    for path in dict.fromkeys(item[1] for item in clips):
        group = [item for item in clips if item[1] == path]
        A.library_add(path, group[0][2], group[0][3], [item[0].name for item in group])
    clips = [item[0] for item in clips]
    end=0
    if settings.get('batch_mode','NLA')=='NLA':
        with S.undo_block('INU: Sequential IFP Import'):
            for index, clip in enumerate(clips):
                apply_clip(clip,root,end,replace=index == 0)
                duration=max((key.time for bone in clip.bones for key in bone.keyframes),default=0)*A.frame_rate()
                end+=duration+float(settings.get('batch_gap',10))
            if clips:
                rt.animationRange=rt.Interval(0,end)
                S.put_field([root],'ifp_start',0.0)
                S.put_field([root],'ifp_end',float(end))
                S.put_field([root],'ifp_current','sequence')
    return 'INFO','Imported %d IFP clips%s' % (len(clips),' into a sequence' if end else ' into the library')


def export_gesture(path):
    from inu_gta_core.ifp import decimate_animation
    rt=S._rt()
    _ped,left,right=A.handsign_status()
    roots=[root for root in (left,right) if root is not None]
    roots.extend(node for node in rt.objects if S.get_data(node,'handsign_parent',None) and node not in roots)
    if not roots:
        raise ValueError('Load gesture hand skeletons first')
    name=settings.get('ifp_action','') or 'gesture'
    clip=Animation(name)
    for root in roots:
        clip.bones.extend(sample_animation(root,name).bones)
    if settings.get('hs_decimate',False):
        decimate_animation(clip,float(settings.get('hs_tol_rot',.001)),float(settings.get('hs_tol_trans',.001)))
    fd,tmp=tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)),suffix='.ifp')
    os.close(fd)
    try:
        if os.path.isfile(path):
            import shutil
            shutil.copy2(path,tmp)
            merge_ifp(tmp,[clip],format=settings.get('hs_format','ANP3'),target=settings.get('game','SA'))
        else:
            write_ifp(tmp,IFPFile('ghands',[clip]),format=settings.get('hs_format','ANP3'),target=settings.get('game','SA'))
        read_ifp(tmp)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return 'INFO','Exported gesture '+name


OPERATIONS.update(batch_ifp=batch_ifp,export_gesture=export_gesture)
