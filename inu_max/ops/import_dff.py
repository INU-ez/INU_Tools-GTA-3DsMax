# INU Tools (Max) — импорт DFF (Фаза 1 MVP).
#
# Читает .dff общим ядром (inu_gta_core) и строит меши в 3ds Max через
# адаптер. Пока: геометрия + трансформ фрейма. Модель связывается с фреймом
# через atomic (geometry_index → frame_index).

import pymxs


def import_dff(filepath, auto_txd=True, extra_tex=None):
    """Импортировать .dff в текущую сцену Max. Возвращает (n_objs, msg).

    auto_txd — искать нужный .txd в папке модели (coverage-подбор);
    extra_tex — {имя_текстуры.lower(): png} из .txd, выбранных вместе с DFF
    в общем импорте (имеют приоритет над найденными автоматически)."""
    rt = pymxs.runtime
    from inu_gta_core.dff import read_dff
    from ..adapter.mesh import build_object_from_geometry

    # read_dff принимает БАЙТЫ содержимого (не путь) — открываем файл сами.
    with open(filepath, 'rb') as _f:
        clump = read_dff(_f.read())
    geoms = clump.geometries or []
    frames = clump.frames or []
    atomics = clump.atomics or []

    # Текстуры: извлекаем ВСЕ .txd из папки модели в <имя>_textures/ и
    # собираем карту {имя: png}. Модель может ссылаться на shared-текстуры из
    # нескольких .txd (имя своего TXD часто НЕ совпадает с именем .dff —
    # напр. rodeo06_LAw2 → TXD rodeo05_law2). Положи нужные .txd рядом.
    tex_map = {}
    if auto_txd:
        try:
            from ..adapter.texture import build_tex_map
            needed = set()
            for _g in geoms:
                for _m in (getattr(_g, 'materials', None) or []):
                    _tx = getattr(_m, 'texture', None)
                    _nm = getattr(_tx, 'name', '') if _tx is not None else ''
                    if _nm:
                        needed.add(_nm.lower())
            tex_map = build_tex_map(filepath, needed)
        except Exception as e:                         # noqa: BLE001
            print("[INU import_dff] извлечение TXD пропущено: %r" % (e,))
    if extra_tex:
        tex_map = dict(tex_map)
        tex_map.update(extra_tex)

    # geometry_index → frame (через атомики). Если атомиков нет — строим
    # геометрии как есть, без трансформа.
    geom_to_frame = {}
    for a in atomics:
        gi = getattr(a, 'geometry_index', -1)
        fi = getattr(a, 'frame_index', -1)
        if 0 <= gi < len(geoms) and 0 <= fi < len(frames):
            geom_to_frame[gi] = frames[fi]

    built = 0
    for gi, geom in enumerate(geoms):
        if geom is None or not getattr(geom, 'vertices', None):
            continue
        frame = geom_to_frame.get(gi)
        name = None
        if frame is not None and getattr(frame, 'name', ''):
            name = frame.name
        if not name:
            import os
            name = "%s_%d" % (os.path.splitext(os.path.basename(filepath))[0], gi)
        try:
            build_object_from_geometry(geom, frame, name, tex_map)
            built += 1
        except Exception as e:                         # noqa: BLE001
            print("[INU import_dff] geom %d '%s' failed: %r" % (gi, name, e))

    try:
        rt.redrawViews()
    except Exception:                                  # noqa: BLE001
        pass
    return built, "Импортировано мешей: %d (из %d геометрий)" % (built, len(geoms))


def import_dff_interactive():
    """Открыть файловый диалог и импортировать выбранный .dff."""
    rt = pymxs.runtime
    path = rt.getOpenFileName(
        caption="INU: Импорт DFF",
        types="GTA DFF (*.dff)|*.dff|All Files (*.*)|*.*|")
    if not path:
        return 0, "Отменено"
    n, msg = import_dff(path)
    try:
        rt.messageBox(msg, title="INU Tools — Импорт DFF")
    except Exception:                                  # noqa: BLE001
        pass
    return n, msg
