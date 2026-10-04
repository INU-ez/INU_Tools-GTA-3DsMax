"""SA character IK controls, adapted from INU Blender's ops/ik_rig.py.

Controls are native Max Point boxes; saved controllers retain all references
without Python frame callbacks. Deform nodes keep their GTA identities.
"""
import json
import math
from pathlib import Path

from ..adapter import selection as S
from .. import settings

DATA = json.loads(Path(__file__).with_name('ik_rig_data.json').read_text(encoding='utf-8'))
SIZES = {'chain': .20, 'pole': .16, 'rot': .18, 'root': .30}
IDS = {'r upperarm': 22, 'r forearm': 23, 'r hand': 24,
       'l upperarm': 32, 'l forearm': 33, 'l hand': 34,
       'l thigh': 41, 'l calf': 42, 'l foot': 43,
       'r thigh': 51, 'r calf': 52, 'r foot': 53,
       'spine1': 3, 'head': 5, 'bip01 r clavicle': 21,
       'bip01 l clavicle': 31, 'pelvis': 1, 'root': 0}

_MXS = r'''
global inuIKQuatTM
fn inuIKQuatTM q = (q as matrix3)
global inuIKSetWorld
fn inuIKSetWorld node tm = (in coordsys world node.transform = tm)
global inuIKCopyRotation
fn inuIKCopyRotation deform control = (
    local rc = Orientation_Constraint()
    rc.relative = false
    rc.local_world = 0
    deform.rotation.controller = rc
    rc.constraints.appendTarget control 100.0
)
global inuIKCopyPosition
fn inuIKCopyPosition deform control = (
    local pc = Position_Constraint()
    pc.relative = false
    deform.position.controller = pc
    pc.constraints.appendTarget control 100.0
)
global inuIKFollowPosition
fn inuIKFollowPosition control deformParent localTrack = (
    local pc = Position_Script()
    pc.addNode "followParent" deformParent
    pc.addTarget "localPoint" localTrack
    pc.setExpression "if isValidNode followParent and localPoint != undefined then localPoint * followParent.transform else [0,0,0]"
    control.position.controller = pc
)
global inuIKFootFloor
fn inuIKFootFloor control ground gap = (
    local zTrack = control.position.controller.Z_Position.controller
    local lim
    if classof zTrack == float_limit then lim = zTrack else (
        lim = float_limit()
        lim.SetLimitedControl zTrack
        control.position.controller.Z_Position.controller = lim
    )
    lim.upper_limit_enabled = false
    lim.lower_limit_enabled = true
    local floorTrack = Float_Script()
    floorTrack.addNode "groundNode" ground
    floorTrack.addConstant "floorGap" gap
    floorTrack.setExpression "if isValidNode groundNode then groundNode.pos.z + floorGap else -1e30"
    setPropertyController lim #lower_limit floorTrack
    lim
)
'''


def _ensure():
    S._rt().execute(_MXS)


def _name(node):
    return ' '.join(str(node.name).lower().split())


def resolve(bones, candidates):
    names = {_name(n): n for n in bones}
    ids = {S.get_field(n, 'bone_id', -1): n for n in bones}
    for candidate in candidates:
        key = ' '.join(candidate.lower().split())
        node = ids.get(IDS.get(key, -999)) or names.get(key)
        if node is not None:
            return node
    return None


def specification(bones, root_motion=False):
    chains, rotations = [], []
    for label, names in DATA['_SA_CHAINS']:
        nodes = [resolve(bones, [name]) for name in names]
        if any(n is None for n in nodes):
            continue
        start, middle, end = nodes
        if middle.parent != start or end.parent != middle:
            raise ValueError(label + ': expected upper → middle → end hierarchy')
        chains.append((label, start, middle, end))
    for label, names in DATA['_SA_ROT_BONES']:
        node = resolve(bones, names)
        if node is not None:
            rotations.append((label, node))
    choices = DATA['_SA_ROOT_BONES' if root_motion else '_SA_PELVIS_BONES']
    root = resolve(bones, choices[0][1])
    if not chains:
        raise ValueError('No standard SA arm/leg chains in the selected skeleton')
    if root is None:
        raise ValueError('Root motion needs Root; stationary IK needs Pelvis')
    return chains, rotations, root


def pole_position(start, middle, end, fallback=(0., 1., 0.)):
    """Keep the pole in the current bend plane, independent of world axes."""
    axis = [end[k] - start[k] for k in range(3)]
    length2 = sum(v*v for v in axis)
    if length2 < 1e-12:
        raise ValueError('IK limb has coincident start and end joints')
    t = sum((middle[k]-start[k])*axis[k] for k in range(3))/length2
    bend = [middle[k]-start[k]-t*axis[k] for k in range(3)]
    norm = math.sqrt(sum(v*v for v in bend))
    if norm < 1e-6:
        t = sum(fallback[k]*axis[k] for k in range(3))/length2
        bend = [fallback[k]-t*axis[k] for k in range(3)]
        norm = math.sqrt(sum(v*v for v in bend))
        if norm < 1e-6:
            fallback = min(((1.,0.,0.), (0.,1.,0.), (0.,0.,1.)),
                           key=lambda v: abs(sum(v[k]*axis[k] for k in range(3))))
            return pole_position(start, middle, end, fallback)
    distance = math.sqrt(length2)*.5
    return tuple(middle[k]+bend[k]/norm*distance for k in range(3))


def _point(p):
    return (float(p.x), float(p.y), float(p.z))


def _handle(node):
    return int(node.handle)


def _belongs(node, field, root):
    owner = (_handle(root) if S.get_field(node,'ik_schema',0) >= 2
             else int(S._rt().getHandleByAnim(root)))
    return S.get_field(node,field,0) == owner


def controls(root=None):
    return [n for n in S._rt().helpers if S.get_field(n, 'ik_control', False)
            and (root is None or _belongs(n,'ik_control_root',root))]


def is_rigged(root):
    if S.get_field(root, 'ik_rigged', False):
        return True
    return any(_belongs(n,'ik_root',root) for n in S._rt().helpers)


def _box(root, label, kind, transform, created):
    rt = S._rt()
    box = rt.Point(name=rt.uniqueName('INU_IK_'+label), box=True, cross=False,
                   axistripod=False, centermarker=False, size=SIZES[kind])
    created.append(box)
    box.transform = rt.copy(transform)
    box.showLinks = False
    if rt.isProperty(box, rt.Name('drawOnTop')):
        box.drawOnTop = True
    for key, value in {'ik_control': True, 'ik_ctrl_type': kind,
                       'ik_control_root': _handle(root), 'preview': True,
                       'type': 'NON', 'ik_schema': 2}.items():
        S.put_field([box], key, value)
    return box


def update_display():
    rt = S._rt()
    color = settings.get('ik_color', [.2, 1., .2, 1.])
    multiplier = max(.01, float(settings.get('ik_size', 1.)))
    for box in controls():
        kind = S.get_field(box, 'ik_ctrl_type', 'chain')
        box.size = SIZES.get(kind, .08)*multiplier
        box.wirecolor = rt.Color(*(max(0., min(1., c))*255 for c in color[:3]))
        box.isHidden = not settings.get('ik_show_'+kind, True)
    rt.redrawViews()


def patch_floor():
    _ensure()
    rt = S._rt()
    ground = next((n for n in rt.objects if S.get_field(n, 'ik_ground', False)), None)
    if ground is None:
        return
    _ensure()
    for box in controls():
        if S.get_field(box, 'ik_foot', False):
            rt.inuIKFootFloor(box, ground, float(settings.get('floor_offset', .05)))


def _keyed_frames(bones):
    from .anim_tools import keyed_controllers
    rt = S._rt()
    return sorted({float(rt.getKeyTime(track, i).frame) for n in bones
                   for track, count in keyed_controllers(n.controller)
                   for i in range(1, count+1)})


def _canonical_pose(root, bones):
    """Preserve Max bind axes and orient the whole character upright."""
    import pymxs
    rt = S._rt()
    head = resolve(bones, ['Head'])
    pelvis = resolve(bones, ['Pelvis'])
    if head is None or pelvis is None:
        return
    up = rt.normalize(head.transform.row4-pelvis.transform.row4)
    vertical = rt.Point3(0,0,1)
    dot = max(-1., min(1., float(rt.dot(up,vertical))))
    if dot > .999999:
        return
    axis = rt.cross(up,vertical)
    if rt.length(axis)<1e-6:
        axis = rt.Point3(1,0,0)
    rotation = rt.inuIKQuatTM(rt.Quat(-math.degrees(math.acos(dot)),rt.normalize(axis)))
    with pymxs.animate(True), pymxs.attime(0):
        world = rt.copy(root.transform)
        position = rt.copy(world.row4)
        world *= rotation
        world.row4 = position
        rt.inuIKSetWorld(root,world)


def _samples(bones, frames):
    import pymxs
    rt = S._rt()
    return [(f, _sample_at(bones, f, pymxs, rt)) for f in frames]


def _sample_at(bones, frame, pymxs, rt):
    with pymxs.attime(frame):
        return {_handle(n): rt.copy(n.transform) for n in bones}


def _control_tm(transform, kind):
    rt = S._rt()
    tm = rt.inuIKQuatTM(transform.rotationPart)
    tm.row4 = rt.copy(transform.row4)
    if kind == 'chain':
        # Blender's DFF importer creates a 0.05-unit bone along local Y.
        # Its three-bone IK target sits at the hand/foot tail, not its head.
        tm.row4 = tm.row4 + tm.row2*.05
    return tm


def _key_controls(mapping, samples):
    import pymxs
    rt = S._rt()
    previous = {}
    for frame, poses in samples:
        with pymxs.animate(True), pymxs.attime(frame):
            for box, node, kind, limb in mapping:
                tm = _control_tm(poses[_handle(node)], kind)
                if kind == 'pole':
                    # Blender places the visible elbow/knee control AT the
                    # joint; the hidden VH offset supplies a stable IK plane.
                    box.pos = tm.row4
                else:
                    box.transform = tm
                    # Max quaternion tracks may choose the opposite hemisphere.
                    q = rt.copy(box.rotation)
                    key = _handle(box)
                    if key in previous and sum(getattr(q,k)*getattr(previous[key],k)
                                               for k in ('x','y','z','w')) < 0:
                        q = rt.Quat(-q.x, -q.y, -q.z, -q.w)
                        box.rotation = q
                    previous[key] = q


# Stored in each native transform controller, so reopened scenes do not need
# Python callbacks or global MAXScript functions to evaluate their limbs.
_LIMB_EXPRESSION = r"""
if not (isValidNode startAnchor and isValidNode goalBox and isValidNode poleTarget) then (matrix3 1) else (
local a = startAnchor.transform.row4
local target = goalBox.transform.row4 - goalBox.transform.row2 * 0.05
local delta = target-a
local d = length delta
local axis = if d>1e-7 then delta/d else normalize startAnchor.transform.row3
local bend = poleTarget.transform.row4-a
bend -= axis * (dot bend axis)
if length bend<1e-7 do (
    bend = [0,0,1]-axis*axis.z
    if length bend<1e-7 do bend = [0,1,0]-axis*axis.y
)
bend = normalize bend
local reach = amax (abs (upperLength-lowerLength)+1e-7) (amin (upperLength+lowerLength-1e-7) d)
local along = (reach*reach+upperLength*upperLength-lowerLength*lowerLength)/(2*reach)
local height = sqrt (amax 0 (upperLength*upperLength-along*along))
local elbow = a + axis*along + bend*height
local finish = a + axis*reach
local normal = normalize (cross axis bend)
local x = if jointIndex==0 then normalize (elbow-a) else normalize (finish-elbow)
local y = normalize (cross normal x)
local z = normalize (cross x y)
local position = if jointIndex==0 then a else (if jointIndex==1 then elbow else finish)
local world = matrix3 x y z position
world
)
"""


def _limb_controller(node, anchor, goal, pole, lengths, index):
    rt = S._rt()
    controller = rt.Transform_Script()
    for name,target in [('startAnchor',anchor),('goalBox',goal),('poleTarget',pole)]:
        controller.addNode(name,target)
    controller.addConstant('upperLength',float(lengths[0]))
    controller.addConstant('lowerLength',float(lengths[1]))
    controller.addConstant('jointIndex',index)
    controller.setExpression(_LIMB_EXPRESSION)
    node.controller = controller


def _reference_pole(limb, expected, forward=None):
    rt = S._rt()
    start,middle,end = [expected[_handle(n)].row4 for n in limb]
    if forward is None:
        return rt.Point3(*pole_position(_point(start),_point(middle),_point(end),
                                       _point(expected[_handle(limb[0])].row3)))
    axis = rt.normalize(end-start)
    direction = forward-axis*rt.dot(forward,axis)
    if rt.length(direction)<1e-6:
        return _reference_pole(limb,expected)
    return middle+rt.normalize(direction)*rt.distance(start,end)*.5



def add(root, bones):
    rt = S._rt()
    chains, rotations, root_node = specification(bones, settings.get('ik_root_motion', False))
    import pymxs
    if S.get_field(root, 'ik_rigged', False):
        return 'INFO', 'This skeleton already has an INU IK rig'
    if any(_belongs(n,'ik_root',root) for n in rt.helpers):
        raise ValueError('This is a legacy four-chain rig. Use Bake & Clear IK, then Add IK Rig to create the full rig.')
    frames = _keyed_frames(bones)
    fresh = not frames
    start = float(rt.animationRange.start.frame)
    end = float(rt.animationRange.end.frame)
    if end-start > 10000:
        raise ValueError('Transfer at most 10000 animation frames per run')
    created, backups, mapping, solvers = [], [], [], []
    _ensure()
    with S.undo_block('INU: Full IK Rig'):
        try:
            for orphan in list(rt.helpers):
                if _belongs(orphan,'ik_backup_root',root):
                    rt.delete(orphan)
            # Snapshot every original controller before any posing or constraint.
            snapshot_nodes = list(bones)
            if root not in snapshot_nodes:
                snapshot_nodes.insert(0, root)
            for n in snapshot_nodes:
                backup = rt.Point(name=rt.uniqueName('INU_FK_Backup'), size=.01)
                created.append(backup)
                backup.controller = rt.copy(n.controller)
                backups.append((n, backup))
                backup.isHidden = True
                for key, value in {'ik_restore_node': _handle(n), 'ik_backup_root': _handle(root),
                                   'preview': True, 'type': 'NON', 'ik_schema': 2}.items():
                    S.put_field([backup], key, value)
            if not frames:
                _canonical_pose(root, bones)
                frames = [0.]
            else:
                # Sample every frame, not just key times: IK interpolation differs
                # from FK interpolation between keys.
                frames = sorted(set(frames) | set(range(int(math.floor(start)), int(math.ceil(end))+1)))
            samples = _samples(bones, frames)
            current = _sample_at(bones, float(rt.sliderTime.frame), pymxs, rt)
            for label, upper, middle, tip in chains:
                goal = _box(root, label, 'chain', _control_tm(current[_handle(tip)], 'chain'), created)
                pole = _box(root, label+'_pole', 'pole', current[_handle(middle)], created)
                limb = (upper, middle, tip)
                mapping += [(goal, tip, 'chain', limb), (pole, middle, 'pole', limb)]
                if label.endswith('_leg'):
                    S.put_field([goal], 'ik_foot', True)
            for label, bone in rotations:
                box = _box(root, label, 'rot', current[_handle(bone)], created)
                mapping.append((box, bone, 'rot', None))
            master = _box(root, 'root', 'root', current[_handle(root_node)], created)
            mapping.append((master, root_node, 'root', None))
            _key_controls(mapping, samples)
            forward = None
            if fresh:
                by_id = {S.get_field(n,'bone_id',-1):n for n in bones}
                if all(i in by_id for i in (43,44,53,54)):
                    direction = sum((current[_handle(by_id[toe])].row4-current[_handle(by_id[foot])].row4
                                    for foot,toe in ((43,44),(53,54))),rt.Point3(0,0,0))
                    if rt.length(direction)>1e-6:
                        forward = rt.normalize(direction)
            driver_chains = []
            for goal, tip, kind, limb in mapping:
                if kind != 'chain':
                    continue
                upper, middle, tip = limb
                pole = next(box for box, n, t, l in mapping if t == 'pole' and l == limb)
                # An unscaled anchor prevents GTA frame scales/shear from
                # changing the native solver's segment lengths.
                anchor = rt.Point(name=rt.uniqueName('INU_IK_Anchor'),size=.001)
                created.append(anchor)
                anchor.pos = current[_handle(upper)].row4
                if upper.parent is not None:
                    saved = next(backup for original,backup in backups if original==upper)
                    local_track = rt.getPropertyController(saved.controller,rt.Name('position'))
                    rt.inuIKFollowPosition(anchor,upper.parent,local_track)
                    rt.inuIKCopyRotation(anchor,upper.parent)
                anchor.isHidden = True
                for key,value in {'ik_aux_root':_handle(root),'preview':True,'type':'NON','ik_schema':2}.items():
                    S.put_field([anchor],key,value)
                vh = rt.Point(name=rt.uniqueName('INU_IK_PoleOffset'),size=.001)
                created.append(vh)
                vh.parent = pole
                desired_forward = forward if S.get_field(goal,'ik_foot',False) else (-forward if forward is not None else None)
                vh.pos = _reference_pole(limb,current,desired_forward)
                vh.isHidden = True
                for key,value in {'ik_aux_root':_handle(root),'preview':True,'type':'NON','ik_schema':2}.items():
                    S.put_field([vh],key,value)
                lengths = (rt.distance(current[_handle(upper)].row4,current[_handle(middle)].row4),
                           rt.distance(current[_handle(middle)].row4,current[_handle(tip)].row4))
                if min(lengths)<1e-6:
                    raise ValueError('IK limb has zero-length segments: '+str(upper.name))
                drivers = []
                for i in range(3):
                    driver = rt.Point(name=rt.uniqueName('INU_IK_Driver'),size=.001)
                    created.append(driver)
                    driver.isHidden = True
                    _limb_controller(driver,anchor,goal,vh,lengths,i)
                    fields = {'ik_aux_root':_handle(root),'preview':True,'type':'NON','ik_schema':2}
                    if i==2:
                        fields.pop('ik_aux_root')
                        fields.update(ik_root=_handle(root),ik_goal_node=_handle(goal),
                                      ik_start_node=_handle(drivers[0]),ik_vh_node=_handle(vh))
                        driver.name = rt.uniqueName('INU_IK_Solver')
                        solvers.append(driver)
                    for key,value in fields.items():
                        S.put_field([driver],key,value)
                    drivers.append(driver)
                offsets = []
                for bone,driver in zip((upper,middle),drivers):
                    offset = rt.Point(name=rt.uniqueName('INU_IK_DeformOffset'),size=.001)
                    created.append(offset)
                    offset.parent = driver
                    offset.transform = rt.copy(current[_handle(bone)])
                    offset.isHidden = True
                    for key,value in {'ik_aux_root':_handle(root),'preview':True,'type':'NON','ik_schema':2}.items():
                        S.put_field([offset],key,value)
                    offsets.append(offset)
                    rt.inuIKCopyRotation(bone,offset)
                    rt.inuIKCopyPosition(bone,driver)
                driver_chains.append((limb,drivers,offsets,vh,desired_forward))
                rt.inuIKCopyRotation(tip,goal)
                rt.inuIKCopyPosition(tip,drivers[2])
            for box, bone, kind, limb in mapping:
                if kind == 'rot':
                    backup = next(saved for original, saved in backups if original == bone)
                    local_track = rt.getPropertyController(backup.controller, rt.Name('position'))
                    rt.inuIKCopyRotation(bone, box)
                    if bone.parent is not None:
                        rt.inuIKFollowPosition(box, bone.parent, local_track)
                elif kind == 'root':
                    rt.inuIKCopyRotation(bone, box)
                    rt.inuIKCopyPosition(bone, box)
            for frame, expected in samples:
                with pymxs.attime(frame), pymxs.animate(True):
                    for limb,drivers,offsets,vh,direction in driver_chains:
                        vh.pos = _reference_pole(limb,expected,direction)
                        # Animated offsets retain arbitrary GTA bind axes and roll.
                        for bone,offset in zip(limb,offsets):
                            offset.transform = rt.copy(expected[_handle(bone)])
            S.put_field([root], 'ik_rigged', True)
            S.put_field([root], 'ik_schema', 2)
            update_display()
            patch_floor()
        except Exception:
            for solver in solvers:
                if rt.isValidNode(solver):
                    rt.delete(solver)
            for bone, backup in backups:
                bone.controller = rt.copy(backup.controller)
            for node in reversed(created):
                if rt.isValidNode(node):
                    rt.delete(node)
            S.put_field([root], 'ik_rigged', False)
            raise
    rt.select(master)
    rt.redrawViews()
    return 'INFO', 'IK rig: %d chains + %d poles + %d rotation controls + 1 root; %d FK samples' % (len(chains), len(chains), len(rotations), len(samples))


def bake(root, bones):
    _ensure()
    import pymxs
    rt = S._rt()
    handle = _handle(root)
    boxes = controls(root)
    solvers = [n for n in rt.helpers if _belongs(n,'ik_root',root)]
    backups = [n for n in rt.helpers if _belongs(n,'ik_backup_root',root)]
    auxiliary = [n for n in rt.helpers if _belongs(n,'ik_aux_root',root)]
    if not boxes and not solvers:
        return 'WARNING', 'No INU IK rig on this skeleton'
    start, end = int(rt.animationRange.start.frame), int(rt.animationRange.end.frame)
    if end-start > 10000:
        raise ValueError('Bake at most 10000 frames per run')
    frames = list(range(start, end+1))
    samples = _samples(bones, frames)
    with S.undo_block('INU: Bake and Clear IK'):
        for backup in backups:
            restore = S.get_field(backup,'ik_restore_node',0)
            bone = (S.node_by_handle(restore) if S.get_field(backup,'ik_schema',0)>=2
                    else rt.getAnimByHandle(restore))
            if bone is not None:
                bone.controller = rt.copy(backup.controller)
        for solver in solvers:
            rt.delete(solver)
        for node in auxiliary:
            rt.delete(node)
        for box in boxes:
            rt.delete(box)
        for backup in backups:
            rt.delete(backup)
        for frame, poses in samples:
            with pymxs.animate(True), pymxs.attime(frame):
                for bone in bones:  # hierarchy order is parent before child
                    rt.inuIKSetWorld(bone, poses[_handle(bone)])
        removed_keys = _simplify_static_tracks(bones)
        S.put_field([root], 'ik_rigged', False)
    rt.select(root)
    rt.redrawViews()
    return 'INFO', 'Baked %d frames; removed %d boxes, %d IK solvers and %d redundant keys' % (len(frames), len(boxes), len(solvers), removed_keys)


def _simplify_static_tracks(bones):
    """Collapse static scalar channels without changing animated tangents."""
    from .anim_tools import keyed_controllers
    rt = S._rt()
    removed = 0
    for bone in bones:
        for track, count in keyed_controllers(bone.controller):
            if count < 2:
                continue
            if rt.superClassOf(track) != rt.FloatController:
                continue
            try:
                values = [float(rt.getKey(track,i).value) for i in range(1,count+1)]
            except (TypeError, ValueError, ArithmeticError, RuntimeError):
                continue
            if max(values)-min(values) <= 1e-6:
                for i in range(count,1,-1):
                    rt.deleteKey(track,i)
                    removed += 1
    return removed



