# INU Tools (Max) — зоны map.zon / info.zon в сцене Max (панель INU
# «map.zon», порт ops/zon_ops.py Blender-версии).
#
# Зона — бокс (Box) в слое «ZON_<имя файла>» (в Blender — коллекция) с user
# properties inu_zon, zon_name, zon_type, zon_level, zon_gxt, zon_index,
# zon_layer. Комментарии над строкой зоны и исходная строка (для экспорта
# байт-в-байт) — в AppData бокса; шапка / хвост файла — в AppData корня
# сцены по имени слоя. Координаты при экспорте — из габарита бокса.

import json
import os
import shutil

from .selection import _rt, _undo, get_prop, get_field, put_field

_APP_BOX = 0x494E5504           # {comment, raw} на боксе
_APP_FILES = 0x494E5503         # {слой: {header, section_tail, footer, eol}}

TYPE_COLORS = {0: (64, 140, 255), 1: (153, 153, 255), 2: (230, 191, 64),
               3: (77, 217, 89), 4: (255, 115, 38)}
_DEFAULT_COLOR = (179, 179, 179)

# подписи типа зоны (_TYPES панели INU)
TYPES = {0: "0 — navigation (info.zon)", 1: "1 — navig", 2: "2 — info",
         3: "3 — map zone (map.zon)", 4: "4 — weather (mod)"}

_COUNT = {}                     # {'n': число геометрии, 'zones': число зон}


def _core():
    from inu_gta_core import zon
    return zon


def layer_name(path):
    """map.zon → ZON_map: у каждого файла свой слой."""
    base = os.path.splitext(os.path.basename(path or ''))[0]
    return "ZON_%s" % (base or 'zon')


def is_zone(o):
    return o is not None and bool(get_prop(o, 'zon', False))


def all_zones():
    rt = _rt()
    return [o for o in rt.geometry if is_zone(o)]


def zone_count():
    """«Zones in scene» — кэш по числу геометрии (как memo INU)."""
    rt = _rt()
    try:
        n = int(rt.geometry.count)
    except Exception:                                  # noqa: BLE001
        n = len(list(rt.geometry))
    if _COUNT.get('n') != n:
        _COUNT.update(n=n, zones=len(all_zones()))
    return _COUNT['zones']


def _json(node, app_id):
    rt = _rt()
    try:
        raw = rt.getAppData(node, app_id)
        return json.loads(str(raw)) if raw else {}
    except (ValueError, Exception):                    # noqa: BLE001
        return {}


def _set_json(node, app_id, data):
    _rt().setAppData(node, app_id, json.dumps(data))


def _order_key(o):
    return (int(get_prop(o, 'zon_index', 10 ** 6)), str(o.name))


# ── импорт ───────────────────────────────────────────────────────────

def import_zon(path):
    """Прочитать .zon и построить бокс на каждую зону (повторный импорт
    того же файла заменяет старые боксы). Возвращает (число, ZonFile)."""
    rt = _rt()
    zc = _core()
    zf = zc.read_zon(path)
    lname = layer_name(path)
    with _undo("INU: Import zones"):
        for o in [o for o in all_zones() if get_field(o, 'zon_layer', '') == lname]:
            rt.delete(o)
        layer = rt.LayerManager.getLayerFromName(lname) or \
            rt.LayerManager.newLayerFromName(lname)
        files = _json(rt.rootNode, _APP_FILES)
        files[lname] = dict(header=zf.header, section_tail=zf.section_tail,
                            footer=zf.footer, eol=zf.eol, source=path)
        _set_json(rt.rootNode, _APP_FILES, files)
        for i, z in enumerate(zf.zones):
            (x1, y1, z1), (x2, y2, z2) = z.bounds
            box = rt.Box(name="Zone_%s" % z.name if z.name else "Zone_%03d" % i,
                         width=max(x2 - x1, 0.1), length=max(y2 - y1, 0.1),
                         height=max(z2 - z1, 0.1),
                         pos=rt.Point3((x1 + x2) / 2.0, (y1 + y2) / 2.0, z1))
            _style(box, z.zone_type)
            _write(box, z.name, z.zone_type, z.level, z.gxt, i, lname)
            _set_json(box, _APP_BOX, dict(comment=z.comment, raw=z.raw))
            layer.addNode(box)
    _COUNT.clear()
    return len(zf.zones), zf


def _style(box, zone_type):
    rt = _rt()
    try:
        box.wirecolor = rt.color(*TYPE_COLORS.get(zone_type, _DEFAULT_COLOR))
        box.boxmode = True              # рамка вместо заливки (как в INU)
        box.renderable = False
    except Exception:                                  # noqa: BLE001
        pass


def _write(box, name, zone_type, level, gxt, index, lname):
    put_field([box], 'zon', True)
    put_field([box], 'zon_name', name)
    put_field([box], 'zon_type', int(zone_type))
    put_field([box], 'zon_level', int(level))
    put_field([box], 'zon_gxt', gxt or _core().DEFAULT_GXT)
    put_field([box], 'zon_index', int(index))
    put_field([box], 'zon_layer', lname)


# ── бокс → зона ──────────────────────────────────────────────────────

def _bounds(o):
    """Мировой габарит объекта (min / max узла Max)."""
    mn, mx = o.min, o.max
    return (float(mn.x), float(mn.y), float(mn.z)), (float(mx.x), float(mx.y),
                                                     float(mx.z))


def _zone_name(o):
    """Переименовал объект — переименовал зону; иначе — сохранённое имя."""
    stored = str(get_field(o, 'zon_name', '') or '')
    name = str(o.name)
    base = name[5:] if name.startswith('Zone_') else name
    if stored and base == stored:
        return stored
    return base or stored


def object_to_zone(o):
    zc = _core()
    (x1, y1, z1), (x2, y2, z2) = _bounds(o)
    extra = _json(o, _APP_BOX)
    return zc.Zone(name=_zone_name(o), zone_type=int(get_prop(o, 'zon_type', 0)),
                   x1=x1, y1=y1, z1=z1, x2=x2, y2=y2, z2=z2,
                   level=int(get_prop(o, 'zon_level', 0)),
                   gxt=str(get_field(o, 'zon_gxt', '') or zc.DEFAULT_GXT),
                   comment=list(extra.get('comment', [])),
                   raw=str(extra.get('raw', '') or ''))


def zone_from_bbox(o):
    """Зона по габариту любого объекта (здание, кусок земли) — тип 3."""
    zc = _core()
    (x1, y1, z1), (x2, y2, z2) = _bounds(o)
    return zc.Zone(name=str(o.name).replace(' ', '_'), zone_type=3,
                   x1=x1, y1=y1, z1=z1, x2=x2, y2=y2, z2=z2)


def lines_for_selection():
    """«Lines to clipboard»: строки .zon выделенного — боксы зон как есть,
    остальное — по габариту. Возвращает (строки, сколько по габариту)."""
    rt = _rt()
    objs = sorted(list(rt.selection), key=_order_key)
    lines, n_bbox = [], 0
    for o in objs:
        if is_zone(o):
            z = object_to_zone(o)
        else:
            z = zone_from_bbox(o)
            n_bbox += 1
        lines.append(_core().zone_line(z))
    return lines, n_bbox


# ── экспорт ──────────────────────────────────────────────────────────

def collect_for_export(path):
    """Что писать в path (как collect_for_export INU): выделенные боксы →
    слой по имени файла → единственный слой ZON_* → все зоны.
    Возвращает (боксы, 'ambiguous' | '')."""
    rt = _rt()
    sel = [o for o in rt.selection if is_zone(o)]
    if sel:
        return sel, ''
    zones = all_zones()
    lname = layer_name(path)
    mine = [o for o in zones if get_field(o, 'zon_layer', '') == lname]
    if mine:
        return mine, ''
    layers = {get_field(o, 'zon_layer', '') for o in zones}
    if len(layers) > 1:
        return [], 'ambiguous'
    return zones, ''


def export_zon(path, objects):
    """Записать боксы в .zon (старый файл — рядом как .bak). Нетронутые
    зоны пишутся исходной строкой. Возвращает (ZonFile, дубли имён)."""
    rt = _rt()
    zc = _core()
    objects = sorted(objects, key=_order_key)
    zf = zc.ZonFile()
    if objects:
        meta = _json(rt.rootNode, _APP_FILES).get(
            get_field(objects[0], 'zon_layer', ''), {})
        zf.header = list(meta.get('header', []))
        zf.section_tail = list(meta.get('section_tail', []))
        zf.footer = list(meta.get('footer', []))
        zf.eol = str(meta.get('eol') or "\r\n")
    seen, dups = set(), []
    for o in objects:
        z = object_to_zone(o)
        if z.name in seen:
            dups.append(z.name)
        seen.add(z.name)
        zf.zones.append(z)
    # .bak — исходник один раз, свои повторные экспорты его не затирают.
    if os.path.isfile(path) and not os.path.isfile(path + '.bak'):
        shutil.copy2(path, path + '.bak')
    zc.write_zon(path, zf)
    return zf, dups


def add_zone(path):
    """«New zone»: бокс 100×100×100 в центре выделения (в Blender — на
    3D-курсоре), тип 3, последним в своём слое."""
    rt = _rt()
    lname = layer_name(path or 'map.zon')
    try:
        c = rt.selection.center if len(list(rt.selection)) else rt.Point3(0, 0, 0)
        pos = rt.Point3(float(c.x), float(c.y), float(c.z) - 50.0)
    except Exception:                                  # noqa: BLE001
        pos = rt.Point3(0, 0, -50.0)
    mine = [o for o in all_zones() if get_field(o, 'zon_layer', '') == lname]
    index = max([int(get_prop(o, 'zon_index', 0)) for o in mine], default=-1) + 1
    with _undo("INU: Add zone"):
        box = rt.Box(name="Zone_NEW", width=100.0, length=100.0,
                     height=100.0, pos=pos)
        _style(box, 3)
        _write(box, "NEW", 3, 0, _core().DEFAULT_GXT, index, lname)
        layer = rt.LayerManager.getLayerFromName(lname) or \
            rt.LayerManager.newLayerFromName(lname)
        layer.addNode(box)
        rt.select(box)
    _COUNT.clear()
    return box


def rename(o, name):
    """Имя зоны → поле и имя бокса «Zone_<имя>» (пробелы → «_»: движок
    делит строку по пробелам)."""
    name = name.replace(' ', '_')
    if not name:
        return
    with _undo("INU: Rename zone"):
        put_field([o], 'zon_name', name)
        o.name = "Zone_" + name


def zero_size(o):
    """Схлопнутая по оси зона не поймает ни одной точки."""
    (x1, y1, z1), (x2, y2, z2) = _bounds(o)
    return min(x2 - x1, y2 - y1, z2 - z1) <= 0.001
