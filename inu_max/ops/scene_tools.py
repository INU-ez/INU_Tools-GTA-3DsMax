"""Scene inspection and edits used by the Check window."""
from ..adapter import selection as S
from .. import settings


def batch_set_type(kind):
    nodes = list(S._rt().selection)
    with S.undo_block('INU: Object Type'):
        S.put_field(nodes, 'type', kind)
    return 'INFO', 'Assigned %s to %d objects' % (kind, len(nodes))


def reset_transform():
    rt = S._rt()
    nodes = S.selected_meshes()
    with S.undo_block('INU: Reset Transform'):
        for node in nodes:
            node.pos = rt.Point3(0, 0, 0)
            node.rotation = rt.Quat(0, 0, 0, 1)
    rt.redrawViews()
    return 'INFO', 'Reset position and rotation of %d meshes' % len(nodes)


def toggle_visibility():
    rt = S._rt()
    count = 0
    with S.undo_block('INU: Model Visibility'):
        for node in list(rt.geometry):
            if S.get_field(node, 'preview', False) or S.get_field(node, 'section', ''):
                continue
            explicit = S.get_field(node, 'type', '')
            if explicit == 'NON':
                continue
            kind = 'SHA' if explicit == 'SHA' else S.classify(node)[0]
            node.isHidden = bool(settings.get('hide_' + kind.lower(), False))
            count += 1
    rt.redrawViews()
    return 'INFO', 'Updated visibility of %d models' % count


def inspect_mesh(node, ngons=False):
    """Inspect a snapshot; preserve the original stack and subobject selection."""
    rt = S._rt()
    if ngons:
        poly = rt.copy(node)
        try:
            rt.convertToPoly(poly)
            faces = [i for i in range(1, int(rt.polyop.getNumFaces(poly)) + 1)
                     if int(rt.polyop.getFaceDeg(poly, i)) > 4]
            return '%s: %d N-gons' % (node.name, len(faces)), bool(faces)
        finally:
            rt.delete(poly)
    mesh = rt.snapshotAsMesh(node)
    try:
        used = set()
        for i in range(1, int(rt.getNumFaces(mesh)) + 1):
            f = rt.getFace(mesh, i)
            used.update((int(f.x), int(f.y), int(f.z)))
        loose = int(rt.getNumVerts(mesh)) - len(used)
        return '%s: %d loose vertices' % (node.name, loose), bool(loose)
    finally:
        rt.delete(mesh)


def check_geometry(ngons=False):
    rt = S._rt()
    nodes = S.selected_meshes()
    if not nodes:
        return 'WARNING', 'Select meshes to inspect'
    reports, bad = [], []
    with S.undo_block('INU: Inspect Geometry'):
        for node in nodes:
            text, problem = inspect_mesh(node, ngons)
            reports.append(text)
            if problem:
                bad.append(node)
        if bad:
            rt.select(rt.Array(*bad))
    return ('WARNING' if bad else 'INFO'), '\n'.join(reports)


def snap_to_dff():
    from .map_link import Scene, LodIndex
    rt = S._rt()
    scene = Scene()
    dffs = [r for r in scene.recs if scene.model_type(r)[0] == 'DFF']
    lods = LodIndex(scene)
    selected = {int(rt.getHandleByAnim(o)) for o in rt.selection}
    moves = []
    for r in scene.recs:
        kind, base = scene.model_type(r)
        if r.handle not in selected or kind not in ('LOD', 'COL'):
            continue
        candidates = [d for d in dffs if scene.model_type(d)[1] == base]
        if kind == 'LOD':
            candidates = [d for d in dffs if lods.partner(d) is r] or candidates
        if not candidates:
            continue
        owner = min(candidates, key=lambda d: rt.distance(d.node.pos, r.node.pos))
        moves.append((r.node, rt.copy(owner.node.pos)))
    with S.undo_block('INU: Snap LOD/COL'):
        for node, pos in moves:
            node.pos = pos
    rt.redrawViews()
    return 'INFO', 'Aligned %d LOD/COL objects to their DFF' % len(moves)


OPERATIONS = {
    'reset_transform': reset_transform,
    'toggle_visibility': toggle_visibility,
    'check_geometry': check_geometry,
    'check_ngons': lambda: check_geometry(ngons=True),
    'snap_to_dff': snap_to_dff,
}
for _kind in ('OBJ', 'COL', 'SHA', 'NON'):
    OPERATIONS['batch_set_type_' + _kind.lower()] = lambda kind=_kind: batch_set_type(kind)


def validate_scene():
    from inu_gta_core import validate as V
    from ..adapter import material as M, fx as F
    rt = S._rt()
    objects = [node for node in rt.geometry if S.node_kind(node) == 'MESH'
               and not S.get_field(node, 'section', '') and not S.get_field(node, 'preview', False)
               and S.get_field(node, 'type', '') != 'NON' and rt.classOf(node) != rt.TargetObject]
    models, meshes, scales, ids = [], [], [], []
    for node in objects:
        kind, base = S.classify(node)
        models.append(dict(name=str(node.name), type=kind, base=base,
                           heuristic_col=kind == 'COL' and S.get_field(node, 'type', '') != 'COL'))
        scale = node.scale
        scales.append(dict(name=str(node.name), scale=(scale.x, scale.y, scale.z)))
        ids.append(dict(name=base, model_id=S.get_field(node, 'model_id', 0)))
        mesh = rt.snapshotAsMesh(node)
        try:
            used = set()
            for i in range(1, int(rt.getNumFaces(mesh)) + 1):
                f = rt.getFace(mesh, i)
                used.update((int(f.x), int(f.y), int(f.z)))
            count = int(rt.getNumVerts(mesh))
            meshes.append(dict(name=str(node.name), vert_count=count,
                loose_verts=count - len(used), loose_edges=0,
                has_uv_anim=any(M.props(m).get('uv_anim_write') for m in M.node_materials([node])),
                night_flag=S.get_flags(node)['night_cols'], has_night_vcol=bool(rt.meshop.getMapSupport(mesh, -1))))
        finally:
            rt.delete(mesh)
    materials = []
    for material in M.node_materials(objects):
        props = M.props(material)
        materials.append(dict(name=str(material.name), alt1=bool(props['paintjob_alt_1']),
            alt2=bool(props['paintjob_alt_2']), has_base=M.base_diffuse(material) is not None,
            has_image=M.base_diffuse(material) is not None, user_count=1, is_collision=False))
    issues = (V.check_empty_meshes(meshes) + V.check_large_meshes(meshes) + V.check_loose_geom(meshes)
              + V.check_orphan_models(models) + V.check_untextured_col(models)
              + V.check_duplicate_model_ids(ids) + V.check_object_scale(scales)
              + V.check_non_ascii_names([str(node.name) for node in objects])
              + V.check_paintjobs(materials) + V.check_materials_without_texture(materials)
              + V.check_damage_pairs([str(node.name) for node in objects])
              + V.check_orphan_2dfx([dict(name=str(n.name), parent_kind=S.node_kind(n.parent) if n.parent else None)
                                    for n in rt.helpers if F.is_2dfx(n)]))
    if settings.get('game', 'SA') == 'SA':
        issues += V.check_uv_anim_night_vcols(meshes)
    return issues


def validate_goto(target_name='', target_kind='OBJECT'):
    rt = S._rt()
    if target_kind == 'MATERIAL':
        from ..adapter import material as M
        mats = [m for m in M.scene_materials() if str(m.name) == target_name]
        return 'INFO', 'Selected %d material users' % M.select_users(mats)
    node = S.find(target_name)
    if node is None:
        return 'WARNING', 'Object no longer exists: ' + target_name
    rt.select(node)
    return 'INFO', 'Selected ' + target_name


OPERATIONS['validate_goto'] = validate_goto


def _refresh_links():
    from .map_link import Scene, LodIndex
    rt=S._rt()
    scene=Scene()
    lods=LodIndex(scene)
    desired=[]
    for record in scene.recs:
        if scene.model_type(record)[0]!='DFF':
            continue
        lod=lods.partner(record)
        if lod is not None:
            desired.append((record.node,lod.node))
        base=scene.model_type(record)[1]
        desired.extend((record.node,c.node) for c in scene.recs
                       if scene.model_type(c)==('COL',base))
    old={S.get_field(n,'link_pair',''):n for n in rt.shapes
         if S.get_field(n,'preview_kind','')=='model_link'}
    for a,b in desired:
        key='%d:%d'%(int(rt.getHandleByAnim(a)),int(rt.getHandleByAnim(b)))
        line=old.pop(key,None)
        if line is None:
            line=rt.SplineShape(name=rt.uniqueName('INU_ModelLink'))
            rt.addNewSpline(line)
            for point in (a.pos,b.pos):
                rt.addKnot(line,1,rt.Name('corner'),rt.Name('line'),point)
            S.put_field([line],'preview_kind','model_link')
            S.put_field([line],'link_pair',key)
            S.put_field([line],'preview',True)
            S.put_field([line],'type','NON')
        else:
            rt.setKnotPoint(line,1,1,a.pos)
            rt.setKnotPoint(line,1,2,b.pos)
        rt.updateShape(line)
    for line in old.values():
        rt.delete(line)
    rt.redrawViews()


def toggle_links():
    from .. import sessions
    rt=S._rt()
    if settings.get('links_active',False):
        sessions.start('model_links',_refresh_links)
        _refresh_links()
        return 'INFO','Model links shown'
    sessions.stop('model_links')
    for node in list(rt.shapes):
        if S.get_field(node,'preview_kind','')=='model_link':
            rt.delete(node)
    rt.redrawViews()
    return 'INFO','Model links hidden'


OPERATIONS['toggle_links']=toggle_links


def batch_set_distance(values):
    from .map_link import Scene
    rt=S._rt()
    scene=Scene()
    selected={int(rt.getHandleByAnim(n)) for n in rt.selection}
    records=[r for r in scene.recs if r.handle in selected]
    records.sort(key=lambda r: {'DFF': 0, 'LOD': 1, 'COL': 2}.get(scene.model_type(r)[0], 3))
    next_id=int(values.get('model_id',0))
    ids={}
    with S.undo_block('INU: Batch IDE Properties'):
        for record in records:
            kind,base=scene.model_type(record)
            assigned=dict(values)
            if 'model_id' in assigned:
                key=(kind,base.lower())
                if kind=='COL':
                    key=('DFF',base.lower())
                if key not in ids:
                    ids[key]=next_id
                    if next_id:
                        next_id+=1
                assigned['model_id']=ids[key]
            for key,value in assigned.items():
                if kind=='COL' and key not in ('model_id','col_library'):
                    continue
                S.put_field([record.node],key,value)
    return 'INFO','Updated IDE properties on %d selected objects'%len(records)


OPERATIONS['batch_set_distance']=batch_set_distance
