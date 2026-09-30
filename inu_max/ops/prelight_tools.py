# INU Tools (Max) — окно Lighting, часть 2: роллауты Tools, Foliage / Tree и
# Post-Processing (порт операторов ops/light_ops.py Blender-версии INU:
# fill_prelight, prelight_merge_paint / split_paint, scatter_color,
# vc_smooth_between, prelight_foliage, foliage_color_reset, vc_smooth,
# vc_contrast, vc_brightness, vc_gamma, lift_shadows); часть 3: вкладка
# PreLight COL (tools/col_light.py: bake_col_light, clear_col_light_mats,
# preview_col_light); часть 4: LightMap UV2 (ops/texture_ops.py).
#
# Формулы — ops/prelight_math.py. Операции пишут в АКТИВНЫЙ слой (Day /
# Night) каждого меша; мазки VertexPaint этого слоя сперва вписываются в
# базу (решение пользователя). Каждая операция возвращает (уровень, текст).

import os

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
    nodes, _other = _ps().selected_meshes()
    return nodes[0] if nodes else None


def _layer(node):
    PS = _ps()
    return PS.active_layer(node), PS.LAYER_CHAN[PS.active_layer(node)]


def _read(node, chan):
    """(значения слоя, грани) после вписывания мазков VertexPaint, или
    (None, None), если слоя нет / модификаторы меняют число граней."""
    PS = _ps()
    PS.absorb_paint([node], chan)
    vals = PS.get_corners(node, chan)
    if vals is None:
        return None, None
    faces = PS.faces_of(node)
    if faces is None or len(faces) * 3 != len(vals):
        return None, None
    return vals, faces


def _g(key, default):
    return settings.get(key, default)


def _rgb(key, default):
    v = settings.get(key, default)
    try:
        return tuple(float(c) for c in list(v)[:3])
    except (TypeError, ValueError):
        return tuple(default)


# ── Post-Processing ───────────────────────────────────────────────────

def _post(label, undo_label, fn):
    """Операция над активным слоем каждого выделенного меша."""
    PS = _ps()
    nodes, _other = PS.selected_meshes()
    if not nodes:
        return 'ERROR', "Select mesh objects"
    count = 0
    with undo_block(undo_label):
        for node in nodes:
            _name, chan = _layer(node)
            vals, faces = _read(node, chan)
            if vals is None:
                continue
            out = fn(vals, faces)
            if out is None:
                continue
            PS.set_corners(node, chan, faces, out)
            count += 1
    return ('INFO' if count else 'WARNING'), label % count


def vc_smooth():
    it = int(_g('vc_smooth_iterations', 1))
    f = float(_g('vc_smooth_factor', 0.5))
    PM = _pm()
    return _post("Smooth: %d objects", "INU: Smooth Vertex Colors",
                 lambda v, fc: PM.pp_smooth(v, fc, int(fc.max()) + 1, it, f))


def vc_contrast():
    c = float(_g('vc_contrast', 1.0))
    return _post("Contrast: %d objects", "INU: Apply Contrast",
                 lambda v, fc: _pm().pp_contrast(v, c))


def vc_brightness():
    b = float(_g('vc_brightness', 0.0))
    return _post("Brightness: %d objects", "INU: Apply Brightness",
                 lambda v, fc: _pm().pp_brightness(v, b))


def vc_gamma():
    g = float(_g('vc_gamma', 1.0))
    if g <= 0.0:
        return 'ERROR', "Gamma must be > 0"
    return _post("Gamma: %d objects", "INU: Apply Gamma",
                 lambda v, fc: _pm().pp_gamma(v, g))


def lift_shadows():
    s = float(_g('lift_shadows_strength', 0.5))
    if s <= 0.0:
        return 'INFO', "Strength is zero — nothing to do"
    level, text = _post("Lift shadows: %d objects", "INU: Lift Shadows",
                        lambda v, fc: _pm().pp_lift_shadows(v, s))
    return level, text + " (strength=%.2f)" % s


# ── Инструменты ───────────────────────────────────────────────────────

def fill_prelight():
    """«Fill with one color»: Day и Night — плоским цветом (байт в байт из
    палитры). Только выделенные меши или все меши сцены (как в Blender)."""
    PS = _ps()
    from ..adapter.selection import get_flags, set_flag
    day = _rgb('fill_prelight_day', (124 / 255.0,) * 3)
    night = _rgb('fill_prelight_night', (83 / 255.0,) * 3)
    if _g('fill_prelight_selected_only', False):
        nodes, _other = PS.selected_meshes()
    else:
        nodes = PS.scene_meshes()
    if not nodes:
        return 'ERROR', "No meshes to fill"
    rt = PS._rt()
    count = 0
    done = set()
    with undo_block("INU: Fill Prelight"):
        for node in nodes:
            key = int(rt.getHandleByAnim(node.baseObject))   # инстансы — один раз
            if key in done or PS.face_count(node) == 0:
                continue
            done.add(key)
            for chan, rgb in ((0, day), (-1, night)):
                PS.absorb_paint([node], chan)
                PS.fill_channel(node, chan, rgb)
            PS.set_active_layer([node], 'Day')
            flags = get_flags(node)
            for k in ('day_cols', 'night_cols'):
                if not flags.get(k, True):
                    set_flag([node], k, True)
            count += 1
    d8 = tuple(int(round(c * 255)) for c in day)
    n8 = tuple(int(round(c * 255)) for c in night)
    return 'INFO', "Prelight filled: %d meshes. Day=%s Night=%s" % (count, d8, n8)


def merge_paint():
    """«Merge»: временная общая модель из выделенных мешей для покраски."""
    PS = _ps()
    nodes, _other = PS.selected_meshes()
    if len(nodes) < 2:
        return 'ERROR', "Select 2+ meshes"
    if PS.merge_proxy() is not None:
        return 'ERROR', "A merge already exists — Split it first"
    with undo_block("INU: Merge for Prelight Paint"):
        obj, n, skipped = PS.merge_build(nodes)
    if obj is None:
        return 'ERROR', "Empty meshes"
    msg = "Merged for painting: %d (add a VertexPaint modifier to paint)" % n
    if skipped:
        return 'WARNING', msg + "\nSkipped: %s" % ", ".join(skipped[:5])
    return 'INFO', msg


def split_paint():
    """«Split»: покраска модели — обратно на оригиналы, модель удаляется."""
    PS = _ps()
    node = _active()
    from ..adapter.selection import get_field
    proxy = node if node is not None and get_field(node, PS.MERGE_KEY, '') else PS.merge_proxy()
    if proxy is None:
        return 'ERROR', "No merged model"
    with undo_block("INU: Split Prelight Paint"):
        back, total = PS.merge_split(proxy)
    if back < total:
        return 'WARNING', "Split: %d (%d not matched — the mesh changed)" % (back, total - back)
    return 'INFO', "Split: %d" % back


def scatter_color():
    """«Scatter color»: цвет вокруг выделенных граней активного меша с
    убыванием по расстоянию. Цвет — кисти VertexPaint (если открыт), иначе
    палитра окна (решение пользователя)."""
    PS, PM = _ps(), _pm()
    node = _active()
    if node is None:
        return 'ERROR', "Select a mesh!"
    sel = PS.selected_faces(node)
    if not len(sel):
        return 'ERROR', "No faces selected"
    color = PS.paint_color() or _rgb('scatter_color_color', (1.0, 1.0, 1.0))
    _name, chan = _layer(node)
    with undo_block("INU: Scatter Color"):
        vals, faces = _read(node, chan)
        if vals is None:
            return 'ERROR', "No active color layer!"
        geo = PS.local_geometry(node)
        if geo is None or len(geo[1]) != len(faces):
            return 'ERROR', "No active color layer!"
        out, n_sel, n_aff, rad = PM.scatter_color(
            vals, geo[0], faces, sel, PM.srgb2lin(np.asarray(color, dtype=np.float32)),
            float(_g('scatter_color_strength', 1.0)), float(_g('scatter_color_distance', 0.3)))
        PS.set_corners(node, chan, faces, out)
    return 'INFO', ("Scattered color around %d selected → %d affected verts (radius %.2f)"
                    % (n_sel, n_aff, rad))


def smooth_between():
    """«Smooth between objects»: цвета на стыках выделенных мешей."""
    PS, PM = _ps(), _pm()
    nodes, _other = PS.selected_meshes()
    if len(nodes) < 2:
        return 'ERROR', "Select at least 2 mesh objects"
    items, data = [], []
    with undo_block("INU: Smooth Between Objects"):
        for node in nodes:
            _name, chan = _layer(node)
            vals, faces = _read(node, chan)
            if vals is None:
                continue
            geo = PS.bake_geometry(node)
            if geo is None or len(geo[1]) != len(faces):
                continue
            items.append((node, chan, faces))
            data.append((geo[0], faces, vals))
        if not items:
            return 'WARNING', "No vertex colors"
        outs, seams = PM.smooth_between(data)
        for (node, chan, faces), out in zip(items, outs):
            PS.set_corners(node, chan, faces, out)
    return 'INFO', "Smoothed seams: %d" % seams


# ── Листва / Дерево ───────────────────────────────────────────────────

def foliage(mode):
    """«Prelight the crown» (mode SHADE) / «Bake color» (mode COLOR)."""
    PS, PM = _ps(), _pm()
    node = _active()
    if node is None:
        return 'ERROR', "Select a tree mesh"
    key = 'foliage_color_material_name' if mode == 'COLOR' else 'foliage_material_name'
    name = str(_g(key, '') or '').strip()
    geo = PS.local_geometry(node)
    if geo is None or len(geo[1]) == 0:
        return 'ERROR', "Mesh has no loops"
    pos, faces = geo
    mask = np.ones(len(faces), dtype=bool)
    if name:
        slot = next((s for s in PS.material_slots(node) if s[0] == name), None)
        if slot is None:
            return 'WARNING', "Material «%s» not found on the object" % name
        if slot[1] is not None:
            mask &= PS.face_matids(node) == slot[1]
    if _g('foliage_select_only', False):
        sel = np.zeros(len(faces), dtype=bool)
        sel[PS.selected_faces(node)] = True
        mask &= sel
    layer, chan = _layer(node)
    with undo_block("INU: Foliage Prelight"):
        vals, fc = _read(node, chan)
        if vals is None:
            if PS.has_channel(node, chan):
                return 'ERROR', "Mesh has no loops"
            vals = np.ones((len(faces) * 3, 3), dtype=np.float32)   # слоя нет — белая база
        elif len(fc) != len(faces):
            return 'ERROR', "Mesh has no loops"
        if mode == 'COLOR':                     # снимок для «Reset»
            PS.foliage_backup()[PS.node_handle(node)] = (chan, np.array(vals), len(faces))
        out, n = PM.foliage(
            vals, pos, faces, mask, mode=mode,
            inside=float(_g('foliage_inside', 0.25)), outside=float(_g('foliage_outside', 1.0)),
            gamma=float(_g('foliage_gamma', 1.0)), height_dark=float(_g('foliage_height_dark', 0.0)),
            color_height_dark=float(_g('foliage_color_height_dark', 0.0)),
            top_bright=float(_g('foliage_top_bright', 0.0)),
            top_height=float(_g('foliage_top_height', 1.0)),
            variation=float(_g('foliage_variation', 0.0)),
            light_tint=_rgb('foliage_light_tint', (0.55, 0.8, 0.3)),
            shadow_tint=_rgb('foliage_shadow_tint', (0.2, 0.35, 0.12)),
            tint_strength=float(_g('foliage_tint_strength', 1.0)),
            metric=str(_g('foliage_metric', 'SPHERE')), blend=str(_g('foliage_blend', 'MULTIPLY')),
            both_sides=bool(_g('foliage_both_sides', True)))
        if out is None:
            return 'WARNING', n
        PS.set_corners(node, chan, faces, out)
    return 'INFO', "Foliage prelight → '%s' (%d loops)" % (layer, n)


def foliage_reset():
    """«Reset»: слой — к снимку, сделанному при «Bake color»."""
    PS = _ps()
    node = _active()
    if node is None:
        return 'ERROR', "Select a tree mesh"
    snap = PS.foliage_backup().get(PS.node_handle(node))
    if snap is None:
        return 'WARNING', 'No saved prelight — "Bake color" first'
    chan, vals, nf = snap
    faces = PS.faces_of(node)
    if faces is None or len(faces) != nf:
        return 'WARNING', "The saved prelight does not match (the mesh changed)"
    with undo_block("INU: Foliage Color Reset"):
        PS.absorb_paint([node], chan)
        PS.set_corners(node, chan, faces, vals)
    return 'INFO', 'Prelight reset to the state before "Bake color"'


# ── часть 3: PreLight COL ─────────────────────────────────────────────

def _col_curve():
    return (float(_g('col_light_edge', 0.0)), float(_g('col_light_contrast', 0.0)),
            int(_g('col_light_threshold', 0)))


def col_bake():
    """«Bake COL Light»: цвет вершин активного меша (Day / Night) → свет COL
    его материалов, разные уровни — копиями «_dN_nN»."""
    PS, PM = _ps(), _pm()
    node = _active()
    if node is None:
        return 'ERROR', "Select a mesh!"
    day_chan = 0 if PS.has_channel(node, 0) else _layer(node)[1]
    night_chan = -1 if PS.has_channel(node, -1) else day_chan
    edge, contrast, thr = _col_curve()
    with undo_block("INU: Bake COL Light"):
        vd, faces = _read(node, day_chan)
        if vd is None:
            return 'ERROR', "No vertex color layer found"
        vn = _read(node, night_chan)[0] if night_chan != day_chan else vd
        if vn is None:
            vn = vd
        d = PM.col_levels(vd, _g('col_day_min', 10), _g('col_day_max', 15), edge, contrast, thr)
        n = PM.col_levels(vn, _g('col_night_min', 0), _g('col_night_max', 5), edge, contrast, thr)
        new, skipped = PS.col_bake_node(node, d, n)
    col_preview_update()
    notes = []
    if skipped:
        notes.append("%d faces without a material were skipped" % skipped)
    if _g('col_light_mode', 'AUTO') == 'AUTO':
        notes.append("Export 'Collision light' = Auto: every face will be exported as Day %d / "
                     "Night %d. Switch it to 'From material' to export the baked values"
                     % (int(_g('col_auto_day', 14)), int(_g('col_auto_night', 4))))
    msg = "COL Light baked: %d new materials, %d polygons" % (new, len(faces))
    return ('WARNING' if notes else 'INFO'), "\n".join([msg] + notes)


def col_clear():
    """«×»: убрать COL light материалы, созданные «Bake COL Light»."""
    PS = _ps()
    node = _active()
    if node is None:
        return 'ERROR', "Select a mesh!"
    with undo_block("INU: Clear COL Light"):
        n = PS.col_clear_node(node)
    if not n:
        return 'INFO', "No COL light materials to clear"
    return 'INFO', "Cleared %d COL light materials" % n


def _col_preview_on(node):
    """Превью по АКТИВНОМУ слою меша и его диапазону (как в Blender)."""
    PS, PM = _ps(), _pm()
    layer, chan = _layer(node)
    vals = PS.get_corners(node, chan)
    faces = PS.faces_of(node)
    geo = PS.local_geometry(node)
    if vals is None or faces is None or geo is None or len(faces) * 3 != len(vals):
        return 'WARNING', "No vertex colors"
    if layer == 'Night':
        vmin, vmax = _g('col_night_min', 0), _g('col_night_max', 5)
    else:
        vmin, vmax = _g('col_day_min', 10), _g('col_day_max', 15)
    lv = PM.col_levels(vals, vmin, vmax, *_col_curve())
    PS.col_preview_set(node, faces, lv, PM.col_border(faces, lv), geo[0],
                       numbers=bool(_g('col_light_show_numbers', True)))
    return None


def col_preview(enable):
    """«Preview COL Light» / «Hide preview»."""
    PS = _ps()
    if not enable:
        PS.col_preview_off()
        return 'INFO', "COL Light preview disabled"
    node = _active()
    if node is None:
        return 'ERROR', "Select a mesh!"
    return _col_preview_on(node) or ('INFO', "COL Light preview enabled")


def col_preview_update():
    """Пересчитать превью (правка «Края» / «Порога» / «Контраста» / «Цифр»,
    смена слоя, выделения, запекание) — на активном меше, как в Blender."""
    PS = _ps()
    if PS.col_preview_node() is None:
        return
    node = _active()
    if node is not None:
        _col_preview_on(node)
        PS.redraw()


# ── часть 4: LightMap UV2 (ops/texture_ops.py Blender-версии) ─────────

def _lm():
    from ..adapter import lightmap_scene
    return lightmap_scene


def lm_apply(path):
    """«Add LightMap»: картинка на UV2 (Multiply) на выделенные меши."""
    PS, LM = _ps(), _lm()
    if not path or not os.path.isfile(path):
        return 'ERROR', "File not found"
    nodes, _other = PS.selected_meshes()
    if not nodes:
        return 'ERROR', "Select a mesh object!"
    applied = skipped = 0
    with undo_block("INU: Apply LightMap UV2"):
        for node in nodes:
            a, s = LM.apply(node, path)
            applied += a
            skipped += s
            LM.set_maps(node, day=path, mode='DAY')
    msg = "LightMap UV2: %d materials" % applied
    if skipped:
        msg += " | skipped (no color input): %d" % skipped
    return 'INFO', msg


def lm_toggle(enable):
    """Глаз: показать / скрыть LightMap UV2 (выделенные меши)."""
    PS, LM = _ps(), _lm()
    nodes, _other = PS.selected_meshes()
    with undo_block("INU: Toggle LightMap UV2"):
        n = sum(LM.toggle(node, enable) for node in nodes)
    return 'INFO', "LightMap UV2: %s (%d)" % ("ON" if enable else "OFF", n)


def lm_remove():
    """«−»: убрать LightMap UV2 из материалов выделенных мешей."""
    PS, LM = _ps(), _lm()
    nodes, _other = PS.selected_meshes()
    with undo_block("INU: Remove LightMap UV2"):
        n = sum(LM.remove(node) for node in nodes)
    return 'INFO', "LightMap UV2: %d removed" % n


def lm_folder(folder, show='DAY'):
    """«LightMap from folder…»: файл <имя>_d — день, <имя>_n — ночь (по
    имени модели)."""
    PS, LM = _ps(), _lm()
    if not folder or not os.path.isdir(folder):
        return 'ERROR', "Folder not found"
    nodes, _other = PS.selected_meshes()
    if not nodes:
        return 'ERROR', "Select a mesh object!"
    found = LM.scan_folder(folder)
    if not found:
        return 'ERROR', "No maps with the _d / _n suffix in the folder"
    n_day = n_night = n_obj = 0
    missing = []
    with undo_block("INU: LightMap from folder"):
        for node in nodes:
            maps = next((found[c.lower()] for c in LM.name_candidates(node)
                         if c.lower() in found), None)
            if not maps:
                missing.append(str(node.name))
                continue
            LM.set_maps(node, day=maps.get('DAY', ''), night=maps.get('NIGHT', ''))
            n_day += 'DAY' in maps
            n_night += 'NIGHT' in maps
            want = show if show in maps else next(iter(maps))
            LM.apply(node, maps[want])
            LM.set_maps(node, mode=want)
            n_obj += 1
    if not n_obj:
        return 'ERROR', "No maps found in the folder for the selected models"
    msg = "LightMap: models %d, day %d, night %d" % (n_obj, n_day, n_night)
    if missing:
        msg += " | without maps: " + ", ".join(missing[:5]) + (
            " +%d" % (len(missing) - 5) if len(missing) > 5 else "")
    return 'INFO', msg


def lm_daynight(mode):
    """Day / Night: выделенные меши, без выделения — вся сцена."""
    PS, LM = _ps(), _lm()
    nodes, _other = PS.selected_meshes()
    if not nodes:
        nodes = LM.scene_nodes_with_maps()
    with undo_block("INU: LightMap day/night"):
        done = sum(1 for node in nodes if LM.set_mode(node, mode))
    if not done:
        return 'WARNING', "No loaded maps — \"LightMap from folder…\""
    return 'INFO', "LightMap: %s (%d)" % ("day" if mode == 'DAY' else "night", done)
