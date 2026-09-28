# INU Tools (Max) — вкладка PreLight окна Lighting (порт операторов
# Lighting → Prelight Blender-версии INU: ops/light_ops.py,
# ops/prelight_preset_ops.py, tools/prelight.py).
#
# Каждая операция возвращает (уровень, текст) — окно показывает отчёт.
# Расчёт — ops/prelight_math.py (numpy), сцена — adapter/prelight_scene.py.

import time

import numpy as np

from .. import settings
from ..adapter.selection import undo_block


def _ps():
    from ..adapter import prelight_scene
    return prelight_scene


def _pm():
    from . import prelight_math
    return prelight_math


def _active():
    """«Активный» меш (первый выделенный с базой Editable Mesh)."""
    nodes, _other = _ps().selected_meshes()
    return nodes[0] if nodes else None


def _targets():
    nodes, other = _ps().selected_meshes()
    return nodes, other


def _other_note(other):
    return (" (%d object(s) skipped: not an Editable Mesh)" % len(other)) if other else ""


def _absorb(nodes, chans):
    """Мазки VertexPaint слоёв chans — в базу (инструмент работает с тем,
    что видно). Текст предупреждения или ''."""
    PS = _ps()
    skipped = []
    for chan in chans:
        skipped += PS.absorb_paint(nodes, chan)[1]
    if not skipped:
        return ""
    return ("VertexPaint strokes not merged (modifiers change the face count): %s"
            % ", ".join(sorted(set(skipped))[:5]))


# ── запекание ────────────────────────────────────────────────────────

_TYPE_KEYS = (('POINT', 'prelight_use_point'), ('SUN', 'prelight_use_sun'),
              ('SPOT', 'prelight_use_spot'), ('AREA', 'prelight_use_area'))


def bake(shadows=False, over=False):
    """«Bake» / «Bake over» (без теней, Ambient / Intensity / Gamma) и
    «Bake with shadows» / «Bake over (shadows)» — в активный слой (Day /
    Night) каждого выделенного меша."""
    PS, PM = _ps(), _pm()
    g = settings.get
    nodes, other = _targets()
    if not nodes:
        return 'ERROR', "Select mesh objects" + _other_note(other)
    allowed = {t for t, k in _TYPE_KEYS if g(k, True)}
    use_hdri = bool(g('prelight_use_hdri', False))
    lamps, skipped = PS.lights(allowed) if allowed else ([], {})
    notes = []
    env_col = None
    if use_hdri:
        env_col, has_map = PS.env_color()
        if has_map:
            notes.append("The environment map is not sampled yet — the background colour is used")
    if not lamps and not (use_hdri and env_col is not None):
        why = ("all light types are off (Point / Sun / Spot / Area)" if not allowed
               else "no visible lights in the scene")
        return 'WARNING', "Nothing to bake: %s." % why
    if shadows and not PS.fast():
        return 'ERROR', ("Bake with shadows needs the INU plugin: press Install / Update "
                         "INU in the launcher and restart 3ds Max.")
    model = 'SHADOWS' if shadows else 'SIMPLE'
    ambient = float(g('bake_ambient', 0.10))
    intensity = float(g('bake_intensity', 0.05))
    gamma = float(g('bake_gamma', 0.50))
    t0 = time.time()
    done, failed, layers = 0, [], set()
    if shadows:
        PS.occlusion_begin()
    try:
        with undo_block("INU: Bake Prelight"):
            by_chan = {}
            for node in nodes:
                by_chan.setdefault(PS.LAYER_CHAN[PS.active_layer(node)], []).append(node)
            for chan, group in by_chan.items():
                note = _absorb(group, [chan])
                if note:
                    notes.append(note)
            for node in nodes:
                geo = PS.bake_geometry(node)
                if geo is None or len(geo[1]) == 0:
                    failed.append(str(node.name))
                    continue
                pos, faces, n_c = geo
                layer = PS.active_layer(node)
                chan = PS.LAYER_CHAN[layer]
                sh = _shadows(PS, PM, lamps, pos, faces) if shadows else None
                env = None
                if use_hdri and env_col is not None:
                    env = np.tile(np.asarray(env_col, dtype=np.float32), (len(faces) * 3, 1))
                total = PM.light_total(pos, faces, n_c, lamps, sh, model=model,
                                       ambient=ambient, intensity=intensity,
                                       over=over, env=env)
                vals = PM.encode(total, model=model, gamma=gamma)
                if over:
                    old = PS.get_corners(node, chan)
                    if old is not None and len(old) == len(vals):
                        vals = PM.add_over(old, vals)
                else:
                    # свежий цвет → сдвиг V поля слоя накладывается заново
                    v = PS.v_value(node, layer)
                    if v != 0.0:
                        vals = PM.v_scale(vals, v, 0.0)
                    PS.set_v([node], layer, applied=v)
                PS.set_corners(node, chan, faces, vals)
                layers.add(layer)
                done += 1
    finally:
        if shadows:
            PS.occlusion_end()
    if not done:
        return 'WARNING', "Nothing baked" + (": " + ", ".join(failed[:5]) if failed else "")
    what = "/".join(sorted(layers))
    msg = ("Baked from lights: %d objects" if shadows else "Baked to '%s' from %%d objects" % what) % done
    msg += " (%d light(s)%s, %.1f s)" % (len(lamps), " + background" if env is not None else "",
                                          time.time() - t0)
    if skipped:
        notes.append("Not used: %s" % ", ".join("%d %s" % (n, k) for k, n in skipped.items()))
    if failed:
        notes.append("Not baked: %s" % ", ".join(failed[:5]))
    if other:
        notes.append(_other_note(other).strip(" ()"))
    return ('WARNING' if failed else 'INFO'), "\n".join([msg] + notes)


def _shadows(PS, PM, lamps, pos, faces):
    """{номер лампы: (nv,) 0/1} — один луч на вершину и лампу (как в INU)."""
    nrm_v = PM.vertex_normals(pos, faces)
    parts, spans = [], []
    for li, L in enumerate(lamps):
        rays, idx = PM.shadow_rays(L, pos, nrm_v)
        parts.append(rays)
        spans.append((li, idx, len(rays)))
    hits = PS.occluded(np.concatenate(parts)) if parts else np.zeros(0, dtype=bool)
    out, off = {}, 0
    for li, idx, n in spans:
        s = np.ones(len(pos), dtype=np.float32)
        s[idx[hits[off:off + n]]] = 0.0
        out[li] = s
        off += n
    return out


def reset_bake_settings():
    settings.set('bake_ambient', 0.10)
    settings.set('bake_intensity', 0.05)
    settings.set('bake_gamma', 0.50)
    return 'INFO', "Settings reset to default"


# ── лампы ────────────────────────────────────────────────────────────

def toggle_lights():
    PS = _ps()
    with undo_block("INU: Prelight lights"):
        if PS.lights_state()[0]:
            PS.remove_lights()
            return 'INFO', "Lights removed"
        PS.create_lights(PS.rig_center())
    return 'INFO', "Created 8 lights"


def toggle_sun():
    PS = _ps()
    with undo_block("INU: Prelight sun"):
        if PS.lights_state()[1]:
            PS.remove_sun()
            return 'INFO', "Sun removed"
        PS.create_sun(PS.rig_center())
    return 'INFO', "Sun created"


# ── слои Day / Night ─────────────────────────────────────────────────

def select_layer(name):
    """Активный слой. Есть VertexPaint слоя — он открывается в панели
    Modify (слой из модификатора), нет — слой из скрипта (превью)."""
    PS = _ps()
    nodes, _other = _targets()
    chan = PS.LAYER_CHAN[name]
    hit = [n for n in nodes if PS.has_channel(n, chan)]
    if not hit:
        return 'WARNING', "%s: not on the selected objects" % name
    PS.set_active_layer(hit, name)
    PS.refresh_preview(hit)
    note = PS.show_layer(hit, chan)
    return 'INFO', "Active: %s (%d objects)%s" % (name, len(hit), note)


def create_layer(name):
    PS = _ps()
    node = _active()
    if node is None:
        return 'ERROR', "Select a mesh object"
    chan = PS.LAYER_CHAN[name]
    if PS.has_channel(node, chan):
        return 'INFO', "%s already exists" % name
    with undo_block("INU: Create %s" % name):
        PS.fill_channel(node, chan, (1.0, 1.0, 1.0))
        PS.set_active_layer([node], name)
        PS.set_v([node], name, applied=0.0)
        PS.refresh_preview([node])
    return 'INFO', "Created: %s" % name


def remove_layer(name):
    PS = _ps()
    nodes, _other = _targets()
    chan = PS.LAYER_CHAN[name]
    n = 0
    with undo_block("INU: Remove %s" % name):
        for node in nodes:
            # слой — вместе с его VertexPaint (иначе мазки вернули бы канал)
            painted = PS.drop_paint([node], chan)
            if PS.drop_channel(node, chan) or painted:
                n += 1
                if PS.active_layer(node) == name:
                    PS.set_active_layer([node], 'Night' if name == 'Day' else 'Day')
                PS.refresh_preview([node])
    if not n:
        return 'ERROR', "%s not found" % name
    return 'INFO', "Removed %s: %d objects" % (name, n)


def copy_layer(src, dst):
    PS = _ps()
    nodes, _other = _targets()
    n = 0
    with undo_block("INU: %s to %s" % (src, dst)):
        note = _absorb(nodes, [PS.LAYER_CHAN[src], PS.LAYER_CHAN[dst]])
        for node in nodes:
            vals = PS.get_corners(node, PS.LAYER_CHAN[src])
            if vals is None:
                continue
            faces = PS.faces_of(node)
            if faces is None or len(faces) * 3 != len(vals):
                continue
            PS.set_corners(node, PS.LAYER_CHAN[dst], faces, vals)
            n += 1
    msg = "%s → %s: %d objects" % (src, dst, n)
    return ('WARNING', msg + "\n" + note) if note else ('INFO', msg)


def clear_alpha():
    """Убрать альфу вершин (канал -2): модель экспортируется без неё."""
    PS = _ps()
    nodes, _other = _targets()
    n = 0
    with undo_block("INU: Clear vertex alpha"):
        for node in nodes:
            # вместе с VertexPaint альфы (иначе мазки вернули бы канал)
            painted = PS.drop_paint([node], PS.ALPHA_CHAN)
            if PS.drop_channel(node, PS.ALPHA_CHAN) or painted:
                n += 1
                if PS.drop_channel(node, PS.ALPHA_VIEW_CHAN):
                    PS.update_display(node)
    if not n:
        return 'WARNING', "No vertex alpha on the selected objects"
    return 'INFO', "Vertex alpha cleared: %d objects" % n


def set_v(layer, value):
    """Поле V (сдвиг яркости слоя, %) — сразу на цвета активного меша."""
    PS, PM = _ps(), _pm()
    node = _active()
    if node is None:
        return 'ERROR', "Select a mesh object"
    chan = PS.LAYER_CHAN[layer]
    applied = PS.v_applied(node, layer)
    with undo_block("INU: V offset"):
        note = _absorb([node], [chan])
        if note:
            return 'WARNING', note
        PS.set_v([node], layer, value=value)
        vals = PS.get_corners(node, chan)
        if vals is None:
            return 'INFO', "V %s = %g (no %s colours yet)" % (layer, value, layer)
        faces = PS.faces_of(node)
        PS.set_corners(node, chan, faces, PM.v_scale(vals, value, applied))
        PS.set_v([node], layer, applied=value)
    k = max(0.0, 1.0 + value / 100.0) / max(0.001, 1.0 + applied / 100.0)
    return 'INFO', "V: %.0f → %.0f (x%.2f)" % (applied, value, k)


# ── превью ───────────────────────────────────────────────────────────

def _view():
    g = settings.get
    return (float(g('prelight_view_bright', 0.004)), float(g('prelight_view_contrast', 0.0)),
            float(g('prelight_view_gamma', 1.0)), float(g('prelight_view_saturation', 1.0)))


def _legacy_note():
    """Снять следы прошлой версии превью (обёртки материалов, лишние
    каналы); текст для сообщения, если что-то было."""
    wraps, nodes = _ps().repair_legacy()
    parts = []
    if wraps:
        parts.append("old preview wrappers removed: %d" % wraps)
    if nodes:
        parts.append("extra map channels removed: %d objects" % nodes)
    return (" (%s)" % "; ".join(parts)) if parts else ""


def preview(enable):
    PS = _ps()
    nodes, _other = _targets()
    if not nodes:
        return 'ERROR', "Select mesh objects"
    note = _legacy_note()
    n = PS.set_preview(nodes, enable, _view())
    return 'INFO', "Prelight preview %s: %d objects%s" % ("enabled" if enable else "disabled", n, note)


def view_update():
    _ps().update_view_all(_view())
    return 'INFO', ""


def view_reset():
    for k, v in (('prelight_view_bright', 0.0), ('prelight_view_contrast', 0.0),
                 ('prelight_view_gamma', 1.0), ('prelight_view_saturation', 1.0)):
        settings.set(k, v)
    _ps().update_view_all(_view())
    return 'INFO', "Preview correction: neutral"


def alpha_preview(enable):
    PS = _ps()
    note = _legacy_note()
    if enable:
        n = PS.set_alpha_preview(True)
        if not n:
            return 'WARNING', "No models with vertex alpha in the scene" + note
        return 'INFO', "Vertex alpha: models %d%s" % (n, note)
    PS.set_alpha_preview(False)
    return 'INFO', "Vertex alpha disabled" + note


# ── пресеты ──────────────────────────────────────────────────────────

def _payload(name):
    """Пресет из текущих настроек + активного меша + ламп (как INU)."""
    from .. import prelight_presets as PP
    PS = _ps()
    g = settings.get
    p = dict(PP.DEFAULT)
    p['name'] = name
    for field, key in PP.SETTINGS_KEYS.items():
        p[field] = g(key, PP.DEFAULT[field])
    node = _active()
    if node is not None:
        p['v_offset_day'] = PS.v_value(node, 'Day')
        p['v_offset_night'] = PS.v_value(node, 'Night')
        p['has_day_attr'] = PS.has_channel(node, 0)
        p['has_night_attr'] = PS.has_channel(node, -1)
    p['lights'] = [{'name': n, 'rel_offset': list(off),
                    'color': [c / 255.0 for c in rgb], 'energy': e, 'radius': 0.1}
                   for n, off, rgb, e in PS.lights_snapshot()]
    return p


def preset_save(name):
    from .. import prelight_presets as PP
    name = (name or '').strip()
    if not name:
        return 'ERROR', "Enter a preset name"
    if name == PP.DEFAULT_NAME:
        return 'ERROR', "'Default' is built-in and cannot be overwritten"
    PP.save(_payload(name))
    settings.set('prelight_preset', name)
    return 'INFO', "Preset saved: %s" % name


def preset_overwrite():
    from .. import prelight_presets as PP
    name = settings.get('prelight_preset', PP.DEFAULT_NAME)
    if name == PP.DEFAULT_NAME or PP.get(name) is None:
        return 'ERROR', "Select a saved preset (not 'Default')"
    old = PP.get(name)
    new = _payload(name)
    PP.save(new)
    changed = ["%s: %s→%s" % (k, old.get(k), new[k]) for k in new
               if k not in ('lights', 'name') and old.get(k) != new[k]]
    return 'INFO', "Overwritten: %s | %s" % (name, ", ".join(changed) if changed else "no changes")


def preset_delete():
    from .. import prelight_presets as PP
    name = settings.get('prelight_preset', PP.DEFAULT_NAME)
    if name == PP.DEFAULT_NAME:
        return 'ERROR', "'Default' cannot be deleted"
    PP.delete(name)
    settings.set('prelight_preset', PP.DEFAULT_NAME)
    return 'INFO', "Preset deleted: %s" % name


def preset_rename(new_name):
    from .. import prelight_presets as PP
    old = settings.get('prelight_preset', PP.DEFAULT_NAME)
    new_name = (new_name or '').strip()
    if old == PP.DEFAULT_NAME:
        return 'ERROR', "'Default' cannot be renamed"
    if not new_name:
        return 'ERROR', "Enter a new name"
    if new_name == old:
        return 'INFO', ""
    if new_name == PP.DEFAULT_NAME or PP.get(new_name) is not None:
        return 'ERROR', "Name already taken"
    p = PP.get(old)
    if p is None:
        return 'ERROR', "Preset not found"
    p['name'] = new_name
    PP.save(p)
    PP.delete(old)
    settings.set('prelight_preset', new_name)
    return 'INFO', "Renamed: %s → %s" % (old, new_name)


def preset_load():
    """«Apply»: настройки пресета, слои и сдвиги V на выделенных мешах,
    лампы пресета вокруг выделенного меша."""
    from .. import prelight_presets as PP
    PS, PM = _ps(), _pm()
    name = settings.get('prelight_preset', PP.DEFAULT_NAME)
    p = PP.get(name)
    if p is None:
        return 'ERROR', "Preset not found"
    for field, key in PP.SETTINGS_KEYS.items():
        if field in p:
            settings.set(key, p[field])
    nodes, _other = _targets()
    n_obj = n_attr = 0
    with undo_block("INU: Load Prelight preset"):
        for node in nodes:
            touched = False
            for layer, flag, vkey in (('Day', 'has_day_attr', 'v_offset_day'),
                                      ('Night', 'has_night_attr', 'v_offset_night')):
                if not p.get(flag):
                    continue
                chan = PS.LAYER_CHAN[layer]
                if not PS.has_channel(node, chan):
                    PS.fill_channel(node, chan, (1.0, 1.0, 1.0))
                    PS.set_v([node], layer, applied=0.0)
                    n_attr += 1
                v = float(p.get(vkey, 0.0))
                applied = PS.v_applied(node, layer)
                if v != applied:
                    vals = PS.get_corners(node, chan)
                    faces = PS.faces_of(node)
                    if vals is not None and faces is not None:
                        PS.set_corners(node, chan, faces, PM.v_scale(vals, v, applied))
                PS.set_v([node], layer, value=v, applied=v)
                touched = True
            n_obj += touched
        k_lamps = 0
        if p.get('lights'):
            rig = [(L.get('name', 'Prelight_Light'), tuple(L.get('rel_offset', (0, 0, 0))),
                    tuple(max(0.0, min(255.0, c * 255.0)) for c in L.get('color', (0.737,) * 3)),
                    float(L.get('energy', 10.0))) for L in p['lights']]
            PS.create_lights(PS.rig_center(), rig=rig)
            k_lamps = len(rig)
    return 'INFO', "Preset loaded: %s | %d objects, +%d attr | %d lamps" % (
        name, n_obj, n_attr, k_lamps)

