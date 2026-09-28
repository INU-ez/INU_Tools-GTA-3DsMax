# INU Tools (Max) — сцена Max для карты (импорт IPL / IMG): расстановка
# моделей по строкам IPL, индекс уже стоящих моделей, связи с LOD.
#
# Расстановка — одним вызовом MAXScript на строку IPL (поэлементные вызовы
# pymxs медленные, а строк у карты тысячи): клоны-instance модели
# (maxOps.cloneNodes сохраняет порядок и иерархию — проверено в Max), имена
# как у оригинала (Max их нумерует), матрицы, буферы user properties, слой.
#
# MAXScript НЕ различает регистр: имена переменных — длинные и разные.

from .selection import _rt

_MXS = r'''
global inuMapPlace
fn inuMapPlace srcNodes doClone tmFlat tmMask propTexts ownerIdx layerName = (
    local outNodes = srcNodes
    if doClone do (
        local clonedArr = #()
        maxOps.cloneNodes srcNodes cloneType:#instance newNodes:&clonedArr
        outNodes = clonedArr
        for k = 1 to outNodes.count do outNodes[k].name = srcNodes[k].name
    )
    local lay = LayerManager.getLayerFromName layerName
    if lay == undefined do lay = LayerManager.newLayerFromName layerName
    for k = 1 to outNodes.count do (
        local nd = outNodes[k]
        if tmMask[k] do (
            local b = (k - 1) * 12
            nd.transform = matrix3 [tmFlat[b+1], tmFlat[b+2], tmFlat[b+3]] \
                [tmFlat[b+4], tmFlat[b+5], tmFlat[b+6]] \
                [tmFlat[b+7], tmFlat[b+8], tmFlat[b+9]] \
                [tmFlat[b+10], tmFlat[b+11], tmFlat[b+12]]
        )
        if propTexts[k] != "" do setUserPropBuffer nd propTexts[k]
        lay.addNode nd
    )
    if ownerIdx > 0 do
        setUserProp outNodes[ownerIdx] "inu_ipl_owner" outNodes[ownerIdx].inode.handle
    outNodes
)
global inuMapSceneIndex
fn inuMapSceneIndex = (
    -- узлы с inu_model_id > 0: id, узел, имя, позиция, поворот (мировые)
    local idArr = #(), nodeArr = #(), nameArr = #(), posArr = #(), rotArr = #()
    for o in geometry do (
        local v = getUserProp o "inu_model_id"
        if v != undefined do (
            local mid = try (v as integer) catch undefined
            if mid != undefined and mid > 0 do (
                append idArr mid
                append nodeArr o
                append nameArr o.name
                append posArr o.transform.translationpart
                append rotArr o.transform.rotationpart
            )
        )
    )
    #(idArr, nodeArr, nameArr, posArr, rotArr)
)
global inuMapLinkLods
fn inuMapLinkLods mainArr lodArr = (
    -- LOD-партнёр (handle) и его дистанция — модели
    for k = 1 to mainArr.count do (
        local lodNode = lodArr[k]
        setUserProp mainArr[k] "inu_lod_object" lodNode.inode.handle
        local dd = getUserProp lodNode "inu_lod_draw_distance"
        if dd != undefined do setUserProp mainArr[k] "inu_lod_draw_distance" dd
    )
    mainArr.count
)
global inuMapMoveTo
fn inuMapMoveTo nodeArr tmFlat layerName = (
    -- узлы в матрицу tm·(своя) и на слой (коллизия модели на её место)
    local tmPlace = matrix3 [tmFlat[1], tmFlat[2], tmFlat[3]] [tmFlat[4], tmFlat[5], tmFlat[6]] \
        [tmFlat[7], tmFlat[8], tmFlat[9]] [tmFlat[10], tmFlat[11], tmFlat[12]]
    local lay = LayerManager.getLayerFromName layerName
    if lay == undefined do lay = LayerManager.newLayerFromName layerName
    for nd in nodeArr do (
        nd.transform = nd.transform * tmPlace
        lay.addNode nd
    )
    nodeArr.count
)
global inuDropEmptyLayer
fn inuDropEmptyLayer layerName = (
    local lay = LayerManager.getLayerFromName layerName
    local dropped = false
    if lay != undefined do (
        local layNodes
        lay.nodes &layNodes
        if layNodes.count == 0 do dropped = LayerManager.deleteLayerByName layerName
    )
    dropped
)
'''

_READY = []


def ensure():
    if not _READY:
        _rt().execute(_MXS)
        _READY.append(True)


def parse_buffer(text):
    """Буфер user properties → {ключ: текст значения} (порядок сохраняется;
    ключи Max не различают регистр — сравниваем в нижнем)."""
    out = {}
    for line in (text or '').splitlines():
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        if k:
            out[k.lower()] = v.strip()
    return out


def buffer_text(d):
    return "\r\n".join("%s = %s" % (k, v) for k, v in d.items())


def read_buffer(node):
    try:
        return parse_buffer(str(_rt().getUserPropBuffer(node) or ''))
    except Exception:                                  # noqa: BLE001
        return {}


def node_rows(node):
    """12 чисел матрицы узла (строки + позиция)."""
    tm = node.transform
    return [float(c) for r in (tm.row1, tm.row2, tm.row3, tm.row4)
            for c in (r.x, r.y, r.z)]


def place(nodes, do_clone, tm_flat, tm_mask, texts, owner_idx, layer):
    """Одна расстановка модели (см. inuMapPlace). Возвращает узлы."""
    ensure()
    return list(_rt().inuMapPlace(nodes, bool(do_clone), tm_flat, tm_mask, texts,
                                  int(owner_idx), layer))


def scene_index():
    """[(id, узел, имя, (x, y, z), (qx, qy, qz, qw))] узлов с inu_model_id."""
    ensure()
    ids, nodes, names, pos, rot = _rt().inuMapSceneIndex()
    return [(int(i), n, str(nm), (float(p.x), float(p.y), float(p.z)),
             (float(q.x), float(q.y), float(q.z), float(q.w)))
            for i, n, nm, p, q in zip(ids, nodes, names, pos, rot)]


def link_lods(mains, lods):
    ensure()
    if mains:
        _rt().inuMapLinkLods(list(mains), list(lods))


def move_to(nodes, tm_flat, layer):
    ensure()
    if nodes:
        _rt().inuMapMoveTo(list(nodes), list(tm_flat), layer)


def drop_empty_layers(names):
    """Убрать пустые слои (сборка DFF / COL кладёт объекты на «2DFX» / «COL»,
    импорт карты переносит их на Map_*)."""
    ensure()
    for nm in names:
        try:
            _rt().inuDropEmptyLayer(nm)
        except Exception as e:                         # noqa: BLE001
            print("[INU map] layer %s: %r" % (nm, e))


def descendants(node):
    """Узел и все его потомки (родитель раньше детей)."""
    out, stack = [], [node]
    while stack:
        o = stack.pop(0)
        out.append(o)
        stack[0:0] = list(o.children)
    return out
