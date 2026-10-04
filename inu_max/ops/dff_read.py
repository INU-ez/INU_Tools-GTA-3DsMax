# INU Tools (Max) — разбор DffClump в нейтральный план импорта (обратный
# путь к ops/dff_build.py, порт import_dff_from_clump Blender-версии INU).
# Чистый Python + numpy: сцену Max строит adapter/scene_build.py.
#
# Соглашения — те же, что читает экспорт (adapter/scene_read.py):
#   • меш — в системе своего фрейма; UV — каналы 1/2 (V снизу: 1 − v);
#     цвет дня — канал 0, ночи — −1, альфа вершин — −2 (0..1);
#   • нормали — явные, на каждый угол грани (Edit_Normals);
#   • фреймы без геометрии — Dummy, кости скелета — Dummy со связями (Kam’s) и inu_bone_id;
#   • флаги геометрии — user properties inu_<флаг>; GTA-свойства материала —
#     props (adapter/material.DEFAULTS);
#   • 2DFX — хелперы-дети меша (поля adapter/fx); коллизия внутри DFF —
#     меш «<имя>_col» / тень «<имя>_sha» + сферы/боксы «<имя>_col_sphere_N».

import math
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .dff_build import MatData

# ── план ─────────────────────────────────────────────────────────────


@dataclass
class ImportMesh:
    verts: list = field(default_factory=list)       # [(x,y,z)] — вершины DFF
    faces: list = field(default_factory=list)       # [(a,b,c)] 0-based
    matids: list = field(default_factory=list)      # 0-based на грань
    uv1: Optional[list] = None                      # на вершину [(u,v)], v уже 1 − v
    uv2: Optional[list] = None
    day: Optional[list] = None                      # на вершину [(r,g,b)] 0..1
    night: Optional[list] = None
    alpha: Optional[list] = None                    # на вершину [a] 0..1
    corner_normals: Optional[list] = None           # на угол [(x,y,z)] (3 на грань)
    weld: str = 'NONE'                              # NONE | ALL | PROTECT
    protect: list = field(default_factory=list)     # вершины, которые не сваривать
    skin: Optional[list] = None                     # на вершину [(индекс узла-кости, вес)]


@dataclass
class ImportNode:
    name: str = ''
    kind: str = 'DUMMY'                             # MESH | DUMMY | BONE
    parent: int = -1                                # индекс в плане
    transform: tuple = ((1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 0))   # локальный
    mesh: Optional[ImportMesh] = None
    materials: List[MatData] = field(default_factory=list)
    props: dict = field(default_factory=dict)       # user properties inu_<ключ>


@dataclass
class ImportFx:
    effect: str = 'LIGHT'
    fields: dict = field(default_factory=dict)
    loc: tuple = (0.0, 0.0, 0.0)                    # в системе меша-родителя
    parent: int = -1
    name: str = ''


@dataclass
class ImportColMesh:
    name: str = ''
    verts: list = field(default_factory=list)
    faces: list = field(default_factory=list)       # 0-based, обход Max
    surfaces: list = field(default_factory=list)    # на грань: props материала COL
    shadow: bool = False
    model: str = ''                                 # имя модели COL (для привязки к DFF)
    bounds: Optional[list] = None                   # границы исходного COL (10 чисел)


@dataclass
class ImportColPrim:
    name: str = ''
    kind: str = 'SPHERE'                            # SPHERE | BOX
    center: tuple = (0.0, 0.0, 0.0)
    radius: float = 0.0
    bb_min: tuple = (0.0, 0.0, 0.0)
    bb_max: tuple = (0.0, 0.0, 0.0)
    surface: dict = field(default_factory=dict)
    model: str = ''
    bounds: Optional[list] = None


@dataclass
class ImportPlan:
    nodes: List[ImportNode] = field(default_factory=list)
    fx: List[ImportFx] = field(default_factory=list)
    col_meshes: List[ImportColMesh] = field(default_factory=list)
    col_prims: List[ImportColPrim] = field(default_factory=list)
    pipeline: str = ''                              # для settings export_pipeline
    skinned: bool = False
    warnings: list = field(default_factory=list)


# ── имена ────────────────────────────────────────────────────────────

def _usable(nm):
    """Имя фрейма годится для узла: не пустое и без мусора прошлых экспортов."""
    nm = (nm or '').strip()
    return bool(nm) and '?' not in nm and not re.search(r'[\x00-\x1f]', nm)


def model_name(base, n_geoms, gi):
    """Имя объекта модели (как у Kam's): имя файла; LOD-модели остаются
    «LOD…» — классификатор экспорта сам узнаёт LOD и базовое имя. Не длиннее
    23 символов (лимит имени фрейма в игре)."""
    name = base if n_geoms <= 1 else "%s_%d" % (base[:20], gi)
    return name[:23]


def frame_name(base, i):
    return ("%s_f%d" % (base[:18], i))[:23]


# ── материалы ────────────────────────────────────────────────────────

def material(dm, uv_anims=None, index=0):
    """MatData из DffMaterial: цвет, текстура и GTA-свойства (обратно к
    build_material)."""
    p = {}
    c = dm.color
    color = (c.r, c.g, c.b, c.a) if c is not None else (255, 255, 255, 255)
    s = dm.surface
    if s is not None:
        p['ambient'], p['surf_specular'], p['surf_diffuse'] = (
            float(s.ambient), float(s.specular), float(s.diffuse))
    tex = ''
    if dm.texture is not None and dm.texture.name:
        tex = dm.texture.name
        f = int(dm.texture.filters or 0)
        p['tex_filter'] = str(f & 0xFF or 2)
        p['tex_addr_u'] = str((f >> 8) & 0xF or 1)
        p['tex_addr_v'] = str((f >> 12) & 0xF or 1)
        p['tex_filter_hi'] = (f >> 16) & 0xFFFF
        if dm.texture.mask:
            p['mask_texture'] = dm.texture.mask
    if dm.bump_map is not None:
        p['export_bump_map'] = True
        bt = getattr(dm.bump_map, 'bump_texture', None)
        if bt is not None and bt.name:
            p['bump_map_tex'] = bt.name
    if dm.env_map is not None:
        p['export_env_map'] = True
        p['env_map_coef'] = float(dm.env_map.coefficient)
        p['env_map_fb_alpha'] = bool(dm.env_map.use_fb_alpha)
        if dm.env_map.texture is not None and dm.env_map.texture.name:
            p['env_map_tex'] = dm.env_map.texture.name
    if dm.specular is not None:
        p['export_specular'] = True
        p['specular_level'] = float(dm.specular.level)
        if dm.specular.name:
            p['specular_texture'] = dm.specular.name
    if dm.reflection is not None:
        p['export_reflection'] = True
        for k in ('scale_x', 'scale_y', 'offset_x', 'offset_y', 'intensity'):
            p['reflection_' + k] = float(getattr(dm.reflection, k))
    if dm.dual_texture is not None:
        p['export_dual_tex'] = True
        p['dual_tex_src_blend'] = str(int(dm.dual_texture.src_blend))
        p['dual_tex_dst_blend'] = str(int(dm.dual_texture.dst_blend))
        if dm.dual_texture.texture is not None and dm.dual_texture.texture.name:
            p['dual_tex_texture'] = dm.dual_texture.texture.name
    names = list(getattr(dm, 'uv_anim_names', None) or [])
    if names:
        p['uv_anim_write'] = True
        p['animation_name'] = names[0]
        anim = next((a for a in (uv_anims or []) if a.name == names[0]), None)
        if anim is not None and anim.keyframes:
            dur = max(0.01, float(anim.duration))
            last = anim.keyframes[-1]
            p['uv_anim_mode'] = 'SCROLL'
            p['uv_anim_duration'] = dur
            p['uv_anim_speed_u'] = float(last.trans_u) / dur
            p['uv_anim_speed_v'] = float(last.trans_v) / dur
    return MatData(color=color, texture=tex, props=p,
                   name=tex or "mat_%d" % index)


def geometry_flags(geom):
    """user properties флагов объекта из флагов геометрии (как
    _set_object_props INU)."""
    mats = geom.materials or []
    beam = bool(mats) and mats[0].color is not None and (
        mats[0].color.r, mats[0].color.g, mats[0].color.b, mats[0].color.a) == (254,) * 4
    return {
        'export_normals': bool(geom.export_normals and geom.normals),
        'light': bool(geom.export_light),
        'modulate_color': bool(geom.export_mod_color),
        'uv_map1': len(geom.uv_layers) >= 1,
        'uv_map2': len(geom.uv_layers) >= 2,
        'day_cols': bool(geom.prelit_colors),
        'night_cols': bool(geom.extra_colors and geom.extra_colors.colors),
        'set_material_alpha': any(m.color is not None and m.color.a == 254
                                  for m in mats) and not beam,
        'light_beam_asi': beam,
    }


# ── 2DFX ─────────────────────────────────────────────────────────────

def fx_fields(entry):
    """(effect, поля adapter/fx, loc) из записи ядра — обратно к fx_entry."""
    from inu_gta_core import dff as D
    loc = tuple(float(x) for x in entry.loc)
    if isinstance(entry, D.Light2dfx):
        c = entry.color
        v = {'color_2dfx': (c.r / 255.0, c.g / 255.0, c.b / 255.0, c.a / 255.0),
             '2dfx_corona_far_clip': float(entry.corona_far_clip),
             '2dfx_pointlight_range': float(entry.pointlight_range),
             'corona_size_2dfx': float(entry.corona_size),
             'shadow_size_2dfx': float(entry.shadow_size),
             'show_mode_2dfx': str(int(entry.corona_show_mode)),
             '2dfx_corona_enable_reflection': int(entry.corona_enable_reflection),
             'flare_type_2dfx': str(int(entry.corona_flare_type)),
             '2dfx_shadow_color_multiplier': int(entry.shadow_color_multiplier),
             '2dfx_flags1': int(entry.flags1), '2dfx_flags2': int(entry.flags2),
             'corona_tex_2dfx': entry.corona_tex_name or '',
             'shadow_tex_2dfx': entry.shadow_tex_name or '',
             '2dfx_shadow_z_distance': int(entry.shadow_z_distance)}
        if entry.look_direction is not None:
            v['2dfx_look_direction'] = tuple(float(x) for x in entry.look_direction)
        return 'LIGHT', v, loc
    if isinstance(entry, D.Particle2dfx):
        return 'PARTICLE', {'2dfx_effect_name': entry.effect_name or ''}, loc
    if isinstance(entry, D.PedAttractor2dfx):
        return 'PED_ATTRACTOR', {
            '2dfx_attractor_type': int(entry.attractor_type),
            '2dfx_rotation_matrix': tuple(float(x) for x in entry.rotation_matrix),
            '2dfx_external_script': entry.external_script or '',
            '2dfx_ped_probability': int(entry.ped_existing_probability)}, loc
    if isinstance(entry, D.SunGlare2dfx):
        return 'SUN_GLARE', {}, loc
    if isinstance(entry, D.EnterExit2dfx):
        return 'ENTER_EXIT', {
            'ee_enter_angle': float(entry.enter_angle),
            'ee_radius_x': float(entry.approximation_radius_x),
            'ee_radius_y': float(entry.approximation_radius_y),
            'ee_exit_loc': tuple(float(x) for x in entry.exit_loc),
            'ee_exit_angle': float(entry.exit_angle),
            'ee_interior': int(entry.interior), 'ee_sky_color': int(entry.sky_color),
            'ee_interior_name': entry.interior_name or '',
            'ee_time_on': int(entry.time_on), 'ee_time_off': int(entry.time_off)}, loc
    if isinstance(entry, D.RoadSign2dfx):
        f = int(entry.flags)
        lines = list(entry.text_lines) + ['', '', '', '']
        v = {'sign_size': tuple(float(x) for x in entry.size),
             'sign_rotation': tuple(float(x) for x in entry.rotation),
             'sign_lines': (f & 3) + 1,
             'sign_maxchars': ('16', '2', '4', '8')[(f >> 2) & 3],
             'sign_color': ('WHITE', 'BLACK', 'GREY', 'RED')[(f >> 4) & 3]}
        for i in range(4):
            v['sign_text%d' % i] = lines[i]
        return 'ROAD_SIGN', v, loc
    if isinstance(entry, D.Escalator2dfx):
        # точки — относительно маркера: двигаешь хелпер — едет весь эскалатор
        rel = [tuple(float(p[i]) - loc[i] for i in range(3))
               for p in (entry.bottom, entry.top, entry.end)]
        return 'ESCALATOR', {'esc_bottom': rel[0], 'esc_top': rel[1],
                             'esc_end': rel[2],
                             'esc_direction': '1' if entry.direction else '0'}, loc
    if isinstance(entry, D.RawUnknown2dfx):
        # байты неизвестного типа — hex-строкой: экспорт вернёт их как есть
        raw = bytes(entry.raw or b'')
        return 'RAW_2DFX', {'2dfx_raw_effect_id': int(entry.effect_id),
                            '2dfx_raw_size': len(raw), '2dfx_raw_hex': raw.hex()}, loc
    return None, {}, loc


# ── геометрия ────────────────────────────────────────────────────────

_CUSTOM_SHARP = math.radians(30.0)


def _np():
    import numpy as np
    return np


def _faces_aligned(geom):
    """Треугольники; если есть авторские нормали — намотка по ним (как
    _align_winding_to_normals INU: иначе грани «вывернуты»)."""
    np = _np()
    tri = np.array([(t.a, t.b, t.c) for t in geom.triangles], dtype=np.int64).reshape(-1, 3)
    mat = [int(t.material) for t in geom.triangles]
    V = np.asarray(geom.vertices, dtype=np.float64).reshape(-1, 3)
    if len(tri) and geom.normals and len(geom.normals) == len(V):
        N = np.asarray(geom.normals, dtype=np.float64).reshape(-1, 3)
        a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
        flip = np.einsum('ij,ij->i', np.cross(V[b] - V[a], V[c] - V[a]),
                         N[a] + N[b] + N[c]) < 0.0
        tri[flip, 1], tri[flip, 2] = tri[flip, 2].copy(), tri[flip, 1].copy()
    return tri, mat, V


def _unit(v):
    np = _np()
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return np.where(n > 1e-12, v / np.maximum(n, 1e-12), np.array([0.0, 0.0, 1.0]))


def corner_normals(tri, V, normals, vanilla):
    """Нормаль на каждый угол. Есть авторские — они. Нет (карты): ванильный
    путь — гладко внутри «острова» (усреднение по индексу вершины DFF: где
    файл разрезал вершины, ребро остаётся жёстким, как weld+sharp INU);
    кастомный — гладко по совпадающим позициям в пределах 30°."""
    np = _np()
    if len(tri) == 0:
        return []
    if normals is not None and len(normals) == len(V):
        N = _unit(np.asarray(normals, dtype=np.float64).reshape(-1, 3))
        return [tuple(map(float, N[i])) for i in tri.reshape(-1)]
    fn = np.cross(V[tri[:, 1]] - V[tri[:, 0]], V[tri[:, 2]] - V[tri[:, 0]])
    fu = _unit(fn)
    if vanilla:
        acc = np.zeros_like(V)
        for k in range(3):
            np.add.at(acc, tri[:, k], fn)
        N = _unit(acc)
        return [tuple(map(float, N[i])) for i in tri.reshape(-1)]
    # кастом: вершины с одной позицией — одна группа; сглаживаем только
    # грани в пределах угла
    _u, pos_id = np.unique(np.round(V, 4), axis=0, return_inverse=True)
    pos_id = pos_id.reshape(-1)
    by_pos = {}
    for f in range(len(tri)):
        for k in range(3):
            by_pos.setdefault(int(pos_id[tri[f, k]]), []).append(f)
    cos_t = math.cos(_CUSTOM_SHARP)
    out = []
    for f in range(len(tri)):
        for k in range(3):
            fs = by_pos[int(pos_id[tri[f, k]])]
            d = fu[fs] @ fu[f]
            n = fn[fs][d >= cos_t].sum(axis=0)
            nn = np.linalg.norm(n)
            out.append(tuple(map(float, n / nn)) if nn > 1e-12 else tuple(map(float, fu[f])))
    return out


def protected_verts(tri, V):
    """Вершины двусторонних граней (две грани на одних позициях — заборы):
    кастомная сварка их не трогает, иначе забор станет односторонним."""
    np = _np()
    if len(tri) == 0:
        return []
    key = {}
    for f in range(len(tri)):
        k = frozenset(tuple(np.round(V[i], 4)) for i in tri[f])
        key.setdefault(k, []).append(f)
    prot = set()
    for fs in key.values():
        if len(fs) >= 2:
            for f in fs:
                prot.update(int(i) for i in tri[f])
    return sorted(prot)


def welded(m, dist=1e-5):
    """(вершины, грани) геометрии после сварки совпадающих вершин (как
    remove_doubles INU). Сварка — ЗДЕСЬ, до создания меша: сварка Max
    (weldVertsByThreshold) удаляет схлопнувшиеся грани и сдвинула бы
    нумерацию граней, к которой привязаны нормали углов и каналы карт.
    Не свариваются: защищённые вершины (заборы) и вершины граней, которые
    от сварки схлопнулись бы."""
    np = _np()
    V = np.asarray(m.verts, dtype=np.float64).reshape(-1, 3)
    F = np.asarray(m.faces, dtype=np.int64).reshape(-1, 3)
    if m.weld == 'NONE' or len(V) == 0:
        return m.verts, m.faces
    keep = np.zeros(len(V), dtype=bool)
    if m.weld == 'PROTECT' and m.protect:
        keep[np.asarray(m.protect, dtype=np.int64)] = True
    key = np.round(V / dist).astype(np.int64)
    for _ in range(4):
        k = key.copy()
        # защищённым — уникальный ключ (не сливаются ни с кем)
        idx = np.nonzero(keep)[0]
        k[idx] = np.stack([np.full(len(idx), -(1 << 40)), idx, idx], axis=1) if len(idx) else k[idx]
        _u, first, inv = np.unique(k, axis=0, return_index=True, return_inverse=True)
        inv = inv.reshape(-1)
        G = inv[F]
        bad = (G[:, 0] == G[:, 1]) | (G[:, 1] == G[:, 2]) | (G[:, 0] == G[:, 2])
        # грань схлопнулась от сварки (в исходнике была целой) — её вершины
        # не свариваем
        was_ok = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
        newly = bad & was_ok
        if not newly.any():
            break
        keep[F[newly].reshape(-1)] = True
    verts = [tuple(map(float, V[i])) for i in first]
    return verts, [tuple(int(x) for x in g) for g in G]


def import_mesh(geom, vanilla=True, skinned=False):
    tri, mat, V = _faces_aligned(geom)
    m = ImportMesh(verts=[tuple(map(float, v)) for v in V],
                   faces=[tuple(int(i) for i in t) for t in tri], matids=mat)
    if geom.uv_layers:
        m.uv1 = [(float(t.u), 1.0 - float(t.v)) for t in geom.uv_layers[0]]
    if len(geom.uv_layers) > 1:
        m.uv2 = [(float(t.u), 1.0 - float(t.v)) for t in geom.uv_layers[1]]
    if geom.prelit_colors:
        m.day = [(c.r / 255.0, c.g / 255.0, c.b / 255.0) for c in geom.prelit_colors]
        m.alpha = [c.a / 255.0 for c in geom.prelit_colors]
    if geom.extra_colors and geom.extra_colors.colors:
        m.night = [(c.r / 255.0, c.g / 255.0, c.b / 255.0) for c in geom.extra_colors.colors]
    has_n = bool(geom.normals) and len(geom.normals) == len(geom.vertices)
    m.corner_normals = corner_normals(tri, V, geom.normals if has_n else None, vanilla)
    # сварка (как INU): скин — никогда (веса на вершину); с нормалями
    # (машины) — всегда, нормали явные; без нормалей — по галочке
    if skinned:
        m.weld = 'NONE'
    elif has_n or vanilla:
        m.weld = 'ALL'
    else:
        m.weld = 'PROTECT'
        m.protect = protected_verts(tri, V)
    return m


# ── матрицы фреймов ──────────────────────────────────────────────────

def _m4(fr):
    r, p = fr.rotation, fr.position
    return [[r[0], r[1], r[2], 0.0], [r[3], r[4], r[5], 0.0],
            [r[6], r[7], r[8], 0.0], [p[0], p[1], p[2], 1.0]]


def _rows(m):
    return (tuple(m[0][:3]), tuple(m[1][:3]), tuple(m[2][:3]), tuple(m[3][:3]))


def _world(frames):
    from .dff_build import _mul
    out = []
    for fr in frames:
        m = _m4(fr)
        out.append(_mul(m, out[fr.parent]) if 0 <= fr.parent < len(out) else m)
    return out


# ── коллизия ─────────────────────────────────────────────────────────

def _surface(s):
    return {'col_mat_index': int(s.material), 'col_flags': int(s.flags),
            'col_brightness': int(s.brightness),
            'col_day_light': int(s.light) & 0xF, 'col_night_light': (int(s.light) >> 4) & 0xF}


_COL_VERSION_TO_GAME = {1: 'III', 2: 'VC', 3: 'SA', 4: 'SA'}


def _bounds10(b):
    """Границы COL как 10 чисел (радиус, центр, AABB) — как inu_col_bounds INU."""
    return [float(b.radius), float(b.center.x), float(b.center.y), float(b.center.z),
            float(b.bb_min.x), float(b.bb_min.y), float(b.bb_min.z),
            float(b.bb_max.x), float(b.bb_max.y), float(b.bb_max.z)]


def col_models(models, base=None, with_prims=True, keep_bounds=True):
    """(меши, примитивы) из моделей COL (порт import_col_from_models INU):
    <имя>_COL / <имя>_sha, сферы и боксы <имя>_sphere_N / <имя>_box_N (с 0).
    Границы исходного COL сохраняются на первом объекте модели: экспорт
    вернёт их как есть (у машин R* считает их по сферам — камера и тень)."""
    meshes, prims = [], []
    for model in models or []:
        name = base or model.model_name or 'col_model'
        game = _COL_VERSION_TO_GAME.get(getattr(model, 'version', 0), '')
        first = []
        for verts, faces, shadow, sfx in ((model.vertices, model.faces, False, '_COL'),
                                          (model.shadow_vertices, model.shadow_faces, True, '_sha')):
            if not faces:
                continue
            surfs = [_surface(f.surface) for f in faces]
            if game:
                for s in surfs:
                    s['col_source_game'] = game
            m = ImportColMesh(
                name=name + sfx, verts=[(v.x, v.y, v.z) for v in verts],
                # обход GTA: при экспорте b и c меняются — возвращаем
                faces=[(f.a, f.c, f.b) for f in faces],
                surfaces=surfs, shadow=shadow, model=name)
            meshes.append(m)
            first.append(m)
        if with_prims:
            for i, s in enumerate(model.spheres):
                p = ImportColPrim(name="%s_sphere_%d" % (name, i), kind='SPHERE',
                                  center=(s.center.x, s.center.y, s.center.z),
                                  radius=float(s.radius), surface=_surface(s.surface),
                                  model=name)
                prims.append(p)
                first.append(p)
            for i, b in enumerate(model.boxes):
                p = ImportColPrim(name="%s_box_%d" % (name, i), kind='BOX',
                                  bb_min=(b.bb_min.x, b.bb_min.y, b.bb_min.z),
                                  bb_max=(b.bb_max.x, b.bb_max.y, b.bb_max.z),
                                  surface=_surface(b.surface), model=name)
                prims.append(p)
                first.append(p)
        if keep_bounds and first and getattr(model, 'bounds', None) is not None:
            first[0].bounds = _bounds10(model.bounds)
    return meshes, prims


def collision(data, base):
    """Меши и примитивы коллизии из встроенного в DFF блока (машины, педы)."""
    from inu_gta_core.col import read_col
    return col_models(read_col(data), base)


# ── план целиком ─────────────────────────────────────────────────────

_PIPES = {0x53F2009A: '0x53F2009A', 0x53F20098: '0x53F20098', 0x53F2009C: '0x53F2009C'}


def plan(clump, base, vanilla=True, with_2dfx=True):
    """ImportPlan из DffClump. base — имя файла без расширения."""
    frames, geoms = clump.frames or [], clump.geometries or []
    atomics = [a for a in (clump.atomics or [])
               if 0 <= a.geometry_index < len(geoms) and 0 <= a.frame_index < len(frames)]
    P = ImportPlan()
    skinned = any(geoms[a.geometry_index].skin is not None for a in atomics)
    P.skinned = skinned
    atomic_of = {}                                   # фрейм → [(порядок, геометрия)]
    for k, a in enumerate(atomics):
        atomic_of.setdefault(a.frame_index, []).append((k, a.geometry_index))
    light_frames = {l.frame_index for l in (clump.lights or [])}
    bone_frames = {i for i, f in enumerate(frames) if f.hanim is not None}
    worlds = _world(frames)
    n_geoms = len(geoms)

    def fname(i, gi=None):
        fr = frames[i]
        # одногеометрийная модель — имя файла (имя фрейма у таких часто
        # мусор моделлера); кроме костей: их имя ищут анимации
        if gi is not None and n_geoms <= 1 and not (fr.hanim is not None and _usable(fr.name)):
            return model_name(base, n_geoms, gi)
        if _usable(fr.name):
            return fr.name
        return model_name(base, n_geoms, gi) if gi is not None else frame_name(base, i)

    node_of = {}                                     # фрейм → узел плана
    geom_node = {}                                   # геометрия → узел плана
    table_frame = next((i for i in bone_frames if frames[i].hanim.bones), None)
    for i, fr in enumerate(frames):
        if i in light_frames and not atomic_of.get(i):
            continue                                 # Omni### — пишет экспорт сам
        parent = node_of.get(fr.parent, -1)
        at = atomic_of.get(i, [])
        own_mesh = at and not (skinned and geoms[at[0][1]].skin is not None)
        if own_mesh:
            order, gi = at[0]
            kind = 'MESH'
        else:
            kind = 'BONE' if (skinned and i in bone_frames) else 'DUMMY'
        n = ImportNode(name=fname(i, at[0][1] if own_mesh else None), kind=kind,
                       parent=parent, transform=_rows(_m4(fr)))
        if fr.hanim is not None:
            n.props['bone_id'] = int(fr.hanim.bone_id)
            if not skinned and i == table_frame:
                n.props['animobj_empty_root'] = True
        if own_mesh:
            geom = geoms[gi]
            n.mesh = import_mesh(geom, vanilla, skinned=False)
            n.materials = [material(m, getattr(clump.uv_anim_dict, 'anims', None), j)
                           for j, m in enumerate(geom.materials)]
            n.props.update(geometry_flags(geom))
            n.props['atomic_order'] = order
            geom_node[gi] = len(P.nodes)
        node_of[i] = len(P.nodes)
        P.nodes.append(n)
        # вторые атомики на том же фрейме (редко) — отдельные меши-дети
        for order, gi in at[1:] if own_mesh else at:
            geom = geoms[gi]
            if skinned and geom.skin is not None:
                continue
            m = ImportNode(name=("%s_%d" % (n.name[:20], gi))[:23], kind='MESH',
                           parent=node_of[i])
            m.mesh = import_mesh(geom, vanilla)
            m.materials = [material(x, getattr(clump.uv_anim_dict, 'anims', None), j)
                           for j, x in enumerate(geom.materials)]
            m.props.update(geometry_flags(geom))
            m.props['atomic_order'] = order
            geom_node[gi] = len(P.nodes)
            P.nodes.append(m)

    # геометрии без атомиков (редкие файлы) — меши в корне, как INU
    if not atomics:
        for gi, geom in enumerate(geoms):
            if not geom.vertices:
                continue
            n = ImportNode(name=model_name(base, n_geoms, gi), kind='MESH')
            n.mesh = import_mesh(geom, vanilla)
            n.materials = [material(x, getattr(clump.uv_anim_dict, 'anims', None), j)
                           for j, x in enumerate(geom.materials)]
            n.props.update(geometry_flags(geom))
            geom_node[gi] = len(P.nodes)
            P.nodes.append(n)

    # скин: меш — ребёнок корня модели, в мировой позе фрейма атомика
    # (не ребёнок кости: иначе двойная трансформация Skin + иерархии)
    if skinned:
        from .dff_build import _inv, _mul
        tbl = frames[table_frame].hanim.bones if table_frame is not None else []
        frame_of_id = {frames[i].hanim.bone_id: i for i in bone_frames}
        palette_size = max((int(b.index) for b in tbl), default=-1) + 1
        pal = [-1] * palette_size
        for b in tbl:
            if b.index >= 0:
                pal[b.index] = node_of.get(frame_of_id.get(b.bone_id, -1), -1)
        # Skin inverse bind matrices are authoritative for the rest pose.
        # Row vectors: IBM = mesh_world * inverse(bone_world).
        # Therefore bone_world = inverse(IBM) * mesh_world.
        bind_worlds = {}
        for a in atomics:
            skin = geoms[a.geometry_index].skin
            if skin is None:
                continue
            for b in tbl:
                fi = frame_of_id.get(b.bone_id)
                if fi is None or not (0 <= b.index < len(skin.bone_matrices)):
                    continue
                world = _mul(_inv(skin.bone_matrices[b.index]), worlds[a.frame_index])
                if fi in bind_worlds:
                    if any(abs(world[r][c] - bind_worlds[fi][r][c]) > 1e-4
                           for r in range(4) for c in range(4)):
                        raise ValueError('Conflicting Skin bind poses for bone %s' % b.bone_id)
                bind_worlds[fi] = world
        corrected = [bind_worlds.get(i, w) for i, w in enumerate(worlds)]
        for fi in bone_frames:
            ni = node_of.get(fi)
            if ni is None:
                continue
            parent = frames[fi].parent
            local = (_mul(corrected[fi], _inv(corrected[parent]))
                     if parent >= 0 else corrected[fi])
            P.nodes[ni].transform = _rows(local)
        root_i = next((i for i, f in enumerate(frames) if f.parent < 0), 0)
        for order, a in enumerate(atomics):
            geom = geoms[a.geometry_index]
            if geom.skin is None:
                continue
            local = _mul(worlds[a.frame_index], _inv(corrected[root_i]))
            n = ImportNode(name=model_name(base, n_geoms, a.geometry_index),
                           kind='MESH', parent=node_of.get(root_i, -1), transform=_rows(local))
            n.mesh = import_mesh(geom, vanilla, skinned=True)
            n.materials = [material(x, getattr(clump.uv_anim_dict, 'anims', None), j)
                           for j, x in enumerate(geom.materials)]
            n.props.update(geometry_flags(geom))
            n.props['atomic_order'] = order
            sk = geom.skin
            n.mesh.skin = []
            for ix, ws in zip(sk.bone_indices, sk.bone_weights):
                n.mesh.skin.append([(pal[i], float(w)) for i, w in zip(ix, ws)
                                    if w > 0 and 0 <= i < len(pal) and pal[i] >= 0])
            geom_node[a.geometry_index] = len(P.nodes)
            P.nodes.append(n)
        P.pipeline = 'PED'

    # 2DFX — дети меша той геометрии, где лежат
    if with_2dfx:
        for gi, geom in enumerate(geoms):
            if not (geom.ext_2dfx and geom.ext_2dfx.entries):
                continue
            host = geom_node.get(gi, -1)
            for k, e in enumerate(geom.ext_2dfx.entries):
                eff, vals, loc = fx_fields(e)
                if eff is None:
                    continue
                P.fx.append(ImportFx(effect=eff, fields=vals, loc=loc, parent=host,
                                     name="%s_2dfx_%s_%d" % (base, eff.lower(), k)))

    if clump.collision_data:
        try:
            P.col_meshes, P.col_prims = collision(clump.collision_data, base)
        except Exception as e:                        # noqa: BLE001
            P.warnings.append("embedded collision not read: %s" % e)

    if not P.pipeline:
        # самый частый pipeline геометрий; нет чанка — None (как
        # _autoset_scene_pipeline INU: иначе остаётся прошлый выбор)
        from collections import Counter
        cnt = Counter(int(g.pipeline) for g in geoms if g.pipeline)
        P.pipeline = _PIPES.get(cnt.most_common(1)[0][0], 'NONE') if cnt else 'NONE'
    return P


def plan_file(path, vanilla=True, with_2dfx=True):
    from inu_gta_core.dff import read_dff
    with open(path, 'rb') as f:
        clump = read_dff(f.read())
    return plan(clump, os.path.splitext(os.path.basename(path))[0], vanilla, with_2dfx), clump
