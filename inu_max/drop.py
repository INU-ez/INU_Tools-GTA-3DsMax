# INU Tools (Max) — импорт одного файла из C++ импортёра (перетаскивание во
# вьюпорт, File → Import, importFile). Max зовёт импортёр на КАЖДЫЙ файл, поэтому
# при сбросе нескольких .dff диалог «Как импортировать DFF?» спрашивается один
# раз на весь пакет (как drop_dff INU в Blender) и открывается у курсора.

import os
import time

_BATCH_SEC = 5.0            # файлы одного сброса идут подряд
_LOG_MAX = 200


def _log(line):
    """Короткий журнал вызовов импортёра (что передал Max) — для проверки."""
    p = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                     'INU_Tools_Max', 'import_log.txt')
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        lines = []
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()[-(_LOG_MAX - 1):]
        lines.append(time.strftime('%Y-%m-%d %H:%M:%S ') + line)
        with open(p, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass


def import_file(path, quiet, state, count=1, key='', from_drop=False):
    """True — импортировано, False — отменено. state — словарь, который
    живёт в inu_boot между вызовами (модули inu_max перезагружаются)."""
    from . import settings
    from .ops.inu_import import import_files
    now = time.time()
    asked = False
    # диалог «Как импортировать DFF?» — только для .dff (у .col / .cst опций нет)
    if not quiet and path.lower().endswith('.dff'):
        same_drop = bool(key) and key == state.get('key') \
            and now - state.get('t', 0.0) < _BATCH_SEC
        if not same_drop:
            from .ui.drop_dialog import ask
            state['ok'] = ask(None, count, at_cursor=from_drop)
            state['key'] = key
            asked = True
        if not state.get('ok', True):
            state['t'] = time.time()
            _log("drop=%s quiet=%s count=%d asked=%s -> cancelled | %s"
                 % (from_drop, quiet, count, asked, path))
            return False
    report = import_files([path], auto_txd=bool(settings.get('auto_txd', True)))
    print("[INU import] %s" % report.replace("\n", " | "))
    state['t'] = time.time()
    _log("drop=%s quiet=%s count=%d asked=%s -> %s | %s"
         % (from_drop, quiet, count, asked, report.replace("\n", " | "), path))
    return True
