# INU Tools (Max) — текстуры: TXD (ядро) → PNG-файлы рядом со сценой.
#
# Max не встраивает картинки в .max (bitmap = ссылка на файл), поэтому
# декодированные ядром текстуры сохраняем на диск как PNG и подключаем
# bitmap'ами. PNG пишем сами (RGBA, через zlib) — без PIL/внешних пакетов.

import os
import re
import struct
import zlib

try:
    import numpy as _np
except Exception:                                      # noqa: BLE001
    _np = None


def _png_chunk(typ, data):
    return (struct.pack('>I', len(data)) + typ + data
            + struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff))


def write_png(path, rgba_bytes, w, h):
    """Записать RGBA (uint8, top-to-bottom, w*h*4) в PNG (8-бит, colortype 6)."""
    stride = w * 4
    if _np is not None:
        arr = _np.frombuffer(rgba_bytes, dtype=_np.uint8).reshape(h, stride)
        raw = _np.hstack([_np.zeros((h, 1), _np.uint8), arr]).tobytes()
    else:
        raw = bytearray()
        for y in range(h):
            raw.append(0)                              # filter: none
            raw += rgba_bytes[y * stride:(y + 1) * stride]
        raw = bytes(raw)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    idat = zlib.compress(raw, 6)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(_png_chunk(b'IHDR', ihdr))
        f.write(_png_chunk(b'IDAT', idat))
        f.write(_png_chunk(b'IEND', b''))


def _safe_name(name):
    return re.sub(r'[^A-Za-z0-9_.\-]', '_', name) or 'tex'


def extract_txd_bytes(txd_bytes, out_dir):
    """Декодировать TXD (байты) ядром и сохранить каждую текстуру в PNG в
    out_dir. Возвращает dict {имя_текстуры.lower(): путь_к_png}."""
    from inu_gta_core.txd import read_txd
    os.makedirs(out_dir, exist_ok=True)
    result = {}
    for tex in read_txd(txd_bytes):
        if not tex.pixels or tex.width <= 0 or tex.height <= 0:
            continue
        png = os.path.join(out_dir, _safe_name(tex.name) + '.png')
        try:
            write_png(png, tex.pixels, tex.width, tex.height)
            result[tex.name.lower()] = png
        except Exception as e:                         # noqa: BLE001
            print("[INU tex] write '%s' failed: %r" % (tex.name, e))
    return result


def extract_txd_file(txd_path, out_dir):
    with open(txd_path, 'rb') as f:
        return extract_txd_bytes(f.read(), out_dir)


def _all_txds(root, cap=20000):
    """[(путь, mtime, размер)] всех .txd в папке модели и подпапках.
    scandir: на Windows размер и дата приходят вместе со списком (без
    обращения к каждому файлу — важно на HDD). Папки «<модель>_textures»
    (наши PNG) не обходятся."""
    out, seen, stack = [], 0, [root]
    while stack:
        d = stack.pop()
        try:
            it = list(os.scandir(d))
        except OSError:
            continue
        for e in it:
            seen += 1
            if seen > cap:
                return out
            try:
                if e.is_dir():
                    n = e.name.lower()
                    if not (n.endswith('_textures') or n.startswith('_inu_probe')):
                        stack.append(e.path)
                elif e.name.lower().endswith('.txd'):
                    st = e.stat()
                    out.append((e.path, st.st_mtime, st.st_size))
            except OSError:
                continue
    return out


def txd_names_from(f, base=0):
    """Имена текстур TXD, начинающегося в открытом файле f со смещения base
    (отдельный .txd — 0, запись внутри IMG — её смещение), по ЗАГОЛОВКАМ
    (seek, без чтения пикселей)."""
    names = []
    try:
        f.seek(base)
        ct, _cs, _cl = struct.unpack('<III', f.read(12))
        if ct != 0x16:
            return []
        _ct, cs, _cl = struct.unpack('<III', f.read(12))
        count = struct.unpack('<H', f.read(4)[:2])[0]
        f.seek(cs - 4, 1)
        for _ in range(count):
            hdr = f.read(12)
            if len(hdr) < 12:
                break
            ct, cs, _cl = struct.unpack('<III', hdr)
            end = f.tell() + cs
            if ct == 0x15:
                f.read(12 + 8)                         # struct + platform, filter
                names.append(f.read(32).split(b'\x00', 1)[0]
                             .decode('ascii', 'replace'))
            f.seek(end)
    except (OSError, struct.error):
        pass
    return names


def _txd_names(path):
    """Имена текстур TXD по ЗАГОЛОВКАМ (seek, без чтения пикселей): ядро
    read_txd_texture_names читает файл целиком — на папке с тысячами .txd
    это гигабайты на каждый импорт."""
    try:
        with open(path, 'rb') as f:
            return txd_names_from(f, 0)
    except OSError:
        return []


# кэш имён текстур TXD: {путь: [mtime, размер, [имена]]} — в памяти и в
# %LOCALAPPDATA%\INU_Tools_Max	xd_names.json: заголовки каждого .txd читаются
# ОДИН раз (на холодном HDD 3000+ файлов — это ~10 с), дальше — только новые
# и изменённые
_MEM = {}


def _cache_path():
    return os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                        'INU_Tools_Max', 'txd_names.json')


def _load_cache():
    if not _MEM:
        try:
            import json
            with open(_cache_path(), 'r', encoding='utf-8') as f:
                _MEM.update(json.load(f))
        except (OSError, ValueError):
            pass
    return _MEM


def _save_cache():
    import json
    p = _cache_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(_MEM, f)
        os.replace(p + '.tmp', p)
    except OSError as e:
        print("[INU tex] txd cache not saved: %r" % (e,))


def _txd_index(root):
    """[(путь, {имена.lower()})] всех .txd папки модели."""
    cache = _load_cache()
    out, dirty = [], False
    for path, mtime, size in _all_txds(root):
        c = cache.get(path)
        if c is None or c[0] != mtime or c[1] != size:
            c = [mtime, size, [n.lower() for n in _txd_names(path)]]
            cache[path] = c
            dirty = True
        out.append((path, set(c[2])))
    if dirty:
        _save_cache()
    return out


def _png_map(out_dir):
    if not os.path.isdir(out_dir):
        return {}
    return {os.path.splitext(f)[0].lower(): os.path.join(out_dir, f)
            for f in os.listdir(out_dir) if f.lower().endswith('.png')}


def build_tex_map(dff_path, needed_names=None):
    """Собрать {имя_текстуры.lower(): путь_png} для модели через
    COVERAGE-подбор (как Blender): среди всех .txd в папке модели читаем
    только ИМЕНА текстур (быстро, без декода) и извлекаем те .txd, что
    покрывают текстуры материалов модели. Так нужный .txd находится сам,
    даже если назван не как .dff (rodeo06 → TXD rodeo05_law2).

    Плюс подхватываем уже лежащие PNG в <имя>_textures/."""
    root = os.path.dirname(dff_path)
    out_dir = os.path.join(
        root, os.path.splitext(os.path.basename(dff_path))[0] + "_textures")
    needed = set(n.lower() for n in (needed_names or []) if n)

    # PNG уже извлечены прошлым импортом — TXD не трогаем
    have = _png_map(out_dir)
    if needed and needed <= set(have):
        print("[INU tex] все %d текстур уже в %s" % (len(needed), out_dir))
        return have

    # (покрытие, путь, имена) по каждому .txd
    index = _txd_index(root)
    cands = [t for t, _n in index]
    scored = [(len(needed & names) if needed else 0, txd, names)
              for txd, names in index]

    n_txd = 0
    if needed:
        # Жадно: сначала .txd с наибольшим покрытием, добираем пока не
        # закроем все нужные текстуры (модель может тянуть из нескольких).
        scored.sort(key=lambda x: -x[0])
        remaining = needed - set(have)
        for cov, txd, names in scored:
            if not remaining:
                break
            if cov == 0 or not (names & remaining):
                continue
            try:
                extract_txd_file(txd, out_dir)
                n_txd += 1
            except Exception as e:                     # noqa: BLE001
                print("[INU tex] %s: %r" % (os.path.basename(txd), e))
            remaining -= names
    else:
        # needed неизвестно → извлекаем все .txd прямо в папке модели.
        for txd in cands:
            if os.path.dirname(txd) == root:
                try:
                    extract_txd_file(txd, out_dir)
                    n_txd += 1
                except Exception:                      # noqa: BLE001
                    pass

    tex_map = _png_map(out_dir)
    print("[INU tex] .txd найдено=%d, извлечено=%d → %d текстур в %s"
          % (len(cands), n_txd, len(tex_map), out_dir))
    return tex_map
