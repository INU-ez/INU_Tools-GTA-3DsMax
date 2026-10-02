# INU Tools (Max) — сцена для окна «IFP IO» (панель INU «Анимации»).
#
# Скелет. В Blender это объект Armature; в Max скелет — иерархия узлов,
# поэтому «выделен скелет» = выделенный узел лежит в иерархии с костями
# (Bone) или с костями педа / кистей GTA по имени. Корень иерархии играет
# роль armature: на нём user properties inu_ifp_current (текущая анимация)
# и inu_ik_rigged.
#
# Библиотека анимаций — аналог Actions с ifp_source: импорт IFP кладёт в
# сцену имена анимаций и путь .ifp (AppData корня сцены — сохраняется в
# .max); ключи читаются из файла при применении.
#
# Animated Map Object: rig из хелперов с user properties как в INU —
# inu_animobj_empty_root (root), inu_animobj_empty_pivot (pivot),
# inu_bone_id; настройки pivot'а — inu_auto_mode, inu_axis, inu_reverse,
# inu_turns_per_cycle, inu_duration_frames; у root — inu_attach_target.

import json
import os

from .selection import (_rt, _undo, get_prop, node_kind, hierarchy,
                        selected_meshes, active_node, get_field)

# ── скелет ───────────────────────────────────────────────────────────

# кости, по которым иерархия считается скелетом: пед (' Pelvis') и кисти
# shandl / shandr (' L Hand01' / ' R Hand01'); регистр и пробелы не важны
_SKELETON_NAMES = {'pelvis', 'bip01 pelvis', 'l hand01', 'r hand01'}
_SKELETON_SCAN = 200            # не больше стольких узлов на один опрос


def _top(node):
    while node is not None and node.parent is not None:
        node = node.parent
    return node


def skeleton_root(node):
    """Корень скелета, в котором лежит node (аналог активной armature),
    или None."""
    if node is None:
        return None
    root, items = hierarchy(node, limit=_SKELETON_SCAN)
    for o, _d in items:
        if node_kind(o) == 'BONE' or \
                str(o.name).strip().lower() in _SKELETON_NAMES:
            return root
    return None


def is_camera(node):
    rt = _rt()
    try:
        return node is not None and rt.superClassOf(node) == rt.camera
    except Exception:                                  # noqa: BLE001
        return False


def has_skin(node):
    """Есть ли у объекта модификатор Skin (в Max веса красят в нём — аналог
    режима Weight Paint)."""
    rt = _rt()
    try:
        return any(rt.classOf(m) == rt.Skin for m in node.modifiers)
    except Exception:                                  # noqa: BLE001
        return False


def frame_rate():
    try:
        return int(_rt().frameRate)
    except Exception:                                  # noqa: BLE001
        return 30


# ── Handsign: скелет игрока и кисти ──────────────────────────────────

def _named(name):
    """Узлы с именем name без учёта регистра и пробелов по краям (в SA у
    костей ведущий пробел: ' L Hand')."""
    rt = _rt()
    want = name.strip().lower()
    out = []
    for n in (name, ' ' + name):
        try:
            found = rt.getNodeByName(n, ignoreCase=True, all=True)
        except Exception:                              # noqa: BLE001
            continue
        for o in (found or []):
            if str(o.name).strip().lower() == want and o not in out:
                out.append(o)
    return out


def handsign_status():
    """(ped, left, right) — корни скелетов, как classify_handsign_armatures
    INU: кисти несут ' L Hand01' / ' R Hand01', скелет игрока — ' L Hand' и
    ' R Hand'. При нескольких — последний найденный; любой может быть None."""
    def roots(name):
        out = []
        for o in _named(name):
            r = _top(o)
            if r not in out:
                out.append(r)
        return out
    from .selection import get_data
    attached = {get_data(o, 'handsign_parent', {}).get('side'): o
                for o in _rt().objects if get_data(o, 'handsign_parent', None)}
    if attached:
        hand = next(iter(attached.values()))
        return _top(hand), attached.get('L'), attached.get('R')
    l01, r01 = roots('L Hand01'), roots('R Hand01')
    lh = l01[-1] if l01 else None
    rh = next((r for r in reversed(r01) if r not in l01), None)
    rset = roots('R Hand')
    ped = next((r for r in reversed(roots('L Hand'))
                if r in rset and r not in l01 and r not in r01), None)
    return ped, lh, rh


# ── Animated Map Object: rig из хелперов ─────────────────────────────

PIVOT_DEFAULTS = {'auto_mode': True, 'axis': 'Z', 'reverse': False,
                  'turns_per_cycle': 1, 'duration_frames': 60}

_RIG_CACHE = {}                 # {'n': число хелперов, 'name': имя root}


def is_rig_root(o):
    return o is not None and bool(get_prop(o, 'animobj_empty_root', False))


def is_pivot(o):
    return o is not None and bool(get_prop(o, 'animobj_empty_pivot', False))


def _up(node):
    while node is not None:
        yield node
        node = node.parent


def rig_of(node):
    """root rig'а, в иерархии которого лежит node (или сам node)."""
    return next((o for o in _up(node) if is_rig_root(o)), None)


def pivot_of(node):
    """Ближайший pivot вверх от node (или сам node)."""
    return next((o for o in _up(node) if is_pivot(o)), None)


def find_rig():
    """Первый root Empty-rig'а в сцене (среди хелперов) или None. Кэш по
    числу хелперов — как memo INU по числу объектов."""
    rt = _rt()
    helpers = rt.helpers
    try:
        n = int(helpers.count)              # ObjectSet MAXScript
    except Exception:                                  # noqa: BLE001
        n = len(list(helpers))
    if _RIG_CACHE.get('n') == n:
        name = _RIG_CACHE.get('name')
        if not name:
            return None
        o = rt.getNodeByName(name)
        if is_rig_root(o):
            return o
    rig = next((o for o in helpers if is_rig_root(o)), None)
    _RIG_CACHE.update(n=n, name=str(rig.name) if rig is not None else '')
    return rig


def first_pivot(root):
    return next((c for c in root.children if is_pivot(c)), None)


def pivots(root):
    """Все pivot'ы rig'а (обход вниз от root)."""
    out, stack = [], list(root.children)
    while stack:
        o = stack.pop(0)
        if is_pivot(o):
            out.append(o)
        stack[0:0] = list(o.children)
    return out


def first_mesh(root):
    """Первый меш в иерархии rig'а (в ширину, как invoke INU)."""
    stack = [root]
    while stack:
        for c in stack.pop(0).children:
            if node_kind(c) == 'MESH':
                return c
            stack.append(c)
    return None


def mesh_count(o):
    return sum(1 for c in o.children if node_kind(c) == 'MESH')


def rig_tree(root):
    """[(узел, глубина)] — root, дети и внуки (глубже INU не показывает)."""
    out = [(root, 0)]
    for c in root.children:
        out.append((c, 1))
        out += [(g, 2) for g in c.children]
    return out


def node_tag(o):
    """(иконка, метка) строки rig'а: [root], [pivot N], [mesh]."""
    if is_rig_root(o):
        return 'pivot', '[root]'
    if is_pivot(o):
        return 'screw', '[pivot %d]' % get_prop(o, 'bone_id', 0)
    if node_kind(o) == 'MESH':
        return 'mesh', '[mesh]'
    return 'empty', ''


def anim_name(pivot):
    """Имя анимации pivot'а (в INU — имя его Action)."""
    return get_field(pivot, 'anim_name', '') or str(pivot.name)


def pivot_settings(pivot):
    return {k: get_field(pivot, k, d) for k, d in PIVOT_DEFAULTS.items()}


def parent_selected(to):
    """«To pivot» / «To root» INU: выделенные меши — детьми pivot'а (to=
    'PIVOT') или root'а rig'а активного объекта, иначе первого rig'а сцены.
    Мировое положение Max сохраняет сам. Возвращает (текст, ошибка?)."""
    rig = rig_of(active_node()) or find_rig()
    if rig is None:
        return ("No Empty-rig in the scene — pick a mesh first, the rig is "
                "created automatically", True)
    target = rig
    if to == 'PIVOT':
        target = first_pivot(rig)
        if target is None:
            return "The rig has no pivot Empty", True
    n = 0
    with _undo("INU: Parent to rig"):
        for o in selected_meshes():
            if o == target or o.parent == target:
                continue
            try:
                o.parent = target
                n += 1
            except Exception as e:                     # noqa: BLE001
                print("[INU] parent %s: %r" % (o.name, e))
    return "%d mesh(es) parented to %s" % (n, target.name), False


# ── библиотека анимаций сцены (аналог Actions с ifp_source) ──────────

_LIB_APPDATA = 0x494E5501       # 'INU' + 1 — id AppData на корне сцены


def library():
    """[{path, package, format, anims: [имя, ...]}] — импортированные IFP."""
    rt = _rt()
    try:
        raw = rt.getAppData(rt.rootNode, _LIB_APPDATA)
    except Exception:                                  # noqa: BLE001
        return []
    if not raw:
        return []
    try:
        data = json.loads(str(raw))
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def library_add(path, package, fmt, names):
    """Записать анимации файла в библиотеку; повторный импорт того же
    файла заменяет его запись. Возвращает общее число анимаций."""
    rt = _rt()
    key = os.path.normcase(os.path.abspath(path))
    items = [e for e in library()
             if os.path.normcase(os.path.abspath(e.get('path', ''))) != key]
    items.append(dict(path=path, package=package, format=fmt,
                      anims=list(names)))
    rt.setAppData(rt.rootNode, _LIB_APPDATA, json.dumps(items))
    return sum(len(e.get('anims', [])) for e in items)


def library_names():
    return [n for e in library() for n in e.get('anims', [])]
