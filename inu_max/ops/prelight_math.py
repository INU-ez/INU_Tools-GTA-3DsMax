# INU Tools (Max) — расчёт Prelight (цвет вершин от ламп), без Max: numpy.
#
# Порт tools/prelight.py Blender-версии INU (bake_vertex_colors_simple и
# bake_vertex_colors_from_lights) — те же формулы:
#   «Bake»:             T = ambient + Σ C·max(N·L,0)·att·spot, C = цвет·энергия·Intensity,
#                       att = 1/(1 + 1e-4·d²); затем T^(1/Gamma), 0..1
#   «Bake with shadows»: T = Σ C·max(N·L,0)·att·spot·тень, C = цвет·энергия,
#                       att = 1/(1 + 0.01·d + 1e-4·d²); 0..1
# Солнце — без затухания (направление на солнце = +Z лампы).
#
# Цвет — как в Blender: там результат пишется в «.color» (линейное
# пространство), а в байт вершины попадает sRGB-кодированное значение.
# Каналы Max хранят именно байт/255 (как color_srgb Blender), поэтому здесь
# в канал уходит lin2srgb(T), округлённое до 1/255 (как пишет Blender).
#
# Исправлено против Blender (решение пользователя: «чинить, модель не менять»):
# - позиции ламп — мировые (в Blender — локальные: лампа с родителем «не там»);
# - «Bake over» не прибавляет Ambient повторно (в Blender — при каждом нажатии);
# - все фильтры Point/Sun/Spot/Area выключены — ламп нет (в Blender — все).
#
# Часть 2 (Post-Processing, Инструменты, Листва) — внизу файла.

import math

import numpy as np

F32 = np.float32


def srgb2lin(s):
    """sRGB → линейный (srgb_to_linearrgb Blender)."""
    s = np.asarray(s, dtype=F32)
    return np.where(s < 0.04045, np.maximum(s, 0.0) / F32(12.92),
                    ((s + F32(0.055)) / F32(1.055)) ** F32(2.4)).astype(F32)


def lin2srgb(c):
    """Линейный → sRGB (linearrgb_to_srgb Blender)."""
    c = np.asarray(c, dtype=F32)
    return np.where(c < 0.0031308, np.maximum(c, 0.0) * F32(12.92),
                    F32(1.055) * np.power(np.maximum(c, 0.0), F32(1.0 / 2.4)) - F32(0.055)
                    ).astype(F32)


def quant(v):
    """Как запись в байтовый цвет Blender: floor(255·v + 0.5) / 255, 0..1."""
    v = np.clip(np.asarray(v, dtype=F32), 0.0, 1.0)
    return (np.floor(v * F32(255.0) + F32(0.5)) / F32(255.0)).astype(F32)


def vertex_normals(pos, faces):
    """Нормали вершин (как vertices.normal Blender — средние нормалей граней,
    взвешенные углом при вершине), единичные."""
    pos = np.asarray(pos, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    nv = len(pos)
    vn = np.zeros((nv, 3))
    if len(faces) == 0:
        return vn.astype(F32)
    p = pos[faces]                                     # (nf, 3, 3)
    fn = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    fl = np.linalg.norm(fn, axis=1, keepdims=True)
    fn = np.where(fl > 1e-20, fn / np.where(fl > 1e-20, fl, 1.0), 0.0)
    for c in range(3):
        a = p[:, (c + 1) % 3] - p[:, c]
        b = p[:, (c + 2) % 3] - p[:, c]
        la = np.linalg.norm(a, axis=1)
        lb = np.linalg.norm(b, axis=1)
        cosang = np.einsum('ij,ij->i', a, b) / np.maximum(la * lb, 1e-20)
        ang = np.arccos(np.clip(cosang, -1.0, 1.0))
        np.add.at(vn, faces[:, c], fn * ang[:, None])
    ln = np.linalg.norm(vn, axis=1, keepdims=True)
    return np.where(ln > 1e-12, vn / np.where(ln > 1e-12, ln, 1.0), 0.0).astype(F32)


def _unit(v):
    v = np.asarray(v, dtype=F32)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n < 1e-6, F32(1.0), n)


def shadow_rays(light, pos_v, nrm_v):
    """Лучи тени одной лампы — по одному на вершину (как в Blender: общий для
    всех углов вершины). Возвращает (rays (n,7) float32: начало, направление,
    длина; индексы вершин, для которых луч пускается)."""
    pos_v = np.asarray(pos_v, dtype=F32)
    start = pos_v + np.asarray(nrm_v, dtype=F32) * F32(0.02)
    if light['type'] == 'SUN':
        d = np.broadcast_to(_unit(light['to_light']), pos_v.shape)
        tmax = np.full(len(pos_v), 1.0e4, dtype=F32)
        idx = np.arange(len(pos_v))
    else:
        ld = np.asarray(light['pos'], dtype=F32)[None, :] - pos_v
        dist = np.linalg.norm(ld, axis=1)
        idx = np.nonzero(dist >= 1e-3)[0]               # ближе 1 мм — без луча (освещена)
        d = ld[idx] / dist[idx, None]
        start = start[idx]
        tmax = (dist[idx] - F32(0.04)).astype(F32)
    rays = np.concatenate([start, d, tmax[:, None]], axis=1).astype(F32)
    return rays, idx


def spot_factor(light, pos_c):
    """Конус прожектора (линейно по косинусу, как _spot_cone_factor)."""
    fwd = _unit(light['fwd'])
    d = _unit(pos_c - np.asarray(light['pos'], dtype=F32)[None, :])
    cos_a = d @ fwd
    denom = (light['cos_in'] - light['cos_out']) or 1e-4
    return np.clip((cos_a - light['cos_out']) / denom, 0.0, 1.0).astype(F32)


def light_total(pos_v, faces, n_c, lights, shadows=None, *, model='SIMPLE',
                ambient=0.10, intensity=0.05, over=False, env=None):
    """Линейная освещённость T на каждый угол (nf·3, 3) ДО гаммы/кодирования.

    pos_v (nv,3) мир; faces (nf,3) с 0; n_c (nf,3,3) нормали углов (мир,
    единичные); lights — список словарей (adapter.prelight_scene.lights);
    shadows — {номер лампы: (nv,) 0/1} или None; env — (nf·3, 3) вклад
    окружения или None."""
    faces = np.asarray(faces, dtype=np.int64)
    vidx = faces.reshape(-1)
    pos_c = np.asarray(pos_v, dtype=F32)[vidx]
    nrm_c = np.asarray(n_c, dtype=F32).reshape(-1, 3)
    simple = model == 'SIMPLE'
    start = ambient if (simple and not over) else 0.0
    total = np.full((len(vidx), 3), start, dtype=F32)
    for li, L in enumerate(lights):
        col = np.asarray(L['color'], dtype=F32) * F32(L['energy'] * (intensity if simple else 1.0))
        sh = shadows.get(li) if shadows else None
        s_c = sh[vidx].astype(F32) if sh is not None else None
        if L['type'] == 'SUN':
            ndl = np.maximum(nrm_c @ _unit(L['to_light']), 0.0).astype(F32)
            if s_c is not None:
                ndl = ndl * s_c
            total += ndl[:, None] * col[None, :]
            continue
        ld = np.asarray(L['pos'], dtype=F32)[None, :] - pos_c
        dist = np.linalg.norm(ld, axis=1)
        valid = dist >= 1e-3
        ld_n = ld / np.where(valid, dist, 1.0)[:, None]
        ndl = np.where(valid, np.maximum(np.sum(nrm_c * ld_n, axis=1), 0.0), 0.0)
        if simple:
            att = 1.0 / (1.0 + dist * dist * 1e-4)
        else:
            att = 1.0 / (1.0 + dist * 0.01 + dist * dist * 1e-4)
        inten = (att * ndl).astype(F32)
        if s_c is not None:
            inten = inten * s_c
        if L['type'] == 'SPOT':
            inten = inten * spot_factor(L, pos_c)
        total += inten[:, None] * col[None, :]
    if env is not None:
        total += np.asarray(env, dtype=F32)
    return total


def encode(total, *, model='SIMPLE', gamma=0.5):
    """T → значения канала (байт/255): гамма «Bake», 0..1, sRGB, 1/255."""
    t = np.asarray(total, dtype=F32)
    if model == 'SIMPLE':
        t = np.power(np.maximum(t, 0.0), F32(1.0 / gamma)).astype(F32)
    t = np.clip(t, 0.0, 1.0)
    return quant(lin2srgb(t))


def add_over(old, new):
    """«Bake over»: сложение с тем, что было (в байтовом пространстве, как
    _bake_add_over), 0..1."""
    return quant(np.asarray(old, dtype=F32) + np.asarray(new, dtype=F32))


def v_scale(values, v_new, v_applied=0.0):
    """Поле V (сдвиг яркости в %): как apply_brightness_offset — множитель
    (1+V/100)/(1+V_применённый/100) в ЛИНЕЙНОМ пространстве, 0..1."""
    k = max(0.0, 1.0 + v_new / 100.0) / max(0.001, 1.0 + v_applied / 100.0)
    lin = srgb2lin(values) * F32(k)
    return quant(lin2srgb(np.clip(lin, 0.0, 1.0)))


def sun_rows(rot_x_deg=50.0, rot_y_deg=0.0, rot_z_deg=40.0):
    """Строки матрицы Max «солнца» Prelight: как rotation_euler Blender
    (XYZ: R = Rz·Ry·Rx); строки Max = столбцы матрицы Blender."""
    ax, ay, az = (math.radians(a) for a in (rot_x_deg, rot_y_deg, rot_z_deg))
    rx = np.array([[1, 0, 0], [0, math.cos(ax), -math.sin(ax)], [0, math.sin(ax), math.cos(ax)]])
    ry = np.array([[math.cos(ay), 0, math.sin(ay)], [0, 1, 0], [-math.sin(ay), 0, math.cos(ay)]])
    rz = np.array([[math.cos(az), -math.sin(az), 0], [math.sin(az), math.cos(az), 0], [0, 0, 1]])
    r = rz @ ry @ rx
    return [list(map(float, r[:, i])) for i in range(3)]


def _rgb_to_hsv(c):
    r, g, b = c[:, 0], c[:, 1], c[:, 2]
    mx = np.max(c, axis=1)
    mn = np.min(c, axis=1)
    d = mx - mn
    h = np.zeros_like(mx)
    nz = d > 1e-12
    rc = np.where(nz, (mx - r) / np.where(nz, d, 1.0), 0.0)
    gc = np.where(nz, (mx - g) / np.where(nz, d, 1.0), 0.0)
    bc = np.where(nz, (mx - b) / np.where(nz, d, 1.0), 0.0)
    h = np.where(r == mx, bc - gc, np.where(g == mx, 2.0 + rc - bc, 4.0 + gc - rc))
    h = np.where(nz, (h / 6.0) % 1.0, 0.0)
    s = np.where(mx > 1e-12, d / np.where(mx > 1e-12, mx, 1.0), 0.0)
    return h, s, mx


def _hsv_to_rgb(h, s, v):
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i = i.astype(np.int64) % 6
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=1)


def view_correct(values, bright=0.0, contrast=0.0, gamma=1.0, sat=1.0):
    """Коррекция превью Prelight (только вьюпорт) — как цепочка узлов
    Blender-версии: Bright/Contrast → Gamma → Hue/Saturation, над линейным
    цветом слоя. (0, 0, 1, 1) — без изменений."""
    v = np.asarray(values, dtype=F32)
    if abs(bright) < 1e-9 and abs(contrast) < 1e-9 and abs(gamma - 1.0) < 1e-9 \
            and abs(sat - 1.0) < 1e-9:
        return v
    lin = srgb2lin(v).astype(np.float64)
    a = 1.0 + contrast
    b = bright - contrast * 0.5
    lin = np.maximum(a * lin + b, 0.0)
    lin = np.where(lin > 0.0, np.power(lin, gamma), lin)
    if abs(sat - 1.0) > 1e-9:
        h, s, mx = _rgb_to_hsv(lin)
        lin = _hsv_to_rgb(h, np.clip(s * sat, 0.0, 1.0), mx)
    return quant(lin2srgb(np.clip(lin, 0.0, 1.0).astype(F32)))


def dedupe_corners(faces, values):
    """Значения на угол (nf·3, 3) → (вершины канала, грани канала с 0):
    один узел канала на пару (вершина, цвет) — канал компактный, а разные
    цвета углов одной вершины сохраняются."""
    vidx = np.asarray(faces, dtype=np.int64).reshape(-1)
    q = np.rint(np.asarray(values, dtype=np.float64) * 255.0).astype(np.int64)
    key = np.concatenate([vidx[:, None], q], axis=1)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    verts = uniq[:, 1:].astype(F32) / F32(255.0)
    return verts, inv.reshape(-1, 3)


# ── часть 2: Post-Processing, Инструменты, Листва ────────────────────
# Порт tools/prelight.py и ops/light_ops.py Blender-версии. Там эти операции
# работают с «.color» (линейное пространство) и пишут в байтовый цвет —
# здесь: srgb2lin → операция → lin2srgb → до 1/255. Альфа вершин (в Blender —
# в том же слое) не трогается: в Max это отдельный канал −2 (решение
# пользователя). Цвета палитры (sRGB) переводятся в линейное — в Blender
# они подставлялись как линейные и результат выходил светлее палитры
# (решение пользователя: «чинить»).

def _lin(values):
    return srgb2lin(values).astype(np.float64)


def _enc(lin):
    return quant(lin2srgb(np.clip(lin, 0.0, 1.0).astype(F32)))


def pp_smooth(values, faces, n_verts, iterations=1, factor=0.5):
    """«Сгладить» (smooth_vertex_colors): цвет вершины — среднее её углов;
    за проход — смесь со средним соседей по рёбрам (своё·(1−f) + соседи·f),
    результат — во все углы вершины. Как в Blender, после каждого прохода
    цвет округляется до байта (запись в байтовый слой)."""
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    cv = faces.reshape(-1)
    cnt = np.bincount(cv, minlength=n_verts).astype(np.float64)
    used = cnt > 0
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e = np.unique(np.sort(e, axis=1), axis=0)
    a, b = e[:, 0], e[:, 1]
    corner = _lin(values)
    f = float(factor)
    for _ in range(max(1, int(iterations))):
        vcol = np.zeros((n_verts, 3))
        np.add.at(vcol, cv, corner)
        vcol[used] /= cnt[used, None]
        nsum = np.zeros((n_verts, 3))
        ncnt = np.zeros(n_verts)
        ok = used[b]
        np.add.at(nsum, a[ok], vcol[b[ok]])
        np.add.at(ncnt, a[ok], 1.0)
        ok = used[a]
        np.add.at(nsum, b[ok], vcol[a[ok]])
        np.add.at(ncnt, b[ok], 1.0)
        has = used & (ncnt > 0)
        sm = vcol.copy()
        sm[has] = vcol[has] * (1.0 - f) + (nsum[has] / ncnt[has, None]) * f
        corner = _lin(_enc(sm[cv]))
    return _enc(corner)


def pp_contrast(values, contrast=1.0):
    """«Контраст» (adjust_vertex_colors_contrast): новое = ср + (старое − ср)
    · контраст; среднее — по всем углам слоя, по каналам."""
    lin = _lin(values)
    if len(lin) == 0:
        return np.asarray(values, dtype=F32)
    avg = lin.mean(axis=0)
    return _enc(avg + (lin - avg) * float(contrast))


def pp_brightness(values, brightness=0.0):
    """«Яркость» (adjust_vertex_colors_brightness): прибавка к каналам."""
    return _enc(_lin(values) + float(brightness))


def pp_gamma(values, gamma=1.0):
    """«Гамма» (adjust_vertex_colors_gamma): канал^гамма."""
    return _enc(np.power(np.maximum(_lin(values), 0.0), float(gamma)))


def pp_lift_shadows(values, strength=0.5):
    """«Подтянуть тени» (lift_shadows): яркость угла (среднее RGB) тянется
    к максимальной по слою на strength, оттенок сохраняется; почти чёрные
    углы (≤ 1e-4) не трогаются. None — всё чёрное, нечего делать."""
    lin = _lin(values)
    br = lin.mean(axis=1)
    target = float(br.max()) if len(br) else 0.0
    if target <= 1e-6:
        return None
    valid = br > 1e-4
    new_b = br + (target - br) * float(strength)
    scale = np.ones(len(br))
    scale[valid] = new_b[valid] / br[valid]
    return _enc(lin * scale[:, None])


def scatter_color(values, pos, faces, sel_faces, color_lin, strength=1.0, distance=0.3):
    """«Рассеять цвет» (scatter_color_from_selected): вершины выделенных
    граней — полный вклад, дальше линейно до 0 на радиусе distance · ½
    диагонали габарита меша (координаты объекта); вклад × strength; цвет
    слоя смешивается с color_lin (линейный) в линейном пространстве.
    Возвращает (значения, выделенных вершин, затронутых вершин, радиус)."""
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    pos = np.asarray(pos, dtype=np.float64)
    sel_v = np.unique(faces[np.asarray(sel_faces, dtype=np.int64)].reshape(-1))
    nv = len(pos)
    half = float(np.linalg.norm(pos.max(axis=0) - pos.min(axis=0))) * 0.5
    rad = max(0.001, half * float(distance))
    blend = np.zeros(nv)
    sp = pos[sel_v].astype(np.float32)
    p32 = pos.astype(np.float32)
    # расстояние до ближайшей выделенной вершины — перебором кусками
    step = max(1, 1_000_000 // max(1, len(sp)))
    for i in range(0, nv, step):
        diff = p32[i:i + step, None, :] - sp[None, :, :]
        d = np.sqrt((diff * diff).sum(axis=2)).min(axis=1).astype(np.float64)
        blend[i:i + step] = np.where(d <= rad, 1.0 - d / rad, 0.0)
    blend[sel_v] = 1.0
    blend *= float(strength)
    f = blend[faces.reshape(-1)][:, None]
    out = _lin(values) * (1.0 - f) + np.asarray(color_lin, dtype=np.float64)[None, :3] * f
    return _enc(out), len(sel_v), int(np.count_nonzero(blend)), rad


def foliage(values, pos, faces, face_mask, *, mode='SHADE', inside=0.25, outside=1.0,
            gamma=1.0, height_dark=0.0, color_height_dark=0.0, top_bright=0.0,
            top_height=1.0, variation=0.0, light_tint=(1.0, 1.0, 1.0),
            shadow_tint=(1.0, 1.0, 1.0), tint_strength=0.0, metric='SPHERE',
            blend='MULTIPLY', both_sides=False):
    """«Листва / Дерево» (prelight_foliage): радиальный градиент кроны
    (внутри темнее, снаружи светлее) — mode SHADE; цвет листвы (тень в
    центре → свет по краю), подсветка верха, затемнение низа, разброс —
    mode COLOR. Координаты — объекта; face_mask — грани листвы (материал /
    выделение). Цвета палитры light_tint / shadow_tint — sRGB. Возвращает
    (значения, окрашено углов) или (None, текст)."""
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    pos = np.asarray(pos, dtype=np.float64)
    nv = len(pos)
    loop_v = faces.reshape(-1)
    loop_pos = pos[loop_v]
    poly_mask = np.asarray(face_mask, dtype=bool).copy()
    # «Обе стороны»: дубль листа (любая триангуляция) — грань, ВСЕ вершины
    # которой лежат в позициях окрашиваемых вершин (сетка 1e-3 ± 1 ячейка)
    if both_sides and poly_mask.any():
        tol = 1.0e-3
        qt = [tuple(r) for r in np.round(pos / tol).astype(np.int64).tolist()]
        cells = set()
        for vid in np.unique(faces[poly_mask].reshape(-1)).tolist():
            bx, by, bz = qt[vid]
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        cells.add((bx + dx, by + dy, bz + dz))
        for fi in np.nonzero(~poly_mask)[0].tolist():
            if all(qt[v] in cells for v in faces[fi].tolist()):
                poly_mask[fi] = True
    mask = np.repeat(poly_mask, 3)
    if not mask.any():
        return None, "No matching faces (material / selection empty)"
    center = loop_pos[mask].mean(axis=0)
    if metric == 'CYLINDER':
        dist = np.linalg.norm(loop_pos[:, :2] - center[:2], axis=1)
    else:
        dist = np.linalg.norm(loop_pos - center, axis=1)
    dmax = float(dist[mask].max())
    if dmax < 1e-9:
        dmax = 1.0
    tgrad = np.clip(dist / dmax, 0.0, 1.0) ** max(float(gamma), 1e-3)
    apply_shade = mode in ('SHADE', 'BOTH')
    apply_color = mode in ('COLOR', 'BOTH')
    z = loop_pos[:, 2]
    zmin, zmax = float(z[mask].min()), float(z[mask].max())
    zt = (np.clip((z - zmin) / (zmax - zmin), 0.0, 1.0) if zmax - zmin > 1e-9
          else np.zeros(len(z)))
    if apply_shade:
        bright = float(inside) + (float(outside) - float(inside)) * tgrad
        if height_dark > 0.0:
            bright = bright * ((1.0 - float(height_dark)) + float(height_dark) * zt)
        bright = np.clip(bright, 0.0, 1.0)
    else:
        bright = np.ones(len(z))
    eff_tint = np.ones((1, 3))
    if apply_color:
        if color_height_dark > 0.0:
            bright = bright * ((1.0 - float(color_height_dark)) + float(color_height_dark) * zt)
        if top_bright > 0.0:
            thr = 1.0 - float(np.clip(top_height, 0.0, 1.0))
            zt_top = np.clip((zt - thr) / max(1.0 - thr, 1e-6), 0.0, 1.0)
            bright = bright * (1.0 + float(top_bright) * zt_top)
        if variation > 0.0:                      # как в Blender: seed 1234, по вершинам
            rng = np.random.default_rng(1234)
            vrand = rng.uniform(1.0 - float(variation), 1.0, size=nv).astype(F32)
            bright = bright * vrand[loop_v]
        light = _lin(np.asarray(light_tint, dtype=F32)[:3])
        shadow = _lin(np.asarray(shadow_tint, dtype=F32)[:3])
        s = float(np.clip(tint_strength, 0.0, 1.0))
        tint_per = shadow[None, :] * (1.0 - tgrad[:, None]) + light[None, :] * tgrad[:, None]
        eff_tint = (1.0 - s) + s * tint_per
    lin = _lin(values)
    shade = bright[:, None] * eff_tint
    out = lin * shade if blend == 'MULTIPLY' else np.broadcast_to(shade, lin.shape)
    res = lin.copy()
    res[mask] = np.clip(out[mask], 0.0, 1.0)
    return _enc(res), int(mask.sum())


def smooth_between(objs, tol=0.001):
    """«Сгладить между объектами» (vc_smooth_between): вершины разных
    объектов в одной точке (± tol, мировые координаты) — всем их углам
    среднее цвета этих углов (линейное). objs — [(позиции (nv,3) мир,
    грани (nf,3), значения на угол (nf·3,3))]. Порядок обхода как в
    Blender (объекты, затем вершины). Возвращает (значения по объектам,
    число стыков)."""
    lins, corners, pos_all, obj_of, v_of = [], [], [], [], []
    for oi, (pos, faces, vals) in enumerate(objs):
        cv = np.asarray(faces, dtype=np.int64).reshape(-1)
        nv = len(pos)
        lins.append(_lin(vals))
        order = np.argsort(cv, kind='stable')
        bounds = np.searchsorted(cv[order], np.arange(nv + 1))
        corners.append((order, bounds))
        pos_all.append(np.asarray(pos, dtype=np.float64))
        obj_of.append(np.full(nv, oi))
        v_of.append(np.arange(nv))
    if not pos_all:
        return [], 0
    pts = np.concatenate(pos_all)
    obj_of = np.concatenate(obj_of)
    v_of = np.concatenate(v_of)
    keys = np.floor(pts / tol).astype(np.int64)
    grid = {}
    for i, k in enumerate(map(tuple, keys.tolist())):
        grid.setdefault(k, []).append(i)
    processed = np.zeros(len(pts), dtype=bool)
    seams = 0
    for i in range(len(pts)):
        if processed[i]:
            continue
        kx, ky, kz = keys[i]
        cand = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    cand.extend(grid.get((kx + dx, ky + dy, kz + dz), ()))
        if len(cand) < 2:
            continue
        cand = np.asarray(cand)
        m = cand[np.linalg.norm(pts[cand] - pts[i], axis=1) <= tol]
        if len(m) < 2 or len(set(obj_of[m].tolist())) < 2:
            continue
        idx = []
        for p in m.tolist():
            order, bounds = corners[obj_of[p]]
            v = v_of[p]
            idx.append((obj_of[p], order[bounds[v]:bounds[v + 1]]))
        cols = [lins[o][c] for o, c in idx if len(c)]
        processed[m] = True
        if not cols:
            continue
        avg = np.concatenate(cols).mean(axis=0)
        for o, c in idx:
            lins[o][c] = avg
        seams += 1
    return [_enc(lin) for lin in lins], seams


# ── часть 3: PreLight COL (свет граней коллизии 0..15) ───────────────
# Порт tools/col_light.py Blender-версии: яркость угла = max(R, G, B) в
# ЛИНЕЙНОМ пространстве (там «.color»), среднее по грани, «Край» — гамма,
# S-контраст, «Порог», перевод в Min..Max, round (банковское, как round()
# Python), 0..15. «Порог» учитывается и в запекании (решение пользователя;
# в Blender — только в превью, и результат мог не совпасть с превью).

def col_gamma(edge):
    """Гамма из «Края»: ≥ 0 — расширить светлое (гамма < 1), < 0 — сжать."""
    edge = float(edge)
    return 1.0 / (1.0 + edge * 4.0) if edge >= 0.0 else 1.0 + abs(edge) * 4.0


def col_threshold(slider):
    """«Порог» 0..100 → доля яркости: (100 − s) / 10000; 100 — без порога."""
    slider = int(slider)
    return (100 - slider) / 10000.0 if slider < 100 else 0.0


def col_levels(values, vmin, vmax, edge=0.0, contrast=0.0, threshold=0):
    """Уровень света COL на грань (nf,) int 0..15 из значений слоя на угол
    (nf·3, 3) sRGB. threshold — слайдер «Порог» (0..100)."""
    br = _lin(values).max(axis=1).reshape(-1, 3).mean(axis=1)
    avg = np.clip(br, 0.0, 1.0)
    g = col_gamma(edge)
    avg = np.where(avg > 0.0, np.power(np.maximum(avg, 0.0), g), avg)
    contrast = float(contrast)
    if contrast > 0.0:
        k = 1.0 + contrast * 10.0
        avg = np.where(avg < 0.5, 0.5 * np.power(2.0 * avg, k),
                       1.0 - 0.5 * np.power(2.0 * (1.0 - avg), k))
    thr = col_threshold(threshold)
    below = np.zeros(len(avg), dtype=bool)
    if thr > 0.0:
        below = avg < thr
        if thr < 1.0:
            avg = (avg - thr) / (1.0 - thr)
    value = float(vmin) + avg * (float(vmax) - float(vmin))
    lv = np.clip(np.round(value), 0, 15).astype(np.int64)
    lv[below] = 0
    return lv


def col_border(faces, levels):
    """Грани у границы уровней (цифры превью): у какой-то грани с общей
    вершиной — другой уровень."""
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    lv = np.asarray(levels, dtype=np.int64)
    if not len(faces):
        return np.zeros(0, dtype=bool)
    nv = int(faces.max()) + 1
    cv = faces.reshape(-1)
    fl = np.repeat(lv, 3)
    vmin = np.full(nv, 99, dtype=np.int64)
    vmax = np.full(nv, -1, dtype=np.int64)
    np.minimum.at(vmin, cv, fl)
    np.maximum.at(vmax, cv, fl)
    mixed = vmin != vmax
    return mixed[faces].any(axis=1)
