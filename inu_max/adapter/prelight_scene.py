# INU Tools (Max) — сцена Max для окна Lighting (Prelight).
#
# Каналы цвета вершин (как у импорта / экспорта DFF и Kam's): 0 — Day,
# -1 — Night, -2 — альфа. «Активный слой» (радио Day / Night Blender-версии)
# — user property узла inu_prelight_active; поля V — inu_v_offset_day /
# _night, применённый сдвиг — inu_v_applied_day / _night.
#
# Геометрия для запекания и тени — функции плагина INU (INU_FastMesh, C++):
# вершины, грани и нормали углов (явные нормали или по группам сглаживания)
# через двоичный файл; тени — BVH по видимой геометрии. Без плагина:
# геометрия — MAXScript (медленнее), тени недоступны.
#
# Чтение канала — ИТОГ узла (база + модификаторы, напр. мазки VertexPaint;
# как видит экспорт), запись — в базу. Рисование слоёв — модификатор
# VertexPaint (раздел «VertexPaint» ниже).

import os
import tempfile
import uuid

import numpy as np

from .selection import _rt, get_prop, set_prop, put_field, get_field

LAYER_CHAN = {'Day': 0, 'Night': -1}
ALPHA_CHAN = -2

# 8 ламп Prelight (create_prelight_scene_lights INU): имя, направление, энергия
LIGHTS8 = (
    ("Prelight_TopRightBack", (1, -1, 1), 11),
    ("Prelight_BottomRightBack", (1, -1, -1), 8),
    ("Prelight_TopLeftBack", (-1, -1, 1), 10),
    ("Prelight_BottomLeftBack", (-1, -1, -1), 7),
    ("Prelight_TopRightFront", (1, 1, 1), 11),
    ("Prelight_BottomRightFront", (1, 1, -1), 11),
    ("Prelight_TopLeftFront", (-1, 1, 1), 9),
    ("Prelight_BottomLeftFront", (-1, 1, -1), 7),
)
LIGHTS_LAYER = "Prelight_Lights"
SUN_NAME = SUN_LAYER = "Prelight_Sun"
LAMP_RGB = 188                      # #BCBCBC = 0.737 — цвет ламп INU

_MXS = r'''
global inuPlLights
fn inuPlLights = (
    -- все лампы: #(класс, имя, вкл, скрыта, рендер, r, g, b, множитель,
    --             позиция, row3 (ось Z), hotspot, falloff)
    local outArr = #()
    for o in lights where (classOf o) != Targetobject do (
        local isOn = true
        try (isOn = o.on) catch (try (isOn = o.enabled) catch ())
        local col = white
        try (col = o.rgb) catch ()
        local mult = 1.0
        try (mult = o.multiplier) catch ()
        local hs = 0.0
        local fo = 0.0
        try (hs = o.hotspot; fo = o.falloff) catch ()
        append outArr #((classOf o) as string, o.name, isOn, o.isHiddenInVpt, o.renderable, \
            col.r, col.g, col.b, mult, o.transform.translationpart, o.transform.row3, hs, fo)
    )
    outArr
)
global inuPlGetChannel
fn inuPlGetChannel obj chanIdx = (
    -- канал без плагина: #(вершины канала плоско, грани канала с 1) | undefined
    if not (meshop.getMapSupport obj chanIdx) then undefined else (
        local nmv = meshop.getNumMapVerts obj chanIdx
        local vArr = #()
        vArr.count = nmv * 3
        for i = 1 to nmv do (
            local pt = meshop.getMapVert obj chanIdx i
            vArr[i*3-2] = pt.x; vArr[i*3-1] = pt.y; vArr[i*3] = pt.z
        )
        local nfc = obj.numfaces
        local fArr = #()
        fArr.count = nfc * 3
        for k = 1 to nfc do (
            local fc = meshop.getMapFace obj chanIdx k
            fArr[k*3-2] = fc.x as integer; fArr[k*3-1] = fc.y as integer; fArr[k*3] = fc.z as integer
        )
        #(vArr, fArr)
    )
)
global inuPlSetNumMaps
fn inuPlSetNumMaps obj newCount = (
    -- число каналов без побочных действий: meshop.setNumMaps включает ВСЕ
    -- каналы 0..n-1 (0 — белым, остальные — позициями вершин); каналы,
    -- выключенные до вызова, и новые каналы выключаются снова. Флаги — базы
    -- узла (meshop на узле с модификаторами читает итог, пишет базу)
    local baseMesh = obj.baseObject
    local oldCount = meshop.getNumMaps baseMesh
    local wasOn = for c = 0 to ((amin oldCount newCount) - 1) collect (meshop.getMapSupport baseMesh c)
    meshop.setNumMaps obj newCount keep:true
    for c = 0 to (newCount - 1) where c >= wasOn.count or not wasOn[c + 1] do
        meshop.setMapSupport obj c false
)
global inuPlSetChannel
fn inuPlSetChannel obj chanIdx inVals inFaces = (
    -- записать канал БАЗЫ целиком (вершины канала + грани), с поддержкой отмены
    if chanIdx > 1 and (meshop.getNumMaps obj.baseObject) <= chanIdx do
        inuPlSetNumMaps obj (chanIdx + 1)
    meshop.setMapSupport obj chanIdx true
    local nmv = inVals.count / 3
    meshop.setNumMapVerts obj chanIdx nmv
    for i = 1 to nmv do
        meshop.setMapVert obj chanIdx i [inVals[i*3-2], inVals[i*3-1], inVals[i*3]]
    for k = 1 to (inFaces.count / 3) do
        meshop.setMapFace obj chanIdx k [inFaces[k*3-2], inFaces[k*3-1], inFaces[k*3]]
    update obj
    true
)
global inuPlDropChannel
fn inuPlDropChannel obj chanIdx = (
    -- выключить канал БАЗЫ; true — он был
    local baseMesh = obj.baseObject
    local had = try (meshop.getMapSupport baseMesh chanIdx) catch false
    if had do (
        meshop.setMapSupport obj chanIdx false
        -- канал превью (98 / 99) — лишние пустые каналы в конце убрать
        if chanIdx > 1 do (
            local topOn = 1
            for c = 2 to ((meshop.getNumMaps baseMesh) - 1) where (meshop.getMapSupport baseMesh c) do topOn = c
            if topOn + 1 < (meshop.getNumMaps baseMesh) do inuPlSetNumMaps obj (topOn + 1)
        )
        update obj
    )
    had
)
global inuPlDefaultMap
fn inuPlDefaultMap msh chanIdx = (
    -- канал с заполнением по умолчанию (meshop.setNumMaps): вершины канала
    -- = позиции вершин меша, грани канала = грани меша. msh — TriMesh базы
    -- узла (координаты объекта; getVert узла дал бы мировые)
    local ok = (meshop.getNumMapVerts msh chanIdx) == (getNumVerts msh)
    for i = 1 to (getNumVerts msh) while ok do ok = (meshop.getMapVert msh chanIdx i) == (getVert msh i)
    for k = 1 to (getNumFaces msh) while ok do ok = (meshop.getMapFace msh chanIdx k) == (getFace msh k)
    ok
)
global inuPlRepairMaps
fn inuPlRepairMaps obj = (
    -- след прошлой версии превью: meshop.setNumMaps 100 включил каналы
    -- 0..98. Признак — включены все каналы 3..97 (INU их не пишет). Они
    -- выключаются; 1, 2, 98 — только с заполнением по умолчанию. Канал 0
    -- не трогается: его белый по умолчанию не отличить от белого слоя.
    -- Число выключенных каналов.
    local cnt = 0
    local baseMesh = obj.baseObject
    if (meshop.getNumMaps baseMesh) >= 99 do (
        local allOn = true
        for c = 3 to 97 while allOn do allOn = meshop.getMapSupport baseMesh c
        if allOn do (
            for c = 3 to 97 do meshop.setMapSupport obj c false
            cnt = 95
            local msh = baseMesh.mesh
            for c in #(1, 2, 98) where (meshop.getMapSupport baseMesh c) and (inuPlDefaultMap msh c) do (
                meshop.setMapSupport obj c false
                cnt += 1
            )
            update obj
        )
    )
    cnt
)
global inuPlRepairScene
fn inuPlRepairScene = (
    -- inuPlRepairMaps для всех мешей сцены; число исправленных узлов
    local fixedNodes = 0
    for o in geometry where (classOf o.baseObject) == Editable_mesh do (
        local nm = try (meshop.getNumMaps o.baseObject) catch 0
        if nm >= 99 and (inuPlRepairMaps o) > 0 do fixedNodes += 1
    )
    fixedNodes
)
global inuPlLayerNodes
fn inuPlLayerNodes layerName = (
    -- узлы слоя одним вызовом (перебор всех объектов из Python медленный)
    local lay = LayerManager.getLayerFromName layerName
    local layNodes = #()
    if lay != undefined do lay.nodes &layNodes
    layNodes
)
global inuPlNodesWith
fn inuPlNodesWith chanIdx = (
    -- меши (Editable Mesh) с поддержкой канала chanIdx
    local outNodes = #()
    for o in geometry where (classOf o.baseObject) == Editable_mesh do (
        local ok = try ((meshop.getNumMaps o) > chanIdx and (meshop.getMapSupport o chanIdx)) catch false
        if chanIdx < 0 do ok = try (meshop.getMapSupport o chanIdx) catch false
        if ok do append outNodes o
    )
    outNodes
)
global inuPlMeshNode
fn inuPlMeshNode obj = (
    -- база узла — Editable Mesh (каналы пишутся через meshop)
    isValidNode obj and (classOf obj.baseObject) == Editable_mesh
)
global inuPlPaintMods
fn inuPlPaintMods obj chanIdx = (
    -- VertexPaint узла, рисующие в канал chanIdx (сверху вниз)
    for m in obj.modifiers where (classOf m) == VertexPaint and m.mapChannel == chanIdx collect m
)
global inuPlReplacePaint
fn inuPlReplacePaint nodeArr chanIdx readdMods = (
    -- VertexPaint канала chanIdx у узлов nodeArr удалить; readdMods — на
    -- месте каждого экземпляра поставить новый пустой (один общий на узлы,
    -- где был один экземпляр). #(новый модификатор вместо открытого в
    -- панели Modify или undefined, число удалённых)
    local curObj = modPanel.getCurrentObject()
    local nowCurrent = undefined
    local groupMods = #()
    local groupNodes = #()
    for n in nodeArr do (
        for m in n.modifiers where (classOf m) == VertexPaint and m.mapChannel == chanIdx do (
            local g = findItem groupMods m
            if g == 0 do (append groupMods m; append groupNodes #(); g = groupMods.count)
            append groupNodes[g] n
        )
    )
    local removedCount = 0
    for g = 1 to groupMods.count do (
        local oldMod = groupMods[g]
        local newMod = undefined
        if readdMods do (
            newMod = VertexPaint()
            newMod.mapChannel = chanIdx
            newMod.name = oldMod.name
        )
        for n in groupNodes[g] do (
            -- ModifierArray не приводится «as array»: индекс — перебором
            local idx = 0
            for i = 1 to n.modifiers.count while idx == 0 do if n.modifiers[i] == oldMod do idx = i
            if idx > 0 do (
                deleteModifier n idx
                removedCount += 1
                -- addModifier before:k ставит модификатор сразу под k-м
                if newMod != undefined do (
                    if idx > 1 then addModifier n newMod before:(idx - 1) else addModifier n newMod
                )
            )
        )
        if curObj == oldMod do nowCurrent = newMod
    )
    #(nowCurrent, removedCount)
)
global inuPlFaceSel
fn inuPlFaceSel obj = (
    -- выделенные грани базы (с 1) — хранятся и вне режима подобъектов
    (getFaceSelection obj.baseObject.mesh) as array
)
global inuPlFaceMatIDs
fn inuPlFaceMatIDs obj = (
    local baseTri = obj.baseObject.mesh
    for k = 1 to baseTri.numfaces collect (getFaceMatID baseTri k)
)
global inuPlSceneMeshes
fn inuPlSceneMeshes = (
    for o in geometry where (classOf o.baseObject) == Editable_mesh collect o
)
global inuPlMergeProxy
fn inuPlMergeProxy = (
    -- временная модель «Объединить» (user property inu_prelight_merge)
    local found = undefined
    for o in geometry while found == undefined do
        if (getUserProp o "inu_prelight_merge") != undefined do found = o
    found
)
global inuColSetFaceIDs
fn inuColSetFaceIDs obj faceArr idArr = (
    -- ID материала граней базы (meshop — и при модификаторах сверху)
    for i = 1 to faceArr.count do meshop.setFaceMatID obj faceArr[i] idArr[i]
    update obj
    true
)
global inuColSetSubs
fn inuColSetSubs mm matArr idArr = (
    -- подматериалы Multi/Sub-Object целиком (numsubs задаёт число; его
    -- чтение в Max 2026 ведёт себя странно — считаем по спискам)
    mm.numsubs = matArr.count
    for i = 1 to matArr.count do (mm.materialList[i] = matArr[i]; mm.materialIDList[i] = idArr[i])
    true
)
global inuColMakeMulti
fn inuColMakeMulti obj matArr idArr = (
    local mm = MultiMaterial numsubs:matArr.count
    inuColSetSubs mm matArr idArr
    mm.name = matArr[1].name
    obj.material = mm
    mm
)
global inuColPrevNode
global inuColNumNode
global inuColNumPts
global inuColNumTxt
global inuColNumDrawReg
if inuColNumPts == undefined do inuColNumPts = #()
if inuColNumTxt == undefined do inuColNumTxt = #()
global inuColNumDraw
fn inuColNumDraw = (
    -- цифры уровня COL на гранях у границ (центры — в системе объекта)
    local nd = inuColNumNode
    if nd != undefined and isValidNode nd and not nd.isHidden and inuColNumPts.count > 0 do (
        gw.setTransform (matrix3 1)
        local tm = nd.objecttransform
        local wx = gw.getWinSizeX()
        local wy = gw.getWinSizeY()
        for i = 1 to inuColNumPts.count do (
            local sp = gw.wTransPoint (inuColNumPts[i] * tm)
            if sp.x >= 0 and sp.y >= 0 and sp.x < wx and sp.y < wy do (
                gw.wText (sp + [1, 1, 0]) inuColNumTxt[i] color:black
                gw.wText sp inuColNumTxt[i] color:white
            )
        )
        gw.enlargeUpdateRect #whole
        gw.updateScreen()
    )
)
global inuColNumSet
fn inuColNumSet obj ptArr txtArr = (
    -- показать / убрать цифры (прежняя функция перерисовки снимается —
    -- после перезагрузки кода INU она другая)
    inuColNumNode = obj
    inuColNumPts = ptArr
    inuColNumTxt = txtArr
    if inuColNumDrawReg != undefined do try (unRegisterRedrawViewsCallback inuColNumDrawReg) catch ()
    inuColNumDrawReg = undefined
    if obj != undefined and ptArr.count > 0 do (
        registerRedrawViewsCallback inuColNumDraw
        inuColNumDrawReg = inuColNumDraw
    )
    true
)
global inuColSetPrev
fn inuColSetPrev obj = (inuColPrevNode = obj; true)
global inuPlWatchedPaint
global inuPlWatchPaint
fn inuPlWatchPaint vpMod = (
    -- смена параметров (канала) открытого VertexPaint → показ узлов
    deleteAllChangeHandlers id:#inuPlPaintParams
    inuPlWatchedPaint = vpMod
    if vpMod != undefined do
        when parameters vpMod changes id:#inuPlPaintParams do (
            try (python.execute "from inu_max.adapter import prelight_scene as inu_pl_cb; inu_pl_cb.on_paint_params()") catch ()
        )
    true
)
global inuPlLastSel
global inuPlSetLastSel
fn inuPlSetLastSel selKey = (
    -- отпечаток выделения при прошлом вызове панели Modify
    inuPlLastSel = selKey
    selKey
)
global inuPlStateGen
if inuPlStateGen == undefined do inuPlStateGen = 0
global inuPlBumpState
fn inuPlBumpState = (
    -- активный слой сменили не кнопками окна — окно перечитает состояние
    inuPlStateGen += 1
)
global inuPlLiveNodes
if inuPlLiveNodes == undefined do inuPlLiveNodes = #()
global inuPlSetLive
fn inuPlSetLive nodeArr = (
    -- узлы, показывающие канал открытого VertexPaint напрямую
    inuPlLiveNodes = nodeArr
    nodeArr.count
)
global inuPlMarkLive
fn inuPlMarkLive obj isLive = (
    -- узел начал / перестал показывать канал VertexPaint напрямую
    local i = findItem inuPlLiveNodes obj
    if isLive and i == 0 do append inuPlLiveNodes obj
    if not isLive and i > 0 do deleteItem inuPlLiveNodes i
    isLive
)
'''

# вход / выход из VertexPaint в панели Modify → Python (модуль берётся
# заново из sys.modules — переживает перезагрузку кода INU)
_CALLBACK = (
    'callbacks.removeScripts id:#inuPrelightPaint\n'
    'callbacks.addScript #modPanelObjPostChange "try (python.execute \\"from inu_max.adapter '
    'import prelight_scene as inu_pl_cb; inu_pl_cb.on_modpanel_change()\\") catch ()" '
    'id:#inuPrelightPaint\n')

_READY = []


def ensure():
    if not _READY:
        rt = _rt()
        rt.execute(_MXS)
        rt.execute(_CALLBACK)
        _READY.append(True)


_VER = []


def _plugin_version():
    if not _VER:
        try:
            _VER.append(int(_rt().execute("try (INU_FastMesh.version()) catch 0")))
        except Exception:                              # noqa: BLE001
            _VER.append(0)
    return _VER[0]


def fast():
    """Есть ли функции плагина INU для Prelight (getBakeMesh и тени).
    Проверка без побочных действий: version() (в старом плагине — только
    setNormals — её нет)."""
    return _plugin_version() >= 2


def fast_final():
    """Плагин читает канал итогового меша узла (getChannelFinal, версия 3)."""
    return _plugin_version() >= 3


def _tmp(tag):
    return os.path.join(tempfile.gettempdir(), "inu_pl_%s_%s.bin" % (tag, uuid.uuid4().hex[:8]))


def _rm(*paths):
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


def is_mesh(node):
    ensure()
    try:
        return bool(_rt().inuPlMeshNode(node))
    except Exception:                                  # noqa: BLE001
        return False


def selected_meshes():
    """Выделенные узлы с базой Editable Mesh (и прочие — отдельно)."""
    rt = _rt()
    ok, other = [], []
    for o in rt.selection:
        if get_field(o, 'preview', False) or get_field(o, 'section', '') or str(rt.classOf(o)) == 'TargetObject':
            continue
        try:
            if rt.superClassOf(o) != rt.GeometryClass:
                continue
        except Exception:                              # noqa: BLE001
            continue
        (ok if is_mesh(o) else other).append(o)
    return ok, other


# ── матрицы ──────────────────────────────────────────────────────────

def _tm_rows(tm):
    return np.array([[float(r.x), float(r.y), float(r.z)]
                     for r in (tm.row1, tm.row2, tm.row3, tm.row4)], dtype=np.float64)


def _apply(rows, pts):
    """Точки (n,3) · матрица Max (строки + позиция)."""
    return pts @ rows[:3] + rows[3]


def _apply_normals(rows, nrm):
    """Нормали (n,3): обратная-транспонированная 3×3 (как normal_matrix)."""
    m = rows[:3]
    try:
        nm = np.linalg.inv(m).T
    except np.linalg.LinAlgError:
        nm = m
    out = nrm @ nm
    ln = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.where(ln < 1e-12, 1.0, ln)


# ── геометрия для запекания ──────────────────────────────────────────

def bake_geometry(node):
    """(позиции вершин (nv,3) мир, грани (nf,3) с 0, нормали углов
    (nf,3,3) мир) базового Editable Mesh узла или None."""
    rt = _rt()
    if fast():
        path = _tmp("mesh")
        try:
            nf = int(rt.INU_FastMesh.getBakeMesh(node, path))
            if nf < 0:
                return None
            with open(path, 'rb') as f:
                nv, nf = np.frombuffer(f.read(8), dtype=np.int32)
                pos = np.frombuffer(f.read(int(nv) * 12), dtype=np.float32).reshape(-1, 3)
                faces = np.frombuffer(f.read(int(nf) * 12), dtype=np.int32).reshape(-1, 3)
                nrm = np.frombuffer(f.read(int(nf) * 36), dtype=np.float32).reshape(-1, 3)
        finally:
            _rm(path)
        rows = _tm_rows(node.objecttransform)
        pos_w = _apply(rows, pos.astype(np.float64))
        n_w = _apply_normals(rows, nrm.astype(np.float64)).reshape(-1, 3, 3)
        return pos_w.astype(np.float32), faces.astype(np.int64), n_w.astype(np.float32)
    # без плагина: MAXScript (вершины и нормали — в системе узла)
    from . import scene_read
    md = scene_read.mesh_data(node)
    rows = _tm_rows(node.transform)
    pos = np.asarray(md.verts, dtype=np.float64)
    faces = np.asarray(md.faces, dtype=np.int64)
    nrm = np.asarray(md.normals, dtype=np.float64).reshape(-1, 3)
    return (_apply(rows, pos).astype(np.float32), faces,
            _apply_normals(rows, nrm).reshape(-1, 3, 3).astype(np.float32))


# ── лампы ────────────────────────────────────────────────────────────

_TYPES = {'omnilight': 'POINT', 'directionallight': 'SUN',
          'targetdirectionallight': 'SUN', 'freespot': 'SPOT', 'targetspot': 'SPOT'}


def lights(allowed):
    """(лампы для запекания [словари], пропущенные: {причина: число}).
    Лампа учитывается, если включена, видна во вьюпорте и рендерится
    (как visible_get / hide_render в Blender), тип — в allowed. Видимые
    лампы других классов — в пропущенные с именами."""
    import math
    ensure()
    out, skipped, other = [], {}, []
    for rec in _rt().inuPlLights():
        cls, name, on, hidden, rend = str(rec[0]), str(rec[1]), bool(rec[2]), bool(rec[3]), bool(rec[4])
        if not on or hidden or not rend:
            continue
        kind = _TYPES.get(cls.lower())
        if kind is None:
            # стандартной Area-лампы в Max 2018+ нет; фотометрические (кд / лм / лк),
            # Arnold, V-Ray — свои единицы, Skylight — купол; не переводим
            other.append("%s (%s)" % (name, cls))
            continue
        if kind not in allowed:
            continue
        p, z = rec[9], rec[10]
        L = {'type': kind, 'name': name,
             'color': (float(rec[5]) / 255.0, float(rec[6]) / 255.0, float(rec[7]) / 255.0),
             'energy': float(rec[8]), 'pos': (float(p.x), float(p.y), float(p.z))}
        zv = np.array((float(z.x), float(z.y), float(z.z)))
        zn = np.linalg.norm(zv) or 1.0
        zv = zv / zn
        if kind == 'SUN':
            L['to_light'] = tuple(zv)                  # на солнце = +Z (светит вдоль −Z)
        elif kind == 'SPOT':
            L['fwd'] = tuple(-zv)
            L['cos_out'] = math.cos(math.radians(float(rec[12])) / 2.0)
            L['cos_in'] = math.cos(math.radians(float(rec[11])) / 2.0)
        out.append(L)
    if other:
        why = ("light(s) not Omni / Spot / Direct: %s%s — only those are baked; sky, "
               "photometric and renderer (Arnold, V-Ray…) lights are not converted"
               % (", ".join(other[:5]), ", …" if len(other) > 5 else ""))
        skipped[why] = len(other)
    return out, skipped


def env_source():
    """Окружение сцены для «HDRI» (как _world_env_sample Blender): карта
    окружения — Bitmap со Spherical Environment (equirect, как HDRI мира
    Blender), иначе цвет фона. (источник | None, [сообщения]).
    Источник: {'color': (r,g,b)} или {'path', 'u_offset', 'level',
    'offset', 'amount'}."""
    rt = _rt()
    notes = []
    m = None
    try:
        if rt.useEnvironmentMap:
            m = rt.environmentMap
    except Exception:                                  # noqa: BLE001
        m = None
    if m is not None:
        try:
            ok = (rt.classOf(m) == rt.Bitmaptexture and int(m.coords.mappingType) == 1
                  and int(m.coords.mapping) == 0)
            path = str(m.fileName or '') if ok else ''
        except Exception:                              # noqa: BLE001
            ok, path = False, ''
        if ok and path and os.path.isfile(path):
            c, o = m.coords, m.output
            ignored = [n for n, v, d in (('W Angle', c.W_Angle, 0.0), ('V Offset', c.V_Offset, 0.0),
                                         ('U Tiling', c.U_Tiling, 1.0), ('V Tiling', c.V_Tiling, 1.0))
                       if abs(float(v) - d) > 1e-6]
            if ignored:
                notes.append("Environment map: %s not used (only U Offset rotates the map)"
                             % ", ".join(ignored))
            return dict(path=path, u_offset=float(c.U_Offset), level=float(o.rgb_level),
                        offset=float(o.RGB_Offset), amount=float(o.Output_Amount)), notes
        notes.append("The environment map is not a Bitmap with Spherical Environment mapping "
                     "(or the file is missing) — the background colour is used")
    try:
        c = rt.backgroundColor
        return {'color': (float(c.r) / 255.0, float(c.g) / 255.0, float(c.b) / 255.0)}, notes
    except Exception:                                  # noqa: BLE001
        return None, notes


# Строки картинки окружения, прочитанные за запекание: {'key', 'bm', 'rows'}.
# getPixels 2048 пикселей ≈ 3.4 мс — читаются только нужные строки.
_ENV = {}


def env_sample(src, dirs):
    """(n,3) вклад окружения по направлениям dirs (мировые нормали углов):
    цвет фона — всем, карта — пиксель по направлению (nearest, значения
    getPixels без перевода в линейное — как image.pixels Blender) × Output."""
    from ..ops import prelight_math as PM
    n = len(dirs)
    if 'color' in src:
        return np.tile(np.asarray(src['color'], dtype=np.float32), (n, 1))
    rt = _rt()
    key = (src['path'], os.path.getmtime(src['path']))
    if _ENV.get('key') != key:
        env_release()
        _ENV.update(key=key, bm=rt.openBitMap(src['path']), rows={})
    bm, rows = _ENV['bm'], _ENV['rows']
    w, h = int(bm.width), int(bm.height)
    iy, ix = PM.env_pixel_index(dirs, w, h, src['u_offset'])
    for y in np.unique(iy):
        y = int(y)
        if y not in rows:
            px = rt.getPixels(bm, rt.Point2(0, y), w, linear=False)
            rows[y] = np.array([(c.r, c.g, c.b) for c in px], dtype=np.float32) / 255.0
    rgb = np.empty((n, 3), dtype=np.float32)
    for y in np.unique(iy):
        sel = iy == y
        rgb[sel] = rows[int(y)][ix[sel]]
    return PM.env_output(rgb, src['level'], src['offset'], src['amount'])


def env_release():
    bm = _ENV.get('bm')
    _ENV.clear()
    if bm is not None:
        try:
            _rt().close(bm)
        except Exception:                              # noqa: BLE001
            pass


# ── тени ─────────────────────────────────────────────────────────────

def occlusion_begin():
    """BVH видимой геометрии сцены (геометрия, не скрытая во вьюпорте).
    Число треугольников."""
    rt = _rt()
    nodes = []
    for o in rt.geometry:
        if get_field(o, 'preview', False) or get_field(o, 'section', '') or str(rt.classOf(o)) == 'TargetObject':
            continue
        try:
            if not o.isHiddenInVpt:
                nodes.append(o)
        except Exception:                              # noqa: BLE001
            continue
    return int(rt.INU_FastMesh.occlusionBegin(nodes))


def occlusion_end():
    try:
        _rt().INU_FastMesh.occlusionEnd()
    except Exception:                                  # noqa: BLE001
        pass


def occluded(rays):
    """rays (n,7) float32 → (n,) bool: луч перекрыт."""
    if len(rays) == 0:
        return np.zeros(0, dtype=bool)
    inp, outp = _tmp("rays"), _tmp("hits")
    try:
        np.ascontiguousarray(rays, dtype=np.float32).tofile(inp)
        n = int(_rt().INU_FastMesh.occlusionTest(inp, outp))
        if n != len(rays):
            raise RuntimeError("occlusionTest: %d of %d rays" % (n, len(rays)))
        return np.fromfile(outp, dtype=np.uint8).astype(bool)
    finally:
        _rm(inp, outp)


# ── каналы цвета ─────────────────────────────────────────────────────

def _has_modifiers(node):
    try:
        return int(node.modifiers.count) > 0
    except Exception:                                  # noqa: BLE001
        return False


def get_corners(node, chan):
    """Значения канала на угол (nf·3, 3) или None, если канала нет. Канал
    ИТОГОВОГО меша узла (база + модификаторы, напр. мазки VertexPaint) —
    как его видит экспорт; без модификаторов итог = база."""
    rt = _rt()
    mods = _has_modifiers(node)
    if fast() and (not mods or fast_final()):
        path = _tmp("chan")
        try:
            fn = rt.INU_FastMesh.getChannelFinal if mods else rt.INU_FastMesh.getChannel
            nf = int(fn(node, int(chan), path))
            if nf < 0:
                return None
            with open(path, 'rb') as f:
                nmv, nf = np.frombuffer(f.read(8), dtype=np.int32)
                mv = np.frombuffer(f.read(int(nmv) * 12), dtype=np.float32).reshape(-1, 3)
                mf = np.frombuffer(f.read(int(nf) * 12), dtype=np.int32).reshape(-1, 3)
        finally:
            _rm(path)
    else:
        # meshop на узле читает итоговый меш (с модификаторами)
        ensure()
        res = rt.inuPlGetChannel(node, int(chan))
        if res is None:
            return None
        mv = np.array(list(res[0]), dtype=np.float32).reshape(-1, 3)
        mf = np.array(list(res[1]), dtype=np.int64).reshape(-1, 3) - 1
    if len(mv) == 0:
        return np.zeros((len(mf) * 3, 3), dtype=np.float32)
    return mv[np.clip(mf, 0, len(mv) - 1)].reshape(-1, 3)


def _write(node, chan, faces, values, fill=None):
    """Сырая запись канала (без обновления копий превью): значения на угол
    или один цвет fill на все углы."""
    ensure()
    rt = _rt()
    if fill is not None:
        rt.inuPlSetChannel(node, int(chan), [float(v) for v in fill],
                           [1] * (int(node.numfaces) * 3))
        return
    from ..ops.prelight_math import dedupe_corners
    verts, mfaces = dedupe_corners(faces, values)
    rt.inuPlSetChannel(node, int(chan), [float(x) for x in verts.reshape(-1)],
                       [int(i) + 1 for i in mfaces.reshape(-1)])


def _sync_views(node, chan):
    """После записи слоя / альфы — обновить их копии превью (если включены)."""
    if chan in (0, -1) and has_channel(node, PREVIEW_CHAN) \
            and LAYER_CHAN.get(active_layer(node)) == chan:
        _copy_view(node)
    if chan == ALPHA_CHAN and has_channel(node, ALPHA_VIEW_CHAN):
        _copy_alpha_view(node)


def set_corners(node, chan, faces, values):
    """Записать канал из значений на угол: одна вершина канала на пару
    (вершина, цвет). Копии превью этого канала обновляются."""
    _write(node, chan, faces, values)
    _sync_views(node, chan)


def has_channel(node, chan):
    try:
        return bool(_rt().meshop.getMapSupport(node, int(chan)))
    except Exception:                                  # noqa: BLE001
        return False


def fill_channel(node, chan, rgb):
    """Канал одного цвета (одна вершина канала на все углы)."""
    _write(node, chan, None, None, fill=rgb)
    _sync_views(node, chan)


def drop_channel(node, chan):
    ensure()
    try:
        return bool(_rt().inuPlDropChannel(node, int(chan)))
    except Exception:                                  # noqa: BLE001
        return False


def face_count(node):
    try:
        return int(node.numfaces)
    except Exception:                                  # noqa: BLE001
        return 0


def faces_of(node):
    """Грани (nf,3) с 0 — для записи канала по значениям на угол."""
    rt = _rt()
    if fast():
        path = _tmp("mesh")
        try:
            nf = int(rt.INU_FastMesh.getBakeMesh(node, path))
            if nf < 0:
                return None
            with open(path, 'rb') as f:
                nv, nf = np.frombuffer(f.read(8), dtype=np.int32)
                f.seek(8 + int(nv) * 12)
                return np.frombuffer(f.read(int(nf) * 12), dtype=np.int32).reshape(-1, 3).astype(np.int64)
        finally:
            _rm(path)
    from . import scene_read
    return np.asarray(scene_read.mesh_data(node).faces, dtype=np.int64)


# ── активный слой и поля V ────────────────────────────────────────────

def active_layer(node):
    v = get_field(node, 'prelight_active', 'Day')
    return v if v in LAYER_CHAN else 'Day'


def set_active_layer(nodes, name):
    put_field(nodes, 'prelight_active', name)


def v_value(node, layer):
    return float(get_prop(node, 'v_offset_' + layer.lower(), 0.0))


def v_applied(node, layer):
    return float(get_prop(node, 'v_applied_' + layer.lower(), 0.0))


def set_v(nodes, layer, value=None, applied=None):
    if value is not None:
        set_prop(nodes, 'v_offset_' + layer.lower(), float(value))
    if applied is not None:
        set_prop(nodes, 'v_applied_' + layer.lower(), float(applied))


# ── лампы Prelight (8 точек и солнце) ────────────────────────────────

def _layer_nodes(name):
    ensure()
    try:
        return list(_rt().inuPlLayerNodes(name))
    except Exception:                                  # noqa: BLE001
        return []


def lights_state():
    """(есть 8 ламп, есть солнце)."""
    rt = _rt()
    return bool(_layer_nodes(LIGHTS_LAYER)), rt.getNodeByName(SUN_NAME) is not None


def rig_center():
    """Центр для ламп: центр выделенного меша (как центр bbox активного
    объекта в INU), иначе 0,0,0."""
    rt = _rt()
    for o in rt.selection:
        try:
            if rt.superClassOf(o) == rt.GeometryClass:
                c = o.center
                return (float(c.x), float(c.y), float(c.z))
        except Exception:                              # noqa: BLE001
            continue
    return (0.0, 0.0, 0.0)


def _to_layer(nodes, name):
    rt = _rt()
    lay = rt.LayerManager.getLayerFromName(name) or rt.LayerManager.newLayerFromName(name)
    for n in nodes:
        lay.addNode(n)


def _delete_layer(name):
    rt = _rt()
    nodes = _layer_nodes(name)
    if nodes:
        rt.delete(nodes)
    try:
        rt.LayerManager.deleteLayerByName(name)
    except Exception:                                  # noqa: BLE001
        pass


def create_lights(center, distance=100.0, rig=None):
    """8 ламп Omni (цвет #BCBCBC, множитель = энергия INU) на слое
    Prelight_Lights. rig — [(имя, смещение, rgb, энергия)] из пресета."""
    rt = _rt()
    _delete_layer(LIGHTS_LAYER)
    made = []
    cx, cy, cz = center
    items = rig or [(n, (d[0] * distance, d[1] * distance, d[2] * distance),
                     (LAMP_RGB,) * 3, e) for n, d, e in LIGHTS8]
    for name, off, rgb, energy in items:
        lamp = rt.Omnilight(name=name, rgb=rt.color(*rgb), multiplier=float(energy),
                            pos=rt.Point3(cx + off[0], cy + off[1], cz + off[2]))
        made.append(lamp)
    _to_layer(made, LIGHTS_LAYER)
    return made


def remove_lights():
    had = bool(_layer_nodes(LIGHTS_LAYER))
    _delete_layer(LIGHTS_LAYER)
    return had


def lights_snapshot():
    """Лампы слоя Prelight_Lights для пресета: [(имя, смещение от их
    среднего, rgb, энергия)]."""
    nodes = [o for o in _layer_nodes(LIGHTS_LAYER)
             if _TYPES.get(str(_rt().classOf(o)).lower())]
    if not nodes:
        return []
    pts = np.array([[float(o.pos.x), float(o.pos.y), float(o.pos.z)] for o in nodes])
    mean = pts.mean(axis=0)
    out = []
    for o, p in zip(nodes, pts):
        c = o.rgb
        out.append((str(o.name), tuple(float(v) for v in (p - mean)),
                    (float(c.r), float(c.g), float(c.b)), float(o.multiplier)))
    return out


def create_sun(center, energy=9.0):
    """«Солнце» Prelight: направленная лампа под углом «сверху-спереди»
    (rotation_euler (50°, 0, 40°) INU), цвет #BCBCBC, слой Prelight_Sun."""
    from ..ops.prelight_math import sun_rows
    rt = _rt()
    remove_sun()
    r = sun_rows()
    cx, cy, cz = center
    sun = rt.Directionallight(name=SUN_NAME, rgb=rt.color(LAMP_RGB, LAMP_RGB, LAMP_RGB),
                              multiplier=float(energy))
    sun.transform = rt.Matrix3(rt.Point3(*r[0]), rt.Point3(*r[1]), rt.Point3(*r[2]),
                               rt.Point3(cx, cy, cz + 100.0))
    _to_layer([sun], SUN_LAYER)
    return sun


def remove_sun():
    rt = _rt()
    sun = rt.getNodeByName(SUN_NAME)
    if sun is None:
        return False
    rt.delete(sun)
    if not _layer_nodes(SUN_LAYER):
        try:
            rt.LayerManager.deleteLayerByName(SUN_LAYER)
        except Exception:                              # noqa: BLE001
            pass
    return True


# ── превью: цвета вершин во вьюпорте ─────────────────────────────────
# Вьюпорт Max НЕ показывает цвет вершин, смешанный с текстурой через
# материал (карта Vertex_Color запекается для вьюпорта по UV — выходит
# красно-зелёный перелив; смешивание работает только при рендере). Поэтому
# превью — штатный показ цвета вершин объекта (Vertex Channel Display) без
# текстуры: активный слой с коррекцией превью (формулы узлов Blender:
# Bright/Contrast, Gamma, Hue/Saturation) копируется в канал PREVIEW_CHAN,
# объект показывает этот канал без освещения — как prelight в игре.
# Превью альфы — канал ALPHA_VIEW_CHAN (копия -2, серым). Материалы не
# меняются; экспорт DFF каналы 98 / 99 не пишет. Запись слоя / альфы
# обновляет копию сама (set_corners / fill_channel).

PREVIEW_CHAN = 99
ALPHA_VIEW_CHAN = 98
COL_VIEW_CHAN = 97                  # превью COL Light (зелёный по уровню)


def _view_settings():
    from .. import settings
    g = settings.get
    return (float(g('prelight_view_bright', 0.004)), float(g('prelight_view_contrast', 0.0)),
            float(g('prelight_view_gamma', 1.0)), float(g('prelight_view_saturation', 1.0)))


def redraw():
    """Полная перерисовка вьюпортов: новый показ цвета вершин (свойства
    узла, канал превью) иначе виден только после поворота вида."""
    try:
        _rt().completeRedraw()
    except Exception:                                  # noqa: BLE001
        pass


def update_display(node):
    """Показ цвета вершин узла: открыт его VertexPaint активного слоя при
    включённом превью — этот канал напрямую (мазки видны сразу); иначе
    превью альфы, иначе превью слоя, иначе показ выключен (и при открытом
    VertexPaint — как кнопка Disable Vertex Color Display его Paintbox)."""
    rt = _rt()
    ensure()
    if has_channel(node, COL_VIEW_CHAN):         # превью COL Light — главнее всего
        try:
            rt.inuPlMarkLive(node, False)
            node.vertexColorType = rt.Name('map_channel')
            node.vertexColorMapChannel = COL_VIEW_CHAN
            node.vertexColorsShaded = True       # с освещением — видна форма
            node.showVertexColors = True
        except Exception as e:                   # noqa: BLE001
            print("[INU prelight] display %s: %r" % (node.name, e))
        return
    live = _live_channel(node, _paint_current())
    ch = ALPHA_VIEW_CHAN if has_channel(node, ALPHA_VIEW_CHAN) else (
        PREVIEW_CHAN if has_channel(node, PREVIEW_CHAN) else None)
    try:
        # учёт узлов с прямым показом — чтобы при выходе из VertexPaint
        # вернуть их к превью (_sync_live), кто бы ни включил показ
        rt.inuPlMarkLive(node, live is not None)
    except Exception:                                  # noqa: BLE001
        pass
    try:
        if live is not None:
            node.vertexColorType = rt.Name(PAINT_VIEW[live])
            node.vertexColorsShaded = False
            node.showVertexColors = True
            return
        if ch is None:
            node.showVertexColors = False
            return
        node.vertexColorType = rt.Name('map_channel')
        node.vertexColorMapChannel = ch
        node.vertexColorsShaded = False
        node.showVertexColors = True
    except Exception as e:                             # noqa: BLE001
        print("[INU prelight] display %s: %r" % (node.name, e))


def nodes_with(chan):
    """Меши сцены с каналом chan (одним вызовом MAXScript)."""
    ensure()
    try:
        return list(_rt().inuPlNodesWith(int(chan)))
    except Exception:                                  # noqa: BLE001
        return []


def preview_on(node):
    return has_channel(node, PREVIEW_CHAN)


def _copy_view(node, view=None):
    """Активный слой (или белый, если его нет) с коррекцией → канал превью."""
    from ..ops.prelight_math import view_correct
    chan = LAYER_CHAN[active_layer(node)]
    vals = get_corners(node, chan)
    faces = faces_of(node) if vals is not None else None
    if vals is None or faces is None or len(faces) * 3 != len(vals):
        _write(node, PREVIEW_CHAN, None, None, fill=(1.0, 1.0, 1.0))
    else:
        _write(node, PREVIEW_CHAN, faces, view_correct(vals, *(view or _view_settings())))


def refresh_preview(nodes):
    """Обновить копию слоя у узлов с включённым превью."""
    for node in nodes:
        if has_channel(node, PREVIEW_CHAN):
            _copy_view(node)
            update_display(node)


def set_preview(nodes, enable, view=None):
    """Включить / выключить превью цвета вершин у узлов. Число узлов."""
    n = 0
    for node in nodes:
        if enable:
            _copy_view(node, view)
            n += 1
        elif drop_channel(node, PREVIEW_CHAN):
            n += 1
        update_display(node)
    return n


def update_view_all(view=None):
    """Новая коррекция превью — всем узлам с включённым превью."""
    nodes = nodes_with(PREVIEW_CHAN)
    for node in nodes:
        _copy_view(node, view)
    if nodes:
        redraw()
    return len(nodes)


# ── превью альфы ─────────────────────────────────────────────────────

def alpha_nodes():
    """Узлы сцены (Editable Mesh) с непрозрачностью < 0.999 в канале -2."""
    out = []
    for o in nodes_with(ALPHA_CHAN):
        a = get_corners(o, ALPHA_CHAN)
        if a is not None and len(a) and float(a[:, 0].min()) < 0.999:
            out.append(o)
    return out


def _copy_alpha_view(node):
    vals = get_corners(node, ALPHA_CHAN)
    faces = faces_of(node) if vals is not None else None
    if vals is None or faces is None or len(faces) * 3 != len(vals):
        _write(node, ALPHA_VIEW_CHAN, None, None, fill=(1.0, 1.0, 1.0))
    else:
        _write(node, ALPHA_VIEW_CHAN, faces, vals)


def set_alpha_preview(enable):
    """Альфа вершин серым во вьюпорте (все модели сцены с альфой). Число
    узлов."""
    if enable:
        nodes = alpha_nodes()
        for node in nodes:
            _copy_alpha_view(node)
            update_display(node)
        return len(nodes)
    nodes = nodes_with(ALPHA_VIEW_CHAN)
    for node in nodes:
        drop_channel(node, ALPHA_VIEW_CHAN)
        update_display(node)
    return len(nodes)


def alpha_preview_on():
    return bool(nodes_with(ALPHA_VIEW_CHAN))


# ── VertexPaint (перекраска слоя) ────────────────────────────────────
# Модификатор VertexPaint пользователь добавляет сам, если хочет перекрасить
# слой (Vertex Color — Day, Vertex Illum — Night, Vertex Alpha — альфа).
# Мазки хранятся в модификаторе поверх базы, экспорт берёт итог. Инструменты
# INU перед работой вписывают мазки слоя в базу (итог → база, VertexPaint —
# пустой на том же месте).
# Кнопки Day / Night: у слоя есть свой VertexPaint — он становится текущим в
# панели Modify (слой — из модификатора, мазки видны сразу); нет — открытый
# VertexPaint другого слоя закрывается (слой — из скрипта: превью). Узел
# показывает канал напрямую, только пока открыт VertexPaint его активного
# слоя (или альфы); открыли в стеке VertexPaint другого слоя (или сменили в
# нём канал) — активным становится его слой. Вышли — копии превью из итога.

PAINT_VIEW = {0: 'color', -1: 'illum', -2: 'alpha'}
_BUSY = []                          # свои изменения стека — без обратного вызова


def paint_mods(node, chan):
    """VertexPaint узла, рисующие в канал chan."""
    ensure()
    try:
        return list(_rt().inuPlPaintMods(node, int(chan)))
    except Exception:                                  # noqa: BLE001
        return []


def _anim(m):
    return int(_rt().getHandleByAnim(m))


def _has_mod(node, h):
    return any(_anim(m) == h for m in node.modifiers)


def _same(a, b):
    """Один и тот же модификатор (удалённый — нет)."""
    try:
        return a is not None and b is not None and _anim(a) == _anim(b)
    except Exception:                                  # noqa: BLE001
        return False


def absorb_paint(nodes, chan, readd=True):
    """Вписать мазки VertexPaint канала chan в базу: итог канала → база,
    VertexPaint — пустой на том же месте (readd) или удалить. Возвращает
    (число узлов, имена пропущенных: модификаторы меняют число граней)."""
    rt = _rt()
    hit = [n for n in nodes if paint_mods(n, chan)]
    if not hit:
        return 0, []
    done, skipped = [], []
    _BUSY.append(True)
    try:
        for n in hit:
            vals = get_corners(n, chan)
            faces = faces_of(n) if vals is not None else None
            if vals is not None and (faces is None or len(faces) * 3 != len(vals)):
                skipped.append(str(n.name))
                continue
            if vals is not None:
                _write(n, chan, faces, vals)
            done.append(n)
        if done:
            cur = rt.inuPlReplacePaint(done, int(chan), bool(readd))[0]
            if cur is not None:
                _set_current(cur)
    finally:
        _BUSY.pop()
    return len(done), skipped


def _set_current(mod):
    """Модификатор — текущим в панели Modify, выделение прежнее. Без node:
    modPanel.setCurrentObject выделяет ОДИН из узлов модификатора — у
    общего экземпляра это может быть другая модель; при повторном выделении
    нескольких текущим становится верхний общий (проверено в Max 2026)."""
    rt = _rt()
    sel = list(rt.selection)
    h = _anim(mod)
    owner = next((n for n in sel if _has_mod(n, h)), None)
    if owner is None:
        return False
    try:
        rt.execute("max modify mode")
        rt.modPanel.setCurrentObject(mod, node=owner)
        if len(sel) > 1:
            rt.select(sel)
        return True
    except Exception:                                  # noqa: BLE001
        return False


def drop_paint(nodes, chan):
    """Удалить VertexPaint канала chan (слой убирается вместе с мазками).
    Число удалённых."""
    ensure()
    _BUSY.append(True)
    try:
        return int(_rt().inuPlReplacePaint(list(nodes), int(chan), False)[1])
    except Exception:                                  # noqa: BLE001
        return 0
    finally:
        _BUSY.pop()


def _open_modifier():
    """VertexPaint, открытый в панели Modify (любой канал), или None."""
    rt = _rt()
    try:
        if str(rt.getCommandPanelTaskMode()) != 'modify':
            return None
        cur = rt.modPanel.getCurrentObject()
        return cur if cur is not None and rt.classOf(cur) == rt.VertexPaint else None
    except Exception:                                  # noqa: BLE001
        return None


def _paint_current():
    """Открытый VertexPaint канала слоя (0 / -1 / -2) или None."""
    cur = _open_modifier()
    try:
        return cur if cur is not None and int(cur.mapChannel) in PAINT_VIEW else None
    except Exception:                                  # noqa: BLE001
        return None


def _live_channel(node, cur):
    """Канал, который узел показывает напрямую: открыт его VertexPaint
    активного слоя (или альфы) и включено превью — глаз слоя (альфы —
    Vertex alpha). Глаз выключен — цвета вершин не показываются и при
    открытом VertexPaint; VertexPaint другого слоя — превью."""
    if cur is None:
        return None
    try:
        if not (node.isSelected and _has_mod(node, _anim(cur))):
            return None
        ch = int(cur.mapChannel)
        if ch == ALPHA_CHAN:
            return ch if has_channel(node, ALPHA_VIEW_CHAN) else None
        if LAYER_CHAN.get(active_layer(node)) != ch or not has_channel(node, PREVIEW_CHAN):
            return None
        return ch
    except Exception:                                  # noqa: BLE001
        return None


def _layer_of(chan):
    return next((layer for layer, c in LAYER_CHAN.items() if c == chan), None)


def _follow_layer(vp):
    """Открыт VertexPaint слоя (выбран в стеке / сменён канал) — активным у
    выделенных узлов с ним становится его слой; окно перечитает кнопки."""
    rt = _rt()
    try:
        layer = _layer_of(int(vp.mapChannel))
        if layer is None:
            return
        h = _anim(vp)
        nodes = [n for n in rt.selection if is_mesh(n) and _has_mod(n, h)
                 and active_layer(n) != layer]
    except Exception:                                  # noqa: BLE001
        return
    if nodes:
        set_active_layer(nodes, layer)
        rt.inuPlBumpState()


def state_gen():
    """Счётчик смен активного слоя не кнопками окна (окно сверяет его)."""
    try:
        return int(_rt().inuPlStateGen)
    except Exception:                                  # noqa: BLE001
        return 0


def show_layer(nodes, chan):
    """Кнопки Day / Night при VertexPaint (один выделенный объект): у слоя
    есть свой VertexPaint — он текущим в панели Modify (слой из
    модификатора). Нет — панель не трогаем: открытый VertexPaint другого
    слоя не показывается напрямую (_live_channel), слой — из скрипта
    (превью). Базу текущей НЕ делаем: тогда Max выключает Show End Result и
    итог (превью, экспорт DFF) считается без модификаторов — мазки теряются
    (проверено в Max 2026). У нескольких объектов текущим может быть только
    верхний общий модификатор (setCurrentObject оставил бы один объект) —
    там показ тоже решает активный слой. Текст для отчёта."""
    rt = _rt()
    ensure()
    note = ""
    if len(nodes) == 1:
        n = nodes[0]
        mods = paint_mods(n, chan)
        if mods:
            note = " (from VertexPaint)"
            _BUSY.append(True)
            try:
                if not _same(_open_modifier(), mods[0]):
                    rt.execute("max modify mode")
                    rt.modPanel.setCurrentObject(mods[0], node=n)
            except Exception as e:                     # noqa: BLE001
                print("[INU prelight] VertexPaint switch: %r" % (e,))
            finally:
                _BUSY.pop()
    on_modpanel_change()
    return note


def _sync_live():
    """Узлы открытого VertexPaint — показ канала напрямую; узлы, которые
    так показывали раньше, — копии превью из итога и обычный показ."""
    rt = _rt()
    cur = _paint_current()
    now = [n for n in rt.selection if cur is not None and is_mesh(n)
           and _live_channel(n, cur) is not None]
    keep = {int(n.inode.handle) for n in now}
    changed = bool(now)
    for n in list(rt.inuPlLiveNodes or []):
        if not rt.isValidNode(n) or int(n.inode.handle) in keep:
            continue
        if has_channel(n, PREVIEW_CHAN):
            _copy_view(n)
        if has_channel(n, ALPHA_VIEW_CHAN):
            _copy_alpha_view(n)
        update_display(n)
        changed = True
    for n in now:
        update_display(n)
    rt.inuPlSetLive(now)
    if changed:
        redraw()


def on_modpanel_change():
    """Обратный вызов #modPanelObjPostChange: вход / выход из VertexPaint;
    слежение за параметрами (каналом) открытого VertexPaint. Выделение то
    же, а открыт другой VertexPaint слоя (выбран в стеке) — его слой
    активный; при смене выделения Max сам открывает верхний модификатор —
    тогда активный слой не трогаем."""
    if _BUSY:
        return
    rt = _rt()
    _BUSY.append(True)
    try:
        ensure()
        opened = _open_modifier()
        watched = rt.execute("inuPlWatchedPaint")      # снимок (rt.<глобал> — живая ссылка)
        sel_key = ",".join(str(int(n.inode.handle)) for n in rt.selection)
        same_sel = sel_key == (rt.inuPlLastSel or "")
        rt.inuPlSetLastSel(sel_key)
        if not ((opened is None and watched is None) or _same(opened, watched)):
            rt.inuPlWatchPaint(opened)
            if opened is not None and same_sel:
                _follow_layer(opened)
        _sync_live()
    except Exception as e:                             # noqa: BLE001
        print("[INU prelight] VertexPaint view: %r" % (e,))
    finally:
        _BUSY.pop()


def on_paint_params():
    """Параметры открытого VertexPaint изменились (например, канал Vertex
    Color → Vertex Illum) — показ узлов следует за ним."""
    if _BUSY:
        return
    _BUSY.append(True)
    try:
        opened = _open_modifier()
        if opened is not None:
            _follow_layer(opened)
        _sync_live()
    except Exception as e:                             # noqa: BLE001
        print("[INU prelight] VertexPaint view: %r" % (e,))
    finally:
        _BUSY.pop()


# ── следы прошлой версии превью (0.20.0) ─────────────────────────────
# Материал: diffuse / прозрачность были обёрнуты в RGB_Multiply «INU_Prelight»
# / «INU_AlphaView» (map1 — исходная карта). Каналы: meshop.setNumMaps 100
# включал каналы 0..98 (UV2 — позициями вершин).

_LEGACY_WRAPPERS = (('diffuseMap', "INU_Prelight"), ('opacityMap', "INU_AlphaView"))


def repair_legacy():
    """Снять обёртки материалов и лишние каналы прошлой версии превью во
    всей сцене. Возвращает (снято обёрток, исправлено узлов)."""
    rt = _rt()
    wraps = 0
    for m in list(rt.sceneMaterials):
        try:
            subs = list(m.materialList) if rt.classOf(m) == rt.MultiMaterial else [m]
        except Exception:                              # noqa: BLE001
            continue
        for s in subs:
            for prop, name in _LEGACY_WRAPPERS:
                try:
                    tm = getattr(s, prop)
                    if tm is not None and rt.classOf(tm) == rt.RGB_Multiply and str(tm.name) == name:
                        setattr(s, prop, tm.map1)
                        wraps += 1
                except Exception:                      # noqa: BLE001
                    continue
    ensure()
    try:
        nodes = int(rt.inuPlRepairScene())
    except Exception as e:                             # noqa: BLE001
        print("[INU prelight] repair channels: %r" % (e,))
        nodes = 0
    return wraps, nodes


# ── часть 2: инструменты (выделение граней, материалы, «Объединить») ──

def local_geometry(node):
    """(позиции вершин (nv,3) в системе объекта, грани (nf,3) с 0) базового
    Editable Mesh узла — как mesh.vertices.co Blender — или None."""
    rt = _rt()
    if fast():
        path = _tmp("mesh")
        try:
            nf = int(rt.INU_FastMesh.getBakeMesh(node, path))
            if nf < 0:
                return None
            with open(path, 'rb') as f:
                nv, nf = np.frombuffer(f.read(8), dtype=np.int32)
                pos = np.frombuffer(f.read(int(nv) * 12), dtype=np.float32).reshape(-1, 3)
                faces = np.frombuffer(f.read(int(nf) * 12), dtype=np.int32).reshape(-1, 3)
        finally:
            _rm(path)
        return pos.astype(np.float64), faces.astype(np.int64)
    from . import scene_read
    md = scene_read.mesh_data(node)
    return np.asarray(md.verts, dtype=np.float64), np.asarray(md.faces, dtype=np.int64)


def selected_faces(node):
    """Выделенные грани базы (с 0) — «выделение в Edit Mode» Blender."""
    ensure()
    try:
        return np.asarray(list(_rt().inuPlFaceSel(node)), dtype=np.int64) - 1
    except Exception:                                  # noqa: BLE001
        return np.zeros(0, dtype=np.int64)


def face_matids(node):
    """ID материала каждой грани базы (как в Max, с 1)."""
    ensure()
    return np.asarray(list(_rt().inuPlFaceMatIDs(node)), dtype=np.int64)


def material_slots(node):
    """Материалы узла для «Листвы»: [(имя, ID граней)]; ID None — один
    материал на весь меш (все грани)."""
    rt = _rt()
    try:
        m = node.material
        if m is None:
            return []
        if rt.classOf(m) == rt.MultiMaterial:
            return [(str(s.name), int(i)) for i, s in zip(list(m.materialIDList), list(m.materialList))
                    if s is not None]
        return [(str(m.name), None)]
    except Exception:                                  # noqa: BLE001
        return []


def paint_color():
    """Цвет кисти VertexPaint (0..1, как пишет кисть), если VertexPaint
    открыт в панели Modify, иначе None."""
    if _open_modifier() is None:
        return None
    try:
        c = _rt().VertexPaintTool().paintColor
        return (float(c.r) / 255.0, float(c.g) / 255.0, float(c.b) / 255.0)
    except Exception:                                  # noqa: BLE001
        return None


def scene_meshes():
    """Все узлы сцены с базой Editable Mesh."""
    ensure()
    return list(_rt().inuPlSceneMeshes())


def node_handle(node):
    return int(node.inode.handle)


def foliage_backup():
    """Снимки слоя до «Bake color» (для «Reset»): {handle: (канал, значения,
    число граней)}. Живут до закрытия Max — как в Blender (память), и
    переживают перезагрузку кода INU при открытии окна."""
    import sys
    store = getattr(sys, '_inu_foliage_backup', None)
    if store is None:
        store = {}
        sys._inu_foliage_backup = store
    return store


# «Объединить / Разъединить» (как в Blender: кисть красит один объект —
# временная общая модель из КОПИЙ выделенных мешей в мировых координатах,
# оригиналы скрыты; «Разъединить» переносит Day / Night обратно по
# диапазонам граней и удаляет модель). Диапазоны — в user property модели
# «handle:первая грань:число граней;…» (handle узла переживает сохранение).

MERGE_NAME = "Prelight_Merge"
MERGE_KEY = 'prelight_merge'


def merge_proxy():
    ensure()
    try:
        return _rt().inuPlMergeProxy()
    except Exception:                                  # noqa: BLE001
        return None


def _sub_of(mm_ids, n_subs, mat_id):
    """Индекс подматериала мульти-материала для ID грани."""
    if mat_id in mm_ids:
        return mm_ids.index(mat_id)
    return (mat_id - 1) % max(1, n_subs)


def merge_build(nodes):
    """Собрать временную модель. Возвращает (узел, число мешей, пропущенные
    имена). Мазки VertexPaint слоёв оригиналов сперва вписываются."""
    from . import scene_build
    rt = _rt()
    ensure()
    scene_build._ensure()
    verts, faces_all, mats_all, uv, day, night = [], [], [], [], [], []
    normals = []
    global_mats, mat_key = [], {}
    ranges, skipped, used = [], [], []
    v_off = f_off = 0
    for node in nodes:
        for chan in (0, -1):
            absorb_paint([node], chan)
        geo = bake_geometry(node)
        if geo is None or len(geo[1]) == 0:
            skipped.append(str(node.name))
            continue
        pos, faces, n_c = geo
        nf = len(faces)
        chans = [get_corners(node, c) for c in (1, 0, -1)]
        if any(c is not None and len(c) != nf * 3 for c in chans):
            skipped.append(str(node.name))            # модификаторы меняют число граней
            continue
        uv1, d, n = chans
        white = np.ones((nf * 3, 3), dtype=np.float32)
        uv.append(uv1 if uv1 is not None else np.zeros((nf * 3, 3), dtype=np.float32))
        day.append(d if d is not None else white)
        night.append(n if n is not None else white)
        # материалы → общий список (текстуры видны на модели)
        m = node.material
        ids = face_matids(node)
        if m is not None and rt.classOf(m) == rt.MultiMaterial:
            subs = list(m.materialList)
            mm_ids = [int(i) for i in m.materialIDList]
            local = []
            for s in subs:
                key = int(rt.getHandleByAnim(s)) if s is not None else 0
                if s is not None and key not in mat_key:
                    mat_key[key] = len(global_mats)
                    global_mats.append(s)
                local.append(mat_key.get(key, 0))
            gid = np.array([local[_sub_of(mm_ids, len(subs), int(i))] for i in ids.tolist()])
        elif m is not None:
            key = int(rt.getHandleByAnim(m))
            if key not in mat_key:
                mat_key[key] = len(global_mats)
                global_mats.append(m)
            gid = np.full(nf, mat_key[key])
        else:
            gid = np.zeros(nf, dtype=np.int64)
        verts.append(pos)
        faces_all.append(faces + v_off)
        mats_all.append(gid + 1)
        normals.append(n_c.reshape(-1, 3))
        ranges.append("%d:%d:%d" % (node_handle(node), f_off, nf))
        used.append(node)
        v_off += len(pos)
        f_off += nf
    if not used:
        return None, 0, skipped
    pos = np.concatenate(verts)
    faces = np.concatenate(faces_all)
    obj = rt.inuMakeMesh([float(x) for x in pos.reshape(-1)],
                         [int(i) + 1 for i in faces.reshape(-1)],
                         [int(i) for i in np.concatenate(mats_all)])
    obj.name = MERGE_NAME
    seq = list(range(1, len(faces) * 3 + 1))
    rt.inuSetChannel(obj, 1, [float(x) for x in np.concatenate(uv).reshape(-1)], seq)
    for chan, vals in ((0, day), (-1, night)):
        _write(obj, chan, faces, np.concatenate(vals))
    flat_n = [float(x) for x in np.concatenate(normals).reshape(-1)]
    try:
        if not (scene_build._fast_mesh() and int(rt.INU_FastMesh.setNormals(obj, flat_n)) > 0):
            rt.inuSetNormals(obj, flat_n)
    except Exception as e:                             # noqa: BLE001
        print("[INU prelight] merge normals: %r" % (e,))
    if global_mats:
        if len(global_mats) == 1:
            obj.material = global_mats[0]
        else:
            mm = rt.MultiMaterial(numsubs=len(global_mats))
            mm.name = MERGE_NAME
            for i, s in enumerate(global_mats):
                rt.setSubMtl(mm, i + 1, s)
            obj.material = mm
    from .selection import put_field
    put_field([obj], MERGE_KEY, ";".join(ranges))
    set_active_layer([obj], 'Day')
    for node in used:
        node.isHidden = True
    rt.select(obj)
    return obj, len(used), skipped


def merge_split(proxy):
    """Перенести Day / Night модели обратно на оригиналы (по диапазонам
    граней), показать их, модель удалить. Возвращает (перенесено, всего)."""
    from .selection import get_field
    rt = _rt()
    ranges = []
    for part in str(get_field(proxy, MERGE_KEY, '') or '').split(';'):
        try:
            h, start, count = (int(x) for x in part.split(':'))
            ranges.append((h, start, count))
        except ValueError:
            continue
    cols = {c: get_corners(proxy, c) for c in (0, -1)}   # итог (мазки модели)
    back = []
    for h, start, count in ranges:
        orig = rt.maxOps.getNodeByHandle(h)
        if orig is None or not rt.isValidNode(orig):
            continue
        faces = faces_of(orig)
        if faces is not None and len(faces) == count:
            for chan, vals in cols.items():
                if vals is not None and len(vals) >= (start + count) * 3:
                    absorb_paint([orig], chan)
                    set_corners(orig, chan, faces, vals[start * 3:(start + count) * 3])
            back.append(orig)
        orig.isHidden = False
    rt.delete(proxy)
    shown = [rt.maxOps.getNodeByHandle(h) for h, _s, _c in ranges]
    shown = [n for n in shown if n is not None and rt.isValidNode(n)]
    if shown:
        rt.select(shown)
    return len(back), len(ranges)


# ── часть 3: PreLight COL (материалы по уровням, превью) ──────────────
# Как bake_col_light / clear_col_light_mats Blender-версии: грани делятся
# по (материал, день, ночь); у материала с несколькими уровнями «главным»
# остаётся самый яркий по дню, остальные — копии «имя_dN_nN» (реквизиты COL
# копируются). В Max материалы граней — подматериалы Multi/Sub-Object: один
# обычный материал превращается в Multi/Sub-Object (исходный первым), «×»
# возвращает его (решение пользователя). Имена копий — user property
# inu_col_light_mats («имя;имя»), признак превращения — inu_col_light_single.

COL_MATS_KEY = 'col_light_mats'
COL_SINGLE_KEY = 'col_light_single'
COL_NAME_RE = r'^(.+)_d(\d{1,2})_n(\d{1,2})$'


def _material():
    from . import material
    return material


def face_slots(node):
    """(«слот» материала каждой грани (nf,) — как material_index Blender,
    материалы-слоты). Multi/Sub-Object — подматериал по ID грани; обычный —
    один слот; нет материала — (None, [])."""
    rt = _rt()
    m = node.material
    if m is None:
        return None, []
    nf = face_count(node)
    if rt.classOf(m) == rt.MultiMaterial:
        subs = list(m.materialList)
        ids = [int(i) for i in m.materialIDList]
        fid = face_matids(node)
        return np.array([_sub_of(ids, len(subs), int(i)) for i in fid.tolist()]), subs
    return np.zeros(nf, dtype=np.int64), [m]


def col_mats_created(node):
    from .selection import get_field
    raw = str(get_field(node, COL_MATS_KEY, '') or '')
    return [n for n in raw.split(';') if n]


def col_bake_node(node, day, night):
    """Уровни граней (day, night — (nf,) 0..15) → материалы. Возвращает
    (новых материалов, пропущено граней без материала)."""
    from .selection import put_field, set_prop
    rt = _rt()
    ensure()
    MAT = _material()
    slots, mats = face_slots(node)
    if slots is None:
        return 0, len(day)
    groups = {}                                   # слот → {(д, н): [грани]} по порядку граней
    for fi, (s, d, n) in enumerate(zip(slots.tolist(), day.tolist(), night.tolist())):
        groups.setdefault(s, {}).setdefault((int(d), int(n)), []).append(fi)
    was_multi = rt.classOf(node.material) == rt.MultiMaterial
    subs = list(mats)
    ids = [int(i) for i in node.material.materialIDList] if was_multi else [1]
    new_mats, new_ids, face_set = [], [], []
    created, skipped = [], 0
    next_id = max(ids) + 1
    for s, levels in groups.items():
        if s >= len(subs) or subs[s] is None:
            skipped += sum(len(f) for f in levels.values())
            continue
        orig = subs[s]
        order = sorted(levels.keys(), key=lambda x: x[0], reverse=True)   # как в Blender
        d, n = order[0]
        MAT.set_props(orig, {'col_day_light': d, 'col_night_light': n})
        for d, n in order[1:]:
            cp = rt.copy(orig)
            cp.name = "%s_d%d_n%d" % (orig.name, d, n)
            props = dict(MAT.props(orig))
            props.update(col_day_light=d, col_night_light=n)
            MAT.set_props(cp, props)
            created.append(str(cp.name))
            new_mats.append(cp)
            new_ids.append(next_id)
            face_set += [(fi, next_id) for fi in levels[(d, n)]]
            next_id += 1
    if new_mats:
        if was_multi:
            rt.inuColSetSubs(node.material, subs + new_mats, ids + new_ids)
        else:
            rt.inuColMakeMulti(node, subs + new_mats, ids + new_ids)
            set_prop([node], COL_SINGLE_KEY, True)
            # все грани — на исходный (ID 1), затем копии
            moved = {f for f, _i in face_set}
            face_set = [(fi, 1) for fi in range(len(day)) if fi not in moved] + face_set
        if face_set:
            rt.inuColSetFaceIDs(node, [f + 1 for f, _i in face_set], [i for _f, i in face_set])
        put_field([node], COL_MATS_KEY, ";".join(col_mats_created(node) + created))
    return len(created), skipped


def col_clear_node(node):
    """Копии «_dN_nN» → грани обратно на исходные подматериалы, копии
    убрать; бывший обычный материал — вернуть. Число убранных."""
    import re
    from .selection import get_prop, set_prop
    rt = _rt()
    ensure()
    m = node.material
    if m is None or rt.classOf(m) != rt.MultiMaterial:
        set_prop([node], COL_MATS_KEY, '""')
        return 0
    subs = list(m.materialList)
    ids = [int(i) for i in m.materialIDList]
    stored = set(col_mats_created(node))
    pat = re.compile(COL_NAME_RE)
    merge = {}                                    # индекс копии → индекс исходного
    for i, s in enumerate(subs):
        if s is None:
            continue
        mt = pat.match(str(s.name))
        if not mt or (str(s.name) not in stored
                      and not (int(mt.group(2)) <= 15 and int(mt.group(3)) <= 15)):
            continue
        j = next((k for k, o in enumerate(subs) if o is not None and str(o.name) == mt.group(1)), None)
        if j is not None and j != i:
            merge[i] = j
    if not merge:
        return 0
    slots, _mats = face_slots(node)
    faces = [fi for fi, s in enumerate(slots.tolist()) if s in merge]
    rt.inuColSetFaceIDs(node, [f + 1 for f in faces], [ids[merge[int(slots[f])]] for f in faces])
    keep = [i for i in range(len(subs)) if i not in merge]
    if get_prop(node, COL_SINGLE_KEY, False) and len(keep) == 1:
        node.material = subs[keep[0]]
        set_prop([node], COL_SINGLE_KEY, False)
    else:
        rt.inuColSetSubs(m, [subs[i] for i in keep], [ids[i] for i in keep])
    set_prop([node], COL_MATS_KEY, '""')
    return len(merge)


def col_preview_node():
    """Узел с превью COL Light (или None). Значение — через execute: чтение
    rt.<глобал> в pymxs даёт ЖИВУЮ ссылку на переменную (обнулили глобал —
    «пропал» и узел в Python; проверено в Max 2026)."""
    ensure()
    rt = _rt()
    try:
        n = rt.execute("inuColPrevNode")
        return n if n is not None and rt.isValidNode(n) else None
    except Exception:                                  # noqa: BLE001
        return None


def col_preview_set(node, faces, levels, border, pos_local, numbers=True):
    """Превью уровней на узле: грань — зелёная (0, 0.9·уровень/15, 0) в
    канале COL_VIEW_CHAN, цифры уровня на гранях у границ."""
    rt = _rt()
    ensure()
    old = col_preview_node()
    if old is not None and node_handle(old) != node_handle(node):
        col_preview_off()
    g = np.repeat(np.asarray(levels, dtype=np.float32) * np.float32(0.9 / 15.0), 3)
    cols = np.zeros((len(g), 3), dtype=np.float32)
    cols[:, 1] = g
    _write(node, COL_VIEW_CHAN, faces, cols)
    rt.inuColSetPrev(node)
    pts, txt = [], []
    if numbers:
        cen = np.asarray(pos_local)[np.asarray(faces)].mean(axis=1)
        for fi in np.nonzero(np.asarray(border))[0].tolist():
            c = cen[fi]
            pts.append(rt.Point3(float(c[0]), float(c[1]), float(c[2])))
            txt.append(str(int(levels[fi])))
    rt.inuColNumSet(node if pts else None, pts, txt)
    update_display(node)


def col_preview_off():
    """Убрать превью COL Light (канал, цифры)."""
    rt = _rt()
    ensure()
    node = col_preview_node()
    rt.inuColNumSet(None, [], [])
    rt.inuColSetPrev(None)
    if node is not None:
        drop_channel(node, COL_VIEW_CHAN)
        update_display(node)
    return node
