# INU Tools (Max) — постройка сцены Max по плану импорта (ops/dff_read.py).
#
# Тяжёлое — одной MAXScript-функцией на объект (поэлементные вызовы pymxs
# медленные): меш + каналы карт, явные нормали (Edit_Normals, затем свёртка в
# Editable Mesh — нормали сохраняются), Skin. Соглашения совпадают с тем, что
# читает экспорт (adapter/scene_read.py): UV 1/2, день 0, ночь −1, альфа −2,
# Dummy — фреймы, Bone — кости скелета, user properties inu_<ключ>.
#
# MAXScript НЕ различает регистр: имена переменных — длинные и разные
# (проверка — scratchpad check_mxs_case.py).

import os

from .selection import _rt, set_prop, put_field

_MXS = r'''
global inuMakeMesh
fn inuMakeMesh inVerts inFaces inMats = (
    local nv = inVerts.count / 3
    local nf = inFaces.count / 3
    local obj = mesh numverts:nv numfaces:nf
    with undo off (
        for i = 1 to nv do
            setVert obj i [inVerts[i*3-2], inVerts[i*3-1], inVerts[i*3]]
        for k = 1 to nf do (
            setFace obj k [inFaces[k*3-2], inFaces[k*3-1], inFaces[k*3]]
            setFaceMatID obj k inMats[k]
            setEdgeVis obj k 1 true; setEdgeVis obj k 2 true; setEdgeVis obj k 3 true
        )
    )
    update obj
    obj
)
global inuSetMeshData
fn inuSetMeshData obj inVerts inFaces = (
    -- заменить геометрию существующего узла (перегенерация <имя>_COL):
    -- узел, его имя, свойства и материал остаются
    if classOf obj != Editable_mesh do convertToMesh obj
    local nv = inVerts.count / 3
    local nf = inFaces.count / 3
    setNumVerts obj nv
    setNumFaces obj nf
    with undo off (
        for i = 1 to nv do
            setVert obj i [inVerts[i*3-2], inVerts[i*3-1], inVerts[i*3]]
        for k = 1 to nf do (
            setFace obj k [inFaces[k*3-2], inFaces[k*3-1], inFaces[k*3]]
            setFaceMatID obj k 1
            setEdgeVis obj k 1 true; setEdgeVis obj k 2 true; setEdgeVis obj k 3 true
        )
    )
    update obj
    obj
)
global inuMakeBone
fn inuMakeBone boneName = (
    local bn = BoneSys.createBone [0,0,0] [0.05,0,0] [0,0,1]
    -- без «поведения кости»: иначе при оценке сцены кость тянется (stretch)
    -- и доворачивается к ребёнку — во вьюпорте длинные «шипы» через модель
    bn.boneEnable = false
    bn.boneFreezeLength = true
    bn.name = boneName
    bn.width = 0.02
    bn.height = 0.02
    bn.taper = 90
    bn
)
global inuSetChannel
fn inuSetChannel obj chan inVals inFaces = (
    -- значения на вершину DFF (по 3 числа), грани карты = грани DFF.
    -- meshop.setNumMaps включает ВСЕ каналы 0..n-1 (0 — белым, остальные —
    -- позициями вершин): выключенные до вызова каналы выключаются снова
    local oldCount = meshop.getNumMaps obj
    if chan > 1 and oldCount <= chan do (
        local offChans = for c = 0 to (oldCount - 1) where not (meshop.getMapSupport obj c) collect c
        meshop.setNumMaps obj (chan + 1) keep:true
        for c in offChans do meshop.setMapSupport obj c false
        for c = oldCount to (chan - 1) do meshop.setMapSupport obj c false
    )
    meshop.setMapSupport obj chan true
    local nmv = inVals.count / 3
    meshop.setNumMapVerts obj chan nmv
    for i = 1 to nmv do
        meshop.setMapVert obj chan i [inVals[i*3-2], inVals[i*3-1], inVals[i*3]]
    for k = 1 to (inFaces.count / 3) do
        meshop.setMapFace obj chan k [inFaces[k*3-2], inFaces[k*3-1], inFaces[k*3]]
    true
)
global inuSetNormals
fn inuSetNormals obj cornerN = (
    -- явная нормаль на каждый угол; модификатор затем сворачивается
    local enm = Edit_Normals()
    addModifier obj enm
    max modify mode
    select obj
    modPanel.setCurrentObject enm
    local total = enm.GetNumNormals node:obj
    if total > 0 do enm.Break selection:#{1..total} node:obj
    for k = 1 to obj.numfaces do (
        for c = 1 to 3 do (
            local nid = enm.GetNormalID k c node:obj
            local b = ((k - 1) * 3 + (c - 1)) * 3
            enm.SetNormal nid [cornerN[b+1], cornerN[b+2], cornerN[b+3]] node:obj
            enm.SetNormalExplicit nid explicit:true node:obj
        )
    )
    convertToMesh obj
    true
)
global inuApplySkin
fn inuApplySkin obj boneNodes weightsFlat = (
    -- weightsFlat: на вершину: число весов, затем пары (номер кости 1.., вес)
    local sk = Skin()
    addModifier obj sk
    max modify mode
    select obj
    modPanel.setCurrentObject sk
    for j = 1 to boneNodes.count do
        skinOps.addBone sk boneNodes[j] (if j == boneNodes.count then 1 else 0)
    local pos = 1
    local vtx = 0
    while pos <= weightsFlat.count do (
        vtx += 1
        local cnt = weightsFlat[pos] as integer
        pos += 1
        local ids = #(), wts = #()
        for q = 1 to cnt do (
            append ids (weightsFlat[pos] as integer)
            append wts weightsFlat[pos + 1]
            pos += 2
        )
        if cnt > 0 do skinOps.ReplaceVertexWeights sk vtx ids wts
    )
    true
)
'''

_READY = []


def _ensure():
    if not _READY:
        _rt().execute(_MXS)
        _READY.append(True)


def _flat(rows):
    return [float(x) for r in rows for x in r]


# ── матрицы ──────────────────────────────────────────────────────────

def _matrix(t):
    rt = _rt()
    P3 = rt.Point3
    (r1, r2, r3, p) = t
    return rt.Matrix3(P3(*map(float, r1)), P3(*map(float, r2)),
                      P3(*map(float, r3)), P3(*map(float, p)))


def _world_rows(nodes):
    from ..ops.dff_build import _mul
    from ..ops.dff_read import _rows
    out = []
    for n in nodes:
        (r1, r2, r3, p) = n.transform
        m = [list(r1) + [0.0], list(r2) + [0.0], list(r3) + [0.0], list(p) + [1.0]]
        out.append(_mul(m, out[n.parent]) if n.parent >= 0 else m)
    return [_rows(m) for m in out]


# ── материалы ────────────────────────────────────────────────────────

def _material(md, tex_map, idx):
    """Standard-материал: цвет/прозрачность, diffuse-bitmap по имени текстуры,
    GTA-свойства в AppData (adapter/material)."""
    from . import material as mat_ad
    rt = _rt()
    std = rt.StandardMaterial(name=md.name or "mat_%d" % idx)
    std.twoSided = True
    r, g, b, a = md.color
    std.diffuse = rt.color(float(r), float(g), float(b))
    std.opacity = float(a) / 255.0 * 100.0
    props = dict(md.props)
    if md.texture:
        props['texture_name'] = md.texture      # имя из DFF (PNG может быть переименован)
        png = tex_map.get(md.texture.lower())
        if png:
            try:
                std.diffuseMap = rt.Bitmaptexture(fileName=png)
                std.showInViewport = True
                if mat_ad._has_alpha(png):
                    mat_ad.set_props(std, props)
                    mat_ad.set_blend(std, 'BLEND')
            except Exception as e:                     # noqa: BLE001
                print("[INU import] bitmap '%s': %r" % (md.texture, e))
    mat_ad.set_props(std, props)
    return std


def _assign_materials(node, mats, tex_map):
    rt = _rt()
    if not mats:
        return
    if len(mats) == 1:
        node.material = _material(mats[0], tex_map, 0)
        return
    mm = rt.MultiMaterial(numsubs=len(mats))
    for i, md in enumerate(mats):
        rt.setSubMtl(mm, i + 1, _material(md, tex_map, i))
    node.material = mm


# ── узлы ─────────────────────────────────────────────────────────────

def _mesh_node(m):
    """Editable Mesh из ImportMesh: сварка (Python), каналы, нормали."""
    from ..ops.dff_read import welded
    rt = _rt()
    verts, gfaces = welded(m)
    nmat = max([i + 1 for i in m.matids] + [1])
    obj = rt.inuMakeMesh(_flat(verts), [i + 1 for f in gfaces for i in f],
                         [min(max(i + 1, 1), nmat) for i in m.matids])
    faces1 = [i + 1 for f in m.faces for i in f]
    for chan, vals in ((1, m.uv1), (2, m.uv2)):
        if vals:
            rt.inuSetChannel(obj, chan, [x for u in vals for x in (u[0], u[1], 0.0)], faces1)
    if m.day:
        rt.inuSetChannel(obj, 0, _flat(m.day), faces1)
    if m.night:
        rt.inuSetChannel(obj, -1, _flat(m.night), faces1)
    if m.alpha:
        rt.inuSetChannel(obj, -2, [x for a in m.alpha for x in (a, a, a)], faces1)
    if m.corner_normals:
        flat = _flat(m.corner_normals)
        # быстрый путь — функция плагина INU (C++, без Edit_Normals и панели
        # Modify); нет плагина или ошибка — MAXScript (результат тот же)
        done = False
        if _fast_mesh():
            try:
                done = int(rt.INU_FastMesh.setNormals(obj, flat)) > 0
            except Exception as e:                     # noqa: BLE001
                print("[INU import] INU_FastMesh.setNormals: %r" % (e,))
        if not done:
            rt.inuSetNormals(obj, flat)
    return obj


_FAST = []


def _fast_mesh():
    """Есть ли в Max интерфейс INU_FastMesh (плагин INU_Import.dli)."""
    if not _FAST:
        try:
            _FAST.append(bool(_rt().execute("INU_FastMesh != undefined")))
        except Exception:                              # noqa: BLE001
            _FAST.append(False)
    return _FAST[0]


def _dummy(name, size=0.1):
    rt = _rt()
    return rt.Dummy(name=name, boxsize=rt.Point3(size, size, size))


def _bone(name):
    """Bone-объект (как у Kam's). BoneGeometry напрямую не создаётся —
    только через BoneSys; трансформ ставится потом."""
    rt = _rt()
    b = rt.inuMakeBone(name)
    return b


def _layer(name, nodes):
    rt = _rt()
    try:
        layer = rt.LayerManager.getLayerFromName(name) or rt.LayerManager.newLayerFromName(name)
        for n in nodes:
            layer.addNode(n)
    except Exception as e:                             # noqa: BLE001
        print("[INU import] layer %s: %r" % (name, e))


def build(plan, tex_map=None, mark=lambda s: None):
    """Сцена Max по плану. Возвращает список созданных узлов."""
    from . import fx as fx_ad
    rt = _rt()
    _ensure()
    tex_map = tex_map or {}
    worlds = _world_rows(plan.nodes)
    made, created = [], []
    for i, n in enumerate(plan.nodes):
        if n.kind == 'MESH':
            obj = _mesh_node(n.mesh)
            obj.name = n.name
            _assign_materials(obj, n.materials, tex_map)
            mark("mesh '%s': %d verts, %d faces" % (n.name, len(n.mesh.verts), len(n.mesh.faces)))
        elif n.kind == 'BONE':
            obj = _bone(n.name)
        else:
            obj = _dummy(n.name)
        if n.parent >= 0:
            obj.parent = made[n.parent]
        obj.transform = _matrix(worlds[i])
        for k, v in n.props.items():
            set_prop([obj], k, v)
        made.append(obj)
        created.append(obj)
    # длина кости — до первого ребёнка-кости (видно в вьюпорте)
    for i, n in enumerate(plan.nodes):
        if n.kind != 'BONE':
            continue
        kids = [j for j, c in enumerate(plan.nodes) if c.parent == i and c.kind == 'BONE']
        if kids:
            p0, p1 = worlds[i][3], worlds[kids[0]][3]
            d = sum((p1[k] - p0[k]) ** 2 for k in range(3)) ** 0.5
            if d > 1e-4:
                made[i].length = d
    # скин — когда все кости созданы
    for i, n in enumerate(plan.nodes):
        if n.mesh is None or not n.mesh.skin:
            continue
        used = sorted({b for vw in n.mesh.skin for b, _w in vw})
        slot = {b: j + 1 for j, b in enumerate(used)}
        flat = []
        for vw in n.mesh.skin:
            flat.append(float(len(vw)))
            for b, w in vw:
                flat += [float(slot[b]), float(w)]
        rt.inuApplySkin(made[i], [made[b] for b in used], flat)
        mark("skin '%s': %d bones" % (n.name, len(used)))
    # 2DFX — хелперы-дети меша
    fx_nodes = []
    for f in plan.fx:
        host = made[f.parent] if f.parent >= 0 else None
        shape, size = fx_ad._DISPLAY.get(f.effect, ('cross', 0.3))
        h = rt.Point(name=f.name, size=size, cross=shape == 'cross', box=shape == 'box',
                     axistripod=shape == 'axistripod', centermarker=False)
        if host is not None:
            h.parent = host
            h.transform = rt.Matrix3(1) * rt.transMatrix(rt.Point3(*f.loc)) * host.transform
        else:
            h.position = rt.Point3(*f.loc)
        put_field([h], 'type', '2DFX')
        put_field([h], 'effect_2dfx', f.effect)
        for k, v in f.fields.items():
            put_field([h], k, v)
        fx_nodes.append(h)
    if fx_nodes:
        _layer("2DFX", fx_nodes)
    created += fx_nodes
    created += build_collision(plan.col_meshes, plan.col_prims)
    return created


# ── коллизия ─────────────────────────────────────────────────────────

def _bounds_prop(obj, bounds):
    """Границы исходного COL — в user property inu_col_bounds (10 чисел, полная
    точность): экспорт вернёт их как есть (как inu_col_bounds INU)."""
    set_prop([obj], 'col_bounds', '"%s"' % ",".join("%.9g" % float(v) for v in bounds))


def build_collision(meshes, prims, mat_cache=None):
    """Меши и примитивы коллизии в сцену: материал на поверхность COL_<id>
    (общий на весь импорт — как кэш материалов INU), границы исходного COL,
    слой «COL», просвечивание. Возвращает созданные узлы."""
    from . import material as mat_ad
    rt = _rt()
    cache = {} if mat_cache is None else mat_cache

    def mat_for(s, shadow):
        key = (tuple(sorted(s.items())), shadow)
        m = cache.get(key)
        if m is None:
            m = rt.StandardMaterial(name="COL_%d" % s['col_mat_index'])
            m.diffuse = rt.color(60, 60, 60) if shadow else rt.color(120, 200, 120)
            mat_ad.set_props(m, s)
            cache[key] = m
        return m

    out = []
    for cm in meshes:
        uniq = []
        for s in cm.surfaces:
            if s not in uniq:
                uniq.append(s)
        ids = [uniq.index(s) + 1 for s in cm.surfaces]
        obj = rt.inuMakeMesh(_flat(cm.verts), [i + 1 for f in cm.faces for i in f], ids)
        obj.name = cm.name
        mats = [mat_for(s, cm.shadow) for s in uniq]
        if len(mats) == 1:
            obj.material = mats[0]
        else:
            mm = rt.MultiMaterial(numsubs=len(mats))
            mm.name = "COL_" + cm.name
            for j, std in enumerate(mats):
                rt.setSubMtl(mm, j + 1, std)
            obj.material = mm
        put_field([obj], 'type', 'SHA' if cm.shadow else 'COL')
        if cm.bounds:
            _bounds_prop(obj, cm.bounds)
        obj.xray = True
        out.append(obj)
    for p in prims:
        s = p.surface
        if p.kind == 'SPHERE':
            obj = rt.Sphere(name=p.name, radius=float(p.radius), pos=rt.Point3(*p.center))
        else:
            lo, hi = p.bb_min, p.bb_max
            obj = rt.Box(name=p.name, width=hi[0] - lo[0], length=hi[1] - lo[1],
                         height=hi[2] - lo[2],
                         pos=rt.Point3((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]))
        put_field([obj], 'col_prim', p.kind)
        set_prop([obj], 'col_material', s['col_mat_index'])
        set_prop([obj], 'col_flags', s['col_flags'])
        set_prop([obj], 'col_brightness', s['col_brightness'])
        set_prop([obj], 'col_light', s['col_day_light'] | (s['col_night_light'] << 4))
        if p.bounds:
            _bounds_prop(obj, p.bounds)
        obj.xray = True
        out.append(obj)
    if out:
        _layer("COL", out)
    return out
