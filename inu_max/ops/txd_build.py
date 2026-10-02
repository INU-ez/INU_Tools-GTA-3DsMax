# INU Tools (Max) — сборка TXD (порт tools/txd_export.py Blender-версии INU).
# Чистый Python + numpy: пиксели RGBA (сверху вниз) → мип-цепочка → DXT1
# (без альфы) / DXT3 (с альфой) → Texture Native → Texture Dictionary.
# Слияние с существующим TXD: одноимённые заменяются, новые дописываются,
# остальные копируются байт в байт (как update_txd INU).

import struct

import numpy as np

RW_TEXDICTIONARY = 0x16
RW_TEXTURENATIVE = 0x15
RW_STRUCT = 0x01
RW_EXTENSION = 0x03
PLATFORM_D3D8 = 8             # III / VC PC
PLATFORM_D3D9 = 9             # SA
RASTER_565 = 0x0200
RASTER_4444 = 0x0300
RASTER_MIPMAP = 0x8000
FILTER_LINEAR = 0x02
FILTER_LINEARMIPLINEAR = 0x06
ADDRESS_WRAP = 0x01
_ALPHA_TEST_REF = 128


def filter_flags(mip_count=1):
    flt = FILTER_LINEARMIPLINEAR if mip_count > 1 else FILTER_LINEAR
    return flt | (ADDRESS_WRAP << 8) | (ADDRESS_WRAP << 12)


def _hdr(kind, size, lib_id):
    return struct.pack('<III', kind, size, lib_id)


# ── пиксели ──────────────────────────────────────────────────────────

def load_rgba(path):
    """(h, w, 4) uint8, строки сверху вниз, или None (файл не читается)."""
    from ..qt import QtGui
    img = QtGui.QImage(path)
    if img.isNull():
        return None
    img = img.convertToFormat(QtGui.QImage.Format_RGBA8888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    buf = np.frombuffer(bytes(img.constBits())[:bpl * h], dtype=np.uint8)
    return buf.reshape(h, bpl)[:, :w * 4].reshape(h, w, 4).copy()


def has_alpha(pixels):
    return bool(pixels is not None and pixels[..., 3].min() < 255)


def _alpha_weighted_mean(blocks, axes):
    """Среднее RGBA с весом RGB по альфе: прозрачные тексели не тащат свой
    мусорный цвет в мипы (тёмные ореолы вокруг вырезов)."""
    f = blocks.astype(np.float32)
    rgb, a = f[..., :3], f[..., 3:4]
    wsum = a.sum(axis=axes)
    rgb_w = (rgb * a).sum(axis=axes)
    out_rgb = np.where(wsum > 0, rgb_w / np.maximum(wsum, 1.0), rgb.mean(axis=axes))
    out = np.concatenate([out_rgb, a.mean(axis=axes)], axis=-1)
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def downsample(pixels, width, height):
    new_w, new_h = max(1, width // 2), max(1, height // 2)
    if width > 1 and height > 1:
        r = pixels[:new_h * 2, :new_w * 2].reshape(new_h, 2, new_w, 2, 4)
        return _alpha_weighted_mean(r, (1, 3)), new_w, new_h
    if width > 1:
        r = pixels[:1, :new_w * 2].reshape(1, new_w, 2, 4)
        return _alpha_weighted_mean(r, (2,)), new_w, new_h
    if height > 1:
        r = pixels[:new_h * 2, :1].reshape(new_h, 2, 1, 4)
        return _alpha_weighted_mean(r, (1,)), new_w, new_h
    return None, 0, 0


def _pad_edge(pixels, width, height, new_w, new_h):
    """Дополнение повтором правого/нижнего края до new_w × new_h."""
    if new_w == width and new_h == height:
        return pixels
    padded = np.zeros((new_h, new_w, 4), dtype=np.uint8)
    padded[:height, :width] = pixels
    if width < new_w:
        padded[:height, width:] = pixels[:, -1:, :]
    if height < new_h:
        padded[height:, :] = padded[height - 1:height, :]
    return padded


def dilate_alpha_edges(pixels, max_iters=32, opaque_thresh=1):
    """RGB (полу)прозрачных текселей ← цвет ближайших непрозрачных; альфа не
    меняется. 250 — для alpha-test (убирает белую кайму), 1 — для blend."""
    h, w, _ = pixels.shape
    rgb = pixels[..., :3].astype(np.float32)
    known = pixels[..., 3] >= opaque_thresh
    if known.all() or not known.any():
        return pixels
    for _ in range(max_iters):
        acc = np.zeros((h, w, 3), dtype=np.float32)
        cnt = np.zeros((h, w), dtype=np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            k = np.roll(known, (dy, dx), axis=(0, 1)).astype(np.float32)
            acc += np.roll(rgb, (dy, dx), axis=(0, 1)) * k[..., None]
            cnt += k
        fill = (~known) & (cnt > 0)
        if not fill.any():
            break
        rgb[fill] = acc[fill] / cnt[fill][..., None]
        known = known | fill
    out = pixels.copy()
    out[..., :3] = np.clip(rgb + 0.5, 0, 255).astype(np.uint8)
    return out


def _is_binary_alpha(alpha, lo=24, hi=232, mid_frac=0.05):
    return np.count_nonzero((alpha > lo) & (alpha < hi)) <= mid_frac * alpha.size


def _alpha_coverage(alpha, ref=_ALPHA_TEST_REF):
    return float(np.count_nonzero(alpha >= ref)) / max(alpha.size, 1)


def _scale_alpha_for_coverage(pixels, target_cov, ref=_ALPHA_TEST_REF):
    """Множитель альфы мипа, при котором alpha-test проходит та же доля
    текселей, что у базы (листва не редеет вдали)."""
    if target_cov <= 0.0 or target_cov >= 1.0:
        return pixels
    alpha = pixels[..., 3].astype(np.float32)
    n = max(alpha.size, 1)
    lo, hi, best, best_err = 0.0, 8.0, 1.0, 2.0
    for _ in range(16):
        mid = 0.5 * (lo + hi)
        cov = float(np.count_nonzero(alpha * mid >= ref)) / n
        if abs(cov - target_cov) < best_err:
            best_err, best = abs(cov - target_cov), mid
        if cov < target_cov:
            lo = mid
        else:
            hi = mid
    out = pixels.copy()
    out[..., 3] = np.clip(alpha * best + 0.5, 0, 255).astype(np.uint8)
    return out


# ── Texture Native ───────────────────────────────────────────────────

def texture_native(name, pixels, use_alpha, platform=PLATFORM_D3D9,
                   lib_id=0x1803FFFF, backend='numpy'):
    """Полная секция 0x15 (с заголовком). backend: 'numpy' — range-fit на
    мипе 0 и быстрый bbox на остальных; 'numpy_fast' — bbox везде."""
    from inu_gta_core.dxt import encode_bc1, encode_bc2
    height, width = pixels.shape[:2]
    new_w, new_h = (width + 3) // 4 * 4, (height + 3) // 4 * 4
    pixels = _pad_edge(pixels, width, height, new_w, new_h)
    width, height = new_w, new_h

    preserve_cov, base_cov = False, 0.0
    if use_alpha:
        binary = _is_binary_alpha(pixels[..., 3])
        pixels = dilate_alpha_edges(pixels, opaque_thresh=250 if binary else 1)
        if binary:
            preserve_cov, base_cov = True, _alpha_coverage(pixels[..., 3])

    enc = encode_bc2 if use_alpha else encode_bc1
    mips, cur, w, h, i = [], pixels, width, height, 0
    while True:
        pw, ph = max(4, w), max(4, h)
        mips.append(enc(_pad_edge(cur, w, h, pw, ph),
                        fast=(backend == 'numpy_fast' or i > 0)))
        cur, w, h = downsample(cur, w, h)
        if cur is None:
            break
        if preserve_cov:
            cur = _scale_alpha_for_coverage(cur, base_cov)
        i += 1

    # DXT3 — 4444 / depth 16 (8888 / 32 — признак несжатого растра)
    raster = (RASTER_4444 if use_alpha else RASTER_565) | RASTER_MIPMAP
    body = bytearray(struct.pack('<II', platform, filter_flags(len(mips))))
    body += name[:31].encode('ascii', errors='replace').ljust(32, b'\x00')
    body += b'\x00' * 32
    body += struct.pack('<I', raster)
    if platform == PLATFORM_D3D8:
        body += struct.pack('<I', 1 if use_alpha else 0)       # hasAlpha
    else:
        body += b'DXT3' if use_alpha else b'DXT1'
    body += struct.pack('<HHBBB', width, height, 16, len(mips), 4)
    if platform == PLATFORM_D3D8:
        body += struct.pack('<B', 3 if use_alpha else 1)       # номер DXT
    else:
        body += struct.pack('<B', 0x09 if use_alpha else 0x08)
    for m in mips:
        body += struct.pack('<I', len(m)) + m
    inner = _hdr(RW_STRUCT, len(body), lib_id) + bytes(body) + _hdr(RW_EXTENSION, 0, lib_id)
    return _hdr(RW_TEXTURENATIVE, len(inner), lib_id) + inner


def assemble(sections, lib_id):
    """TXD из готовых секций 0x15 [(name, bytes)]."""
    tex = b''.join(s for _n, s in sections)
    st = _hdr(RW_STRUCT, 4, lib_id) + struct.pack('<HH', len(sections), 0)
    ext = _hdr(RW_EXTENSION, 0, lib_id)
    content = st + tex + ext
    return _hdr(RW_TEXDICTIONARY, len(content), lib_id) + content


def merge(base_bytes, new_sections):
    """(lib_id, sections, replaced, added) или None — base не TXD."""
    from inu_gta_core.txd import split_txd_sections
    base_lib, base = split_txd_sections(base_bytes)
    if base_lib is None:
        return None
    new_by = {n.lower(): (n, s) for n, s in new_sections}
    merged, used, replaced = [], set(), 0
    for n, s in base:
        k = n.lower()
        if k in new_by:
            merged.append(new_by[k])
            used.add(k)
            replaced += 1
        else:
            merged.append((n, s))
    added = 0
    for n, s in new_sections:
        if n.lower() not in used:
            merged.append((n, s))
            used.add(n.lower())
            added += 1
    return base_lib, merged, replaced, added
