# INU Tools (Max) — выделение сцены для окна DFF IO.
#
# Аналог tools/model_utils из Blender-версии: какие меши выделены, какого они
# типа (DFF / LOD / COL — общий классификатор ядра inu_gta_core.model_classify)
# и как они группируются по базовому имени (имя экспорта). Плюс DFF-флаги
# экспорта на объекте: в Blender это obj.inu.*, здесь — user properties
# объекта Max (переживают сохранение .max).
#
# pymxs импортируем лениво: модуль должен грузиться и вне Max (UI берёт
# отсюда FLAG_DEFAULTS, в т.ч. при offscreen-рендере панели).

import contextlib
import json

_DATA_IDS = {'water_vertices': 0x494E5510, 'path_knots': 0x494E5511,
             'nodes_file': 0x494E5512, 'path_accessory': 0x494E5513,
             'weight_merge': 0x494E5514, 'handsign_parent': 0x494E5515}
_DATA_IDS['ipl_section'] = 0x494E5516
_DATA_IDS['ipl_placeholder'] = 0x494E5517
_DATA_IDS['nodes_identity'] = 0x494E5518


def put_data(nodes, key, value):
    """Structured data belongs in AppData: user properties alter quotes."""
    raw = json.dumps(value, separators=(',', ':'), ensure_ascii=True)
    for node in nodes:
        _rt().setAppData(node, _DATA_IDS[key], raw)


def get_data(node, key, default=None):
    raw = _rt().getAppData(node, _DATA_IDS[key])
    return json.loads(str(raw)) if raw else default


def _rt():
    import pymxs
    return pymxs.runtime

# DFF-флаги экспорта (как obj.inu.* в Blender) и их значения по умолчанию.
FLAG_DEFAULTS = {
    'export_normals': False,
    'light': True,
    'modulate_color': True,
    'set_material_alpha': False,
    'light_beam_asi': False,
    'uv_map1': True,
    'uv_map2': True,
    'day_cols': True,
    'night_cols': True,
}
_PROP_PREFIX = "inu_"

# Больше этого числа мешей не классифицируем на каждом опросе UI (дорого).
_CLASSIFY_LIMIT = 1000


def selected_meshes():
    """Выделенные геометрические объекты (Editable Mesh/Poly и т.п.)."""
    rt = _rt()
    out = []
    for o in rt.selection:
        try:
            if rt.superClassOf(o) == rt.GeometryClass:
                out.append(o)
        except Exception:                              # noqa: BLE001
            pass
    return out


def _has_texture(o):
    """Есть ли у материала объекта текстура (diffuseMap). Нужна классификатору
    на последнем шаге: меш без текстур считается коллизией."""
    rt = _rt()
    try:
        m = o.material
    except Exception:                                  # noqa: BLE001
        return True
    if m is None:
        return False
    mats = [m]
    try:
        if rt.classOf(m) == rt.MultiMaterial:
            mats = [s for s in m.materialList if s is not None]
    except Exception:                                  # noqa: BLE001
        pass
    from .material import base_diffuse          # без обёрток INU (LightMap, превью)
    for s in mats:
        try:
            if base_diffuse(s) is not None:
                return True
        except Exception:                              # noqa: BLE001
            continue
    return False


def classify(o):
    """(тип, базовое имя) объекта: 'DFF' | 'LOD' | 'COL'."""
    rt = _rt()
    from inu_gta_core.model_classify import classify_model
    try:
        tag = rt.getUserProp(o, _PROP_PREFIX + "type")
    except Exception:                                  # noqa: BLE001
        tag = None
    return classify_model(str(o.name), has_texture=lambda: _has_texture(o),
                          inu_type=str(tag) if tag else 'OBJ')


def summary():
    """Сводка выделения для UI (как диагностика панели Экспорт/Импорт INU).

    Возвращает dict: n — число выделенных мешей; first — {тип: имя первого
    объекта этого типа | None}; counts — {тип: число групп с этим типом};
    n_groups — число моделей (групп по базовому имени); name — имя экспорта
    при одной модели; too_many — выделено слишком много для классификации."""
    meshes = selected_meshes()
    res = dict(n=len(meshes), first={'DFF': None, 'LOD': None, 'COL': None},
               counts={'DFF': 0, 'LOD': 0, 'COL': 0}, n_groups=0, name='',
               too_many=len(meshes) > _CLASSIFY_LIMIT)
    if res['too_many']:
        return res
    groups = {}
    for o in meshes:
        kind, base = classify(o)
        base = (base or '').rstrip('_')
        if not base:
            continue
        if res['first'][kind] is None:
            res['first'][kind] = str(o.name)
        g = groups.setdefault(base, {'DFF': False, 'LOD': False, 'COL': False})
        g[kind] = True
    for g in groups.values():
        for k in res['counts']:
            if g[k]:
                res['counts'][k] += 1
    res['n_groups'] = len(groups)
    if len(groups) == 1:
        res['name'] = next(iter(groups))
    return res


def selection_key():
    """Дешёвый отпечаток выделения — чтобы UI пересчитывал сводку и флаги
    только когда выделение реально поменялось."""
    rt = _rt()
    try:
        return tuple(int(rt.getHandleByAnim(o)) for o in rt.selection)
    except Exception:                                  # noqa: BLE001
        return None


def get_flags(o):
    """DFF-флаги объекта (user properties), недостающие — по умолчанию."""
    rt = _rt()
    flags = {}
    for k, dflt in FLAG_DEFAULTS.items():
        try:
            v = rt.getUserProp(o, _PROP_PREFIX + k)
        except Exception:                              # noqa: BLE001
            v = None
        flags[k] = dflt if v is None else bool(v)
    return flags


def set_flag(objs, key, value):
    """Записать DFF-флаг всем переданным объектам (как в INU: правка флага
    активного объекта копируется на все выделенные меши)."""
    rt = _rt()
    for o in objs:
        try:
            rt.setUserProp(o, _PROP_PREFIX + key, bool(value))
        except Exception:                              # noqa: BLE001
            pass


# ── свойства объекта для IDE / IPL (obj.inu.* в INU) ─────────────────

def get_prop(o, key, default):
    """User property объекта «inu_<key>», приведённая к типу default."""
    rt = _rt()
    try:
        v = rt.getUserProp(o, _PROP_PREFIX + key)
    except Exception:                                  # noqa: BLE001
        v = None
    if v is None:
        return default
    try:
        if isinstance(default, bool):
            return bool(v)
        if isinstance(default, int):
            return int(v)
        if isinstance(default, float):
            return float(v)
        return str(v)
    except (TypeError, ValueError):
        return default


def set_prop(objs, key, value):
    """Записать «inu_<key>» всем переданным объектам."""
    rt = _rt()
    for o in objs:
        try:
            rt.setUserProp(o, _PROP_PREFIX + key, value)
        except Exception:                              # noqa: BLE001
            pass


# Строки и векторы — В КАВЫЧКАХ: getUserProp Max разбирает значение как
# литерал MAXScript, и без кавычек «1,1,0.67,1» вернулся бы числом 1, а
# «2DFX» мог бы прочитаться как число. Строка в кавычках читается строкой;
# если Max вернёт текст как есть — кавычки снимаем сами.

def _unquote(v):
    if isinstance(v, str) and len(v) >= 2 and v[0] == v[-1] == '"':
        return v[1:-1]
    return v


def get_field(o, key, default):
    """Поле «inu_<key>»: tuple-умолчание → вектор из строки «x,y,z»."""
    if isinstance(default, tuple):
        raw = _unquote(get_prop(o, key, ''))
        try:
            vals = tuple(float(x) for x in str(raw).split(',')) if raw else ()
        except ValueError:
            vals = ()
        return vals if len(vals) == len(default) else default
    return _unquote(get_prop(o, key, default))


def put_field(nodes, key, value):
    """Записать поле: строки и векторы — в кавычках (см. выше)."""
    if isinstance(value, (tuple, list)):
        # %.9g — float32 без потерь (%g давал 6 цифр: 2233.8032 → 2233.8)
        value = '"%s"' % ",".join("%.9g" % float(v) for v in value)
    elif isinstance(value, float):
        # число — тоже текстом %.9g: Float Max печатает сам с 6 цифрами;
        # repr оставляет точку («300.0»), getUserProp вернёт Float
        value = repr(float("%.9g" % value))
    elif isinstance(value, str):
        value = '"%s"' % value.replace('"', "'")
    set_prop(nodes, key, value)


def node_by_handle(handle):
    if int(handle or 0) <= 0:
        return None
    rt = _rt()
    node = rt.maxOps.getNodeByHandle(int(handle))
    return node if node is not None and rt.isValidNode(node) else None


def pick_node(prompt):
    rt = _rt()
    node = rt.pickObject(message=prompt)
    try:
        return node if rt.isValidNode(node) and rt.superClassOf(node) == rt.GeometryClass else None
    except Exception:
        return None


def id_conflicts(o, model_id, limit=3):
    """Другие меши сцены с тем же Model ID, но другим базовым именем
    (как проверка конфликтов в «Object IDE / IPL» INU)."""
    rt = _rt()
    if model_id <= 0:
        return []
    import re
    base = re.sub(r'\d{3}$', '', str(o.name))
    out = []
    for other in rt.objects:
        try:
            if other == o or rt.superClassOf(other) != rt.GeometryClass:
                continue
            if get_prop(other, 'model_id', 0) != model_id:
                continue
            if re.sub(r'\d{3}$', '', str(other.name)) != base:
                out.append(str(other.name))
                if len(out) >= limit:
                    break
        except Exception:                              # noqa: BLE001
            continue
    return out


def scene_file():
    """Путь сохранённой сцены .max ('' — сцена не сохранена)."""
    rt = _rt()
    try:
        folder, name = str(rt.maxFilePath or ''), str(rt.maxFileName or '')
    except Exception:                                  # noqa: BLE001
        return ''
    import os
    return os.path.join(folder, name) if folder and name else ''


# ── иерархия сцены (дерево фреймов машины / педа) ────────────────────

def active_node():
    """«Активный» объект Max: первый выделенный (любого типа)."""
    rt = _rt()
    try:
        for o in rt.selection:
            return o
    except Exception:                                  # noqa: BLE001
        pass
    return None


def selected_names():
    rt = _rt()
    try:
        return [str(o.name) for o in rt.selection]
    except Exception:                                  # noqa: BLE001
        return []


def node_kind(o):
    """'BONE' | 'MESH' | 'EMPTY' — для иконки строки дерева."""
    rt = _rt()
    try:
        if rt.classOf(o) == rt.BoneGeometry:
            return 'BONE'
        if rt.superClassOf(o) == rt.GeometryClass:
            return 'MESH'
    except Exception:                                  # noqa: BLE001
        pass
    return 'EMPTY'


def hierarchy(node, limit=None):
    """(корень, [(узел, глубина)]) — корень = верхний предок node, обход в
    глубину по детям (родитель раньше детей)."""
    root = node
    while root is not None and root.parent is not None:
        root = root.parent
    items, stack = [], [(root, 0)]
    while stack:
        o, d = stack.pop(0)
        items.append((o, d))
        if limit and len(items) > limit:
            break
        stack[0:0] = [(c, d + 1) for c in list(o.children)]
    return root, items


def find(name):
    rt = _rt()
    try:
        return rt.getNodeByName(name)
    except Exception:                                  # noqa: BLE001
        return None


def _undo(label):
    """Шаг отмены операций окон — ошибка в блоке не глотается (undo_block)."""
    return undo_block(label)


@contextlib.contextmanager
def undo_block(label):
    """Шаг отмены, ошибка внутри которого НЕ глотается. pymxs.undo при
    исключении в блоке молча отменяет его и продолжает код после блока
    (проверено в Max 2026: операция отчитывается об успехе, в 3dsmaxbatch
    отмена удалила и узел, созданный до блока). Здесь изменения до ошибки
    остаются (их снимает Ctrl+Z), а ошибка идёт дальше — в отчёт окна."""
    import pymxs
    from ..i18n import tr
    err = []
    with pymxs.undo(True, tr(label)):
        try:
            yield
        except Exception as e:                         # noqa: BLE001
            err.append(e)
    if err:
        raise err[0]


def select_node(name):
    rt = _rt()
    o = find(name)
    if o is not None:
        with _undo("INU: Select Frame"):
            rt.select(o)
    return o is not None


def set_parent(child_name, parent_name):
    """Сменить родителя (parent_name='' — снять родителя). Мировое
    положение Max сохраняет сам. Возвращает текст ошибки или ''."""
    child = find(child_name) if child_name else active_node()
    parent = find(parent_name) if parent_name else None
    if child is None:
        return "Object not found"
    if parent is not None:
        if parent == child:
            return "Can't parent an object to itself"
        p = parent
        while p is not None:
            if p == child:
                return "Circular hierarchy is not allowed"
            p = p.parent
    with _undo("INU: Reparent Frame"):
        child.parent = parent
    return ''


def rename_node(name, new_name):
    o = find(name)
    if o is None or not new_name:
        return False
    with _undo("INU: Rename Frame"):
        o.name = new_name
    return True


def set_hidden(nodes, hidden):
    with _undo("INU: Damage state"):
        for o in nodes:
            try:
                o.isHidden = bool(hidden)
            except Exception:                          # noqa: BLE001
                pass
