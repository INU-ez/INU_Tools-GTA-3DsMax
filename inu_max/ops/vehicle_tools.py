"""Vehicle edits. All mutations participate in the native Max undo stack."""
import math
import re

from ..adapter import selection as S


def mirror_name(name):
    """Swap a side token without touching unrelated substrings."""
    return re.sub(r'_(lf|rf|lb|rb|lm|rm)(?=_|$)',
                  lambda m: '_' + {'lf': 'rf', 'rf': 'lf', 'lb': 'rb',
                                   'rb': 'lb', 'lm': 'rm', 'rm': 'lm'}[m[1]],
                  name, count=1)


def _mesh_scale(rt, node, factor):
    # Scale the evaluated mesh, including UV/color channels; never modify an
    # instanced base object shared by another vehicle.
    mesh = rt.snapshotAsMesh(node)
    try:
        for i in range(1, int(rt.getNumVerts(mesh)) + 1):
            rt.setVert(mesh, i, rt.getVert(mesh, i) * factor)
        rt.convertToMesh(node)
        node.mesh = mesh
        rt.update(node)
    finally:
        rt.delete(mesh)


def vehicle_scale(factor=1.0, dummies_only=False):
    factor = float(factor)
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError('Scale must be finite and greater than zero')
    active = S.active_node()
    if active is None:
        return 'WARNING', 'Select a vehicle first'
    rt = S._rt()
    root, items = S.hierarchy(active)
    # Snapshot world positions before changing parents (children inherit moves).
    anchor = rt.copy(root.pos)
    positions = [(o, rt.copy(o.pos)) for o, _ in items]
    meshes = [o for o, _ in items if S.node_kind(o) == 'MESH']
    if not dummies_only and any(list(o.modifiers) for o in meshes):
        return 'ERROR', ('Scaling geometry would collapse the modifier stack. '
                         'Collapse it explicitly first, or use Dummies Only.')
    with S.undo_block('INU: Vehicle Scale'):
        if not dummies_only:
            for o in meshes:
                _mesh_scale(rt, o, factor)
        for o, pos in positions:
            o.pos = anchor + (pos - anchor) * factor
    rt.redrawViews()
    return 'INFO', 'Scaled %d vehicle frames by %g' % (len(items), factor)


def vehicle_add_damage_variant():
    source = S.active_node()
    if source is None or S.node_kind(source) != 'MESH':
        return 'WARNING', 'Select the original vehicle mesh'
    name = str(source.name)
    base = name[:-3] if name.endswith('_ok') else name
    if name.endswith('_dam'):
        return 'WARNING', 'Select an intact part, not its _dam variant'
    if S.find(base + '_dam') is not None:
        return 'WARNING', 'Damage variant already exists: ' + base + '_dam'
    rt = S._rt()
    with S.undo_block('INU: Create Damage Variant'):
        damaged = rt.copy(source)
        damaged.name = base + '_dam'
        damaged.parent = source.parent
        damaged.transform = rt.copy(source.transform)
        damaged.isHidden = True
        if not name.endswith('_ok'):
            source.name = base + '_ok'
    rt.redrawViews()
    return 'INFO', 'Created ' + base + '_dam'


def frame_mirror_lr():
    rt = S._rt()
    selected = list(rt.selection)
    if not selected:
        return 'WARNING', 'Select frames to mirror'
    _, hierarchy = S.hierarchy(selected[0])
    ranks = {int(rt.getHandleByAnim(o)): d for o, d in hierarchy}
    selected.sort(key=lambda o: ranks.get(int(rt.getHandleByAnim(o)), 0))
    plan = [(o, mirror_name(str(o.name))) for o in selected]
    plan = [(o, n) for o, n in plan if n != str(o.name) and S.find(n) is None]
    if any(S.node_kind(o) == 'MESH' and list(o.modifiers) for o, _ in plan):
        return 'ERROR', 'Collapse mesh modifiers before mirroring frames'
    reflection = rt.scaleMatrix(rt.Point3(-1, 1, 1))
    created = []
    with S.undo_block('INU: Mirror Frames'):
        for source, name in plan:
            clone = rt.copy(source)
            clone.name = name
            parent = source.parent
            twin_parent = S.find(mirror_name(str(parent.name))) if parent else None
            clone.parent = twin_parent if twin_parent is not None else parent
            local = rt.copy(source.transform)
            if parent is not None:
                local = local * rt.inverse(parent.transform)
            mirrored = reflection * local * reflection
            clone.transform = (mirrored * clone.parent.transform
                               if clone.parent is not None else mirrored)
            if S.node_kind(source) == 'MESH':
                mesh = rt.snapshotAsMesh(source)
                try:
                    for i in range(1, int(rt.getNumVerts(mesh)) + 1):
                        v = rt.getVert(mesh, i)
                        rt.setVert(mesh, i, rt.Point3(-v.x, v.y, v.z))
                    faces = rt.BitArray()
                    faces.count = int(rt.getNumFaces(mesh))
                    for i in range(1, faces.count + 1):
                        faces[i] = True
                    rt.meshop.flipNormals(mesh, faces)
                    rt.convertToMesh(clone)
                    clone.mesh = mesh
                    rt.update(clone)
                finally:
                    rt.delete(mesh)
            created.append(clone)
        if created:
            rt.select(rt.Array(*created))
    rt.redrawViews()
    return 'INFO', 'Created %d mirrored frames; existing twins preserved' % len(created)


OPERATIONS = {name: globals()[name] for name in (
    'vehicle_scale', 'vehicle_add_damage_variant', 'frame_mirror_lr')}
