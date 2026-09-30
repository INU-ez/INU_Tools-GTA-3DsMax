# INU Tools (Max) — пресеты Model ID (как data/id_manager в Blender-версии).
#
# Формат файла тот же, что у INU (один ID в строке):
#   свободный ID — просто число, занятый — с суффиксом «-имя_модели»:
#     3500
#     3501-tatar_str_2817_1
#   строки с «#» — комментарии (шапка до первого ID сохраняется при записи).
# Пресеты: %LOCALAPPDATA%\INU_Tools_Max\id_presets\<имя>.txt; «default»
# есть всегда.
#
# ID игры (From Game) помечаются в соседнем файле <имя>.game (список ID,
# по одному в строке): Free phantoms / Clear All их не освобождают (в
# Blender освобождались все записи без объекта в сцене — и ID игры
# выдавались заново). Сам .txt остаётся в формате INU.

import os
import re
import tempfile

DEFAULT = 'default'
FIRST_ID, LAST_ID = 321, 19999          # Create ID (как create_id_file INU)


def presets_dir():
    d = os.path.join(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir(),
                     'INU_Tools_Max', 'id_presets')
    os.makedirs(d, exist_ok=True)
    return d


def _sanitize(name):
    name = re.sub(r'[^\w.\- ]+', '_', (name or '').strip())
    return name or DEFAULT


sanitize = _sanitize


def preset_path(name):
    return os.path.join(presets_dir(), _sanitize(name) + '.txt')


def game_path(name):
    return os.path.join(presets_dir(), _sanitize(name) + '.game')


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
    for i, model in load(name):
        if model:
            used[i] = model
        else:
            free.append(i)
    return free, used


def load(name):
    """[(ID, имя или None)] в порядке файла (как _load INU; «3501-» — свободен)."""
    out = []
    try:
        with open(preset_path(name), 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                num, sep, model = line.partition('-')
                try:
                    i = int(num.strip())
                except ValueError:
                    continue
                model = model.strip()
                out.append((i, model if (sep and model) else None))
    except FileNotFoundError:
        pass
    except Exception as e:                             # noqa: BLE001
        print("[INU] ID preset %s: %r" % (name, e))
    return out


def _write_atomic(path, text):
    tmp = path + '.inu_tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    os.replace(tmp, path)


def save(name, entries):
    """Записать пресет (как _save INU: шапка до первого ID сохраняется,
    записи — по возрастанию ID). Запись через временный файл."""
    path = preset_path(name)
    head = []
    if os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                if s[0].isdigit():
                    break
                head.append(line.rstrip('\n'))
    else:
        head.append('# GTA SA model ID preset: %s' % _sanitize(name))
    lines = head + ["%d-%s" % (i, n) if n else str(i)
                    for i, n in sorted(entries, key=lambda e: e[0])]
    _write_atomic(path, "\n".join(lines) + "\n")


def game_ids(name):
    """ID, помеченные как занятые игрой (From Game)."""
    out = set()
    try:
        with open(game_path(name), 'r', encoding='utf-8') as f:
            for line in f:
                s = line.strip()
                if s.isdigit():
                    out.add(int(s))
    except FileNotFoundError:
        pass
    return out


def save_game_ids(name, ids):
    _write_atomic(game_path(name), "# INU: IDs used by the game (From Game)\n"
                  + "".join("%d\n" % i for i in sorted(ids)))


def create(name, copy_from=None):
    """Новый пресет (пустой или копия другого). False — уже есть / ошибка."""
    dst = preset_path(name)
    if os.path.isfile(dst):
        return False
    try:
        src = preset_path(copy_from) if copy_from else None
        if src and os.path.isfile(src):
            with open(src, 'r', encoding='utf-8') as f:
                data = f.read()
            g = game_ids(copy_from)
            if g:
                save_game_ids(name, g)
        else:
            data = '# GTA SA model ID preset: %s\n' % _sanitize(name)
        with open(dst, 'w', encoding='utf-8') as f:
            f.write(data)
    except OSError as e:
        print("[INU] ID preset create %s: %r" % (name, e))
        return False
    return True


def delete(name):
    """Удалить пресет; «default» удалить нельзя."""
    if _sanitize(name) == DEFAULT:
        return False
    try:
        os.remove(preset_path(name))
    except Exception:                                  # noqa: BLE001
        return False
    try:
        os.remove(game_path(name))
    except OSError:
        pass
    return True


def rename(old, new):
    src, dst = preset_path(old), preset_path(new)
    if (_sanitize(old) == DEFAULT or _sanitize(old) == _sanitize(new)
            or os.path.exists(dst) or not os.path.isfile(src)):
        return False
    try:
        os.rename(src, dst)
        if os.path.isfile(game_path(old)):
            os.replace(game_path(old), game_path(new))
    except OSError as e:
        print("[INU] ID preset rename %s: %r" % (old, e))
        return False
    return True


def stamp(name):
    """Отпечаток пресета на диске (для перечитывания окна при правке
    снаружи — блокнот, Blender)."""
    out = []
    for p in (preset_path(name), game_path(name)):
        try:
            st = os.stat(p)
            out.append((st.st_mtime_ns, st.st_size))
        except OSError:
            out.append(None)
    return tuple(out)


class Preset:
    """Пресет в памяти на одну операцию: читается и пишется один раз
    (в INU — чтение и запись файла на каждый выданный ID)."""

    def __init__(self, name):
        self.name = _sanitize(name)
        self.entries = load(self.name)
        self._idx = {}                       # ID → позиции в entries (дубли — несколько)
        for k, (i, _n) in enumerate(self.entries):
            self._idx.setdefault(i, []).append(k)
        self.game = game_ids(self.name)
        self._game0 = set(self.game)
        self.changed = False

    # — запросы —
    def used(self):
        return {i: n for i, n in self.entries if n}

    def ids(self):
        return set(self._idx)

    def is_free(self, i):
        """ID есть в пресете и ни одна его строка не занята."""
        pos = self._idx.get(i)
        return bool(pos) and not any(self.entries[k][1] for k in pos)

    # — изменения —
    def _append(self, i, name):
        self._idx.setdefault(i, []).append(len(self.entries))
        self.entries.append((i, name))
        self._order = None
        self.changed = True

    def _set(self, i, name):
        pos = self._idx.get(i)
        if not pos:
            self._append(i, name)
            return
        for k in pos:
            self.entries[k] = (i, name)
        if name is None:
            self._order = None          # освобождён — поиск снова с начала
        self.changed = True

    _order = None

    def allocate(self, name, skip, prefer=None):
        """Первый по возрастанию свободный ID (не в skip) → занят именем.
        prefer — сначала он, если свободен. None — свободных нет. Поиск идёт
        курсором по отсортированным ID (skip за операцию только растёт)."""
        if prefer is not None and prefer not in skip and self.is_free(prefer):
            self._set(prefer, name)
            return prefer
        if self._order is None:
            self._order = sorted(self._idx)
            self._cur = 0
        k = self._cur
        while k < len(self._order):
            i = self._order[k]
            if i not in skip and self.is_free(i):
                self._set(i, name)
                self._cur = k + 1
                return i
            k += 1
        self._cur = k
        return None

    def reserve(self, i, name):
        """ID занят именем (перезаписывает имя; нет в пресете — добавляется)."""
        if self.used().get(i) != name or i not in self.ids():
            self._set(i, name)

    def release(self, i):
        if i in self.used():
            self._set(i, None)
            return True
        return False

    def gc(self, scene_ids):
        """Free phantoms: занятые без объекта в сцене → свободны (кроме ID
        игры). Сколько освобождено."""
        n = 0
        for i in list(self.used()):
            if i not in scene_ids and i not in self.game:
                self._set(i, None)
                n += 1
        return n

    def clear_all(self):
        """Clear All: все занятые → свободны (кроме ID игры)."""
        n = 0
        for i in list(self.used()):
            if i not in self.game:
                self._set(i, None)
                n += 1
        return n

    def fill(self, first=FIRST_ID, last=LAST_ID):
        """Create ID: недостающие first..last — свободными; занятые остаются."""
        have = self.ids()
        add = [i for i in range(first, last + 1) if i not in have]
        for i in add:
            self._append(i, None)
        return len(add)

    def extend(self, count):
        """Extend FLA: count свободных после максимального ID. (от, до)."""
        top = max(self.ids()) if self.entries else FIRST_ID - 1
        start = top + 1
        for i in range(start, start + count):
            self._append(i, None)
        return start, start + count - 1

    def mark_game(self, game):
        """From Game: {ID: имя} игры → заняты этими именами и помечены.
        ([(ID, старое имя, имя игры)] — занятые ранее другим именем, новых)."""
        clashes, added = [], 0
        cur = self.used()
        have = self.ids()
        for i, gname in sorted(game.items()):
            old = cur.get(i)
            if old and old.lower() != gname.lower() and i not in self.game:
                clashes.append((i, old, gname))
            if i not in have:
                added += 1
            if old != gname or i not in have:
                self._set(i, gname)
        self.game |= set(game)
        return clashes, added

    def save(self):
        if self.changed:
            save(self.name, self.entries)
        if self.game != self._game0:
            save_game_ids(self.name, self.game)
