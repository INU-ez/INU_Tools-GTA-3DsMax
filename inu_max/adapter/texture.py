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
    """Все .txd в папке модели и подпапках (с лимитом на число файлов)."""
    out = []
    seen = 0
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            if f.lower().endswith('.txd'):
                out.append(os.path.join(dp, f))
            seen += 1
            if seen > cap:
                return out
    return out


def build_tex_map(dff_path, needed_names=None):
    """Собрать {имя_текстуры.lower(): путь_png} для модели через
    COVERAGE-подбор (как Blender): среди всех .txd в папке модели читаем
    только ИМЕНА текстур (быстро, без декода) и извлекаем те .txd, что
    покрывают текстуры материалов модели. Так нужный .txd находится сам,
    даже если назван не как .dff (rodeo06 → TXD rodeo05_law2).

    Плюс подхватываем уже лежащие PNG в <имя>_textures/."""
    from inu_gta_core.txd import read_txd_texture_names
    root = os.path.dirname(dff_path)
    out_dir = os.path.join(
        root, os.path.splitext(os.path.basename(dff_path))[0] + "_textures")
    needed = set(n.lower() for n in (needed_names or []) if n)

    cands = _all_txds(root)
    # (покрытие, путь, имена) по каждому .txd
    scored = []
    for txd in cands:
        try:
            names = set(n.lower() for n in read_txd_texture_names(txd))
        except Exception:                              # noqa: BLE001
            names = set()
        scored.append((len(needed & names) if needed else 0, txd, names))

    n_txd = 0
    if needed:
        # Жадно: сначала .txd с наибольшим покрытием, добираем пока не
        # закроем все нужные текстуры (модель может тянуть из нескольких).
        scored.sort(key=lambda x: -x[0])
        remaining = set(needed)
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

    tex_map = {}
    if os.path.isdir(out_dir):
        for f in os.listdir(out_dir):
            if f.lower().endswith('.png'):
                tex_map[os.path.splitext(f)[0].lower()] = os.path.join(out_dir, f)
    print("[INU tex] .txd найдено=%d, извлечено=%d → %d текстур в %s"
          % (len(cands), n_txd, len(tex_map), out_dir))
    return tex_map
