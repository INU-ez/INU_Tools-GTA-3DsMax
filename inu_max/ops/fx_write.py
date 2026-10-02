"""Transactional editing of effects.fxp, preserving unrelated emitters."""
import copy
import math
import os
import re
import shutil
import tempfile

from inu_gta_core import fxp
from .fx import fxp_path, _sample

_INFO_ZONES = {
    # Zone 1 — Emission / birth
    'EMLIFE': 1, 'EMRATE': 1, 'EMSPEED': 1, 'EMANGLE': 1, 'EMDIR': 1,
    'EMSIZE': 1, 'EMROTATION': 1, 'EMPOS': 1, 'EMWEATHER': 1,
    # Zone 2 — Physics / movement
    'FORCE': 2, 'FRICTION': 2, 'WIND': 2, 'ROTSPEED': 2, 'NOISE': 2,
    'JITTER': 2, 'GROUNDCOLLIDE': 2, 'ATTRACTPT': 2, 'FLOAT': 2,
    'UNDERWATER': 2,
    # Zone 3 — Rendering / visuals
    'SIZE': 3, 'COLOUR': 3, 'COLOURBRIGHT': 3, 'SPRITERECT': 3, 'DIR': 3,
    'ANIMTEX': 3, 'TRAIL': 3, 'FLAT': 3, 'HEATHAZE': 3, 'SELFLIT': 3,
}

_INFO_TEMPLATES = {
    'COLOUR': (
        [('TIMEMODEPRT', '1')],
        {'RED': 255.0, 'GREEN': 255.0, 'BLUE': 255.0, 'ALPHA': 255.0},
    ),
    'COLOURBRIGHT': (
        [('TIMEMODEPRT', '1')],
        {'RED': 255.0, 'GREEN': 255.0, 'BLUE': 255.0, 'ALPHA': 255.0, 'BIAS': 0.0},
    ),
    'SIZE': (
        [('TIMEMODEPRT', '1')],
        {'SIZEX': 1.0, 'SIZEY': 1.0, 'SIZEXBIAS': 0.0, 'SIZEYBIAS': 0.0},
    ),
    'EMLIFE':     ([], {'LIFE': 1.0, 'BIAS': 0.0}),
    'EMRATE':     ([], {'RATE': 10.0}),
    'EMSPEED':    ([], {'SPEED': 1.0, 'BIAS': 0.0}),
    'EMDIR':      ([], {'DIRX': 0.0, 'DIRY': 0.0, 'DIRZ': 1.0}),
    'EMANGLE':    ([], {'MIN': 0.0, 'MAX': 0.0}),
    'EMSIZE': (
        # Zone 1 blocks never carry TIMEMODEPRT in original GTA SA data;
        # adding one here desynchronises the native field-order parser.
        [],
        # Interleaved axis order — GTA SA's native parser reads these
        # sequentially by position, not by name. Wrong order => particles
        # emit along a degenerate line/point instead of the intended volume.
        {
            'RADIUS': 0.0,
            'SIZEMINX': 0.0, 'SIZEMAXX': 0.0,
            'SIZEMINY': 0.0, 'SIZEMAXY': 0.0,
            'SIZEMINZ': 0.0, 'SIZEMAXZ': 0.0,
        },
    ),
    'EMPOS':      ([], {'X': 0.0, 'Y': 0.0, 'Z': 0.0}),
    'EMROTATION': ([], {'ANGLEMIN': 0.0, 'ANGLEMAX': 0.0}),
    'FORCE': (
        [('TIMEMODEPRT', '1')],
        {'FORCEX': 0.0, 'FORCEY': 0.0, 'FORCEZ': 0.0},
    ),
    'FRICTION':   ([('TIMEMODEPRT', '1')], {'FRICTION': 0.0}),
    'WIND':       ([('TIMEMODEPRT', '1')], {'WINDFACTOR': 0.0}),
    'NOISE':      ([('TIMEMODEPRT', '1')], {'NOISE': 0.0}),
    'JITTER':     ([('TIMEMODEPRT', '1')], {'JITTERFACTOR': 0.0}),
    'ROTSPEED': (
        [('TIMEMODEPRT', '1')],
        {'MINCW': 0.0, 'MAXCW': 0.0, 'MINCCW': 0.0, 'MAXCCW': 0.0},
    ),
    'GROUNDCOLLIDE': (
        [('TIMEMODEPRT', '1')],
        {'BOUNCE': 0.0, 'SPEEDMULT': 1.0, 'BOUNCEERROR': 0.0},
    ),
}


def _pairs_set(pairs, key, value):
    for i, (k, _) in enumerate(pairs):
        if k == key:
            pairs[i] = (key, str(value))
            return
    pairs.append((key, str(value)))


def _curve(emitter, kind, field, keys):
    info = emitter.info(kind)
    if info is None:
        scalars, fields = _INFO_TEMPLATES[kind]
        info = fxp.FXInfoBlock(type=kind, scalars=list(scalars),
            curves={f: fxp.FXCurve(keys=[fxp.FXKeyframe(0, v)]) for f, v in fields.items()})
        emitter.infos.append(info)
    old = info.curves.get(field)
    info.curves[field] = fxp.FXCurve(old.looped if old else 0,
        [fxp.FXKeyframe(float(t), float(v)) for t, v in keys])
    # The engine shares the first curve's time array across the entire block.
    times = sorted({k.time for c in info.curves.values() for k in c.keys})
    if len(times) > 127 or any(not math.isfinite(t) or abs(t) >= 128 for t in times):
        raise ValueError('An FX info block needs at most 127 keys with |time| < 128')
    for c in info.curves.values():
        values = [c.sample(t) for t in times]
        if any(not math.isfinite(v) for v in values):
            raise ValueError('Curve values must be finite')
        c.keys = [fxp.FXKeyframe(t, v) for t, v in zip(times, values)]


def blank_system(name):
    system = fxp.FXSystem(header=[('FILENAME', 'effects/particles/%s.fxs' % name),
        ('NAME', name), ('LENGTH', '1.000'), ('LOOPINTERVALMIN', '0.000'),
        ('LOOPINTERVALMAX', '0.000'), ('PLAYMODE', '2'), ('CULLDIST', '50.000'),
        ('BOUNDINGSPHERE', '0.0 0.0 0.0 0.0')],
        footer=[('OMITTEXTURES', '0'), ('TXDNAME', 'NOTXDSET')])
    em = fxp.FXEmitter(base=[('NAME', 'ParticleEmitter'),
        ('MATRIX', '1 0 0 0 1 0 0 0 1 0 0 0'), ('TEXTURE', 'sphere'),
        ('TEXTURE2', 'NULL'), ('TEXTURE3', 'NULL'), ('TEXTURE4', 'NULL'),
        ('ALPHAON', '1'), ('SRCBLENDID', '4'), ('DSTBLENDID', '5')],
        footer=[('LODSTART', '30.000'), ('LODEND', '50.000')])
    for kind, fields in {
        'EMLIFE': {'LIFE': 1, 'BIAS': 0}, 'EMRATE': {'RATE': 10},
        'EMSPEED': {'SPEED': 1, 'BIAS': 0},
        'EMDIR': {'DIRX': 0, 'DIRY': 0, 'DIRZ': 1}}.items():
        for field, value in fields.items():
            _curve(em, kind, field, [(0, value)])
    for field in ('SIZEX', 'SIZEY', 'SIZEXBIAS', 'SIZEYBIAS'):
        _curve(em, 'SIZE', field, [(0, .3 if 'BIAS' not in field else 0),
                                  (1, .5 if 'BIAS' not in field else 0)])
    for field in ('RED', 'GREEN', 'BLUE', 'ALPHA'):
        _curve(em, 'COLOUR', field, [(0, 255), (1, 0 if field == 'ALPHA' else 255)])
    for kind in ('SIZE', 'COLOUR'):
        em.info(kind).scalars.append(('TIMEMODEPRT', '1'))
    system.emitters.append(em)
    return system


def _name(name):
    name = str(name).strip()
    if not re.fullmatch(r'[A-Za-z0-9_\-]+', name):
        raise ValueError('Effect name must contain ASCII letters, digits, _ or -')
    return name


def _edit(root, mutate):
    path = fxp_path(root)
    project = fxp.read_fxp(path)  # Fresh file: never overwrite an external edit from cache.
    mutate(project)
    fd, tmp = tempfile.mkstemp(prefix='.inu_fx_', suffix='.fxp', dir=os.path.dirname(path))
    os.close(fd)
    try:
        fxp.write_fxp(tmp, project)
        reread = fxp.read_fxp(tmp)
        canonical = lambda p: [line.rstrip() for line in fxp.format_fxp(p).splitlines()]
        if canonical(reread) != canonical(project):
            raise ValueError('FXP verification failed; original file retained')
        if not os.path.exists(path + '.bak'):
            shutil.copy2(path, path + '.bak')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    fxp.clear_cache()
    return 'INFO', 'Saved effects.fxp (original backup: effects.fxp.bak)'


def create(root, name):
    name = _name(name)
    def mutate(project):
        if project.find(name):
            raise ValueError('Effect already exists: ' + name)
        project.systems.append(blank_system(name))
    return _edit(root, mutate)


def delete(root, name):
    def mutate(project):
        system = project.find(name)
        if system is None:
            raise ValueError('Effect not found: ' + name)
        project.systems.remove(system)
    return _edit(root, mutate)


def write_curve(root, name, index, curve, keys):
    if not keys or len({float(t) for t, _ in keys}) != len(keys):
        raise ValueError('Curve must have keys at distinct times')
    kind, field = curve.split('.', 1)
    def mutate(project):
        system = project.find(name)
        if system is None or not 0 <= index < len(system.emitters):
            raise ValueError('Emitter not found')
        emitter = system.emitters[index]
        if emitter.info(kind) is None or field not in emitter.info(kind).curves:
            raise ValueError('Curve not found: ' + curve)
        _curve(emitter, kind, field, sorted(keys))
    return _edit(root, mutate)


def save(root, current, name, index, values, overwrite=True):
    name = _name(name)
    def mutate(project):
        source = project.find(current)
        if source is None or not 0 <= index < len(source.emitters):
            raise ValueError('Source emitter not found')
        target = project.find(name)
        if target is not None and not overwrite:
            raise ValueError('Effect already exists: ' + name)
        system = copy.deepcopy(source)
        _pairs_set(system.header, 'NAME', name)
        _pairs_set(system.header, 'FILENAME', 'effects/particles/%s.fxs' % name)
        for prop, head in (('length', 'LENGTH'), ('playmode', 'PLAYMODE'), ('culldist', 'CULLDIST')):
            _pairs_set(system.header, head, values['particle_sys_' + prop])
        em = system.emitters[index]
        original = _sample(em)
        for prop, head in (('texture', 'TEXTURE'), ('src_blend', 'SRCBLENDID'), ('dst_blend', 'DSTBLENDID')):
            _pairs_set(em.base, head, values['particle_' + prop] or 'NULL')
        scalar_map = {
            'life': ('EMLIFE', 'LIFE'), 'life_bias': ('EMLIFE', 'BIAS'),
            'rate': ('EMRATE', 'RATE'), 'speed': ('EMSPEED', 'SPEED'),
            'speed_bias': ('EMSPEED', 'BIAS'), 'angle_min': ('EMANGLE', 'MIN'),
            'angle_max': ('EMANGLE', 'MAX'), 'rotation_min': ('EMROTATION', 'ANGLEMIN'),
            'rotation_max': ('EMROTATION', 'ANGLEMAX'), 'friction': ('FRICTION', 'FRICTION'),
            'wind': ('WIND', 'WINDFACTOR'), 'noise': ('NOISE', 'NOISE'),
            'jitter': ('JITTER', 'JITTERFACTOR'), 'rotspeed_min': ('ROTSPEED', 'MINCW'),
            'rotspeed_max': ('ROTSPEED', 'MAXCW'), 'ground_bounce': ('GROUNDCOLLIDE', 'BOUNCE'),
            'ground_speedmult': ('GROUNDCOLLIDE', 'SPEEDMULT')}
        for prop, (kind, field) in scalar_map.items():
            if 'particle_' + prop in values and values['particle_' + prop] != original.get('particle_' + prop):
                _curve(em, kind, field, [(0, values['particle_' + prop])])
        for prop, kind, fields in (
            ('direction', 'EMDIR', ('DIRX', 'DIRY', 'DIRZ')),
            ('offset', 'EMPOS', ('X', 'Y', 'Z')),
            ('force', 'FORCE', ('FORCEX', 'FORCEY', 'FORCEZ'))):
            if values['particle_' + prop] == original.get('particle_' + prop):
                continue
            for field, value in zip(fields, values['particle_' + prop]):
                _curve(em, kind, field, [(0, value)])
        for axis, value in zip('XYZ', values['particle_volume']):
            if values['particle_volume'] == original.get('particle_volume'):
                continue
            for prefix, sign in (('SIZEMIN', -1), ('SIZEMAX', 1)):
                _curve(em, 'EMSIZE', prefix + axis, [(0, value * sign)])
        for field in ('SIZEX', 'SIZEY'):
            if any(values['particle_size_' + p] != original.get('particle_size_' + p) for p in ('start', 'end')):
                _curve(em, 'SIZE', field, [(0, values['particle_size_start']), (1, values['particle_size_end'])])
        colors = [(0, values['particle_color_start']), (1, values['particle_color_end'])]
        if values['particle_color_mid_enabled']:
            colors.insert(1, (values['particle_color_mid_time'], values['particle_color_mid']))
        for j, field in enumerate(('RED', 'GREEN', 'BLUE', 'ALPHA')):
            if any(values[k] != original.get(k) for k in values if k.startswith('particle_color_')):
                _curve(em, 'COLOUR', field, [(t, rgba[j] * 255) for t, rgba in colors])
        em.infos.sort(key=lambda info: _INFO_ZONES.get(info.type, 3))
        if target is None:
            project.systems.append(system)
        else:
            project.systems[project.systems.index(target)] = system
    return _edit(root, mutate)
