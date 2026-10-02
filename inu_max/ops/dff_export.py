# INU Tools (Max) — экспорт моделей из окна экспорта DFF IO (порт
# run_group_export / run_single_dff_export Blender-версии INU).
#
# «Группы»: выделенные меши группируются по базовому имени (DFF / LOD / COL,
# общий классификатор ядра) → <имя>.dff, LOD<имя>.dff; 2DFX-хелперы — дети
# меша. «Один DFF»: вся иерархия от корня крупнейшего выделенного меша (кузов
# машины / пед) → один .dff. Сборка клапма — ops/dff_build.py, чтение сцены —
# adapter/scene_read.py, запись — ядро.

import os

from .. import settings


def _sr():
    from ..adapter import scene_read
    return scene_read


def _sel():
    from ..adapter import selection
    return selection


def _version(game):
    from inu_gta_core import game_versions
    return game_versions.rw_version_for_game(game or 'SA')


# ── узлы сцены → ExportNode ──────────────────────────────────────────

def _node(o, parent_obj, parent_idx, pipeline, skins=None, skin_bones=None):
    """ExportNode из узла Max (меш или дамми). skins — {узел: веса Skin},
    skin_bones — {имя кости (нижний регистр): ID} для костей без inu_bone_id."""
    from .dff_build import ExportNode, ExportError, export_flags
    sr = _sr()
    kind = sr.frame_kind(o) or 'DUMMY'
    tm = sr.local_tm(o, parent_obj)
    if parent_obj is None:
        # корень модели — в 0,0,0 (как INU): положение объекта в сцене в DFF
        # не пишется, размещение — дело IPL; поворот сохраняется
        tm = (tm[0], tm[1], tm[2], (0.0, 0.0, 0.0))
    n = ExportNode(name=str(o.name), kind=kind, parent=parent_idx, transform=tm)
    order = _sel().get_prop(o, 'atomic_order', -1)
    if order >= 0:
        n.order = order
    bone = _sel().get_prop(o, 'bone_id', -1)
    if bone < 0 and skin_bones:
        bone = skin_bones.get(n.name.strip().lower(), -1)
    if bone >= 0:
        n.bone_id = bone
        n.rig_root = bool(_sel().get_prop(o, 'animobj_empty_root', False))
    if kind == 'MESH':
        n.mesh = sr.mesh_data(o)
        n.materials = sr.materials_and_ids(o, n.mesh)
        n.flags = export_flags(sr.flags(o), pipeline)
        skin = (skins or {}).get(o)
        if skin:
            if len(skin) != len(n.mesh.verts):
                raise ExportError("'%s': a modifier above Skin changes the vertex "
                                  "count (%d → %d) — collapse or disable it"
                                  % (n.name, len(skin), len(n.mesh.verts)))
            n.mesh.skin = skin
    return n


def _fx_entries(helpers, mesh_obj):
    """2DFX-хелперы → записи ядра в системе меша mesh_obj."""
    from .dff_build import fx_entry
    from ..adapter import fx as fx_ad
    sr = _sr()
    out = []
    for h in helpers:
        eff = fx_ad.effect_of(h)
        vals = fx_ad.fields(h)
        vals['2dfx_look_direction'] = fx_ad.get(h, '2dfx_look_direction', (0.0, 0.0, 0.0))
        loc = sr.point_in(sr.world_pos(h), None, mesh_obj)
        esc = None
        if eff == 'ESCALATOR':
            esc = [sr.point_in(vals[k], h, mesh_obj)
                   for k in ('esc_bottom', 'esc_top', 'esc_end')]
        e = fx_entry(eff, vals, loc, esc)
        if e is not None:
            out.append(e)
    return out


def _hierarchy(root):
    """[(узел, родитель-узел-во-фреймах)] обходом в глубину: родитель раньше
    детей; не-фреймы (2DFX, коллизия, свет…) пропускаются, их дети
    поднимаются к ближайшему фрейму-предку."""
    sr = _sr()
    out = []

    def walk(o, frame_parent):
        is_frame = sr.frame_kind(o) is not None
        if is_frame:
            out.append((o, frame_parent))
        for c in list(o.children):
            walk(c, o if is_frame else frame_parent)
    walk(root, None)
    return out


def _nodes_for(objs_with_parents, pipeline):
    from .dff_build import SA_PED_BONE_IDS
    sr = _sr()
    # веса Skin читаются заранее: кости без inu_bone_id получают ID
    # скелета педа SA по имени, иначе свободный
    skins = {}
    for o, _p in objs_with_parents:
        if sr.frame_kind(o) == 'MESH':
            s = sr.skin_data(o)
            if s:
                skins[o] = s
    skin_bones = {}
    if skins:
        # все кости скелета педа (и невзвешенный Root — ID 0, его двигает
        # анимация) + прочие взвешенные кости
        skin_bones = dict(SA_PED_BONE_IDS)
        names = {b.strip().lower() for s in skins.values() for vw in s for b, _w in vw}
        free = 1000
        for nm in sorted(names - set(skin_bones)):
            skin_bones[nm] = free
            free += 1
    idx = {}
    nodes = []
    for o, p in objs_with_parents:
        nodes.append(_node(o, p, idx[p] if p is not None else -1, pipeline,
                           skins, skin_bones))
        idx[o] = len(nodes) - 1
    return nodes


# ── коллизия ─────────────────────────────────────────────────────────

def _col_version(game):
    from inu_gta_core import game_versions
    return game_versions.profile_for(game or 'SA').col_version


def _prim_in(o, ref, version=1):
    """ColPrim примитива в системе узла ref (модель карты стоит в мире со
    своим поворотом, а в COL сферы / боксы — в системе модели): центр сферы
    — через обратную матрицу ref без масштаба, бокс — в той же системе."""
    from ..adapter.selection import _rt
    rt = _rt()
    p = _sr().col_prim_data(o, version=version)
    # COL mesh coordinates already include scale; the reference must be rigid.
    frame = rt.matrix3(ref.transform.rotationpart)
    frame.row4 = ref.transform.translationpart
    if p.kind == 'BOX':
        mn, mx = rt.nodeGetBoundingBox(o, frame)
        p.bb_min = (float(mn.x), float(mn.y), float(mn.z))
        p.bb_max = (float(mx.x), float(mx.y), float(mx.z))
    else:
        c = o.pos * rt.inverse(frame)
        p.center = (float(c.x), float(c.y), float(c.z))
    return p


def _col_model(name, version, meshes, prims, opts, warnings, empty=False,
               bounds_objs=(), origin=(0.0, 0.0, 0.0), ref_node=None):
    """ColModel из узлов Max (+ аудит при «Audit models on export»).
    origin — мировая позиция корня модели: сферы и боксы берутся в мире,
    а в COL нужны относительно модели (корень пишется в 0,0,0). ref_node —
    узел модели: примитивы пересчитываются в его систему целиком (с
    поворотом; для моделей карты, Export to IMG)."""
    from .col_build import build_model
    sr = _sr()
    pr = []
    for o in prims:
        if ref_node is not None:
            pr.append(_prim_in(o, ref_node, version))
            continue
        p = sr.col_prim_data(o, version=version)
        p.center = tuple(p.center[i] - origin[i] for i in range(3))
        p.bb_min = tuple(p.bb_min[i] - origin[i] for i in range(3))
        p.bb_max = tuple(p.bb_max[i] - origin[i] for i in range(3))
        pr.append(p)
    model, dropped = build_model(
        name, version, [sr.col_mesh(o) for o in meshes], pr,
        opts['auto_light'], empty, [sr.col_mesh(o) for o in bounds_objs])
    if not empty:
        # границы исходного COL, если коллизия импортирована (как _stored_bounds
        # INU): у машин R* строит их по сферам — от них дальность камеры и длина
        # тени; пересчёт по мешу их раздувает
        saved = next((b for b in (sr.col_bounds(o) for o in list(meshes) + list(prims)) if b),
                     None)
        if saved:
            from inu_gta_core.col import Bounds, Vec3
            model.bounds = Bounds(center=Vec3(*saved[1:4]), radius=float(saved[0]),
                                  bb_min=Vec3(*saved[4:7]), bb_max=Vec3(*saved[7:10]))
    if dropped:
        warnings.append("%s.col: degenerate faces dropped: %d" % (name, dropped))
    if opts['audit']:
        from inu_gta_core.col_lint import check_col_models
        fatal, warn = check_col_models([model])
        warnings += ["%s.col: GAME WILL CRASH — %s" % (name, x) for x in fatal]
        warnings += ["%s.col: %s" % (name, x) for x in warn]
    return model


def _collision_objects(meshes_sel, picked):
    """Коллизия машины / педа для «Одного DFF» (как run_single_dff_export
    INU): COL/SHA-меши верхнего уровня или выделенные, и примитивы
    «<модель>_sphere_N / _box_N», чьё имя начинается с имени COL-меша."""
    import re
    from ..adapter.selection import _rt
    sr = _sr()
    rt = _rt()
    picked_set = list(picked)
    cols = [o for o in rt.geometry if sr.is_col(o)
            and (o.parent is None or o in meshes_sel)]
    names = [str(o.name) for o in cols]
    prims = []
    for o in rt.geometry:
        if not sr.col_prim(o) or not (o.parent is None or o in picked_set):
            continue
        base = re.sub(r'_(sphere|box)_\d+$', '', str(o.name), flags=re.I)
        if not names or any(n.lower().startswith(base.lower()) for n in names):
            prims.append(o)
    return cols, prims


# ── запись одного DFF ────────────────────────────────────────────────

def _merge_note(warnings, head, names):
    if not names:
        return
    for i, message in enumerate(warnings):
        if message.startswith(head):
            names = message[len(head):].split(', ') + list(names)
            warnings[i] = head + ', '.join(dict.fromkeys(names))
            return
    warnings.append(head + ', '.join(dict.fromkeys(names)))


def _uv_anim_notes(warnings, materials, version):
    from .dff_build import uv_anim_materials, keyframe_uv_materials
    if version < 0x35000:
        _merge_note(warnings, 'UV animation is not written — GTA III/VC have no UV animation; materials: ',
                    uv_anim_materials(materials))
    else:
        _merge_note(warnings, 'UV Keyframes: no sampled keys; materials: ',
                    keyframe_uv_materials(materials))

def dff_bytes(name, nodes, fx, opts, warnings, collision=b''):
    """Байты .dff (клапм + аудит); name — имя модели для сообщений."""
    from inu_gta_core.dff import DFF_EXPORT_WARNINGS
    from .dff_build import build_clump
    nodes = list(nodes)
    _uv_anim_notes(warnings, [m for n in nodes for m in n.materials], opts['version'])
    clump = build_clump(nodes, version=opts['version'],
                        write_valpha=opts['vertex_alpha'], fx=fx,
                        collision=collision)
    if opts['platform'] == 'MOBILE':
        for g in clump.geometries:
            g.is_native_ogl = True
        clump.is_mobile = True
    if opts['audit']:
        warnings += ["%s: %s" % (name, w) for w in audit(clump, name)]
    data = clump.to_bytes()
    warnings += ["%s: %s" % (name, w) for w in DFF_EXPORT_WARNINGS]
    return data


def _write(path, nodes, fx, opts, warnings, collision=b''):
    name = os.path.splitext(os.path.basename(path))[0]
    data = dff_bytes(name, nodes, fx, opts, warnings, collision)
    with open(path, 'wb') as f:
        f.write(data)


def audit(clump, model_name):
    """Проверка на краши/баги в игре (как export_dff INU при «Audit models
    on export»): имена дамми машины, скин, объект карты."""
    out = []
    names = [f.name for f in clump.frames if f.name]
    if any('wheel' in n.lower() for n in names):
        from .frames import check_vehicle_names
        fatal, warn = check_vehicle_names(names)
        out += ["GAME WILL CRASH — missing dummy: %s" % x for x in fatal]
        out += ["vehicle dummy: %s" % x for x in warn]
    if any(g.skin is not None for g in clump.geometries):
        from inu_gta_core.skin_lint import check_skin_clump
        fatal, warn = check_skin_clump(clump)
        out += ["GAME WILL CRASH — skin: %s" % x for x in fatal]
        out += ["skin: %s" % x for x in warn]
    else:
        from inu_gta_core.mapdff_lint import check_map_clump
        is_veh = bool(clump.collision_data) or any(
            k in n.lower() for n in names for k in ('wheel', 'chassis', 'gunflash'))
        fatal, warn = check_map_clump(clump, model_name=model_name, is_vehicle=is_veh)
        out += ["GAME WILL CRASH — model: %s" % x for x in fatal]
        out += ["model: %s" % x for x in warn]
    return [str(x) for x in out]


# ── TXD ──────────────────────────────────────────────────────────────

def txd_data(name, objs, opts, warnings, base=None):
    """Текстуры материалов objs → байты .txd (DXT1 / DXT3 с мипами). base —
    байты существующего TXD для слияния (одноимённые заменяются, остальные
    текстуры сохраняются). (байты | None — текстур нет, подпись)."""
    from inu_gta_core.dff import make_library_id
    from . import txd_build as tb
    sources, missing = _sr().texture_sources(objs)
    warnings += ["%s: texture file not found — %s" % (name, m) for m in missing]
    if not sources:
        return None, ''
    lib_id = make_library_id(opts['version'])
    platform = tb.PLATFORM_D3D9 if opts['game'] == 'SA' else tb.PLATFORM_D3D8
    sections = []
    for tex, (src, alpha) in sources.items():
        px = tb.load_rgba(src)
        if px is None:
            warnings.append("%s: can't read %s" % (name, src))
            continue
        sections.append((tex, tb.texture_native(tex, px, alpha, platform, lib_id,
                                                opts['dxt_backend'])))
    if not sections:
        return None, ''
    if opts.get('platform') == 'MOBILE':
        # мобильный TXD в Max ещё не сделан — одна строка на весь экспорт,
        # в начало списка (окно показывает первые 12)
        w = ("Mobile target: TXD written in PC format, as in Blender; "
             "convert it to the device's PVRTC/ETC format before installation")
        if w not in warnings:
            warnings.insert(0, w)
    note = "%d textures" % len(sections)
    data = None
    if base is not None:
        res = tb.merge(base, sections)
        if res is None:
            warnings.append("%s: existing data is not a TXD — replaced" % name)
        else:
            lib, merged, rep, add = res
            data = tb.assemble(merged, lib)
            note = "merged: %d updated, %d added, %d total" % (rep, add, len(merged))
    if data is None:
        data = tb.assemble(sections, lib_id)
    return data, note


def write_txd(path, objs, opts, warnings):
    """Текстуры материалов objs → .txd. При «Merge into existing TXD» и
    существующем файле — слияние. Возвращает подпись для списка записанного
    или '' (текстур нет)."""
    name = os.path.basename(path)
    base = None
    if opts['txd_merge'] and os.path.isfile(path):
        with open(path, 'rb') as f:
            base = f.read()
    data, note = txd_data(name, objs, opts, warnings, base)
    if data is None:
        return ''
    with open(path, 'wb') as f:
        f.write(data)
    return "%s (%s)" % (name, note)


# ── сценарии ─────────────────────────────────────────────────────────

def _opts():
    g = settings.get
    game = g('game', 'SA')
    return dict(game=game, version=_version(game), col_version=_col_version(game),
                platform=g('platform', 'PC'),
                pipeline=g('export_pipeline', 'NONE'),
                vertex_alpha=bool(g('export_vertex_alpha', False)),
                audit=bool(g('audit_on_export', False)),
                auto_light=(g('col_light_mode', 'AUTO'),
                            int(g('col_auto_day', 14)), int(g('col_auto_night', 4))),
                txd=bool(g('exp_txd', True)), txd_merge=bool(g('txd_merge', False)),
                txd_shared=bool(g('txd_shared', False)),
                txd_shared_name=(g('txd_shared_name', 'textures') or 'textures').strip(),
                dxt_backend=g('dxt_backend', 'numpy'))


def groups():
    """{базовое имя: {'DFF': узел, 'LOD': узел, 'COL': узел}} выделенных мешей."""
    sel = _sel()
    out = {}
    for o in sel.selected_meshes():
        kind, base = sel.classify(o)
        base = (base or '').rstrip('_')
        if not base:
            continue
        g = out.setdefault(base, {'DFF': None, 'LOD': None, 'COL': None})
        if kind and g.get(kind) is None:
            g[kind] = o
    return out


def export_groups(directory, name_override=''):
    """Export All по группам. Возвращает (записано, ошибки, предупреждения)."""
    from ..adapter import fx as fx_ad
    g = settings.get
    opts = _opts()
    done, errors, warnings = [], [], []
    model_groups = groups()
    if not model_groups:
        return done, ["Select the models to export"], warnings
    renamed = bool(name_override and len(model_groups) == 1)
    if renamed:
        model_groups = {name_override: next(iter(model_groups.values()))}
    library = []                    # COL-библиотека: все модели в один .col
    shared_txd = []                 # «Shared TXD»: текстуры всех групп в один .txd
    for base, models in model_groups.items():
        for kind, fname, want in (('DFF', base + '.dff', g('exp_dff', True)),
                                  ('LOD', 'LOD' + base + '.dff', g('exp_lod', True))):
            o = models[kind]
            if o is None or not want:
                continue
            if kind == 'LOD':
                from . import map_link as ML
                from ..adapter import link_scene as LS
                rec = LS.rec_of(o)
                hd = base if models['DFF'] is not None else ''
                fname = ((ML.new_lod_name(hd, base, game=opts['game']) if renamed else
                          ML.lod_model_name(rec, base, hd=hd, game=opts['game'])) + '.dff')
                note = ML.lod_name_note(rec, fname[:-4], hd, game=opts['game'])
                if note:
                    warnings.append(note)
            try:
                nodes = _nodes_for([(o, None)], opts['pipeline'])
                fx = []
                if kind == 'DFF':
                    fx = _fx_entries([c for c in o.children if fx_ad.is_2dfx(c)], o)
                _write(os.path.join(directory, fname), nodes, fx, opts, warnings)
                done.append(fname)
            except Exception as e:                     # noqa: BLE001
                import traceback
                traceback.print_exc()
                errors.append("%s: %s" % (fname, e))
        # коллизия группы: .col (или в библиотеку) и .cst
        empty = bool(g('col_empty', False))
        col = models['COL']
        if (col is not None or empty) and (g('exp_col', True) or g('exp_cst', False)):
            try:
                visual = [o for o in (models['DFF'], models['LOD']) if o is not None][:1]
                model = _col_model(base, opts['col_version'],
                                   [col] if col is not None else [], [], opts,
                                   warnings, empty=empty, bounds_objs=visual)
                if g('exp_col', True):
                    if g('col_library', False):
                        library.append(model)
                    else:
                        from inu_gta_core.col import write_col_file
                        write_col_file(os.path.join(directory, base + '.col'),
                                       [model], target_game=opts['game'])
                        done.append(base + '.col')
                if g('exp_cst', False):
                    from inu_gta_core.cst import write_cst
                    write_cst(os.path.join(directory, base + '.cst'), [model])
                    done.append(base + '.cst')
            except Exception as e:                     # noqa: BLE001
                import traceback
                traceback.print_exc()
                errors.append("%s.col: %s" % (base, e))
        # текстуры группы (DFF + LOD): <имя>.txd или в общий
        if opts['txd']:
            visual = [o for o in (models['DFF'], models['LOD']) if o is not None]
            if opts['txd_shared']:
                shared_txd += visual
            elif visual:
                _txd(os.path.join(directory, base + '.txd'), visual, opts,
                     done, errors, warnings)
    if shared_txd:
        _txd(os.path.join(directory, opts['txd_shared_name'] + '.txd'), shared_txd,
             opts, done, errors, warnings)
    if library:
        name = (g('col_library_name', 'collision') or 'collision').strip()
        try:
            from inu_gta_core.col import write_col_file
            write_col_file(os.path.join(directory, name + '.col'), library,
                           target_game=opts['game'])
            done.append("%s.col (%d records)" % (name, len(library)))
        except Exception as e:                         # noqa: BLE001
            errors.append("%s.col: %s" % (name, e))
    return done, errors, warnings


def export_single(directory, name_override=''):
    """«Один DFF»: вся иерархия от корня крупнейшего выделенного меша."""
    from ..adapter import fx as fx_ad
    sel = _sel()
    opts = _opts()
    done, errors, warnings = [], [], []
    meshes = sel.selected_meshes()
    if not meshes:
        return done, ["No mesh objects to export"], warnings
    root = max(meshes, key=lambda o: _sr().vert_count(o))
    while root.parent is not None:
        root = root.parent
    name = name_override or str(root.name)
    fname = name + '.dff'
    try:
        pairs = _hierarchy(root)
        nodes = _nodes_for(pairs, opts['pipeline'])
        first_mesh = next((o for o, _p in pairs if _sr().frame_kind(o) == 'MESH'), None)
        helpers = []

        def walk(o):
            for c in list(o.children):
                if fx_ad.is_2dfx(c):
                    helpers.append(c)
                walk(c)
        walk(root)
        fx = _fx_entries(helpers, first_mesh) if first_mesh is not None else []
        # коллизия машины / педа — ВНУТРЬ .dff (отдельный .col не пишется)
        collision = b''
        cols, prims = _collision_objects(meshes, list(_sel()._rt().selection))
        if cols or prims:
            from inu_gta_core.col import write_col
            model = _col_model(name, 3 if opts['version'] >= 0x36000 else 1,
                               cols, prims, opts, warnings, ref_node=root)
            collision = write_col([model], target_game=opts['game'])
        elif settings.get('exp_col', True) and not any(
                n.mesh is not None and n.mesh.skin for n in nodes):   # пед — без COL
            warnings.append("COL mesh not found — collision is not embedded "
                            "into the .dff")
        _write(os.path.join(directory, fname), nodes, fx, opts, warnings, collision)
        done.append(fname + (" (+collision)" if collision else ""))
    except Exception as e:                             # noqa: BLE001
        import traceback
        traceback.print_exc()
        errors.append("%s: %s" % (fname, e))
    if opts['txd']:
        objs = [o for o, _p in _hierarchy(root) if _sr().frame_kind(o) == 'MESH']
        txd_name = opts['txd_shared_name'] if opts['txd_shared'] else name
        _txd(os.path.join(directory, txd_name + '.txd'), objs, opts,
             done, errors, warnings)
    return done, errors, warnings


def _txd(path, objs, opts, done, errors, warnings):
    try:
        note = write_txd(path, objs, opts, warnings)
        if note:
            done.append(note)
    except Exception as e:                             # noqa: BLE001
        import traceback
        traceback.print_exc()
        errors.append("%s: %s" % (os.path.basename(path), e))


def export(directory, name_override=''):
    """Точка входа окна экспорта. Модели — целиком, при любом открытом
    уровне стека (scene_read.full_result)."""
    if settings.get('export_to_img', False):
        return [], ['All → IMG requires the IMG resource dialog; use Export in the INU panel'], []
    with _sr().full_result():
        if settings.get('exp_single_dff', False):
            res = export_single(directory, name_override)
        else:
            res = export_groups(directory, name_override)
    if not res[1] and settings.get('exp_ide_ipl', False):
        from . import map_link_ops
        for operation in (map_link_ops.upsert_ide, map_link_ops.upsert_ipl):
            report = operation()
            if report:
                (res[1] if report[0] == 'ERROR' else res[2]).append(report[1])
    return res
