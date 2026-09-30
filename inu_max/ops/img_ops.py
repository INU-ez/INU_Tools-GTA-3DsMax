# INU Tools (Max) — строка IMG вкладки Export окна Map IO: Export to IMG,
# Remove from IMG, Verify IMG, Rebuild IMG (порт export_to_img /
# remove_from_img / verify_img_link / rebuild_img из ops/img_ops.py
# Blender-версии INU). Архивы — ядро inu_gta_core.img (VER1 III/VC .dir+.img,
# VER2 SA — формат берётся из самого файла).
#
# Исправлено против Blender (решения пользователя, 2026-09-28):
# - TXD сливается с TXD архива (одноимённые текстуры заменяются, чужие
#   остаются) — в Blender общий TXD заменялся текстурами выделенных, и
#   остальные модели этого TXD теряли текстуры;
# - COL — в свою библиотеку: .col архива, где уже есть модель с этим именем,
#   меняется только её запись (остальные модели — байт в байт); нет нигде —
#   отдельный <модель>.col; сферы / боксы — в системе модели;
# - заглушки LOD (копия модели) и пустой COL — выключены по умолчанию;
# - Remove: DFF + LOD модели, TXD — только если его больше никто не
#   использует (IDE игры из default.dat + gta*.dat / бокса / списка, все
#   секции с TXD и txdp; модели сцены), COL — свой .col
#   или запись в библиотеке; перед удалением — список и вопрос;
# - модели из разных архивов — каждая в свой, без своего — в выбранный;
# - Verify — архивы игры в порядке загрузки (gta3.img, gta_int.img, IMG из
#   gta.dat, затем прочие; папки кэша INU пропускаются), первый + где ещё;
#   LOD ищется под своим именем (в Blender — под именем модели);
# - формат архива — из файла (в Blender — из игры сцены: SA-архив при сцене
#   III/VC тихо портился);
# - после Export ставится, после Remove снимается «In IMG» (img_target_file);
# - Rebuild IMG — и кнопкой в строке IMG (с подтверждением).
# Бэкап архива не делается (решение пользователя; как в Blender).

import os
import re
import struct

from .. import settings
from . import map_link as ML

MAX_NAME = 23                         # движок обнуляет 24-й байт имени записи
_CACHES = ('img_tex_names.json', 'img_col_names.json')
_COL_MAGIC = (b'COLL', b'COL2', b'COL3', b'COL4')


def _img():
    from inu_gta_core import img
    return img


def _undo(label):
    from ..adapter.selection import undo_block
    return undo_block(label)


def _selected():
    from ..adapter import selection
    return selection.selected_meshes()


def _base(p):
    return os.path.basename(p) or p


def _norm(p):
    return os.path.normcase(os.path.abspath(p)) if p else ''


# ── архивы ───────────────────────────────────────────────────────────

def game_archives():
    """.img папки игры в порядке загрузки (map_import._game_imgs)."""
    root = settings.get('game_root', '') or ''
    if not root or not os.path.isdir(root):
        return []
    from .map_import import _game_imgs
    return _game_imgs(root)


def archive_choices():
    """Архивы для окна экспорта: IMG из настроек, найденные Find IMG, игры."""
    out, seen = [], set()
    for p in ([settings.get('img_path', '') or ''] + list(settings.get('found_imgs', []) or [])
              + game_archives()):
        k = _norm(p)
        if p and k not in seen and os.path.isfile(p):
            seen.add(k)
            out.append(p)
    return out


_DIRS = {}


def _names_in(path):
    """{имя записи (нижний регистр)} архива (кэш по размеру и времени)."""
    I = _img()
    try:
        st = os.stat(path)
        key = (st.st_size, st.st_mtime_ns)
        if I.detect_img_version(path) == I.IMG_VERSION_1:
            d = os.stat(os.path.splitext(path)[0] + '.dir')
            key += (d.st_size, d.st_mtime_ns)
    except OSError:
        return None
    hit = _DIRS.get(path)
    if hit and hit[0] == key:
        return hit[1]
    try:
        names = {e.name.lower() for e in I.read_directory(path)}
    except Exception as e:                             # noqa: BLE001
        print("[INU img] %s: %r" % (path, e))
        return None
    _DIRS[path] = (key, names)
    return names


def _drop_caches(path):
    from .. import cache
    cache.disk_drop(_CACHES, path)
    _DIRS.pop(path, None)


# ── COL-библиотеки: записи моделей как есть, по байтам ───────────────

def col_chunks(data):
    """[(начало, конец, имя модели, model_id)] записей COL подряд."""
    out, pos = [], 0
    while pos + 32 <= len(data) and data[pos:pos + 4] in _COL_MAGIC:
        size = struct.unpack_from('<I', data, pos + 4)[0]
        end = pos + 8 + size
        if end > len(data):
            break
        name = data[pos + 8:pos + 30].split(b'\x00', 1)[0].decode('ascii', 'replace')
        mid = struct.unpack_from('<H', data, pos + 30)[0]
        out.append((pos, end, name, mid))
        pos = end
    return out


def col_splice(data, name, make):
    """Записи модели name → make(model_id) (None — удалить). (данные,
    сколько записей, сколько моделей осталось). Прочие записи и хвост —
    байт в байт."""
    chunks = col_chunks(data)
    out, n, left, prev = [], 0, 0, 0
    for s, e, nm, mid in chunks:
        out.append(data[prev:s])
        if nm.lower() == name.lower():
            n += 1
            new = make(mid)
            if new:
                out.append(new)
                left += 1
        else:
            out.append(data[s:e])
            left += 1
        prev = e
    out.append(data[prev:])
    return b''.join(out), n, left


def _col_index(reader):
    """{имя модели (нижний): [имя записи .col]} архива (по заголовкам)."""
    idx = {}
    for e in reader.entries:
        if not e.name.lower().endswith('.col') or not e.size:
            continue
        data = reader.read_entry(e)
        for _s, _e, nm, _mid in col_chunks(data):
            lst = idx.setdefault(nm.lower(), [])
            if e.name not in lst:
                lst.append(e.name)
    return idx


# ── модели выделения ─────────────────────────────────────────────────

_PRIM_RE = r'^%s_(sphere|box)_\d+$'


def _col_nodes(sc, base):
    """(меши коллизии, примитивы) модели base: <base>_COL / <base>_sha,
    <base>_sphere_N / <base>_box_N (как импорт коллизии)."""
    from ..adapter import scene_read as sr
    low = base.lower()
    meshes, prims = [], []
    pr = re.compile(_PRIM_RE % re.escape(low), re.I)
    for r in sc.recs:
        nm = r.name.lower()
        if nm in (low + '_col', low + '_sha'):
            meshes.append(r.node)
        elif pr.match(nm) and sr.col_prim(r.node):
            prims.append(r.node)
    return meshes, prims


def plan():
    """Модели выделения для окна экспорта: [dict]. Выделенный LOD — вместе
    со своей моделью (без DFF, если она не выделена)."""
    sc = ML.Scene()
    lodix = ML.LodIndex(sc)
    items, by_dff = [], {}
    recs = [r for r in sc.pick(_selected()) if sc.model_type(r)[0] != 'COL']

    def item_for(dff, lod, want_dff):
        key = dff.handle if dff is not None else ('lod', lod.handle)
        it = by_dff.get(key)
        if it is not None:
            it['inc_dff'] = it['inc_dff'] or want_dff
            return it
        base = sc.model_name(dff) if dff is not None else ''
        lod_base = sc.model_type(lod)[1] if lod is not None else ''
        meshes, prims = _col_nodes(sc, base) if base else ([], [])
        txd = ((dff.get('txd_name', '') or '').strip() or base) if dff is not None else ''
        lod_txd = ((lod.get('txd_name', '') or '').strip() if lod is not None else '') or txd
        own = dff.get('img_target_file', '') if dff is not None else \
            lod.get('img_target_file', '')
        it = dict(dff=dff, lod=lod, name=base or ML.lod_model_name(lod, lod_base),
                  lod_name=ML.lod_model_name(lod, lod_base) if lod is not None else '',
                  col_meshes=meshes, col_prims=prims, txd=txd or lod_txd,
                  lod_txd=lod_txd, own=own if own and os.path.isfile(own) else '',
                  inc_dff=want_dff and dff is not None, inc_lod=lod is not None,
                  inc_col=bool(meshes or prims), stub_lod=False, stub_col=False,
                  inc_txd=True)
        by_dff[key] = it
        items.append(it)
        return it

    for r in recs:
        mt = sc.model_type(r)[0]
        if mt == 'LOD':
            owner = ML.lod_owner(sc, lodix, r)
            if owner is not None:
                it = item_for(owner, r, False)
                it['lod'] = r
                it['inc_lod'] = True
            else:
                item_for(None, r, False)
        else:
            item_for(r, lodix.partner(r), True)
    return items


# ── Export to IMG ────────────────────────────────────────────────────

def _check_name(fname, bad):
    try:
        raw = fname.encode('ascii')
    except UnicodeEncodeError:
        bad.append(fname)
        return
    if not raw or len(raw) > MAX_NAME:
        bad.append(fname)


def export_to_img(items, default_archive, rebuild_after=False):
    """Записать модели items (из plan(), с правками окна) в архивы."""
    from . import dff_export as DE
    from ..adapter import fx as fx_ad, scene_read as sr
    I = _img()
    opts = DE._opts()
    warnings, errors, lines = [], [], []
    groups = {}
    for it in items:
        if not (it['inc_dff'] or it['inc_lod'] or it['inc_col'] or it['stub_lod']
                or it['stub_col']):
            continue
        arch = it['own'] or default_archive
        if not arch or not os.path.isfile(arch):
            errors.append("«%s»: no IMG archive — choose one in the window" % it['name'])
            continue
        groups.setdefault(arch, []).append(it)
    if not groups:
        return 'ERROR', "\n".join(errors or ["Nothing to export"])
    # имена записей: движок читает 23 символа (24-й — ноль)
    bad = []
    for arch, its in groups.items():
        for it in its:
            if it['inc_dff']:
                _check_name(it['name'] + '.dff', bad)
            if it['inc_lod'] or it['stub_lod']:
                _check_name((it['lod_name'] or 'LOD' + it['name']) + '.dff', bad)
            if it['inc_col'] or it['stub_col']:
                _check_name(it['name'] + '.col', bad)
            if it['inc_txd']:
                _check_name(it['txd'] + '.txd', bad)
                _check_name(it['lod_txd'] + '.txd', bad)
    if bad:
        return 'ERROR', ("IMG entry name longer than %d characters (or not ASCII) — the "
                         "game won't find it: %s. Shorten the model / TXD name."
                         % (MAX_NAME, ", ".join(sorted(set(bad))[:8])))
    written_recs = {}
    with sr.full_result():
        for arch, its in groups.items():
            try:
                res = _export_archive(arch, its, opts, warnings, DE, fx_ad, I)
            except PermissionError:
                errors.append("%s: the .img file is locked — close the game (or other "
                              "program) and try again" % _base(arch))
                continue
            except Exception as e:                     # noqa: BLE001
                import traceback
                traceback.print_exc()
                errors.append("%s: %s" % (_base(arch), e))
                continue
            _drop_caches(arch)
            lines.append(res['line'])
            for r in res['recs']:
                written_recs[r.handle] = (r, arch)
            if rebuild_after:
                try:
                    st = I.rebuild_img(arch)
                    lines.append("  rebuild: %d entries, %.1f MB freed"
                                 % (st['entries'], st['saved'] / 1048576.0))
                    _drop_caches(arch)
                except Exception as e:                 # noqa: BLE001
                    errors.append("%s: rebuild failed — %s" % (_base(arch), e))
    if written_recs:
        with _undo("INU: Export to IMG"):
            for r, arch in written_recs.values():
                r.put({'img_target_file': arch})
    level = 'ERROR' if errors and not lines else ('WARNING' if errors or warnings else 'INFO')
    return level, "\n".join(lines + ["Error: " + e for e in errors] + warnings[:30])


def _export_archive(arch, its, opts, warnings, DE, fx_ad, I):
    """Одна запись в архив: сначала всё собрать (DFF / LOD / COL / TXD,
    TXD и COL-библиотеки — слиянием с данными архива), затем одна сессия
    ImgWriter. {'line', 'recs'}."""
    files, recs = [], []                      # [(имя записи, байты)]
    n = dict(dff=0, lod=0, col=0, lib=0, txd=0)
    with I.ImgReader(arch) as rd:
        col_idx = _col_index(rd) if any(it['inc_col'] or it['stub_col'] for it in its) else {}
        libs = {}                             # запись .col → байты (с правками)
        txd_objs = {}                         # имя TXD → [узлы]
        for it in its:
            dff, lod = it['dff'], it['lod']
            if it['inc_dff'] and dff is not None:
                nodes = DE._nodes_for([(dff.node, None)], opts['pipeline'])
                fx = DE._fx_entries([c for c in dff.node.children if fx_ad.is_2dfx(c)],
                                    dff.node)
                files.append((it['name'] + '.dff',
                              DE.dff_bytes(it['name'], nodes, fx, opts, warnings)))
                n['dff'] += 1
                recs.append(dff)
            lod_node = lod.node if (it['inc_lod'] and lod is not None) else (
                dff.node if (it['stub_lod'] and lod is None and dff is not None) else None)
            if lod_node is not None:
                lname = it['lod_name'] or 'LOD' + it['name']
                nodes = DE._nodes_for([(lod_node, None)], opts['pipeline'])
                files.append((lname + '.dff', DE.dff_bytes(lname, nodes, [], opts, warnings)))
                n['lod'] += 1
                if lod is not None:
                    recs.append(lod)
            if (it['inc_col'] or it['stub_col']) and dff is not None:
                empty = not (it['inc_col'] and (it['col_meshes'] or it['col_prims']))
                model = DE._col_model(it['name'], opts['col_version'],
                                      [] if empty else it['col_meshes'],
                                      [] if empty else it['col_prims'], opts, warnings,
                                      empty=empty, bounds_objs=[dff.node], ref_node=dff.node)
                from inu_gta_core.col import write_col

                def make(mid, model=model):
                    model.model_id = mid
                    return write_col([model], target_game=opts['game'])
                where = col_idx.get(it['name'].lower(), [])
                if where:
                    for ename in where:
                        data = libs.get(ename)
                        if data is None:
                            data = rd.read(ename) or b''
                        data, cnt, _left = col_splice(data, it['name'], make)
                        libs[ename] = data
                    n['lib'] += 1
                else:
                    files.append((it['name'] + '.col', make(0)))
                    n['col'] += 1
            if it['inc_txd']:
                if it['inc_dff'] and dff is not None:
                    txd_objs.setdefault(it['txd'], []).append(dff.node)
                if lod_node is not None:
                    txd_objs.setdefault(it['lod_txd'], []).append(lod_node)
        txd_notes = []
        for tname, objs in txd_objs.items():
            base = rd.read(tname + '.txd')
            data, note = DE.txd_data(tname + '.txd', objs, opts, warnings, base)
            if data is not None:
                files.append((tname + '.txd', data))
                n['txd'] += 1
                txd_notes.append("%s.txd (%s)" % (tname, note))
        files += list(libs.items())
    status = {}
    with I.ImgWriter(arch) as w:               # формат — из самого архива
        for fname, data in files:
            status[fname] = w.add(fname, data)
    added = sum(1 for s in status.values() if s == 'added')
    line = ("%s: DFF %d, LOD %d, COL %d%s, TXD %d — added %d, replaced %d"
            % (_base(arch), n['dff'], n['lod'], n['col'],
               (" + %d in libraries (%s)" % (n['lib'], ", ".join(sorted(libs))))
               if n['lib'] else "", n['txd'], added, len(status) - added))
    if txd_notes:
        line += "\n  " + "; ".join(txd_notes)
    return {'line': line, 'recs': recs}


# ── Remove from IMG ──────────────────────────────────────────────────

def _txd_ide_files():
    """IDE для проверки TXD: список + IDE игры (default.dat + gta*.dat, как
    From Game ID-менеджера) + IDE бокса — всегда, не только когда пусто."""
    from inu_gta_core.gta_dat import parse_gta_dat, resolve_paths
    from .map_link_ops import ide_targets, _dedupe
    from .id_manager_ops import _DATS
    raw = list(ide_targets()[0])
    root = settings.get('game_root', '') or ''
    if root and os.path.isdir(root):
        for dat in _DATS:
            p = os.path.join(root, 'data', dat)
            if not os.path.isfile(p):
                continue
            try:
                raw += resolve_paths(root, parse_gta_dat(p)).ide_paths
            except Exception as e:                     # noqa: BLE001
                print("[INU] %s: %r" % (dat, e))
    raw.append(settings.get('ide_path', '') or '')
    return _dedupe([p for p in raw if p])[0]


def _txd_users(exclude_models):
    """{имя TXD (нижний): {модели}} — кто использует TXD: IDE игры / бокса /
    списка (все секции с TXD + родитель из txdp) и модели сцены (кроме
    exclude_models)."""
    from inu_gta_core.ide import read_ide
    users = {}
    ex = {m.lower() for m in exclude_models}
    for p in _txd_ide_files():
        try:
            ide = read_ide(p)
        except Exception:                              # noqa: BLE001
            continue
        for sec in (ide.objects, ide.anims, ide.cars, ide.peds, ide.weaps, ide.hiers):
            for e in sec:
                t = (getattr(e, 'txd_name', '') or '').lower()
                m = (getattr(e, 'model_name', '') or '').lower()
                if t and m not in ex:
                    users.setdefault(t, set()).add(m)
        for e in ide.txdps:                            # txdp: ребёнок, родитель
            c = (e.txd_name or '').lower()
            par = (e.parent_txd_name or '').lower()
            if c and par:                              # ребёнок грузит родителя
                users.setdefault(par, set()).add('txdp ' + c)
    sc = ML.Scene()
    for r in sc.models():
        m = sc.model_name(r).lower()
        t = (r.get('txd_name', '') or '').lower()
        if t and m not in ex:
            users.setdefault(t, set()).add(m)
    return users


def _lod_entry(it):
    """Имя LOD-модели пункта: из сцены или (LOD не в сцене) lod_ide_name."""
    return it['lod_name'] or (it['dff'].get('lod_ide_name', '')
                              if it['dff'] is not None else '')


def _remove_plan():
    """{архив: {'entries': [имя записи], 'libs': {запись .col: имя модели},
    'recs': [Rec], 'kept_txd': [(txd, пример модели)]}} и сообщения."""
    notes = []
    items = plan()
    by_arch = {}
    for it in items:
        arch = it['own']
        if not arch:
            notes.append("«%s»: not in an IMG (press Verify)" % it['name'])
            continue
        by_arch.setdefault(arch, []).append(it)
    if not by_arch:
        return {}, notes
    removing = {it['name'] for its in by_arch.values() for it in its} | \
        {_lod_entry(it) for its in by_arch.values() for it in its} - {''}
    users = _txd_users(removing)
    I = _img()
    out = {}
    for arch, its in by_arch.items():
        names = _names_in(arch) or set()
        ent, libs, recs, kept = [], {}, [], []
        with I.ImgReader(arch) as rd:
            col_idx = _col_index(rd)
        for it in its:
            if it['dff'] is not None:
                recs.append(it['dff'])
                if it['name'].lower() + '.dff' in names:
                    ent.append(it['name'] + '.dff')
            if it['lod'] is not None:
                recs.append(it['lod'])
            lname = _lod_entry(it)
            if lname and lname.lower() + '.dff' in names:
                ent.append(lname + '.dff')
            for t in {it['txd'], it['lod_txd']} - {''}:
                if t.lower() + '.txd' not in names or t + '.txd' in ent:
                    continue
                others = users.get(t.lower())
                if others:
                    kept.append((t, sorted(others)[0], len(others)))
                else:
                    ent.append(t + '.txd')
            for ename in col_idx.get(it['name'].lower(), []):
                libs.setdefault(ename, []).append(it['name'])
        out[arch] = dict(entries=ent, libs=libs, recs=recs, kept_txd=kept)
    return out, notes


def remove_from_img(confirm=None):
    if not _selected():
        return 'ERROR', "Select mesh objects"
    I = _img()
    todo, notes = _remove_plan()
    if not todo:
        return 'WARNING', "\n".join(notes or ["Nothing to remove"])
    lines = []
    for arch, t in todo.items():
        parts = list(t['entries']) + ["%s (from %s)" % (", ".join(ms), e)
                                      for e, ms in t['libs'].items()]
        lines.append("%s: %s" % (_base(arch), ", ".join(parts) or "nothing"))
        for tx, ex, cnt in t['kept_txd']:
            lines.append("  %s.txd kept — used by %s%s" % (tx, ex, (" +%d" % (cnt - 1))
                                                           if cnt > 1 else ""))
    if not any(t['entries'] or t['libs'] for t in todo.values()):
        return 'WARNING', "\n".join(["Files not found in IMG"] + lines + notes)
    if confirm is not None and not confirm(
            "Remove from IMG", ["Will be removed from the archives:"] + lines + notes,
            "Remove?"):
        return None
    done, errors = [], []
    for arch, t in todo.items():
        try:
            n = 0
            for ename in t['entries']:
                if I.remove_file(arch, ename):
                    n += 1
            if t['libs']:
                with I.ImgReader(arch) as rd:
                    datas = {e: rd.read(e) or b'' for e in t['libs']}
                gone = []
                with I.ImgWriter(arch) as w:
                    for ename, models in t['libs'].items():
                        data = datas[ename]
                        left = 1
                        for m in models:
                            data, _c, left = col_splice(data, m, lambda _mid: None)
                        if left:
                            w.add(ename, data)
                        else:
                            gone.append(ename)
                        n += len(models)
                for ename in gone:          # библиотека опустела — запись долой
                    I.remove_file(arch, ename)
            done.append("%s: removed %d" % (_base(arch), n))
            _drop_caches(arch)
        except PermissionError:
            errors.append("%s: the .img file is locked — close the game" % _base(arch))
            continue
        except Exception as e:                         # noqa: BLE001
            errors.append("%s: %s" % (_base(arch), e))
            continue
        with _undo("INU: Remove from IMG"):
            for r in t['recs']:
                r.put({'img_target_file': ''})
    level = 'ERROR' if errors and not done else ('WARNING' if errors else 'INFO')
    return level, "\n".join(done + lines + ["Error: " + e for e in errors] + notes)


# ── Verify IMG ───────────────────────────────────────────────────────

def verify_img_link():
    """В каком архиве модель: архивы игры в порядке загрузки (+ IMG из
    настроек и найденные Find IMG); первый — «In IMG», где ещё — в отчёт."""
    nodes = _selected()
    if not nodes:
        return 'ERROR', "Select mesh objects"
    order = []
    seen = set()
    for p in game_archives() + [settings.get('img_path', '') or ''] + \
            list(settings.get('found_imgs', []) or []):
        k = _norm(p)
        if p and k not in seen and os.path.isfile(p):
            seen.add(k)
            order.append(p)
    if not order:
        return 'ERROR', "No IMG: set the game folder (or find IMG on the Import tab)"
    dirs, failed = [], []
    for p in order:
        names = _names_in(p)
        if names is None:
            failed.append(_base(p))
        else:
            dirs.append((p, names))
    sc = ML.Scene()
    lodix = ML.LodIndex(sc)
    recs = [r for r in sc.pick(nodes) if sc.model_type(r)[0] != 'COL']
    found = missing = 0
    notes = []
    with _undo("INU: Verify IMG"):
        for r in recs:
            mt, base = sc.model_type(r)
            name = (ML.lod_model_name(r, base) if mt == 'LOD' else sc.model_name(r)) + '.dff'
            hits = [p for p, names in dirs if name.lower() in names]
            if hits:
                r.put({'img_target_file': hits[0]})
                found += 1
                if len(hits) > 1:
                    notes.append("%s: in %s (used), also in %s"
                                 % (name, _base(hits[0]), ", ".join(_base(h) for h in hits[1:])))
            else:
                missing += 1
                if not failed:
                    r.put({'img_target_file': ''})
            lod = lodix.partner(r) if mt == 'DFF' else None
            if lod is not None and lod not in recs:
                lname = ML.lod_model_name(lod, sc.model_type(lod)[1]) + '.dff'
                lh = [p for p, names in dirs if lname.lower() in names]
                if lh:
                    lod.put({'img_target_file': lh[0]})
    lines = ["IMG check: found %d, not in archives %d (%d archives)" % (found, missing, len(dirs))]
    if failed:
        lines.append("Not read (links of missing models kept): %s" % ", ".join(failed))
    lines += notes[:10]
    return ('WARNING' if failed else 'INFO'), "\n".join(lines)


# ── Rebuild IMG ──────────────────────────────────────────────────────

def rebuild_target():
    """Архив для Rebuild: «In IMG» активной модели, иначе IMG из настроек."""
    sc = ML.Scene()
    for n in _selected():
        r = sc.rec(n)
        if r is not None:
            p = sc.main_of(r).get('img_target_file', '')
            if p and os.path.isfile(p):
                return p
    p = settings.get('img_path', '') or ''
    return p if os.path.isfile(p) else ''


def rebuild_img(confirm=None):
    I = _img()
    arch = rebuild_target()
    if not arch:
        return 'ERROR', "No IMG: select a model that is in an IMG (Verify) first"
    n = len(_names_in(arch) or ())
    if confirm is not None and not confirm(
            "Rebuild IMG", ["Compact %s (%d entries): dead space left by replaced entries is "
                            "removed; entries and their order stay." % (_base(arch), n)],
            "Rebuild?"):
        return None
    try:
        st = I.rebuild_img(arch)
    except PermissionError:
        return 'ERROR', "%s: the .img file is locked — close the game" % _base(arch)
    _drop_caches(arch)
    return 'INFO', "IMG rebuilt: %s — %d entries, %.1f MB freed" % (
        _base(arch), st['entries'], st['saved'] / 1048576.0)
