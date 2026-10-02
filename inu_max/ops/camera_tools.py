"""GTA cutscene cameras (four DAT blocks, 2048-byte padding)."""
import math
import os
import tempfile

from ..adapter import selection as S, anim as A
from .. import settings


def read_camera(path):
    with open(path, 'rb') as stream:
        text = stream.read().rstrip(b'\x00').decode('ascii')
    blocks = text.split(';')
    result = {}
    for name, block, width in zip(('fov', 'roll', 'pos', 'target'), blocks, (4, 4, 10, 10)):
        rows = [[float(v.strip().rstrip('fF')) for v in line.split(',') if v.strip()]
                for line in block.splitlines() if line.strip()]
        if not rows or len(rows[0]) != 1 or int(rows[0][0]) != len(rows) - 1:
            raise ValueError('Invalid camera DAT block: ' + name)
        if any(len(row) != width for row in rows[1:]):
            raise ValueError('Invalid camera DAT key: ' + name)
        result[name] = [tuple(row[:2] if width == 4 else row[:4]) for row in rows[1:]]
    if len(result) != 4 or any(not result[k] for k in ('pos', 'target')):
        raise ValueError('Camera DAT needs position and target blocks')
    return result


def write_camera(path, keys):
    lines = []
    for name in ('fov', 'roll', 'pos', 'target'):
        rows = keys[name]
        lines.append('%d,' % len(rows))
        for row in rows:
            if any(not math.isfinite(v) for v in row):
                raise ValueError('Camera keys must be finite')
            values = [row[0]] + list(row[1:]) * 3
            lines.append(','.join('%.9g' % v for v in values) + ',')
        lines.append(';')
    lines.append(';')
    data = ('\n'.join(lines) + '\n').encode('ascii')
    data += b'\x00' * ((-len(data)) % 2048)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix='.dat')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        read_camera(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def import_camera(path):
    import pymxs
    keys = read_camera(path)
    rt = S._rt()
    fps = A.frame_rate()
    offset = -1 if settings.get('cam_z_import', True) else 0
    with S.undo_block('INU: Import Camera DAT'):
        target = rt.TargetObject(name=rt.uniqueName('INU_CameraTarget'))
        camera = rt.Targetcamera(name=rt.uniqueName(os.path.splitext(os.path.basename(path))[0]), target=target)
        camera.fovType = 2
        for name, node in (('pos', camera), ('target', target)):
            for time, x, y, z in keys[name]:
                with pymxs.animate(True), pymxs.attime(time * fps):
                    node.pos = rt.Point3(x, y, z + offset)
        for time, value in keys['fov']:
            with pymxs.animate(True), pymxs.attime(time * fps):
                aspect = float(rt.renderWidth) / max(1, float(rt.renderHeight))
                camera.fov = math.degrees(2 * math.atan(math.tan(math.radians(value) / 2) * aspect))
        for time, value in keys['roll']:
            with pymxs.animate(True), pymxs.attime(time * fps):
                z = rt.normalize(camera.pos - target.pos)
                x = rt.cross(rt.Point3(0, 0, 1), z)
                if rt.length(x) < 1e-6:
                    x = rt.Point3(1, 0, 0)
                x = rt.normalize(x)
                y = rt.normalize(rt.cross(z, x))
                angle = math.radians(value)
                camera.transform = rt.Matrix3(x * math.cos(angle) + y * math.sin(angle),
                    y * math.cos(angle) - x * math.sin(angle), z, camera.pos)
        end = max(row[0] for rows in keys.values() for row in rows)
        rt.animationRange = rt.Interval(0, end * fps)
        rt.select(camera)
    rt.redrawViews()
    return 'INFO', 'Imported camera ' + str(camera.name)


def export_camera(path):
    import pymxs
    camera = S.active_node()
    if not A.is_camera(camera):
        raise ValueError('Select a camera to export')
    rt = S._rt()
    fps = A.frame_rate()
    offset = 1 if settings.get('cam_z_export', True) else 0
    start, end = int(rt.animationRange.start.frame), int(rt.animationRange.end.frame)
    if end - start > 100000:
        raise ValueError('Camera animation exceeds 100000 frames')
    keys = {name: [] for name in ('fov', 'roll', 'pos', 'target')}
    for frame in range(start, end + 1):
        with pymxs.attime(frame):
            time = (frame - start) / fps
            p = camera.pos
            target = getattr(camera, 'target', None)
            q = target.pos if target is not None else p - camera.transform.row3 * 10
            keys['pos'].append((time, p.x, p.y, p.z + offset))
            keys['target'].append((time, q.x, q.y, q.z + offset))
            fov = float(camera.fov)
            aspect = float(rt.renderWidth) / max(1, float(rt.renderHeight))
            fov = math.degrees(2 * math.atan(math.tan(math.radians(fov) / 2) / aspect))
            keys['fov'].append((time, fov))
            z = rt.normalize(camera.transform.row3)
            x = rt.cross(rt.Point3(0, 0, 1), z)
            x = rt.normalize(x) if rt.length(x) > 1e-6 else rt.Point3(1, 0, 0)
            y = rt.normalize(rt.cross(z, x))
            roll = math.degrees(math.atan2(rt.dot(camera.transform.row1, y), rt.dot(camera.transform.row1, x)))
            keys['roll'].append((time, roll))
    write_camera(path, keys)
    return 'INFO', 'Exported camera DAT: ' + path


OPERATIONS = {name: globals()[name] for name in ('import_camera', 'export_camera')}
