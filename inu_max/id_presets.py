# INU Tools (Max) — пресеты Model ID (как data/id_manager в Blender-версии).
#
# Формат файла тот же, что у INU (один ID в строке):
#   свободный ID — просто число, занятый — с суффиксом «-имя_модели»:
#     3500
#     3501-tatar_str_2817_1
#   строки с «#» — комментарии.
# Пресеты: %LOCALAPPDATA%\INU_Tools_Max\id_presets\<имя>.txt; «default»
# есть всегда.

import os
import re
import tempfile

DEFAULT = 'default'


def presets_dir():
    d = os.path.join(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir(),
                     'INU_Tools_Max', 'id_presets')
    os.makedirs(d, exist_ok=True)
    return d


def _sanitize(name):
    name = re.sub(r'[^\w.\- ]+', '_', (name or '').strip())
    return name or DEFAULT


def preset_path(name):
    return os.path.join(presets_dir(), _sanitize(name) + '.txt')


def list_presets():
    """Имена пресетов (без .txt), «default» — первым."""
    try:
        names = [os.path.splitext(f)[0] for f in os.listdir(presets_dir())
                 if f.lower().endswith('.txt') and not f.startswith('_')]
    except Exception:                                  # noqa: BLE001
        names = []
    names.sort(key=lambda s: s.lower())
    if DEFAULT in names:
        names.remove(DEFAULT)
    return [DEFAULT] + names


def read(name):
    """(свободные ID в порядке файла, {занятый ID: имя модели})."""
    free, used = [], {}
    try:
        with open(preset_path(name), 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                num, sep, model = line.partition('-')
                try:
                    i = int(num)
                except ValueError:
                    continue
                if sep and model:
                    used[i] = model
                else:
                    free.append(i)
    except FileNotFoundError:
        pass
    except Exception as e:                             # noqa: BLE001
        print("[INU] ID preset %s: %r" % (name, e))
    return free, used


def create(name, copy_from=None):
    """Новый пресет (пустой или копия другого). False — уже есть."""
    dst = preset_path(name)
    if os.path.isfile(dst):
        return False
    src = preset_path(copy_from) if copy_from else None
    if src and os.path.isfile(src):
        with open(src, 'r', encoding='utf-8') as f:
            data = f.read()
    else:
        data = '# GTA SA model ID preset: %s\n' % _sanitize(name)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(data)
    return True


def delete(name):
    """Удалить пресет; «default» удалить нельзя."""
    if _sanitize(name) == DEFAULT:
        return False
    try:
        os.remove(preset_path(name))
        return True
    except Exception:                                  # noqa: BLE001
        return False


def rename(old, new):
    src, dst = preset_path(old), preset_path(new)
    if _sanitize(old) == DEFAULT or os.path.exists(dst) or not os.path.isfile(src):
        return False
    os.rename(src, dst)
    return True
