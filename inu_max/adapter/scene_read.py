# INU Tools (Max) — чтение сцены Max для экспорта DFF: узлы → ExportNode /
# MeshData / MatData (ops/dff_build.py).
#
# Тяжёлые данные меша (вершины, грани, нормали, каналы UV и цветов) отдаёт
# одна MAXScript-функция за вызов — поэлементные вызовы pymxs на тысячах
# граней слишком медленные. Соглашения как у скриптов Kam's: UV — каналы 1
# и 2, цвет дня — канал 0, ночи — −1 (Illumination), альфа — −2.

import contextlib
import re

from .selection import (_rt, get_flags, get_prop, classify, node_kind)


def _owns(node, h):
    """Узел содержит объект стека (база или модификатор) с anim-handle h."""
    rt = _rt()
    try:
        if int(rt.getHandleByAnim(node.baseObject)) == h:
            return True
        return any(int(rt.getHandleByAnim(m)) == h for m in node.modifiers)
    except Exception:                                  # noqa: BLE001
        return False


@contextlib.contextmanager
def full_result():
    """Модели читаются целиком, какой бы уровень стека ни был открыт. Если в
    панели Modify текущий уровень ниже верхнего и выключен Show End Result,
    Max считает модель только до этого уровня — всё, что выше (например,
    мазки VertexPaint), не попало бы в файл (проверено экспортом DFF в Max
    2026). На время блока Show End Result включается; после — настройка и
    текущий уровень стека пользователя возвращаются (чтение нормалей для
    экспорта само переключает стек на верхний модификатор)."""
    rt = _rt()
    saved = cur = owner = None
    sel = []
    try:
        saved = bool(rt.execute("showEndResult"))
        if str(rt.getCommandPanelTaskMode()) == 'modify':
            cur = rt.modPanel.getCurrentObject()
            sel = list(rt.selection)
            if cur is not None:
                h = int(rt.getHandleByAnim(cur))
                owner = next((n for n in sel if _owns(n, h)), None)
        if saved is False:
            rt.execute("showEndResult = true")
    except Exception as e:                             # noqa: BLE001
        print("[INU] full result: %r" % (e,))
    try:
        yield
    finally:
        try:
            if owner is not None and rt.isValidNode(owner):
                rt.execute("max modify mode")
                rt.modPanel.setCurrentObject(cur, node=owner)
                if len(sel) > 1:                    # setCurrentObject оставил один узел
                    rt.select(sel)
            if saved is False:
                rt.execute("showEndResult = false")
        except Exception as e:                         # noqa: BLE001
            print("[INU] full result restore: %r" % (e,))

# MAXScript: данные меша узла в его системе координат (как фрейм DFF).
# Возврат: #(V, F, M, N, uv1v, uv1f, uv2v, uv2f, c0v, c0f, cNv, cNf, cAv, cAf),
# массивы плоские; отсутствующий канал — undefined.
_MXS = r'''
global inuMeshData
fn inuMeshData node = (
    -- MAXScript НЕ различает регистр: m и M, f и F — одна переменная!
    -- меш — в системе ОБЪЕКТА (node.mesh), а не мира (snapshotAsMesh):
    -- у модели далеко от 0,0,0 путь «мир → обратно» терял точность float32
    local inv = inverse node.transform
    local worldMesh = false
    local msh = undefined
    try (msh = copy node.mesh) catch (msh = undefined)
    if msh == undefined do (msh = snapshotAsMesh node; worldMesh = true)
    local toNode = if worldMesh then inv else (node.objectTransform * inv)
    local toNodeT = toNode.row4
    -- без смещения пивота система объекта = система узла: координаты как есть
    local plainOffset = (not worldMesh) and node.objectOffsetPos == [0,0,0] and \
        node.objectOffsetScale == [1,1,1] and node.objectOffsetRot == (quat 0 0 0 1)
    local outV = #(), outF = #(), outM = #(), outN = #()
    for i = 1 to msh.numverts do (
        local p = getVert msh i
        if not plainOffset do p = p * toNode
        append outV p.x; append outV p.y; append outV p.z
    )
    -- нормали — временным Edit_Normals НАВЕРХУ стека: getFaceRNormals
    -- не видит явных нормалей (Edit Normals / импорт) и отдал бы гладкие
    local enm = undefined
    local oldSel = selection as array
    local oldMode = getCommandPanelTaskMode()
    try (
        enm = Edit_Normals()
        addModifier node enm
        max modify mode
        select node
        modPanel.setCurrentObject enm
        if (enm.GetNumFaces node:node) != msh.numfaces do (deleteModifier node enm; enm = undefined)
    ) catch (enm = undefined)
    -- нормали Edit_Normals — в системе объекта; в систему узла
    local o2n = node.objectTransform * inv
    local o2nT = o2n.row4
    for k = 1 to msh.numfaces do (
        local fc = getFace msh k
        append outF (fc.x as integer); append outF (fc.y as integer); append outF (fc.z as integer)
        append outM (getFaceMatID msh k)
        local rn = #()
        if enm != undefined then (
            for c = 1 to 3 do (
                local en0 = enm.GetNormal (enm.GetNormalID k c node:node) node:node
                append rn (if plainOffset then normalize en0 else normalize ((en0 * o2n) - o2nT))
            )
        ) else (
            try (rn = meshop.getFaceRNormals msh k) catch ()
            if rn == undefined or rn.count != 3 then (
                local fn0 = getFaceNormal msh k
                rn = #(fn0, fn0, fn0)
            )
            -- нормали меша — в его системе (объекта или мира) → в систему узла
            for c = 1 to 3 do rn[c] = normalize ((rn[c] * toNode) - toNodeT)
        )
        for nrm in rn do (
            append outN nrm.x; append outN nrm.y; append outN nrm.z
        )
    )
    if enm != undefined do deleteModifier node enm
    if oldSel.count > 0 then select oldSel else clearSelection()
    setCommandPanelTaskMode oldMode
    local res = #(outV, outF, outM, outN)
    for ch in #(1, 2, 0, -1, -2) do (
        if meshop.getMapSupport msh ch then (
            local cv = #(), cf = #()
            for i = 1 to (meshop.getNumMapVerts msh ch) do (
                local t = meshop.getMapVert msh ch i
                append cv t.x; append cv t.y; append cv t.z
            )
            for k = 1 to msh.numfaces do (
                local mf = meshop.getMapFace msh ch k
                append cf (mf.x as integer); append cf (mf.y as integer); append cf (mf.z as integer)
            )
            append res cv; append res cf
        ) else (
            append res undefined; append res undefined
        )
    )
    delete msh
    res
)
global inuMeshVerts
fn inuMeshVerts node = (
    -- только вершины в системе узла (для Generate COL): без нормалей и каналов
    local vertMesh = undefined
    try (vertMesh = copy node.mesh) catch (vertMesh = undefined)
    local fromWorld = (vertMesh == undefined)
    if fromWorld do vertMesh = snapshotAsMesh node
    local toLocal = if fromWorld then (inverse node.transform) else (node.objectTransform * (inverse node.transform))
    local plainOff = (not fromWorld) and node.objectOffsetPos == [0,0,0] and \
        node.objectOffsetScale == [1,1,1] and node.objectOffsetRot == (quat 0 0 0 1)
    local flat = #()
    for i = 1 to vertMesh.numverts do (
        local pt = getVert vertMesh i
        if not plainOff do pt = pt * toLocal
        append flat pt.x; append flat pt.y; append flat pt.z
    )
    delete vertMesh
    flat
)
global inuSkinData
fn inuSkinData node = (
    local sk = undefined
    for m in node.modifiers where classOf m == Skin and m.enabled do (sk = m; exit)
    if sk == undefined then undefined else (
        -- skinOps работает только с модификатором, открытым в Modify
        local oldSel = selection as array
        local oldMode = getCommandPanelTaskMode()
        max modify mode
        select node
        modPanel.setCurrentObject sk
        local names = #()
        for b = 1 to (skinOps.GetNumberBones sk) do (
            local nm = undefined
            try (nm = (skinOps.GetBoneNode sk b).name) catch ()
            if nm == undefined do nm = skinOps.GetBoneName sk b 0
            append names nm
        )
        local W = #()
        for v = 1 to (skinOps.GetNumberVertices sk) do (
            local c = skinOps.GetVertexWeightCount sk v
            append W c
            for i = 1 to c do (
                append W (skinOps.GetVertexWeightBoneID sk v i)
                append W (skinOps.GetVertexWeight sk v i)
            )
        )
        if oldSel.count > 0 then select oldSel else clearSelection()
        setCommandPanelTaskMode oldMode
        #(names, W)
    )
)
global inuLocalTM
fn inuLocalTM node parentNode = (
    local tm = node.transform
    if parentNode != undefined do (
        -- родитель-фрейм = родитель в Max и обычный PRS-контроллер: его
        -- значение — точный локальный трансформ («мир × обратный мир» теряет
        -- точность вдали от 0,0,0). NB: «in coordsys parent .transform» НЕ
        -- работает — .transform всегда мировой.
        if node.parent == parentNode and classOf node.controller == prs then
            tm = node.controller.value
        else tm = tm * (inverse parentNode.transform)
    )
    #(tm.row1.x, tm.row1.y, tm.row1.z, tm.row2.x, tm.row2.y, tm.row2.z,
      tm.row3.x, tm.row3.y, tm.row3.z, tm.row4.x, tm.row4.y, tm.row4.z)
)
global inuPointIn
fn inuPointIn p fromNode toNode = (
    local w = p
    if fromNode != undefined do w = p * fromNode.transform
    local q = w * (inverse toNode.transform)
    #(q.x, q.y, q.z)
)
'''

_READY = []


def _ensure():
    if not _READY:
        _rt().execute(_MXS)
        _READY.append(True)


def _triples(flat, conv=float):
    flat = list(flat)
    return [tuple(conv(flat[i + k]) for k in range(3)) for i in range(0, len(flat), 3)]


def _faces(flat):
    return [(a - 1, b - 1, c - 1) for (a, b, c) in _triples(flat, int)]


def mesh_data(node):
    """MeshData узла (ops/dff_build)."""
    from ..ops.dff_build import MeshData
    _ensure()
    res = list(_rt().inuMeshData(node))
    V, F, M, N = res[0], res[1], res[2], res[3]
    md = MeshData(verts=_triples(V), faces=_faces(F),
                  matids=[int(x) for x in M])
    nrm = _triples(N)
    md.normals = [tuple(nrm[i * 3 + k] for k in range(3)) for i in range(len(md.faces))]

    def chan(i):
        cv, cf = res[i], res[i + 1]
        if cv is None or cf is None:
            return None
        return _triples(cv), _faces(cf)
    uv1, uv2, day, night, alpha = (chan(4), chan(6), chan(8), chan(10), chan(12))
    if uv1:
        md.uv1 = ([(t[0], t[1]) for t in uv1[0]], uv1[1])
    if uv2:
        md.uv2 = ([(t[0], t[1]) for t in uv2[0]], uv2[1])
    md.day, md.night = day, night
    if alpha:
        md.alpha = ([t[0] for t in alpha[0]], alpha[1])
    return md


def mesh_verts(node):
    """Вершины меша в системе узла [(x, y, z)] — быстро, без нормалей."""
    _ensure()
    return _triples(_rt().inuMeshVerts(node))


def skin_data(node):
    """Веса модификатора Skin: на вершину [(имя кости, вес)] или None."""
    _ensure()
    res = _rt().inuSkinData(node)
    if res is None:
        return None
    names, flat = [str(n) for n in res[0]], list(res[1])
    out, i = [], 0
    while i < len(flat):
        c = int(flat[i])
        i += 1
        vw = []
        for _ in range(c):
            b, w = int(flat[i]), float(flat[i + 1])
            i += 2
            if 1 <= b <= len(names):
                vw.append((names[b - 1], w))
        out.append(vw)
    return out


def local_tm(node, parent):
    """Трансформ узла относительно родителя (4 строки-оси)."""
    _ensure()
    v = [float(x) for x in _rt().inuLocalTM(node, parent)]
    return (tuple(v[0:3]), tuple(v[3:6]), tuple(v[6:9]), tuple(v[9:12]))


def point_in(p, from_node, to_node):
    """Точка p (в системе from_node или мира) → в систему to_node."""
    _ensure()
    rt = _rt()
    return tuple(float(x) for x in rt.inuPointIn(rt.Point3(*p), from_node, to_node))


def vert_count(node):
    """Число вершин (Editable Mesh или Poly); 0 — не меш."""
    rt = _rt()
    for fn in (lambda: rt.getNumVerts(node), lambda: rt.polyop.getNumVerts(node)):
        try:
            return int(fn())
        except Exception:                              # noqa: BLE001
            continue
    return 0


def world_pos(node):
    pos = node.position
    return (float(pos.x), float(pos.y), float(pos.z))


# ── материалы ────────────────────────────────────────────────────────

def materials_and_ids(node, md):
    """MatData на каждый «слот» материала узла и перевод matID граней Max
    (1-based) в индексы этого списка."""
    from ..ops.dff_build import MatData
    from . import material as mat_ad
    try:
        mat = node.material
    except Exception:                                  # noqa: BLE001
        mat = None
    if mat is None:
        md.matids = [0] * len(md.faces)
        return [MatData()]
    if mat_ad.is_multi(mat):
        subs = list(mat.materialList)
        ids = [int(x) for x in mat.materialIDList]
        n = max(1, len(subs))
        index_of = {mid: i for i, mid in enumerate(ids)}
        md.matids = [index_of.get(m, (m - 1) % n) for m in md.matids]
        mats = subs
    else:
        md.matids = [0] * len(md.faces)
        mats = [mat]
    out = []
    for m in mats:
        if m is None:
            out.append(MatData())
            continue
        rgba = mat_ad.color(m) or (1.0, 1.0, 1.0, 1.0)
        gta_props = mat_ad.props(m)
        if gta_props.get('uv_anim_write') and gta_props.get('uv_anim_mode') == 'KEYFRAME':
            gta_props['uv_keyframes'] = mat_ad.uv_keyframes(m)
        out.append(MatData(color=tuple(int(round(max(0.0, min(1.0, c)) * 255))
                                       for c in rgba),
                           texture=mat_ad.texture_stem(m), props=gta_props,
                           name=str(m.name)))
    return out


# ── текстуры для TXD ─────────────────────────────────────────────────

_TEX_EXT = ('.png', '.tga', '.bmp', '.dds', '.jpg', '.jpeg', '.tif', '.tiff')


def _find_file(name, dirs):
    """Файл текстуры по имени: путь как есть, иначе <имя>.<ext> в dirs."""
    import os
    if name and os.path.isfile(name):
        return name
    stem = os.path.splitext(os.path.basename(name or ''))[0]
    for d in dirs:
        for ext in _TEX_EXT:
            p = os.path.join(d, stem + ext)
            if os.path.isfile(p):
                return p
    return ''


def texture_sources(nodes):
    """({имя в TXD: [файл, альфа]}, [ненайденные]) текстур материалов узлов.
    Имя — как пишет DFF (texture_name, иначе имя файла diffuse). Альфа (DXT3)
    — карта opacity включена или у файла есть значимый альфа-канал. Как
    collect_textures INU: ещё текстуры эффектов (env / bump / dual /
    specular) — файлы рядом с diffuse, и paintjob → <имя>_paintjob1/2."""
    import os
    from . import material as mat_ad
    from ..ops.dff_build import _strip_ext
    out, missing = {}, []

    def add(name, path, alpha):
        if not name:
            return
        if not path:
            if name not in missing:
                missing.append(name)
            return
        if name in out:
            out[name][1] = out[name][1] or alpha
        else:
            out[name] = [path, alpha]

    for m in mat_ad.node_materials(nodes):
        p = mat_ad.props(m)
        diffuse = mat_ad.texture_file(m)
        dirs = [os.path.dirname(diffuse)] if diffuse else []
        base = _strip_ext(p.get('texture_name') or mat_ad.texture_stem(m))
        if base:
            path = diffuse if os.path.isfile(diffuse) else _find_file(base, dirs)
            add(base, path, mat_ad._opacity_on(m) or mat_ad._has_alpha(path))
        for flag, key in (('export_env_map', 'env_map_tex'),
                          ('export_bump_map', 'bump_map_tex'),
                          ('export_dual_tex', 'dual_tex_texture'),
                          ('export_specular', 'specular_texture'),
                          ('export_dk_normal_map', 'dk_normal_texture'),
                          ('export_dk_normal_map', 'dk_reflection_texture')):
            name = _strip_ext(p.get(key, ''))
            if p.get(flag) and name:
                path = _find_file(p[key], dirs)
                add(name, path, mat_ad._has_alpha(path))
        if base:
            for key, sfx in (('paintjob_alt_1', '_paintjob1'),
                             ('paintjob_alt_2', '_paintjob2')):
                if p.get(key):
                    path = _find_file(p[key], dirs)
                    add(base + sfx, path, out.get(base, ['', False])[1]
                        or mat_ad._has_alpha(path))
    return out, missing


# ── коллизия ─────────────────────────────────────────────────────────

_PRIM_NAME = re.compile(r'_(sphere|box)_\d+$', re.I)


def col_prim(o):
    """'SPHERE' | 'BOX' — примитив коллизии (Sphere / Box с user property
    inu_col_prim или именем «<модель>_sphere_N» / «_box_N»), иначе None."""
    rt = _rt()
    tag = str(get_prop(o, 'col_prim', '')).strip('"').upper()
    if tag in ('SPHERE', 'BOX'):
        return tag
    if get_prop(o, 'zon', False):
        return None
    m = _PRIM_NAME.search(str(o.name))
    if not m:
        return None
    try:
        cls = rt.classOf(o)
        if m.group(1).lower() == 'sphere' and cls == rt.Sphere:
            return 'SPHERE'
        if m.group(1).lower() == 'box' and cls == rt.Box:
            return 'BOX'
    except Exception:                                  # noqa: BLE001
        pass
    return None


def is_shadow(o):
    """Меш тени: тип SHA или имя «…_sha» (соглашение Kam's)."""
    mat = getattr(o, 'material', None)
    material_shadow = mat is not None and str(_rt().classOf(mat)).lower() in ('inu_gta_colshadow', 'gta_colshadow')
    return (material_shadow or str(get_prop(o, 'type', '')).strip('"').upper() == 'SHA'
            or str(o.name).lower().endswith('_sha'))


def col_mesh(o):
    """ColMesh узла: вершины в системе узла с его масштабом (без поворота и
    позиции, как INU), поверхности граней — из свойств материалов."""
    from ..ops.col_build import ColMesh, surface_of
    md = mesh_data(o)
    mats = materials_and_ids(o, md)
    try:
        s = o.scale
        sx, sy, sz = float(s.x), float(s.y), float(s.z)
    except Exception:                                  # noqa: BLE001
        sx = sy = sz = 1.0
    surf = [surface_of(m.props) for m in mats]
    return ColMesh(verts=[(x * sx, y * sy, z * sz) for (x, y, z) in md.verts],
                   faces=md.faces,
                   surfaces=[surf[i] if 0 <= i < len(surf) else surf[0]
                             for i in md.matids],
                   shadow=is_shadow(o))


def col_bounds(o):
    """Границы исходного COL (user property inu_col_bounds, 10 чисел: радиус,
    центр, AABB) или None — у коллизии, собранной с нуля."""
    from .selection import get_field
    b = get_field(o, 'col_bounds', (0.0,) * 10)
    return b if any(b) else None


def col_prim_data(o, version=1):
    """ColPrim примитива: сфера — центр (мир) и радиус × наибольший
    масштаб; бокс — мировой габарит. Поверхность — из материала или user
    properties col_material / col_light."""
    from ..ops.col_build import ColPrim, surface_of, clamp_light
    from . import material as mat_ad
    kind = col_prim(o)
    surf = (clamp_light(get_prop(o, 'col_material', 0)), clamp_light(get_prop(o, 'col_flags', 0)),
            clamp_light(get_prop(o, 'col_brightness', 0)), clamp_light(get_prop(o, 'col_light', 0)))
    try:
        if o.material is not None and not mat_ad.is_multi(o.material):
            surf = surface_of(mat_ad.props(o.material))
            if version >= 2 and not mat_ad.is_col(o.material):
                surf = (surf[0], surf[1], surf[3], clamp_light(get_prop(o, 'col_light', 0)))
    except Exception:                                  # noqa: BLE001
        pass
    if kind == 'BOX':
        mn, mx = o.min, o.max
        return ColPrim(kind='BOX', bb_min=(float(mn.x), float(mn.y), float(mn.z)),
                       bb_max=(float(mx.x), float(mx.y), float(mx.z)), surface=surf)
    s = o.objecttransform.scalepart
    r = float(o.radius) * max(abs(float(s.x)), abs(float(s.y)), abs(float(s.z)))
    return ColPrim(kind='SPHERE', center=world_pos(o), radius=r, surface=surf)


# ── какие узлы идут во фреймы ────────────────────────────────────────

def is_col(o):
    """Коллизия (COL/SHA): встраивается отдельно, не фрейм. Как
    is_collision_mesh INU — только ЯВНЫЙ признак: тип COL/SHA или маркер
    имени «_col» / «_sha» (эвристика «нет текстуры = коллизия» здесь не
    годится: нетекстурный кузов машины выпал бы из DFF). Маркер «_DFF» /
    «_LOD» в имени сильнее устаревшего тега."""
    try:
        if node_kind(o) != 'MESH':
            return False
        from inu_gta_core.model_classify import explicit_name_type
        marker, _base = explicit_name_type(str(o.name))
        if marker in ('DFF', 'LOD'):
            return False
        tag = str(get_prop(o, 'type', '')).strip('"').upper()
        return tag in ('COL', 'SHA') or marker == 'COL'
    except Exception:                                  # noqa: BLE001
        return False


def frame_kind(o):
    """'MESH' | 'DUMMY' | None (не фрейм: 2DFX, коллизия, свет, камера…)."""
    from . import fx as fx_ad
    rt = _rt()
    if fx_ad.is_2dfx(o) or str(get_prop(o, 'type', '')).strip('"') == 'NON':
        return None
    if col_prim(o) or get_prop(o, 'zon', False):
        return None
    kind = node_kind(o)
    if kind == 'MESH':
        return None if is_col(o) else 'MESH'
    try:
        if rt.superClassOf(o) == rt.helper or kind == 'BONE':
            return 'DUMMY'
    except Exception:                                  # noqa: BLE001
        pass
    return None


def flags(node):
    return get_flags(node)
