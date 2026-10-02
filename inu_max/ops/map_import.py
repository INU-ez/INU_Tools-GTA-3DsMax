# INU Tools (Max) — вкладка Import окна Map IO: модели карты прямо из IMG —
# по IPL (с расстановкой) или по IDE (сеткой). Порт gtatools.import_from_img,
# scan_img_for_ipl и scan_ide_for_ipl Blender-версии INU.
#
# Как в INU: IPL из списка «IPL to import», IMG — найденные кнопкой Find IMG,
# IDE — выбранная в боксе IDE, иначе все IDE игры, плюс найденные Find IDE.
# Первая расстановка модели — импорт DFF, остальные — instance (меш общий).
# Слои Map_DFF / Map_LOD / Map_COL. Имена как в INU: <модель>_DFF,
# <модель>_LOD, коллизия <модель>_COL. На объекты — Model ID, дистанция,
# флаги, TXD, связь с IDE и якорь строки IPL (для Add / Sync, ops/map_link).
#
# Исправлено против Blender (решение: «чинить»):
# - кнопка COL работает; коллизия ищется и в COL-библиотеках архивов
#   (в ванили вся коллизия там), ставится один раз на модель со своими
#   сферами и боксами (в Blender все объекты коллизии ложились в одну точку);
# - текстуры добираются из ВСЕХ найденных IMG, а не только из основного;
#   кнопка TXD выключена — модели без текстур;
# - interior и 12-я колонка FLA сохраняются; IPL scale игнорируется как игрой;
# - повтор модели из сцены — по имени и ID (в Blender только по ID);
# - строки бинарного IPL: имя модели — из IDE по ID; их lod_index указывает в
#   другой (текстовый) IPL, поэтому по нему LOD не связывается;
# - сетка «только IDE» — только из явно выбранной IDE; IPL без строк —
#   сообщение (в Blender это грузило сеткой все модели всех IDE игры);
# - порядок архивов: как грузит игра (gta3.img, gta_int.img, IMG из gta.dat,
#   затем прочие); модель, которая есть в нескольких, берётся из ПЕРВОГО
#   (решение 2026-09-28: как игра внутри архива; было — из последнего).

import math
import os

import pymxs

from .. import settings

_SKIP_DIRS = {'.git', '.svn', '__pycache__', '.inu_cache', 'node_modules'}
_SECTOR = 2048


# ── входные файлы ────────────────────────────────────────────────────

def _ipl_paths():
    """IPL для импорта: список «IPL to import», иначе IPL бокса Export
    (как _ipl_paths_for_import INU)."""
    out, seen = [], set()
    for p in settings.get('ipl_sync_list', []) or []:
        if p and os.path.isfile(p):
            k = os.path.normcase(os.path.normpath(p))
            if k not in seen:
                seen.add(k)
                out.append(p)
    if out:
        return out
    p = settings.get('ipl_path', '') or ''
    return [p] if p and os.path.isfile(p) else []


def _explicit_ides():
    """IDE, выбранные явно: бокс IDE (вкладка Export) + найденные Find IDE."""
    out, seen = [], set()
    for p in [settings.get('ide_path', '') or ''] + list(settings.get('found_ides', []) or []):
        if p and os.path.isfile(p):
            k = os.path.normcase(os.path.abspath(p))
            if k not in seen:
                seen.add(k)
                out.append(p)
    return out


def _is_binary_ipl(path):
    try:
        with open(path, 'rb') as f:
            return f.read(4) == b'bnry'
    except OSError:
        return False


def _game_imgs(root):
    """Все .img папки игры в порядке загрузки игрой: models/gta3.img,
    models/gta_int.img, IMG из gta.dat — затем остальные по алфавиту."""
    found = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d.lower() not in _SKIP_DIRS]
        found += [os.path.join(dp, f) for f in fn if f.lower().endswith('.img')]
    return order_archives(found, root)


def order_archives(paths, root):
    """Use the shared, game-specific archive load order."""
    from inu_gta_core.gta_dat import order_archives as ordered
    return ordered(paths, root)


def _read_ides(paths, models, source):
    """IDE → models {id: IdeObject/IdeAnim}, source {id: путь}. Первый файл,
    где есть ID, выигрывает (как _load_ide_into INU)."""
    from inu_gta_core.ide import read_ide
    for p in paths:
        try:
            ide = read_ide(p)
        except Exception as e:                         # noqa: BLE001
            print("[INU map] IDE %s: %r" % (os.path.basename(p), e))
            continue
        for o in list(ide.objects) + list(ide.anims):
            if o.model_id not in models:
                models[o.model_id] = o
                source[o.model_id] = p


# ── Find IMG / Find IDE ─────────────────────────────────────────────

def scan_img_for_ipl():
    """Find IMG: какие .img папки игры содержат DFF моделей из IPL."""
    from inu_gta_core.ipl import read_ipl
    from inu_gta_core.img import read_directory
    paths = _ipl_paths()
    if not paths:
        return 'ERROR', "Select an IPL file"
    root = settings.get('game_root', '') or ''
    if not os.path.isdir(root):
        return 'ERROR', "Set the game folder"
    names, unnamed = set(), set()
    for p in paths:
        try:
            ipl = read_ipl(p)
        except Exception as e:                         # noqa: BLE001
            print("[INU map] IPL %s: %r" % (os.path.basename(p), e))
            continue
        for inst in ipl.instances:
            if inst.model_name:
                names.add(inst.model_name.lower())
            elif inst.model_id > 0:
                unnamed.add(inst.model_id)
    if unnamed:
        # бинарный IPL: имён нет — берём из IDE игры по ID
        from inu_gta_core.gta_dat import list_ide_files
        models, _src = {}, {}
        _read_ides(list_ide_files(root), models, _src)
        names |= {models[i].model_name.lower() for i in unnamed if i in models}
    want = {n + '.dff' for n in names}
    if not want:
        settings.set('found_imgs', [])
        return 'WARNING', "The IPL has no models"
    found, covered = [], set()
    for p in _game_imgs(root):
        try:
            have = {e.name.lower() for e in read_directory(p)}
        except Exception as e:                         # noqa: BLE001
            print("[INU map] IMG %s: %r" % (os.path.basename(p), e))
            continue
        hit = want & have
        if hit:
            found.append(p)
            covered |= hit
    settings.set('found_imgs', found)
    return 'INFO', "Found IMG: %d · models covered %d/%d" % (len(found), len(covered),
                                                             len(want))


def scan_ide_for_ipl():
    """Find IDE: в каких .ide определены модели IPL (по Model ID). Список
    заодно становится «IDE to export» вкладки Export (как в INU)."""
    from inu_gta_core.ipl import read_ipl
    from inu_gta_core.ide import find_ides_for_model_ids
    from inu_gta_core.gta_dat import list_ide_files
    paths = _ipl_paths()
    if not paths:
        return 'ERROR', "Select an IPL file"
    root = settings.get('game_root', '') or ''
    if not os.path.isdir(root):
        return 'ERROR', "Set the IDE folder"
    ids = set()
    for p in paths:
        try:
            ids |= {i.model_id for i in read_ipl(p).instances if i.model_id > 0}
        except Exception as e:                         # noqa: BLE001
            print("[INU map] IPL %s: %r" % (os.path.basename(p), e))
    if not ids:
        settings.set('found_ides', [])
        return 'WARNING', "The IPL has no models"
    found = find_ides_for_model_ids(list_ide_files(root), ids)
    lst = sorted(found)
    settings.set('found_ides', lst)
    settings.set('ide_sync_list', list(lst))
    covered = set()
    for v in found.values():
        covered |= set(v)
    return 'INFO', "IDE found: %d · models covered %d/%d" % (len(found), len(covered),
                                                             len(ids))


# ── индексы архивов (кэш на диске: inu_max/cache.py) ─────────────────

def _txd_names_in_img(arch):
    """{txd: [текстуры]} всех .txd архива — только заголовки (без пикселей)."""
    from inu_gta_core.img import read_directory
    from ..adapter.texture import txd_names_from
    out = {}
    with open(arch, 'rb') as f:
        for e in read_directory(arch):
            low = e.name.lower()
            if low.endswith('.txd'):
                out[low[:-4]] = [n.lower() for n in txd_names_from(f, e.offset * _SECTOR)]
    return out


def _col_names_in_img(arch):
    """{запись .col: [[модель, смещение, длина], ...]} — по заголовкам
    моделей COL (сигнатура, размер, имя), без разбора геометрии."""
    import struct
    from inu_gta_core.img import read_directory
    magics = (b'COLL', b'COL2', b'COL3', b'COL4')
    out = {}
    with open(arch, 'rb') as f:
        for e in read_directory(arch):
            if not e.name.lower().endswith('.col'):
                continue
            base, end = e.offset * _SECTOR, (e.offset + e.size) * _SECTOR
            pos, models = 0, []
            while base + pos + 32 <= end:
                f.seek(base + pos)
                hdr = f.read(32)
                if len(hdr) < 32 or hdr[:4] not in magics:
                    break
                size = struct.unpack_from('<I', hdr, 4)[0]
                name = hdr[8:30].split(b'\x00', 1)[0].decode('ascii', 'replace')
                if size <= 0:
                    break
                models.append([name, pos, 8 + size])
                pos += 8 + size
            if models:
                out[e.name] = models
    return out


def _tex_root():
    """Папка PNG текстур: .inu_cache\\textures рядом с .max; сцена не
    сохранена — общий кэш INU в %LOCALAPPDATA%."""
    from ..adapter.selection import scene_file
    scene = scene_file()
    if scene:
        return os.path.join(os.path.dirname(scene), '.inu_cache', 'textures')
    return os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                        'INU_Tools_Max', 'tex_cache')


# ── импорт ───────────────────────────────────────────────────────────

class _GridInst:
    """Псевдо-строка IPL для импорта «только IDE» (сетка)."""

    def __init__(self, model_id, model_name, x, y):
        self.model_id, self.model_name = model_id, model_name
        self.interior, self.real_interior, self.lod_index = 0, 0, -1
        self.pos_x, self.pos_y, self.pos_z = float(x), float(y), 0.0
        self.rot_x = self.rot_y = self.rot_z = 0.0
        self.rot_w = 1.0
        self.scale_x = self.scale_y = self.scale_z = 1.0


def _grid(ide_models, step=30.0):
    """Все модели IDE сеткой (_instances_from_ide INU): по одной на имя."""
    seen, uniq = set(), []
    for mid, o in ide_models.items():
        k = (o.model_name or '').strip().lower()
        if k and k not in seen:
            seen.add(k)
            uniq.append((mid, o.model_name))
    cols = max(1, int(math.ceil(math.sqrt(len(uniq))))) if uniq else 1
    return [_GridInst(mid, name, (i % cols) * step, (i // cols) * step)
            for i, (mid, name) in enumerate(uniq)]


class _Model:
    """Шаблон модели для расстановок: узлы (порядок — родитель раньше
    детей), какие из них корни DFF / верхние / меши, матрицы верхних в
    пространстве модели, буферы user props мешей."""

    def __init__(self, nodes, roots, meshes, layer, placed=0):
        from ..adapter import map_scene
        self.nodes = list(nodes)
        self.roots = roots
        self.meshes = meshes
        ids = {int(pymxs.runtime.getHandleByAnim(n)) for n in self.nodes}
        self.top = [n.parent is None or int(pymxs.runtime.getHandleByAnim(n.parent)) not in ids
                    for n in self.nodes]
        self.model_tm = [map_scene.node_rows(n) if t and not r else None
                         for n, t, r in zip(self.nodes, self.top, self.roots)]
        self.bufs = [map_scene.read_buffer(n) if m else None
                     for n, m in zip(self.nodes, self.meshes)]
        self.main = next((i for i, m in enumerate(self.meshes) if m), 0)
        self.layer = layer
        self.placed = placed
        self.col_done = False


class _Importer:
    def __init__(self):
        g = settings.get
        self.load_lod = bool(g('map_load_lod', False))
        self.load_txd = bool(g('map_load_txd', False))
        self.load_col = bool(g('map_load_col', False))
        self.with_2dfx = bool(g('map_load_2dfx', False))
        self.vanilla = bool(g('import_weld_sharpen', False))
        self.game = g('game', 'SA')
        self.readers = {}
        self.txd_maps = {}
        self.col_bytes = {}
        self._tex_idx = None
        self._col_idx = None
        self.col_mat_cache = {}
        self.errors, self.notes = [], []
        self.n_col = 0
        self.n_col_empty = 0             # запись COL есть, но без геометрии

    # — архивы —
    def reader(self, arch):
        r = self.readers.get(arch)
        if r is None:
            from inu_gta_core.img import ImgReader
            r = ImgReader(arch)
            r.open()
            self.readers[arch] = r
        return r

    def close(self):
        for r in self.readers.values():
            try:
                r.close()
            except Exception:                          # noqa: BLE001
                pass
        self.readers = {}

    def read_entry(self, name_lower):
        hit = self.img_index.get(name_lower)
        if hit is None:
            return None, None
        arch, real = hit[0], hit[1]
        return self.reader(arch).read(real), arch

    # — текстуры —
    def txd_pngs(self, txd):
        """{текстура: png} TXD из IMG. PNG пишутся один раз: рядом лежит
        отпечаток записи архива и версии декода (.src) — не изменились, PNG
        берутся готовые."""
        from ..adapter.texture import extract_txd_bytes, _png_map, _safe_name, TEX_VER
        key = txd.lower()
        if key in self.txd_maps:
            return self.txd_maps[key]
        res = {}
        hit = self.img_index.get(key + '.txd')
        if hit is not None:
            arch, real, off, size = hit
            folder = os.path.join(self.tex_root, _safe_name(real[:-4]))
            stamp = "v%d|%s|%d|%d" % (TEX_VER, os.path.normcase(os.path.abspath(arch)),
                                      off, size)
            sp = os.path.join(folder, '.src')
            try:
                with open(sp, 'r', encoding='utf-8') as f:
                    same = f.read().strip() == stamp
            except OSError:
                same = False
            if same:
                res = _png_map(folder)
            if not res:
                try:
                    res = extract_txd_bytes(self.reader(arch).read(real), folder)
                    with open(sp, 'w', encoding='utf-8') as f:
                        f.write(stamp)
                except Exception as e:                 # noqa: BLE001
                    self.errors.append("%s: TXD not read (%s)" % (real, e))
        self.txd_maps[key] = res
        return res

    def tex_index(self):
        """{текстура: [txd]} по всем архивам (только выигравшие копии TXD)."""
        if self._tex_idx is None:
            from .. import cache
            idx = {}
            for arch in self.archives:
                data = cache.disk_get('img_tex_names.json', arch)
                if data is None:
                    try:
                        data = _txd_names_in_img(arch)
                    except Exception as e:             # noqa: BLE001
                        print("[INU map] textures of %s: %r" % (os.path.basename(arch), e))
                        data = {}
                    cache.disk_put('img_tex_names.json', arch, data)
                for txd, texs in data.items():
                    hit = self.img_index.get(txd + '.txd')
                    if hit is None or hit[0] != arch:
                        continue
                    for t in texs:
                        idx.setdefault(t, []).append(txd)
            self._tex_idx = idx
        return self._tex_idx

    def rescue(self, missing):
        """Недостающие текстуры — из других TXD архивов: жадно берём TXD,
        которые закрывают больше всего (как _rescue_textures_from_img INU)."""
        idx = self.tex_index()
        provides = {}
        for t in missing:
            for txd in idx.get(t, []):
                provides.setdefault(txd, set()).add(t)
        out, remaining = {}, set(missing)
        while remaining and provides:
            txd = max(provides, key=lambda k: len(provides[k] & remaining))
            if not provides[txd] & remaining:
                break
            got = self.txd_pngs(txd)
            for t in provides.pop(txd) & remaining:
                if t in got:
                    out[t] = got[t]
            remaining -= set(got)
        return out

    # — коллизия —
    def col_index(self):
        """{модель: (архив, запись, смещение, длина)} — модели COL всех
        архивов, включая библиотеки (первый архив выигрывает — как игра)."""
        if self._col_idx is None:
            from .. import cache
            idx = {}
            for arch in self.archives:
                data = cache.disk_get('img_col_names.json', arch)
                if data is None:
                    try:
                        data = _col_names_in_img(arch)
                    except Exception as e:             # noqa: BLE001
                        print("[INU map] COL of %s: %r" % (os.path.basename(arch), e))
                        data = {}
                    cache.disk_put('img_col_names.json', arch, data)
                for entry, models in data.items():
                    for m, off, ln in models:
                        if m:
                            idx.setdefault(m.lower(), (arch, entry, off, ln))
            self._col_idx = idx
        return self._col_idx

    def col_blob(self, arch, entry):
        """Байты записи .col (кэш на импорт)."""
        key = (arch, entry.lower())
        data = self.col_bytes.get(key)
        if data is None:
            data = self.reader(arch).read(entry) or b''
            self.col_bytes[key] = data
        return data

    def build_col(self, name, base):
        """Объекты коллизии модели (в пространстве модели) или []."""
        from inu_gta_core.col import read_col
        from .dff_read import col_models
        from ..adapter import scene_build
        hit = self.col_index().get(name.lower())
        if hit is None:
            return []
        arch, entry, off, ln = hit
        data = self.col_blob(arch, entry)
        models = read_col(data[off:off + ln])
        if not models:
            return []
        meshes, prims = col_models(models[:1], base=base)
        if not (meshes or prims):
            # пустая запись (только имя и границы) — в сцене не создаётся,
            # как при импорте .col
            self.n_col_empty += 1
            return []
        return list(scene_build.build_collision(meshes, prims, self.col_mat_cache))

    # — модель —
    def build_model(self, name, is_lod, ide):
        """Первая расстановка модели: DFF из архива → узлы сцены. Возвращает
        (_Model, узлы встроенной коллизии) или (None, причина)."""
        from inu_gta_core.dff import read_dff
        from inu_gta_core.ipl import strip_lod_marker
        from . import dff_read
        from ..adapter import scene_build
        data, arch = self.read_entry(name.lower() + '.dff')
        if not data:
            return None, 'noimg'
        clump = read_dff(data)
        plan = dff_read.plan(clump, name, vanilla=self.vanilla, with_2dfx=self.with_2dfx)
        # имена как в INU: <модель>_DFF / <модель>_LOD
        base = strip_lod_marker(name) if is_lod else name
        if base.upper().endswith('_DFF'):
            base = base[:-4]
        meshes = [n for n in plan.nodes if n.kind == 'MESH']
        if meshes:
            meshes[0].name = base + ('_LOD' if is_lod else '_DFF')
        for w in plan.warnings:
            print("[INU map] %s: %s" % (name, w))
        tex_map = {}
        if self.load_txd:
            needed = {m.texture.name.lower() for g in (clump.geometries or [])
                      for m in (g.materials or []) if m.texture is not None and m.texture.name}
            if needed:
                txd = (ide.txd_name if ide is not None and ide.txd_name else name)
                tex_map.update(self.txd_pngs(txd))
                missing = needed - set(tex_map)
                if missing:
                    tex_map.update(self.rescue(missing))
        created = scene_build.build(plan, tex_map)
        n_main = len(plan.nodes) + len(plan.fx)
        nodes, emb_col = created[:n_main], created[n_main:]
        roots = [n.parent < 0 for n in plan.nodes] + [False] * len(plan.fx)
        mesh_flags = [n.kind == 'MESH' for n in plan.nodes] + [False] * len(plan.fx)
        model = _Model(nodes, roots, mesh_flags, 'Map_LOD' if is_lod else 'Map_DFF')
        model.arch = arch
        return model, emb_col

    # — главный цикл —
    def run(self):
        from inu_gta_core.img import read_directory
        from inu_gta_core.ipl import read_ipl
        from inu_gta_core.game_versions import detect_game_from_img
        from inu_gta_core.gta_dat import list_ide_files
        from ..adapter import map_scene

        # архивы: основной IMG (если задан) + найденные Find IMG — в порядке
        # загрузки игрой (модель из нескольких — из первого)
        archives, seen = [], set()
        for p in [settings.get('img_path', '') or ''] + list(settings.get('found_imgs', []) or []):
            if p and os.path.isfile(p):
                k = os.path.normcase(os.path.abspath(p))
                if k not in seen:
                    seen.add(k)
                    archives.append(p)
        if not archives:
            return 'ERROR', "No IMG: press «Find IMG» or set an archive"
        archives = order_archives(archives, settings.get('game_root', '') or '')
        self.archives = archives

        # IDE и строки
        ide_models, ide_source = {}, {}
        instances, inst_src = [], {}
        ipl_paths = _ipl_paths()
        if ipl_paths:
            ide_path = settings.get('ide_path', '') or ''
            root = settings.get('game_root', '') or ''
            if ide_path and os.path.isfile(ide_path):
                _read_ides([ide_path], ide_models, ide_source)
            elif os.path.isdir(root):
                _read_ides(list_ide_files(root), ide_models, ide_source)
            _read_ides([p for p in (settings.get('found_ides', []) or [])
                        if os.path.isfile(p)], ide_models, ide_source)
            for p in ipl_paths:
                try:
                    ipl = read_ipl(p)
                except Exception as e:                 # noqa: BLE001
                    self.errors.append("%s: %s" % (os.path.basename(p), e))
                    continue
                binary = _is_binary_ipl(p)
                base, n_local = len(instances), len(ipl.instances)
                for k, inst in enumerate(ipl.instances):
                    li = inst.lod_index
                    if binary:
                        inst.lod_index = -1          # указывает в другой (текстовый) IPL
                        if not inst.model_name and inst.model_id in ide_models:
                            inst.model_name = ide_models[inst.model_id].model_name
                    else:
                        inst.lod_index = base + li if 0 <= li < n_local else -1
                        inst_src[base + k] = (p, base)
                    instances.append(inst)
            if not instances:
                return 'ERROR', "The IPL has no placements (no inst rows)"
        else:
            ides = _explicit_ides()
            if not ides:
                return 'ERROR', "Set an IPL or IDE file"
            _read_ides(ides, ide_models, ide_source)
            instances = _grid(ide_models)
            if not instances:
                return 'ERROR', "The IDE has no models"

        # индекс имён всех архивов: первый архив (и первая запись) выигрывает
        self.img_index = {}
        multi = set()
        for p in archives:
            try:
                for e in read_directory(p):
                    k = e.name.lower()
                    hit = self.img_index.get(k)
                    if hit is None or (not hit[3] and e.size):
                        self.img_index[k] = (p, e.name, e.offset, e.size)
                    elif hit[0] != p and k.endswith('.dff'):
                        multi.add(k)
            except Exception as e:                     # noqa: BLE001
                self.errors.append("%s: %s" % (os.path.basename(p), e))
        self.multi_arch = multi
        self.tex_root = _tex_root()

        # игра по архиву (как maybe_set_game_from_import INU)
        scene = map_scene.scene_index()
        game_msg = ''
        try:
            from inu_gta_core.gta_dat import dat_game
            detected = dat_game(settings.get('game_root', '') or '') or detect_game_from_img(archives[0])
        except Exception:                              # noqa: BLE001
            detected = None
        if detected and detected != self.game:
            if not scene:
                settings.set('game', detected)
                self.game = detected
                game_msg = " → game=%s" % detected
            else:
                self.notes.append(
                    "Imported file = %s, but the active game = %s. Switch INU to «%s» — "
                    "otherwise export uses the wrong format." % (detected, self.game, detected))

        return self.place(instances, inst_src, ide_models, ide_source, scene, game_msg)

    def place(self, instances, inst_src, ide_models, ide_source, scene, game_msg='', *,
              title="INU: Import from IMG", skip_existing=True, reuse_scene=True,
              layer_of=None, noimg_text="no DFF in IMG", prof=None):
        """Расстановка строк IPL (общая для вкладки Import и Import Map).
        skip_existing — строки, уже стоящие в сцене (тот же ID, позиция,
        поворот), пропускаются; reuse_scene — модель берётся из сцены вместо
        повторного импорта; layer_of(idx, inst, is_lod) → (слой модели, слой
        коллизии) — иначе Map_DFF / Map_LOD / Map_COL."""
        rt = pymxs.runtime
        from ..profiler import Profiler
        if prof is None:
            prof = Profiler('', enabled=False)
        from inu_gta_core.ipl import lod_instance_indices, is_lod_name, strip_lod_marker
        from ..adapter import map_scene
        from . import map_link as ML

        # что уже стоит в сцене: повторы строк пропускаются, модели берутся
        # из сцены вместо повторного импорта
        placed_by_id, scene_models = {}, {}
        for mid, node, nm, pos, q in (scene if (skip_existing or reuse_scene) else ()):
            placed_by_id.setdefault(mid, []).append((pos, q, node))
            kind, base = classify_name(nm)
            scene_models.setdefault((kind, base.lower(), mid), node)

        def find_placed(mid, pos, q):
            for p2, q2, node in placed_by_id.get(mid, ()):
                if sum((a - b) ** 2 for a, b in zip(p2, pos)) <= 1e-6 \
                        and abs(sum(a * b for a, b in zip(q2, q))) >= 0.9999:
                    return node
            return None

        n = len(instances)
        lod_refs = lod_instance_indices(instances)
        models = {}
        inst_node = [None] * n
        imported = skip_lod = skip_placed = skip_noimg = skip_noname = reused = 0
        cancelled = False
        noimg_names = []

        rt.progressStart(title)
        rt.disableSceneRedraw()
        try:
            with pymxs.undo(False):
                for idx, inst in enumerate(instances):
                    if idx % 4 == 0:
                        if not rt.progressUpdate(100.0 * idx / max(n, 1)) \
                                or rt.getProgressCancel():
                            cancelled = True
                            break
                    name = inst.model_name or ''
                    if not name:
                        skip_noname += 1
                        continue
                    is_lod = idx in lod_refs or is_lod_name(name)
                    if is_lod and not self.load_lod:
                        skip_lod += 1
                        continue
                    rows = ML.inst_rows(inst)
                    q = _unit((inst.rot_x, inst.rot_y, inst.rot_z, inst.rot_w))
                    pos = (inst.pos_x, inst.pos_y, inst.pos_z)
                    hit = find_placed(inst.model_id, pos, q) if skip_existing else None
                    if hit is not None:
                        skip_placed += 1
                        inst_node[idx] = hit
                        continue
                    ide = ide_models.get(inst.model_id)
                    key = name.lower()
                    model = models.get(key)
                    emb_col = []
                    if model is None:
                        base = (strip_lod_marker(name) if is_lod else name).lower()
                        src = scene_models.get(('LOD' if is_lod else 'DFF', base, inst.model_id)) \
                            if reuse_scene else None
                        if src is not None:
                            tree = map_scene.descendants(src)
                            model = _Model(tree, [True] + [False] * (len(tree) - 1),
                                           [_is_mesh(o) for o in tree],
                                           'Map_LOD' if is_lod else 'Map_DFF', placed=1)
                            model.arch = ''
                            model.col_done = True
                            reused += 1
                        else:
                            try:
                                with prof.stage('build model', note=name):
                                    model, emb_col = self.build_model(name, is_lod, ide)
                            except Exception as e:     # noqa: BLE001
                                import traceback
                                traceback.print_exc()
                                self.errors.append("%s: %s" % (name, e))
                                models[key] = False
                                continue
                            if model is None:
                                skip_noimg += 1
                                if len(noimg_names) < 5:
                                    noimg_names.append(name)
                                models[key] = False
                                continue
                        models[key] = model
                    elif model is False:
                        skip_noimg += 1
                        continue
                    main_props, other_props = self.props(inst, idx, is_lod, ide, model,
                                                         inst_src, ide_source, ML)
                    texts = []
                    tm, mask = [], []
                    for i, node in enumerate(model.nodes):
                        if model.meshes[i] or model.roots[i]:
                            tm += rows
                            mask.append(True)
                        elif model.top[i]:
                            tm += ML.mul_rows(model.model_tm[i], rows)
                            mask.append(True)
                        else:
                            tm += [0.0] * 12
                            mask.append(False)
                        if model.meshes[i]:
                            d = dict(model.bufs[i])
                            d.update(main_props if i == model.main else other_props)
                            texts.append(map_scene.buffer_text(d))
                        else:
                            texts.append("")
                    owner = model.main + 1 if main_props.get('inu_ipl_uuid', '""') != '""' else 0
                    lay, col_lay = (layer_of(idx, inst, is_lod) if layer_of is not None
                                    else (model.layer, 'Map_COL'))
                    with prof.stage('place', note=name):
                        out = map_scene.place(model.nodes, model.placed > 0, tm, mask, texts,
                                              owner, lay)
                    model.placed += 1
                    inst_node[idx] = out[model.main] if out else None
                    imported += 1
                    # коллизия — один раз на модель, на её первой расстановке
                    if not model.col_done:
                        model.col_done = True
                        col_nodes = list(emb_col)
                        if self.load_col:
                            try:
                                with prof.stage('build COL', note=name):
                                    made = self.build_col(name, strip_lod_marker(name))
                                if made:
                                    self.n_col += 1
                                col_nodes += made
                            except Exception as e:     # noqa: BLE001
                                self.errors.append("%s: COL %s" % (name, e))
                        map_scene.move_to(col_nodes, rows, col_lay)

                # LOD-партнёры: строка модели → строка её LOD (lod_index)
                mains, lods = [], []
                for idx, inst in enumerate(instances):
                    main = inst_node[idx]
                    li = inst.lod_index
                    if main is not None and 0 <= li < n and li != idx \
                            and inst_node[li] is not None:
                        mains.append(main)
                        lods.append(inst_node[li])
                with prof.stage('LOD link'):
                    map_scene.link_lods(mains, lods)
        finally:
            rt.enableSceneRedraw()
            rt.progressEnd()
            self.close()
            map_scene.drop_empty_layers(('COL', '2DFX'))
        try:
            rt.clearSelection()
            rt.completeRedraw()
        except Exception:                              # noqa: BLE001
            pass

        # отчёт (как у INU)
        msg = "Imported: %d" % imported
        skipped = skip_lod + skip_placed + skip_noimg + skip_noname
        if skipped:
            why = []
            if skip_placed:
                why.append("%d already in scene" % skip_placed)
            if skip_lod:
                why.append("%d LOD — press «LOD» to import them" % skip_lod)
            if skip_noimg:
                why.append("%d %s" % (skip_noimg, noimg_text))
            if skip_noname:
                why.append("%d no model name (not in IDE)" % skip_noname)
            msg += ", skipped: %d (%s)" % (skipped, ", ".join(why))
        if self.errors:
            msg += ", errors: %d" % len(self.errors)
        msg += game_msg
        extra = []
        if reused:
            extra.append("Models taken from the scene: %d" % reused)
        if self.load_col:
            extra.append("Collision: %d model(s)%s" % (
                self.n_col, (", %d with an empty COL record (no geometry)" % self.n_col_empty)
                if self.n_col_empty else ""))
        if noimg_names:
            extra.append("%s, e.g.: %s" % (noimg_text[0].upper() + noimg_text[1:],
                                           ", ".join(noimg_names)))
        multi = [n for n in getattr(self, 'multi_arch', ()) if n[:-4] in models]
        if multi:
            extra.append("Models in several archives (taken from the first in the "
                         "game load order): %d" % len(multi))
        if cancelled:
            extra.insert(0, "Cancelled — objects already created stay in the scene.")
        for e in self.errors[:5]:
            print("[INU map] %s" % e)
        lines = [msg] + extra + list(getattr(self, 'infos', [])) + self.notes + \
            ["Error: " + e for e in self.errors[:5]]
        level = 'WARNING' if (self.errors or cancelled or self.notes) else 'INFO'
        return level, "\n".join(lines)

    def props(self, inst, idx, is_lod, ide, model, inst_src, ide_source, ML):
        """User properties расстановки: (главному мешу, остальным мешам)."""
        common = {'model_id': int(inst.model_id), 'interior_id': int(inst.interior),
                  'real_interior': int(getattr(inst, 'real_interior', 0) or 0)}
        if model.arch:
            common['img_target_file'] = model.arch
        if ide is not None:
            dd = float(ide.draw_distance)
            common['lod_draw_distance' if is_lod else 'draw_distance'] = dd
            common['ide_flags'] = int(ide.flags)
            common['txd_name'] = ide.txd_name
            src = ide_source.get(inst.model_id, '')
            common.update(ML.ide_stamp(src, ide) if src else ML.IDE_CLEAR)
        else:
            common.update(ML.IDE_CLEAR)
            if not any('inu_txd_name' in (b or {}) for b in model.bufs):
                common['txd_name'] = inst.model_name
        other = dict(common)
        other.update(ML.IPL_CLEAR)
        other['lod_object'] = 0
        main = dict(common)
        src = inst_src.get(idx)
        if src is not None and not is_lod:
            path, base = src
            li = inst.lod_index
            main.update(ML.IPL_CLEAR)
            main.update(ML.ipl_stamp(path, inst, li - base if li >= 0 else -1))
        else:
            main.update(ML.IPL_CLEAR)
        main['lod_object'] = 0
        return ML.buffer_props(main), ML.buffer_props(other)


def classify_name(name):
    """(тип, базовое имя) по одному имени (классификатор ядра без сцены)."""
    from inu_gta_core.model_classify import classify_model
    return classify_model(name, has_texture=lambda: True, inu_type='OBJ')


def _is_mesh(node):
    """Меш модели (не коллизия, не хелпер)."""
    rt = pymxs.runtime
    try:
        if rt.superClassOf(node) != rt.GeometryClass:
            return False
        t = rt.getUserProp(node, "inu_type")
        return str(t).strip('"').upper() not in ('COL', 'SHA') if t is not None else True
    except Exception:                                  # noqa: BLE001
        return False


def _unit(q):
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def import_from_img():
    imp = _Importer()
    try:
        return imp.run()
    finally:
        imp.close()
