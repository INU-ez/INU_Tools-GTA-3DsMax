# INU Tools (Max) — кэши: в памяти на время сеанса и на диске.
#
# В памяти: словарь MEM живёт, пока окна INU открыты (кнопки окон перед
# каждой операцией перезагружают только inu_max.ops / inu_max.adapter —
# см. panel._reload_dev; этот модуль они не трогают).
#
# На диске: JSON в %LOCALAPPDATA%\INU_Tools_Max — индексы, которые долго
# строить (имена текстур и моделей COL внутри больших IMG). Запись ключа —
# [размер, дата изменения, данные]: изменился файл — индекс строится заново.

import json
import os

MEM = {}


def _dir():
    return os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                        'INU_Tools_Max')


def file_key(path):
    """(размер, дата изменения) файла — отпечаток для проверки кэша."""
    try:
        st = os.stat(path)
        return [int(st.st_size), int(st.st_mtime)]
    except OSError:
        return [0, 0]


def _load(name):
    key = ('disk', name)
    if key not in MEM:
        data = {}
        try:
            with open(os.path.join(_dir(), name), 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            pass
        MEM[key] = data
    return MEM[key]


def disk_get(name, path):
    """Данные из кэша-файла name для path, если path не изменился; иначе None."""
    rec = _load(name).get(os.path.normcase(os.path.abspath(path)))
    if rec and rec[:2] == file_key(path):
        return rec[2]
    return None


def disk_put(name, path, data):
    store = _load(name)
    store[os.path.normcase(os.path.abspath(path))] = file_key(path) + [data]
    p = os.path.join(_dir(), name)
    try:
        os.makedirs(_dir(), exist_ok=True)
        with open(p + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(store, f)
        os.replace(p + '.tmp', p)
    except OSError as e:
        print("[INU cache] %s not saved: %r" % (name, e))
