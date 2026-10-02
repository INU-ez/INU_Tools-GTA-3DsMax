# INU Tools (Max) — сборка DffClump из нейтральных данных сцены (порт
# ops/dff_export.py Blender-версии INU). Чистый Python, без pymxs: сцену Max
# читает adapter/scene_read.py в ExportNode / MeshData, здесь — только
# геометрия, материалы, фреймы, атомики, 2DFX, UV-анимации.
#
# Соглашения данных (как у скриптов Kam's): вершины и нормали — в системе
# узла (= системе фрейма); грани — треугольники 0-based; UV — каналы 1/2
# (V снизу, при записи 1 − v); цвета — канал 0 (день), −1 (ночь), −2 (альфа),
# 0..1; transform — 4 строки-оси Max (= строки RwMatrix).

import math
import re
from dataclasses import dataclass, field
from typing import List, Optional

from inu_gta_core.dff import (
    DffClump, DffFrame, DffGeometry, DffAtomic, DffMaterial, DffTexture,
    DffLight, Triangle, TexCoords, RGBA, BoundingSphere, SurfaceProperties,
    BumpMapEffect, EnvMapEffect, SpecularMaterial, ReflectionMaterial,
    DualTextureEffect, ExtraVertColors, UVAnim, UVAnimDict, UVAnimKeyframe,
    HAnimData, Extension2dfx, Light2dfx, GTA_SA_VERSION,
)

FRAME_NAME_MAX = 23


# ── нейтральные данные сцены ─────────────────────────────────────────

@dataclass
class MeshData:
    """Треугольный меш узла в его системе координат."""
    verts: list = field(default_factory=list)       # [(x,y,z)]
    faces: list = field(default_factory=list)       # [(a,b,c)] 0-based
    matids: list = field(default_factory=list)      # [int] 0-based на грань
    normals: list = field(default_factory=list)     # [(n0,n1,n2)] на грань
    uv1: Optional[tuple] = None                     # (verts [(u,v)], faces)
    uv2: Optional[tuple] = None
    day: Optional[tuple] = None                     # (verts [(r,g,b)], faces)
    night: Optional[tuple] = None
    alpha: Optional[tuple] = None                   # (verts [a], faces)
    skin: Optional[list] = None                     # на вершину [(имя кости, вес)]


@dataclass
class MatData:
    """Материал для DFF: цвет 0..255, имя текстуры, GTA-свойства."""
    color: tuple = (255, 255, 255, 255)
    texture: str = ''
    props: dict = field(default_factory=dict)       # adapter/material.DEFAULTS
    name: str = ''


@dataclass
class ExportNode:
    name: str = ''
    kind: str = 'MESH'                              # MESH | DUMMY
    parent: int = -1                                # индекс в списке узлов
    transform: tuple = ((1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 0))  # локальный
    mesh: Optional[MeshData] = None
    materials: List[MatData] = field(default_factory=list)
    flags: dict = field(default_factory=dict)
    bone_id: Optional[int] = None                   # HAnim (Empty-rig)
    rig_root: bool = False
    fx: list = field(default_factory=list)          # 2DFX-записи (готовые)
    # порядок атомика (inu_atomic_order с импорта): движок рисует атомики
    # в порядке списка — для прозрачных частей машины это важно
    order: int = 1 << 30


class ExportError(ValueError):
    """Модель нельзя записать (понятное пользователю сообщение)."""


# ── флаги ────────────────────────────────────────────────────────────

_PED_OVERRIDES = {'export_normals': True, 'day_cols': False, 'night_cols': False,
                  'modulate_color': False, 'set_material_alpha': False,
                  'uv_map2': False, 'light_beam_asi': False}


def export_flags(obj_flags, scene_pipeline='NONE'):
    """Флаги геометрии (как _get_obj_export_flags INU): флаги объекта +
    pipeline сцены; пресет «Ped» перекрывает флаги."""
    f = {'export_normals': True, 'uv_map1': True, 'uv_map2': True,
         'day_cols': True, 'night_cols': True, 'light': True,
         'modulate_color': True, 'set_material_alpha': True,
         'light_beam_asi': False}
    f.update(obj_flags or {})
    if scene_pipeline == 'PED':
        f.update(_PED_OVERRIDES)
    try:
        f['pipeline'] = 0 if scene_pipeline in ('NONE', 'PED') else int(scene_pipeline, 0)
    except (TypeError, ValueError):
        f['pipeline'] = 0
    return f


# ── материалы ────────────────────────────────────────────────────────

def _strip_ext(name):
    name = (name or '').strip()
    return re.sub(r'\.(png|tga|bmp|dds|jpg|jpeg)$', '', name, flags=re.I)


def build_material(md: MatData) -> DffMaterial:
    """DffMaterial из цвета, текстуры и GTA-свойств (как _build_material INU)."""
    p = md.props or {}
    m = DffMaterial()
    r, g, b, a = (list(md.color) + [255])[:4]
    m.color = RGBA(int(r), int(g), int(b), int(a))
    m.surface = SurfaceProperties()
    m.surface.ambient = float(p.get('ambient', 1.0))
    m.surface.specular = float(p.get('surf_specular', 1.0))
    m.surface.diffuse = float(p.get('surf_diffuse', 1.0))
    tex = _strip_ext(p.get('texture_name') or md.texture)
    if tex:
        try:
            # старшие биты — как были в файле (tex_filter_hi, INU); у новых — 1
            filt = (int(p.get('tex_filter', '2')) | (int(p.get('tex_addr_u', '1')) << 8)
                    | (int(p.get('tex_addr_v', '1')) << 12)
                    | (int(p.get('tex_filter_hi', 1)) << 16))
        except (TypeError, ValueError):
            filt = 0x11106
        m.texture = DffTexture(name=tex, mask=_strip_ext(p.get('mask_texture', '')),
                               filters=filt)
    if p.get('export_bump_map'):
        m.bump_map = BumpMapEffect()
        if p.get('bump_map_tex'):
            m.bump_map.bump_texture = DffTexture(name=_strip_ext(p['bump_map_tex']))
    if p.get('export_env_map'):
        m.env_map = EnvMapEffect()
        m.env_map.coefficient = float(p.get('env_map_coef', 0.5))
        m.env_map.use_fb_alpha = bool(p.get('env_map_fb_alpha', False))
        if p.get('env_map_tex'):
            m.env_map.texture = DffTexture(name=_strip_ext(p['env_map_tex']))
    if p.get('export_specular'):
        m.specular = SpecularMaterial()
        m.specular.level = float(p.get('specular_level', 1.0))
        m.specular.name = _strip_ext(p.get('specular_texture', ''))
    if p.get('export_reflection'):
        m.reflection = ReflectionMaterial()
        for k in ('scale_x', 'scale_y', 'offset_x', 'offset_y', 'intensity'):
            setattr(m.reflection, k, float(p.get('reflection_' + k, 0.0)))
    if p.get('export_dual_tex'):
        m.dual_texture = DualTextureEffect()
        m.dual_texture.src_blend = int(p.get('dual_tex_src_blend', '5'))
        m.dual_texture.dst_blend = int(p.get('dual_tex_dst_blend', '6'))
        if p.get('dual_tex_texture'):
            m.dual_texture.texture = DffTexture(name=_strip_ext(p['dual_tex_texture']))
    if p.get('uv_anim_write'):
        m.uv_anim_names = [(p.get('animation_name') or md.name or 'uvanim')[:31]]
    return m


def uv_anim_dict(materials):
    """Словарь UV-анимаций материалов (режим прокрутки Speed U/V)."""
    anims, seen = [], set()
    for md in materials:
        p = md.props or {}
        if not p.get('uv_anim_write'):
            continue
        name = (p.get('animation_name') or md.name or 'uvanim')[:31]
        if name in seen:
            continue
        seen.add(name)
        if p.get('uv_anim_mode') == 'KEYFRAME':
            keys = [UVAnimKeyframe(**k) for k in p.get('uv_keyframes', [])]
            if not keys:
                raise ValueError('%s: no sampled UV keyframes' % name)
            anims.append(UVAnim(name=name, type_id=0x1C1,
                               duration=max(.01, keys[-1].time), keyframes=keys))
            continue
        dur = max(0.01, float(p.get('uv_anim_duration', 1.0)))
        su, sv = float(p.get('uv_anim_speed_u', 0.0)), float(p.get('uv_anim_speed_v', 0.0))
        anims.append(UVAnim(name=name, type_id=0x1C1, duration=dur, keyframes=[
            UVAnimKeyframe(time=0.0, scale_u=1.0, scale_v=1.0, trans_u=0.0, trans_v=0.0),
            UVAnimKeyframe(time=dur, scale_u=1.0, scale_v=1.0,
                           trans_u=su * dur, trans_v=sv * dur)]))
    return UVAnimDict(anims=anims) if anims else None


def keyframe_uv_materials(materials):
    """UV Keyframes materials with no sampled keys."""
    out = []
    for md in materials:
        p = md.props or {}
        if p.get('uv_anim_write') and p.get('uv_anim_mode') == 'KEYFRAME' and not p.get('uv_keyframes'):
            name = md.name or p.get('animation_name') or 'uvanim'
            if name not in out:
                out.append(name)
    return out


def uv_anim_materials(materials):
    return list(dict.fromkeys(md.name or (md.props or {}).get('animation_name') or 'uvanim'
                             for md in materials if (md.props or {}).get('uv_anim_write')))


# ── геометрия ────────────────────────────────────────────────────────

def _corner(ch, f, k):
    """Значение канала в углу k грани f (или None, если канала нет)."""
    if ch is None:
        return None
    verts, faces = ch
    if f >= len(faces):
        return None
    i = faces[f][k]
    return verts[i] if 0 <= i < len(verts) else None


def _q(v, s=10000.0):
    return None if v is None else tuple(int(round(float(x) * s)) for x in v)


def build_geometry(node: ExportNode, write_valpha=False, origin=None) -> DffGeometry:
    """DffGeometry из меша узла: вершина делится, если в её углах разные
    UV / цвета / нормали (DFF хранит всё на вершину — как _needs_split
    INU); неиспользуемые материалы выбрасываются. origin (список) —
    заполняется исходным индексом вершины на каждую вершину DFF."""
    md, fl = node.mesh, node.flags
    use_uv1 = fl.get('uv_map1', True) and md.uv1 is not None
    use_uv2 = use_uv1 and fl.get('uv_map2', True) and md.uv2 is not None
    has_day = fl.get('day_cols', True) and md.day is not None
    has_night = has_day and fl.get('night_cols', True) and md.night is not None
    # нормали не пишутся — по ним и не делим вершины (иначе лишние вершины)
    write_n = bool(fl.get('export_normals', True))

    positions, normals, split = [], [], {}
    uv1, uv2, day, night = [], [], [], []
    tris = []
    for f, face in enumerate(md.faces):
        out = []
        for k in range(3):
            vi = face[k]
            n = md.normals[f][k] if f < len(md.normals) else None
            u1 = _corner(md.uv1, f, k) if use_uv1 else None
            u2 = _corner(md.uv2, f, k) if use_uv2 else None
            dc = _corner(md.day, f, k) if has_day else None
            nc = _corner(md.night, f, k) if has_night else None
            al = _corner(md.alpha, f, k) if has_day else None   # одно число
            key = (vi, _q(u1), _q(u2), _q(dc, 255), _q(nc, 255),
                   None if al is None else int(round(float(al) * 255)),
                   _q(n, 1000.0) if write_n else None)
            idx = split.get(key)
            if idx is None:
                idx = len(positions)
                split[key] = idx
                if origin is not None:
                    origin.append(vi)
                positions.append(tuple(float(x) for x in md.verts[vi]))
                normals.append(tuple(float(x) for x in n) if n else (0.0, 0.0, 1.0))
                if use_uv1:
                    uv1.append(TexCoords(float(u1[0]), 1.0 - float(u1[1])) if u1
                               else TexCoords(0.0, 0.0))
                if use_uv2:
                    uv2.append(TexCoords(float(u2[0]), 1.0 - float(u2[1])) if u2
                               else TexCoords(0.0, 0.0))
                # альфа вершин пишется только с галкой Vertex Alpha: иначе
                # случайная альфа протекает в DFF (как в INU)
                a = 255
                if write_valpha and al is not None:
                    a = int(round(max(0.0, min(1.0, float(al))) * 255))
                if has_day:
                    day.append(_rgba(dc, a, (255, 255, 255)))
                if has_night:
                    night.append(_rgba(nc, a, (0, 0, 0)))
            out.append(idx)
        mat = md.matids[f] if f < len(md.matids) else 0
        tris.append(Triangle(a=out[0], b=out[1], c=out[2], material=mat))

    # материалы: только те, на которые ссылаются грани (лимит движка)
    mats = list(node.materials) or [MatData()]
    used = sorted({t.material for t in tris if 0 <= t.material < len(mats)}) or [0]
    remap = {old: new for new, old in enumerate(used)}
    for t in tris:
        t.material = remap.get(t.material, 0)
    dff_mats = [build_material(mats[i]) for i in used]

    g = DffGeometry()
    g.vertices, g.normals, g.triangles = positions, normals, tris
    g.uv_layers = [uv1] + ([uv2] if use_uv2 else []) if use_uv1 else []
    g.prelit_colors = day
    if has_night:
        g.extra_colors = ExtraVertColors(colors=night)
    if day and fl.get('set_material_alpha', True) and any(c.a < 255 for c in day):
        for m in dff_mats:
            if m.color.a == 255:
                m.color = RGBA(m.color.r, m.color.g, m.color.b, 254)
    center, radius = _bsphere(positions)
    if fl.get('light_beam_asi'):
        dff_mats[0].color = RGBA(254, 254, 254, 254)
        center, radius = (0.0, 0.0, 0.0), max(radius, 1.0) * 5.0
    g.materials = dff_mats
    g.bounding_sphere = BoundingSphere(center[0], center[1], center[2], radius)
    g.export_normals = bool(fl.get('export_normals', True))
    g.write_bin_mesh = True
    g.pipeline = int(fl.get('pipeline', 0))
    g.export_light = bool(fl.get('light', True))
    g.export_mod_color = bool(fl.get('modulate_color', True))
    return g


def _rgba(c, a, dflt):
    if c is None:
        return RGBA(dflt[0], dflt[1], dflt[2], a)
    return RGBA(*[int(round(max(0.0, min(1.0, float(x))) * 255)) for x in c[:3]], a)


def _bsphere(positions):
    """Центр — середина габарита, радиус — до самой дальней вершины."""
    if not positions:
        return (0.0, 0.0, 0.0), 0.0
    c = tuple((min(p[i] for p in positions) + max(p[i] for p in positions)) / 2.0
              for i in range(3))
    r = max(math.sqrt(sum((p[i] - c[i]) ** 2 for i in range(3))) for p in positions)
    return c, r


# ── 2DFX ─────────────────────────────────────────────────────────────

def fx_entry(effect, v, loc, esc=None):
    """Запись 2DFX ядра из полей хелпера (adapter/fx.fields) — как
    _collect_2dfx INU. loc — в системе меша; esc — точки эскалатора
    (низ, верх, конец) уже в системе меша."""
    from inu_gta_core import dff as D
    loc = tuple(float(x) for x in loc)
    if effect == 'LIGHT':
        c = v.get('color_2dfx', (1.0, 1.0, 1.0, 1.0))
        e = D.Light2dfx(loc=loc, color=RGBA(*[int(round(max(0.0, min(1.0, x)) * 255))
                                               for x in (list(c) + [1.0])[:4]]))
        e.corona_far_clip = float(v.get('2dfx_corona_far_clip', 0.0))
        e.pointlight_range = float(v.get('2dfx_pointlight_range', 0.0))
        e.corona_size = float(v.get('corona_size_2dfx', 0.0))
        e.shadow_size = float(v.get('shadow_size_2dfx', 0.0))
        e.corona_show_mode = int(v.get('show_mode_2dfx', 0))
        e.corona_enable_reflection = int(v.get('2dfx_corona_enable_reflection', 0))
        e.corona_flare_type = int(v.get('flare_type_2dfx', 0))
        e.shadow_color_multiplier = int(v.get('2dfx_shadow_color_multiplier', 0))
        e.flags1 = int(v.get('2dfx_flags1', 0))
        e.flags2 = int(v.get('2dfx_flags2', 0))
        e.corona_tex_name = str(v.get('corona_tex_2dfx', ''))
        e.shadow_tex_name = str(v.get('shadow_tex_2dfx', ''))
        e.shadow_z_distance = int(v.get('2dfx_shadow_z_distance', 0))
        look = v.get('2dfx_look_direction')
        if look and any(look):
            e.look_direction = tuple(int(x) for x in look)
        return e
    if effect == 'PARTICLE':
        return D.Particle2dfx(loc=loc, effect_name=str(v.get('2dfx_effect_name', '')))
    if effect == 'PED_ATTRACTOR':
        e = D.PedAttractor2dfx(loc=loc)
        e.attractor_type = int(v.get('2dfx_attractor_type', 0))
        e.rotation_matrix = tuple(float(x) for x in v.get(
            '2dfx_rotation_matrix', (1, 0, 0, 0, 1, 0, 0, 0, 1)))
        e.external_script = str(v.get('2dfx_external_script', ''))
        e.ped_existing_probability = int(v.get('2dfx_ped_probability', 0))
        return e
    if effect == 'SUN_GLARE':
        return D.SunGlare2dfx(loc=loc)
    if effect == 'ENTER_EXIT':
        e = D.EnterExit2dfx(loc=loc)
        e.enter_angle = float(v.get('ee_enter_angle', 0.0))
        e.approximation_radius_x = float(v.get('ee_radius_x', 1.0))
        e.approximation_radius_y = float(v.get('ee_radius_y', 1.0))
        e.exit_loc = tuple(float(x) for x in v.get('ee_exit_loc', (0, 0, 0)))
        e.exit_angle = float(v.get('ee_exit_angle', 0.0))
        e.interior = int(v.get('ee_interior', 0))
        e.sky_color = int(v.get('ee_sky_color', 0))
        e.interior_name = str(v.get('ee_interior_name', ''))
        e.time_on = int(v.get('ee_time_on', 0))
        e.time_off = int(v.get('ee_time_off', 24))
        return e
    if effect == 'ROAD_SIGN':
        e = D.RoadSign2dfx(loc=loc)
        e.size = tuple(float(x) for x in v.get('sign_size', (2.0, 1.0)))
        e.rotation = tuple(float(x) for x in v.get('sign_rotation', (90.0, 0, 0)))
        e.text_lines = [str(v.get('sign_text%d' % i, '')) for i in range(4)]
        mc = {'16': 0, '2': 1, '4': 2, '8': 3}.get(str(v.get('sign_maxchars', '16')), 0)
        col = {'WHITE': 0, 'BLACK': 1, 'GREY': 2, 'RED': 3}.get(
            str(v.get('sign_color', 'WHITE')), 0)
        e.flags = ((max(1, int(v.get('sign_lines', 1))) - 1) & 3) | (mc << 2) | (col << 4)
        return e
    if effect == 'RAW_2DFX':
        # неизвестный движку INU тип — байты как были при импорте
        try:
            raw = bytes.fromhex(str(v.get('2dfx_raw_hex', '')))
        except ValueError:
            raw = b''
        return D.RawUnknown2dfx(effect_id=int(v.get('2dfx_raw_effect_id', 0)),
                                loc=loc, raw=raw)
    if effect == 'ESCALATOR' and esc:
        e = D.Escalator2dfx(loc=loc)
        e.bottom, e.top, e.end = (tuple(float(x) for x in p) for p in esc)
        e.direction = int(v.get('esc_direction', 1))
        return e
    return None


# ── клапм ────────────────────────────────────────────────────────────

def _frame(node: ExportNode, taken=frozenset()) -> DffFrame:
    from .frames import game_frame_name
    original = node.name.strip()
    cleaned = game_frame_name(original)
    name = original if cleaned.casefold() != original.casefold() and cleaned.casefold() in taken else cleaned
    if len(name.encode('ascii', 'replace')) > FRAME_NAME_MAX:
        raise ExportError("Frame name '%s' is longer than %d characters — the "
                          "game stores it in a 24-byte slot and crashes. Rename "
                          "the object." % (name, FRAME_NAME_MAX))
    (r1, r2, r3, pos) = node.transform
    f = DffFrame(name=name, parent=node.parent, write_name=bool(name))
    f.rotation = tuple(float(x) for x in (*r1, *r2, *r3))
    f.position = tuple(float(x) for x in pos)
    if node.bone_id is not None:
        f.hanim = HAnimData(bone_id=int(node.bone_id))
        if node.rig_root:
            f.flags = 0x20003
    return f


# ── скин педа ────────────────────────────────────────────────────────

# ID костей скелета педа SA (HAnim) по имени фрейма — если у кости нет
# user property inu_bone_id (снято с ванильного педа)
SA_PED_BONE_IDS = {
    'root': 0, 'pelvis': 1, 'spine': 2, 'spine1': 3, 'neck': 4, 'head': 5,
    'l brow': 6, 'r brow': 7, 'jaw': 8, 'bip01 r clavicle': 21, 'r upperarm': 22,
    'r forearm': 23, 'r hand': 24, 'r finger': 25, 'r finger01': 26,
    'bip01 l clavicle': 31, 'l upperarm': 32, 'l forearm': 33, 'l hand': 34,
    'l finger': 35, 'l finger01': 36, 'l thigh': 41, 'l calf': 42, 'l foot': 43,
    'l toe0': 44, 'r thigh': 51, 'r calf': 52, 'r foot': 53, 'r toe0': 54,
    'belly': 201, 'r breast': 301, 'l breast': 302,
}


def _m4(t):
    (r1, r2, r3, p) = t
    return [list(map(float, r1)) + [0.0], list(map(float, r2)) + [0.0],
            list(map(float, r3)) + [0.0], list(map(float, p)) + [1.0]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _inv(m):
    """Обратная аффинной матрицы (строки-оси + строка позиции)."""
    a = [row[:3] for row in m[:3]]
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
           - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    if abs(det) < 1e-12:
        raise ExportError("Bone has a degenerate (zero-scale) transform")
    inv = [[(a[(j + 1) % 3][(i + 1) % 3] * a[(j + 2) % 3][(i + 2) % 3]
             - a[(j + 1) % 3][(i + 2) % 3] * a[(j + 2) % 3][(i + 1) % 3]) / det
            for j in range(3)] for i in range(3)]
    p = m[3][:3]
    t = [-sum(p[k] * inv[k][j] for k in range(3)) for j in range(3)]
    return [inv[0] + [0.0], inv[1] + [0.0], inv[2] + [0.0], t + [1.0]]


def world_matrices(nodes):
    """Мировые 4×4 узлов из локальных (строки-векторы: local × world родителя)."""
    out = []
    for n in nodes:
        m = _m4(n.transform)
        out.append(_mul(m, out[n.parent]) if n.parent >= 0 else m)
    return out


def hanim_table(nodes, bones):
    """HAnimBone[] корня скелета: кости в порядке обхода (= порядок узлов),
    тип — флаги стека матриц RW: 2 (push) — после узла есть ещё брат,
    1 (pop) — лист (правило проверено на ванильных педах)."""
    from inu_gta_core.dff import HAnimBone
    bset = set(bones)
    kids = {i: [] for i in bones}
    roots = []
    for i in bones:
        (kids[nodes[i].parent] if nodes[i].parent in bset else roots).append(i)
    out = []
    for j, i in enumerate(bones):
        p = nodes[i].parent
        sib = kids[p] if p in bset else roots
        t = (2 if sib[-1] != i else 0) | (0 if kids[i] else 1)
        out.append(HAnimBone(bone_id=int(nodes[i].bone_id), index=j, bone_type=t))
    return out


def build_skin(mesh_idx, nodes, origin, bones, worlds):
    """SkinData меша: обратные bind-матрицы костей в системе меша (текущая
    поза — вершины снимаются в ней же), до 4 весов на вершину по убыванию,
    нормализованы, кость 0 — в последнем слоте (как INU / Kam's)."""
    from inu_gta_core.dff import SkinData
    md = nodes[mesh_idx].mesh
    index_of = {}
    for j, i in enumerate(bones):
        index_of.setdefault(nodes[i].name.strip().lower(), j)
    missing = sorted({b for vw in md.skin for b, _w in vw
                      if b.strip().lower() not in index_of})
    if missing:
        raise ExportError("Skin of '%s': bones not in the exported hierarchy: %s"
                          % (nodes[mesh_idx].name, ", ".join(missing)))
    per_vert = []
    for vw in md.skin:
        acc = {}
        for b, w in vw:
            if w > 0:
                k = index_of[b.strip().lower()]
                acc[k] = acc.get(k, 0.0) + float(w)
        e = sorted(acc.items(), key=lambda x: -x[1])[:4]
        tot = sum(w for _k, w in e)
        idx = [k for k, _w in e] + [0] * (4 - len(e))
        wgt = [w / tot for _k, w in e] + [0.0] * (4 - len(e)) if tot > 0 else [0.0] * 4
        for s in range(3):
            if idx[s] == 0 and wgt[s] > 0:
                idx[s], idx[3] = idx[3], idx[s]
                wgt[s], wgt[3] = wgt[3], wgt[s]
                break
        per_vert.append((tuple(idx), tuple(wgt)))
    skin = SkinData(num_bones=len(bones))
    for vi in origin:
        iw = per_vert[vi] if vi < len(per_vert) else ((0, 0, 0, 0), (0.0,) * 4)
        skin.bone_indices.append(iw[0])
        skin.bone_weights.append(iw[1])
    mesh_w = worlds[mesh_idx]
    for i in bones:
        # вершина меша → пространство кости: M_mesh × B⁻¹
        skin.bone_matrices.append(_mul(mesh_w, _inv(worlds[i])))
    used = {i for ix, ws in zip(skin.bone_indices, skin.bone_weights)
            for i, w in zip(ix, ws) if w > 0}
    skin.bones_used = sorted(used)
    skin.num_used = len(skin.bones_used)
    skin.max_weights = max([sum(1 for w in ws if w > 0) for ws in skin.bone_weights]
                           or [1]) or 1
    return skin


def build_clump(nodes: List[ExportNode], version=GTA_SA_VERSION,
                write_valpha=False, collision=b'', fx=None) -> DffClump:
    """Клапм из узлов в порядке «родитель раньше детей» (как статичная
    иерархия INU): фреймы — все узлы, атомики — меши в том же порядке,
    2DFX — на последнюю геометрию + Omni-фреймы у света. Меш со скином —
    SkinPLG, а у первой кости — таблица HAnim всего скелета."""
    clump = DffClump(version=version)
    taken = {n.name.strip().casefold() for n in nodes}
    for i, n in enumerate(nodes):
        if n.parent >= i:
            raise ExportError("Internal: node '%s' comes before its parent" % n.name)
        frame = _frame(n, taken)
        clump.frames.append(frame)
        taken.add(frame.name.casefold())
    all_mats, fx = [], list(fx or [])
    meshes = sorted((i for i, n in enumerate(nodes)
                     if n.kind == 'MESH' and n.mesh is not None and n.mesh.faces),
                    key=lambda i: nodes[i].order)          # устойчивая сортировка
    bones = [i for i, n in enumerate(nodes) if n.bone_id is not None]
    skinned = [i for i in meshes if nodes[i].mesh.skin]
    worlds = world_matrices(nodes) if skinned else None
    if skinned:
        if not bones:
            raise ExportError("'%s' has a Skin, but no bones are in the exported "
                              "hierarchy" % nodes[skinned[0]].name)
        root = clump.frames[bones[0]]
        root.hanim.bones = hanim_table(nodes, bones)
        root.hanim.flags, root.hanim.keyframe_size = 0, 36
    for i in meshes:
        n = nodes[i]
        origin = [] if i in skinned else None
        clump.geometries.append(build_geometry(n, write_valpha, origin))
        if origin is not None:
            clump.geometries[-1].skin = build_skin(i, nodes, origin, bones, worlds)
        clump.atomics.append(DffAtomic(frame_index=i,
                                       geometry_index=len(clump.geometries) - 1))
        all_mats += n.materials
        fx += n.fx
    if not clump.frames:
        clump.frames.append(DffFrame(name="root"))
    if fx and clump.geometries:
        clump.geometries[-1].ext_2dfx = Extension2dfx(entries=fx)
        k = 0
        for e in fx:
            if isinstance(e, Light2dfx):
                k += 1
                clump.frames.append(DffFrame(name="Omni%03d" % k, position=e.loc,
                                             parent=0, flags=3))
                clump.lights.append(DffLight(
                    frame_index=len(clump.frames) - 1,
                    radius=e.pointlight_range * 10.0,
                    color=(e.color.r / 255.0, e.color.g / 255.0, e.color.b / 255.0)))
    clump.uv_anim_dict = uv_anim_dict(all_mats) if version >= 0x35000 else None
    clump.collision_data = collision or b''
    return clump
