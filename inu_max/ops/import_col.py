# INU Tools (Max) — импорт коллизии .col и .cst (порт ops/col_import.py и
# ops/cst_import.py Blender-версии INU).
#
# Каждая модель файла (в .col их может быть много — библиотека района):
# меш <имя>_COL, тень <имя>_sha, сферы / боксы <имя>_sphere_N / <имя>_box_N,
# материал на поверхность COL_<id>, слой «COL». Границы исходного COL
# сохраняются — экспорт вернёт их как есть. Если в сцене есть модель с тем же
# именем (или <имя>_DFF), коллизия ставится на её место (как INU); сферы и
# боксы едут вместе с мешем.

import os

import pymxs


def _import_models(models, with_prims=True, keep_bounds=True):
    """(моделей, объектов, поставлено на модели сцены, пустых записей).
    Пустые записи (только имя и границы, без геометрии — «пустой COL»)
    в сцене не создаются, как в INU; экспорт «Empty COL» делает их заново."""
    from .dff_read import col_models
    from ..adapter import scene_build
    rt = pymxs.runtime
    if not models:
        raise ValueError("No collision models found in file")
    scene_build._ensure()
    meshes, prims = col_models(models, None, with_prims, keep_bounds)
    created = scene_build.build_collision(meshes, prims)
    mine = {int(rt.getHandleByAnim(o)) for o in created}
    by_model = {}
    for obj, src in zip(created, list(meshes) + list(prims)):
        by_model.setdefault(src.model.lower(), []).append(obj)
    names = {}
    for o in rt.geometry:
        if int(rt.getHandleByAnim(o)) not in mine:
            names.setdefault(str(o.name).lower(), o)
    placed = 0
    for model, objs in by_model.items():
        match = names.get(model) or names.get(model + '_dff')
        if match is None:
            continue
        pos = match.position
        for o in objs:
            o.position = o.position + pos
        placed += 1
    if created:
        rt.select(created)
    empty = sum(1 for m in models
                if not (m.faces or m.shadow_faces or m.spheres or m.boxes))
    return len(models), len(created), placed, empty


def import_col(path):
    from inu_gta_core.col import read_col_file
    return _import_models(read_col_file(path))


def import_cst(path):
    """CST (Collision File Editor II) — те же меши и примитивы; границ в
    файле нет — экспорт посчитает их заново."""
    from inu_gta_core.cst import read_cst
    return _import_models(read_cst(path), keep_bounds=False)


def report_line(kind, path, res):
    n_models, n_obj, placed, empty = res
    return "%s %s: %d model%s, %d object%s%s%s" % (
        kind, os.path.basename(path), n_models, "" if n_models == 1 else "s",
        n_obj, "" if n_obj == 1 else "s",
        (", %d placed on scene models" % placed) if placed else "",
        (", %d empty (no geometry) skipped" % empty) if empty else "")
