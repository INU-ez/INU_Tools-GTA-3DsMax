"""Per-object pipeline flag snapshots, persisted in Max user properties."""
from .. import settings
from ..adapter.selection import FLAG_DEFAULTS

FLAGS = tuple(FLAG_DEFAULTS)
SNAP = {'0x53F2009A': 'flags_snap_vehicle', '0x53F20098': 'flags_snap_dn',
        '0x53F2009C': 'flags_snap_building', 'PED': 'flags_snap_ped'}
FORCE_OFF = {'0x53F20098': ('light',)}
VERSION = 1


def pack(values):
    return ''.join('1' if values.get(k, FLAG_DEFAULTS[k]) else '0' for k in FLAGS)


def unpack(raw):
    if not isinstance(raw, str) or not raw or any(c not in '01' for c in raw):
        return None
    return {k: c == '1' for k, c in zip(FLAGS, raw)}


def global_defaults(pipeline):
    data = settings.get('pipe_flag_defaults', {}) or {}
    if data.get('version') != VERSION:
        return None
    value = data.get('pipelines', {}).get(pipeline)
    return value if isinstance(value, dict) else None


def save_global(pipeline, values):
    if pipeline not in SNAP:
        return
    data = settings.get('pipe_flag_defaults', {}) or {}
    pipelines = dict(data.get('pipelines', {})) if data.get('version') == VERSION else {}
    pipelines[pipeline] = {k: bool(values.get(k, FLAG_DEFAULTS[k])) for k in FLAGS}
    settings.set('pipe_flag_defaults', {'version': VERSION, 'pipelines': pipelines})


def plan(objects, old, new, global_new=None):
    if old == new or old not in SNAP and new not in SNAP:
        return []
    out = []
    for obj in objects:
        if obj.get('col_prim', ''):
            continue
        live = {k: bool(obj.get(k, d)) for k, d in FLAG_DEFAULTS.items()}
        updates = {}
        if old in SNAP:
            raw = pack(live)
            if obj.get(SNAP[old], '') != raw:
                updates[SNAP[old]] = raw
        restored = unpack(obj.get(SNAP.get(new, ''), '')) if new in SNAP else None
        if restored is None and new in SNAP:
            restored = global_new
        wanted = dict(live)
        if isinstance(restored, dict):
            wanted.update({k: bool(v) for k, v in restored.items() if k in FLAGS})
        for k in FORCE_OFF.get(new, ()):
            wanted[k] = False
        updates.update({k: v for k, v in wanted.items() if live[k] != v})
        if updates:
            out.append((obj, updates))
    return out


def scene_pipeline():
    from ..adapter.selection import _rt
    rt = _rt()
    i = rt.fileProperties.findProperty(rt.Name('custom'), 'INU_Pipeline')
    return str(rt.fileProperties.getPropertyValue(rt.Name('custom'), i)) if i else ''


def set_scene_pipeline(value):
    from ..adapter.selection import _rt
    rt = _rt()
    rt.fileProperties.addProperty(rt.Name('custom'), 'INU_Pipeline', str(value))


def switch(old, new):
    if old == new or old not in SNAP and new not in SNAP:
        return
    import pymxs
    from ..adapter import link_scene
    updates = plan(link_scene.index(), old, new, global_defaults(new))
    with pymxs.undo(False):
        for obj, values in updates:
            obj.put(values)


def set_pipeline(new):
    try:
        old = scene_pipeline() or settings.get('export_pipeline', 'NONE')
    except (ImportError, AttributeError):
        old = settings.get('export_pipeline', 'NONE')
    try:
        try:
            switch(old, new)
        except ImportError:
            # Settings-only use outside the Max host.
            pass
    finally:
        settings.set('export_pipeline', new)
        try:
            set_scene_pipeline(new)
        except (ImportError, AttributeError):
            pass
