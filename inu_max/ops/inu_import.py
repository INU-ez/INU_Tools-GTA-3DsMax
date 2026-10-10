# INU Tools (Max) — общий импорт (как «Импорт» в панели Экспорт/Импорт INU).
#
# Чистый диспетчер: импортирует РОВНО выбранные файлы, каждый по своему типу,
# в порядке TXD → DFF → COL → CST → IDE → IPL. Текстуры из выбранных .txd
# уходят в DFF этого же импорта. Реализованы TXD, DFF, COL и CST; IDE и IPL

import os

_ORDER = ('.txd', '.dff', '.col', '.cst', '.ide', '.ipl')


def _logged_files(kind, paths, progress=None, state=None):
    from ..diag import mark
    if state is None:
        state = {'done': 0, 'total': len(paths), 'cancelled': False}
    for index, path in enumerate(paths, 1):
        if state['cancelled']:
            return
        if progress and progress(state['done'], state['total'], path) is False:
            state['cancelled'] = True
            return
        mark('%s %d/%d: %s' % (kind, index, len(paths), os.path.basename(path)))
        yield path
        state['done'] += 1
        if progress and progress(state['done'], state['total'], path) is False:
            state['cancelled'] = state['done'] < state['total']
            return


def import_files(paths, auto_txd=True, progress=None):
    """Импортировать файлы по расширению. Возвращает текст отчёта."""
    from .import_dff import import_dff
    from .import_txd import import_txd

    by_ext = {e: [] for e in _ORDER}
    other = []
    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        (by_ext[ext] if ext in by_ext else other).append(p)

    lines = []
    state = {'done': 0, 'total': sum(map(len, by_ext.values())), 'cancelled': False}
    extra_tex = {}
    for p in _logged_files('TXD', by_ext['.txd'], progress, state):
        try:
            m, _out = import_txd(p)
            extra_tex.update(m)
            lines.append("TXD %s: %d textures" % (os.path.basename(p), len(m)))
        except Exception as e:                         # noqa: BLE001
            lines.append("TXD %s: error %s" % (os.path.basename(p), e))

    for p in _logged_files('DFF', by_ext['.dff'], progress, state):
        try:
            n, _msg = import_dff(p, auto_txd=auto_txd, extra_tex=extra_tex)
            lines.append("DFF %s: %d meshes" % (os.path.basename(p), n))
        except Exception as e:                         # noqa: BLE001
            lines.append("DFF %s: error %s" % (os.path.basename(p), e))

    # коллизия: .col (одна модель или библиотека) и .cst — после DFF, чтобы
    # встать на место одноимённых моделей
    from .import_col import import_col, import_cst, report_line
    for ext, fn, kind in (('.col', import_col, 'COL'), ('.cst', import_cst, 'CST')):
        for p in _logged_files(kind, by_ext[ext], progress, state):
            try:
                lines.append(report_line(kind, p, fn(p)))
            except Exception as e:                     # noqa: BLE001
                import traceback
                traceback.print_exc()
                lines.append("%s %s: error %s" % (kind, os.path.basename(p), e))

    from .ipl_tools import import_ide, import_ipl
    for ext, fn in (('.ide', import_ide), ('.ipl', import_ipl)):
        for path in _logged_files(ext[1:].upper(), by_ext[ext], progress, state):
            try:
                level, text = fn(path)
                lines.append('%s %s: %s' % (ext[1:].upper(), os.path.basename(path), text))
            except Exception as error:
                lines.append('%s %s: error %s' % (ext[1:].upper(), os.path.basename(path), error))
    if other:
        lines.append("Unknown type: " + ", ".join(os.path.basename(p) for p in other))
    if state['cancelled']:
        lines.append('Import cancelled: %d/%d files processed' % (state['done'], state['total']))
    return "\n".join(lines) or "Nothing imported."
