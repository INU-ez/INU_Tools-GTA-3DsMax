# INU Tools (Max) — строка IMG вкладки Export окна Map IO: Export to IMG,
# Remove from IMG, Verify IMG, Rebuild IMG (порт export_to_img /
# remove_from_img / verify_img_link / rebuild_img из ops/img_ops.py
# Blender-версии INU). Архивы — ядро inu_gta_core.img (VER1 III/VC .dir+.img,
# VER2 SA — формат берётся из самого файла).
#
# Правила IMG (решения пользователя и паритет с Blender, 01.10.2026):
# - TXD сливается с TXD архива (одноимённые текстуры заменяются, чужие
#   остаются);
# - COL — в свою библиотеку: .col архива, где уже есть модель с этим именем,
#   меняется только её запись (остальные модели — байт в байт); нет нигде —
#   отдельный <модель>.col; сферы / боксы — в системе модели;
# - заглушки LOD (копия модели) и пустой COL — выключены по умолчанию;
# - Remove: DFF и только явно выделенный LOD, TXD — если его больше никто не
#   использует (IDE игры из default.dat + gta*.dat / бокса / списка, все
#   секции с TXD и txdp; модели сцены), COL — свой .col
#   или запись в библиотеке; перед удалением — список и вопрос;
# - модели из разных архивов — каждая в свой, без своего — в выбранный;
# - Verify — архивы игры в порядке загрузки (gta3.img, gta_int.img, IMG из
#   gta.dat, затем прочие; папки кэша INU пропускаются), первый + где ещё;
#   LOD ищется под своим именем;
# - формат архива проверяется против игры экспорта до сборки ресурсов;
# - после Export ставится, после Remove снимается «In IMG» (img_target_file);
# - Rebuild IMG — и кнопкой в строке IMG (с подтверждением).
# Бэкап архива не делается (решение пользователя; как в Blender).

import os
import re

from inu_gta_core.col_library import col_chunks, col_splice

from .. import settings
from . import map_link as ML

MAX_NAME = 23                         # движок обнуляет 24-й байт имени записи
_CACHES = ('img_tex_names.json', 'img_col_names.json')


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
        lod_txd = (((lod.get('txd_name', '') or '').strip() if lod is not None else '')
                   or txd or (ML.lod_model_name(lod, lod_base) if lod is not None else ''))
        own = dff.get('img_target_file', '') if dff is not None else \
            lod.get('img_target_file', '')
        it = dict(dff=dff, lod=lod, name=base or ML.lod_model_name(lod, lod_base),
                  lod_name=ML.lod_model_name(lod, lod_base, hd=base, sc=sc) if lod is not None else '',
                  col_meshes=meshes, col_prims=prims, txd=txd or lod_txd,
                  lod_txd=lod_txd, own=own,
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
    if not raw or fname.startswith('.') or len(raw) > MAX_NAME:
        bad.append(fname)


def _prepare_archive(arch, game, I):
    """Validate the destination before building DFF/COL/TXD resources."""
    version = I.IMG_VERSION_2 if game == 'SA' else I.IMG_VERSION_1
    dir_path = os.path.splitext(arch)[0] + '.dir'
    if (os.path.getsize(arch) == 0 and not os.path.exists(dir_path)
            and not os.path.exists(arch + '.dir')):
        I.create_img(arch, version=version)
    I.read_directory(arch)
    actual = I.detect_img_version(arch)
    if actual != version:
        raise ValueError("archive is VER%d but the export game is %s — "
                         "switch the game or pick another archive" % (actual, game))
    # Probe both files of VER1 before the potentially expensive TXD build.
    for path in ([arch, dir_path] if actual == I.IMG_VERSION_1 else [arch]):
        with open(path, 'r+b'):
            pass


def export_to_img(items, default_archive, rebuild_after=False):
    """Записать модели items (из plan(), с правками окна) в архивы."""
    from . import dff_export as DE
    from ..adapter import fx as fx_ad, scene_read as sr
    I = _img()
    opts = DE._opts()
    warnings, errors, lines = [], [], []
    for it in items:
        if it['inc_lod'] and it['lod'] is not None and it['dff'] is not None:
            note = ML.lod_name_note(it['lod'], it['lod_name'], it['name'], game=opts['game'])
            if note:
                warnings.append(note)
    from inu_gta_core.img_routing import route_groups, lod_routes
    active = [dict(it) for it in items if any(it[k] for k in
              ('inc_dff', 'inc_lod', 'inc_col', 'stub_lod', 'stub_col'))]
    routes, missing = route_groups({i: it['own'] for i, it in enumerate(active)},
                                    default_archive)
    errors += ["«%s»: no IMG archive — choose one in the window" % active[i]['name']
               for i in missing]
    main_arch = {i: a for a, indices in routes.items() for i in indices}
    lod_arch, missing_lod = lod_routes(
        {i: (it['lod'].get('img_target_file', '') if it['lod'] is not None else '')
         for i, it in enumerate(active) if it['inc_lod'] or it['stub_lod']}, main_arch)
    errors += ["«%s»: explicit LOD IMG is missing — LOD not written" % active[i]['name']
               for i in missing_lod]
    groups, txd_sources, col_sources = {}, {}, []
    for i, it in enumerate(active):
        arch = main_arch.get(i)
        if arch is None:
            continue
        main = dict(it, inc_lod=False, stub_lod=False, inc_txd=False)
        if it['inc_dff']:
            groups.setdefault(arch, []).append(main)
        else:
            groups.setdefault(arch, [])
        if it['inc_col'] or it['stub_col']:
            col_sources.append((arch, dict(main, inc_dff=False)))
        main['inc_col'] = main['stub_col'] = False
        if it['inc_txd'] and it['inc_dff'] and it['dff'] is not None:
            txd_sources.setdefault(it['txd'].casefold(), []).append(
                (it['txd'], arch, it['dff'].node, False))
        la = lod_arch.get(i)
        if la:
            groups.setdefault(la, []).append(dict(it, inc_dff=False, inc_col=False,
                                                 stub_col=False, inc_txd=False))
            node = (it['lod'].node if it['lod'] is not None else
                    it['dff'].node if it['dff'] is not None else None)
            if it['inc_txd'] and node is not None:
                txd_sources.setdefault(it['lod_txd'].casefold(), []).append(
                    (it['lod_txd'], la, node, True))
    if not groups:
        return 'ERROR', "\n".join(errors or ["Nothing to export"])
    # имена записей: движок читает 23 символа (24-й — ноль)
    bad = []
    for its in [active]:
        for it in its:
            if it['inc_dff']:
                _check_name(it['name'] + '.dff', bad)
            if it['inc_lod'] or it['stub_lod']:
                _check_name((it['lod_name'] or ML.new_lod_name(it['name'], it['name'], game=opts['game'])) + '.dff', bad)
            if it['inc_col'] or it['stub_col']:
                _check_name(it['name'] + '.col', bad)
            if it['inc_txd']:
                if it['inc_dff'] and it['dff'] is not None:
                    _check_name(it['txd'] + '.txd', bad)
                if it['inc_lod'] or it['stub_lod']:
                    _check_name(it['lod_txd'] + '.txd', bad)
    if bad:
        return 'ERROR', ("IMG entry name empty, longer than %d characters or not ASCII — the "
                         "game won't find it: %s. Shorten the model / TXD name."
                         % (MAX_NAME, ", ".join(sorted(set(bad))[:8])))
    prepared = {}
    for arch, its in groups.items():
        try:
            _prepare_archive(arch, opts['game'], I)
        except PermissionError:
            errors.append("%s: the .img file is locked — close the game (or other "
                          "program) and try again" % _base(arch))
        except (ValueError, OSError) as e:
            errors.append("%s: %s" % (_base(arch), e))
        except Exception as e:                         # noqa: BLE001
            errors.append("%s: %s" % (_base(arch), e))
        else:
            prepared[arch] = its
    if not prepared:
        return 'ERROR', "\n".join("Error: " + e for e in errors)
    from inu_gta_core.img_routing import shared_targets
    names, indices = {}, {}
    for arch in groups:
        try:
            with I.ImgReader(arch) as reader:
                names[arch] = {e.name.casefold() for e in reader.entries}
                indices[arch] = _col_index(reader) if col_sources else {}
        except Exception:
            names[arch] = None
            indices[arch] = None
    txd_jobs = {}
    for sources in txd_sources.values():
        tname = sources[0][0]
        users = sorted(dict.fromkeys(a for _, a, _, _ in sources),
                       key=lambda a: a not in prepared)
        entry = (tname + '.txd').casefold()
        targets = shared_targets(users, lambda a: names[a] is None or entry in names[a],
                                 required=[a for _, a, _, required in sources if required])
        # A complete shared dictionary requires every selected source to be readable.
        if any(a not in prepared for a in users):
            errors.append('%s: not written — a source archive was rejected' % entry)
            continue
        objs = list({id(node): node for _, _, node, _ in sources}.values())
        for arch in targets:
            if arch in prepared:
                txd_jobs.setdefault(arch, {})[tname] = objs
        if len(users) > 1:
            lines.append('%s: complete shared TXD → %s' %
                         (entry, ', '.join(_base(a) for a in targets)))
    for own, it in col_sources:
        if own not in prepared:
            continue
        base = it['name'].casefold()
        targets = [a for a in groups if indices[a] is None or
                   indices[a].get(base) or base + '.col' in (names[a] or ())]
        targets = targets or [own]
        for arch in targets:
            if arch in prepared:
                prepared[arch].append(it)
            else:
                errors.append('%s.col: not written in rejected archive %s' %
                              (base, _base(arch)))
    written_recs = {}
    with sr.full_result():
        for arch, its in prepared.items():
            try:
                res = _export_archive(arch, its, opts, warnings, DE, fx_ad, I,
                                      txd_jobs.get(arch, {}))
            except PermissionError:
                errors.append("%s: the .img file is locked — close the game (or other "
                              "program) and try again" % _base(arch))
                continue
            except (ValueError, OSError) as e:
                errors.append("%s: %s" % (_base(arch), e))
                continue
            except Exception as e:                     # noqa: BLE001
                import traceback
                traceback.print_exc()
                errors.append("%s: %s" % (_base(arch), e))
                continue
            _drop_caches(arch)
            lines.append(res['line'])
            for r in res['recs']:
                record, destinations = written_recs.setdefault(r.handle, (r, set()))
                destinations.add(arch)
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
            for r, destinations in written_recs.values():
                # A shared LOD without its own archive must keep routing to all
                # owners on the next export, rather than acquiring the last IMG.
                if len(destinations) == 1:
                    r.put({'img_target_file': next(iter(destinations))})
    level = 'ERROR' if errors else ('WARNING' if warnings else 'INFO')
    return level, "\n".join(lines + ["Error: " + e for e in errors] + warnings[:30])


def _export_archive(arch, its, opts, warnings, DE, fx_ad, I, txd_jobs=None):
    """Одна запись в архив: сначала всё собрать (DFF / LOD / COL / TXD,
    TXD и COL-библиотеки — слиянием с данными архива), затем одна сессия
    ImgWriter. {'line', 'recs'}."""
    files, recs = [], []                      # [(имя записи, байты)]
    n = dict(dff=0, lod=0, col=0, lib=0, txd=0)
    with I.ImgReader(arch) as rd:
        names = {e.name.lower(): e.name for e in rd.entries}
        col_idx = _col_index(rd) if any(it['inc_col'] or it['stub_col'] for it in its) else {}
        libs = {}                             # запись .col → байты (с правками)
        txd_objs = dict(txd_jobs or {})       # complete shared source buckets
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
                lname = it['lod_name'] or ML.new_lod_name(it['name'], it['name'], game=opts['game'])
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
                fallback = names.get((it['name'] + '.col').lower())
                if not where and fallback:
                    where = [fallback]
                if where:
                    for ename in where:
                        data = libs.get(ename)
                        if data is None:
                            data = rd.read(ename) or b''
                        data, cnt, _left = col_splice(data, it['name'], make)
                        if not cnt:
                            data += make(0)
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
            if data is None:
                raise ValueError('%s.txd: texture dictionary could not be built' % tname)
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
    """Export lists, startup IDEs of the game and the IDE box."""
    from inu_gta_core.gta_dat import game_ide_paths
    from .map_link_ops import _dedupe
    raw = list(settings.get('ide_sync_list', []) or [])
    root = settings.get('game_root', '') or ''
    if root and os.path.isdir(root):
        raw += game_ide_paths(root)[0]
    raw.append(settings.get('ide_path', '') or '')
    return _dedupe([p for p in raw if p])[0]


def _remove_scene(sc):
    """Resource names and LOD owners across the whole scene, including copies."""
    lodix = ML.LodIndex(sc)
    names, kinds, dffs, lods, owners, by_base = {}, {}, [], [], {}, {}
    own_ides = []
    for r in sc.recs:
        own = ML.ide_linked_file(r)
        if own:
            own_ides.append(own)
        mt, base = sc.model_type(r)
        name = sc.model_name(r)
        if mt == 'LOD':
            name = ML.lod_model_name(r, name)
            lods.append(r)
        elif mt == 'DFF':
            dffs.append(r)
            by_base.setdefault(name.lower(), r)
        names[r.handle], kinds[r.handle] = name, mt.lower()
    for d in dffs:
        lod = lodix.partner(d)
        if lod is not None:
            owners.setdefault(names[lod.handle].lower(), d)
        stored = (d.get('lod_ide_name', '') or '').strip()
        if stored:
            owners.setdefault(stored.lower(), d)
    for lod in lods:
        name = names[lod.handle].lower()
        if name not in owners:
            base = sc.model_type(lod)[1].lower()
            owner = by_base.get(base)
            if owner is None and settings.get('game', 'SA') in ('III', 'VC'):
                owner = next((d for d in dffs if len(names[d.handle]) > 3
                              and names[d.handle][3:].lower() == name[3:]), None)
            if owner is not None:
                owners[name] = owner
    return names, kinds, owners, by_base, own_ides, lodix


def _txd_users(sc, names, kinds, owners, own_ides):
    """IDE and scene users; the core planner excludes only real removals."""
    from inu_gta_core.img_remove import scene_txd_users, txd_users
    users, bad = txd_users(_txd_ide_files() + own_ides)
    dffs, lods = [], []
    for r in sc.recs:
        name = names[r.handle]
        txd = (r.get('txd_name', '') or '').strip()
        if not name:
            continue
        kind = kinds[r.handle]
        if kind == 'lod':
            owner = owners.get(name.lower())
            lods.append((name, txd, names[owner.handle] if owner is not None else ''))
        elif kind == 'dff' or (txd and r.get('type', 'OBJ').upper() not in ('COL', 'SHA')):
            dffs.append((name, txd))
    for txd, models in scene_txd_users(dffs, lods).items():
        users.setdefault(txd, set()).update(models)
    return users, bad


def _remove_plan():
    """Core removal plan plus scene records whose DFF is actually scheduled."""
    from inu_gta_core.img_remove import remove_plan
    sc = ML.Scene()
    names, kinds, owners, by_base, own_ides, lodix = _remove_scene(sc)
    selected, handles = [], set()
    for node in _selected():
        r = sc.rec(node)
        if r is None:
            continue
        # Scene.pick intentionally excludes tagged COL; removal accepts them.
        if kinds[r.handle] == 'dff':
            r = sc.main_of(r)
        if r.handle not in handles:
            handles.add(r.handle)
            selected.append(r)
    selected_lods = {names[r.handle].lower() for r in selected if kinds[r.handle] == 'lod'}
    notes, parts, arch_of, seen = [], [], {}, set()
    for r in selected:
        kind, name = kinds[r.handle], names[r.handle]
        if not name:
            continue
        extra, fallback = {}, ''
        if kind == 'dff':
            extra['txd'] = (r.get('txd_name', '') or '').strip() or name
            lod = lodix.partner(r)
            lname = names[lod.handle] if lod is not None else r.get('lod_ide_name', '')
            if lname and lname.lower() not in selected_lods:
                extra['lod'] = lname
        elif kind == 'lod':
            owner = owners.get(name.lower())
            if owner is not None:
                fallback = owner.get('img_target_file', '')
            # No own TXD: inherit the owner's TXD; never touch COL or the HD DFF.
            owner_txd = ((owner.get('txd_name', '') or '').strip() or names[owner.handle]
                         if owner is not None else '')
            extra['txd'] = (r.get('txd_name', '') or '').strip() or owner_txd or name
        else:
            owner = by_base.get(name.lower())
            fallback = owner.get('img_target_file', '') if owner is not None else ''
        raw = r.get('img_target_file', '')
        # A LOD without a usable own path falls back to its owner's archive.
        if kind == 'lod' and not (raw and os.path.isfile(raw)):
            raw = fallback
        elif not raw:
            raw = fallback
        if not raw or not os.path.isfile(raw):
            notes.append("«%s»: not in an IMG (press Verify)" % r.name)
            continue
        key = _norm(raw)
        arch = arch_of.setdefault(key, raw)
        part_key = (key, kind, name.lower())
        if part_key not in seen:
            seen.add(part_key)
            parts.append(dict(kind=kind, arch=arch, name=name, **extra))
    I = _img()
    names_by_arch, col_idx_by_arch = {}, {}
    for arch in arch_of.values():
        try:
            entry_names = {}
            for e in I.read_directory(arch):
                entry_names.setdefault(e.name.lower(), e.name)
            if any(p['arch'] == arch and p['kind'] != 'lod' for p in parts):
                with I.ImgReader(arch) as rd:
                    col_idx_by_arch[arch] = _col_index(rd)
            names_by_arch[arch] = entry_names
        except Exception as e:                         # noqa: BLE001
            notes.append("%s: %s" % (_base(arch), e))
    users = {}
    if any(p.get('txd') and (p['txd'] + '.txd').lower() in names_by_arch.get(p['arch'], {})
           for p in parts):
        users, bad = _txd_users(sc, names, kinds, owners, own_ides)
        if bad:
            notes.append("IDE not read: %s" % ', '.join(_base(p) for p in bad))
    todo = remove_plan(parts, names_by_arch, col_idx_by_arch, users)
    for arch, t in todo.items():
        for name in t['missing']:
            notes.append("«%s»: not in %s (press Verify)" % (name, _base(arch)))
        gone = {e.lower() for e in t['entries'] if e.lower().endswith('.dff')}
        t['recs'] = [r for r in sc.recs if kinds[r.handle] in ('dff', 'lod')
                     and _norm(r.get('img_target_file', '')) == _norm(arch)
                     and (names[r.handle] + '.dff').lower() in gone]
        t['rec_entries'] = {r.handle: (names[r.handle] + '.dff').lower() for r in t['recs']}
    root = settings.get('game_root', '') or ''
    from inu_gta_core.gta_dat import game_ide_paths
    if (any(e.lower().endswith('.txd') for t in todo.values() for e in t['entries'])
            and not (root and os.path.isdir(root) and game_ide_paths(root)[1])):
        notes.insert(0, "Game folder not set or startup DAT not found — TXD checked only "
                     "against the scene and IDE lists")
    return todo, list(dict.fromkeys(notes))


def remove_from_img(confirm=None):
    if not _selected():
        return 'ERROR', "Select mesh objects"
    from inu_gta_core.img_remove import remove_entries
    todo, notes = _remove_plan()
    if not todo:
        return 'WARNING', "\n".join(notes or ["Nothing to remove"])
    lines = []
    for arch, t in todo.items():
        parts = list(t['entries']) + ["%s (from %s)" % (", ".join(ms), e)
                                      for e, ms in t['libs'].items()]
        lines.append("%s: %s" % (_base(arch), ", ".join(parts) or "nothing"))
        for tx, ex, cnt in t['kept_txd']:
            lines.append("  %s kept — used by %s%s" % (tx, ex, (" +%d" % (cnt - 1))
                                                           if cnt > 1 else ""))
        for lod in t['kept_lod']:
            lines.append("  LOD «%s» kept — select the LOD to remove it" % lod)
    if not any(t['entries'] or t['libs'] for t in todo.values()):
        return 'WARNING', "\n".join(["Files not found in IMG"] + lines + notes)
    if confirm is not None and not confirm(
            "Remove from IMG", ["Will be removed from the archives:"] + lines + notes,
            "Remove?"):
        return None
    done, errors = [], []
    for arch, t in todo.items():
        changed = []
        try:
            remove_entries(arch, t['entries'], t['libs'], changed)
        except PermissionError:
            errors.append("%s: the .img file is locked — close the game" % _base(arch))
        except Exception as e:                         # noqa: BLE001
            errors.append("%s: %s" % (_base(arch), e))
        if not changed:
            continue
        n = sum(1 if isinstance(e, str) else len(e[1]) for e in changed)
        done.append("%s: removed %d" % (_base(arch), n))
        _drop_caches(arch)
        gone = {e.lower() for e in changed if isinstance(e, str)}
        with _undo("INU: Remove from IMG"):
            for r in t['recs']:
                if t['rec_entries'][r.handle] in gone:
                    r.put({'img_target_file': ''})
    level = 'ERROR' if errors and not done else ('WARNING' if errors or notes else 'INFO')
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
