# INU Tools (Max) — импорт DFF (порт import_dff_from_clump Blender-версии
# INU).
#
# .dff читает ядро, план сцены строит ops/dff_read.py (иерархия фреймов,
# Dummy/Bone, меши с UV1/UV2, цветами день/ночь/альфа, явными нормалями,
# GTA-свойства материалов, флаги, 2DFX, встроенная коллизия, скин), сцену
# Max — adapter/scene_build.py. Соглашения те же, что читает экспорт, — модель
# после «импорт → экспорт» возвращается той же.

import os

import pymxs

from .. import settings


def import_dff(filepath, auto_txd=True, extra_tex=None):
    """Импортировать .dff в текущую сцену Max. Возвращает (число мешей, текст).

    auto_txd — искать нужный .txd в папке модели (coverage-подбор);
    extra_tex — {имя_текстуры.lower(): png} из .txd, выбранных вместе с DFF
    в общем импорте (имеют приоритет над найденными автоматически)."""
    rt = pymxs.runtime
    from ..diag import mark
    from . import dff_read
    from ..adapter import scene_build

    vanilla = bool(settings.get('import_weld_sharpen', False))
    plan, clump = dff_read.plan_file(filepath, vanilla=vanilla,
                                     with_2dfx=bool(settings.get('import_2dfx', True)))
    mark("plan: %d nodes, %d 2dfx, %d col" % (len(plan.nodes), len(plan.fx),
                                               len(plan.col_meshes) + len(plan.col_prims)))

    # Текстуры: .txd из папки модели, покрывающие текстуры материалов
    # (имя своего TXD часто НЕ совпадает с именем .dff — rodeo06 → rodeo05_law2)
    tex_map = {}
    if auto_txd:
        try:
            from ..adapter.texture import build_tex_map
            needed = {m.texture.name.lower() for g in (clump.geometries or [])
                      for m in (g.materials or []) if m.texture is not None and m.texture.name}
            tex_map = build_tex_map(filepath, needed)
        except Exception as e:                         # noqa: BLE001
            print("[INU import_dff] извлечение TXD пропущено: %r" % (e,))
    mark("textures ready: %d" % len(tex_map))
    if extra_tex:
        tex_map = dict(tex_map)
        tex_map.update(extra_tex)

    created = scene_build.build(plan, tex_map, mark)
    if plan.pipeline:
        settings.set('export_pipeline', plan.pipeline)
    for w in plan.warnings:
        print("[INU import_dff] %s: %s" % (os.path.basename(filepath), w))

    mark("redraw")
    try:
        # синхронная перерисовка: текстуры вьюпорта грузятся здесь же
        rt.completeRedraw()
    except Exception:                                  # noqa: BLE001
        pass
    mark("redraw done")
    n_mesh = sum(1 for n in plan.nodes if n.kind == 'MESH')
    return n_mesh, "Imported: %d meshes, %d frames, %d 2DFX, %d collision objects" % (
        n_mesh, len(plan.nodes) - n_mesh, len(plan.fx),
        len(plan.col_meshes) + len(plan.col_prims))


def import_dff_interactive():
    """Открыть файловый диалог и импортировать выбранный .dff."""
    rt = pymxs.runtime
    path = rt.getOpenFileName(
        caption="INU: Import DFF",
        types="GTA DFF (*.dff)|*.dff|All Files (*.*)|*.*|")
    if not path:
        return 0, "Cancelled"
    n, msg = import_dff(path)
    try:
        rt.messageBox(msg, title="INU Tools — Import DFF")
    except Exception:                                  # noqa: BLE001
        pass
    return n, msg
