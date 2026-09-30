# INU Tools (Max) — Export Map вкладки Map окна Map IO (порт map_export /
# iter_export_map Blender-версии INU): модели сцены → папка с .dff / .col /
# .txd / .ide / .ipl (по ячейкам сетки или слоям).
#
# Исправлено против Blender (решения пользователя, 2026-09-28):
# - КАЖДАЯ расстановка — своя строка IPL (Blender писал одну строку на имя
#   модели — копии молча терялись); DFF / TXD / COL / строка IDE — один раз
#   на модель (в ячейке её первой расстановки);
# - LOD — отдельный LOD<модель>.dff, своя строка IDE и свои строки IPL,
#   строки модели ссылаются на них lod_index; коллизия — в .col (Blender
#   вшивал LOD и COL в <модель>.dff);
# - модели без Model ID получают его из ID Manager (активный пресет, как
#   Assign), с шагом отмены (Blender — от 20000 без сверки с игрой);
# - файлы, которые уже есть в папке, — список и вопрос; .txd — слияние
#   (чужие текстуры остаются);
# - «Binary IPL» — пара, как в игре: <ячейка>.ipl (текст: строки LOD) +
#   <ячейка>_stream0.ipl (бинарный: модели, lod_index — в текстовый);
#   бинарный IPL игра грузит только из IMG;
# - сферы и боксы коллизии — в системе модели;
# - одинаковые строки (ID + позиция до мм) — одна (SA падает на дублях,
#   как в Blender).

import math
import os
import re

from .. import settings
from . import map_link as ML

SPLITS = (('NONE', "No split"), ('GRID', "XY grid"), ('ADAPTIVE', "Adaptive grid"),
          ('COLLECTION', "By layer"))
STREAM_NAME_MAX = 17          # IplDef.name[18] (DAT-39)


def _selected():
    from ..adapter import selection
    return selection.selected_meshes()


def _safe(name):
    return re.sub(r'[^\w.\-]+', '_', name).strip('_') or 'map'


def _collect():
    """(Scene, расстановки DFF [Rec], LOD без своей модели [Rec], область)."""
    sc = ML.Scene()
    nodes = _selected()
    recs = sc.pick(nodes) if nodes else sc.models()
    dffs, lonely = [], []
    lodix = ML.LodIndex(sc)
    for r in recs:
        mt = sc.model_type(r)[0]
        if mt == 'DFF':
            dffs.append(r)
        elif mt == 'LOD' and ML.lod_owner(sc, lodix, r) is None:
            lonely.append(r)
    return sc, dffs, lonely, ('selection' if nodes else 'scene')


def plan_info():
    """Для окна экспорта: сколько расстановок / моделей / без ID."""
    sc, dffs, lonely, scope = _collect()
    names = {sc.model_name(r).lower() for r in dffs}
    zero = {sc.model_name(r).lower() for r in dffs if r.get('model_id', 0) <= 0}
    return dict(scope=scope, placements=len(dffs), models=len(names), zero=len(zero),
                lonely=[r.name for r in lonely][:5])


# ── ячейки ───────────────────────────────────────────────────────────

def _grid_key(base, x, y, size):
    def f(v):
        c = int(math.floor(v / size))
        return ('m%d' % -c) if c < 0 else str(c)
    return "%s_x%s_y%s" % (base, f(x), f(y))


def _adaptive(base, pts, max_per, min_size):
    """Квадродерево: ячейка делится, пока в ней больше max_per расстановок и
    она больше min_size. {индекс: ключ}."""
    out = {}

    def split(ids, x0, y0, x1, y1, path):
        if len(ids) <= max_per or max(x1 - x0, y1 - y0) <= min_size:
            for i in ids:
                out[i] = "%s_q%s" % (base, path or '0')
            return
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        quads = {0: [], 1: [], 2: [], 3: []}
        for i in ids:
            x, y = pts[i]
            quads[(1 if x >= mx else 0) + (2 if y >= my else 0)].append(i)
        for q, sub in quads.items():
            if sub:
                split(sub, mx if q & 1 else x0, my if q & 2 else y0,
                      x1 if q & 1 else mx, y1 if q & 2 else my, path + str(q))
    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        side = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
        split(list(range(len(pts))), min(xs), min(ys), min(xs) + side, min(ys) + side, '')
    return out


def _cells(sc, dffs, opts):
    """[ключ ячейки] на каждую расстановку."""
    base = _safe(opts['base_name'])
    mode = opts['split']
    if mode == 'COLLECTION':
        out = []
        for r in dffs:
            try:
                out.append(_safe(str(r.node.layer.name)) or 'unsorted')
            except Exception:                          # noqa: BLE001
                out.append('unsorted')
        return out
    if mode == 'NONE' or not dffs:
        return [base] * len(dffs)
    pts = [sc.LS.world(r.node)[0][:2] for r in dffs]
    if mode == 'GRID':
        keys = [_grid_key(base, x, y, float(opts['cell_size'])) for x, y in pts]
    else:
        m = _adaptive(base, pts, int(opts['max_per_cell']), float(opts['min_cell_size']))
        keys = [m[i] for i in range(len(pts))]
    return keys if len(set(keys)) > 1 else [base] * len(dffs)


# ── экспорт ──────────────────────────────────────────────────────────

def export_map(folder, opts, confirm=None):
    """opts: base_name, dff, col, txd, ide, ipl, col_library, binary, fla,
    split, cell_size, max_per_cell, min_cell_size."""
    from . import dff_export as DE
    from .img_ops import _col_nodes
    from ..adapter import fx as fx_ad, scene_read as sr
    from ..adapter.selection import undo_block
    if not folder or not os.path.isdir(folder):
        return 'ERROR', "Pick a target folder"
    sc, dffs, lonely, _scope = _collect()
    if not dffs:
        return 'WARNING', "No DFF models to export (select them, or nothing selected = whole scene)"
    game = settings.get('game', 'SA') or 'SA'
    notes, warnings, errors = [], [], []
    if lonely:
        notes.append("LOD without its model in the scene — not exported: %s"
                     % ", ".join(r.name for r in lonely[:5]))
    # 1. Model ID моделям без ID — ID Manager (как Assign), шаг отмены
    lodix = ML.LodIndex(sc)
    need = [r for r in dffs if r.get('model_id', 0) <= 0]
    need += [l for l in (lodix.partner(r) for r in dffs) if l is not None
             and l.get('model_id', 0) <= 0]
    if need:
        from .id_manager_ops import assign_models
        with undo_block("INU: Export Map IDs"):
            done, _reused, left, warn = assign_models(sc, need)
        if done:
            notes.append("IDs from ID Manager: %d model(s)" % len(done))
        warnings += warn
        if left:
            return 'ERROR', ("No free IDs in the active preset (ID Manager) for: %s — nothing "
                             "exported" % ", ".join(left[:8]))
    # 2. модели и ячейки
    cells = _cells(sc, dffs, opts)
    models, home = {}, {}                       # имя → данные; имя → ячейка
    for r, cell in zip(dffs, cells):
        nm = sc.model_name(r)
        key = nm.lower()
        if key not in models:
            lod = lodix.partner(r)
            meshes, prims = _col_nodes(sc, nm)
            txd = (r.get('txd_name', '') or '').strip() or nm
            lod_txd = ((lod.get('txd_name', '') or '').strip() if lod is not None else '') or txd
            models[key] = dict(name=nm, dff=r, lod=lod, meshes=meshes, prims=prims, txd=txd,
                               lod_txd=lod_txd,
                               lod_name=ML.lod_model_name(lod, sc.model_type(lod)[1])
                               if lod is not None else '')
            home[key] = cell
    multi = len(set(cells)) > 1
    out_dir = {c: (os.path.join(folder, c) if multi else folder) for c in set(cells)}
    # 3. что будет записано
    plan = {}                                   # путь → (вид, данные для записи)
    for cell in sorted(set(cells)):
        d = out_dir[cell]
        mine = [m for k, m in models.items() if home[k] == cell]
        if opts['dff']:
            for m in mine:
                plan[os.path.join(d, m['name'] + '.dff')] = ('dff', m)
                if m['lod'] is not None:
                    plan[os.path.join(d, m['lod_name'] + '.dff')] = ('lod', m)
        if opts['col'] and any(m['meshes'] or m['prims'] for m in mine):
            if opts['col_library']:
                plan[os.path.join(d, cell + '.col')] = ('col_lib', [m for m in mine
                                                                    if m['meshes'] or m['prims']])
            else:
                for m in mine:
                    if m['meshes'] or m['prims']:
                        plan[os.path.join(d, m['name'] + '.col')] = ('col', m)
        if opts['txd']:
            buckets = {}
            for m in mine:
                buckets.setdefault(m['txd'], []).append(m['dff'].node)
                if m['lod'] is not None:
                    buckets.setdefault(m['lod_txd'], []).append(m['lod'].node)
            for t, objs in buckets.items():
                plan[os.path.join(d, t + '.txd')] = ('txd', objs)
        if opts['ide'] and mine:
            plan[os.path.join(d, cell + '.ide')] = ('ide', mine)
        if opts['ipl']:
            rows = [r for r, c in zip(dffs, cells) if c == cell]
            plan[os.path.join(d, cell + '.ipl')] = ('ipl', rows)
            if opts['binary'] and game == 'SA':
                stem = cell + '_stream0'
                if len(stem) > STREAM_NAME_MAX:
                    warnings.append("%s.ipl: name longer than %d characters — the game can't "
                                    "stream it (DAT-39). Shorten the base name."
                                    % (stem, STREAM_NAME_MAX))
                plan[os.path.join(d, stem + '.ipl')] = ('bnry', rows)
    if opts['binary'] and game != 'SA':
        notes.append("Binary IPL is SA only — %s gets a text IPL" % game)
    exist = [p for p in plan if os.path.exists(p)]
    if exist and confirm is not None:
        shown = [os.path.relpath(p, folder) for p in exist[:20]]
        if len(exist) > 20:
            shown.append("… %d more" % (len(exist) - 20))
        if not confirm("Export Map", ["These files already exist and will be replaced "
                                      "(.txd — merged):"] + shown, "Continue?"):
            return None
    # 4. запись
    opts_x = DE._opts()
    counts = dict(dff=0, lod=0, col=0, txd=0, ide=0, ipl=0, rows=0)
    for d in set(out_dir.values()):
        os.makedirs(d, exist_ok=True)
    with sr.full_result():
        for path, (kind, obj) in plan.items():
            try:
                _write_one(path, kind, obj, sc, lodix, opts, opts_x, game, warnings, counts,
                           DE, fx_ad)
            except Exception as e:                     # noqa: BLE001
                import traceback
                traceback.print_exc()
                errors.append("%s: %s" % (os.path.basename(path), e))
    lines = ["%s%d model(s), %d placement(s) → DFF %d, LOD %d, COL %d, TXD %d, IDE %d, IPL %d "
             "(%d rows)" % (("%d cells, " % len(set(cells))) if multi else "", len(models),
                            len(dffs), counts['dff'], counts['lod'], counts['col'], counts['txd'],
                            counts['ide'], counts['ipl'], counts['rows'])]
    if opts['binary'] and game == 'SA':
        lines.append("Binary IPL: put <name>_stream0.ipl into an IMG — the game streams binary "
                     "IPLs from IMG only; the text <name>.ipl goes into gta.dat")
    lines += notes + warnings[:20] + ["Error: " + e for e in errors[:10]]
    level = 'ERROR' if errors and not counts['dff'] else ('WARNING' if errors or warnings
                                                           else 'INFO')
    return level, "\n".join(lines)


def _ipl_rows(sc, lodix, rows, pair):
    """Строки IPL ячейки. (модели, LOD): pair=False — всё в одном списке
    (LOD в конце, lod_index — на них); pair=True — модели отдельно, lod_index
    — индекс в списке LOD (текстовом файле пары)."""
    import copy
    mains, lods, seen = [], [], set()
    dup = 0
    for r in rows:
        e = ML.ipl_entry(sc, r)
        key = (e.model_id, round(e.pos_x, 3), round(e.pos_y, 3), round(e.pos_z, 3))
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        e.lod_index = -1
        lod = lodix.partner(r)
        if lod is not None:
            le = ML.lod_inst_for(sc, r, lod, sc.model_type(r)[1])
            if le.model_id > 0:
                le.lod_index = -1
                lods.append(copy.copy(le))
                e.lod_index = len(lods) - 1
        mains.append(e)
    if not pair:
        off = len(mains)
        for e in mains:
            if e.lod_index >= 0:
                e.lod_index += off
        return mains + lods, [], dup
    return lods, mains, dup


def _write_one(path, kind, obj, sc, lodix, opts, ox, game, warnings, counts, DE, fx_ad):
    name = os.path.splitext(os.path.basename(path))[0]
    if kind == 'dff':
        m = obj
        node = m['dff'].node
        nodes = DE._nodes_for([(node, None)], ox['pipeline'])
        fx = DE._fx_entries([c for c in node.children if fx_ad.is_2dfx(c)], node)
        data = DE.dff_bytes(name, nodes, fx, ox, warnings)
        counts['dff'] += 1
    elif kind == 'lod':
        nodes = DE._nodes_for([(obj['lod'].node, None)], ox['pipeline'])
        data = DE.dff_bytes(name, nodes, [], ox, warnings)
        counts['lod'] += 1
    elif kind in ('col', 'col_lib'):
        from inu_gta_core.col import write_col
        ms = [obj] if kind == 'col' else obj
        models = [DE._col_model(m['name'], ox['col_version'], m['meshes'], m['prims'], ox,
                                warnings, bounds_objs=[m['dff'].node], ref_node=m['dff'].node)
                  for m in ms]
        data = write_col(models, target_game=game)
        counts['col'] += len(models)
    elif kind == 'txd':
        base = None
        if os.path.isfile(path):
            with open(path, 'rb') as f:
                base = f.read()
        data, _note = DE.txd_data(os.path.basename(path), obj, ox, warnings, base)
        if data is None:
            return
        counts['txd'] += 1
    elif kind == 'ide':
        from inu_gta_core.ide import IdeFile, write_ide
        recs = []
        for m in obj:
            recs.append(m['dff'])
            if m['lod'] is not None:
                recs.append(m['lod'])
        rep = ML.Report()
        entries, seen = [], set()
        for _r, e, _p in ML.ide_entries(sc, recs, rep):
            if e.model_name.lower() not in seen:
                seen.add(e.model_name.lower())
                entries.append(e)
        warnings += [t for _l, t in rep.messages]
        ide = IdeFile()
        ide.objects = entries
        write_ide(path, ide, game=game)
        counts['ide'] += 1
        return
    elif kind in ('ipl', 'bnry'):
        from inu_gta_core.ipl import IplFile, write_ipl
        pair = bool(opts['binary']) and game == 'SA'
        text_rows, bin_rows, dup = _ipl_rows(sc, lodix, obj, pair)
        rows = bin_rows if kind == 'bnry' else text_rows
        if dup and kind == 'ipl':
            warnings.append("%s: %d identical placement(s) (same ID and position) written once"
                            % (os.path.basename(path), dup))
        ipl = IplFile()
        ipl.instances = rows
        write_ipl(path, ipl, binary=(kind == 'bnry'), game=game,
                  fla_extended=bool(opts['fla']) and kind == 'ipl' and game == 'SA')
        counts['ipl'] += 1
        counts['rows'] += len(rows)
        return
    else:
        return
    with open(path, 'wb') as f:
        f.write(data)
