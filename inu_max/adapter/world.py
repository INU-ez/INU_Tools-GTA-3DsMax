# INU Tools (Max) — вода и пути в сцене Max (панели INU «Water» и «Пути»).
#
# Вода: параметры водного меша — user properties water_flag, water_speed_x /
# _y / _z, water_wave_height (в Blender — слои вершин; «Apply» ставит их
# всем вершинам одинаково — здесь это значения объекта).
# Пути: объект пути — сплайн / меш с user properties path_type (path_ipl |
# track | nodes_vehicle | nodes_ped | nodes_navi), group_type, sapath_* —
# атрибуты кривой в духе Kam's / ZZPuma.

from .selection import (_rt, _undo, _unquote, get_prop, get_field,
                        put_field, selected_meshes, put_data, get_data)

WATER_FLAGS = {0: "Default / Invisible", 1: "Default / Visible",
               2: "Shallow / Invisible", 3: "Shallow / Visible"}

SAPATH_KEYS = ('sapath_type', 'sapath_width', 'sapath_pathid',
               'sapath_traffic', 'sapath_spawn', 'sapath_highway',
               'sapath_roadblock', 'sapath_boats', 'sapath_emergency',
               'sapath_parking', 'sapath_laneright', 'sapath_laneleft')

PATH_TYPES = {'track': "Train Track", 'path_ipl': "Path IPL",
              'nodes_vehicle': "Vehicle Paths", 'nodes_ped': "Ped Paths",
              'nodes_navi': "Navigation Nodes"}


# ── вода ─────────────────────────────────────────────────────────────

WATER_BLOCK = 500.0


def add_water(size=WATER_BLOCK):
    """«Add Water» (add_water INU с настройками по умолчанию): квад 500×500
    в блоке сетки воды под центром выделения (иначе вода в игре без
    текстуры), Editable Poly, флаг 1, в слое «Water»."""
    import math
    rt = _rt()
    try:
        c = rt.selection.center if len(list(rt.selection)) else rt.Point3(0, 0, 0)
        x, y, z = float(c.x), float(c.y), float(c.z)
    except Exception:                                  # noqa: BLE001
        x = y = z = 0.0
    x = math.floor(x / WATER_BLOCK) * WATER_BLOCK + WATER_BLOCK / 2.0
    y = math.floor(y / WATER_BLOCK) * WATER_BLOCK + WATER_BLOCK / 2.0
    with _undo("INU: Add water"):
        p = rt.Plane(name=rt.uniqueName("Water"), length=size, width=size,
                     lengthsegs=1, widthsegs=1, pos=rt.Point3(x, y, z))
        rt.convertToPoly(p)
        for key, v in (('water_flag', 1), ('water_speed_x', 0.0),
                       ('water_speed_y', 0.0), ('water_speed_z', 0.05),
                       ('water_wave_height', 0.1)):
            put_field([p], key, v)
        try:
            layer = rt.LayerManager.getLayerFromName("Water") or \
                rt.LayerManager.newLayerFromName("Water")
            layer.addNode(p)
        except Exception as e:                         # noqa: BLE001
            print("[INU] Water layer: %r" % (e,))
        rt.select(p)
    return p


def set_water_params(flag, sx, sy, sz, wave):
    """«Apply» (water_set_params INU) — выделенным мешам. Возвращает число."""
    meshes = selected_meshes()
    if any(list(node.modifiers) for node in meshes):
        raise ValueError('Collapse water modifiers before applying vertex parameters')
    with _undo("INU: Water parameters"):
        for key, v in (('water_flag', int(flag)), ('water_speed_x', float(sx)),
                       ('water_speed_y', float(sy)), ('water_speed_z', float(sz)),
                       ('water_wave_height', float(wave))):
            put_field(meshes, key, v)
        import json
        rt = _rt()
        for node in meshes:
            if list(node.modifiers):
                raise ValueError('Collapse water modifiers before applying vertex parameters')
            rt.convertToPoly(node)
            count = int(rt.polyop.getNumVerts(node.baseObject))
            old = get_data(node, 'water_vertices', [])
            if len(old) != count:
                old = [{} for _ in range(count)]
            selected = list(rt.polyop.getVertSelection(node.baseObject)) if int(rt.subObjectLevel) == 1 else []
            targets = [int(i) - 1 for i in selected] if selected else range(count)
            for i in targets:
                old[i].update(speed_x=float(sx), speed_y=float(sy), speed_z=float(sz), wave_height=float(wave))
            put_data([node], 'water_vertices', old)
            put_field([node], 'water_active', True)
            put_field([node], 'type', 'NON')
            put_field([node], 'section', 'water')
    return len(meshes)


def water_flag(o):
    """Флаг водного меша или None, если объект — не вода."""
    if not get_field(o, 'water_active', True):
        return None
    v = get_prop(o, 'water_flag', None)
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


# ── пути ─────────────────────────────────────────────────────────────

def is_shape(o):
    rt = _rt()
    try:
        return rt.superClassOf(o) == rt.shape
    except Exception:                                  # noqa: BLE001
        return False


def path_type(o):
    return str(get_field(o, 'path_type', '') or '') if o is not None else ''


def knot_count(o):
    rt = _rt()
    try:
        return sum(int(rt.numKnots(o, s)) for s in range(1, int(rt.numSplines(o)) + 1))
    except Exception:                                  # noqa: BLE001
        return 0


def vert_count(o):
    try:
        return int(_rt().getNumVerts(o))
    except Exception:                                  # noqa: BLE001
        return 0


def sapath(o):
    """{ключ: значение} атрибутов sapath_*, заданных у объекта (числа —
    числами, строки — без кавычек)."""
    rt = _rt()
    out = {}
    for k in SAPATH_KEYS:
        try:
            v = rt.getUserProp(o, 'inu_' + k)
        except Exception:                              # noqa: BLE001
            v = None
        if v is not None:
            out[k] = _unquote(v)
    return out


def path_shapes(kind):
    """Кривые путей: 'PED' — sapath_type=1, 'VEH' — =2, 'ALL' — любые с
    sapath_* (select_path_* INU)."""
    rt = _rt()
    out = []
    for o in rt.shapes:
        a = sapath(o)
        if not a:
            continue
        t = a.get('sapath_type')
        if kind == 'ALL' or (kind == 'PED' and t == 1) or (kind == 'VEH' and t == 2):
            out.append(o)
    return out


def select_nodes(nodes):
    rt = _rt()
    with _undo("INU: Select paths"):
        rt.clearSelection()
        if nodes:
            rt.select(nodes)
    return len(nodes)


def selected_shapes():
    return [o for o in _rt().selection if is_shape(o)]


def apply_sapath(values, nodes=None):
    """Записать атрибуты sapath_* выделенным кривым (Apply / Bulk)."""
    nodes = selected_shapes() if nodes is None else nodes
    with _undo("INU: Path props"):
        for k, v in values.items():
            put_field(nodes, k, v)
    return len(nodes)
