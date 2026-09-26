# INU Tools (Max) — 2DFX на общем ядре: effects.fxp (системы частиц, их
# эмиттеры, параметры и кривые) и источник текстур эффектов (.txd) — как
# _particle_effect_enum_items / _sample_particle_from_emitter /
# resolve_fx_txd_display Blender-версии INU. Только чтение файлов.

import os

# отдельные TXD эффектов в <игра>/models — в порядке приоритета (как INU)
_FX_TXD_CANDIDATES = ('particle.txd', 'particle2.txd', 'effectsPC.txd',
                      'misc.txd')


def fxp_path(game_root):
    return os.path.join(game_root or '', 'models', 'effects.fxp')


def _fxp(game_root):
    """(FXFile, None) или (None, текст для списка) — как пункты-заглушки
    выпадающего списка INU."""
    if not game_root or not os.path.isdir(game_root):
        return None, "<Game Root is not set>"
    path = fxp_path(game_root)
    if not os.path.isfile(path):
        return None, "<effects.fxp not found>"
    from inu_gta_core import fxp
    return fxp.load_cached(path), None


def systems(game_root):
    """(имена систем, заглушка '' | текст)."""
    try:
        fxf, err = _fxp(game_root)
    except Exception as e:                             # noqa: BLE001
        return [], "<error: %s>" % e
    if fxf is None:
        return [], err
    names = [s.name for s in fxf.systems]
    return names, ('' if names else "<no effects>")


def reload():
    """«Reload effects.fxp»: сбросить кэш ядра."""
    from inu_gta_core import fxp
    fxp.clear_cache()


def _system(game_root, name):
    fxf, _err = _fxp(game_root)
    return fxf.find(name) if fxf is not None and name else None


def emitter_count(game_root, name):
    try:
        s = _system(game_root, name)
    except Exception:                                  # noqa: BLE001
        return 0
    return len(s.emitters) if s is not None else 0


def particle_params(game_root, name, index=0):
    """Параметры index-го эмиттера системы name — поля particle_* INU
    (как _populate_particle_props_from_fxp); None — нет системы."""
    s = _system(game_root, name)
    if s is None or not s.emitters:
        return None
    em = s.emitters[max(0, min(index, len(s.emitters) - 1))]
    vals = _sample(em)
    for key, head, cast, dflt in (('particle_sys_length', 'LENGTH', float, 1.0),
                                  ('particle_sys_playmode', 'PLAYMODE', int, 2),
                                  ('particle_sys_culldist', 'CULLDIST', float, 50.0)):
        try:
            vals[key] = cast(s.header_get(head) or dflt)
        except ValueError:
            vals[key] = dflt
    return vals


def _sample(em):
    """Порт _sample_particle_from_emitter INU: значения на t=0 / t=1."""
    tex = (em.base_get('TEXTURE') or '').strip()

    def _int(key, dflt):
        try:
            return int(em.base_get(key) or dflt)
        except (TypeError, ValueError):
            return dflt

    def cv(info_type, fld, default=0.0, t=0.0):
        info = em.info(info_type)
        c = info.curves.get(fld) if info else None
        return c.sample(t) if c else default

    def rgba(t):
        return tuple(max(min(cv('COLOUR', ch, 255.0, t) / 255.0, 1.0), 0.0)
                     for ch in ('RED', 'GREEN', 'BLUE', 'ALPHA'))

    colour = em.info('COLOUR')
    mid, mid_t = False, 0.5
    if colour is not None:
        for ch in ('ALPHA', 'RED', 'GREEN', 'BLUE'):
            c = colour.curves.get(ch)
            if c is not None and len(c.keys) >= 3:
                mid = True
                if ch == 'ALPHA':
                    mid_t = max(0.01, min(c.keys[len(c.keys) // 2].time, 0.99))
                    break

    def half(axis):
        return max(abs(cv('EMSIZE', 'SIZEMAX' + axis)),
                   abs(cv('EMSIZE', 'SIZEMIN' + axis)))

    return {
        'particle_texture': '' if tex == 'NULL' else tex,
        'particle_src_blend': _int('SRCBLENDID', 4),
        'particle_dst_blend': _int('DSTBLENDID', 5),
        'particle_color_start': rgba(0.0), 'particle_color_end': rgba(1.0),
        'particle_color_mid_enabled': mid, 'particle_color_mid': rgba(mid_t),
        'particle_color_mid_time': mid_t,
        'particle_size_start': max(cv('SIZE', 'SIZEX', 0.3, 0.0), 0.0),
        'particle_size_end': max(cv('SIZE', 'SIZEX', 0.5, 1.0), 0.0),
        'particle_life': max(cv('EMLIFE', 'LIFE', 1.0), 0.0),
        'particle_life_bias': max(cv('EMLIFE', 'BIAS'), 0.0),
        'particle_rate': max(cv('EMRATE', 'RATE', 10.0), 0.0),
        'particle_speed': max(cv('EMSPEED', 'SPEED', 1.0), 0.0),
        'particle_speed_bias': max(cv('EMSPEED', 'BIAS'), 0.0),
        'particle_direction': (cv('EMDIR', 'DIRX'), cv('EMDIR', 'DIRY'),
                               cv('EMDIR', 'DIRZ', 1.0)),
        'particle_angle_min': cv('EMANGLE', 'MIN'),
        'particle_angle_max': cv('EMANGLE', 'MAX'),
        'particle_volume': (half('X'), half('Y'), half('Z')),
        'particle_offset': (cv('EMPOS', 'X'), cv('EMPOS', 'Y'), cv('EMPOS', 'Z')),
        'particle_rotation_min': cv('EMROTATION', 'ANGLEMIN'),
        'particle_rotation_max': cv('EMROTATION', 'ANGLEMAX'),
        'particle_force': (cv('FORCE', 'FORCEX'), cv('FORCE', 'FORCEY'),
                           cv('FORCE', 'FORCEZ')),
        'particle_friction': cv('FRICTION', 'FRICTION'),
        'particle_wind': cv('WIND', 'WINDFACTOR'),
        'particle_noise': cv('NOISE', 'NOISE'),
        'particle_jitter': cv('JITTER', 'JITTERFACTOR'),
        'particle_rotspeed_min': cv('ROTSPEED', 'MINCW'),
        'particle_rotspeed_max': cv('ROTSPEED', 'MAXCW'),
        'particle_ground_bounce': cv('GROUNDCOLLIDE', 'BOUNCE'),
        'particle_ground_speedmult': cv('GROUNDCOLLIDE', 'SPEEDMULT', 1.0),
    }


def curves(game_root, name, index=0):
    """Кривые эмиттера «INFO.FIELD» (как _particle_curve_items INU)."""
    s = _system(game_root, name)
    if s is None or not s.emitters:
        return []
    em = s.emitters[max(0, min(index, len(s.emitters) - 1))]
    return ["%s.%s" % (info.type, fld) for info in em.infos
            for fld in info.curves.keys()]


def curve_keys(game_root, name, index, curve):
    """[(time, value)] ключей кривой «INFO.FIELD»."""
    s = _system(game_root, name)
    if s is None or not s.emitters or '.' not in curve:
        return []
    em = s.emitters[max(0, min(index, len(s.emitters) - 1))]
    info_type, fld = curve.split('.', 1)
    info = em.info(info_type)
    c = info.curves.get(fld) if info else None
    return [(float(k.time), float(k.val)) for k in c.keys] if c else []


# ── текстуры эффектов (.txd) ─────────────────────────────────────────

def fx_txd(explicit, game_root):
    """(путь к .txd, путь внутри IMG | None, подпись) — откуда берутся
    текстуры эффектов (resolve_fx_txd_display INU): явный .txd →
    <игра>/models/particle.txd… → gta3.img/particle.txd. Подпись '' —
    источника нет («Not selected»)."""
    if explicit and os.path.isfile(explicit):
        return explicit, None, _short(explicit)
    if game_root and os.path.isdir(game_root):
        models = os.path.join(game_root, 'models')
        for name in _FX_TXD_CANDIDATES:
            cand = os.path.join(models, name)
            if os.path.isfile(cand):
                return cand, None, _short(cand)
        img = os.path.join(models, 'gta3.img')
        if os.path.isfile(img):
            return img, 'particle.txd', "gta3.img/particle.txd"
    return None, None, ''


def _short(p):
    parent = os.path.basename(os.path.dirname(p))
    return (parent + "/" + os.path.basename(p)) if parent else os.path.basename(p)


def sprite_names(explicit, game_root):
    """Имена спрайтов для поля Texture частицы: движок берёт их из
    <имя fxp>PC.txd (effectsPC.txd рядом с effects.fxp); нет его —
    источник текстур эффектов."""
    pc = os.path.join(game_root or '', 'models', 'effectsPC.txd')
    if game_root and os.path.isfile(pc):
        from inu_gta_core.txd import read_txd_texture_names
        return sorted(read_txd_texture_names(pc), key=str.lower)
    return texture_names(explicit, game_root)


def texture_names(explicit, game_root):
    """Имена текстур источника эффектов (.txd или particle.txd из IMG)."""
    path, inner, _label = fx_txd(explicit, game_root)
    if path is None:
        return []
    from inu_gta_core.txd import read_txd_texture_names
    if inner is None:
        return sorted(read_txd_texture_names(path), key=str.lower)
    from inu_gta_core.img import ImgReader
    import tempfile
    with ImgReader(path) as img:
        data = img.read(inner)
    if not data:
        return []
    fd, tmp = tempfile.mkstemp(suffix='.txd')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        return sorted(read_txd_texture_names(tmp), key=str.lower)
    finally:
        os.remove(tmp)
