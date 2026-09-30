# INU Tools (Max) — кнопки вкладки Export окна Map IO: связь моделей с
# IDE / IPL (порт операторов ops/ide_ipl.py Blender-версии INU; логика —
# ops/map_link.py).
#
# Каждая функция возвращает (уровень, текст отчёта) или None — пользователь
# отменил в окне подтверждения. confirm(заголовок, строки, вопрос) → bool
# даёт окно (panel). Как ConfirmOnProblems INU: сначала пробный прогон без
# записи; есть проблемы — список и вопрос. Корзины Unlink IDE+IPL / Unlink
# from IDE / Remove from IPL удаляют строки из файлов — подтверждение ВСЕГДА
# (решение пользователя; в Blender вложенный вызов обходил диалог).
#
# Изменения сцены (свойства связи, перемещение узлов) — одним шагом отмены;
# сами файлы Ctrl+Z не возвращает (при первой записи за сеанс рядом
# кладётся <файл>.bak — ядро mapsync).

import os

from .. import settings
from . import map_link as ML


def _game():
    return settings.get('game', 'SA') or 'SA'


def _selected():
    from ..adapter import selection
    return selection.selected_meshes()


def _undo(label):
    from ..adapter.selection import undo_block
    return undo_block(label)


def _no_sel():
    return 'ERROR', "Select mesh objects"


def _with_confirm(run, confirm, title, prefix, always=False):
    """Пробный прогон → (при проблемах / always) подтверждение → запись."""
    dry = run(True)
    probs = [t for _lvl, t in dry.problems()]
    lines = []
    if always:
        for path, what in sorted(dry.touch.items()):
            rm = [w for w in what if w.startswith('remove')]
            if rm:
                lines.append("%s: %s" % (os.path.basename(path), "; ".join(rm)))
        if not lines and not probs:
            always = False           # удалять нечего — сразу отчёт
    if probs or always:
        shown = probs[:12] + (["… %d more" % (len(probs) - 12)] if len(probs) > 12 else [])
        if always:
            text = (["Rows will be DELETED from the files:"] + lines
                    + ([""] + ["Problems:"] + shown if shown else []))
            question = "Delete these rows?"
        else:
            text = ["Problems found before writing:"] + shown
            question = "Everything else will be written. Continue?"
        if confirm is not None and not confirm(title, text, question):
            return None
    with _undo("INU: " + title):
        rep = run(False)
    return ML.report_text(prefix, rep)


# ── боксы IDE / IPL: Add / Del (выбранный файл) ──────────────────────

def upsert_ide(confirm=None):
    nodes = _selected()
    if not nodes:
        return _no_sel()
    picked = settings.get('ide_path', '') or ''

    def run(dry):
        sc = ML.Scene()
        rep = ML.ide_write(sc, sc.pick(nodes), picked=picked, game=_game(), dry_run=dry)
        if picked and not picked.lower().endswith('.ide'):
            rep.msg('WARNING', "IDE path is not a .ide file — check the IDE box")
        _id_warnings(sc, sc.pick(nodes), rep)
        return rep
    return _with_confirm(run, confirm, "Add to IDE", "IDE")


def upsert_ipl(confirm=None):
    nodes = _selected()
    if not nodes:
        return _no_sel()
    picked = settings.get('ipl_path', '') or ''

    def run(dry):
        sc = ML.Scene()
        rep = ML.ipl_write(sc, sc.pick(nodes), picked=picked, game=_game(), dry_run=dry)
        if picked and not picked.lower().endswith('.ipl'):
            rep.msg('WARNING', "IPL path is not a .ipl file — check the IPL box")
        _id_warnings(sc, sc.pick(nodes), rep)
        return rep
    return _with_confirm(run, confirm, "Add to IPL", "IPL")


def remove_ide(confirm=None):
    nodes = _selected()
    if not nodes:
        return _no_sel()
    target = settings.get('ide_path', '') or ''

    def run(dry):
        sc = ML.Scene()
        return ML.ide_remove(sc, sc.pick(nodes), target=target, game=_game(), dry_run=dry)
    return _with_confirm(run, confirm, "Remove from IDE", "IDE")


def remove_ipl(confirm=None):
    nodes = _selected()
    if not nodes:
        return _no_sel()
    target = settings.get('ipl_path', '') or ''

    def run(dry):
        sc = ML.Scene()
        return ML.ipl_remove(sc, sc.pick(nodes), target=target, game=_game(), dry_run=dry)
    return _with_confirm(run, confirm, "Remove from IPL", "IPL")


def _id_warnings(sc, recs, rep):
    """LOD, который возьмёт id модели + 1, а этот id уже у другого меша
    (_validate_model_ids INU)."""
    by_id = {}
    for r in sc.recs:
        m = r.get('model_id', 0)
        if m > 0:
            by_id.setdefault(m, []).append(r)
    lodix = ML.LodIndex(sc)
    for d in recs:
        if sc.model_type(d)[0] != 'DFF':
            continue
        lod = lodix.partner(d)
        did = d.get('model_id', 0)
        if lod is None or lod.get('model_id', 0) > 0 or did <= 0:
            continue
        owners = [o for o in by_id.get(did + 1, []) if o is not lod and o is not d]
        if owners:
            rep.msg('WARNING', "LOD uses an already-occupied ID: %s → id %d (%s)"
                    % (lod.name, did + 1, owners[0].name))


# ── Export: новый файл ───────────────────────────────────────────────

def export_ide(path):
    nodes = _selected()
    if not nodes:
        return _no_sel()
    if not path.lower().endswith('.ide'):
        path += '.ide'
    sc = ML.Scene()
    n, rep = ML.export_ide_file(sc, sc.pick(nodes), path, _game())
    if not n:
        return 'WARNING', "\n".join(["Nothing to export"] + [t for _l, t in rep.messages])
    lines = ["Exported IDE: %s (%d)" % (path, n)] + [t for _l, t in rep.messages]
    return ('WARNING' if rep.problems() else 'INFO'), "\n".join(lines)


def export_ipl(path, binary=False):
    nodes = _selected()
    if not nodes:
        return _no_sel()
    if not path.lower().endswith('.ipl'):
        path += '.ipl'
    sc = ML.Scene()
    n, rep = ML.export_ipl_file(sc, sc.pick(nodes), path, _game(), binary=binary)
    if not n:
        return 'WARNING', "\n".join(["Nothing to export"] + [t for _l, t in rep.messages])
    lines = ["Exported IPL: %s (%d)" % (path, n)] + [t for _l, t in rep.messages]
    return ('WARNING' if rep.problems() else 'INFO'), "\n".join(lines)


# ── файлы для Sync / Restore / Check ─────────────────────────────────

_WALK = {}       # папка → (mtime, [файлы .ipl], [подпапки])


def _walk_ipls(root):
    """Все .ipl под root (рекурсивно). Содержимое папки перечитывается,
    только если сменилось её время изменения (кэш на сеанс)."""
    out, stack = [], [root]
    while stack:
        d = stack.pop()
        try:
            mt = os.stat(d).st_mtime_ns
        except OSError:
            continue
        hit = _WALK.get(d)
        if hit is None or hit[0] != mt:
            files, subs = [], []
            try:
                for e in os.scandir(d):
                    if e.is_dir(follow_symlinks=False):
                        subs.append(e.path)
                    elif e.name.lower().endswith('.ipl'):
                        files.append(e.path)
            except OSError:
                pass
            hit = (mt, files, subs)
            _WALK[d] = hit
        out += hit[1]
        stack += hit[2]
    return out


def _dedupe(raw):
    valid, missing, seen = [], [], set()
    for p in raw:
        k = os.path.normcase(os.path.normpath(p))
        if k in seen:
            continue
        seen.add(k)
        (valid if os.path.isfile(p) else missing).append(p)
    return valid, missing


def ipl_targets():
    """Список «IPL to export» + все .ipl папки игры; выбранный в боксе — если
    больше ничего нет (_ipl_sync_targets INU). (есть, нет)."""
    raw = [p for p in (settings.get('ipl_sync_list', []) or []) if p]
    root = settings.get('game_root', '') or ''
    if root and os.path.isdir(root):
        raw += _walk_ipls(root)
    if not raw:
        single = settings.get('ipl_path', '') or ''
        if single:
            raw.append(single)
    return _dedupe(raw)


def ide_targets():
    """Список «IDE to export» + IDE игры (gta.dat, иначе все .ide папки);
    выбранный в боксе — если больше ничего нет."""
    raw = [p for p in (settings.get('ide_sync_list', []) or []) if p]
    root = settings.get('game_root', '') or ''
    if root and os.path.isdir(root):
        from inu_gta_core.gta_dat import list_ide_files
        raw += list_ide_files(root)
    if not raw:
        single = settings.get('ide_path', '') or ''
        if single:
            raw.append(single)
    return _dedupe(raw)


def _sel_or_all(sc):
    nodes = _selected()
    return sc.pick(nodes) if nodes else sc.models()


# ── строки выбранной модели и списки ─────────────────────────────────

def ipl_sync_from_file():
    """Sync from IPL: модели встают на свои строки; несвязанные — к строке
    своей модели в 0.5 м. Пустое выделение — вся сцена."""
    valid, missing = ipl_targets()
    sc = ML.Scene()
    with _undo("INU: Sync from IPL"):
        rep = ML.ipl_pull(sc, _sel_or_all(sc), valid, move=True)
    if missing:
        rep.msg('WARNING', "files not found: %d" % len(missing))
    return ML.report_text("Sync IPL", rep)


def ipl_restore_coords():
    nodes = _selected()
    if not nodes:
        return 'ERROR', "Select a model"
    valid, _missing = ipl_targets()
    sc = ML.Scene()
    with _undo("INU: Restore coords from IPL"):
        rep = ML.ipl_pull(sc, sc.pick(nodes), valid, move=True, far='nearest')
    return ML.report_text("Coords from IPL", rep)


def ipl_sync_export(confirm=None):
    nodes = _selected()
    if not nodes:
        return _no_sel()

    def run(dry):
        sc = ML.Scene()
        return ML.ipl_write(sc, sc.pick(nodes), game=_game(), dry_run=dry)
    return _with_confirm(run, confirm, "Export placements to their IPLs", "IPL")


def ide_sync_export(confirm=None):
    nodes = _selected()
    if not nodes:
        return _no_sel()

    def run(dry):
        sc = ML.Scene()
        return ML.ide_write(sc, sc.pick(nodes), game=_game(), dry_run=dry)
    return _with_confirm(run, confirm, "Export models to their IDEs", "IDE")


def ipl_remove_link(confirm=None):
    nodes = _selected()
    if not nodes:
        return _no_sel()
    picked = settings.get('ipl_path', '') or ''

    def run(dry):
        sc = ML.Scene()
        return ML.ipl_remove(sc, sc.pick(nodes), picked=picked, game=_game(), dry_run=dry)
    return _with_confirm(run, confirm, "Remove from IPL", "IPL", always=True)


def ide_remove_link(confirm=None):
    nodes = _selected()
    if not nodes:
        return _no_sel()
    picked = settings.get('ide_path', '') or ''

    def run(dry):
        sc = ML.Scene()
        return ML.ide_remove(sc, sc.pick(nodes), picked=picked, game=_game(), dry_run=dry)
    return _with_confirm(run, confirm, "Unlink from IDE", "IDE", always=True)


def link_unlink(confirm=None):
    """Корзина у имени модели: удалить из IDE и IPL (оба файла)."""
    nodes = _selected()
    if not nodes:
        return _no_sel()
    ide_p = settings.get('ide_path', '') or ''
    ipl_p = settings.get('ipl_path', '') or ''

    def run(dry):
        sc = ML.Scene()
        recs = sc.pick(nodes)
        rep = ML.ide_remove(sc, recs, picked=ide_p, game=_game(), dry_run=dry)
        rep.merge(ML.ipl_remove(sc, recs, picked=ipl_p, game=_game(), dry_run=dry))
        return rep
    return _with_confirm(run, confirm, "Unlink IDE+IPL", "IDE+IPL", always=True)


def ide_sync_from_file():
    files, _missing = ide_targets()
    if not files:
        return 'ERROR', "No IDE: pick a file or the game folder"
    sc = ML.Scene()
    with _undo("INU: Sync from IDE"):
        linked, skipped, rep = ML.ide_sync_from_file(sc, _sel_or_all(sc), files)
    lines = ["Sync IDE: linked %d, skipped %d (%d IDE)" % (linked, skipped, len(files))]
    lines += [t for _l, t in rep.messages]
    return ('WARNING' if rep.problems() else 'INFO'), "\n".join(lines)


def link_verify():
    """Check: IDE (Model ID есть в IDE модели) + IPL (строка по якорю;
    потерянная — связь снимается; несвязанные — строка рядом)."""
    sc = ML.Scene()
    recs = _sel_or_all(sc)
    with _undo("INU: Verify IDE+IPL Links"):
        present, missing, zero, cleared = ML.ide_verify_links(
            sc, recs, settings.get('ide_path', '') or '')
        valid, _missing = ipl_targets()
        rep = ML.ipl_pull(sc, recs, valid, move=False, far='unique', clear_lost=True)
    lines = ["IDE Verify: present %d, missing %d, cleared %d, no ID %d"
             % (present, missing, cleared, zero)]
    level, text = ML.report_text("IPL check", rep)
    return ('WARNING' if (missing or level != 'INFO') else 'INFO'), "\n".join(lines + [text])
