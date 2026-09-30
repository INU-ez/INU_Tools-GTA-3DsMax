# INU Tools (Max) — вкладка Map окна Map IO: Scan IPLs, Extract resources,
# Import Map, BBox (порт scan_binary_ipls / extract_textures / import_map /
# toggle_bbox Blender-версии INU). Export Map — ops/map_export.py.
#
# Как в Blender (решения пользователя, 2026-09-28): Import Map берёт модели
# ТОЛЬКО из кэша .inu_cache рядом с .max, который заполняет Extract
# resources (DFF / COL архивов игры — плоско, текстуры — в одну папку
# .inu_cache\textures, при совпадении имён остаётся большая).
#
# Исправлено против Blender:
# - Scan и Import Map берут один набор файлов: текстовые IPL — из gta.dat
#   региона, бинарные — <имя текстового>_stream*.ipl из IMG (в Blender Scan
#   искал по префиксу региона — у COUNTRY терялись countn2_stream*, а
#   заполненный список пропускал в импорт только найденное);
# - lod_index бинарного IPL указывает в ОДНОИМЁННЫЙ ТЕКСТОВЫЙ IPL
#   (проверено на SA: 4648 из 4648) — в Blender он считался внутри самого
#   бинарного и LOD цеплялись к чужим моделям;
# - LOD — по ссылкам lod_index и по имени (в Blender только по имени);
# - модель в нескольких архивах — из первого в порядке загрузки игры (в
#   Extract — как Blender), кэш обновляется, если запись архива изменилась
#   (в Blender уже распакованный файл не перезаписывался никогда);
# - копии модели не наследуют связь IPL оригинала (IPL_CLEAR, как импорт
#   вкладки Import); связь с IPL — у строк текстовых IPL.
# Секции IPL (cull, grge, enex…) — часть 6.

import json
import os
import re
import struct

import pymxs

from .. import settings

_STREAM = re.compile(r'^(.+)_stream\d+\.ipl$', re.I)


def _root():
    r = settings.get('game_root', '') or ''
    return r if os.path.isdir(r) else ''


def cache_dir():
    """.inu_cache рядом с .max ('' — сцена не сохранена)."""
    from ..adapter.selection import scene_file
    f = scene_file()
    return os.path.join(os.path.dirname(f), '.inu_cache') if f else ''


def tex_dir():
    c = cache_dir()
    return os.path.join(c, 'textures') if c else ''


def _archives():
    """Архивы игры в порядке загрузки (+ IMG из настроек)."""
    from .map_import import _game_imgs, order_archives
    root = _root()
    out = _game_imgs(root) if root else []
    extra = settings.get('img_path', '') or ''
    if extra and os.path.isfile(extra) and os.path.normcase(os.path.abspath(extra)) not in \
            {os.path.normcase(os.path.abspath(p)) for p in out}:
        out = order_archives(out + [extra], root)
    return out


# ── файлы региона: одни и те же для Scan и Import Map ────────────────

def _region_match(path, region):
    if not region or region == 'ALL':
        return True
    parts = [x for x in path.replace('/', '\\').split('\\') if x]
    low = [x.lower() for x in parts]
    if 'maps' in low:
        i = low.index('maps')
        if i + 1 < len(parts) - 1:
            return parts[i + 1].upper() == region.upper()
    return os.path.basename(path).upper().startswith(region.upper())


def region_files(region=None):
    """(текстовые IPL [путь], бинарные [(имя записи, архив)]) региона.
    Текстовые — из gta.dat / gta_int.dat; бинарные — <стем текстового>_
    stream*.ipl из архивов игры (первый архив выигрывает)."""
    from inu_gta_core.gta_dat import find_all_resources
    from inu_gta_core.img import read_directory
    root = _root()
    if not root:
        return [], []
    region = region or settings.get('map_region', 'ALL') or 'ALL'
    try:
        res = find_all_resources(root)
    except Exception:                                  # noqa: BLE001
        return [], []
    text, seen = [], set()
    for p in res.ipl_paths:
        k = os.path.normcase(os.path.abspath(p))
        if k in seen or not os.path.isfile(p) or not _region_match(p, region):
            continue
        seen.add(k)
        text.append(p)
    stems = {os.path.splitext(os.path.basename(p))[0].lower() for p in text}
    binary, taken = [], set()
    for arch in _archives():
        try:
            ents = read_directory(arch)
        except Exception:                              # noqa: BLE001
            continue
        for e in ents:
            m = _STREAM.match(e.name)
            if not m or m.group(1).lower() not in stems or e.name.lower() in taken:
                continue
            taken.add(e.name.lower())
            binary.append((e.name, arch))
    return text, binary


def scan_binary_ipls():
    """Scan IPLs: списки текстовых и бинарных IPL региона (галочки
    вкл/выкл сохраняются по имени)."""
    if not _root():
        return 'ERROR', "Set the game folder"
    region = settings.get('map_region', 'ALL') or 'ALL'
    old = {(d.get('name') or '').lower(): d.get('enabled', True)
           for d in list(settings.get('binary_ipls', []) or [])
           + list(settings.get('text_ipls', []) or [])}
    text, binary = region_files(region)
    settings.set('text_ipls', [dict(name=os.path.basename(p), path=p, img_source='',
                                    enabled=old.get(os.path.basename(p).lower(), True))
                               for p in text])
    settings.set('binary_ipls', [dict(name=n, img_source=a, enabled=old.get(n.lower(), True))
                                 for n, a in binary])
    settings.set('map_scanned_region', region)
    return 'INFO', "%d binary + %d text IPL(s) for region '%s'" % (len(binary), len(text), region)


def _enabled(kind, name):
    """Галочка файла в списке Scan (список другого региона / не сканирован
    — все включены)."""
    if settings.get('map_scanned_region', '') != (settings.get('map_region', 'ALL') or 'ALL'):
        return True
    for d in settings.get(kind, []) or []:
        if (d.get('name') or '').lower() == name.lower():
            return bool(d.get('enabled', True))
    return True


# ── Extract resources ────────────────────────────────────────────────

_INDEX = '_extract_index.json'


def _png_size(path):
    try:
        with open(path, 'rb') as f:
            head = f.read(24)
        if head[:8] == b'\x89PNG\r\n\x1a\n':
            return struct.unpack('>II', head[16:24])
    except OSError:
        pass
    return None


def _load_index(cdir):
    try:
        with open(os.path.join(cdir, _INDEX), 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_index(cdir, idx):
    p = os.path.join(cdir, _INDEX)
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(idx, f)
    os.replace(p + '.tmp', p)


def _region_txds(ide_models):
    """TXD моделей региона (строки текстовых и бинарных IPL → ID → IDE)."""
    from inu_gta_core.ipl import read_ipl, _read_binary_ipl
    from inu_gta_core.img import ImgReader
    text, binary = region_files()
    ids = set()
    for p in text:
        try:
            ids |= {i.model_id for i in read_ipl(p).instances}
        except Exception:                              # noqa: BLE001
            pass
    by_arch = {}
    for n, a in binary:
        by_arch.setdefault(a, []).append(n)
    for a, names in by_arch.items():
        with ImgReader(a) as r:
            for n in names:
                try:
                    ids |= {i.model_id for i in _read_binary_ipl(r.read(n) or b'').instances}
                except Exception:                      # noqa: BLE001
                    pass
    return {(ide_models[i].txd_name or '').lower() for i in ids if i in ide_models} - {''}


def extract_textures():
    """Extract resources: DFF / COL всех архивов игры в .inu_cache (первый
    архив выигрывает; запись изменилась — файл обновляется), TXD →
    .inu_cache\\textures\\<текстура>.png (регион ≠ ALL — только TXD моделей
    региона; одноимённые — остаётся большая по размеру, как Blender)."""
    from concurrent.futures import ThreadPoolExecutor
    from inu_gta_core.img import ImgReader, read_directory
    from inu_gta_core.txd import read_txd
    from inu_gta_core.gta_dat import list_ide_files
    from ..adapter.texture import write_png, _safe_name, tex_rgba, TEX_VER
    from .map_import import _read_ides
    rt = pymxs.runtime
    cdir = cache_dir()
    if not cdir:
        return 'ERROR', "Save the .max first — the cache lives next to it (.inu_cache)"
    root = _root()
    if not root:
        return 'ERROR', "Set the game folder"
    archives = _archives()
    if not archives:
        return 'ERROR', "No IMG archives in the game folder"
    os.makedirs(os.path.join(cdir, 'textures'), exist_ok=True)
    idx = _load_index(cdir)
    files = idx.setdefault('files', {})       # запись → [архив, смещение, размер]
    txds = idx.setdefault('txd', {})          # TXD → [архив, смещение, размер]
    # PNG прошлой версии декода: все TXD — заново, такие PNG перезаписываются
    # без сравнения размеров (список живёт в индексе до перезаписи)
    if idx.get('tex_ver') != TEX_VER:
        txds.clear()
        idx['tex_stale'] = [f.lower() for f in os.listdir(os.path.join(cdir, 'textures'))
                            if f.lower().endswith('.png')]
        idx['tex_ver'] = TEX_VER
    stale = set(idx.get('tex_stale') or ())
    region = settings.get('map_region', 'ALL') or 'ALL'
    want_txd = None
    if region != 'ALL':
        ide_models, _src = {}, {}
        _read_ides(list_ide_files(root), ide_models, _src)
        want_txd = _region_txds(ide_models)
    # победители: первый архив, первая запись
    win = {}
    for a in archives:
        try:
            for e in read_directory(a):
                k = e.name.lower()
                if k.endswith(('.dff', '.col', '.txd')) and k not in win:
                    win[k] = (a, e)
        except Exception as ex:                        # noqa: BLE001
            print("[INU extract] %s: %r" % (a, ex))
    todo_files = [(k, a, e) for k, (a, e) in win.items() if not k.endswith('.txd')]
    todo_txd = [(k, a, e) for k, (a, e) in win.items() if k.endswith('.txd')
                and (want_txd is None or k[:-4] in want_txd)]
    n_file = n_same = 0
    n_tex = n_tex_skip = n_txd_same = 0
    errors = []
    readers = {}

    def rd(a):
        if a not in readers:
            readers[a] = ImgReader(a)
            readers[a].open()
        return readers[a]

    total = len(todo_files) + len(todo_txd)
    step = 0
    cancelled = False
    rt.progressStart("INU: Extract resources")
    try:
        for k, a, e in todo_files:
            step += 1
            if step % 50 == 0 and (not rt.progressUpdate(100.0 * step / max(total, 1))
                                   or rt.getProgressCancel()):
                cancelled = True
                break
            stamp = [a, e.offset, e.size]
            out = os.path.join(cdir, e.name)
            if files.get(k) == stamp and os.path.isfile(out):
                n_same += 1
                continue
            data = rd(a).read_entry(e)
            with open(out, 'wb') as f:
                f.write(data)
            files[k] = stamp
            n_file += 1
        tdir = os.path.join(cdir, 'textures')

        def decode(item):
            k, a, e, data = item
            try:
                return k, [(t.name, t.width, t.height, tex_rgba(t)) for t in read_txd(data)
                           if t.pixels and t.width > 0 and t.height > 0], None
            except Exception as ex:                    # noqa: BLE001
                return k, [], "%s: %s" % (e.name, ex)
        batch = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for k, a, e in todo_txd if not cancelled else []:
                stamp = [a, e.offset, e.size]
                if txds.get(k) == stamp:
                    n_txd_same += 1
                    continue
                batch.append((k, a, e, rd(a).read_entry(e)))
                if len(batch) < 16:
                    continue
                for res in pool.map(decode, batch):
                    n_tex, n_tex_skip = _write_texs(res, tdir, write_png, _safe_name, errors,
                                                    n_tex, n_tex_skip, stale)
                    txds[res[0]] = [win[res[0]][0], win[res[0]][1].offset, win[res[0]][1].size]
                step += len(batch)
                batch = []
                if not rt.progressUpdate(100.0 * step / max(total, 1)) or rt.getProgressCancel():
                    cancelled = True
                    break
            if batch and not cancelled:
                for res in pool.map(decode, batch):
                    n_tex, n_tex_skip = _write_texs(res, tdir, write_png, _safe_name, errors,
                                                    n_tex, n_tex_skip, stale)
                    txds[res[0]] = [win[res[0]][0], win[res[0]][1].offset, win[res[0]][1].size]
    finally:
        rt.progressEnd()
        for r in readers.values():
            r.close()
        idx['tex_stale'] = sorted(stale)
        _save_index(cdir, idx)
    lines = ["DFF/COL: %d extracted, %d unchanged · textures: %d written, %d kept (same or "
             "larger file there), %d TXD unchanged" % (n_file, n_same, n_tex, n_tex_skip,
                                                        n_txd_same)]
    if region != 'ALL':
        lines.append("Region %s: %d TXD" % (region, len(todo_txd)))
    if cancelled:
        lines.insert(0, "Cancelled — what was extracted stays in the cache.")
    lines += ["Error: " + x for x in errors[:5]]
    return ('WARNING' if errors or cancelled else 'INFO'), "\n".join(lines)


def _write_texs(res, tdir, write_png, safe, errors, n_tex, n_skip, stale):
    k, texs, err = res
    if err:
        errors.append(err)
    for name, w, h, px in texs:
        fn = safe(name) + '.png'
        p = os.path.join(tdir, fn)
        old = None if fn.lower() in stale else _png_size(p)
        if old is not None and old[0] >= w and old[1] >= h:
            n_skip += 1
            continue
        try:
            write_png(p, px, w, h)
            stale.discard(fn.lower())
            n_tex += 1
        except Exception as ex:                        # noqa: BLE001
            errors.append("%s: %s" % (name, ex))
    return n_tex, n_skip


def cache_has_models():
    c = cache_dir()
    if not c or not os.path.isdir(c):
        return False
    try:
        return any(f.lower().endswith('.dff') for f in os.listdir(c))
    except OSError:
        return False


# ── Import Map (из кэша) ─────────────────────────────────────────────

def _importer_cls():
    from .map_import import _Importer
    from .img_ops import col_chunks

    class _CacheImporter(_Importer):
        """Импорт вкладки Import, но модели, коллизия и текстуры — из
        .inu_cache (Extract resources)."""

        def setup(self, cdir):
            self.cdir = cdir
            idx = _load_index(cdir)
            self.src_arch = {k: v[0] for k, v in idx.get('files', {}).items()}
            self.files = {}
            for f in os.listdir(cdir):
                if os.path.isfile(os.path.join(cdir, f)):
                    self.files.setdefault(f.lower(), f)
            self.flat = {}
            td = os.path.join(cdir, 'textures')
            if os.path.isdir(td):
                for f in os.listdir(td):
                    if f.lower().endswith('.png'):
                        self.flat.setdefault(f[:-4].lower(), os.path.join(td, f))
            # PNG прошлой версии декода (Extract resources ещё не обновил) —
            # берутся как есть, но с пометкой в отчёте
            from ..adapter.texture import TEX_VER
            old = set(idx.get('tex_stale') or ()) if idx.get('tex_ver') == TEX_VER else None
            self.flat_old = {k for k, p in self.flat.items()
                             if old is None or os.path.basename(p).lower() in old}
            self.archives = []
            self.img_index = {}

        def read_entry(self, name_lower):
            real = self.files.get(name_lower)
            if real is None:
                return None, None
            with open(os.path.join(self.cdir, real), 'rb') as f:
                return f.read(), self.src_arch.get(name_lower, '')

        def txd_pngs(self, txd):
            return {}

        def rescue(self, missing):
            out = {t: self.flat[t] for t in missing if t in self.flat}
            if self.flat_old and not self.flat_old.isdisjoint(out):
                self.flat_old = set()                  # пометка — одна на импорт
                self.notes.append("Texture cache is from an older version (GTA III colours "
                                  "may be off) — press «Extract resources» to refresh it")
            return out

        def col_index(self):
            if self._col_idx is None:
                idx = {}
                for low, real in sorted(self.files.items()):
                    if not low.endswith('.col'):
                        continue
                    try:
                        with open(os.path.join(self.cdir, real), 'rb') as f:
                            data = f.read()
                    except OSError:
                        continue
                    self.col_bytes[(self.cdir, real.lower())] = data
                    for s, e, nm, _mid in col_chunks(data):
                        if nm:
                            idx.setdefault(nm.lower(), (self.cdir, real, s, e - s))
                self._col_idx = idx
            return self._col_idx

        def col_blob(self, arch, entry):
            key = (arch, entry.lower())
            if key not in self.col_bytes:
                with open(os.path.join(self.cdir, entry), 'rb') as f:
                    self.col_bytes[key] = f.read()
            return self.col_bytes[key]

    return _CacheImporter


_LAYERS = r'''
global inuMapEnsureLayer
fn inuMapEnsureLayer layName parentName = (
    local lay = LayerManager.getLayerFromName layName
    if lay == undefined do lay = LayerManager.newLayerFromName layName
    if parentName != "" do (
        local par = LayerManager.getLayerFromName parentName
        if par == undefined do par = LayerManager.newLayerFromName parentName
        lay.setParent par
    )
    true
)
'''


def import_map():
    """Import Map: строки IPL региона (галочки Scan) → модели из кэша."""
    from inu_gta_core.ipl import read_ipl, _read_binary_ipl
    from inu_gta_core.img import ImgReader
    from inu_gta_core.gta_dat import list_ide_files
    from ..adapter import map_scene
    from .map_import import _read_ides
    rt = pymxs.runtime
    cdir = cache_dir()
    if not cdir:
        return 'ERROR', "Save the .max first"
    if not cache_has_models():
        return 'ERROR', "Cache is empty — press «Extract resources» first"
    root = _root()
    if not root:
        return 'ERROR', "Set the game folder"
    text, binary = region_files()
    text = [p for p in text if _enabled('text_ipls', os.path.basename(p))]
    binary = [(n, a) for n, a in binary if _enabled('binary_ipls', n)]
    if not text and not binary:
        return 'ERROR', "No IPL for this region (or all unchecked)"
    ide_models, ide_source = {}, {}
    _read_ides(list_ide_files(root), ide_models, ide_source)
    instances, inst_src, src_of = [], {}, []
    text_base, errors = {}, []
    for p in text:
        try:
            ipl = read_ipl(p)
        except Exception as e:                         # noqa: BLE001
            errors.append("%s: %s" % (os.path.basename(p), e))
            continue
        base, n_local = len(instances), len(ipl.instances)
        stem = os.path.splitext(os.path.basename(p))[0]
        text_base[stem.lower()] = (base, n_local)
        for k, inst in enumerate(ipl.instances):
            li = inst.lod_index
            inst.lod_index = base + li if 0 <= li < n_local else -1
            if not inst.model_name and inst.model_id in ide_models:
                inst.model_name = ide_models[inst.model_id].model_name
            inst_src[base + k] = (p, base)
            instances.append(inst)
            src_of.append(stem)
    by_arch = {}
    for n, a in binary:
        by_arch.setdefault(a, []).append(n)
    n_bin_lod = 0
    for a, names in by_arch.items():
        with ImgReader(a) as r:
            for n in names:
                try:
                    ipl = _read_binary_ipl(r.read(n) or b'')
                except Exception as e:                 # noqa: BLE001
                    errors.append("%s: %s" % (n, e))
                    continue
                stem = _STREAM.match(n).group(1).lower()
                tb = text_base.get(stem)
                for inst in ipl.instances:
                    li = inst.lod_index
                    # lod_index бинарного — в одноимённый ТЕКСТОВЫЙ IPL
                    if tb is not None and 0 <= li < tb[1]:
                        inst.lod_index = tb[0] + li
                        n_bin_lod += 1
                    else:
                        inst.lod_index = -1
                    if not inst.model_name and inst.model_id in ide_models:
                        inst.model_name = ide_models[inst.model_id].model_name
                    instances.append(inst)
                    src_of.append(os.path.splitext(n)[0])
    if not instances:
        return 'ERROR', "The region IPLs have no placements"

    group = bool(settings.get('map_group_by_ipl', True))
    rt.execute(_LAYERS)
    made = set()

    def ensure(name, parent=''):
        if name not in made:
            rt.inuMapEnsureLayer(name, parent)
            made.add(name)

    def layer_of(idx, inst, is_lod):
        if group:
            ipl = src_of[idx]
            lay = ipl + ('_LOD' if is_lod else '_DFF')
            ensure(lay, ipl)
            ensure(ipl + '_COL', ipl)
            return lay, ipl + '_COL'
        if is_lod:
            ensure('Map_LOD')
            ensure('Map_COL')
            return 'Map_LOD', 'Map_COL'
        ide = ide_models.get(inst.model_id)
        dd = float(getattr(ide, 'draw_distance', 300.0) or 300.0) if ide is not None else 300.0
        lay = 'Map_DFF_Far' if dd >= 300 else ('Map_DFF_Mid' if dd >= 100 else 'Map_DFF_Near')
        ensure(lay)
        ensure('Map_COL')
        return lay, 'Map_COL'

    imp = _importer_cls()()
    imp.setup(cdir)
    imp.errors += errors
    imp.infos = []
    if n_bin_lod:
        imp.infos.append("Binary IPL rows linked to LOD rows of their text IPL: %d" % n_bin_lod)
    scene = map_scene.scene_index()
    return imp.place(instances, inst_src, ide_models, ide_source, scene,
                     title="INU: Import Map",
                     skip_existing=bool(settings.get('map_skip_dupes', False)),
                     reuse_scene=False, layer_of=layer_of,
                     noimg_text="not in the cache (Extract resources)")


# ── BBox ─────────────────────────────────────────────────────────────

BBOX_RADIUS = 300.0
# Пересчёт — в MAXScript (на каждую смену выделения обход всей геометрии
# через pymxs на карте в тысячи объектов заметно тормозил бы).
_BBOX_MXS = r'''
global inuBBoxNodes
if inuBBoxNodes == undefined do inuBBoxNodes = #()
global inuBBoxSet
fn inuBBoxSet nodeArr = (inuBBoxNodes = nodeArr as array; inuBBoxNodes.count)
global inuBBoxUpdate
fn inuBBoxUpdate radiusM = (
    local selPos = for s in selection collect s.pos
    local r2 = radiusM * radiusM
    local cnt = 0
    disableSceneRedraw()
    for o in inuBBoxNodes where isValidNode o do (
        local p = o.pos
        local near = false
        for s in selPos while not near do (
            local d = p - s
            if (dot d d) <= r2 do near = true
        )
        local want = not near
        if o.boxMode != want do o.boxMode = want
        if want do cnt += 1
    )
    enableSceneRedraw()
    redrawViews()
    cnt
)
'''
_BBOX_CB = ('callbacks.removeScripts id:#inuMapBBox\n'
            'callbacks.addScript #selectionSetChanged "try (inuBBoxUpdate %s) catch ()" '
            'id:#inuMapBBox\n' % BBOX_RADIUS)


def bbox_active():
    import sys
    return bool(getattr(sys, '_inu_bbox_on', False))


def _bbox_nodes():
    """Меши сцены без коллизии (COL / SHA, сферы и боксы)."""
    rt = pymxs.runtime
    from ..adapter import scene_read as sr
    return [o for o in rt.geometry if not sr.is_col(o) and not sr.col_prim(o)]


def toggle_bbox():
    """BBox (toggle_bbox INU): ON — меши дальше 300 м от выделения
    показываются коробкой («Display as Box»), и так при каждой смене
    выделения; OFF — все как есть."""
    import sys
    rt = pymxs.runtime
    rt.execute(_BBOX_MXS)
    on = not bbox_active()
    sys._inu_bbox_on = on
    if on:
        rt.inuBBoxSet(_bbox_nodes())
        rt.execute(_BBOX_CB)
        n = int(rt.inuBBoxUpdate(BBOX_RADIUS))
        return 'INFO', "BBox: ON (%d as box, radius %d m around the selection)" % (
            n, BBOX_RADIUS)
    rt.execute('callbacks.removeScripts id:#inuMapBBox')
    n = 0
    for o in _bbox_nodes():
        if o.boxMode:
            o.boxMode = False
            n += 1
    rt.inuBBoxSet([])
    rt.redrawViews()
    return 'INFO', "BBox: OFF (%d restored)" % n
