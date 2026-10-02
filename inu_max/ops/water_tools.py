"""Water DAT IO and block edits with interpolated per-vertex parameters."""
from dataclasses import asdict, fields
import json
import math
import os
import tempfile

from inu_gta_core.water import WaterVertex, WaterPolygon, WaterFile, read_water, write_water, check_quad_fit
from ..adapter import selection as S
from ..adapter.world import water_flag

_FIELDS = tuple(f.name for f in fields(WaterVertex))


def clip(vertices, axis, boundary, greater):
    out = []
    if not vertices:
        return out
    previous = vertices[-1]
    for current in vertices:
        a, b = getattr(previous, axis), getattr(current, axis)
        inside_a = a >= boundary - 1e-8 if greater else a <= boundary + 1e-8
        inside_b = b >= boundary - 1e-8 if greater else b <= boundary + 1e-8
        if inside_a != inside_b:
            t = (boundary - a) / (b - a)
            out.append(WaterVertex(**{f: getattr(previous, f) + t * (getattr(current, f) - getattr(previous, f))
                                      for f in _FIELDS}))
        if inside_b:
            out.append(current)
        previous = current
    unique = []
    for vertex in out:
        if not unique or any(abs(getattr(vertex, f) - getattr(unique[-1], f)) > 1e-7 for f in ('x', 'y', 'z')):
            unique.append(vertex)
    if len(unique) > 1 and all(abs(getattr(unique[0], f) - getattr(unique[-1], f)) < 1e-7 for f in ('x', 'y', 'z')):
        unique.pop()
    return unique


def split_polygon(polygon):
    verts = polygon.vertices
    x0, x1 = math.floor(min(v.x for v in verts) / 500), math.floor((max(v.x for v in verts) - 1e-7) / 500)
    y0, y1 = math.floor(min(v.y for v in verts) / 500), math.floor((max(v.y for v in verts) - 1e-7) / 500)
    if (x1 - x0 + 1) * (y1 - y0 + 1) > 10000:
        raise ValueError('Water polygon spans too many blocks')
    result = []
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            part = verts
            for axis, bound, greater in (('x', x * 500, True), ('x', (x + 1) * 500, False),
                                          ('y', y * 500, True), ('y', (y + 1) * 500, False)):
                part = clip(part, axis, bound, greater)
            if len(part) < 3:
                continue
            area = abs(sum(a.x * b.y - b.x * a.y for a, b in zip(part, part[1:] + part[:1])))
            if area < 1e-8:
                continue
            if len(part) <= 4:
                result.append(WaterPolygon(part, polygon.flag))
            else:
                result.extend(WaterPolygon([part[0], part[i], part[i + 1]], polygon.flag)
                              for i in range(1, len(part) - 1))
    return result


def _selected():
    return [node for node in S.selected_meshes() if water_flag(node) is not None]


def create_polygon(polygon, name='Water'):
    rt = S._rt()
    node = rt.Editable_Poly(name=rt.uniqueName(name))
    ids = [rt.polyop.createVert(node.baseObject, rt.Point3(v.x, v.y, v.z)) for v in polygon.vertices]
    rt.polyop.createPolygon(node.baseObject, rt.Array(*ids))
    S.put_field([node], 'water_flag', polygon.flag)
    S.put_field([node], 'type', 'NON')
    S.put_field([node], 'section', 'water')
    S.put_data([node], 'water_vertices', [asdict(v) for v in polygon.vertices])
    layer = rt.LayerManager.getLayerFromName('Water') or rt.LayerManager.newLayerFromName('Water')
    layer.addNode(node)
    rt.update(node)
    return node


def polygons(node):
    rt = S._rt()
    clone = rt.copy(node)
    try:
        rt.convertToPoly(clone)
        obj = clone.baseObject
        count = int(rt.polyop.getNumVerts(obj))
        metadata = S.get_data(node, 'water_vertices', [])
        if metadata and len(metadata) != count:
            raise ValueError('%s: topology changed; apply water parameters again' % node.name)
        defaults = dict(speed_x=S.get_field(node, 'water_speed_x', 0.0),
                        speed_y=S.get_field(node, 'water_speed_y', 0.0),
                        speed_z=S.get_field(node, 'water_speed_z', .05),
                        wave_height=S.get_field(node, 'water_wave_height', .1))
        verts = []
        for i in range(1, count + 1):
            pos = rt.polyop.getVert(obj, i) * clone.transform
            params = {k: metadata[i - 1].get(k, v) for k, v in defaults.items()} if metadata else defaults
            verts.append(WaterVertex(pos.x, pos.y, pos.z, **params))
        result = []
        for i in range(1, int(rt.polyop.getNumFaces(obj)) + 1):
            ids = list(rt.polyop.getFaceVerts(obj, i))
            face = [verts[int(j) - 1] for j in ids]
            if len(face) not in (3, 4):
                raise ValueError('%s: water faces must have 3 or 4 vertices' % node.name)
            result.append(WaterPolygon(face, water_flag(node)))
        return result
    finally:
        rt.delete(clone)


def import_water(path):
    water = read_water(path)
    rt = S._rt()
    with S.undo_block('INU: Import Water'):
        nodes = [create_polygon(polygon) for polygon in water.polygons]
        if nodes:
            rt.select(rt.Array(*nodes))
    rt.redrawViews()
    return 'INFO', 'Imported %d water polygons' % len(nodes)


def export_water(path):
    nodes = _selected() or [o for o in S._rt().geometry if water_flag(o) is not None]
    water = WaterFile([p for o in nodes for p in polygons(o)])
    if not water.polygons:
        return 'WARNING', 'No water polygons to export'
    invalid = [p for p in water.polygons if check_quad_fit(min(v.x for v in p.vertices), min(v.y for v in p.vertices),
                max(v.x for v in p.vertices), max(v.y for v in p.vertices)) != 'ok']
    if invalid:
        return 'ERROR', '%d polygons cross water block boundaries; split or snap them before export' % len(invalid)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix='.dat')
    os.close(fd)
    try:
        write_water(tmp, water)
        if len(read_water(tmp).polygons) != len(water.polygons):
            raise ValueError('Water DAT verification failed')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return 'INFO', 'Exported %d water polygons' % len(water.polygons)


def water_split_blocks():
    rt = S._rt()
    nodes = _selected()
    plan = [(node, [part for p in polygons(node) for part in split_polygon(p)]) for node in nodes]
    created = []
    with S.undo_block('INU: Split Water Blocks'):
        for source, parts in plan:
            created.extend(create_polygon(p, str(source.name) + '_Block') for p in parts)
            source.isHidden = True
            # Hidden source remains recoverable, but is excluded from DAT IO.
            S.put_field([source], 'water_active', False)
        if created:
            rt.select(rt.Array(*created))
    rt.redrawViews()
    return 'INFO', 'Created %d water block polygons' % len(created)


def water_snap_grid():
    rt = S._rt()
    nodes = _selected()
    with S.undo_block('INU: Snap Water Grid'):
        for node in nodes:
            if list(node.modifiers):
                raise ValueError('Collapse water modifiers before moving vertices')
            rt.convertToPoly(node)
            inverse = rt.inverse(node.transform)
            for i in range(1, int(rt.polyop.getNumVerts(node.baseObject)) + 1):
                p = rt.polyop.getVert(node.baseObject, i) * node.transform
                p.x, p.y = round(p.x / 4) * 4, round(p.y / 4) * 4
                rt.polyop.setVert(node.baseObject, i, p * inverse)
            rt.update(node)
    rt.redrawViews()
    return 'INFO', 'Snapped %d water objects to the 4-unit grid' % len(nodes)


def water_snap_block():
    rt = S._rt()
    plan = []
    for node in _selected():
        verts = [v for p in polygons(node) for v in p.vertices]
        bounds = [(min(getattr(v, a) for v in verts), max(getattr(v, a) for v in verts)) for a in ('x', 'y')]
        if any(hi - lo > 500 + .01 for lo, hi in bounds):
            return 'ERROR', 'Water larger than 500 must be split first'
        delta = []
        for lo, hi in bounds:
            block = math.floor(((lo + hi) / 2) / 500) * 500
            delta.append(max(block - lo, min(0, block + 500 - hi)))
        plan.append((node, rt.Point3(delta[0], delta[1], 0)))
    with S.undo_block('INU: Snap Water Block'):
        for node, offset in plan:
            node.pos += offset
    rt.redrawViews()
    return 'INFO', 'Aligned %d water objects to blocks' % len(plan)


def water_stitch(tolerance=.01):
    rt = S._rt()
    nodes = _selected()
    entries = []
    for node in nodes:
        if list(node.modifiers):
            raise ValueError('Collapse water modifiers before stitching')
        rt.convertToPoly(node)
        for i in range(1, int(rt.polyop.getNumVerts(node.baseObject)) + 1):
            p = rt.polyop.getVert(node.baseObject, i) * node.transform
            entries.append((node, i, p))
    # Spatial buckets, including neighbours: do not join distant points just
    # because they rounded to the same coarse grid cell.
    buckets, groups = {}, []
    for entry in entries:
        p = entry[2]
        key = tuple(math.floor(float(v) / tolerance) for v in (p.x, p.y, p.z))
        found = None
        for x in (-1, 0, 1):
            for y in (-1, 0, 1):
                for z in (-1, 0, 1):
                    for group in buckets.get((key[0] + x, key[1] + y, key[2] + z), ()):
                        if rt.distance(group[0][2], p) <= tolerance:
                            found = group
                            break
        if found is None:
            found = []
            buckets.setdefault(key, []).append(found)
            groups.append(found)
        found.append(entry)
    changed = 0
    with S.undo_block('INU: Stitch Water Edges'):
        for group in groups:
            if len(group) < 2:
                continue
            position = rt.Point3(0, 0, 0)
            for _, _, p in group:
                position += p
            position /= len(group)
            for node, index, _ in group:
                rt.polyop.setVert(node.baseObject, index, position * rt.inverse(node.transform))
                changed += 1
        for node in nodes:
            rt.update(node)
    rt.redrawViews()
    return 'INFO', 'Stitched %d water vertices (tolerance %g)' % (changed, tolerance)


def toggle_water_limits():
    rt = S._rt()
    old = [node for node in rt.objects if S.get_field(node, 'preview_kind', '') == 'water_limits']
    with S.undo_block('INU: Water Limits'):
        if old:
            for node in old:
                rt.delete(node)
        else:
            for axis in (0, 1):
                for value in range(-3000, 3001, 500):
                    line = rt.SplineShape(name=rt.uniqueName('INU_WaterLimit'))
                    rt.addNewSpline(line)
                    a = rt.Point3(value, -3000, 0) if axis == 0 else rt.Point3(-3000, value, 0)
                    b = rt.Point3(value, 3000, 0) if axis == 0 else rt.Point3(3000, value, 0)
                    for point in (a, b):
                        rt.addKnot(line, 1, rt.Name('corner'), rt.Name('line'), point)
                    rt.updateShape(line)
                    S.put_field([line], 'preview', True)
                    S.put_field([line], 'preview_kind', 'water_limits')
                    S.put_field([line], 'type', 'NON')
    rt.redrawViews()
    return 'INFO', 'Water limits ' + ('hidden' if old else 'shown')


OPERATIONS = {name: globals()[name] for name in ('import_water', 'export_water',
    'water_split_blocks', 'water_snap_grid', 'water_snap_block', 'water_stitch', 'toggle_water_limits')}
