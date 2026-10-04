# INU Tools (Max) — GTA-свойства материалов (панель INU «GTA Material»).
#
# Свойства (mat.inu.* в Blender-версии) — JSON в AppData материала (сохраняется
# в .max): поверхность COL, RW-затенение, фильтрация/адресация текстуры, маска,
# слот цвета машины, paintjob, GTA-эффекты (env map, bump, reflection,
# specular, dual texture, UV-анимация), режим альфы. Цвет и прозрачность —
# родные diffuse / opacity Standard-материала. Материалы объекта: сам
# материал или подматериалы Multi/Sub-Object («слоты» Blender).

import json
import math
import os

from .selection import _rt, _undo, classify, selected_meshes

_APP_MAT = 0x494E5505

_COL_FIELDS = {'col_mat_index': 'surface', 'col_flags': 'flags',
               'col_brightness': 'brightness', 'col_day_light': 'dayLight',
               'col_night_light': 'nightLight'}


def is_col(mat):
    try:
        return str(_rt().classOf(mat)).lower() in ('inu_gta_colsurface', 'inu_gta_colshadow',
                                                 'gta_colsurface', 'gta_colshadow')
    except Exception:
        return False


def _col_values(mat):
    cls = str(_rt().classOf(mat)).lower()
    if cls == 'gta_colsurface':
        return dict(col_mat_index=int(mat.surface), col_flags=int(mat.u2),
                    col_brightness=int(mat.part) & 255, col_day_light=int(mat.u1) & 15,
                    col_night_light=(int(mat.u1) >> 4) & 15)
    if cls == 'gta_colshadow':
        return dict(col_mat_index=int(mat.u1), col_brightness=int(mat.u2))
    return {key: int(getattr(mat, field)) for key, field in _COL_FIELDS.items()}


def _set_col_values(mat, values, data):
    cls = str(_rt().classOf(mat)).lower()
    if cls == 'gta_colsurface':
        for key, field in (('col_mat_index', 'surface'), ('col_flags', 'u2'),
                           ('col_brightness', 'part')):
            if key in values:
                setattr(mat, field, max(0, min(255, int(values[key]))))
        if 'col_day_light' in values or 'col_night_light' in values:
            from ..ops.col_build import light_byte
            mat.u1 = light_byte(data.get('col_day_light', 0), data.get('col_night_light', 0))
    elif cls == 'gta_colshadow':
        for key, field in (('col_mat_index', 'u1'), ('col_brightness', 'u2')):
            if key in values:
                setattr(mat, field, max(0, min(255, int(values[key]))))
    else:
        for key, field in _COL_FIELDS.items():
            if key in values:
                limit = 15 if key in ('col_day_light', 'col_night_light') else 255
                setattr(mat, field, max(0, min(limit, int(values[key]))))


def ensure_materials():
    rt = _rt()
    folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    for filename, expression in (
            ('GTA_Material.ms', 'GTA_Mtl != undefined'),
            ('GTA_COLplugin.ms', 'GTA_COLSurface != undefined and GTA_COLShadow != undefined'),
            ('Legacy_GTA_Material.ms', 'INU_GTA_Mtl != undefined'),
            ('Legacy_GTA_COLplugin.ms', 'INU_GTA_COLSurface != undefined and INU_GTA_COLShadow != undefined')):
        if not rt.execute(expression):
            rt.fileIn(os.path.join(folder, filename))


def create_collision_material(name, values, shadow=False):
    ensure_materials()
    rt = _rt()
    mat = rt.GTA_COLShadow(name=name) if shadow else rt.GTA_COLSurface(name=name)
    set_props(mat, values)
    return mat

# Kam's scripted material extends Standard, but its UI uses these fields.
_KAM_FIELDS = {'ambient': 'amb', 'surf_specular': 'spc', 'surf_diffuse': 'dif',
               'export_env_map': 'use_RF', 'env_map_coef': 'Reflection',
               'export_specular': 'use_SI', 'specular_level': 'spec_power',
               'export_reflection': 'use_SAS', 'reflection_intensity': 'blend',
               'dual_tex_src_blend': 'p_srcblend', 'dual_tex_dst_blend': 'p_destblend'}
_KAM_MAPS = {'env_map_tex': 'reflectionmap', 'bump_map_tex': 'bumpMap',
             'specular_texture': 'specularmap', 'dual_tex_texture': 'dualMap',
             'dk_normal_texture': 'dkpNmap', 'dk_reflection_texture': 'dkpRmap'}


def resolve_effect_maps(mat, tex_map):
    """Use discovered image paths instead of placeholder effect filenames."""
    if not is_gta(mat):
        return
    values = props(mat)
    for key, field in _KAM_MAPS.items():
        path = tex_map.get(str(values.get(key, '')).lower())
        if path:
            setattr(mat, field, _rt().Bitmaptexture(fileName=path))


def is_gta(mat):
    try:
        return str(_rt().classOf(mat)).lower() in ('inu_gta_mtl', 'gta_mtl')
    except Exception:
        return False


def check_import_material():
    from .. import settings
    if settings.get('import_material_type', 'STANDARD') == 'GTA':
        ensure_materials()
        if not _rt().execute('GTA_Mtl != undefined'):
            raise ValueError('Cannot load INU GTA_Material.ms. Reinstall INU or select Standard.')


def create_import_material(name):
    from .. import settings
    check_import_material()
    rt = _rt()
    return rt.GTA_Mtl(name=name) if settings.get('import_material_type', 'STANDARD') == 'GTA' \
        else rt.StandardMaterial(name=name)


def set_diffuse(mat, texture):
    if is_gta(mat):
        mat.colormap = texture
        mat.use_colormap = True
    else:
        mat.diffuseMap = texture


def _kam_values(mat):
    values = {}
    for key, field in _KAM_FIELDS.items():
        value = getattr(mat, field)
        if key in ('env_map_coef', 'specular_level'):
            value = float(value) / 100.0
        elif key.startswith('dual_tex_'):
            value = str(int(value))
        values[key] = value
    for key, field in _KAM_MAPS.items():
        texture = getattr(mat, field, None)
        path = str(getattr(texture, 'fileName', '') or '') if texture is not None else ''
        values[key] = os.path.splitext(os.path.basename(path))[0]
    if str(_rt().classOf(mat)).lower() == 'gta_mtl':
        values.update(reflection_scale_x=float(mat.specular.r) / 255.0,
                      reflection_scale_y=float(mat.specular.g) / 255.0,
                      reflection_offset_x=float(mat.specular.b) / 255.0,
                      reflection_offset_y=float(mat.spec_alpha) / 255.0)
        values['bump_map_intensity'] = float(mat.bumpMapAmount)
        for key, flag in (('env_map_tex', 'use_reflectionmap'),
                          ('specular_texture', 'use_specularmap')):
            if not bool(getattr(mat, flag)):
                values[key] = ''
    effect = int(mat.matEffect)
    values['export_bump_map'] = effect in (3, 4)
    values['export_dual_tex'] = effect == 5
    if effect == 6:
        values.update(export_dk_normal_map=True, dk_reflection_amount=float(mat.dkpRAmount))
        values.update(export_env_map=False, export_bump_map=False, export_dual_tex=False)
    else:
        values['export_dk_normal_map'] = False
    if str(_rt().classOf(mat)).lower() == 'inu_gta_mtl':
        slots = ('NONE', 'PRIMARY', 'SECONDARY', 'THIRD', 'FOURTH',
                 'HL_LEFT', 'HL_RIGHT', 'TL_LEFT', 'TL_RIGHT')
        index = int(mat.colhprIdx) - 1
        values['vehicle_color_slot'] = slots[index] if 0 <= index < len(slots) else 'NONE'
    return values

DEFAULTS = {
    'col_mat_index': 0, 'col_flags': 0, 'col_day_light': 0, 'col_night_light': 0,
    'col_brightness': 0,
    'ambient': 1.0, 'surf_specular': 1.0, 'surf_diffuse': 1.0,
    'texture_name': '', 'tex_filter': '2', 'tex_addr_u': '1', 'tex_addr_v': '1',
    'tex_filter_hi': 1,
    'mask_texture': '',
    'vehicle_color_slot': 'NONE', 'paintjob_alt_1': '', 'paintjob_alt_2': '',
    'export_env_map': False, 'env_map_tex': '', 'env_map_coef': 0.5,
    'env_map_fb_alpha': False,
    'export_bump_map': False, 'bump_map_tex': '', 'bump_map_intensity': 1.0,
    'export_dk_normal_map': False, 'dk_normal_texture': '',
    'dk_reflection_texture': '', 'dk_reflection_amount': 1.0, 'dk_effect_type': 49,
    'export_reflection': False, 'reflection_scale_x': 0.0,
    'reflection_scale_y': 0.0, 'reflection_offset_x': 0.0,
    'reflection_offset_y': 0.0, 'reflection_intensity': 0.0,
    'export_specular': False, 'specular_level': 0.0, 'specular_texture': '',
    'export_dual_tex': False, 'dual_tex_src_blend': '5', 'dual_tex_dst_blend': '6',
    'dual_tex_texture': '',
    'uv_anim_write': False, 'animation_name': '', 'uv_anim_mode': 'SCROLL',
    'uv_anim_speed_u': 0.0, 'uv_anim_speed_v': 0.0, 'uv_anim_duration': 1.0,
    'alpha_blend': 'OPAQUE',
}

# «волшебные» RGB слотов цвета машины (движок SA подставит цвет carcols)
COLOR_SLOTS = {
    'PRIMARY': (60, 255, 0), 'SECONDARY': (255, 0, 175),
    'THIRD': (0, 255, 255), 'FOURTH': (255, 0, 255),
    'HL_LEFT': (255, 175, 0), 'HL_RIGHT': (0, 255, 200),
    'TL_LEFT': (185, 255, 0), 'TL_RIGHT': (255, 60, 0),
}

# «Копировать на выделенные»: RW/материал, БЕЗ коллизии и слота цвета (как
# _COPY_PROPS INU)
_COPY = ('ambient', 'surf_specular', 'surf_diffuse', 'tex_filter', 'tex_addr_u',
         'tex_addr_v', 'mask_texture', 'export_env_map', 'env_map_tex',
         'env_map_coef', 'env_map_fb_alpha', 'export_bump_map', 'bump_map_tex',
         'bump_map_intensity', 'export_dk_normal_map', 'dk_normal_texture',
         'dk_reflection_texture', 'dk_reflection_amount', 'dk_effect_type',
         'export_reflection', 'reflection_scale_x', 'reflection_scale_y',
         'reflection_offset_x', 'reflection_offset_y', 'reflection_intensity',
         'export_specular', 'specular_level', 'specular_texture',
         'export_dual_tex', 'dual_tex_src_blend', 'dual_tex_dst_blend',
         'dual_tex_texture', 'uv_anim_write', 'animation_name', 'uv_anim_mode')

_EFFECT_FLAGS = ('export_dk_normal_map', 'export_env_map', 'export_bump_map', 'export_reflection',
                 'export_specular', 'export_dual_tex', 'uv_anim_write')


# ── материалы объекта ────────────────────────────────────────────────

def is_multi(mat):
    rt = _rt()
    try:
        return rt.classOf(mat) == rt.MultiMaterial
    except Exception:                                  # noqa: BLE001
        return False


def slots(node):
    """[(подпись, материал)] — «слоты» объекта: подматериалы Multi/Sub
    («ID: имя»), иначе сам материал."""
    try:
        mat = node.material if node is not None else None
    except Exception:                                  # noqa: BLE001
        mat = None
    if mat is None:
        return []
    if not is_multi(mat):
        return [(str(mat.name), mat)]
    ids = list(mat.materialIDList)
    out = []
    for i, sub in enumerate(list(mat.materialList)):
        if sub is not None:
            out.append(("%d: %s" % (ids[i] if i < len(ids) else i + 1, sub.name), sub))
    return out


def _flat(mats):
    """Материалы с раскрытыми Multi/Sub, без повторов."""
    out = []
    for m in mats:
        subs = [s for s in list(m.materialList) if s is not None] if is_multi(m) else [m]
        for s in subs:
            if s not in out:
                out.append(s)
    return out


def node_materials(nodes):
    return _flat([n.material for n in nodes if getattr(n, 'material', None) is not None])


def scene_materials():
    return _flat([m for m in _rt().sceneMaterials if m is not None])


# ── свойства (AppData JSON) ──────────────────────────────────────────

def props(mat):
    """Все GTA-свойства материала (недостающие — по умолчанию)."""
    data = dict(DEFAULTS)
    try:
        raw = _rt().getAppData(mat, _APP_MAT)
        if raw:
            data.update(json.loads(str(raw)))
    except (ValueError, Exception):                    # noqa: BLE001
        pass
    if is_gta(mat):
        data.update(_kam_values(mat))
    elif is_col(mat):
        data.update(_col_values(mat))
    if not data.get('texture_name'):
        data['texture_name'] = texture_stem(mat)
    return data


def set_props(mat, values):
    """Записать свойства поверх сохранённых в материале."""
    rt = _rt()
    try:
        raw = rt.getAppData(mat, _APP_MAT)
        data = json.loads(str(raw)) if raw else {}
    except (ValueError, Exception):                    # noqa: BLE001
        data = {}
    if is_gta(mat):
        data.update(_kam_values(mat))
    elif is_col(mat):
        data.update(_col_values(mat))
    data.update(values)
    if is_gta(mat):
        if str(rt.classOf(mat)).lower() == 'gta_mtl':
            channels = ('reflection_scale_x', 'reflection_scale_y', 'reflection_offset_x')
            if any(key in values for key in channels):
                mat.specular = rt.color(*(float(data.get(key, 0.0)) * 255.0 for key in channels))
            if 'reflection_offset_y' in values:
                mat.spec_alpha = int(round(float(values['reflection_offset_y']) * 255.0))
            if 'bump_map_intensity' in values:
                mat.bumpMapAmount = float(values['bump_map_intensity'])
        if 'vehicle_color_slot' in values and str(rt.classOf(mat)).lower() == 'inu_gta_mtl':
            slots = ('NONE', 'PRIMARY', 'SECONDARY', 'THIRD', 'FOURTH',
                     'HL_LEFT', 'HL_RIGHT', 'TL_LEFT', 'TL_RIGHT')
            mat.colhprIdx = slots.index(values['vehicle_color_slot']) + 1
        for key, field in _KAM_FIELDS.items():
            if key in values:
                value = values[key]
                if key in ('env_map_coef', 'specular_level'):
                    value = float(value) * 100.0
                elif key.startswith('dual_tex_'):
                    value = int(value)
                setattr(mat, field, value)
        for key, field in _KAM_MAPS.items():
            if key in values:
                name = values[key]
                if hasattr(mat, field):
                    setattr(mat, field, rt.Bitmaptexture(fileName=name + '.png') if name else None)
        if 'dk_reflection_amount' in values and hasattr(mat, 'dkpRAmount'):
            mat.dkpRAmount = float(values['dk_reflection_amount'])
        env, bump, dual = (bool(data.get(k)) for k in
                          ('export_env_map', 'export_bump_map', 'export_dual_tex'))
        mat.matEffect = 6 if data.get('export_dk_normal_map') else 5 if dual else 4 if env and bump else 3 if bump else 2 if env else 1
    elif is_col(mat):
        _set_col_values(mat, values, data)
    rt.setAppData(mat, _APP_MAT, json.dumps(data))


def set_prop(mat, key, value):
    set_props(mat, {key: value})


def uv_keyframes(mat):
    """Sample animated bitmap coordinates over the current scene range."""
    import pymxs
    rt = _rt()
    tex = base_diffuse(mat)
    if tex is None or not hasattr(tex, 'coords'):
        raise ValueError('%s: Keyframes needs a diffuse bitmap with coordinates' % mat.name)
    start, end = float(rt.animationRange.start.frame), float(rt.animationRange.end.frame)
    if end < start or end - start > 10000:
        raise ValueError('UV animation range must contain at most 10000 frames')
    fps = float(rt.frameRate)
    times = sorted({start, end} | {float(frame) for frame in range(int(start), int(end) + 1) if start <= frame <= end})
    out = []
    for frame in times:
        with pymxs.attime(frame):
            coords = tex.coords
            angle = math.radians(float(coords.W_angle))
            su, sv = float(coords.U_tiling), float(coords.V_tiling)
            out.append(dict(time=(frame - start) / fps,
                scale_u=su * math.cos(angle), scale_v=sv * math.cos(angle),
                shear_u=-sv * math.sin(angle), shear_v=su * math.sin(angle),
                trans_u=float(coords.U_offset), trans_v=float(coords.V_offset)))
    return out


# ── цвет и текстура Standard-материала ───────────────────────────────

def color(mat):
    """(r, g, b, a) 0..1 или None (не Standard)."""
    try:
        if is_col(mat):
            c = mat.previewColor
            alpha = float(mat.brightness) / 255.0 if str(_rt().classOf(mat)).lower().endswith('shadow') else 1.0
            return (c.r / 255.0, c.g / 255.0, c.b / 255.0, alpha)
        gta = is_gta(mat)
        c = mat.color if gta else mat.diffuse
        alpha = float(mat.alpha) / 255.0 if gta else float(mat.opacity) / 100.0
        return (c.r / 255.0, c.g / 255.0, c.b / 255.0, alpha)
    except Exception:                                  # noqa: BLE001
        return None


def set_color(mat, rgba):
    rt = _rt()
    r, g, b, a = (list(rgba) + [1.0])[:4]
    with _undo("INU: Material color"):
        if is_col(mat):
            mat.previewColor = rt.color(r * 255.0, g * 255.0, b * 255.0)
            if str(rt.classOf(mat)).lower().endswith('shadow'):
                mat.brightness = int(round(a * 255.0))
        elif is_gta(mat):
            mat.color = rt.color(r * 255.0, g * 255.0, b * 255.0)
            mat.alpha = int(round(a * 255.0))
        else:
            mat.diffuse = rt.color(r * 255.0, g * 255.0, b * 255.0)
            mat.opacity = a * 100.0


# обёртки diffuse, которые ставит INU (превью Prelight, LightMap UV2):
# RGB_Multiply с этим именем, исходная карта — map1
_WRAPPERS = ('INU_Prelight', 'INU_LightMap')


def base_diffuse(mat):
    """Карта diffuse материала без обёрток INU (превью, LightMap)."""
    rt = _rt()
    if is_col(mat):
        return None
    if is_gta(mat) and not bool(mat.use_colormap):
        return None
    try:
        m = mat.colormap if is_gta(mat) else mat.diffuseMap
    except Exception:                                  # noqa: BLE001
        return None
    for _ in range(4):
        try:
            if m is not None and rt.classOf(m) == rt.RGB_Multiply                     and str(m.name) in _WRAPPERS:
                m = m.map1
                continue
        except Exception:                              # noqa: BLE001
            pass
        break
    return m


def texture_file(mat):
    try:
        m = base_diffuse(mat)
        return str(m.fileName) if m is not None else ''
    except Exception:                                  # noqa: BLE001
        return ''


def texture_stem(mat):
    f = texture_file(mat)
    return os.path.splitext(os.path.basename(f))[0] if f else ''


# ── действия вкладки Effects ─────────────────────────────────────────

def apply_preset(mat, preset):
    """Быстрые пресеты (apply_preset INU): эффекты с чистого листа."""
    vals = {k: False for k in _EFFECT_FLAGS}
    msg = "Generic — effects cleared"
    if preset in ('VEHICLE', 'CHROME'):
        vals.update(export_env_map=True, env_map_tex='xvehicleenv128',
                    env_map_coef=0.2 if preset == 'VEHICLE' else 0.85,
                    env_map_fb_alpha=False, export_specular=True,
                    specular_level=1.0, specular_texture='vehiclespecdot64')
        if preset == 'VEHICLE':
            vals.update(export_reflection=True, reflection_scale_x=1.0,
                        reflection_scale_y=1.0, reflection_intensity=0.05)
            msg = "Vehicle Body — env + specular + reflection"
        else:
            msg = "Chrome — strong env reflection + specular"
    elif preset == 'VEHICLE_GLASS':
        vals.update(export_env_map=True, env_map_tex='xvehicleenv128',
                    env_map_coef=0.4, env_map_fb_alpha=True)
        msg = "Vehicle Glass — env map with FB alpha"
    set_props(mat, vals)
    return msg


def set_color_slot(mat, slot):
    """Слот цвета машины: свойство + «волшебный» RGB в diffuse."""
    set_prop(mat, 'vehicle_color_slot', slot)
    rgb = COLOR_SLOTS.get(slot)
    if rgb is not None:
        c = color(mat)
        set_color(mat, (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0,
                        c[3] if c else 1.0))


def sa_vehicle_defaults(mat):
    """«Apply SA Vehicle defaults» (как SA Vehicle default Kam's
    GTA_Material): env xvehicleenv128 + specular vehiclespecdot64 +
    reflection 0.05; pipeline экспорта — Vehicle."""
    set_props(mat, dict(export_env_map=True, env_map_tex='xvehicleenv128',
                        env_map_coef=0.2, export_specular=True,
                        specular_level=1.0, specular_texture='vehiclespecdot64',
                        export_reflection=True, reflection_scale_x=1.0,
                        reflection_scale_y=1.0, reflection_intensity=0.05))
    return "SA Vehicle defaults applied (env + specular + reflection)"


def copy_to_selected(src):
    """Настройки материала → материалы всех выделенных объектов."""
    vals = {k: v for k, v in props(src).items() if k in _COPY}
    rgba = color(src)
    targets = [m for m in node_materials(list(_rt().selection)) if m != src]
    with _undo("INU: Copy material settings"):
        for m in targets:
            set_props(m, vals)
            if rgba is not None and color(m) is not None:
                set_color(m, rgba)
    return len(targets)


def paintjob_report():
    """(ok, [проблемы]) по всем материалам сцены с paintjob."""
    ok, problems = 0, []
    for m in scene_materials():
        p = props(m)
        a, b = p.get('paintjob_alt_1'), p.get('paintjob_alt_2')
        if not (a or b):
            continue
        if not (a and b):
            problems.append("%s: both paintjob slots are needed" % m.name)
        elif not texture_file(m):
            problems.append("%s: no main texture" % m.name)
        else:
            ok += 1
    return ok, problems


# ── поверхность COL ──────────────────────────────────────────────────

def set_surface(mat, sid, all_selected=False):
    """ID поверхности: материалу или (all_selected) всем материалам всех
    выделенных COL-объектов. Возвращает число материалов."""
    targets = [mat] if mat is not None else []
    if all_selected:
        cols = [o for o in selected_meshes() if classify(o)[0] == 'COL']
        targets = node_materials(cols) or targets
    with _undo("INU: COL surface"):
        for m in targets:
            set_prop(m, 'col_mat_index', int(sid))
    return len(targets)


def favorites_path():
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'INU_Tools_Max', 'surface_favorites.json')


def favorites():
    try:
        with open(favorites_path(), encoding='utf-8') as f:
            return set(int(x) for x in json.load(f))
    except (OSError, ValueError, TypeError):
        return set()


def toggle_favorite(sid):
    favs = favorites()
    favs.symmetric_difference_update({int(sid)})
    path = favorites_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(sorted(favs), f)
    return favs


# ── альфа-материалы ──────────────────────────────────────────────────

def _has_alpha(path):
    """Значимый альфа-канал у файла текстуры (не все пиксели 255)."""
    if not path or not os.path.isfile(path):
        return False
    from ..qt import QtGui
    img = QtGui.QImage(path)
    if img.isNull() or not img.hasAlphaChannel():
        return False
    a = img.convertToFormat(QtGui.QImage.Format_Alpha8)
    w, h, bpl = a.width(), a.height(), a.bytesPerLine()
    buf = bytes(a.constBits())[:bpl * h]
    if not buf:
        return False
    if bpl == w:
        return min(buf) < 255
    # строки выровнены по 4 байта — хвост строки не пиксели
    return any(min(buf[y * bpl:y * bpl + w]) < 255 for y in range(h))


def _opacity_on(mat):
    if is_col(mat):
        return False
    try:
        if is_gta(mat):
            return mat.alphamap is not None and bool(mat.use_alphamap)
        return mat.opacityMap is not None and bool(mat.opacityMapEnable)
    except Exception:                                  # noqa: BLE001
        return False


def scan_alpha(scope, mode):
    """Альфа-материалы (alpha_scan INU): scope SCENE | SELECTED; mode
    NODE (карта opacity — альфа текстуры подключена), CHANNEL (у текстуры
    есть альфа), TRANSPARENT (уже прозрачный), ALL."""
    mats = scene_materials() if scope == 'SCENE' else \
        node_materials(list(_rt().selection))
    out = []
    for m in mats:
        node = _opacity_on(m)
        trans = node
        try:
            trans = trans or (color(m) or (1, 1, 1, 1))[3] < 1.0
        except Exception:                              # noqa: BLE001
            pass
        hit = ((mode in ('NODE', 'ALL') and node)
               or (mode in ('TRANSPARENT', 'ALL') and trans))
        if not hit and mode in ('CHANNEL', 'ALL'):
            hit = _has_alpha(texture_file(m))
        if hit:
            out.append(m)
    return out


def set_blend(mat, mode):
    """Режим альфы материала: OPAQUE — без карты opacity; иначе — альфа
    текстуры в opacity (монохром из альфа-канала). Режим — в свойствах."""
    rt = _rt()
    set_prop(mat, 'alpha_blend', mode)
    if is_col(mat):
        return  # COL has raw brightness data, not a diffuse alpha map.
    with _undo("INU: Alpha blend mode"):
        if mode == 'OPAQUE':
            if is_gta(mat):
                mat.alphamap = None
                mat.use_alphamap = False
            else:
                mat.opacityMap = None
                mat.opacityMapEnable = False
            return
        f = texture_file(mat)
        if f:
            op = rt.Bitmaptexture(fileName=f)
            op.monoOutput = 1           # альфа
            if is_gta(mat):
                mat.alphamap = op
                mat.use_alphamap = True
            else:
                mat.opacityMap = op
                mat.opacityMapEnable = True


def select_users(mats):
    """Выделить объекты, использующие эти материалы."""
    rt = _rt()
    users = [o for o in rt.geometry
             if getattr(o, 'material', None) is not None
             and any(m in mats for m in _flat([o.material]))]
    with _undo("INU: Select objects"):
        rt.clearSelection()
        if users:
            rt.select(users)
    return len(users)
