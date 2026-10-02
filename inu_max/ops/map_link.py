# INU Tools (Max) — связь объектов сцены со строками IDE / IPL (порт
# ops/map_link.py Blender-версии INU; ядро — inu_gta_core.mapsync).
#
# Строка файла ищется по «якорю» — тому, что объект помнит о своей строке
# (id, имя, позиция, поворот), а не по номеру строки: номера сдвигаются от
# любой правки файла. В Blender якорь — obj.inu.*, здесь — user properties
# узла «inu_<ключ>» (как все свойства INU в Max).
#
# Отличия от Blender: владелец строки (ipl_owner) — handle узла, а не имя
# (в Max имена могут повторяться); LOD-партнёр (lod_object) — тоже handle.
# Позиция и поворот якоря пишутся с полной точностью (repr), иначе строку
# далеко от центра карты не найти.
#
# Исправлено против Blender (решения пользователя, 2026-09-28):
# - Add верхнего бокса для модели, связанной с ДРУГИМ файлом, — перенос:
#   строка пишется в выбранный файл и удаляется из старого (в Blender —
#   вторая расстановка, старая строка оставалась);
# - VC / III: масштаб строки = масштаб узла (Blender писал 1.0); новые
#   строки — в формате строк самого файла (Blender — формат игры сцены);
# - слежение за файлами: пропавший на время файл связи не снимает;
# - статусы сравнивают с тем, что реально уходит в файл (TXD модели, TXD и
#   дистанция LOD из его модели); LOD с Model ID 0 получает записанный id;
#   поворот тоже даёт «coordinates drifted»;
# - Sync from IDE: сначала своя IDE; имя в нескольких IDE с разными id —
#   не связывается; смена id — в отчёте;
# - Check IPL: «единственная свободная строка модели» — только в 2 м;
# - Restore coords — мировая матрица (с родителем тоже верно), с масштабом;
# - ide_remove: ошибка чтения файла — сообщение, а не исключение.
# - TXD LOD-а в IDE: свой, затем модели (Blender писал TXD модели поверх
#   своего TXD ванильного LOD-а).
# Дополнительно: позиция / поворот узла в пределах 1 мм / 1e-5 от якоря
# пишутся значениями якоря (float32 Max далеко от центра карты иначе давал
# «изменено» у нетронутых строк), знак кватерниона — как у якоря.
#
# Под-меши модели (импорт многомешевой DFF: несколько мешей с одним Model
# ID под одним корнем) — одна расстановка: пишется главный меш.

import math
import os
import re
import uuid

PREFIX = 'inu_'


def norm(p):
    """Путь для сравнения (как norm INU): абсолютный, регистр Windows."""
    return os.path.normcase(os.path.abspath(p)) if p else ''


def fmt(v):
    """Значение для буфера user properties (как пишут setUserProp /
    selection.put_field): строки и векторы — в кавычках."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, (tuple, list)):
        return '"%s"' % ",".join(repr(float(x)) for x in v)
    return '"%s"' % str(v).replace('"', "'")


def buffer_props(d):
    """{ключ: значение} → {inu_ключ: текст для буфера}."""
    return {PREFIX + k: fmt(v) for k, v in d.items()}


# ── поля связи (что пишет импорт; Add / Sync — во 2-й части) ─────────

IPL_CLEAR = {
    'ipl_uuid': '', 'ipl_target_file': '', 'ipl_last_model_id': 0,
    'ipl_last_name': '', 'ipl_last_pos': (0.0, 0.0, 0.0),
    'ipl_last_rot': (0.0, 0.0, 0.0, 1.0), 'ipl_owner': 0, 'lod_index': -1,
}

IDE_CLEAR = {
    'ide_linked': False, 'ide_target_file': '', 'ide_last_model_id': 0,
    'ide_last_name': '', 'ide_last_draw_distance': 0.0,
    'ide_last_txd_name': '', 'ide_last_flags': 0,
}


def ipl_stamp(path, inst, lod_index=None):
    """Якорь строки IPL (stamp_ipl INU): новый uuid, файл, id / имя /
    позиция / поворот строки (кватернион — как в файле, x y z w).
    ipl_owner (handle узла) ставит тот, кто знает узел."""
    d = {
        'ipl_uuid': uuid.uuid4().hex, 'ipl_target_file': norm(path),
        'ipl_last_model_id': int(inst.model_id), 'ipl_last_name': inst.model_name,
        'ipl_last_pos': (float(inst.pos_x), float(inst.pos_y), float(inst.pos_z)),
        'ipl_last_rot': (float(inst.rot_x), float(inst.rot_y), float(inst.rot_z),
                         float(inst.rot_w)),
    }
    if lod_index is not None:
        d['lod_index'] = int(lod_index)
    return d


def ide_stamp(path, entry):
    """Связь со строкой IDE (stamp_ide INU): файл и значения строки на момент
    связи — по ним статус показывает «изменено»."""
    return {
        'ide_linked': True, 'ide_target_file': norm(path),
        'ide_last_model_id': int(entry.model_id), 'ide_last_name': entry.model_name,
        'ide_last_draw_distance': float(entry.draw_distance),
        'ide_last_txd_name': entry.txd_name, 'ide_last_flags': int(entry.flags),
    }


# ── строка IPL ↔ матрица узла ────────────────────────────────────────
# Кватернион IPL (x, y, z, w) — это ровно node.transform.rotationpart Max
# (проверено в Max: строки [0,1,0] [-1,0,0] [0,0,1] = +90° по Z → (0, 0,
# −0.7071, 0.7071), как пишет INU). Строки матрицы Max = строки обычной
# матрицы поворота этого кватерниона, без сопряжения.

def quat_rows(x, y, z, w):
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def inst_rows(inst):
    """Game placement matrix: rotation and position; IPL scale is ignored."""
    rows = quat_rows(inst.rot_x, inst.rot_y, inst.rot_z, inst.rot_w)
    return [c for r in rows for c in r] + [float(inst.pos_x), float(inst.pos_y),
                                           float(inst.pos_z)]


def mul_rows(a, b):
    """Произведение матриц Max a·b (12 чисел: строки поворота + позиция)."""
    out = []
    for i in range(3):
        for j in range(3):
            out.append(sum(a[i * 3 + k] * b[k * 3 + j] for k in range(3)))
    for j in range(3):
        out.append(sum(a[9 + k] * b[k * 3 + j] for k in range(3)) + b[9 + j])
    return out


# ══ часть 2 Map IO: запись / удаление / синхронизация ═══════════════════

DEFAULT_DD = 299.0          # draw_distance / lod_draw_distance по умолчанию (как INU)
DEFAULT_LOD_DD = 999.0
POS_EPS = 1e-3              # сдвиг узла меньше 1 мм от якоря — это float32, не правка
ROT_EPS = 1e-5

# Сообщения ядра (шаблоны mapsync по-русски, как в INU) → англ. из locale/eng.py.
_EN = {
    "«{0}»: у строки нет LOD — отвязывать нечего":
        "«{0}»: the row has no LOD — nothing to detach",
    "«{0}»: строка в файле была изменена вручную — найдена рядом и обновлена":
        "«{0}»: the row was edited by hand — found nearby and updated",
    "«{0}»: прежняя строка в файле не найдена (удалена или правилась вручную) — "
    "добавлена заново":
        "«{0}»: its previous row is not in the file (deleted or edited by hand) — added again",
    "«{0}»: строка не найдена в файле — удалять нечего":
        "«{0}»: row not found in the file — nothing to remove",
    "{0} строк(и) ссылались на удалённый LOD — их lod_index сброшен в -1":
        "{0} row(s) pointed at a removed LOD — their lod_index was reset to -1",
    "ID {0} уже занят в секции {1} («{2}») — «{3}» не записана":
        "ID {0} is already used in section {1} («{2}») — «{3}» not written",
    "ID {0} в файле занят другой моделью «{1}» — «{2}» не записана. Проверь Model ID":
        "ID {0} is taken in the file by another model «{1}» — «{2}» not written. "
        "Check the Model ID",
    "«{0}» уже есть в файле с ID {1} — не записана (поставь модели этот ID или удали "
    "ту строку)":
        "«{0}» is already in the file with ID {1} — not written (give the model that ID "
        "or delete that row)",
    "«{0}»: ID изменён {1} → {2}": "«{0}»: ID changed {1} → {2}",
    "«{0}»: у копий разные параметры IDE — записаны параметры первой":
        "«{0}»: copies have different IDE settings — the first one was written",
    "ID {0} в файле принадлежит «{1}», а не «{2}» — не удалено":
        "ID {0} in the file belongs to «{1}», not «{2}» — not removed",
}


def _core_text(m):
    return _EN.get(m.fmt, m.fmt).format(*m.args)


def _base(path):
    return os.path.basename(path) or path


class Report:
    """Счётчики + сообщения одного прогона (как Report INU)."""

    def __init__(self):
        self.counts = {}
        self.messages = []          # (уровень, текст)
        self.files = set()          # записанные файлы
        self.touch = {}             # файл → что в нём будет сделано (для подтверждения)

    def add(self, key, n=1):
        self.counts[key] = self.counts.get(key, 0) + n

    def msg(self, level, text):
        self.messages.append((level, text))

    def plan(self, path, what):
        self.touch.setdefault(path, []).append(what)

    def problems(self):
        return [m for m in self.messages if m[0] in ('WARNING', 'ERROR')]

    def merge(self, other):
        for k, v in other.counts.items():
            self.add(k, v)
        self.messages += other.messages
        self.files |= other.files
        for p, w in other.touch.items():
            self.touch.setdefault(p, []).extend(w)


def summary(prefix, rep):
    """Итоговая строка (summary INU, англ. подписи из eng.py)."""
    c = rep.counts
    parts = []
    if c.get('add'):
        parts.append("added %d" % c['add'])
    if c.get('update'):
        parts.append("updated %d" % c['update'])
    if c.get('moved'):
        parts.append("moved from another file %d" % c['moved'])
    if c.get('lod_add') or c.get('lod_update'):
        parts.append("LOD +%d ~%d" % (c.get('lod_add', 0), c.get('lod_update', 0)))
    if c.get('removed'):
        parts.append("removed %d" % c['removed'])
    if c.get('lod_removed'):
        parts.append("LOD removed %d" % c['lod_removed'])
    if c.get('unchanged') or c.get('same'):
        parts.append("unchanged %d" % (c.get('unchanged', 0) + c.get('same', 0)))
    if c.get('conflict'):
        parts.append("conflicts %d" % c['conflict'])
    if c.get('synced'):
        parts.append("updated from file %d" % c['synced'])
    if c.get('linked'):
        parts.append("new links %d" % c['linked'])
    if c.get('lost'):
        parts.append("row not found %d" % c['lost'])
    if c.get('skipped'):
        parts.append("skipped %d" % c['skipped'])
    if not parts:
        parts.append("nothing to do")
    return "%s: %s" % (prefix, ", ".join(parts))


def report_text(prefix, rep):
    """(уровень, текст): итог первой строкой, затем сообщения без повторов."""
    lines, seen = [summary(prefix, rep)], set()
    for level, text in rep.messages:
        if (level, text) in seen:
            continue
        seen.add((level, text))
        lines.append(text)
    level = 'ERROR' if any(m[0] == 'ERROR' for m in rep.messages) else (
        'WARNING' if rep.problems() else 'INFO')
    return level, "\n".join(lines)


# ── индекс сцены ─────────────────────────────────────────────────────

_DUP_MARK = re.compile(r'^(.*_(?:dff|lod|col|sha))\d{3}$', re.I)
_DUP_TAIL = re.compile(r'^(.+?)(\d{3})$')


def _unit(q):
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


class Scene:
    """Геометрия сцены на одну операцию: узлы, их свойства, типы моделей,
    под-меши, держатели строк IPL."""

    def __init__(self, recs=None):
        from ..adapter import link_scene as LS
        self.LS = LS
        self.recs = LS.index() if recs is None else list(recs)
        self.by_handle = {r.handle: r for r in self.recs}
        self._types = {}
        self._groups = None
        self._holders = None

    # — узлы —
    def rec(self, node):
        try:
            return self.by_handle.get(int(node.inode.handle))
        except Exception:                              # noqa: BLE001
            return None

    def is_col(self, r):
        return r.get('type', 'OBJ').upper() in ('COL', 'SHA')

    def model_type(self, r):
        """(DFF | LOD | COL, базовое имя) — классификатор ядра; суффикс Max
        «001» после маркера (_DFF001) не часть имени."""
        hit = self._types.get(r.handle)
        if hit is None:
            from inu_gta_core.model_classify import classify_model
            name = r.name
            m = _DUP_MARK.match(name)
            if m:
                name = m.group(1)
            hit = classify_model(name, has_texture=lambda: self.LS.has_texture(r.node),
                                 inu_type=r.get('type', 'OBJ').upper())
            self._types[r.handle] = hit
        return hit

    def model_name(self, r):
        """Game model name of a placement, preserving a valid import stamp."""
        from inu_gta_core.mapsync import game_model_name
        base = self.model_type(r)[1]
        m = _DUP_TAIL.match(base)
        if m:
            known = {r.get('ipl_last_name', '').lower(), r.get('ide_last_name', '').lower()}
            if m.group(1).lower() in known - {''}:
                base = m.group(1)
        main = self.main_of(r)
        peers = self._groups.get(r.handle, (r, [r]))[1] if self._groups else [r]
        if len(peers) > 1 or game_model_name(base) != base:
            mid = main.get('model_id', 0)
            for prefix in ('ipl', 'ide'):
                stamp = main.get(prefix + '_last_name', '')
                if stamp and mid > 0 and main.get(prefix + '_last_model_id', 0) == mid:
                    return stamp
            return game_model_name(self.model_type(main)[1])
        return base

    def _placements(self):
        from inu_gta_core.mapsync import group_instances, is_damage_part
        items = []
        for o in self.recs:
            if o.get('model_id', 0) > 0 and self.model_type(o)[0] == 'DFF':
                pos, quat, _scale = self.LS.world(o.node)
                items.append((o.handle, o.get('model_id', 0), pos, quat))
        self._groups = {}
        def rank(o):
            return (is_damage_part(o.name), o.get('atomic_order', 1 << 30),
                    o.name.casefold(), o.handle)
        for handles in group_instances(items):
            peers = [self.by_handle[h] for h in handles]
            linked = [o for o in peers if o.get('ipl_uuid', '')]
            originals = [o for o in linked if not self.is_copy(o)]
            head = min(originals or linked or peers, key=rank)
            original_handles = {o.handle for o in originals}
            for o in peers:
                self._groups[o.handle] = (o if o.handle in original_handles else head, peers)

    def main_of(self, r):
        """Meshes with the same ID and placement form one model, regardless of parent."""
        if r.get('model_id', 0) <= 0 or self.model_type(r)[0] != 'DFF':
            return r
        if self._groups is None:
            self._placements()
        return self._groups.get(r.handle, (r, [r]))[0]

    def followers(self, r):
        self.main_of(r)
        peers = self._groups.get(r.handle, (r, [r]))[1] if self._groups else [r]
        return [o for o in peers if self.main_of(o) is r]

    def pick(self, nodes):
        """Выделение → модели (главные меши, без повторов, без коллизии)."""
        out, seen = [], set()
        for n in nodes:
            r = self.rec(n)
            if r is None or self.is_col(r):
                continue
            r = self.main_of(r)
            if r.handle in seen:
                continue
            seen.add(r.handle)
            out.append(r)
        return out

    def models(self):
        """Все модели сцены (главные меши) — для «пустого выделения = вся сцена»."""
        return self.pick([r.node for r in self.recs])

    # — копии (Shift-клон переносит user props вместе с ipl_uuid) —
    def reset_copies(self):
        self._holders = None
        self._groups = None

    def is_copy(self, r):
        u = r.get('ipl_uuid', '')
        if not u:
            return False
        if self._holders is None:
            self._holders = {}
            for o in self.recs:
                h = o.get('ipl_uuid', '')
                if h:
                    self._holders.setdefault(h, []).append(o)
        hs = [o for o in self._holders.get(u, ()) if o.get('ipl_uuid', '') == u]
        if len(hs) <= 1:
            return False
        stamped = [o for o in hs if o.get('ipl_owner', 0) == o.handle]
        owner = stamped[0] if stamped else min(hs, key=lambda o: o.handle)
        return r is not owner

    def split_copies(self, recs):
        self.reset_copies()
        copies = [r for r in recs if self.is_copy(r)]
        for r in copies:
            clear_ipl(r)
        self.reset_copies()
        return len(copies)

    def linked_models(self):
        return [r for r in self.models() if r.get('ipl_uuid', '')]


# ── якоря IPL / IDE ──────────────────────────────────────────────────

def ipl_linked_file(r):
    if not r.get('ipl_uuid', '') or not r.get('ipl_target_file', ''):
        return ''
    return norm(r.get('ipl_target_file', ''))


def ipl_anchor(r):
    from inu_gta_core.mapsync import Anchor
    if not r.get('ipl_uuid', ''):
        return None
    mid = r.get('ipl_last_model_id', 0) or r.get('model_id', 0)
    rot = r.get('ipl_last_rot', (0.0, 0.0, 0.0, 1.0))
    if not any(rot):
        rot = None
    return Anchor(mid, r.get('ipl_last_name', ''), r.get('ipl_last_pos', (0.0, 0.0, 0.0)), rot)


def stamp_ipl(r, path, inst, lod_index=None, fresh=False):
    d = ipl_stamp(path, inst, lod_index)
    if not fresh and r.get('ipl_uuid', ''):
        d['ipl_uuid'] = r.get('ipl_uuid', '')
    d['ipl_owner'] = r.handle
    r.put(d)


def clear_ipl(r):
    r.put(IPL_CLEAR)


def ide_linked_file(r):
    if not r.get('ide_linked', False) or not r.get('ide_target_file', ''):
        return ''
    return norm(r.get('ide_target_file', ''))


def stamp_ide(r, path, entry):
    r.put(ide_stamp(path, entry))


def clear_ide(r):
    r.put(IDE_CLEAR)


def _snap(pos, q, anchor):
    """Позиция / поворот узла в пределах float32 от якоря → значения якоря;
    знак кватерниона — как у якоря (q и −q — один поворот)."""
    if anchor is None:
        return pos, q
    if all(abs(p - c) <= POS_EPS for p, c in zip(pos, anchor.pos)):
        pos = tuple(float(c) for c in anchor.pos)
    if anchor.rot is not None:
        if sum(x * y for x, y in zip(q, anchor.rot)) < 0:
            q = tuple(-x for x in q)
        if all(abs(x - y) <= ROT_EPS for x, y in zip(q, anchor.rot)):
            q = tuple(float(c) for c in anchor.rot)
    return pos, q


def ipl_entry(sc, r):
    """Строка IPL из узла (_ipl_entry_from_obj INU): мировая позиция,
    поворот (rotationpart = кватернион IPL)."""
    from inu_gta_core.ipl import IplInstance
    pos, q, _scale = sc.LS.world(r.node)
    pos, q = _snap(pos, _unit(q), ipl_anchor(r))
    return IplInstance(
        model_id=r.get('model_id', 0), model_name=sc.model_name(r),
        interior=r.get('interior_id', 0),
        pos_x=pos[0], pos_y=pos[1], pos_z=pos[2],
        rot_x=q[0], rot_y=q[1], rot_z=q[2], rot_w=q[3],
        lod_index=r.get('lod_index', -1), real_interior=r.get('real_interior', 0))


def apply_inst(r, inst, sc=None):
    """Узел → мировая матрица строки (Restore coords / Sync)."""
    from ..adapter import link_scene as LS
    nodes = sc.followers(r) if sc is not None else [r]
    for part in nodes:
        LS.set_world(part.node, inst_rows(inst))


def file_game(doc, default):
    """Формат строк IPL-файла (SA / VC / III) — по его строкам inst; пустой
    или новый — игра сцены."""
    counts = {}
    for row in doc.rows:
        if row.inst is not None:
            counts[row.style] = counts.get(row.style, 0) + 1
    if not counts:
        return default
    return max(counts, key=lambda k: counts[k])


# ── LOD-партнёры ─────────────────────────────────────────────────────

class LodIndex:
    """LOD-меши сцены по базовому имени модели (LodIndex INU)."""

    def __init__(self, sc):
        from inu_gta_core.ipl import strip_lod_marker
        self.sc = sc
        self.by_base = {}
        self.by_tail = {}
        from .. import settings
        self.game = settings.get('game', 'SA')
        for r in sc.recs:
            if sc.is_col(r):
                continue
            nm = r.name.lower()
            if 'lod' not in nm and r.get('type', '').upper() != 'LOD':
                continue
            mt, base = sc.model_type(r)
            if mt != 'LOD' or not base:
                continue
            if self.game in ('III', 'VC'):
                for name in {lod_model_name(r, base, game=self.game, sc=sc), _plain_lod_name(r)}:
                    if name.lower().startswith('lod') and len(name) > 3:
                        self.by_tail.setdefault(name[3:], []).append((name, r))
            low = base.lower()
            keys = {low, strip_lod_marker(base).lower()}
            if low.startswith('lod'):
                keys.add(low[3:].lstrip('_-'))
            for k in keys:
                if k:
                    self.by_base.setdefault(k, []).append(r)

    def partner(self, dff):
        h = dff.get('lod_object', 0)
        if h:
            r = self.sc.by_handle.get(h)
            if r is not None and r is not dff:
                return r
        return self.by_name(dff)

    def by_name(self, dff):
        base = self.sc.model_type(dff)[1]
        cands = [c for c in self.by_base.get((base or '').lower(), []) if c is not dff]
        if not cands:
            cands = self.tail_partners(dff, self.sc.model_name(dff))
        if not cands:
            return None
        # без суффикса Max «001» — первым
        return min(cands, key=lambda o: (bool(_DUP_TAIL.match(o.name)), o.handle))

    def tail_partners(self, dff, name):
        from inu_gta_core.ipl import lod_owner_by_tail
        from inu_gta_core.mapsync import pos_close, rot_close
        hits = self.by_tail.get(name[3:], ()) if len(name) > 3 else ()
        if not hits:
            return []
        models = [(r.get('model_id', 0), self.sc.model_name(r)) for r in self.sc.recs
                  if self.sc.model_type(r)[0] == 'DFF']
        lp = []
        dp, dq, _ = self.sc.LS.world(dff.node)
        spots = [(dp, dq)]
        if dff.get('ipl_uuid', ''):
            spots.append((dff.get('ipl_last_pos', dp), dff.get('ipl_last_rot', dq)))
        for nm, r in hits:
            if lod_owner_by_tail(nm, models) != name:
                continue
            p, q, _ = self.sc.LS.world(r.node)
            if any(pos_close(p, pos, .01) and rot_close(q, quat, 1e-4) for pos, quat in spots):
                lp.append(r)
        return list({r.handle: r for r in lp}.values())

    def owners(self, lod, dffs):
        return [d for d in dffs if self.partner(d) is lod]


class IdeLods:
    """LOD модели из IDE, когда LOD-меша в сцене нет (IdeLods INU): своя IDE
    модели, IDE бокса, список «IDE to export»; строка LOD-имени с базой
    модели, при нескольких — с id = id модели + 1."""

    def __init__(self):
        from .. import settings
        self.common = []
        for p in [settings.get('ide_path', '') or ''] + list(settings.get('ide_sync_list', []) or []):
            p = norm(p) if p else ''
            if p and p not in self.common and os.path.isfile(p):
                self.common.append(p)
        self._by_file = {}
        self._model_rows = {}

    def _index(self, path):
        if path not in self._by_file:
            from inu_gta_core.mapsync import IdeDoc
            from inu_gta_core.ipl import is_lod_name, strip_lod_marker
            idx = {}
            try:
                doc = IdeDoc.load(path)
            except OSError:
                doc = None
            self._model_rows[path] = [(int(row.model_id), row.name) for row in (doc.rows if doc else ())
                                      if row.section in ('objs', 'tobj') and not is_lod_name(row.name)]
            for row in (doc.rows if doc else ()):
                if row.section not in ('objs', 'tobj') or not is_lod_name(row.name):
                    continue
                low = row.name.lower()
                bases = {strip_lod_marker(row.name).lower(), '~' + row.name[3:]}
                if low.startswith('lod'):
                    bases.add(low[3:].lstrip('_-'))
                for b in bases:
                    idx.setdefault(b, []).append((row.model_id, row.name))
            self._by_file[path] = idx
        return self._by_file[path]

    def find(self, dff, base):
        files = []
        own = ide_linked_file(dff)
        if own and os.path.isfile(own):
            files.append(own)
        files += [p for p in self.common if p not in files]
        did = dff.get('model_id', 0)
        from .. import settings
        from inu_gta_core.ipl import lod_owner_by_tail
        game = settings.get('game', 'SA')
        for path in files:
            self._index(path)
        all_models = [row for path in files for row in self._model_rows.get(path, ())]
        for path in files:
            cands = self._index(path).get((base or '').lower())
            if not cands and game in ('III', 'VC') and len(base) > 3:
                models = self._model_rows.get(path, ()) if game == 'VC' else all_models
                cands = [c for c in self._index(path).get('~' + base[3:], ())
                         if lod_owner_by_tail(c[1], models) == base]
            if cands:
                best = min(cands, key=lambda c: (c[0] != did + 1, c[0]))
                return best[0], best[1], path
        return None


_IDE_NAMES = {}


def _ide_names(path):
    try:
        st = os.stat(path)
    except OSError:
        return {}, {}
    stamp = st.st_mtime_ns, st.st_size
    hit = _IDE_NAMES.get(norm(path))
    if hit is None or hit[0] != stamp:
        from inu_gta_core.mapsync import IdeDoc
        by_name, by_tail = {}, {}
        try:
            rows = IdeDoc.load(path).rows
        except (OSError, ValueError):
            rows = []
        for row in rows:
            if row.section not in ('objs', 'tobj'):
                continue
            pair = (int(row.model_id), row.name)
            by_name.setdefault(row.name.casefold(), []).append(pair)
            if len(row.name) > 3:
                by_tail.setdefault(row.name[3:], []).append(pair)
        hit = _IDE_NAMES[norm(path)] = (stamp, by_name, by_tail)
    return hit[1], hit[2]


def _known_ides(recs, game):
    from .. import settings
    from inu_gta_core.gta_dat import dat_game, game_ide_paths
    paths = [ide_linked_file(r) for r in recs]
    paths += [settings.get('ide_path', '')] + list(settings.get('ide_sync_list', []) or [])
    root = settings.get('game_root', '') or ''
    if root and dat_game(root) == game:
        paths += game_ide_paths(root)[0]
    return list(dict.fromkeys(norm(p) for p in paths if p and os.path.isfile(p)))


def _plain_lod_name(lod):
    name = _DUP_MARK.sub(r'\1', lod.name)
    name = re.sub(r'_(?:DFF|LOD)$', '', name, flags=re.I)
    stamp = lod.get('ide_last_name', '')
    if _DUP_TAIL.match(name) and _DUP_TAIL.match(name).group(1).casefold() == stamp.casefold():
        name = _DUP_TAIL.match(name).group(1)
    return name


def lod_name_taken(name, hd, lod=None, game=None, sc=None):
    from .. import settings
    from inu_gta_core.ipl import lod_owner_by_tail
    game = game or settings.get('game', 'SA')
    if game not in ('III', 'VC') or len(hd) <= 3:
        return ''
    sc = sc or Scene()
    peers, linked = {hd.casefold(): (0, hd)}, [lod] if lod is not None else []
    me = _plain_lod_name(lod).casefold() if lod is not None else ''
    for r in sc.recs:
        if sc.is_col(r):
            continue
        plain = _plain_lod_name(r)
        if me and plain.casefold() == me:
            continue
        if name.casefold() in (plain.casefold(), r.get('ide_last_name', '').casefold()):
            return r.name
        if sc.model_type(r)[0] != 'DFF':
            continue
        base = sc.model_name(r)
        if base[3:].casefold() != hd[3:].casefold():
            continue
        mid = int(r.get('model_id', 0))
        old = peers.get(base.casefold())
        if old is None or (mid > 0 and (old[0] <= 0 or mid < old[0])):
            peers[base.casefold()] = (mid, base)
        if base.casefold() == hd.casefold():
            linked.append(r)
    first = min(peers.values(), key=lambda v: (v[0] <= 0, v[0], v[1].casefold()))
    if first[1].casefold() != hd.casefold():
        return first[1]
    hid = peers[hd.casefold()][0]
    lid = lod.get('model_id', 0) if lod is not None else 0
    lid = lid or (hid + 1 if hid > 0 else 0)
    for path in _known_ides(linked, game):
        by_name, by_tail = _ide_names(path)
        for mid, nm in by_name.get(name.casefold(), ()):
            if mid != lid:
                return '%s, %s' % (nm, _base(path))
        if game == 'VC' and hd.casefold() not in by_name:
            continue
        candidates = [v for v in by_tail.get(hd[3:], ()) if v[1].casefold() != name.casefold()]
        owner = lod_owner_by_tail(name, candidates + [(hid, hd)])
        if owner is not None and owner.casefold() != hd.casefold():
            return '%s, %s' % (owner, _base(path))
    return ''


def lod_model_name(lod, base, hd='', game=None, sc=None):
    from .. import settings
    from inu_gta_core.ipl import lod_name_for
    game = game or settings.get('game', 'SA')
    fallback = base[3:] if base.lower().startswith('lod') else base
    return lod_name_for(_plain_lod_name(lod), lod.get('ide_last_name', ''), hd, fallback, game,
                        taken=lambda n: lod_name_taken(n, hd, lod, game, sc))


def new_lod_name(hd, base, game=None, sc=None):
    from .. import settings
    from inu_gta_core.ipl import lod_name_for
    game = game or settings.get('game', 'SA')
    return lod_name_for('', '', hd, base, game,
                        taken=lambda n: lod_name_taken(n, hd, None, game, sc))


def lod_name_note(lod, name, hd, game=None, sc=None):
    from .. import settings
    from inu_gta_core.ipl import default_lod_name, lod_pairs_by_name
    game = game or settings.get('game', 'SA')
    if game not in ('III', 'VC') or not hd:
        return ''
    if len(hd) <= 3:
        return '«%s»: name shorter than 4 characters — the game cannot pair its LOD' % hd
    if lod_pairs_by_name(name, hd):
        return ''
    wanted = default_lod_name(hd, game)
    who = lod_name_taken(wanted, hd, lod, game, sc)
    if who:
        return '«%s»: LOD name %s is taken (%s); %s will not pair — rename the model' % (hd, wanted, who, name)
    return '«%s»: LOD %s will not pair in III/VC — expected %s' % (hd, name, wanted)


def lod_model_id(lod, dff):
    mid = lod.get('model_id', 0)
    if mid > 0:
        return mid
    did = dff.get('model_id', 0) if dff is not None else 0
    return did + 1 if did > 0 else 0


def _lod_is_model(lod, dinst):
    return (int(lod.model_id) == int(dinst.model_id)
            or lod.model_name.lower() == dinst.model_name.lower())


def lod_inst_for(sc, dff, lod, base):
    """Строка LOD: модель LOD в матрице модели."""
    import copy as _copy
    d = ipl_entry(sc, dff)
    e = _copy.copy(d)
    e.model_name = lod_model_name(lod, sc.model_type(lod)[1] or base, hd=sc.model_name(dff), sc=sc)
    e.model_id = lod_model_id(lod, dff)
    e.lod_index = -1
    return e


def _load_ipl(path, rep):
    from inu_gta_core.mapsync import IplDoc, IplBinaryError
    try:
        return IplDoc.load(path)
    except IplBinaryError:
        rep.msg('ERROR', "%s: binary IPL (from an IMG) — cannot be edited" % _base(path))
    except OSError as e:
        rep.msg('ERROR', "%s: %s" % (_base(path), e))
    return None


def _commit(ed, path, rep, dry_run):
    new = ed.commit()
    for m in ed.messages:
        rep.msg(m.level, _core_text(m))
    if dry_run:
        return True
    if ed.doc.exists and new.to_text() == ed.doc.tl.to_text():
        return True
    try:
        new.write(path)
    except OSError as e:
        rep.msg('ERROR', "%s: %s" % (_base(path), e))
        return False
    rep.files.add(path)
    return True


def _reserve_others(sc, ed, path, batch):
    ids = {r.handle for r in batch}
    for r in sc.recs:
        if r.handle in ids or ipl_linked_file(r) != path or sc.is_copy(r):
            continue
        a = ipl_anchor(r)
        if a is not None:
            ed.reserve(a)


def ipl_expand(sc, recs):
    """(модели DFF, LOD-меши); коллизия в inst не идёт."""
    dffs, lods = [], []
    for r in recs:
        mt = sc.model_type(r)[0]
        if mt == 'COL':
            continue
        (lods if mt == 'LOD' else dffs).append(r)
    return dffs, lods


def _scale_note(sc, d, game, rep):
    s = sc.LS.world(d.node)[2]
    if any(abs(c - 1.0) > 1e-4 for c in s):
        rep.msg('WARNING', "«%s»: scaled — the game does not apply IPL scale (row keeps its own; new rows get 1)"
                % d.name)


# ── IPL: запись ──────────────────────────────────────────────────────

def _lod_row_apart(doc, anchor, inst, lod_id):
    from inu_gta_core.mapsync import pos_close, rot_close
    ref = inst
    if anchor is not None:
        index = doc.find(anchor)
        if index >= 0:
            ref = doc.rows[index].inst
    rows = [row.inst for row in doc.rows if row.inst.model_id == lod_id]
    if not rows:
        return False
    def at(row):
        return pos_close((row.pos_x, row.pos_y, row.pos_z),
                         (ref.pos_x, ref.pos_y, ref.pos_z), .01) and rot_close(
            (row.rot_x, row.rot_y, row.rot_z, row.rot_w),
            (ref.rot_x, ref.rot_y, ref.rot_z, ref.rot_w), 1e-4)
    return not any(at(row) for row in rows)


def ipl_write(sc, recs, *, picked='', game='SA', dry_run=False):
    """Add / обновить расстановки моделей (+ их LOD). picked — IPL бокса:
    все модели идут туда; модель, связанная с другим IPL, переносится
    (строка удаляется из старого файла). Без picked — каждая в свой IPL."""
    sc.reset_copies()
    rep = Report()
    picked = norm(picked) if picked else ''
    lodix = LodIndex(sc)
    dffs, lods = ipl_expand(sc, recs)

    via_lod = set()
    if lods:
        dff_ids = {d.handle for d in dffs}
        linked = [o for o in sc.linked_models() if sc.model_type(o)[0] == 'DFF']
        for lod in lods:
            if any(lodix.partner(d) is lod for d in dffs):
                continue
            owners = lodix.owners(lod, linked)
            if not owners:
                rep.msg('WARNING', "«%s»: LOD without its main model — select the main model"
                        % lod.name)
            for d in owners:
                if d.handle not in dff_ids:
                    dffs.append(d)
                    dff_ids.add(d.handle)
                    via_lod.add(d.handle)

    # перенос: модель связана с другим существующим IPL — старый якорь запомнить
    moved = {}
    for d in dffs:
        own = ipl_linked_file(d)
        if (own and picked and own != picked and d.handle not in via_lod
                and os.path.isfile(own) and not sc.is_copy(d)):
            moved[d.handle] = (own, ipl_anchor(d))

    # копия идёт новой строкой в IPL оригинала (так обещает статус «Copy —
    # will be added as a new instance»; в Blender Add в строке модели для
    # копии давал «нет своего IPL»)
    copy_file = {d.handle: ipl_linked_file(d) for d in dffs if sc.is_copy(d)}
    if not dry_run:
        n = sc.split_copies(dffs)
        if n:
            rep.msg('INFO', "%d copies — added as new placements" % n)

    groups = {}
    for d in dffs:
        own = ipl_linked_file(d)
        if dry_run and sc.is_copy(d):
            own = ''
        own = own or copy_file.get(d.handle, '')
        path = own if d.handle in via_lod else (picked or own)
        if not path:
            rep.msg('ERROR', "«%s»: has no IPL of its own — pick a file in the IPL box" % d.name)
            continue
        if d.handle in moved:
            rep.msg('INFO', "«%s»: moves from %s to %s" % (d.name, _base(moved[d.handle][0]),
                                                           _base(path)))
        groups.setdefault(path, []).append(d)

    ide_lods = IdeLods()
    written = set()
    for path, batch in groups.items():
        doc = _load_ipl(path, rep)
        if doc is None:
            continue
        fgame = file_game(doc, game)
        fla = any(o.get('real_interior', 0) for o in batch)
        ed = doc.editor(game=fgame, fla=fla or None)
        _reserve_others(sc, ed, path, batch)
        placed, lod_of = [], {}
        for d in batch:
            if d.get('model_id', 0) <= 0:
                rep.msg('ERROR', "«%s»: Model ID = 0 — not written" % d.name)
                continue
            copy_now = dry_run and sc.is_copy(d)
            anchor = ipl_anchor(d) if (ipl_linked_file(d) == path and not copy_now) else None
            base = sc.model_type(d)[1]
            lod_rec = lodix.partner(d)
            lod = None
            dinst = ipl_entry(sc, d)
            _scale_note(sc, d, fgame, rep)
            if lod_rec is not None:
                lod = lod_inst_for(sc, d, lod_rec, base)
                if lod.model_id <= 0:
                    rep.msg('WARNING', "«%s»: the LOD has no Model ID — LOD not written"
                            % lod_rec.name)
                    lod = None
                elif _lod_is_model(lod, dinst):
                    rep.msg('WARNING', "«%s»: LOD «%s» has the model's own ID/name — LOD taken "
                            "from the IDE" % (d.name, lod_rec.name))
                    lod, lod_rec = None, None
            if lod is None:
                hit = ide_lods.find(d, base)
                if hit is not None:
                    import copy as _copy
                    lod = _copy.copy(dinst)
                    lod.model_id, lod.model_name, lod.lod_index = hit[0], hit[1], -1
                    if _lod_is_model(lod, dinst):
                        lod = None
                    elif fgame in ('III', 'VC') and _lod_row_apart(doc, anchor, dinst, hit[0]):
                        rep.msg('INFO', '«%s»: existing LOD stands apart — IPL row kept' % d.name)
                        lod = None
                    else:
                        rep.msg('INFO', "«%s»: LOD taken from IDE — %s (ID %d, %s)"
                                % (d.name, hit[1], hit[0], _base(hit[2])))
                        if not dry_run:
                            d.put({'lod_ide_id': int(hit[0]), 'lod_ide_name': hit[1],
                                   'lod_ide_file': hit[2]})
            res = ed.place(d, dinst, anchor=anchor, lod=lod)
            placed.append(res)
            if lod_rec is not None and lod is not None:
                lod_of[d.handle] = lod_rec
            rep.plan(path, 'add/update %s' % d.name)
        if not _commit(ed, path, rep, dry_run):
            continue
        for res in placed:
            rep.add(res.action)
            if res.lod_action in ('add', 'update'):
                rep.add('lod_' + res.lod_action)
            written.add(res.tag.handle)
            if dry_run:
                continue
            stamp_ipl(res.tag, path, res.inst, res.lod_index)
            lr = lod_of.get(res.tag.handle)
            if lr is not None and lr.get('model_id', 0) <= 0 and res.lod_inst is not None:
                lr.put({'model_id': int(res.lod_inst.model_id)})

    # перенос: убрать строки из старых файлов (только у записанных в новый)
    old_groups = {}
    for h, (own, anchor) in moved.items():
        if h in written and anchor is not None:
            old_groups.setdefault(own, []).append((sc.by_handle[h], anchor))
    for path, items in old_groups.items():
        doc = _load_ipl(path, rep)
        if doc is None:
            continue
        ed = doc.editor(game=file_game(doc, game))
        _reserve_others(sc, ed, path, [r for r, _a in items])
        results = [ed.remove(r, a) for r, a in items]
        rep.plan(path, 'remove %d moved placement(s)' % len(items))
        if not _commit(ed, path, rep, dry_run):
            continue
        for res in results:
            if res.removed:
                rep.add('moved')
            if res.lod_removed:
                rep.add('lod_removed')
    return rep


# ── IPL: удаление ────────────────────────────────────────────────────

def _lod_owner_at(sc, lod, dffs, tol):
    """III/VC: explicit owner, else one nearest placement within tol.

    Names also pair by the game tail after the first three characters.
    Earlier candidates win ties; selected placements precede linked ones.
    """
    base = (sc.model_type(lod)[1] or '').lower()
    lname = (lod.get('ide_last_name', '') or base).lower()
    pos = sc.LS.world(lod.node)[0]
    best, best_d = None, tol * tol
    for d in dffs:
        explicit = d.get('lod_object', 0)
        if explicit == lod.handle:
            return d
        name = (d.get('ide_last_name', '') or sc.model_type(d)[1] or '').lower()
        tail_pair = len(name) > 3 and len(lname) > 3 and name[3:] == lname[3:]
        if explicit or (name != base and not tail_pair):
            continue
        spots = [sc.LS.world(d.node)[0]]
        if d.get('ipl_uuid', ''):
            spots.append(d.get('ipl_last_pos', (0.0, 0.0, 0.0)))
        for spot in spots:
            dist = sum((a - b) ** 2 for a, b in zip(spot, pos))
            if dist < best_d or (best is None and dist == best_d):
                best, best_d = d, dist
    return best


def ipl_remove(sc, recs, *, picked='', target='', game='SA', dry_run=False):
    """Удалить расстановки (их LOD — если больше не нужны). Файл: target,
    иначе свой IPL модели, иначе picked. LOD без модели — отвязывается."""
    from inu_gta_core.mapsync import Anchor, MATCH_TOL
    sc.reset_copies()
    rep = Report()
    lodix = LodIndex(sc)
    dffs, lods = ipl_expand(sc, recs)
    target = norm(target) if target else ''
    picked = norm(picked) if picked else ''
    if not dry_run:
        sc.split_copies(dffs)

    groups = {}
    for d in dffs:
        own = '' if (dry_run and sc.is_copy(d)) else ipl_linked_file(d)
        path = target or own or picked
        if not path or not os.path.isfile(path):
            rep.msg('WARNING', "«%s»: no IPL file" % d.name)
            continue
        if own == path:
            groups.setdefault(path, []).append((d, ipl_anchor(d), None, 'dff'))
        else:
            e = ipl_entry(sc, d)
            a = Anchor(d.get('model_id', 0), e.model_name, (e.pos_x, e.pos_y, e.pos_z), None)
            groups.setdefault(path, []).append((d, a, MATCH_TOL, 'dff'))
    if lods:
        linked = [o for o in sc.linked_models()
                  if sc.model_type(o)[0] == 'DFF' and not sc.is_copy(o)]
        sel = {d.handle for d in dffs}
        for lod in lods:
            if game in ('III', 'VC'):
                owner = _lod_owner_at(sc, lod, dffs + linked, MATCH_TOL)
                owners = [owner] if owner is not None else []
            elif any(lodix.partner(d) is lod for d in dffs):
                continue
            else:
                owners = lodix.owners(lod, linked)
            if not owners:
                rep.msg('WARNING', "«%s»: LOD without a main model — select the main model"
                        % lod.name)
            for d in owners:
                if d.handle in sel:
                    continue
                path = target or ipl_linked_file(d)
                if path and os.path.isfile(path):
                    groups.setdefault(path, []).append((d, ipl_anchor(d), None, 'lod'))
                else:
                    rep.msg('WARNING', "«%s»: no IPL file" % d.name)

    for path, items in groups.items():
        doc = _load_ipl(path, rep)
        if doc is None:
            continue
        ed = doc.editor(game=file_game(doc, game))
        _reserve_others(sc, ed, path, [it[0] for it in items])
        results = []
        for obj, anchor, tol, kind in items:
            if kind == 'lod':
                results.append((obj, kind, ed.detach_lod(obj, anchor)))
            elif tol is None:
                results.append((obj, kind, ed.remove(obj, anchor)))
            else:
                results.append((obj, kind, ed.remove(obj, anchor, tol=tol)))
        if not _commit(ed, path, rep, dry_run):
            continue
        n_rm = sum(1 for _o, k, r in results if k == 'dff' and r.removed)
        n_link = sum(1 for _o, k, r in results if k == 'lod' and r._row is not None)
        n_lod = sum(int(r.lod_removed or 0) for _o, _k, r in results)
        if n_rm:
            rep.plan(path, 'remove %d placement(s)' % n_rm)
        if n_link:
            rep.plan(path, 'remove LOD link of %d placement(s)' % n_link)
        if n_lod:
            rep.plan(path, 'remove %d LOD row(s)' % n_lod)
        for obj, kind, r in results:
            if kind == 'dff' and r.removed:
                rep.add('removed')
                if not dry_run and ipl_linked_file(obj) == path:
                    clear_ipl(obj)
            if r.lod_removed:
                rep.add('lod_removed')
            if kind == 'lod' and not dry_run and r._row is not None:
                obj.put({'lod_index': -1})
    return rep


# ── IPL: чтение (Sync / Restore / Check) ─────────────────────────────

class IplCache:
    def __init__(self, rep):
        self.rep = rep
        self.docs = {}

    def get(self, path):
        key = norm(path)
        if key not in self.docs:
            self.docs[key] = _load_ipl(key, self.rep) if os.path.isfile(key) else None
        return self.docs[key]


def ipl_locate(sc, r, cache, claimed):
    from inu_gta_core.mapsync import RELINK_TOL
    path = ipl_linked_file(r)
    if not path or sc.is_copy(r):
        return '', -1
    doc = cache.get(path)
    if doc is None:
        return path, -1
    ex = claimed.setdefault(path, set())
    a = ipl_anchor(r)
    i = doc.find(a, exclude=ex)
    if i < 0:
        i = doc.find(a, exclude=ex, tol=RELINK_TOL)
    if i >= 0:
        ex.add(i)
    return path, i


def ipl_pull(sc, recs, files, *, move=True, far=None, clear_lost=False):
    """Связать / обновить модели по строкам IPL (ipl_pull INU).

    Связанные — своя строка в своём IPL по якорю (move — узел встаёт на
    неё). Несвязанные — ближайшая свободная строка своей модели в files в
    пределах 0.5 м; far: 'nearest' — на любом расстоянии (Restore coords);
    'unique' — единственная свободная строка модели в пределах 2 м (Check;
    в Blender — на любом расстоянии). clear_lost — связь, чья строка
    пропала, снимается."""
    from inu_gta_core.mapsync import MATCH_TOL, RELINK_TOL
    sc.reset_copies()
    rep = Report()
    cache = IplCache(rep)
    claimed = {}
    objs = [r for r in recs if sc.model_type(r)[0] == 'DFF']
    unlinked = []
    kept_files = {}
    for r in objs:
        if not r.get('ipl_uuid', '') or sc.is_copy(r):
            unlinked.append(r)
            continue
        path, i = ipl_locate(sc, r, cache, claimed)
        doc = cache.get(path) if path else None
        if i < 0 or doc is None:
            rep.add('lost')
            if clear_lost:
                if doc is None:
                    kept_files[path] = kept_files.get(path, 0) + 1
                    continue
                clear_ipl(r)
                rep.msg('WARNING', "«%s»: its row is not in %s (nor within %g m) — link removed"
                        % (r.name, _base(path), RELINK_TOL))
            else:
                unlinked.append(r)
            continue
        inst = doc.rows[i].inst
        if move:
            apply_inst(r, inst, sc=sc)
        stamp_ipl(r, path, inst, inst.lod_index)
        rep.add('synced')
    in_objs = {r.handle for r in objs}
    for o in sc.linked_models():
        if o.handle not in in_objs and not sc.is_copy(o):
            ipl_locate(sc, o, cache, claimed)
    for r in unlinked:
        mid = r.get('model_id', 0)
        if mid <= 0:
            rep.add('skipped')
            continue
        pos = sc.LS.world(r.node)[0]
        hit = None
        for mode in ('near', far):
            if mode is None or hit is not None:
                continue
            for fp in files:
                doc = cache.get(fp)
                if doc is None:
                    continue
                ex = claimed.setdefault(norm(fp), set())
                if mode == 'near':
                    i = doc.nearest(mid, pos, exclude=ex, max_dist=MATCH_TOL)
                elif mode == 'nearest':
                    i = doc.nearest(mid, pos, exclude=ex, max_dist=1e9)
                else:
                    free = [k for k in doc.rows_of(mid) if k not in ex]
                    i = free[0] if len(free) == 1 else -1
                    if i >= 0:
                        inst = doc.rows[i].inst
                        d2 = sum((a - b) ** 2 for a, b in zip(
                            pos, (inst.pos_x, inst.pos_y, inst.pos_z)))
                        if d2 > RELINK_TOL * RELINK_TOL:
                            i = -1
                if i >= 0:
                    hit = (norm(fp), doc, i)
                    ex.add(i)
                    break
        if hit is None:
            rep.add('skipped')
            continue
        path, doc, i = hit
        fresh = sc.is_copy(r)
        inst = doc.rows[i].inst
        if move:
            apply_inst(r, inst, sc=sc)
        stamp_ipl(r, path, inst, inst.lod_index, fresh=fresh)
        rep.add('linked')
    for path, count in kept_files.items():
        rep.msg('WARNING', '%s: file missing or unreadable — links of %d models kept' %
                (_base(path), count))
    sc.reset_copies()
    return rep


def refresh_links(sc, files=None):
    """Перепроверить связи со строками файлов (только чтение с диска).
    IPL: строки нет — связь снимается; строка сдвинута (≤ 2 м) — связь идёт
    за ней. IDE: id нет или он у другого имени — связь снимается. Файл,
    которого сейчас нет (редактор пересохраняет его), связи НЕ снимает
    (в Blender — снимал все). (ipl_lost, ide_lost)."""
    from inu_gta_core.mapsync import IdeDoc, RELINK_TOL
    sc.reset_copies()
    rep = Report()
    cache = IplCache(rep)
    want = None if files is None else set(files)
    ipl_by, ide_by = {}, {}
    for r in sc.recs:
        p = ipl_linked_file(r)
        if p and (want is None or p in want) and not sc.is_copy(r):
            ipl_by.setdefault(p, []).append(r)
        q = ide_linked_file(r)
        if q and (want is None or q in want):
            ide_by.setdefault(q, []).append(r)
    ipl_lost = 0
    for path, objs in ipl_by.items():
        if not os.path.isfile(path):
            continue
        doc = cache.get(path)
        if doc is None:
            continue
        taken, misses = set(), []
        for r in objs:
            i = doc.find(ipl_anchor(r), exclude=taken)
            if i >= 0:
                taken.add(i)
            else:
                misses.append(r)
        for r in misses:
            i = doc.find(ipl_anchor(r), exclude=taken, tol=RELINK_TOL)
            if i < 0:
                clear_ipl(r)
                ipl_lost += 1
                continue
            taken.add(i)
            inst = doc.rows[i].inst
            stamp_ipl(r, path, inst, inst.lod_index)
    ide_lost = 0
    for path, objs in ide_by.items():
        if not os.path.isfile(path):
            continue
        try:
            doc = IdeDoc.load(path)
        except OSError:
            continue
        for r in objs:
            mid = r.get('ide_last_model_id', 0) or r.get('model_id', 0)
            row = doc.by_id(mid)
            name = r.get('ide_last_name', '').lower()
            if row is None or (name and row.name.lower() != name):
                clear_ide(r)
                ide_lost += 1
    sc.reset_copies()
    return ipl_lost, ide_lost


# ── IDE ──────────────────────────────────────────────────────────────

def ide_entry(sc, r, dff=None):
    """Строка IDE из узла (_ide_entry_from_obj INU). LOD: имя LOD-модели,
    id — свой или id модели + 1, TXD и дистанция — из его модели (dff)."""
    from inu_gta_core.ide import IdeObject
    mt, base = sc.model_type(r)
    name = sc.model_name(r)
    txd = (r.get('txd_name', '') or '').strip() or name
    if mt == 'LOD':
        dd = r.get('lod_draw_distance', DEFAULT_LOD_DD)
    else:
        dd = r.get('draw_distance', DEFAULT_DD)
    e = IdeObject(model_id=r.get('model_id', 0), model_name=name, txd_name=txd,
                  draw_distance=dd, flags=r.get('ide_flags', 0))
    if mt == 'LOD':
        e.model_name = lod_model_name(r, base, hd=sc.model_name(dff) if dff is not None else '', sc=sc)
        e.model_id = lod_model_id(r, dff)
        dff_txd = (dff.get('txd_name', '') or '').strip() if dff is not None else ''
        own_txd = (r.get('txd_name', '') or '').strip()
        # свой TXD LOD-а первым (у ванильных LOD он свой; Blender писал TXD модели
        # поверх — LOD в игре терял текстуры), затем TXD модели, затем имя
        e.txd_name = own_txd or dff_txd or (sc.model_name(dff) if dff is not None else base)
        if dff is not None:
            e.draw_distance = dff.get('lod_draw_distance', DEFAULT_LOD_DD)
    return e


def lod_owner(sc, lodix, lod):
    """Модель LOD-меша в сцене (первая по handle) или None."""
    owners = lodix.owners(lod, [o for o in sc.models() if sc.model_type(o)[0] == 'DFF'])
    return min(owners, key=lambda o: o.handle) if owners else None


def ide_entries(sc, recs, rep):
    """Выделение → [(rec, IdeObject, модель LOD-а или None)]: модели и их
    LOD-партнёры, по одной записи на узел. LOD, выделенный без модели,
    берёт дистанцию из своей модели в сцене (в Blender — свою, а с моделью —
    её: статус «изменено» зависел от выделения)."""
    lodix = LodIndex(sc)
    ordered, dff_of_lod = [], {}
    for r in recs:
        mt = sc.model_type(r)[0]
        if mt == 'COL':
            continue
        ordered.append(r)
        if mt == 'DFF':
            lod = lodix.partner(r)
            if lod is not None:
                dff_of_lod.setdefault(lod.handle, r)
                ordered.append(lod)
    out, seen = [], set()
    for r in ordered:
        if r.handle in seen:
            continue
        seen.add(r.handle)
        dff = None
        if sc.model_type(r)[0] == 'LOD':
            dff = dff_of_lod.get(r.handle) or lod_owner(sc, lodix, r)
        e = ide_entry(sc, r, dff)
        if e.model_id <= 0:
            rep.msg('ERROR', "«%s»: Model ID = 0 — not written" % r.name)
            continue
        if dff is not None:
            note = lod_name_note(r, e.model_name, sc.model_name(dff), sc=sc)
            if note:
                rep.msg('WARNING', note)
            from .. import settings
            if settings.get('game', 'SA') in ('III', 'VC'):
                if e.draw_distance <= 300:
                    rep.msg('WARNING', '«%s»: LOD distance must exceed 300 for III/VC pairing' % r.name)
                own, hd_own = ide_linked_file(r), ide_linked_file(dff)
                if settings.get('game', 'SA') == 'VC' and own and hd_own and own != hd_own:
                    rep.msg('WARNING', '«%s»: LOD and model are in different IDE files — VC will not pair them' % r.name)
        out.append((r, e, dff))
    return out


def ide_write(sc, recs, *, picked='', game='SA', dry_run=False):
    """Add / обновить определения моделей (+ LOD). picked — IDE бокса;
    запись в другом IDE вызывает предупреждение и остаётся в исходном файле.
    Без picked — каждая в свою IDE (или IDE своей модели)."""
    from inu_gta_core.mapsync import IdeDoc
    rep = Report()
    picked = norm(picked) if picked else ''
    groups, moved = {}, {}
    for r, e, parent in ide_entries(sc, recs, rep):
        own = ide_linked_file(r)
        path = picked or own or (ide_linked_file(parent) if parent is not None else '')
        if not path:
            rep.msg('ERROR', "«%s»: has no IDE of its own — pick a file in the IDE box" % r.name)
            continue
        for other in _known_ides(sc.recs, game):
            if norm(other) == norm(path):
                continue
            by_name, _tails = _ide_names(other)
            names = {e.model_name.casefold()}
            if norm(other) == norm(own):
                last = r.get('ide_last_name', '')
                if last and r.get('ide_last_model_id', 0) == e.model_id:
                    names.add(last.casefold())
            if any(by_name.get(nm) for nm in names):
                rep.msg('WARNING', '«%s»: model already exists in another IDE (%s)' %
                        (e.model_name, other))
        groups.setdefault(path, []).append((r, e))
    written = set()
    for path, items in groups.items():
        try:
            doc = IdeDoc.load(path)
        except OSError as ex:
            rep.msg('ERROR', "%s: %s" % (_base(path), ex))
            continue
        ed = doc.editor(game=game)
        results = []
        for r, e in items:
            same = ide_linked_file(r) == path
            results.append(ed.write(r, e, anchor_id=r.get('ide_last_model_id', 0) if same else 0,
                                    anchor_name=r.get('ide_last_name', '') if same else ''))
            rep.plan(path, 'add/update %s' % e.model_name)
        if not _commit(ed, path, rep, dry_run):
            continue
        for res in results:
            rep.add(res.action)
            if res.action == 'conflict':
                continue
            written.add(res.tag.handle)
            if not dry_run:
                stamp_ide(res.tag, path, res.entry)
                if res.tag.get('model_id', 0) <= 0:
                    res.tag.put({'model_id': int(res.entry.model_id)})
    return rep


def ide_remove(sc, recs, *, picked='', target='', game='SA', dry_run=False):
    from inu_gta_core.mapsync import IdeDoc
    rep = Report()
    target = norm(target) if target else ''
    picked = norm(picked) if picked else ''
    entries = [(r, e) for r, e, _p in ide_entries(sc, recs, Report())]
    removing = {int(e.model_id) for _r, e in entries}
    groups = {}
    for r, e in entries:
        path = target or ide_linked_file(r) or picked
        if not path or not os.path.isfile(path):
            rep.msg('WARNING', "«%s»: no IDE file" % r.name)
            continue
        groups.setdefault(path, []).append((r, e))
    sel = {r.handle for r, _e in entries}
    users = {}
    for o in sc.linked_models():
        mid = o.get('model_id', 0)
        if mid in removing and o.handle not in sel:
            users[mid] = users.get(mid, 0) + 1
    for mid, n in sorted(users.items()):
        rep.msg('WARNING', "ID %d is still placed in IPL by %d objects" % (mid, n))
    for path, items in groups.items():
        try:
            doc = IdeDoc.load(path)
        except OSError as ex:
            rep.msg('ERROR', "%s: %s" % (_base(path), ex))
            continue
        ed = doc.editor(game=game)
        done = []
        for r, e in items:
            same = ide_linked_file(r) == path
            ok = ed.remove(r, int(e.model_id), e.model_name,
                           anchor_name=r.get('ide_last_name', '') if same else '')
            done.append((r, ok))
        n_rm = sum(1 for _r, ok in done if ok)
        if n_rm:
            rep.plan(path, 'remove %d definition(s)' % n_rm)
        if not _commit(ed, path, rep, dry_run):
            continue
        for r, ok in done:
            if ok:
                rep.add('removed')
                if not dry_run:
                    clear_ide(r)
    return rep


def ide_sync_from_file(sc, recs, ide_files):
    """IDE → узлы: дистанция, TXD, флаги, Model ID (ide_sync_from_file INU).

    Сначала своя связанная IDE модели. Иначе — все ide_files; имя найдено
    в нескольких IDE с разными id — не связывается (сообщение). Смена Model
    ID — строка в отчёте. LOD сопоставляется только со строкой LOD."""
    from inu_gta_core.ide import read_ide
    from inu_gta_core.mapsync.ide_match import build_index, match_ide_row
    rep = Report()
    parsed, own_indices, kept = {}, {}, {}

    def load(fp):
        fp = norm(fp)
        if fp not in parsed:
            try:
                ide = read_ide(fp)
                parsed[fp] = list(ide.objects) + list(ide.anims)
            except Exception:
                parsed[fp] = None
        return parsed[fp]

    paths = list(dict.fromkeys(norm(fp) for fp in ide_files if fp))
    index = build_index((fp, load(fp)) for fp in paths)
    linked = skipped = 0
    for r in recs:
        mt = sc.model_type(r)[0]
        if mt == 'COL':
            continue
        is_lod = mt == 'LOD'
        mid = r.get('model_id', 0)
        cname = sc.model_name(r).lower()
        own = ide_linked_file(r)
        own_index = None
        unreadable = False
        if own:
            rows = load(own)
            unreadable = rows is None
            if rows is not None:
                own_index = own_indices.setdefault(own, build_index([(own, rows)]))
        hit, ambiguous = match_ide_row(own_index, index, cname,
                                      r.get('ide_last_name', ''),
                                      r.get('ide_last_model_id', 0), mid, is_lod)
        if unreadable and (hit is None or int(hit[0].model_id) != mid):
            kept[own] = kept.get(own, 0) + 1
            skipped += 1
            continue
        if hit is None:
            skipped += 1
            if ambiguous == 'id':
                rep.msg('WARNING', '«%s»: ID %d is in several IDEs under different names — not linked' %
                        (r.name, mid))
            elif ambiguous:
                rep.msg('WARNING', '«%s»: found in several IDE with different IDs — not linked' % r.name)
            continue
        e, fp = hit
        eid = int(e.model_id)
        d = {}
        if eid > 0 and eid != mid:
            d['model_id'] = eid
            if mid > 0:
                rep.msg('INFO', "«%s»: Model ID %d → %d (from %s)" % (r.name, mid, eid, _base(fp)))
        dd = float(e.draw_distance)
        d['lod_draw_distance' if is_lod else 'draw_distance'] = dd
        d['txd_name'] = str(e.txd_name or '')
        d['ide_flags'] = int(e.flags)
        r.put(d)
        stamp_ide(r, fp, e)
        linked += 1
    for fp, count in kept.items():
        rep.msg('WARNING', '%s: file missing or unreadable — links of %d models kept' %
                (_base(fp), count))
    return linked, skipped, rep


def ide_verify_links(sc, recs, picked=''):
    """Model ID есть в IDE модели (своей, иначе picked); нет — связь
    снимается. (есть, нет, без ID, снято)."""
    from inu_gta_core.ide import read_ide
    cache = {}

    def ids_for(fp):
        if not fp or not os.path.isfile(fp):
            return None
        key = norm(fp)
        if key not in cache:
            try:
                ide = read_ide(fp)
                cache[key] = {int(e.model_id) for e in list(ide.objects) + list(ide.anims)}
            except Exception:                          # noqa: BLE001
                cache[key] = None
        return cache[key]

    present = missing = zero = cleared = 0
    for r in recs:
        if sc.model_type(r)[0] == 'COL':
            continue
        mid = r.get('model_id', 0)
        if mid <= 0:
            zero += 1
            continue
        ids = ids_for(r.get('ide_target_file', '') or picked)
        if ids is None:
            continue
        if mid in ids:
            present += 1
        else:
            missing += 1
            if r.get('ide_linked', False):
                r.put({'ide_linked': False})
                cleared += 1
    return present, missing, zero, cleared


# ── статусы выбранной модели (окно Map IO) ───────────────────────────

def ide_status(sc, r):
    """(текст, ok) строки IDE: сравнение с тем, что уйдёт в файл."""
    mid = r.get('model_id', 0)
    linked = r.get('ide_linked', False)
    last_id = r.get('ide_last_model_id', 0)
    mt = sc.model_type(r)[0]
    if mt == 'LOD':
        lodix = LodIndex(sc)
        dff = lod_owner(sc, lodix, r)
        e = ide_entry(sc, r, dff)
        mid = e.model_id
    else:
        e = ide_entry(sc, r)
    if linked and last_id > 0 and mid != last_id:
        return "Not in IDE — Model ID changed (was %d)" % last_id, False
    if not linked or mid <= 0:
        return "Not in IDE", None
    drift = []
    if abs(e.draw_distance - r.get('ide_last_draw_distance', e.draw_distance)) > 1e-3:
        drift.append("DrawDist")
    if e.txd_name != r.get('ide_last_txd_name', ''):
        drift.append("TXD")
    if e.flags != r.get('ide_last_flags', 0):
        drift.append("Flags")
    if drift:
        return "In IDE, changed: " + ", ".join(drift), False
    return "In IDE (%s)" % (_base(r.get('ide_target_file', '')) or "?"), True


def ipl_status(sc, r):
    """(текст, ok) строки IPL."""
    if not r.get('ipl_uuid', ''):
        if sc.model_type(r)[0] == 'LOD':
            return "LOD — written together with its model", None
        return "Not in IPL", None
    if sc.is_copy(r):
        return "Copy — will be added as a new instance", None
    a = ipl_anchor(r)
    e = ipl_entry(sc, r)
    moved = any(abs(x - y) > POS_EPS for x, y in zip((e.pos_x, e.pos_y, e.pos_z), a.pos))
    if a.rot is not None:
        q = (e.rot_x, e.rot_y, e.rot_z, e.rot_w)
        moved = moved or any(abs(x - y) > ROT_EPS for x, y in zip(q, a.rot))
    if moved:
        return "In IPL, coordinates drifted", False
    return "In IPL (%s)" % (_base(r.get('ipl_target_file', '')) or "?"), True


# ── слежение за файлами (map_watch INU) ──────────────────────────────

class Watch:
    """Раз в 2 с — stat связанных файлов, раз в 10 с — список файлов из
    сцены. Изменился файл → refresh_links(только он). tick() → True, если
    связи перечитаны (окну обновить статусы)."""

    RESCAN = 10.0

    def __init__(self):
        self.files = None
        self.stats = {}
        self.last_scan = 0.0

    @staticmethod
    def _stat(p):
        try:
            st = os.stat(p)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def reset(self):
        self.files = None
        self.stats = {}

    def tick(self, now):
        from ..adapter import link_scene as LS
        if self.files is None or now - self.last_scan >= self.RESCAN:
            self.last_scan = now
            files = {norm(p) for p in LS.linked_files()}
            for p in files - set(self.stats):
                self.stats[p] = self._stat(p)
            for p in set(self.stats) - files:
                del self.stats[p]
            self.files = files
        changed = []
        for p in self.files:
            st = self._stat(p)
            if st is None:
                continue          # файла сейчас нет — ждём, связи не трогаем
            if st != self.stats.get(p):
                self.stats[p] = st
                changed.append(p)
        if not changed:
            return False
        refresh_links(Scene(), changed)
        return True


# ── Export: новые файлы (ide_export / ipl_export INU) ────────────────

def export_ide_file(sc, recs, path, game):
    """Новый .ide из моделей (одна строка на модель; LOD — своя)."""
    from inu_gta_core.ide import IdeFile, write_ide
    rep = Report()
    ide = IdeFile()
    seen = set()
    for r, e, _p in ide_entries(sc, recs, rep):
        key = e.model_name.lower()
        if key in seen:
            continue
        seen.add(key)
        ide.objects.append(e)
    if not ide.objects:
        return 0, rep
    write_ide(path, ide, game=game)
    return len(ide.objects), rep


def export_ipl_file(sc, recs, path, game, binary=False):
    """Новый .ipl из расстановок моделей; lod_index — по lod_object в этом
    же файле; одинаковые (id, позиция до мм) — одна строка (как INU)."""
    from inu_gta_core.ipl import IplFile, write_ipl
    rep = Report()
    ipl = IplFile()
    per, seen = [], set()
    lodix = LodIndex(sc)
    for r in recs:
        mt, base = sc.model_type(r)
        if mt == 'COL':
            continue
        e = ipl_entry(sc, r)
        if mt == 'LOD':
            dff = lod_owner(sc, lodix, r)
            e.model_name = lod_model_name(r, base, hd=sc.model_name(dff) if dff is not None else '', game=game, sc=sc)
            e.model_id = lod_model_id(r, dff)
        if e.model_id <= 0:
            rep.msg('ERROR', "«%s»: Model ID = 0 — not written" % r.name)
            continue
        key = (e.model_id, round(e.pos_x, 3), round(e.pos_y, 3), round(e.pos_z, 3))
        if key in seen:
            continue
        seen.add(key)
        e.lod_index = -1
        ipl.instances.append(e)
        per.append(r)
    idx = {r.handle: i for i, r in enumerate(per)}
    for i, r in enumerate(per):
        h = r.get('lod_object', 0)
        if h:
            ipl.instances[i].lod_index = idx.get(h, -1)
        else:
            raw = r.get('lod_index', -1)
            if 0 <= raw < len(per):
                ipl.instances[i].lod_index = raw
    if not ipl.instances:
        return 0, rep
    write_ipl(path, ipl, binary=binary, game=game)
    return len(ipl.instances), rep
