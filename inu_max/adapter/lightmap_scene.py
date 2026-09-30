# INU Tools (Max) — LightMap на UV2 (порт ops/texture_ops.py Blender-версии:
# apply_lightmap_uv2, toggle / remove_lightmap_uv2, lightmap_folder,
# lightmap_daynight).
#
# В Blender лайтмап — ноды материала «UV2 → картинка → Multiply поверх
# цвета». Здесь: diffuse Standard-материала оборачивается в RGB_Multiply
# «INU_LightMap» (map1 — исходная карта, или color1 — цвет материала; map2 —
# Bitmap по каналу 2). Вьюпорт Max это показывает (проверено пользователем).
# Показ / скрытие — map2Enabled (как mute LM_Mix). Экспорт и классификатор
# моделей видят исходную карту (material.base_diffuse).
#
# Картинки модели — user properties inu_lm_day / inu_lm_night (пути),
# показ — inu_lm_mode (DAY / NIGHT).

import os
import re

from .selection import _rt, get_field, put_field

WRAP = "INU_LightMap"
DAY_KEY, NIGHT_KEY, MODE_KEY = 'lm_day', 'lm_night', 'lm_mode'
IMAGE_EXT = ('.png', '.tga', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.dds')
DAY_SUFFIX = ('_d', '_day')
NIGHT_SUFFIX = ('_n', '_night')
NAME_TAIL = ('_lod_dff', '_dam_dff', '_ok_dff', '_dff', '.dff', '_lod', '_dam', '_ok')

_MXS = r'''
global inuLmCopyUV
fn inuLmCopyUV obj = (
    -- UV2 = копия UV1 (как новый UV-слой Blender копирует активный); прочие
    -- каналы не включаются (meshop.setNumMaps включил бы все — см. prelight)
    if not (meshop.getMapSupport obj.baseObject 1) then false else (
        local srcCount = meshop.getNumMaps obj.baseObject
        if srcCount < 3 do (
            local wasOn = for c = 0 to (srcCount - 1) collect (meshop.getMapSupport obj.baseObject c)
            meshop.setNumMaps obj 3 keep:true
            for c = 0 to 2 where c >= wasOn.count or not wasOn[c + 1] do meshop.setMapSupport obj c false
        )
        meshop.setMapSupport obj 2 true
        local nmv = meshop.getNumMapVerts obj 1
        meshop.setNumMapVerts obj 2 nmv
        for i = 1 to nmv do meshop.setMapVert obj 2 i (meshop.getMapVert obj 1 i)
        for k = 1 to obj.numfaces do meshop.setMapFace obj 2 k (meshop.getMapFace obj 1 k)
        update obj
        true
    )
)
'''
_READY = []


def ensure():
    if not _READY:
        _rt().execute(_MXS)
        _READY.append(True)


def _material():
    from . import material
    return material


def is_wrapper(tm):
    rt = _rt()
    try:
        return tm is not None and rt.classOf(tm) == rt.RGB_Multiply and str(tm.name) == WRAP
    except Exception:                                  # noqa: BLE001
        return False


def _subs(mat):
    """Материалы-«слоты»: подматериалы Multi/Sub или сам материал."""
    MAT = _material()
    if mat is None:
        return []
    return [s for s in list(mat.materialList) if s is not None] if MAT.is_multi(mat) else [mat]


def _copy_mat(mat):
    """Копия материала с GTA-свойствами (copy Max их не переносит)."""
    rt = _rt()
    MAT = _material()
    cp = rt.copy(mat)
    for src, dst in zip(_subs(mat), _subs(cp)):
        raw = rt.getAppData(src, MAT._APP_MAT)
        if raw:
            rt.setAppData(dst, MAT._APP_MAT, raw)
    return cp


def localize(node):
    """Материал, общий с другими узлами, — личная копия (как
    _lm_localize_materials: лайтмап живёт в материале). True — скопирован."""
    rt = _rt()
    m = node.material
    if m is None:
        return False
    try:
        users = list(rt.refs.dependentNodes(m))
    except Exception:                                  # noqa: BLE001
        users = []
    if len(users) > 1:
        node.material = _copy_mat(m)
        return True
    return False


def ensure_uv2(node):
    """UV2 есть или создан копией UV1. False — нет и UV1."""
    ensure()
    rt = _rt()
    if rt.meshop.getMapSupport(node, 2):
        return True
    return bool(rt.inuLmCopyUV(node))


def _apply_mat(mat, path):
    """Лайтмап на материал (повторно — новая картинка, показ включён).
    False — не Standard-материал (нет diffuse)."""
    rt = _rt()
    try:
        cur = mat.diffuseMap
    except Exception:                                  # noqa: BLE001
        return False
    if is_wrapper(cur):
        wrap = cur
    else:
        wrap = rt.RGB_Multiply(name=WRAP)
        if cur is not None:
            wrap.map1 = cur
        else:
            wrap.color1 = mat.diffuse
        mat.diffuseMap = wrap
    bm = wrap.map2 if wrap.map2 is not None and rt.classOf(wrap.map2) == rt.Bitmaptexture \
        else rt.Bitmaptexture(name="INU_LightMap_UV2")
    bm.fileName = path
    bm.coords.mapChannel = 2
    wrap.map2 = bm
    wrap.map2Enabled = True
    try:
        mat.showInViewport = True
    except Exception:                                  # noqa: BLE001
        pass
    return True


def apply(node, path, localize_mats=True):
    """Лайтмап path на все материалы узла. (наложено, пропущено)."""
    if localize_mats:
        localize(node)
    ensure_uv2(node)
    applied = skipped = 0
    for s in _subs(node.material):
        if _apply_mat(s, path):
            applied += 1
        else:
            skipped += 1
    return applied, skipped


def wrappers(node):
    out = []
    for s in _subs(getattr(node, 'material', None)):
        try:
            if is_wrapper(s.diffuseMap):
                out.append(s.diffuseMap)
        except Exception:                              # noqa: BLE001
            continue
    return out


def state(node):
    """(есть лайтмап, показан)."""
    ws = wrappers(node)
    return bool(ws), any(bool(w.map2Enabled) for w in ws)


def toggle(node, enable):
    n = 0
    for w in wrappers(node):
        w.map2Enabled = bool(enable)
        n += 1
    return n


def remove(node):
    """Обёртки → исходные карты (записи о картах модели остаются, как в
    Blender). Число материалов."""
    n = 0
    for s in _subs(getattr(node, 'material', None)):
        try:
            w = s.diffuseMap
            if is_wrapper(w):
                s.diffuseMap = w.map1
                n += 1
        except Exception:                              # noqa: BLE001
            continue
    return n


def name_candidates(node):
    """Имена, под которыми у модели может лежать лайтмап: имя узла, без
    суффикса Max «001» и хвостов _dff / _LOD / _dam / _ok."""
    names = []
    raw = str(node.name)
    for cand in (re.sub(r'\d{3}$', '', raw), raw):
        if cand and cand not in names:
            names.append(cand)
        low = cand.lower()
        for tail in NAME_TAIL:
            if low.endswith(tail):
                cut = cand[:-len(tail)]
                if cut and cut not in names:
                    names.append(cut)
                break
    return names


def scan_folder(folder):
    """{имя без суффикса (нижний регистр): {'DAY': путь, 'NIGHT': путь}}."""
    found = {}
    try:
        entries = os.listdir(folder)
    except OSError:
        return found
    for fn in entries:
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in IMAGE_EXT:
            continue
        low = stem.lower()
        for kind, suffixes in (('DAY', DAY_SUFFIX), ('NIGHT', NIGHT_SUFFIX)):
            hit = next((x for x in suffixes if low.endswith(x)), None)
            if hit is None:
                continue
            found.setdefault(low[:-len(hit)], {})[kind] = os.path.join(folder, fn)
            break
    return found


def maps_of(node):
    return {k: str(get_field(node, key, '') or '') for k, key in
            (('DAY', DAY_KEY), ('NIGHT', NIGHT_KEY))}


def set_maps(node, day=None, night=None, mode=None):
    if day is not None:
        put_field([node], DAY_KEY, day.replace('\\', '/'))
    if night is not None:
        put_field([node], NIGHT_KEY, night.replace('\\', '/'))
    if mode is not None:
        put_field([node], MODE_KEY, mode)


def mode_of(node):
    return str(get_field(node, MODE_KEY, '') or '')


def set_mode(node, mode):
    """Показать дневную / ночную карту узла. True — карта есть и подставлена."""
    path = maps_of(node).get(mode)
    if not path:
        return False
    rt = _rt()
    changed = False
    for w in wrappers(node):
        if w.map2 is not None and rt.classOf(w.map2) == rt.Bitmaptexture:
            w.map2.fileName = path
            changed = True
    if changed:
        set_maps(node, mode=mode)
    return changed


def scene_nodes_with_maps():
    rt = _rt()
    return [o for o in rt.geometry if maps_of(o)['DAY'] or maps_of(o)['NIGHT']]
