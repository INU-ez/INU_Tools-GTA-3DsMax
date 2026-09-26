# INU Tools (Max) — общий импорт (как «Импорт» в панели Экспорт/Импорт INU).
#
# Чистый диспетчер: импортирует РОВНО выбранные файлы, каждый по своему типу,
# в порядке TXD → DFF → COL → CST → IDE → IPL. Текстуры из выбранных .txd
# уходят в DFF этого же импорта. Пока реализованы DFF и TXD, остальные типы
# перечисляются в отчёте как ещё не поддержанные.

import os

_ORDER = ('.txd', '.dff', '.col', '.cst', '.ide', '.ipl')


def import_files(paths, auto_txd=True):
    """Импортировать файлы по расширению. Возвращает текст отчёта."""
    from .import_dff import import_dff
    from .import_txd import import_txd

    by_ext = {e: [] for e in _ORDER}
    other = []
    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        (by_ext[ext] if ext in by_ext else other).append(p)

    lines = []
    extra_tex = {}
    for p in by_ext['.txd']:
        try:
            m, _out = import_txd(p)
            extra_tex.update(m)
            lines.append("TXD %s: %d textures" % (os.path.basename(p), len(m)))
        except Exception as e:                         # noqa: BLE001
            lines.append("TXD %s: error %s" % (os.path.basename(p), e))

    for p in by_ext['.dff']:
        try:
            n, _msg = import_dff(p, auto_txd=auto_txd, extra_tex=extra_tex)
            lines.append("DFF %s: %d meshes" % (os.path.basename(p), n))
        except Exception as e:                         # noqa: BLE001
            lines.append("DFF %s: error %s" % (os.path.basename(p), e))

    todo = [os.path.basename(p) for e in _ORDER[2:] for p in by_ext[e]]
    if todo:
        lines.append("Not supported yet: " + ", ".join(todo))
    if other:
        lines.append("Unknown type: " + ", ".join(os.path.basename(p) for p in other))
    return "\n".join(lines) or "Nothing imported."
