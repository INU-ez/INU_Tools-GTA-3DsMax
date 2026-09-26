# INU Tools (Max) — проверки файлов для окна «Check» (как операторы INU
# file_scanner_ops / map_analyzer_ops / texture_browser_ops). Чистый Python
# поверх общего ядра inu_gta_core — без pymxs: всё работает с файлами.

import datetime
import os

_GAME_NAMES = {'SA': "San Andreas", 'VC': "Vice City", 'III': "GTA III"}


def _issue(i):
    """LintIssue ядра → dict для UI."""
    return dict(severity=str(i.severity), code=str(i.code), file=str(i.file or ''),
                where=str(i.where or ''), message=str(i.message or ''))


# ── Файлы: скан DFF / COL / TXD на диске ─────────────────────────────

def scan_files(folder, recursive=False, dff=True, col=True, txd=True,
               profile='STANDARD', game='SA', progress_cb=None):
    """Проблемы файлов папки (core.file_lint.scan_folder) → [dict]."""
    from inu_gta_core.file_lint import scan_folder
    issues = scan_folder(folder, scan_dff=dff, scan_col=col, scan_txd=txd,
                         recursive=recursive, progress_cb=progress_cb,
                         profile=profile, game=game)
    return [_issue(i) for i in issues]


def explain_file_code(code):
    from inu_gta_core.file_lint import explain
    try:
        return explain(code) or ''
    except Exception:                                  # noqa: BLE001
        return ''


# ── Карта: перекрёстная проверка IDE / IPL (+ IMG) ──────────────────

def gather_img_files(img_paths):
    """{архив: {имена записей}} для проверки моделей в IMG (как INU)."""
    from inu_gta_core.img import ImgReader
    out = {}
    for path in img_paths:
        try:
            with ImgReader(path) as reader:           # оглавление читается в open()
                out[path] = {e.name.lower() for e in reader.entries}
        except Exception:                              # noqa: BLE001
            continue
    return out


def collect_map_inputs(get):
    """Входы анализа по источнику (DAT / FOLDER / CUSTOM), как
    _collect_inputs в INU. get(key, default) — чтение настроек.
    Возвращает (ides, ipls, img_files, ошибка)."""
    mode = get('map_analyzer_mode', 'FOLDER')
    check_img = bool(get('map_analyzer_check_img', False))
    if mode == 'DAT':
        from inu_gta_core.gta_dat import parse_gta_dat, resolve_paths
        dat = get('map_analyzer_dat_path', '') or ''
        if not dat or not os.path.isfile(dat):
            return None, None, None, "Specify an existing .dat file"
        root = get('game_root', '') or os.path.dirname(os.path.dirname(dat))
        try:
            info = resolve_paths(root, parse_gta_dat(dat))
        except Exception as e:                         # noqa: BLE001
            return None, None, None, "DAT parse error: %s" % e
        ides = [p for p in info.ide_paths if os.path.isfile(p)]
        ipls = [p for p in info.ipl_paths if os.path.isfile(p)]
        imgs = [p for p in info.img_paths if os.path.isfile(p)]
        return ides, ipls, (gather_img_files(imgs) if check_img and imgs else None), None
    if mode == 'FOLDER':
        folder = get('map_analyzer_folder', '') or ''
        if not folder or not os.path.isdir(folder):
            return None, None, None, "Pick an existing folder"
        ides, ipls, imgs = [], [], []
        if get('map_analyzer_recursive', True):
            walk = ((r, f) for r, _d, fs in os.walk(folder) for f in fs)
        else:
            walk = ((folder, f) for f in os.listdir(folder))
        for r, fn in walk:
            low, p = fn.lower(), os.path.join(r, fn)
            if low.endswith('.ide'):
                ides.append(p)
            elif low.endswith('.ipl'):
                ipls.append(p)
            elif low.endswith('.img'):
                imgs.append(p)
        return ides, ipls, (gather_img_files(imgs) if check_img and imgs else None), None
    # CUSTOM
    ides = [p for p in (get('map_analyzer_custom_ides', []) or []) if os.path.isfile(p)]
    ipls = [p for p in (get('map_analyzer_custom_ipls', []) or []) if os.path.isfile(p)]
    if not ides and not ipls:
        return None, None, None, "IDE/IPL list is empty — add files with the '+' button"
    img_files = None
    if check_img:
        roots = {os.path.dirname(p) for p in ides + ipls}
        gr = get('game_root', '') or ''
        if gr and os.path.isdir(gr):
            roots.add(gr)
        imgs = [os.path.join(r2, f) for r in roots if os.path.isdir(r)
                for r2, _d, fs in os.walk(r) for f in fs if f.lower().endswith('.img')]
        img_files = gather_img_files(imgs) if imgs else None
    return ides, ipls, img_files, None


def _n(v):
    return "{:,}".format(int(v)).replace(",", " ")


def stats_lines(stats, game):
    """Сводка анализа карты (в INU — строки «Игра / Файлы / Модели /
    Проблемы / Прочее»)."""
    other = "Other:    %s interior • %s LOD pairs" % (_n(stats.interiors_used),
                                                     _n(stats.lod_pairs))
    if stats.lod_chain_broken:
        other += " • %s broken" % _n(stats.lod_chain_broken)
    return [
        "Game:     %s" % _GAME_NAMES.get(game, game),
        "Files:    IDE %s • IPL %s" % (_n(stats.ide_files), _n(stats.ipl_files)),
        "Models:   %s defined • %s placed" % (_n(stats.defined_models),
                                              _n(stats.placed_instances)),
        "Problems: %s orphans • %s unused • %s dup." % (
            _n(stats.orphan_placements), _n(stats.unused_models),
            _n(stats.duplicate_ids)),
        other,
    ]


def analyze_map(get, profile='STANDARD', game='SA'):
    """Анализ карты → (issues [dict], stats_lines, ошибка)."""
    ides, ipls, img_files, err = collect_map_inputs(get)
    if err:
        return [], [], err
    from inu_gta_core.map_lint import analyze_files
    try:
        issues, stats = analyze_files(ides, ipls, img_files=img_files,
                                      profile=profile, game=game)
    except Exception as e:                             # noqa: BLE001
        return [], [], "Analyze error: %s" % e
    return [_issue(i) for i in issues], stats_lines(stats, game), None


def explain_map_code(code):
    from inu_gta_core.map_lint import explain
    try:
        return explain(code) or ''
    except Exception:                                  # noqa: BLE001
        return ''


# ── Текстуры (TXD): индекс по источнику ─────────────────────────────

def scan_textures(get):
    """Метаданные текстур по источнику DAT / FOLDER / CUSTOM (как
    scan_textures в INU) → ([dict], ошибка)."""
    from inu_gta_core import texture_index as ti
    mode = get('texture_browser_source', 'DAT')
    img_paths, folder, ides, singles = [], '', [], []
    if mode == 'DAT':
        from inu_gta_core.gta_dat import parse_gta_dat, resolve_paths
        dat = get('map_analyzer_dat_path', '') or ''
        if not dat or not os.path.isfile(dat):
            return [], "Specify gta.dat file in Map Analyzer"
        root = get('game_root', '') or os.path.dirname(os.path.dirname(dat))
        try:
            info = resolve_paths(root, parse_gta_dat(dat))
        except Exception as e:                         # noqa: BLE001
            return [], "DAT parse error: %s" % e
        img_paths = [p for p in info.img_paths if os.path.isfile(p)]
        ides = [p for p in info.ide_paths if os.path.isfile(p)]
    elif mode == 'FOLDER':
        folder = get('texture_browser_folder', '') or ''
        if not folder or not os.path.isdir(folder):
            return [], "Pick an existing folder"
        img_paths = [os.path.join(r, f) for r, _d, fs in os.walk(folder)
                     for f in fs if f.lower().endswith('.img')]
    else:
        items = [p for p in (get('texture_browser_custom', []) or [])
                 if os.path.isfile(p)]
        if not items:
            return [], "File list is empty — add .img / .txd with the '+' button"
        img_paths = [p for p in items if p.lower().endswith('.img')]
        singles = [p for p in items if p.lower().endswith('.txd')]

    entries = []
    for ip in img_paths:
        entries.extend(ti.scan_img(ip))
    if folder:
        entries.extend(ti.scan_folder(folder, recursive=True))
    for p in singles:
        try:
            with open(p, 'rb') as f:
                raw = f.read()
        except OSError:
            continue
        entries.extend(ti.scan_txd_bytes(raw, p, os.path.basename(p).rsplit('.', 1)[0]))

    usage = {}
    if get('texture_browser_check_ide', True):
        ide_paths = ides or [p for p in (get('map_analyzer_custom_ides', []) or [])
                             if os.path.isfile(p)]
        if ide_paths:
            usage = ti.build_usage_map(ide_paths)
    out = []
    for e in entries:
        out.append(dict(archive_path=e.archive_path, txd_name=e.txd_name,
                        texture_name=e.texture_name, width=e.width,
                        height=e.height, depth=e.depth, num_levels=e.num_levels,
                        format_label=e.format_label,
                        usage_count=len(usage.get(e.txd_name.lower(), []))))
    return out, None


def decode_texture(entry):
    """Пиксели выбранной текстуры для превью: (rgba_bytes, w, h) или None."""
    from inu_gta_core.texture_index import decode_one_texture
    t = decode_one_texture(entry['archive_path'], entry['txd_name'],
                           entry['texture_name'])
    if t is None or not t.pixels:
        return None
    return bytes(t.pixels), t.width, t.height


# ── Отчёты .txt ─────────────────────────────────────────────────────

def _rows(issues):
    lines = []
    for i in issues:
        lines.append("[%s] %s" % (i['severity'], i['code']))
        lines.append("  file:    %s" % i['file'])
        if i['where']:
            lines.append("  where:   %s" % i['where'])
        lines.append("  message: %s" % i['message'].replace("\n", " | "))
        lines.append("")
    return lines


def _counts(issues):
    c = {'ERROR': 0, 'WARN': 0, 'INFO': 0}
    for i in issues:
        c[i['severity']] = c.get(i['severity'], 0) + 1
    return c


def save_scan_report(folder, issues, scanned_dir, recursive):
    """inu_lint_<время>.txt в папке folder (как scan_save_report INU)."""
    ts = datetime.datetime.now()
    c = _counts(issues)
    path = os.path.join(folder, "inu_lint_%s.txt" % ts.strftime("%Y-%m-%d_%H-%M-%S"))
    head = ["INU Tools — Binary File Lint Report",
            "Generated: %s" % ts.strftime("%Y-%m-%d %H:%M:%S"),
            "Scanned:   %s" % scanned_dir,
            "Recursive: %s" % bool(recursive),
            "Issues:    %d ERROR, %d WARN, %d INFO" % (c['ERROR'], c['WARN'], c['INFO']),
            "=" * 78, ""]
    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(head + _rows(issues)))
    return path


def save_map_report(folder, issues, stats):
    """inu_map_lint_<время>.txt (как map_analyzer_save_report INU)."""
    ts = datetime.datetime.now()
    c = _counts(issues)
    path = os.path.join(folder, "inu_map_lint_%s.txt"
                        % ts.strftime("%Y-%m-%d_%H-%M-%S"))
    head = ["INU Tools — Map Cross-Reference Report",
            "Generated: %s" % ts.strftime("%Y-%m-%d %H:%M:%S"),
            "Stats:     %s" % " | ".join(stats),
            "Issues:    %d ERROR, %d WARN, %d INFO" % (c['ERROR'], c['WARN'], c['INFO']),
            "=" * 78, ""]
    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(head + _rows(issues)))
    return path
