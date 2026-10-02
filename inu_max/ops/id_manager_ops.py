# INU Tools (Max) — ID Manager окна Map IO (порт ops/id_manager_ops.py и
# data/id_manager.py Blender-версии INU; пресеты — inu_max/id_presets.py).
#
# Каждая функция возвращает (уровень, текст отчёта) или None — отменено в
# окне подтверждения. Model ID узла — user property inu_model_id; изменения
# сцены — одним шагом отмены, пресет (файл) Ctrl+Z не возвращает (как в INU).
#
# Исправлено против Blender (решения пользователя, 2026-09-28):
# - From Game читает и default.dat (машины, педы, оружие) — в Blender
#   первые выданные ID совпадали с ванильными (321–372, 400–611);
# - ID игры помечены отдельно (id_presets .game): Free phantoms / Clear All
#   их не освобождают;
# - Assign: копии одной модели — один ID; LOD модели (и не выделенный) —
#   ID модели + 1, если свободен; обходятся и ID из IDE (бокс IDE, список
#   «IDE to export», IDE связанных моделей);
# - From ID...: «Skip occupied IDs» по умолчанию включён;
# - Create ID — с подтверждением, занятые остаются;
# - активный пресет хранится в сцене .max.
# Дополнительно: пресет читается и пишется один раз на операцию (в INU — на
# каждый ID); коллизия не получает ID; имя LOD в пресете — имя LOD-модели
# (в INU «LOD»+имя давало LODLOD… у импортированных LOD).

import os

from .. import settings
from .. import id_presets as IP
from . import map_link as ML

_SCENE_KEY = "INU_ID_Preset"


# ── активный пресет (в сцене .max; новая сцена — последний выбранный) ─

def scene_preset():
    import pymxs
    rt = pymxs.runtime
    try:
        i = rt.fileProperties.findProperty(rt.Name('custom'), _SCENE_KEY)
        if i:
            return str(rt.fileProperties.getPropertyValue(rt.Name('custom'), i))
    except Exception:                                  # noqa: BLE001
        pass
    return ''


def set_scene_preset(name):
    import pymxs
    rt = pymxs.runtime
    try:
        rt.fileProperties.addProperty(rt.Name('custom'), _SCENE_KEY, str(name))
    except Exception as e:                             # noqa: BLE001
        print("[INU] ID preset → scene: %r" % (e,))


def active():
    """Активный пресет: записанный в сцене, иначе последний выбранный."""
    name = ''
    try:
        name = scene_preset()
    except Exception:                                  # noqa: BLE001
        name = ''
    return IP.sanitize(name or settings.get('id_preset', IP.DEFAULT) or IP.DEFAULT)


def set_active(name):
    name = IP.sanitize(name)
    settings.set('id_preset', name)
    try:
        set_scene_preset(name)
    except Exception:                                  # noqa: BLE001
        pass
    return name


# ── общее ────────────────────────────────────────────────────────────

def _selected():
    from ..adapter import selection
    return selection.selected_meshes()


def _undo(label):
    from ..adapter.selection import undo_block
    return undo_block(label)


def _no_sel():
    return 'ERROR', "Select mesh objects"


def _scene_ids(sc, exclude=()):
    ex = {r.handle for r in exclude}
    return {r.get('model_id', 0) for r in sc.recs
            if r.handle not in ex and r.get('model_id', 0) > 0}


_IDE_IDS = {}


def _ids_of_ide(path):
    """ID всех секций IDE (кэш по времени изменения)."""
    try:
        st = os.stat(path)
        mt = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    hit = _IDE_IDS.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    ids = {}
    try:
        from inu_gta_core.ide import read_ide
        ide = read_ide(path)
        for sec in (ide.objects, ide.anims, ide.cars, ide.peds, ide.weaps, ide.hiers):
            for e in sec:
                ids.setdefault(int(e.model_id), set()).add((e.model_name or '').casefold())
    except Exception as e:                             # noqa: BLE001
        print("[INU] IDE ids %s: %r" % (os.path.basename(path), e))
    _IDE_IDS[path] = (mt, ids)
    return ids


def _ide_names_for_scene(sc):
    paths = [settings.get('ide_path', '') or ''] + list(settings.get('ide_sync_list', []) or [])
    paths += [r.get('ide_target_file', '') for r in sc.recs if r.get('ide_linked', False)]
    rows, seen = {}, set()
    for path in paths:
        key = ML.norm(path) if path else ''
        if key and key not in seen and os.path.isfile(key):
            seen.add(key)
            for mid, names in _ids_of_ide(key).items():
                rows.setdefault(mid, set()).update(names)
    return rows


def _ide_ids(sc):
    """IDs of every relevant IDE section, including foreign model holders."""
    return set(_ide_names_for_scene(sc))


def _ide_name(sc, r):
    """Имя модели для пресета: как её строка в IDE."""
    mt, base = sc.model_type(r)
    return ML.lod_model_name(r, base) if mt == 'LOD' else sc.model_name(r)


def _models_by_key(sc):
    """(тип, имя модели) → все узлы-модели сцены с этим именем (копии)."""
    out = {}
    for r in sc.recs:
        mt = sc.model_type(r)[0]
        if mt == 'COL':
            continue
        out.setdefault((mt, _ide_name(sc, r).lower()), []).append(r)
    return out


def _ordered_keys(sc, recs, lodix, with_lods):
    """Модели выделения по порядку: модель, затем её LOD (with_lods — и не
    выделенный LOD из сцены)."""
    keys, trailing = [], []
    sel = {r.handle for r in recs}
    for r in recs:
        mt = sc.model_type(r)[0]
        if mt == 'COL':
            continue
        k = (mt, _ide_name(sc, r).lower())
        if mt == 'LOD':
            trailing.append(k)
            continue
        if k not in keys:
            keys.append(k)
        lod = lodix.partner(r)
        if lod is not None and (with_lods or lod.handle in sel):
            lk = ('LOD', _ide_name(sc, lod).lower())
            if lk not in keys:
                keys.append(lk)
    for k in trailing:
        if k not in keys:
            keys.append(k)
    return keys


def _own_ide_ids(group, name, sc=None):
    """Only a row of this model may be reused; another name keeps the ID busy."""
    own = set()
    for r in group:
        path = ML.ide_linked_file(r)
        rows = _ids_of_ide(path) if path else {}
        for mid in (r.get('model_id', 0), r.get('ide_last_model_id', 0)):
            if mid > 0 and rows.get(mid) == {name.casefold()}:
                own.add(mid)
    if sc is not None:
        all_names = _ide_names_for_scene(sc)
        own = {mid for mid in own if all_names.get(mid) == {name.casefold()}}
    return own


def _own_col_records(sc, key):
    if key[0] != 'DFF':
        return []
    return [r for r in sc.recs if sc.is_col(r) and
            sc.model_type(r)[1].casefold() == key[1]]


def _exclusive_col_ids(sc, key):
    collisions = _own_col_records(sc, key)
    ids = {r.get('model_id', 0) for r in collisions} - {0}
    for r in sc.recs:
        if r in collisions:
            continue
        if (sc.model_type(r)[0], _ide_name(sc, r).casefold()) != key:
            ids.discard(r.get('model_id', 0))
    return ids


def _fmt_ids(pairs, n=6):
    s = ", ".join("%s %d" % (nm, i) for nm, i in pairs[:n])
    return s + (" …" if len(pairs) > n else "")


# ── Assign / From ID / Clear selected / Release ──────────────────────

def id_manager_auto_assign():
    """Assign: ID моделям выделения с Model ID = 0 (копии одной модели — один
    ID; LOD модели, даже не выделенный, — ID модели + 1, если свободен)."""
    nodes = _selected()
    if not nodes:
        return _no_sel()
    sc = ML.Scene()
    recs = [r for r in sc.pick(nodes) if sc.model_type(r)[0] != 'COL']
    with _undo("INU: Assign IDs"):
        done, reused, left, warn = assign_models(sc, recs)
    if not done and not reused and not left:
        return 'INFO', "Assigned IDs: 0 (the selected models already have IDs)"
    lines = ["Assigned IDs: %d model(s)%s" % (len(done), (", copies given the existing ID: %d"
                                                           % reused) if reused else "")]
    if done:
        lines.append(_fmt_ids(done))
    lines += warn
    if left:
        lines.append("No free IDs in the active preset — without ID: %s" % ", ".join(left[:8]))
    level = 'ERROR' if left else ('WARNING' if warn else 'INFO')
    return level, "\n".join(lines)


def assign_models(sc, recs):
    """ID моделям recs с Model ID = 0 из активного пресета (Assign; также
    Export Map). Вызывать внутри шага отмены. (выдано [(имя, ID)], копий с
    готовым ID, без ID [имя], предупреждения)."""
    P = IP.Preset(active())
    lodix = ML.LodIndex(sc)
    by_key = _models_by_key(sc)
    keys = _ordered_keys(sc, recs, lodix, with_lods=True)
    skip = _scene_ids(sc) | _ide_ids(sc)
    done, reused, left, warn = [], 0, [], []
    for key in keys:
        group = by_key.get(key, [])
        forbidden = ({r.get('model_id', 0) for r in sc.recs
                      if sc.model_type(r)[0] == 'DFF' and r.get('model_id', 0) > 0}
                     if key[0] == 'LOD' else set())
        zero = [r for r in group if r.get('model_id', 0) <= 0 or r.get('model_id', 0) in forbidden]
        if not zero:
            continue
        have = sorted({r.get('model_id', 0) for r in group
                       if r.get('model_id', 0) > 0 and r.get('model_id', 0) not in forbidden})
        name = _ide_name(sc, group[0])
        if have:
            # у копии модели ID уже есть — остальным тот же
            if len(have) > 1:
                warn.append("«%s»: copies have different IDs (%s) — %d used"
                            % (name, ", ".join(map(str, have)), have[0]))
            nid = have[0]
            reused += len(zero)
        else:
            prefer = None
            if key[0] == 'LOD':
                handles = {r.handle for r in group}
                owners = [r.get('model_id', 0) for r in sc.models()
                          if sc.model_type(r)[0] == 'DFF' and
                          (lodix.partner(r) is not None and lodix.partner(r).handle in handles)
                          and r.get('model_id', 0) > 0]
                if owners:
                    prefer = min(owners) + 1
            others = _scene_ids(sc, exclude=group)
            own = _own_ide_ids(group, name, sc) - others - set(P.game)
            reusable = own | (_exclusive_col_ids(sc, key) - _ide_ids(sc) - set(P.game))
            if prefer in own and prefer not in P.ids():
                P.reserve(prefer, name)
                nid = prefer
            else:
                nid = P.allocate(name, skip - reusable, prefer, restart=bool(reusable))
            if nid is None:
                left.append(name)
                continue
            skip.add(nid)
            if prefer is not None and nid != prefer:
                reason = "is taken" if prefer in P.ids() else "is not in the preset"
                warn.append("«%s»: ID %d %s — the LOD got %d" % (name, prefer, reason, nid))
            done.append((name, nid))
        for r in zero:
            r.put({'model_id': int(nid)})
    P.save()
    return done, reused, left, warn


def id_manager_assign_from(start_id=321, skip_occupied=True):
    """From ID...: ID подряд от start_id моделям выделения (модель, затем её
    выделенный LOD; копии модели — тот же ID)."""
    nodes = _selected()
    if not nodes:
        return _no_sel()
    sc = ML.Scene()
    P = IP.Preset(active())
    lodix = ML.LodIndex(sc)
    by_key = _models_by_key(sc)
    recs = [r for r in sc.pick(nodes) if sc.model_type(r)[0] != 'COL']
    keys = _ordered_keys(sc, recs, lodix, with_lods=False)
    affected = [r for k in keys for r in by_key.get(k, [])]
    affected += [r for k in keys for r in _own_col_records(sc, k)]
    old_ids = {r.get('model_id', 0) for r in affected} - {0}
    others = _scene_ids(sc, exclude=affected)
    own = set().union(*[_own_ide_ids(by_key.get(k, []), k[1], sc) for k in keys]) if keys else set()
    ide_foreign = _ide_ids(sc) - own
    used = set(P.used()) | others | ide_foreign | set(P.game)
    used -= old_ids - set(P.game) - others - ide_foreign
    preset_used = P.used()
    for key in keys:
        for mid in _own_ide_ids(by_key.get(key, []), key[1], sc):
            if mid not in P.game and mid not in others and preset_used.get(mid, key[1]).casefold() == key[1]:
                used.discard(mid)
    cur = max(1, int(start_id))
    done, clashes = [], 0
    with _undo("INU: Assign IDs from"):
        for key in keys:
            group = by_key.get(key, [])
            if not group:
                continue
            if skip_occupied:
                while cur in used:
                    cur += 1
            elif cur in used:
                clashes += 1
            name = _ide_name(sc, group[0])
            for r in group + _own_col_records(sc, key):
                r.put({'model_id': int(cur)})
            P.reserve(cur, name)
            used.add(cur)
            done.append((name, cur))
            cur += 1
        # прежние ID выделения — свободны, если больше никем не заняты
        still = _scene_ids(sc)
        freed = 0
        for i in old_ids:
            if i not in still and i not in P.game and P.release(i):
                freed += 1
        P.save()
    lines = ["Assigned IDs: %d (%d+)%s" % (len(done), int(start_id),
                                           (" — conflicts with occupied: %d" % clashes)
                                           if clashes else "")]
    if done:
        lines.append(_fmt_ids(done))
    if freed:
        lines.append("Previous IDs freed in the preset: %d" % freed)
    return ('WARNING' if clashes else 'INFO'), "\n".join(lines)


def id_manager_clear_selected():
    """Clear selected: Model ID = 0 у выделенных; в пресете освобождаются ID,
    которых больше нет ни у одного узла (ID игры не освобождаются)."""
    nodes = _selected()
    sc = ML.Scene()
    recs = [r for r in (sc.rec(n) for n in nodes) if r is not None and r.get('model_id', 0) > 0]
    if not recs:
        return 'INFO', "Cleared IDs: 0"
    P = IP.Preset(active())
    ids = {r.get('model_id', 0) for r in recs}
    with _undo("INU: Clear selected IDs"):
        for r in recs:
            r.put({'model_id': 0})
        remaining = _scene_ids(sc)
        freed = sum(1 for i in ids if i not in remaining and i not in P.game and P.release(i))
        P.save()
    return 'INFO', "Cleared IDs: %d (freed in preset: %d)" % (len(recs), freed)


def id_manager_release(model_id, confirm=None):
    """✕ у ID в списке: ID снимается со всех узлов и освобождается в пресете.
    ID игры (From Game) — не освобождается."""
    model_id = int(model_id)
    P = IP.Preset(active())
    if model_id in P.game:
        if confirm is None:
            return 'WARNING', 'ID %d is used by the game — confirmation required' % model_id
        if not confirm('Release game ID',
                       ['ID %d belongs to a vanilla model. Reusing it replaces that model in the game.' % model_id],
                       'Release this ID?'):
            return None
        P.game.remove(model_id)
    sc = ML.Scene()
    holders = [r for r in sc.recs if r.get('model_id', 0) == model_id]
    with _undo("INU: Release ID"):
        for r in holders:
            r.put({'model_id': 0})
        P.release(model_id)
        P.save()
    return 'INFO', "ID %d released%s" % (model_id, (" (cleared on %d object(s))" % len(holders))
                                          if holders else "")


# ── ID database & service ────────────────────────────────────────────

def id_manager_sync_scene():
    """Sync: ID моделей сцены → пресет (нет — добавляется, свободен —
    занимается именем модели; чужие имена не меняются)."""
    sc = ML.Scene()
    P = IP.Preset(active())
    have = P.ids()
    used = P.used()
    added = 0
    for r in sc.models():
        mid = r.get('model_id', 0)
        if mid <= 0 or sc.model_type(r)[0] == 'COL':
            continue
        if mid not in have or mid not in used:
            P.reserve(mid, _ide_name(sc, r))
            have.add(mid)
            used[mid] = True
            added += 1
    P.save()
    return 'INFO', "Added IDs: %d" % added


_DATS = ('default.dat', 'gta.dat', 'gta_int.dat', 'gta_vc.dat', 'gta3.dat')


def id_manager_from_game():
    """From Game: ID всех IDE игры (default.dat + gta*.dat) → заняты именами
    игры и помечены как ID игры."""
    root = settings.get('game_root', '') or ''
    if not root or not os.path.isdir(root):
        return 'ERROR', "Specify the game root folder (Map IO → Map tab / Import)"
    from inu_gta_core.gta_dat import game_ide_paths, GAME_DATS
    from inu_gta_core.fs_ci import resolve
    from inu_gta_core.ide import read_ide
    ide_paths, dats = game_ide_paths(root)
    unread_dats = [dat for dat in GAME_DATS if dat not in dats and
                  os.path.isfile(resolve(os.path.join(root, 'data', dat)))]
    if not dats and unread_dats:
        return 'ERROR', 'Not read: ' + ', '.join(unread_dats)
    if not dats:
        return 'ERROR', "No data\\gta.dat / default.dat in %s" % root
    game, bad = {}, []
    for p in ide_paths:
        if not os.path.isfile(p):
            bad.append(os.path.basename(p))
            continue
        try:
            ide = read_ide(p)
        except Exception:                              # noqa: BLE001
            bad.append(os.path.basename(p))
            continue
        for sec in (ide.objects, ide.anims, ide.cars, ide.peds, ide.weaps, ide.hiers):
            for e in sec:
                game[int(e.model_id)] = str(e.model_name)
    P = IP.Preset(active())
    clashes, added = P.mark_game(game)
    P.save()
    lines = ["Game IDs: %d (%d IDE from %s), newly used: %d"
             % (len(game), len(ide_paths) - len(bad), ", ".join(dats), added)]
    if clashes:
        lines.append("Your entries on game IDs (renamed to the game model): %d — %s"
                     % (len(clashes), ", ".join("%d %s→%s" % c for c in clashes[:5])
                        + (" …" if len(clashes) > 5 else "")))
    if unread_dats:
        lines.append("Not read: " + ", ".join(unread_dats))
    if bad:
        lines.append("IDE not read: %s" % ", ".join(bad[:5]))
    return ('WARNING' if clashes or bad or unread_dats else 'INFO'), "\n".join(lines)


def id_manager_create(confirm=None):
    P = IP.Preset(active())
    n_used = len(P.used())
    if confirm is not None and not confirm(
            "Create ID",
            ["Fill the preset «%s» with IDs %d-%d." % (P.name, IP.FIRST_ID, IP.LAST_ID),
             "Missing IDs are added as free; used IDs (%d) stay." % n_used],
            "Continue?"):
        return None
    n = P.fill()
    P.save()
    return 'INFO', "ID: %d-%d (+%d free)" % (IP.FIRST_ID, IP.LAST_ID, n)


def id_manager_extend(count=1000):
    P = IP.Preset(active())
    a, b = P.extend(int(count))
    P.save()
    return 'INFO', "ID: +%d (%d-%d)" % (int(count), a, b)


def id_manager_gc():
    sc = ML.Scene()
    P = IP.Preset(active())
    n = P.gc(_scene_ids(sc))
    P.save()
    return 'INFO', "Phantom IDs freed: %d%s" % (n, (" (game IDs kept: %d)" % len(P.game))
                                               if P.game else "")


def id_manager_clear(confirm=None):
    P = IP.Preset(active())
    if confirm is not None and not confirm(
            "Clear All", ["Free all used IDs of the preset «%s» (%d)." % (P.name, len(P.used())),
                          "Game IDs (From Game) stay."], "Continue?"):
        return None
    n = P.clear_all()
    P.save()
    return 'INFO', "All IDs cleared: %d%s" % (n, (" (game IDs kept: %d)" % len(P.game))
                                             if P.game else "")
