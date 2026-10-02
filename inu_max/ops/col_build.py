# INU Tools (Max) — сборка ColModel из нейтральных данных сцены (порт
# ops/col_export.py Blender-версии INU). Чистый Python: меши коллизии и тени,
# сферы и боксы читает adapter/scene_read.py.
#
# Геометрия — в системе модели (как DFF): вершины меша в системе узла с его
# масштабом, БЕЗ поворота и позиции (поворот — размещение модели в IPL).

import math
from dataclasses import dataclass, field

from inu_gta_core.col import (ColModel, ColFace, ColSphere, ColBox, Surface,
                              Bounds, Vec3)


@dataclass
class ColMesh:
    verts: list = field(default_factory=list)       # [(x,y,z)]
    faces: list = field(default_factory=list)       # [(a,b,c)] как в Max
    surfaces: list = field(default_factory=list)    # [(material, flags, brightness, light)]
    shadow: bool = False


@dataclass
class ColPrim:
    kind: str = 'SPHERE'                            # SPHERE | BOX
    center: tuple = (0.0, 0.0, 0.0)
    radius: float = 0.0
    bb_min: tuple = (0.0, 0.0, 0.0)
    bb_max: tuple = (0.0, 0.0, 0.0)
    surface: tuple = (0, 0, 0, 0)


def light_byte(day, night):
    """Байт света COL: день — младший полубайт, ночь — старший, каждое
    0..15 (больше 15 — 15, меньше 0 — 0; маска & 0xF превращала 16 в 0)."""
    d = max(0, min(15, int(day)))
    n = max(0, min(15, int(night)))
    return d | (n << 4)


def clamp_light(value):
    """u8; день/ночь в четвёртом байте верны только для COL1 в SA."""
    return max(0, min(255, int(value)))


def surface_of(props):
    """(material, flags, brightness, light) из GTA-свойств материала:
    свет — день в младшем полубайте, ночь в старшем (каждое 0..15)."""
    p = props or {}
    return (clamp_light(p.get('col_mat_index', 0)), clamp_light(p.get('col_flags', 0)),
            clamp_light(p.get('col_brightness', 0)),
            light_byte(p.get('col_day_light', 0), p.get('col_night_light', 0)))


def _area(a, b, c):
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    x = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return 0.5 * math.sqrt(x[0] ** 2 + x[1] ** 2 + x[2] ** 2)


def auto_light_byte(auto_light):
    """Байт света режима «Авто» или None (режим «Из материала»).
    auto_light = (mode, day, night), mode — 'AUTO' | 'MATERIAL'
    (как gtatools_col_light_mode Blender-версии)."""
    mode, day, night = auto_light
    return light_byte(day, night) if mode == 'AUTO' else None


def _add_mesh(cm, model, auto_light):
    """Треугольники меша → вершины/грани модели (или тени). Вырожденные
    грани (площадь < 1e-4, либо схлопнувшиеся на сетке 1/128 у COL2+)
    выбрасываются, висячие вершины — тоже (как _drop_degenerate_faces)."""
    compressed = model.version >= 2
    keep = []
    for f, (a, b, c) in enumerate(cm.faces):
        pa, pb, pc = cm.verts[a], cm.verts[b], cm.verts[c]
        if _area(pa, pb, pc) < 1e-4:
            continue
        if compressed and len({tuple(round(x * 128) for x in p) for p in (pa, pb, pc)}) < 3:
            continue
        keep.append(f)
    verts = model.shadow_vertices if cm.shadow else model.vertices
    faces = model.shadow_faces if cm.shadow else model.faces
    forced = None if cm.shadow else auto_light_byte(auto_light)
    remap = {}
    for f in keep:
        for vi in cm.faces[f]:
            if vi not in remap:
                remap[vi] = len(verts)
                x, y, z = cm.verts[vi]
                verts.append(Vec3(float(x), float(y), float(z)))
    for f in keep:
        a, b, c = cm.faces[f]
        s = cm.surfaces[f] if f < len(cm.surfaces) else (0, 0, 0, 0)
        surf = Surface(material=s[0], flags=s[1], brightness=s[2], light=s[3])
        # «Авто»: единые день/ночь на ВСЮ коллизию (поверх материалов);
        # «Из материала»: свет, заданный на COL-материале. Тень не трогаем.
        if forced is not None:
            surf.light = forced
        # обход GTA: b и c меняются местами
        faces.append(ColFace(remap[a], remap[c], remap[b], surf))
    return len(cm.faces) - len(keep)


def _add_prim(p, model, auto_light):
    forced = auto_light_byte(auto_light)
    s = Surface(material=p.surface[0], flags=p.surface[1],
                brightness=p.surface[2],
                light=p.surface[3])
    if forced is not None:
        if model.version >= 2:
            s.brightness = forced
        else:
            s.light = forced
    if p.kind == 'BOX':
        lo = [min(p.bb_min[i], p.bb_max[i]) for i in range(3)]
        hi = [max(p.bb_min[i], p.bb_max[i]) for i in range(3)]
        model.boxes.append(ColBox(bb_min=Vec3(*lo), bb_max=Vec3(*hi), surface=s))
    else:
        model.spheres.append(ColSphere(center=Vec3(*p.center), radius=float(p.radius),
                                       surface=s))


def compute_bounds(model):
    """Сфера + AABB по КОЛЛИЗИИ (без тени; радиус — до самой дальней точки,
    как _compute_bounds INU). Только тень — по ней."""
    has_col = bool(model.vertices) or bool(model.spheres) or bool(model.boxes)
    verts = model.vertices if has_col else model.shadow_vertices
    if not (verts or model.spheres or model.boxes):
        return Bounds()
    pts = [(v.x, v.y, v.z) for v in verts]
    for s in model.spheres:
        r = s.radius
        pts += [(s.center.x - r, s.center.y - r, s.center.z - r),
                (s.center.x + r, s.center.y + r, s.center.z + r)]
    for b in model.boxes:
        pts += [(b.bb_min.x, b.bb_min.y, b.bb_min.z), (b.bb_max.x, b.bb_max.y, b.bb_max.z)]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    c = [(lo[i] + hi[i]) / 2.0 for i in range(3)]

    def dist(x, y, z):
        return math.sqrt((x - c[0]) ** 2 + (y - c[1]) ** 2 + (z - c[2]) ** 2)
    r = max([dist(v.x, v.y, v.z) for v in verts] or [0.0])
    for s in model.spheres:
        r = max(r, dist(s.center.x, s.center.y, s.center.z) + s.radius)
    for b in model.boxes:
        for x in (b.bb_min.x, b.bb_max.x):
            for y in (b.bb_min.y, b.bb_max.y):
                for z in (b.bb_min.z, b.bb_max.z):
                    r = max(r, dist(x, y, z))
    return Bounds(center=Vec3(*c), radius=r, bb_min=Vec3(*lo), bb_max=Vec3(*hi))


def build_model(name, version, meshes=(), prims=(), auto_light=('MATERIAL', 0, 0),
                empty=False, bounds_meshes=()):
    """ColModel. empty=True — без геометрии, но с настоящими границами по
    видимой модели (bounds_meshes): нулевая сфера — модель в игре пропадает."""
    model = ColModel(version=version, model_name=name[:21])
    if empty:
        tmp = ColModel(version=version)
        for cm in bounds_meshes:
            _add_mesh(ColMesh(cm.verts, cm.faces, [], False), tmp, ('MATERIAL', 0, 0))
        model.bounds = compute_bounds(tmp)
        return model, 0
    dropped = 0
    for cm in meshes:
        dropped += _add_mesh(cm, model, auto_light)
    for p in prims:
        _add_prim(p, model, auto_light)
    model.bounds = compute_bounds(model)
    return model, dropped
