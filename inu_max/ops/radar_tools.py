"""Top-down native Max renders and per-tile GTA TXD packing."""
import math
import os
import re

from inu_gta_core.game_versions import radar_layout, radar_tile_center, rw_version_for_game
from inu_gta_core.dff import make_library_id
from ..adapter import selection as S
from .. import settings


def radar_plan(mode, game, override=0, specific=''):
    grid, half = radar_layout(game, override)
    if mode in ('FULL', 'FULL_MENU'):
        return [(('FullRadar' if mode == 'FULL' else 'FullMenuRadar'), 0, 0, half * 2)]
    if mode == 'MENU':
        grid = 3
        names = ['Map%s%02d' % (row, col) for row in ('Top', 'Mid', 'Bot') for col in range(1, 4)]
        indices = range(9)
    else:
        names = ['radar%02d' % i for i in range(grid * grid)]
        indices = sorted(set(int(v.strip()) for v in specific.split(',') if v.strip())) if mode == 'SPECIFIC' else range(grid * grid)
        if any(i < 0 or i >= grid * grid for i in indices):
            raise ValueError('Radar indices must be between 0 and %d' % (grid * grid - 1))
    return [(names[i], *radar_tile_center(i, grid, half), half * 2 / grid) for i in indices]


def radar_generate(mode='ALL'):
    rt = S._rt()
    folder = settings.get('radar_output', '')
    if not folder:
        raise ValueError('Choose the radar output folder')
    os.makedirs(folder, exist_ok=True)
    plan = radar_plan(mode, settings.get('game', 'SA'), int(settings.get('radar_grid', 0)), settings.get('radar_specific', ''))
    height, size = float(settings.get('radar_height', 3000)), int(settings.get('radar_size', 256))
    camera = target = None
    old = {k: getattr(rt, k) for k in ('renderWidth', 'renderHeight', 'rendSaveFile', 'rendOutputFilename')}
    try:
        target = rt.TargetObject(name=rt.uniqueName('INU_RadarTarget'))
        camera = rt.Targetcamera(name=rt.uniqueName('INU_RadarCamera'), target=target)
        S.put_field([target], 'preview', True)
        S.put_field([target], 'type', 'NON')
        camera.orthoProjection = True
        camera.clipManually = True
        camera.nearclip, camera.farclip = 1, height + 5000
        S.put_field([camera], 'preview', True)
        S.put_field([camera], 'type', 'NON')
        rt.renderWidth, rt.renderHeight = size, size
        for name, x, y, width in plan:
            target.pos = rt.Point3(x, y, 0)
            camera.transform = rt.Matrix3(rt.Point3(1, 0, 0), rt.Point3(0, 1, 0), rt.Point3(0, 0, 1), rt.Point3(x, y, height))
            camera.fov = math.degrees(2 * math.atan(width / (2 * height)))
            bitmap = rt.render(camera=camera, outputfile=os.path.join(folder, name + '.png'), vfb=False)
            if bitmap is None:
                raise ValueError('Render was cancelled: ' + name)
            rt.close(bitmap)
    finally:
        for key, value in old.items():
            setattr(rt, key, value)
        if camera is not None:
            rt.delete(camera)
        if target is not None:
            rt.delete(target)
    return 'INFO', 'Rendered %d radar images to %s' % (len(plan), folder)


def radar_pack_txd():
    from . import txd_build as B
    folder = settings.get('radar_output', '')
    files = [f for f in os.listdir(folder) if re.fullmatch(r'(radar\d+|Map(?:Top|Mid|Bot)\d+)\.png', f, re.I)]
    game = settings.get('game', 'SA')
    lib = make_library_id(rw_version_for_game(game))
    platform = B.PLATFORM_D3D9 if game == 'SA' else B.PLATFORM_D3D8
    for filename in sorted(files):
        name = os.path.splitext(filename)[0]
        pixels = B.load_rgba(os.path.join(folder, filename))
        section = B.texture_native(name, pixels, False, platform, lib)
        data = B.assemble([(name, section)], lib)
        path = os.path.join(folder, name + '.txd')
        tmp = path + '.inu_tmp'
        try:
            with open(tmp, 'wb') as stream:
                stream.write(data)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return ('INFO' if files else 'WARNING'), 'Packed %d radar TXDs' % len(files)


OPERATIONS = {'radar_generate': radar_generate, 'radar_pack_txd': radar_pack_txd}
