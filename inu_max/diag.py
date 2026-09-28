# INU Tools (Max) — диагностика зависаний.
#
# faulthandler пишет стеки Python всех потоков в файл из СВОЕГО C-потока —
# работает, даже когда Max висит. Если в момент зависания главный поток
# стоит в нашем коде — в файле будет точная строка; если Python-кадров нет —
# висит сам Max (не наш код).

import faulthandler
import os
import time

_FILE = None
_T0 = [0.0]
_GEN = [0]                  # номер записи: старые таймеры не глушат новую


def path():
    return os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                        'INU_Tools_Max', 'freeze_trace.txt')


def start(label, every=2.0):
    """Начать запись стеков каждые `every` секунд."""
    global _FILE
    stop()
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    _FILE = open(path(), 'w', encoding='utf-8')
    _FILE.write("INU freeze trace: %s  %s\n" % (label, time.strftime('%H:%M:%S')))
    _FILE.flush()
    _T0[0] = time.perf_counter()
    _GEN[0] += 1
    faulthandler.dump_traceback_later(every, repeat=True, file=_FILE)
    return _GEN[0]


def generation():
    return _GEN[0]


def mark(text):
    """Отметка времени — в Listener и в файл трассы."""
    line = "[INU diag] +%.2fs %s" % (time.perf_counter() - _T0[0], text)
    print(line)
    if _FILE is not None:
        try:
            _FILE.write(line + "\n")
            _FILE.flush()
        except Exception:                              # noqa: BLE001
            pass


def stop(gen=None):
    """Остановить запись (gen — только если это всё ещё та же запись)."""
    global _FILE
    if gen is not None and gen != _GEN[0]:
        return
    faulthandler.cancel_dump_traceback_later()
    if _FILE is not None:
        try:
            _FILE.close()
        except Exception:                              # noqa: BLE001
            pass
        _FILE = None
