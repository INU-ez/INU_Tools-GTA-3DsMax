# INU Tools (Max) — окно Map IO: панели Blender-версии INU
#   «IDE / IPL / IMG» (вкладки Импорт / Экспорт / Карта),
#   «Object IDE / IPL» (свойства активного объекта),
#   «ID Manager» (пресеты Model ID).
# Состав, подписи (англ. из locale/eng.py INU) и условия показа — как в INU,
# оформление — роллауты Kam's (widgets.py). Операции записи пока заглушки
# (dispatch → «not implemented»); интерфейсные вещи работают: списки
# файлов, пути, счётчики IDE/IPL и районы (ядро inu_gta_core), статусы.

import math
import os

from PySide6 import QtWidgets, QtCore

from .style import C, BTN_H, icon
from .widgets import BuildMixin, FusedBlock, ElideLabel, Expander, icon_btn

# Флаги IDE (obj.inu.flag_* в INU): имя → (подпись, подсказка, бит). Какие
# показывать для игры — inu_gta_core.ide_flag_translate.flag_props_for_game.
IDE_FLAGS = {
    'flag_draw_last': ("Draw last (DRAW_LAST)",
                       "Transparent, draw last (4) · III/VC/SA", 4),
    'flag_additive': ("Additive (ADDITIVE)",
                      "Additive blending (8) · III/VC/SA", 8),
    'flag_no_zbuffer': ("No Z-buffer (NO_ZBUFFER_WRITE)",
                        "No write to Z-buffer (64) · III/VC/SA", 64),
    'flag_do_not_fade': ("No fade (DO_NOT_FADE)",
                         "No distance fade (2) · III/VC", 2),
    'flag_ignore_lighting': ("Dynamic light (IGNORE_LIGHTING)",
                             "Dynamic lighting instead of static (32) · III/VC", 32),
    'flag_is_subway': ("Subway tunnel (IS_SUBWAY)",
                       "Tunnel, visible only in cull zone (16) · III only", 16),
    'flag_is_road': ("Road (IS_ROAD)", "Road, wet reflections (1) · VC/SA", 1),
    'flag_no_shadows': ("No shadows (NO_SHADOWS)",
                        "Do not receive shadows (128) · VC/SA", 128),
    'flag_glass_1': ("Breakable glass (GLASS_TYPE_1)",
                     "Breakable glass (512) · VC/SA", 512),
    'flag_glass_2': ("Cracked glass (GLASS_TYPE_2)",
                     "Cracked glass (1024) · VC/SA", 1024),
    'flag_ignore_draw_dist': ("Ignore draw dist (IGNORE_DRAW_DIST)",
                              "Ignore draw distance (256) · VC only — typical "
                              "for LOD models", 256),
    'flag_garage_door': ("Garage door (GARAGE_DOOR)",
                         "Garage door (2048) · SA only", 2048),
    'flag_damagable': ("Damageable (DAMAGABLE)",
                       "Breakable ok/dam (4096) · SA only", 4096),
    'flag_is_tree': ("Tree (IS_TREE)", "Tree, sways in wind (8192) · SA only", 8192),
    'flag_is_palm': ("Palm (IS_PALM)", "Palm, sways in wind (16384) · SA only", 16384),
    'flag_no_flyer_col': ("No flyer collision (NO_FLYER_COL)",
                          "No collision with flying (32768) · SA only", 32768),
    'flag_is_tag': ("Graffiti tag (IS_TAG)",
                    "Graffiti tag (1048576) · SA only", 1048576),
    'flag_no_backface': ("Double-sided (NO_BACKFACE_CULL)",
                         "Draw both sides (2097152) · SA only", 2097152),
    'flag_breakable': ("Breakable statue (BREAKABLE_STATUE)",
                       "Breakable statue (4194304) · SA only", 4194304),
}

# Свойства объекта для IDE / IPL: ключ → значение по умолчанию (тип важен).
OBJ_DEFAULTS = {
    'model_id': 0, 'draw_distance': 299.0, 'lod_draw_distance': 999.0,
    'ide_flags': 0, 'interior_id': 0, 'lod_index': -1, 'breakable': False,
}


def _sel():
    """Модуль выделения сцены (адаптер Max); вне Max его функции бросают."""
    from ..adapter import selection
    return selection


def short_path(p, last=0):
    """Как _short_path INU: last>0 — последние N частей; иначе от «data»
    (без него — последние 3 части)."""
    if not p:
        return ''
    parts = [x for x in p.replace('/', '\\').split('\\') if x]
    if last > 0:
        return '\\'.join(parts[-last:])
    low = [x.lower() for x in parts]
    if 'data' in low:
        return '\\'.join(parts[low.index('data'):])
    return '\\'.join(parts[-3:])


_COUNTS = {}


def _counts(path, kind):
    """Счётчики секций IDE/IPL («objs: N, …» / «inst: N, …»), кэш по mtime."""
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return ''
    hit = _COUNTS.get((path, kind))
    if hit and hit[0] == mt:
        return hit[1]
    text = ''
    try:
        if kind == 'ide':
            from inu_gta_core.ide import read_ide
            f = read_ide(path)
            secs = (("objs", f.objects), ("anim", f.anims), ("cars", f.cars),
                    ("peds", f.peds), ("txdp", f.txdps))
        else:
            from inu_gta_core.ipl import read_ipl
            f = read_ipl(path)
            secs = (("inst", f.instances), ("cull", f.culls), ("grge", f.garages),
                    ("enex", f.enexs), ("pick", f.pickups), ("cars", f.cars),
                    ("jump", f.jumps), ("auzo", f.auzos), ("occl", f.occls),
                    ("zone", f.zones))
        text = ", ".join("%s: %d" % (n, len(v)) for n, v in secs if v)
    except Exception as e:                             # noqa: BLE001
        print("[INU] counts %s: %r" % (os.path.basename(path), e))
    _COUNTS[(path, kind)] = (mt, text)
    return text


def _open_file(path):
    """Открыть файл во внешней программе ОС (как open_text_file в INU)."""
    if path and os.path.exists(path):
        try:
            os.startfile(path)                         # noqa: S606 (Windows)
        except Exception as e:                         # noqa: BLE001
            print("[INU] open %s: %r" % (path, e))


def _err(lbl):
    lbl.setStyleSheet("color:%s;" % C['err'])
    return lbl


class _FileList(BuildMixin, QtWidgets.QWidget):
    """Список файлов в settings[key] (IPL/IDE для синхронизации): строка =
    короткий путь + открыть + убрать. Кнопки заголовка — у владельца."""

    changed = QtCore.Signal()

    def __init__(self, key, icon_name='text', parent=None):
        super().__init__(parent)
        self._key = key
        self._lay = QtWidgets.QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(1)
        self.rebuild()

    def items(self):
        return list(self._get(self._key, []) or [])

    def set_items(self, items):
        seen, out = set(), []
        for p in items:
            k = os.path.normcase(os.path.abspath(p))
            if k not in seen:
                seen.add(k)
                out.append(p)
        self._set(self._key, out)
        self.rebuild()
        self.changed.emit()

    def add(self, paths):
        self.set_items(self.items() + list(paths))

    def remove(self, index=-1):
        items = self.items()
        self.set_items([] if index < 0 else
                       [p for i, p in enumerate(items) if i != index])

    def rebuild(self):
        while self._lay.count():
            it = self._lay.takeAt(0)
            if it.widget() is not None:
                it.widget().deleteLater()
        for i, p in enumerate(self.items()):
            row = QtWidgets.QWidget()
            hl = QtWidgets.QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(3)
            lbl = ElideLabel(short_path(p))
            lbl.setToolTip(p)
            hl.addWidget(lbl, 1)
            hl.addWidget(FusedBlock([[
                icon_btn('text', "Open in text editor", lambda p=p: _open_file(p)),
                icon_btn('x', "Remove from the list", lambda i=i: self.remove(i)),
            ]]))
            self._lay.addWidget(row)


def _pick_files(owner, title, pattern, key):
    """Несколько файлов по маске через наше окно выбора."""
    from .file_dialog import INUFileDialog
    ext = pattern.upper().lstrip('*.')
    dlg = INUFileDialog(owner, title, mode='open_multi', key=key,
                        filters=[("%s (%s)" % (ext, pattern), [pattern]),
                                 ("All Files (*.*)", ["*"])],
                        accept_label="Add")
    return dlg.selected_files() if dlg.exec() else []


def _pick_folder_files(owner, title, pattern, key):
    """Все файлы по маске из выбранной папки (галочка «Include subfolders»,
    как у ipl_sync_add_folder в INU)."""
    from .file_dialog import INUFileDialog
    opts = QtWidgets.QWidget()
    ol = QtWidgets.QVBoxLayout(opts)
    ol.setContentsMargins(4, 4, 4, 4)
    sub = QtWidgets.QCheckBox("Include subfolders")
    sub.setChecked(True)
    sub.setToolTip("Search for %s in all subfolders too" % pattern.lstrip('*'))
    ol.addWidget(sub)
    ol.addStretch(1)
    dlg = INUFileDialog(owner, title, mode='folder', key=key, options=opts,
                        accept_label="Add")
    if not dlg.exec() or not dlg.selected_folder():
        return []
    root, ext = dlg.selected_folder(), pattern.lstrip('*').lower()
    out = []
    if sub.isChecked():
        for dp, _dn, fn in os.walk(root):
            out += [os.path.join(dp, f) for f in fn if f.lower().endswith(ext)]
    else:
        out = [os.path.join(root, f) for f in os.listdir(root)
               if f.lower().endswith(ext)]
    return sorted(out, key=lambda s: s.lower())


# ══ «IDE / IPL / IMG»: вкладки Импорт / Экспорт / Карта ═══════════════

class IdeIplImg(BuildMixin, QtWidgets.QWidget):
    """Панель INU «IDE / IPL / IMG»: ряд вкладок + одна видимая вкладка."""

    _TABS = (("Import", 'IMPORT', "Import models from the game"),
             ("Export", 'EXPORT', "Write IDE/IPL/IMG"),
             ("Map", 'MAP', "Full map import/export (gta.dat, binary/text "
                            "IPLs, regions)"))

    def __init__(self, dispatch, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        tabs, self._tab_group = self._seg_buttons(
            self._TABS, self._get('ide_ipl_mode', 'IMPORT'), self._on_tab)
        lay.addWidget(FusedBlock([tabs], height=BTN_H + 3))
        self.pages = {'IMPORT': ImportTab(dispatch), 'EXPORT': ExportTab(dispatch),
                      'MAP': MapTab(dispatch)}
        for p in self.pages.values():
            lay.addWidget(p)
        # один общий список IPL: «IPL для импорта» = «IPL для экспорта»
        self.pages['IMPORT'].ipls.changed.connect(self.pages['EXPORT'].ipls.rebuild)
        self.pages['IMPORT'].ipls.changed.connect(self.pages['EXPORT'].refresh)
        self.pages['EXPORT'].ipls.changed.connect(self.pages['IMPORT'].ipls.rebuild)
        self.pages['EXPORT'].ipls.changed.connect(self.pages['IMPORT'].refresh)
        self._on_tab(self._get('ide_ipl_mode', 'IMPORT'))

    def _on_tab(self, mode):
        self._set('ide_ipl_mode', mode)
        for m, p in self.pages.items():
            p.setVisible(m == mode)

    def on_selection(self, snap):
        self.pages['EXPORT'].on_selection(snap)
        self.pages['MAP'].refresh()


class ImportTab(BuildMixin, QtWidgets.QWidget):
    """Вкладка «Импорт»: папка игры, LOD/TXD/COL, IPL для импорта, найденные
    IMG и IDE, Import."""

    def __init__(self, dispatch, parent=None):
        super().__init__(parent)
        self._dispatch = dispatch
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        b = self._box()
        b.addLayout(self._labeled("Game folder", self._path_field(
            'game_root', 'folder', title="INU: Game folder",
            tip="GTA SA root folder", on_change=self.refresh), label_w=66))
        b.addWidget(FusedBlock([[
            self._tbtn("LOD", 'map_load_lod', False, "Load LOD models"),
            self._tbtn("TXD", 'map_load_txd', False,
                       "Load TXD textures with DFF"),
            self._tbtn("COL", 'map_load_col', False,
                       "Load collisions from cache on map import"),
        ]]))
        lay.addWidget(b.box)

        # IPL для импорта
        b = self._box()
        self.ipls = _FileList('ipl_sync_list')
        self._ipl_trash = icon_btn('trash', "Remove an IPL from the sync list "
                                   "(clears the whole list)",
                                   lambda: self.ipls.remove(-1))
        self._ipl_btns = FusedBlock([[
            icon_btn('add', "Add one or several IPL to the sync list. The file "
                     "dialog supports multi-selection (Ctrl/Shift).",
                     lambda: self.ipls.add(_pick_files(
                         self, "INU: Add IPL", "*.ipl", 'ipl_list'))),
            icon_btn('folder', "Add ALL .ipl from the chosen folder to the sync "
                     "list - by default including subfolders (recursively).",
                     lambda: self.ipls.add(_pick_folder_files(
                         self, "INU: Add IPL folder", "*.ipl", 'ipl_list'))),
            self._ipl_trash]])
        self._ex_ipl = Expander(self, 'show_import_ipl_list', True,
                                right=[self._ipl_btns])
        self._ex_ipl.body.addWidget(self.ipls)
        self.ipls.changed.connect(self.refresh)
        b.addWidget(self._ex_ipl)
        lay.addWidget(b.box)

        # IMG с моделями из IPL
        b = self._box()
        self._scan_img = icon_btn(
            'refresh', "Find IMG: read the chosen IPL and find in the game "
            "folder all the .img archives that actually hold the DFF of its "
            "models. Imports nothing.",
            lambda: self._dispatch("Find IMG by IPL", "scan_img_for_ipl"))
        self._ex_img = Expander(self, 'show_found_imgs', True,
                                right=[self._scan_img])
        self._imgs = QtWidgets.QVBoxLayout()
        self._imgs.setSpacing(0)
        self._ex_img.body.addLayout(self._imgs)
        b.addWidget(self._ex_img)
        lay.addWidget(b.box)

        # IDE с моделями из IPL
        b = self._box()
        self._scan_ide = icon_btn(
            'refresh', "Find IDE: read the chosen IPL and find the .ide files "
            "where its models are defined (by Model ID). Imports nothing.",
            lambda: self._dispatch("Find IDE by IPL", "scan_ide_for_ipl"))
        self._ex_ide = Expander(self, 'show_found_ides', True,
                                right=[self._scan_ide])
        self._ides = QtWidgets.QVBoxLayout()
        self._ides.setSpacing(1)
        self._ex_ide.body.addLayout(self._ides)
        b.addWidget(self._ex_ide)
        lay.addWidget(b.box)

        self._btn_import = QtWidgets.QPushButton("Import")
        self._btn_import.setIcon(icon('import'))
        self._btn_import.setFixedHeight(BTN_H + 9)
        self._btn_import.setToolTip(
            "Import all models from IMG: by IPL (with placement) OR by IDE (all "
            "defined models laid out in a grid). Geometry and TEXTURES are "
            "pulled from the IMG on-the-fly.")
        self._btn_import.clicked.connect(
            lambda: self._dispatch("Import from IMG", "import_from_img"))
        lay.addWidget(self._btn_import)
        self.refresh()

    def refresh(self):
        g = self._get
        n = len(self.ipls.items())
        self._ex_ipl.set_title("IPL to import (%d):" % n)
        self._ipl_trash.setVisible(n > 0)
        self._ipl_btns.update_corners()
        has_ipl = bool(n or g('ipl_path', ''))
        root = bool(g('game_root', ''))
        imgs = list(g('found_imgs', []) or [])
        ides = list(g('found_ides', []) or [])
        self._ex_img.set_title("IMG with IPL models (%d):" % len(imgs))
        self._ex_ide.set_title("IDE with this IPL's models (%d):" % len(ides))
        self._scan_img.setEnabled(has_ipl and root)
        self._scan_ide.setEnabled(has_ipl and root)
        for lay, paths, with_open in ((self._imgs, imgs, False),
                                      (self._ides, ides, True)):
            while lay.count():
                it = lay.takeAt(0)
                if it.widget() is not None:
                    it.widget().deleteLater()
            for p in paths:
                row = QtWidgets.QWidget()
                hl = QtWidgets.QHBoxLayout(row)
                hl.setContentsMargins(0, 0, 0, 0)
                lbl = ElideLabel(short_path(p, last=2))
                lbl.setToolTip(p)
                hl.addWidget(lbl, 1)
                if with_open:
                    hl.addWidget(icon_btn('text', "Open in text editor",
                                          lambda p=p: _open_file(p)))
                lay.addWidget(row)
        self._btn_import.setEnabled(has_ipl and bool(imgs or g('img_path', '')))


class ExportTab(BuildMixin, QtWidgets.QWidget):
    """Вкладка «Экспорт»: боксы IDE | IPL, выбранная модель (статусы IDE /
    IPL / IMG), IPL и IDE для экспорта, флаги IDE, «Дополнительно (IPL)»."""

    def __init__(self, dispatch, parent=None):
        super().__init__(parent)
        self._dispatch = dispatch
        self._snap = None
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        # A. IDE | IPL рядом
        cols = QtWidgets.QHBoxLayout()
        cols.setSpacing(3)
        self._files = {}
        for kind, key in (('IDE', 'ide_path'), ('IPL', 'ipl_path')):
            cols.addWidget(self._file_box(kind, key), 1)
        lay.addLayout(cols)

        # B. Выбранная модель
        b = self._box()
        self._sel_host = QtWidgets.QVBoxLayout()
        self._sel_host.setSpacing(2)
        b.addLayout(self._sel_host)
        lay.addWidget(b.box)

        # C/D. IPL и IDE для экспорта (тот же список IPL, что во вкладке Import)
        self.ipls = _FileList('ipl_sync_list')
        self.ides = _FileList('ide_sync_list')
        self._lists = {}
        for lst, kind, show_key in ((self.ipls, 'IPL', 'show_sync_ipl'),
                                    (self.ides, 'IDE', 'show_sync_ide')):
            ext = "*." + kind.lower()
            trash = icon_btn('trash', "Clear the %s sync list" % kind,
                             lambda l=lst: l.remove(-1))
            btns = FusedBlock([[
                icon_btn('refresh', "Sync %s → scene: linked models take their "
                         "row from their own %s." % (kind, kind),
                         lambda k=kind: self._dispatch(
                             "Sync from " + k, k.lower() + "_sync_from_file")),
                icon_btn('add', "Add one or several %s to the sync list" % kind,
                         lambda l=lst, k=kind, e=ext: l.add(_pick_files(
                             self, "INU: Add " + k, e, k.lower() + '_list'))),
                icon_btn('folder', "Add ALL %s from the chosen folder (with "
                         "subfolders)" % ext.lstrip('*'),
                         lambda l=lst, k=kind, e=ext: l.add(_pick_folder_files(
                             self, "INU: Add %s folder" % k, e,
                             k.lower() + '_list'))),
                trash]])
            ex = Expander(self, show_key, False, right=[btns])
            ex.body.addWidget(lst)
            lst.changed.connect(self.refresh)
            self._lists[kind] = (ex, trash, btns, lst)
            b = self._box()
            b.addWidget(ex)
            lay.addWidget(b.box)

        # E. Флаги IDE
        b = self._box()
        self._ex_flags = Expander(self, 'show_ide_flags_box', False, "IDE Flags")
        self.flags = IdeFlagsEditor()
        self._no_model = self._info("Select a model")
        self._ex_flags.body.addWidget(self._no_model)
        self._ex_flags.body.addWidget(self.flags)
        b.addWidget(self._ex_flags)
        lay.addWidget(b.box)

        # F. Дополнительно (IPL)
        b = self._box()
        ex = Expander(self, 'show_ipl_extra', False, "Advanced (IPL)")
        ex.body.addWidget(self._info("IPL sections (cull, paths, garages…):"))
        ex.body.addWidget(FusedBlock([[
            self._act("Import", "import_ipl_sections",
                      "Import IPL sections (cull, grge, enex, pick, cars, "
                      "auzo, jump, occl)"),
            self._act("Export", "export_ipl_sections",
                      "Export IPL sections from IPL_* groups into a file")]]))
        ex.body.addWidget(self._act(
            "Replace Empty with models", "replace_ipl_placeholders",
            "Replace IPL empty placeholders with scene models"))
        b.addWidget(ex)
        lay.addWidget(b.box)
        self.refresh()
        self.on_selection(None)

    def _act(self, label, key, tip, icon_name=None):
        btn = QtWidgets.QPushButton(label)
        btn.setFixedHeight(BTN_H)
        btn.setToolTip(tip)
        if icon_name:
            btn.setIcon(icon(icon_name))
        btn.clicked.connect(lambda _c=False: self._dispatch(label, key))
        return btn

    def _file_box(self, kind, key):
        """Бокс IDE / IPL: путь (кнопки открыть / выбрать), Add | Del,
        Export, счётчики секций файла."""
        b = self._box()
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(2)
        head.addWidget(QtWidgets.QLabel(kind), 1)
        op = icon_btn('text', "Open in text editor",
                      lambda k=key: _open_file(self._get(k, '')))
        pick = icon_btn('folder', "Choose a file and write the path into the "
                        "setting", lambda k=kind, s=key: self._pick_path(k, s))
        head.addWidget(FusedBlock([[op, pick]]))
        b.addLayout(head)
        path = ElideLabel()
        b.addWidget(path)
        ext = kind.lower()
        add = self._act("Add", "upsert_" + ext,
                        "Add: write/update the SELECTED models in the CHOSEN ."
                        + ext)
        dele = self._act("Del", "remove_" + ext,
                         "Del: remove the SELECTED models from the chosen ." + ext)
        b.addWidget(FusedBlock([[add, dele]]))
        b.addWidget(self._act("Export", "export_" + ext,
                              "Export: save the SELECTED models to a NEW ." + ext
                              + " file (save dialog)"))
        counts = self._info("")
        b.addWidget(counts)
        self._files[kind] = dict(key=key, open=op, path=path, add=add,
                                 dele=dele, counts=counts)
        return b.box

    def _pick_path(self, kind, key):
        from .file_dialog import INUFileDialog
        ext = kind.lower()
        cur = self._get(key, '')
        dlg = INUFileDialog(self, "INU: Pick %s file" % kind, mode='open',
                            key='pick_' + ext, accept_label="Select",
                            filters=[("GTA %s (*.%s)" % (kind, ext), ["*." + ext]),
                                     ("All Files (*.*)", ["*"])],
                            start_dir=os.path.dirname(cur) if cur else None)
        if dlg.exec() and dlg.selected_files():
            self._set(key, dlg.selected_files()[0])
            self.refresh()

    def refresh(self):
        has_sel = bool(self._snap and self._snap.get('n'))
        for kind, f in self._files.items():
            p = self._get(f['key'], '') or ''
            f['path'].setText(short_path(p, last=2) if p else "No file selected")
            f['path'].setToolTip(p)
            f['open'].setEnabled(bool(p))
            f['add'].setEnabled(has_sel)
            f['dele'].setEnabled(has_sel)
            cnt = _counts(p, kind.lower()) if p else ''
            f['counts'].setText(cnt)
            f['counts'].setVisible(bool(cnt))
        for kind, (ex, trash, btns, lst) in self._lists.items():
            n = len(lst.items())
            ex.set_title("%s to export%s" % (kind, " (%d)" % n if n else ""))
            trash.setVisible(n > 0)
            btns.update_corners()

    # — выбранная модель —
    def on_selection(self, snap):
        self._snap = snap
        while self._sel_host.count():
            it = self._sel_host.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        obj = snap.get('active') if snap else None
        if obj is None:
            self._sel_host.addWidget(self._info("No model selected"))
            self._no_model.setVisible(True)
            self.flags.setVisible(False)
        else:
            self._build_status(obj, snap)
            self._no_model.setVisible(False)
            self.flags.setVisible(True)
            self.flags.load(obj)
        self.refresh()

    def _status_row(self, text, ok, buttons):
        row = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(3)
        lbl = ElideLabel(text)
        if ok is False:
            _err(lbl)
        hl.addWidget(lbl, 1)
        hl.addWidget(FusedBlock([buttons]))
        self._sel_host.addWidget(row)

    def _main_btn(self, label, key, tip, enabled=True):
        b = self._act(label, key, tip)
        b.setFixedWidth(52)
        b.setEnabled(enabled)
        return b

    def _build_status(self, obj, snap):
        sel = _sel()
        gp = lambda k, d: sel.get_prop(obj, k, d)       # noqa: E731
        has_sel = bool(snap.get('n'))

        def slot():
            s = QtWidgets.QWidget()
            s.setFixedSize(BTN_H, BTN_H)
            return s

        # имя: [Check] [unlink]
        name_btns = [slot(), slot(),
                     self._main_btn("Check", "link_verify",
                                    "Verify both: IDE links (by model_id) + IPL "
                                    "links (the row is found by content)."),
                     icon_btn('trash', "Unlink from both files: IDE + IPL for "
                              "the selected objects.",
                              lambda: self._dispatch("Unlink IDE+IPL", "link_unlink"))]
        row = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(3)
        hl.addWidget(ElideLabel(str(obj.name)), 1)
        hl.addWidget(name_btns[0])
        hl.addWidget(name_btns[1])
        hl.addWidget(FusedBlock([name_btns[2:]]))
        self._sel_host.addWidget(row)

        # IDE
        mid = gp('model_id', 0)
        linked = gp('ide_linked', False)
        last_id = gp('ide_last_model_id', 0)
        ide_file = gp('ide_target_file', '')
        id_changed = linked and last_id > 0 and mid != last_id
        if id_changed:
            text, ok = "Not in IDE — Model ID changed (was %d)" % last_id, False
        elif not linked or mid <= 0:
            text, ok = "Not in IDE", None
        else:
            drift = []
            is_lod = snap.get('active_type') == 'LOD'
            cur = gp('lod_draw_distance' if is_lod else 'draw_distance', 299.0)
            if abs(cur - gp('ide_last_draw_distance', cur)) > 1e-3:
                drift.append("DrawDist")
            if gp('txd_name', '') != gp('ide_last_txd_name', ''):
                drift.append("TXD")
            if gp('ide_flags', 0) != gp('ide_last_flags', 0):
                drift.append("Flags")
            if drift:
                text, ok = "In IDE, changed: " + ", ".join(drift), False
            else:
                text, ok = "In IDE (%s)" % (os.path.basename(ide_file) or "?"), True
        o1 = icon_btn('text', "Open in text editor", lambda: _open_file(ide_file))
        o1.setEnabled(bool(ide_file) and has_sel)
        s1 = icon_btn('forward', "Sync from IDE: pull draw distance, TXD and "
                      "flags from the IDE into the object.",
                      lambda: self._dispatch("Sync from IDE", "ide_sync_from_file"))
        s1.setEnabled(linked and has_sel)
        a1 = self._main_btn("Add", "ide_sync_export",
                            "Export each model to its own IDE (the IDE it is "
                            "linked to).", has_sel)
        t1 = icon_btn('trash', "Remove the selected models from their IDE and "
                      "unlink them.",
                      lambda: self._dispatch("Unlink from IDE", "ide_remove_link"))
        t1.setEnabled(bool(ide_file) and linked and not id_changed and has_sel)
        self._status_row(text, ok, [o1, s1, a1, t1])

        # IPL
        uuid = gp('ipl_uuid', '')
        ipl_file = gp('ipl_target_file', '')
        if not uuid:
            if snap.get('active_type') == 'LOD':
                text, ok = "LOD — written together with its model", None
            else:
                text, ok = "Not in IPL", None
        else:
            text, ok = "In IPL (%s)" % (os.path.basename(ipl_file) or "?"), True
        o2 = icon_btn('text', "Open in text editor", lambda: _open_file(ipl_file))
        o2.setEnabled(bool(ipl_file) and has_sel)
        r2 = icon_btn('forward', "Restore coords from IPL (position and "
                      "rotation).",
                      lambda: self._dispatch("Restore coords from IPL",
                                             "ipl_restore_coords"))
        r2.setEnabled(bool(uuid) and has_sel)
        a2 = self._main_btn("Add", "ipl_sync_export",
                            "Update the coordinates of the selected models in "
                            "their own IPLs.", has_sel)
        t2 = icon_btn('trash', "Remove the selected objects from their IPL and "
                      "unlink them.",
                      lambda: self._dispatch("Remove from IPL", "ipl_remove_link"))
        t2.setEnabled(bool(uuid) and has_sel)
        self._status_row(text, ok, [o2, r2, a2, t2])

        # IMG
        img_file = gp('img_target_file', '')
        target = img_file or self._get('img_path', '')
        if img_file:
            text, ok = "In IMG (%s)" % (os.path.basename(img_file) or "?"), True
        else:
            text, ok = "Not in IMG", None
        o3 = icon_btn('archive', "Open the IMG archive",
                      lambda: _open_file(img_file))
        o3.setEnabled(bool(img_file) and has_sel)
        v3 = icon_btn('refresh', "Verify IMG: find which IMG archive of the "
                      "game folder holds the DFF of the selected models.",
                      lambda: self._dispatch("Verify IMG", "verify_img_link"))
        v3.setEnabled(has_sel)
        e3 = self._main_btn("Export", "export_to_img",
                            "Export DFF + TXD + COL directly into .img archive",
                            has_sel and bool(target))
        t3 = icon_btn('trash', "Remove selected models' DFF / TXD / COL from "
                      "the IMG archive",
                      lambda: self._dispatch("Remove from IMG", "remove_from_img"))
        t3.setEnabled(bool(img_file) and has_sel)
        self._status_row(text, ok, [o3, v3, e3, t3])


class IdeFlagsEditor(BuildMixin, QtWidgets.QWidget):
    """«IDE Flags» (число) + галочки флагов текущей игры для активного
    объекта. Галочки = биты числа (в обе стороны)."""

    def __init__(self, show_int=True, parent=None):
        super().__init__(parent)
        self._obj = None
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.spin = QtWidgets.QSpinBox()
        self.spin.setRange(0, 2 ** 31 - 1)
        self.spin.setFixedHeight(BTN_H)
        self.spin.setToolTip("Object flags in IDE")
        self.spin.valueChanged.connect(self._on_int)
        if show_int:
            lay.addLayout(self._labeled("IDE Flags", self.spin, label_w=58))
        self._box_w = QtWidgets.QWidget()
        self._grid = QtWidgets.QVBoxLayout(self._box_w)
        self._grid.setContentsMargins(2, 0, 0, 0)
        self._grid.setSpacing(2)
        lay.addWidget(self._box_w)
        self.cb = {}
        self.rebuild()

    def rebuild(self):
        """Галочки для игры проекта (ядро: flag_props_for_game)."""
        while self._grid.count():
            it = self._grid.takeAt(0)
            if it.widget() is not None:
                it.widget().deleteLater()
        self.cb = {}
        try:
            from inu_gta_core.ide_flag_translate import flag_props_for_game
            props = flag_props_for_game(self._get('game', 'SA'))
        except Exception:                              # noqa: BLE001
            props = list(IDE_FLAGS)
        for p in props:
            label, tip, bit = IDE_FLAGS[p]
            box = QtWidgets.QCheckBox(label)
            box.setToolTip(tip)
            box.toggled.connect(lambda v, b=bit: self._on_bit(b, v))
            self.cb[p] = box
            self._grid.addWidget(box)
        self._sync_boxes()

    def load(self, obj):
        self._obj = obj
        v = 0
        if obj is not None:
            try:
                v = _sel().get_prop(obj, 'ide_flags', 0)
            except Exception:                          # noqa: BLE001
                v = 0
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self._sync_boxes()

    def _sync_boxes(self):
        v = self.spin.value()
        for p, box in self.cb.items():
            box.blockSignals(True)
            box.setChecked(bool(v & IDE_FLAGS[p][2]))
            box.blockSignals(False)

    def _write(self, v):
        if self._obj is not None:
            try:
                _sel().set_prop([self._obj], 'ide_flags', int(v))
            except Exception as e:                     # noqa: BLE001
                print("[INU] write IDE flags: %r" % (e,))

    def _on_int(self, v):
        self._sync_boxes()
        self._write(v)

    def _on_bit(self, bit, on):
        v = self.spin.value()
        v = (v | bit) if on else (v & ~bit)
        self.spin.setValue(v)               # → _on_int → запись и галочки


class MapTab(BuildMixin, QtWidgets.QWidget):
    """Вкладка «Карта»: папка игры, LOD/2DFX/TXD/COL, без дублей, по IPL,
    район, бинарные и текстовые IPL, извлечение ресурсов, Import / Export
    Map, профайлер, BBox."""

    _bbox_on = False            # как map_ops._bbox_mode_active в INU

    def __init__(self, dispatch, parent=None):
        super().__init__(parent)
        self._dispatch = dispatch
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        b = self._box()
        b.addLayout(self._labeled("Game folder", self._path_field(
            'game_root', 'folder', title="INU: Game folder",
            tip="GTA SA root folder", on_change=self._fill_regions), label_w=66))
        b.addWidget(FusedBlock([[
            self._tbtn("LOD", 'map_load_lod', False, "Load LOD models"),
            self._tbtn("2DFX", 'map_load_2dfx', False, "Import 2DFX effects"),
            self._tbtn("TXD", 'map_load_txd', False, "Load TXD textures with DFF"),
            self._tbtn("COL", 'map_load_col', False,
                       "Load collisions from cache on map import"),
        ]]))
        lay.addWidget(b.box)

        lay.addWidget(FusedBlock([
            [self._tbtn("No duplicates", 'map_skip_dupes', False,
                        "Skip placements already in the scene: matching model "
                        "ID and position. Handy for importing an adjacent map "
                        "piece without spawning duplicates")],
            [self._tbtn("Group by IPL", 'map_group_by_ipl', True,
                        "Create a separate group per IPL file")]]))
        self._region = QtWidgets.QComboBox()
        self._region.setFixedHeight(BTN_H)
        self._region.setToolTip("Map region for import")
        self._region.currentIndexChanged.connect(self._on_region)
        lay.addWidget(self._region)

        # Бинарные / текстовые IPL
        self._lists = {}
        for key, title, show_key in (('binary_ipls', "Binary IPLs",
                                      'show_binary_ipls'),
                                     ('text_ipls', "Text IPLs", 'show_text_ipls')):
            scan = icon_btn('refresh', "Scan IMG archives and collect the list "
                            "of binary IPLs for the selected region",
                            lambda: self._dispatch("Scan IPLs", "scan_binary_ipls"))
            ex = Expander(self, show_key, False, right=[scan])
            host = QtWidgets.QVBoxLayout()
            host.setSpacing(1)
            ex.body.addLayout(host)
            b = self._box()
            b.addWidget(ex)
            lay.addWidget(b.box)
            self._lists[key] = (ex, host, title)

        # Извлечь ресурсы
        self._extract = QtWidgets.QPushButton("Extract resources")
        self._extract.setFixedHeight(BTN_H)
        self._extract.setToolTip(
            "Extract all DFF, COL and textures from GTA SA IMG archives. The "
            "cache is created in the .inu_cache folder next to your .max file, "
            "so the scene must be saved first.")
        self._extract.clicked.connect(
            lambda: self._dispatch("Extract resources", "extract_textures"))
        self._warn_save = _err(self._info("Save the .max first"))
        self._warn_save.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self._warn_save)
        lay.addWidget(self._extract)

        # Import / Export Map
        self._warn_cache = self._info("Cache is empty — map without models")
        self._warn_cache.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self._warn_cache)
        self._imp = QtWidgets.QPushButton("Import Map")
        self._imp.setToolTip("Import GTA SA map: auto-discover IDE/IPL/IMG from "
                             "the game folder")
        self._imp.clicked.connect(lambda: self._dispatch("Import Map", "import_map"))
        self._exp = QtWidgets.QPushButton("Export Map")
        self._exp.setToolTip("Export the current selection as a ready-to-ship "
                             "GTA SA map (DFF + COL + TXD + IDE + IPL in one "
                             "folder)")
        self._exp.clicked.connect(lambda: self._dispatch("Export Map", "map_export"))
        self._imp.setIcon(icon('import'))
        self._exp.setIcon(icon('export'))
        lay.addWidget(FusedBlock([[self._imp, self._exp]], height=BTN_H + 13))

        lay.addWidget(self._check(
            "Profiler (timings to console)", 'profile_enabled', False,
            "Measure the time of import operations and print per-stage "
            "timings to the MAXScript Listener. Useful for diagnosing "
            "slowdowns"))
        self._bbox = QtWidgets.QPushButton()
        self._bbox.setCheckable(True)
        self._bbox.setFixedHeight(BTN_H)
        self._bbox.setToolTip("Toggle every Map_ object between Bounding Box "
                              "and Textured")
        self._bbox.setChecked(MapTab._bbox_on)
        self._bbox.toggled.connect(self._on_bbox)
        self._on_bbox(MapTab._bbox_on)
        lay.addWidget(self._bbox)
        self._fill_regions()
        self.refresh()

    def _on_bbox(self, on):
        MapTab._bbox_on = bool(on)
        self._bbox.setText("BBox: ON" if on else "BBox: OFF")

    def _fill_regions(self):
        """«Entire Map» + районы из <папка игры>/data/gta.dat."""
        regions = []
        root = self._get('game_root', '') or ''
        dat = os.path.join(root, 'data', 'gta.dat')
        if root and os.path.isfile(dat):
            try:
                from inu_gta_core.gta_dat import parse_gta_dat, extract_regions
                regions = extract_regions(parse_gta_dat(dat))
            except Exception as e:                     # noqa: BLE001
                print("[INU] gta.dat: %r" % (e,))
        cur = self._get('map_region', 'ALL')
        self._region.blockSignals(True)
        self._region.clear()
        self._region.addItem("Entire Map", 'ALL')
        self._region.setItemData(0, "Import Entire Map", QtCore.Qt.ToolTipRole)
        for r in regions:
            self._region.addItem(r, r)
            self._region.setItemData(self._region.count() - 1, "Region: " + r,
                                     QtCore.Qt.ToolTipRole)
        i = self._region.findData(cur)
        self._region.setCurrentIndex(max(0, i))
        self._region.blockSignals(False)

    def _on_region(self, i):
        # как в INU: смена района очищает оба списка IPL
        self._set('map_region', self._region.itemData(i))
        self._set('binary_ipls', [])
        self._set('text_ipls', [])
        self.refresh()

    def refresh(self):
        for key, (ex, host, title) in self._lists.items():
            items = list(self._get(key, []) or [])
            ex.set_title("%s: %d" % (title, len(items)))
            while host.count():
                it = host.takeAt(0)
                w = it.widget()
                if w is not None:
                    w.deleteLater()
                elif it.layout() is not None:
                    it.layout().deleteLater()
            if not items:
                host.addWidget(self._info("List is empty — click Scan"))
                continue
            host.addWidget(FusedBlock([[
                self._all_btn("All", key, True), self._all_btn("None", key, False)]]))
            for idx, item in enumerate(items):
                name = item.get('name', '?')
                if key == 'text_ipls':
                    name = "%s  [%s]" % (name, "IMG" if item.get('img_source')
                                         else "loose")
                cb = QtWidgets.QCheckBox(name)
                cb.setChecked(bool(item.get('enabled', True)))
                cb.toggled.connect(lambda v, k=key, j=idx: self._toggle_item(k, j, v))
                host.addWidget(cb)
        saved = ''
        try:
            saved = _sel().scene_file()
        except Exception:                              # noqa: BLE001
            saved = ''
        cache = bool(saved) and os.path.isdir(
            os.path.join(os.path.dirname(saved), '.inu_cache'))
        self._warn_save.setVisible(not saved)
        self._extract.setEnabled(bool(saved))
        self._warn_cache.setVisible(bool(saved) and not cache)
        self._imp.setEnabled(bool(saved) and cache)
        self._exp.setEnabled(bool(saved))

    def _all_btn(self, label, key, on):
        b = QtWidgets.QPushButton(label)
        b.setToolTip("Enable or disable every IPL in the list at once")
        b.clicked.connect(lambda _c=False: self._set_all(key, on))
        return b

    def _set_all(self, key, on):
        items = [dict(it, enabled=on) for it in (self._get(key, []) or [])]
        self._set(key, items)
        self.refresh()

    def _toggle_item(self, key, idx, on):
        items = list(self._get(key, []) or [])
        if 0 <= idx < len(items):
            items[idx] = dict(items[idx], enabled=bool(on))
            self._set(key, items)


# ══ «Object IDE / IPL» ═════════════════════════════════════════════

class ObjectIdeIpl(BuildMixin, QtWidgets.QWidget):
    """Свойства активного объекта для IDE / IPL (как панель INU): Model ID,
    дистанции, флаги, Interior, LOD, Breakable, конфликт ID. Значения — user
    properties объекта «inu_*»."""

    def __init__(self, dispatch, parent=None):
        super().__init__(parent)
        self._dispatch = dispatch
        self._obj = None
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self._hint = self._info("Select a mesh object")
        lay.addWidget(self._hint)
        self._body = QtWidgets.QWidget()
        bl = QtWidgets.QVBoxLayout(self._body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(3)
        lay.addWidget(self._body)

        self._col_info = self._info("COL — no Model ID (bound to its DFF by name)")
        bl.addWidget(self._col_info)
        self._id = self._int_spin(0, 2 ** 31 - 1, "Model ID in GTA SA (IDE/IPL)",
                                  'model_id')
        self._row_id = self._labeled("Model ID", self._id, label_w=58)
        self._w_id = QtWidgets.QWidget()
        self._w_id.setLayout(self._row_id)
        bl.addWidget(self._w_id)
        self._dd = self._float_spin("Object draw distance (IDE)", 'draw_distance')
        self._w_dd = QtWidgets.QWidget()
        self._w_dd.setLayout(self._labeled("Draw Dist", self._dd, label_w=58))
        bl.addWidget(self._w_dd)
        self._ld = self._float_spin("LOD model draw distance (IDE)",
                                    'lod_draw_distance')
        self._w_ld = QtWidgets.QWidget()
        self._w_ld.setLayout(self._labeled("LOD Dist", self._ld, label_w=58))
        bl.addWidget(self._w_ld)

        self._apply = QtWidgets.QPushButton()
        self._apply.setFixedHeight(BTN_H)
        self._apply.setToolTip(
            "Set IDE properties (distances, Model ID, TXD, Interior, flags, COL "
            "Library) on every selected mesh object. Fields are prefilled from "
            "the active object.")
        self._apply.clicked.connect(
            lambda: self._dispatch("Apply to selected", "batch_set_distance"))
        bl.addWidget(self._apply)

        # Flags (число) + треугольник-разворот с галочками
        self.flags = IdeFlagsEditor(show_int=False)
        frow = QtWidgets.QHBoxLayout()
        frow.setContentsMargins(2, 0, 0, 0)
        frow.setSpacing(4)
        lab = QtWidgets.QLabel("Flags")
        lab.setFixedWidth(58)
        frow.addWidget(lab)
        frow.addWidget(self.flags.spin, 1)
        self._ex_flags = Expander(self, 'show_ide_flags', False, "")
        self._ex_flags.setFixedWidth(18)
        self._ex_flags.body.setContentsMargins(0, 0, 0, 0)
        frow.addWidget(self._ex_flags)
        bl.addLayout(frow)
        self._flags_box = self._box()
        self._flags_box.addWidget(self.flags)
        bl.addWidget(self._flags_box.box)
        self._ex_flags._hdr.clicked.connect(self._sync_flags_box)

        self._int = self._int_spin(0, 2 ** 31 - 1, "Interior ID for IPL "
                                   "(0 = exterior)", 'interior_id')
        self._lod = self._int_spin(-1, 2 ** 31 - 1, "LOD model index in IPL "
                                   "(-1 = no LOD)", 'lod_index')
        irow = QtWidgets.QHBoxLayout()
        irow.setContentsMargins(2, 0, 0, 0)
        irow.setSpacing(4)
        for text, w in (("Interior", self._int), ("LOD", self._lod)):
            lab = QtWidgets.QLabel(text)
            irow.addWidget(lab)
            irow.addWidget(w, 1)
        bl.addLayout(irow)
        b = self._box()
        self._brk = QtWidgets.QCheckBox("Breakable")
        self._brk.setToolTip("Mark geometry as breakable (writes chunk "
                             "0x253F2FD into the DFF)")
        self._brk.toggled.connect(lambda v: self._write('breakable', bool(v)))
        b.addWidget(self._brk)
        bl.addWidget(b.box)
        self._conflict = _err(self._info(""))
        bl.addWidget(self._conflict)
        self.on_selection(None)

    def _sync_flags_box(self):
        self._flags_box.box.setVisible(self._ex_flags.is_open())

    def _int_spin(self, lo, hi, tip, key):
        sp = QtWidgets.QSpinBox()
        sp.setRange(lo, hi)
        sp.setFixedHeight(BTN_H)
        sp.setToolTip(tip)
        sp.valueChanged.connect(lambda v, k=key: self._write(k, int(v)))
        return sp

    def _float_spin(self, tip, key):
        sp = QtWidgets.QDoubleSpinBox()
        sp.setLocale(QtCore.QLocale.c())      # точка, как в файлах GTA
        sp.setRange(0.0, 100000.0)
        sp.setDecimals(1)
        sp.setFixedHeight(BTN_H)
        sp.setToolTip(tip)
        sp.valueChanged.connect(lambda v, k=key: self._write(k, float(v)))
        return sp

    def _write(self, key, value):
        if self._obj is None:
            return
        try:
            _sel().set_prop([self._obj], key, value)
        except Exception as e:                         # noqa: BLE001
            print("[INU] write %s: %r" % (key, e))
        if key == 'model_id':
            self._update_conflict()

    def on_selection(self, snap):
        obj = snap.get('active') if snap else None
        self._obj = obj
        self._hint.setVisible(obj is None)
        self._body.setVisible(obj is not None)
        if obj is None:
            self.flags.load(None)
            return
        typ = snap.get('active_type', 'DFF')
        sel = _sel()
        vals = {k: sel.get_prop(obj, k, d) for k, d in OBJ_DEFAULTS.items()}
        for w, k in ((self._id, 'model_id'), (self._dd, 'draw_distance'),
                     (self._ld, 'lod_draw_distance'), (self._int, 'interior_id'),
                     (self._lod, 'lod_index')):
            w.blockSignals(True)
            w.setValue(vals[k])
            w.blockSignals(False)
        self._brk.blockSignals(True)
        self._brk.setChecked(vals['breakable'])
        self._brk.blockSignals(False)
        self._col_info.setVisible(typ == 'COL')
        self._w_id.setVisible(typ != 'COL')
        self._w_dd.setVisible(typ != 'LOD')
        self._w_ld.setVisible(typ == 'LOD')
        n = snap.get('n', 0)
        self._apply.setVisible(n > 1)
        self._apply.setText("Apply to selected (%d)" % n)
        self.flags.load(obj)
        self._sync_flags_box()
        self._update_conflict()

    def _update_conflict(self):
        if self._obj is None:
            self._conflict.setVisible(False)
            return
        try:
            mid = self._id.value()
            names = _sel().id_conflicts(self._obj, mid)
        except Exception:                              # noqa: BLE001
            names = []
        self._conflict.setText("ID %d: conflict with %s" % (self._id.value(),
                                                             ", ".join(names)))
        self._conflict.setVisible(bool(names))


# ══ «ID Manager» ═══════════════════════════════════════════════════

class IdManager(BuildMixin, QtWidgets.QWidget):
    """Менеджер Model ID (как панель INU): пресет, статистика, поиск,
    занятые / свободные ID, назначение выделенным, сервис."""

    _PER_PAGE = 20

    def __init__(self, dispatch, parent=None):
        super().__init__(parent)
        self._dispatch = dispatch
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        # пресет: список + новый / переименовать / удалить
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(3)
        self._preset = QtWidgets.QComboBox()
        self._preset.setFixedHeight(BTN_H)
        self._preset.setToolTip("Active file with the ID list")
        self._preset.currentIndexChanged.connect(self._on_preset)
        row.addWidget(self._preset, 1)
        row.addWidget(FusedBlock([[
            icon_btn('add', "Create a new ID preset", self._new_preset),
            icon_btn('edit', "Rename the active ID preset", self._rename_preset),
            icon_btn('remove', "Delete the active ID preset. The 'default' "
                     "preset cannot be removed", self._delete_preset)]]))
        lay.addLayout(row)

        b = self._box()
        srow = QtWidgets.QHBoxLayout()
        self._lb_free = QtWidgets.QLabel()
        self._lb_used = QtWidgets.QLabel()
        srow.addWidget(self._lb_free, 1)
        srow.addWidget(self._lb_used, 1)
        b.addLayout(srow)
        self._lb_next = QtWidgets.QLabel()
        b.addWidget(self._lb_next)
        lay.addWidget(b.box)

        self._search = QtWidgets.QLineEdit()
        self._search.setFixedHeight(BTN_H)
        self._search.setPlaceholderText("Search by ID or model name")
        self._search.setText(self._get('id_search', ''))
        self._search.textChanged.connect(self._on_search)
        lay.addWidget(self._search)

        self._used_box = self._box()
        lay.addWidget(self._used_box.box)
        self._nothing = _err(self._info("Nothing found"))
        lay.addWidget(self._nothing)
        self._free_box = self._box()
        self._free_box.addWidget(QtWidgets.QLabel("Free IDs:"))
        self._lb_free_list = self._info("")
        self._free_box.addWidget(self._lb_free_list)
        lay.addWidget(self._free_box.box)

        b = self._box()
        b.addWidget(QtWidgets.QLabel("Assign to selected:"))
        b.addWidget(FusedBlock([[
            self._act("Assign", "id_manager_auto_assign",
                      "Assign IDs to every selected object with Model ID = 0"),
            self._act("From ID...", "id_manager_assign_from",
                      "Assign sequential IDs to selected objects starting from a "
                      "given value")]]))
        b.addWidget(self._act("Clear selected", "id_manager_clear_selected",
                              "Clear Model ID on selected objects"))
        lay.addWidget(b.box)

        b = self._box()
        ex = Expander(self, 'show_id_service', False, "ID database & service")
        ex.body.addWidget(FusedBlock([
            [self._act("Sync", "id_manager_sync_scene",
                       "Add IDs from scene objects into the manager"),
             self._act("From Game", "id_manager_from_game",
                       "Load occupied IDs from GTA SA IDE files")],
            [self._act("Create ID", "id_manager_create",
                       "Fill the active ID preset (321-19999, all free)"),
             self._act("Extend FLA", "id_manager_extend",
                       "Add IDs (Fastman Limit Adjuster)")]]))
        ex.body.addWidget(self._act("Free phantoms", "id_manager_gc",
                                    "Free preset entries with no matching scene "
                                    "object"))
        ex.body.addWidget(FusedBlock([[
            self._act("Clear All", "id_manager_clear", "Clear all occupied IDs"),
            self._btn("Open ID File", "Open the active ID preset file in a text "
                      "editor", self._open_preset)]]))
        b.addWidget(ex)
        lay.addWidget(b.box)
        self._fill_presets()

    def _act(self, label, key, tip):
        return self._btn(label, tip, lambda: self._dispatch(label, key))

    @staticmethod
    def _btn(label, tip, slot):
        b = QtWidgets.QPushButton(label)
        b.setFixedHeight(BTN_H)
        b.setToolTip(tip)
        b.clicked.connect(lambda _c=False: slot())
        return b

    # — пресеты —
    def _presets(self):
        from .. import id_presets
        return id_presets

    def _fill_presets(self):
        ip = self._presets()
        cur = self._get('id_preset', ip.DEFAULT)
        self._preset.blockSignals(True)
        self._preset.clear()
        for n in ip.list_presets():
            self._preset.addItem(n, n)
        i = self._preset.findData(cur)
        self._preset.setCurrentIndex(max(0, i))
        self._preset.blockSignals(False)
        self._set('id_preset', self._preset.currentData())
        self.refresh()

    def _on_preset(self, i):
        self._set('id_preset', self._preset.itemData(i))
        self._set('id_page', 0)
        self.refresh()

    def _new_preset(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("INU: New ID Preset")
        v = QtWidgets.QVBoxLayout(dlg)
        name = QtWidgets.QLineEdit()
        name.setPlaceholderText("Name")
        name.setToolTip("Name of the new preset")
        copy = QtWidgets.QCheckBox("Copy from active")
        copy.setToolTip("Create the preset as a copy of the current active one")
        v.addWidget(name)
        v.addWidget(copy)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                        | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() and name.text().strip():
            ip = self._presets()
            src = self._get('id_preset', ip.DEFAULT) if copy.isChecked() else None
            if ip.create(name.text().strip(), src):
                self._set('id_preset', name.text().strip())
            self._fill_presets()

    def _rename_preset(self):
        ip = self._presets()
        cur = self._get('id_preset', ip.DEFAULT)
        new, ok = QtWidgets.QInputDialog.getText(self, "INU: Rename ID Preset",
                                                 "New name", text=cur)
        if ok and new.strip() and ip.rename(cur, new.strip()):
            self._set('id_preset', new.strip())
            self._fill_presets()

    def _delete_preset(self):
        ip = self._presets()
        cur = self._get('id_preset', ip.DEFAULT)
        if cur == ip.DEFAULT:
            QtWidgets.QMessageBox.information(
                self, "INU Tools", "The 'default' preset cannot be removed.")
            return
        if QtWidgets.QMessageBox.question(
                self, "INU Tools", "Delete ID preset '%s'?" % cur) \
                == QtWidgets.QMessageBox.Yes:
            ip.delete(cur)
            self._set('id_preset', ip.DEFAULT)
            self._fill_presets()

    def _open_preset(self):
        ip = self._presets()
        path = ip.preset_path(self._get('id_preset', ip.DEFAULT))
        if not os.path.isfile(path):
            ip.create(self._get('id_preset', ip.DEFAULT))
        _open_file(path)

    def _on_search(self, text):
        self._set('id_search', text)
        self._set('id_page', 0)
        self.refresh()

    # — списки —
    def refresh(self):
        ip = self._presets()
        free, used = ip.read(self._get('id_preset', ip.DEFAULT))
        self._lb_free.setText("Free: %d" % len(free))
        self._lb_used.setText("Used: %d" % len(used))
        self._lb_next.setText("Next free: %d" % free[0] if free else "")
        self._lb_next.setVisible(bool(free))

        q = (self._get('id_search', '') or '').strip()
        items = sorted(used.items())
        if q:
            items = [(i, n) for i, n in items
                     if (q in str(i) if q.isdigit() else q.lower() in n.lower())]
        lay = self._used_box
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
            elif it.layout() is not None:
                self._clear_layout(it.layout())
        self._nothing.setVisible(bool(used) and bool(q) and not items)
        self._used_box.box.setVisible(bool(items))
        if items:
            total = len(items)
            max_page = max(0, (total - 1) // self._PER_PAGE)
            page = min(int(self._get('id_page', 0) or 0), max_page)
            start = page * self._PER_PAGE
            chunk = items[start:start + self._PER_PAGE]
            lay.addWidget(QtWidgets.QLabel("In use:"))
            half = int(math.ceil(len(chunk) / 2.0))
            grid = QtWidgets.QGridLayout()
            grid.setHorizontalSpacing(4)
            grid.setVerticalSpacing(1)
            for k, (i, name) in enumerate(chunk):
                r, c = (k, 0) if k < half else (k - half, 2)
                lbl = ElideLabel("%d %s" % (i, name))
                grid.addWidget(lbl, r, c)
                grid.addWidget(icon_btn('x', "Release ID", lambda i=i: self._dispatch(
                    "Release ID %d" % i, "id_manager_release")), r, c + 1)
            lay.addLayout(grid)
            if total > self._PER_PAGE:
                # страницы: [◀] «21-40 / 57» [▶] (в INU — поле номера страницы)
                prev = self._btn("◀", "Previous page",
                                 lambda p=page: self._on_page(p - 1))
                nxt = self._btn("▶", "Next page",
                                lambda p=page: self._on_page(p + 1))
                mid = QtWidgets.QPushButton("%d-%d / %d" % (
                    start + 1, min(start + self._PER_PAGE, total), total))
                mid.setFocusPolicy(QtCore.Qt.NoFocus)
                prev.setEnabled(page > 0)
                nxt.setEnabled(page < max_page)
                prev.setFixedWidth(28)
                nxt.setFixedWidth(28)
                lay.addWidget(FusedBlock([[prev, mid, nxt]]))
        self._free_box.box.setVisible(bool(free))
        head = sorted(free)[:20]
        self._lb_free_list.setText(", ".join(str(i) for i in head)
                                   + ("..." if len(free) > 20 else ""))

    def _on_page(self, v):
        self._set('id_page', max(0, int(v)))
        QtCore.QTimer.singleShot(0, self.refresh)

    @staticmethod
    def _clear_layout(lay):
        while lay.count():
            it = lay.takeAt(0)
            if it.widget() is not None:
                it.widget().deleteLater()
