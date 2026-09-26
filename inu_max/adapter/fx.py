# INU Tools (Max) — 2DFX в сцене Max (панели INU «Эффекты» и «GTA SA: <тип>»).
#
# Эффект — хелпер Point с user properties, как пустышка Blender-версии:
# inu_type = 2DFX, inu_effect_2dfx = LIGHT | PARTICLE | ...; поля эффекта —
# inu_<имя поля INU> (color_2dfx, 2dfx_flags1, ee_interior, sign_text0,
# esc_bottom, particle_life, ...). Векторы и цвет хранятся строкой «x,y,z»
# (видно и правится во вкладке User Defined свойств объекта).

from .selection import (_rt, _undo, node_kind, active_node, get_field,
                        put_field)

TYPE_ICON = {'LIGHT': 'light', 'PARTICLE': 'particles', 'PED_ATTRACTOR': 'ped',
             'SUN_GLARE': 'sun', 'ENTER_EXIT': 'arrows', 'ROAD_SIGN': 'text',
             'ESCALATOR': 'stairs', 'RAW_2DFX': 'lock'}

# поля по умолчанию при создании (как create_2dfx INU)
DEFAULTS = {
    'LIGHT': {
        'color_2dfx': (1.0, 1.0, 1.0, 1.0), 'corona_size_2dfx': 1.0,
        'shadow_size_2dfx': 8.0, '2dfx_corona_far_clip': 100.0,
        '2dfx_pointlight_range': 18.0, '2dfx_corona_enable_reflection': 0,
        '2dfx_shadow_color_multiplier': 40, '2dfx_flags1': 96,
        '2dfx_shadow_z_distance': 0, '2dfx_flags2': 0,
        'corona_tex_2dfx': 'coronastar', 'shadow_tex_2dfx': 'shad_exp',
        'show_mode_2dfx': '0', 'flare_type_2dfx': '0', 'preset_2dfx': 'DEFAULT',
    },
    'PARTICLE': {'2dfx_effect_name': ''},
    'PED_ATTRACTOR': {
        '2dfx_attractor_type': 0,
        '2dfx_rotation_matrix': (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        '2dfx_external_script': '', '2dfx_ped_probability': 0,
    },
    'SUN_GLARE': {},
    'ENTER_EXIT': {
        'ee_interior': 0, 'ee_interior_name': '', 'ee_enter_angle': 0.0,
        'ee_exit_angle': 0.0, 'ee_exit_loc': (0.0, 0.0, 0.0),
        'ee_radius_x': 1.5, 'ee_radius_y': 1.5, 'ee_time_on': 0,
        'ee_time_off': 24, 'ee_sky_color': 0,
    },
    'ROAD_SIGN': {
        'sign_text0': 'TEXT', 'sign_text1': '', 'sign_text2': '',
        'sign_text3': '', 'sign_lines': 1, 'sign_maxchars': '16',
        'sign_color': 'WHITE', 'sign_size': (2.0, 1.0),
        'sign_rotation': (90.0, 0.0, 0.0),        # градусы
    },
    'ESCALATOR': {
        'esc_bottom': (0.0, 0.0, 0.0), 'esc_top': (0.0, 2.0, 3.0),
        'esc_end': (0.0, 3.0, 3.0), 'esc_direction': '1',
    },
    'RAW_2DFX': {'2dfx_raw_effect_id': 0, '2dfx_raw_size': 0},
}

# редактируемые параметры частицы (obj.inu.particle_* INU) и их умолчания
PARTICLE_DEFAULTS = {
    'particle_texture': '', 'particle_src_blend': 4, 'particle_dst_blend': 5,
    'particle_color_start': (1.0, 1.0, 1.0, 1.0),
    'particle_color_end': (1.0, 1.0, 1.0, 0.0),
    'particle_color_mid_enabled': False,
    'particle_color_mid': (1.0, 1.0, 1.0, 1.0), 'particle_color_mid_time': 0.5,
    'particle_size_start': 0.3, 'particle_size_end': 0.5,
    'particle_life': 1.0, 'particle_life_bias': 0.0, 'particle_rate': 10.0,
    'particle_speed': 1.0, 'particle_speed_bias': 0.0,
    'particle_direction': (0.0, 0.0, 1.0),
    'particle_angle_min': 0.0, 'particle_angle_max': 0.0,
    'particle_volume': (0.0, 0.0, 0.0), 'particle_offset': (0.0, 0.0, 0.0),
    'particle_rotation_min': 0.0, 'particle_rotation_max': 0.0,
    'particle_force': (0.0, 0.0, 0.0), 'particle_friction': 0.0,
    'particle_wind': 0.0, 'particle_noise': 0.0, 'particle_jitter': 0.0,
    'particle_rotspeed_min': 0.0, 'particle_rotspeed_max': 0.0,
    'particle_ground_bounce': 0.0, 'particle_ground_speedmult': 1.0,
    'particle_sys_length': 1.0, 'particle_sys_playmode': 2,
    'particle_sys_culldist': 50.0, 'particle_emitter_index': 0,
}

# пресеты света (_2DFX_PRESETS INU): цвет 0..255
PRESETS = {
    'DEFAULT': ("Default", "Default light settings", dict(
        color=(255, 255, 255, 255), corona_size=1.0, far_clip=100.0, range=18.0,
        corona_tex='coronastar', show_mode=0, flare=0, reflection=0,
        shadow_size=8.0, shadow_z=0, shadow_mult=40, shadow_tex='shad_exp',
        flags1=96, flags2=0)),
    'ONALLDAY': ("OnAllDay", "Always visible light", dict(
        color=(255, 255, 255, 255), corona_size=1.0, far_clip=100.0, range=18.0,
        corona_tex='coronastar', show_mode=0, flare=0, reflection=0,
        shadow_size=8.0, shadow_z=0, shadow_mult=40, shadow_tex='shad_exp',
        flags1=96, flags2=0)),
    'LAMP_POST': ("Lamp Post", "Standard lamp post", dict(
        color=(255, 255, 171, 255), corona_size=1.5, far_clip=200.0, range=16.0,
        corona_tex='coronastar', show_mode=0, flare=0, reflection=1,
        shadow_size=10.0, shadow_z=0, shadow_mult=40, shadow_tex='shad_exp',
        flags1=64, flags2=0)),
    'LAMP_POST_COAST': ("Lamp Post Coast", "Coastal lamp post (warm)", dict(
        color=(255, 217, 163, 255), corona_size=1.2, far_clip=200.0, range=14.0,
        corona_tex='coronamoon', show_mode=0, flare=0, reflection=1,
        shadow_size=8.0, shadow_z=0, shadow_mult=40, shadow_tex='shad_exp',
        flags1=64, flags2=0)),
    'BB_PICKUP': ("BB Pickup", "Red pickup marker", dict(
        color=(255, 0, 0, 255), corona_size=0.8, far_clip=80.0, range=8.0,
        corona_tex='coronastar', show_mode=0, flare=0, reflection=0,
        shadow_size=0.0, shadow_z=0, shadow_mult=0, shadow_tex='shad_exp',
        flags1=96, flags2=0)),
    'FLASHING_MAV1': ("Flashing (Maverick1)", "Red blinking helicopter light", dict(
        color=(255, 0, 0, 255), corona_size=0.5, far_clip=200.0, range=0.0,
        corona_tex='coronastar', show_mode=1, flare=0, reflection=0,
        shadow_size=0.0, shadow_z=0, shadow_mult=0, shadow_tex='shad_exp',
        flags1=96, flags2=0)),
    'FLASHING_MAV2': ("Flashing (Maverick2)", "Green blinking helicopter light", dict(
        color=(0, 255, 0, 255), corona_size=0.5, far_clip=200.0, range=0.0,
        corona_tex='coronastar', show_mode=1, flare=0, reflection=0,
        shadow_size=0.0, shadow_z=0, shadow_mult=0, shadow_tex='shad_exp',
        flags1=96, flags2=0)),
    'FLASHING_TUG': ("Flashing (Tug)", "Orange blinking tug light", dict(
        color=(255, 128, 0, 255), corona_size=0.4, far_clip=150.0, range=0.0,
        corona_tex='coronastar', show_mode=1, flare=0, reflection=0,
        shadow_size=0.0, shadow_z=0, shadow_mult=0, shadow_tex='shad_exp',
        flags1=96, flags2=0)),
    'TRAIN_CROSSING': ("Train Crossing", "Red blinking train crossing", dict(
        color=(255, 0, 0, 255), corona_size=1.0, far_clip=200.0, range=12.0,
        corona_tex='coronastar', show_mode=1, flare=0, reflection=1,
        shadow_size=0.0, shadow_z=0, shadow_mult=0, shadow_tex='shad_exp',
        flags1=96, flags2=0)),
    'TRAFFIC': ("Traffic", "Traffic light", dict(
        color=(255, 0, 0, 255), corona_size=0.7, far_clip=120.0, range=6.0,
        corona_tex='coronastar', show_mode=0, flare=0, reflection=0,
        shadow_size=0.0, shadow_z=0, shadow_mult=0, shadow_tex='shad_exp',
        flags1=96, flags2=0)),
}

# вид хелпера по типу (empty_display_type / size INU)
_DISPLAY = {'LIGHT': ('cross', 0.3), 'PARTICLE': ('box', 0.2),
            'PED_ATTRACTOR': ('box', 0.15), 'SUN_GLARE': ('cross', 0.1),
            'ENTER_EXIT': ('axistripod', 0.5), 'ROAD_SIGN': ('cross', 0.5),
            'ESCALATOR': ('axistripod', 0.5)}


# ── чтение / запись полей (строки и векторы — в кавычках, см. selection) ──

get = get_field
put = put_field


def is_2dfx(o):
    if o is None:
        return False
    rt = _rt()
    try:
        if rt.superClassOf(o) != rt.helper:
            return False
    except Exception:                                  # noqa: BLE001
        return False
    return str(get(o, 'type', '')) == '2DFX'


def effect_of(o):
    return str(get(o, 'effect_2dfx', 'LIGHT'))


def fields(o):
    """Все поля эффекта объекта (умолчания для отсутствующих)."""
    eff = effect_of(o)
    spec = dict(DEFAULTS.get(eff, {}))
    if eff == 'PARTICLE':
        spec.update(PARTICLE_DEFAULTS)
    return {k: get(o, k, d) for k, d in spec.items()}


def selected_2dfx():
    rt = _rt()
    return [o for o in rt.selection if is_2dfx(o)]


# ── действия панели «Эффекты» ────────────────────────────────────────

def create_effect(kind):
    """«Create effect»: хелпер Point с полями по умолчанию, на месте
    выделения (в Blender — на 3D-курсоре), в слое «2DFX», выделенный."""
    rt = _rt()
    try:
        pos = rt.selection.center if len(list(rt.selection)) else rt.Point3(0, 0, 0)
    except Exception:                                  # noqa: BLE001
        pos = rt.Point3(0, 0, 0)
    shape, size = _DISPLAY.get(kind, ('cross', 0.3))
    with _undo("INU: Create 2DFX"):
        node = rt.Point(name=rt.uniqueName("2dfx_%s" % kind.lower()), pos=pos,
                        size=size, cross=shape == 'cross', box=shape == 'box',
                        axistripod=shape == 'axistripod', centermarker=False)
        put([node], 'type', '2DFX')
        put([node], 'effect_2dfx', kind)
        for k, v in DEFAULTS.get(kind, {}).items():
            put([node], k, v)
        try:
            layer = rt.LayerManager.getLayerFromName("2DFX") or \
                rt.LayerManager.newLayerFromName("2DFX")
            layer.addNode(node)
        except Exception as e:                         # noqa: BLE001
            print("[INU] 2DFX layer: %r" % (e,))
        rt.select(node)
    return node


def apply_preset(o, key):
    """Пресет света (apply_2dfx_preset INU) → поля объекта."""
    label, _tip, p = PRESETS.get(key, PRESETS['DEFAULT'])
    vals = {
        'color_2dfx': tuple(c / 255.0 for c in p['color']),
        'corona_size_2dfx': p['corona_size'], 'shadow_size_2dfx': p['shadow_size'],
        '2dfx_corona_far_clip': p['far_clip'], '2dfx_pointlight_range': p['range'],
        '2dfx_corona_enable_reflection': p['reflection'],
        '2dfx_shadow_z_distance': p['shadow_z'],
        '2dfx_shadow_color_multiplier': p['shadow_mult'],
        '2dfx_flags1': p['flags1'], '2dfx_flags2': p['flags2'],
        'corona_tex_2dfx': p['corona_tex'], 'shadow_tex_2dfx': p['shadow_tex'],
        'show_mode_2dfx': str(p['show_mode']), 'flare_type_2dfx': str(p['flare']),
        'preset_2dfx': key,
    }
    with _undo("INU: 2DFX preset"):
        for k, v in vals.items():
            put([o], k, v)
    return "Preset '%s' applied" % label


def copy_to_selected():
    """«Apply settings» (apply_2dfx_to_selected INU): поля активного 2DFX —
    на остальные выделенные 2DFX. Возвращает (текст, ошибка?)."""
    src = active_node()
    targets = [o for o in selected_2dfx() if o != src]
    if not targets:
        return ("Select the target 2DFX helpers (Ctrl+click), the source "
                "first", True)
    vals = fields(src)
    with _undo("INU: Apply 2DFX to selected"):
        for o in targets:
            put([o], 'effect_2dfx', effect_of(src))
            for k, v in vals.items():
                put([o], k, v)
    return "2DFX settings applied to %d" % len(targets), False


def attach_selected():
    """«Attach to model»: выделенные 2DFX — детьми выделенного меша."""
    rt = _rt()
    meshes = [o for o in rt.selection if node_kind(o) == 'MESH']
    fx = selected_2dfx()
    if not fx:
        return "No 2DFX selected", True
    if not meshes:
        return "Select the mesh together with the 2DFX", True
    with _undo("INU: Attach 2DFX"):
        for o in fx:
            o.parent = meshes[0]
    return "Attached 2DFX: %d → '%s'" % (len(fx), meshes[0].name), False


def detach(o):
    if o is None or o.parent is None:
        return "Nothing to detach", True
    name = str(o.parent.name)
    with _undo("INU: Detach 2DFX"):
        o.parent = None
    return "'%s' detached from '%s'" % (o.name, name), False


def attached(mesh):
    """2DFX-дети меша."""
    return [c for c in mesh.children if is_2dfx(c)]


def detach_all(mesh):
    kids = attached(mesh)
    if not kids:
        return "No attached 2DFX found", True
    with _undo("INU: Detach all 2DFX"):
        for c in kids:
            c.parent = None
    return "%d 2DFX detached from '%s'" % (len(kids), mesh.name), False


def effect_users(name):
    """Сколько 2DFX-частиц сцены используют систему name (диалог удаления)."""
    rt = _rt()
    return sum(1 for o in rt.helpers
               if is_2dfx(o) and effect_of(o) == 'PARTICLE'
               and str(get(o, '2dfx_effect_name', '')) == name)


def show_links(on):
    """«Relationship lines»: линии связи 2DFX → модель (Display Links)."""
    rt = _rt()
    n = 0
    for o in rt.helpers:
        if is_2dfx(o):
            try:
                o.showLinks = bool(on)
                n += 1
            except Exception:                          # noqa: BLE001
                pass
    return n
