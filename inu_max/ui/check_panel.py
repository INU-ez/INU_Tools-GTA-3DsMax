# INU Tools (Max) — окно «Check»: панели Blender-версии INU
#   «Проверка» (инструменты сцены), «Анализ карты/файлов» (скан DFF/COL/TXD
#   и перекрёстная проверка IDE/IPL), «Текстуры (TXD)» (индекс текстур),
# и роллаут «Проверка перед экспортом» для окна DFF IO.
# Состав и подписи — как в INU; оформление — роллауты Kam's. Анализ файлов
# и текстур работает (ядро inu_gta_core через ops/checks.py); операции над

import os

from PySide6 import QtWidgets, QtCore, QtGui

from .style import C, BTN_H, icon, SEVERITY_COLOR
from .widgets import BuildMixin, FusedBlock, ElideLabel, Expander, icon_btn

_PROFILES = [
    ("Standard", 'STANDARD', "Calibrated for vanilla SA — out-of-the-box behavior"),
    ("FLA", 'FLA', "Assume Fastman92 Limit Adjuster is installed: suppress "
                   "warnings about ID > 19999, interior > 18, COL surface > 178"),
    ("Strict", 'STRICT', "Stricter thresholds: draw_distance > 800m, mat > 50, "
                         "vert > 16k, 2DFX > 100, texture > 512px. For QA builds"),
    ("Soft", 'LENIENT', "Hide all INFO levels. For legacy projects where "
                        "informational noise outweighs the signal"),
]


def _checks():
    from ..ops import checks
    return checks


def _sev_icon(sev):
    s = 'WARN' if sev == 'WARNING' else sev
    return icon({'ERROR': 'warning', 'WARN': 'warning'}.get(s, 'info'),
                SEVERITY_COLOR.get(s))


def _busy(fn):
    """Долгая операция с курсором ожидания."""
    QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
    try:
        return fn()
    finally:
        QtWidgets.QApplication.restoreOverrideCursor()


def _scene_file():
    try:
        from ..adapter import selection
        return selection.scene_file()
    except Exception:                                  # noqa: BLE001
        return ''


def _reveal(path):
    """Открыть папку файла в Проводнике (с выделением файла)."""
    if path and os.path.exists(path):
        import subprocess
        subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])


def _clear(lay):
    while lay.count():
        it = lay.takeAt(0)
        if it.widget() is not None:
            it.widget().deleteLater()
        elif it.layout() is not None:
            _clear(it.layout())


def _wrap_label(text, color=None):
    lbl = QtWidgets.QLabel(text)
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    if color:
        lbl.setStyleSheet("color:%s;" % color)
    return lbl


# ══ «Проверка» ══════════════════════════════════════════════════════

class CheckTools(BuildMixin, QtWidgets.QWidget):
    """Кнопки панели INU «Проверка»: проверка вершин / N-gon, сброс
    трансформ, LOD/COL → DFF, фрагментация, чанки, видимость DFF/LOD/COL/
    SHA, связи, тип объектов."""

    def __init__(self, dispatch, parent=None):
        super().__init__(parent)
        self._dispatch = dispatch
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        a = self._act
        self._frag = a("Fragment mesh", "fragment_mesh",
                       "Split a mesh into separate shard objects (grid / "
                       "clusters).", self._fragment_dialog)
        self._chunk = a("Split into chunks", "chunk_map",
                        "Split the map/mesh into square chunks on an XY grid. "
                        "Each chunk becomes a separate object Name_Chunk_X_Y; "
                        "UV, vertex colors and materials are kept. The original "
                        "is hidden (not deleted).", self._chunk_dialog)
        self._vis = []
        for t in ("DFF", "LOD", "COL", "SHA"):
            b = QtWidgets.QPushButton(t)
            b.setCheckable(True)
            b.setChecked(bool(self._get('hide_' + t.lower(), False)))
            b.setToolTip("Hide / show %s objects across the whole scene" % t)
            b.toggled.connect(lambda v, t=t, b=b: self._on_vis(t, b, v))
            self._on_vis(t, b, b.isChecked(), quiet=True)
            self._vis.append(b)
        self._links = QtWidgets.QPushButton()
        self._links.setCheckable(True)
        self._links.setChecked(bool(self._get('links_active', False)))
        self._links.setToolTip("Show / hide DFF ↔ LOD ↔ COL link lines")
        self._links.toggled.connect(self._on_links)
        self._on_links(self._links.isChecked(), quiet=True)
        lay.addWidget(FusedBlock([
            [a("Check Vertex", "check_geometry",
               "Check geometry for loose vertex and edges"),
             a("Check N-gon", "check_ngons",
               "Check geometry for N-gons (polygons with 5+ vertex)")],
            [a("Reset Transform", "reset_transform",
               "Reset Location and Rotation to (0, 0, 0) on selected meshes")],
            [a("LOD/COL → DFF", "snap_to_dff",
               "Snap LOD and COL to the DFF model's position")],
            [self._frag], [self._chunk], self._vis, [self._links]]))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QtWidgets.QLabel("Type:"))
        row.addWidget(FusedBlock([[
            a(t, "batch_set_type_" + t.lower(),
              "Batch switch object type (OBJ/COL/SHA/NON): " + desc)
            for t, desc in (("OBJ", "Object"), ("COL", "Collision"),
                            ("SHA", "Shadow"), ("NON", "Don't export"))]]), 1)
        lay.addLayout(row)
        self.on_selection(None)

    def _act(self, label, key, tip, slot=None):
        b = QtWidgets.QPushButton(label)
        b.setToolTip(tip)
        b.clicked.connect(lambda _c=False: (slot or
                                            (lambda: self._dispatch(label, key)))())
        return b

    def _on_vis(self, t, b, hidden, quiet=False):
        self._set('hide_' + t.lower(), bool(hidden))
        b.setIcon(icon('eye_off' if hidden else 'eye'))
        if not quiet:
            self._dispatch("%s: %s" % (t, "Hidden" if hidden else "Visible"),
                           "toggle_visibility")

    def _on_links(self, on, quiet=False):
        self._set('links_active', bool(on))
        self._links.setText("Links: ON" if on else "Links: OFF")
        if not quiet:
            self._dispatch("Model Links", "toggle_links")

    def on_selection(self, snap):
        has = bool(snap and snap.get('active') is not None)
        for b in (self._frag, self._chunk):
            b.setEnabled(has)

    # — диалоги (как invoke_props_dialog INU) —
    def _dialog(self, title, build):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        form = QtWidgets.QFormLayout(dlg)
        getters = build(dlg, form)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                        | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        return getters if dlg.exec() else None

    @staticmethod
    def _dspin(v, lo, hi, dec=2):
        s = QtWidgets.QDoubleSpinBox()
        s.setLocale(QtCore.QLocale.c())
        s.setRange(lo, hi)
        s.setDecimals(dec)
        s.setValue(v)
        return s

    @staticmethod
    def _ispin(v, lo, hi):
        s = QtWidgets.QSpinBox()
        s.setRange(lo, hi)
        s.setValue(v)
        return s

    def _fragment_dialog(self):
        def build(dlg, form):
            mode = QtWidgets.QComboBox()
            mode.addItem("Grid (X/Y step)", 'GRID')
            mode.setItemData(0, "Slice along a rectangular grid — like "
                                "object_explode", QtCore.Qt.ToolTipRole)
            mode.addItem("Clusters (N seeds)", 'SCATTER')
            mode.setItemData(1, "Group faces by nearest of N random seeds",
                             QtCore.Qt.ToolTipRole)
            xs, ys = self._dspin(2.0, 0.01, 100.0), self._dspin(2.0, 0.01, 100.0)
            cnt, seed = self._ispin(10, 2, 200), self._ispin(0, 0, 10 ** 6)
            name = QtWidgets.QLineEdit("model_frag")
            dele = QtWidgets.QCheckBox("Delete original")
            dele.setChecked(True)
            form.addRow("Mode", mode)
            form.addRow("X step", xs)
            form.addRow("Y step", ys)
            form.addRow("Shard count", cnt)
            form.addRow("Seed", seed)
            form.addRow("Shard name", name)
            form.addRow(dele)

            def sync():
                grid = mode.currentData() == 'GRID'
                for w, show in ((xs, grid), (ys, grid), (cnt, not grid),
                                (seed, not grid)):
                    w.setVisible(show)
                    form.labelForField(w).setVisible(show)
            mode.currentIndexChanged.connect(lambda _i: sync())
            sync()
            return dict(mode=mode.currentData, xstep=xs.value, ystep=ys.value,
                        count=cnt.value, seed=seed.value, name=name.text,
                        delete_original=dele.isChecked)
        getters = self._dialog("INU: Fragment Mesh", build)
        if getters is not None:
            self._dispatch("Fragment mesh", "fragment_mesh", **{k: fn() for k, fn in getters.items()})

    def _chunk_dialog(self):
        def build(dlg, form):
            size = self._dspin(180.0, 1.0, 1000.0, 1)
            size.setToolTip("Side length of a square chunk in meters")
            cut = QtWidgets.QComboBox()
            cut.addItem("Along grid lines", 'EXACT')
            cut.setItemData(0, "Physically splits polygons exactly on cell "
                               "borders", QtCore.Qt.ToolTipRole)
            cut.addItem("By existing geometry", 'TOPOLOGY')
            cut.setItemData(1, "Doesn't split polygons; assigns a face to a "
                               "chunk by its center", QtCore.Qt.ToolTipRole)
            mats = QtWidgets.QCheckBox("Separate materials")
            mats.setToolTip("Create unique material copies for each chunk")
            center = QtWidgets.QCheckBox("Center origin")
            center.setChecked(True)
            center.setToolTip("Set the pivot to the chunk's geometric center")
            hide = QtWidgets.QCheckBox("Hide original")
            hide.setChecked(True)
            hide.setToolTip("Hide the source mesh after slicing")
            form.addRow("Chunk size (m)", size)
            form.addRow("Cut mode", cut)
            form.addRow(mats)
            form.addRow(center)
            form.addRow(hide)
            return dict(size=size.value, cut=cut.currentData, separate_materials=mats.isChecked,
                        center_origin=center.isChecked, hide_original=hide.isChecked)
        getters = self._dialog("INU: Split into chunks", build)
        if getters is not None:
            self._dispatch("Split into chunks", "chunk_map", **{k: fn() for k, fn in getters.items()})


# ══ Список проблем (результаты скана / анализа) ══════════════════════

class _IssueList(QtWidgets.QListWidget):
    """Строка: иконка важности + «файл · первая строка сообщения».
    Фильтр «только ERROR» прячет строки, счётчики не меняет (как в INU)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextElideMode(QtCore.Qt.ElideRight)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setUniformItemSizes(True)
        self.setIconSize(QtCore.QSize(14, 14))
        self.setMinimumHeight(8 * 18 + 4)
        self.setMaximumHeight(8 * 18 + 4)
        self._issues = []

    def set_issues(self, issues, only_errors):
        self._issues = list(issues)
        self.clear()
        for i, it in enumerate(self._issues):
            first = (it['message'].split("\n", 1)[0])
            item = QtWidgets.QListWidgetItem(
                _sev_icon(it['severity']),
                "%s · %s" % (os.path.basename(it['file']) or '?', first))
            item.setData(QtCore.Qt.UserRole, i)
            item.setToolTip("[%s] %s\n%s" % (it['severity'], it['code'],
                                             it['message']))
            self.addItem(item)
            item.setHidden(only_errors and it['severity'] != 'ERROR')

    def current_issue(self):
        it = self.currentItem()
        if it is None:
            return None
        return self._issues[it.data(QtCore.Qt.UserRole)]


def _counts(issues):
    c = {'ERROR': 0, 'WARN': 0, 'INFO': 0}
    for i in issues:
        c[i['severity']] = c.get(i['severity'], 0) + 1
    return c


# ══ «Анализ карты/файлов» ═══════════════════════════════════════════

class FileAnalysis(BuildMixin, QtWidgets.QWidget):
    """Панель INU «Анализ карты/файлов»: вкладки Files (скан DFF/COL/TXD)
    и Map (перекрёстная проверка IDE/IPL)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_issues, self._map_issues, self._map_stats = [], [], []
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        tabs, self._tabs = self._seg_buttons(
            [("Files", 'FILES', "Scan DFF/COL/TXD on disk"),
             ("Map", 'MAP', "Cross-reference IDE/IPL")],
            self._get('analysis_mode', 'FILES'), self._on_tab)
        lay.addWidget(FusedBlock([tabs], height=BTN_H + 3))
        self._files = self._build_files()
        self._map = self._build_map()
        lay.addWidget(self._files)
        lay.addWidget(self._map)
        self._on_tab(self._get('analysis_mode', 'FILES'))

    def _on_tab(self, mode):
        self._set('analysis_mode', mode)
        self._files.setVisible(mode == 'FILES')
        self._map.setVisible(mode == 'MAP')

    def _profile_combo(self):
        return self._combo('lint_profile', _PROFILES, 'STANDARD',
                           "Standard (vanilla SA) / FLA / Strict / Soft")

    # — Files —
    def _build_files(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        lay.addWidget(self._path_field('scan_dir', 'folder', title="INU: Folder",
                                       placeholder="Folder with DFF/COL/TXD",
                                       tip="Folder with DFF/COL/TXD to scan"))
        lay.addWidget(self._check(
            "Include subfolders", 'scan_recursive', False,
            "Recursively walk subfolders. Off by default to avoid accidentally "
            "scanning the whole system"))
        lay.addWidget(FusedBlock([[self._tbtn(t, 'scan_' + t.lower(), True,
                                              "Scan %s files" % t)
                                   for t in ("DFF", "COL", "TXD")]]))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(self._profile_combo(), 1)
        row.addWidget(self._check("ERR", 'scan_only_errors', True,
                                  "Hide WARN/INFO in the list",
                                  self._refresh_files))
        lay.addLayout(row)
        scan = QtWidgets.QPushButton("Scan")
        scan.setIcon(icon('refresh'))
        scan.setFixedHeight(BTN_H + 6)
        scan.setToolTip("Scan selected folder for crash-prone patterns in "
                        "DFF/COL/TXD")
        scan.clicked.connect(self._scan_files)
        lay.addWidget(scan)

        self._f_box = self._box()
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(6)
        self._f_counts = QtWidgets.QLabel()
        head.addWidget(self._f_counts, 1)
        head.addWidget(icon_btn('x', "Clear results list", self._clear_files))
        self._f_box.addLayout(head)
        self._f_list = _IssueList()
        self._f_list.currentRowChanged.connect(lambda _r: self._detail_files())
        self._f_box.addWidget(self._f_list)
        self._f_detail = self._box()
        self._f_box.addWidget(self._f_detail.box)
        lay.addWidget(self._f_box.box)

        self._f_report = self._box()
        self._f_report.addWidget(QtWidgets.QLabel("Save report:"))
        self._f_report.addWidget(self._combo(
            'scan_report_target',
            [("Next to the .max", 'SCENE', "In the current scene's folder "
                                           "(.max must be saved)"),
             ("In the scan folder", 'SCAN', "To the same place the files came from"),
             ("Custom folder", 'CUSTOM', "Specify manually")],
            'SCENE', "Where to save the report", self._refresh_files))
        self._f_custom = self._path_field('scan_report_custom_path', 'folder',
                                          title="INU: Report folder",
                                          placeholder="Report folder")
        self._f_report.addWidget(self._f_custom)
        self._f_unsaved = _wrap_label("Scene not saved!", C['err'])
        self._f_report.addWidget(self._f_unsaved)
        save = QtWidgets.QPushButton("Save .txt")
        save.setIcon(icon('text'))
        save.setFixedHeight(BTN_H)
        save.setToolTip("Save scan result to .txt")
        save.clicked.connect(self._save_files_report)
        self._f_report.addWidget(save)
        lay.addWidget(self._f_report.box)
        self._f_empty = self._info("List empty — run a scan")
        lay.addWidget(self._f_empty)
        self._refresh_files()
        return w

    def _scan_files(self):
        folder = self._get('scan_dir', '') or ''
        if not folder or not os.path.isdir(folder):
            QtWidgets.QMessageBox.warning(self, "INU Tools", "Pick an existing folder")
            return
        types = [self._get('scan_' + t, True) for t in ('dff', 'col', 'txd')]
        if not any(types):
            QtWidgets.QMessageBox.warning(
                self, "INU Tools", "Enable at least one file type (DFF/COL/TXD)")
            return
        self._file_issues = _busy(lambda: _checks().scan_files(
            folder, recursive=bool(self._get('scan_recursive', False)),
            dff=types[0], col=types[1], txd=types[2],
            profile=self._get('lint_profile', 'STANDARD'),
            game=self._get('game', 'SA')))
        self._refresh_files()

    def _clear_files(self):
        self._file_issues = []
        self._refresh_files()

    def _refresh_files(self):
        issues = self._file_issues
        has = bool(issues)
        self._f_box.box.setVisible(has)
        self._f_report.box.setVisible(has)
        self._f_empty.setVisible(not has)
        c = _counts(issues)
        self._f_counts.setText("ERROR: %d   WARN: %d   total: %d"
                               % (c['ERROR'], c['WARN'], len(issues)))
        self._f_list.set_issues(issues, bool(self._get('scan_only_errors', True)))
        tgt = self._get('scan_report_target', 'SCENE')
        self._f_custom.setVisible(tgt == 'CUSTOM')
        self._f_unsaved.setVisible(tgt == 'SCENE' and not _scene_file())
        self._detail_files()

    def _detail_files(self):
        _clear(self._f_detail)
        it = self._f_list.current_issue()
        self._f_detail.box.setVisible(it is not None)
        if it is None:
            return
        head = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel("[%s] %s" % (it['severity'], it['code']))
        lbl.setStyleSheet("color:%s;" % SEVERITY_COLOR.get(it['severity'], C['text']))
        head.addWidget(lbl, 1)
        head.addWidget(icon_btn('folder', "Open file's folder in Explorer",
                                lambda p=it['file']: _reveal(p)))
        self._f_detail.addLayout(head)
        self._f_detail.addWidget(ElideLabel(os.path.basename(it['file']) or '?'))
        if it['where']:
            self._f_detail.addWidget(_wrap_label(it['where'], "#b8b8b8"))
        self._f_detail.addWidget(_wrap_label(it['message']))
        self._f_detail.addWidget(QtWidgets.QLabel("What it means:"))
        self._f_detail.addWidget(_wrap_label(
            _checks().explain_file_code(it['code'])
            or "(no description for this code)", "#b8b8b8"))

    def _save_files_report(self):
        tgt = self._get('scan_report_target', 'SCENE')
        if tgt == 'SCENE':
            scene = _scene_file()
            if not scene:
                QtWidgets.QMessageBox.warning(
                    self, "INU Tools", "Scene not saved — save the .max or "
                    "choose another report folder")
                return
            folder = os.path.dirname(scene)
        elif tgt == 'SCAN':
            folder = self._get('scan_dir', '') or ''
        else:
            folder = self._get('scan_report_custom_path', '') or ''
        if not folder or not os.path.isdir(folder):
            QtWidgets.QMessageBox.warning(self, "INU Tools",
                                          "Report folder not set or doesn't exist")
            return
        path = _checks().save_scan_report(folder, self._file_issues,
                                          self._get('scan_dir', ''),
                                          self._get('scan_recursive', False))
        QtWidgets.QMessageBox.information(self, "INU Tools", "Report saved: " + path)

    # — Map —
    def _build_map(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        lay.addWidget(self._combo(
            'map_analyzer_mode',
            [("DAT file", 'DAT', "gta.dat / default.dat / custom — follows the "
                                 "IDE/IPL/IMG lines"),
             ("Folder", 'FOLDER', "Scan all *.ide / *.ipl in the specified folder"),
             ("Custom paths", 'CUSTOM', "Manual list of IDE and IPL files")],
            'FOLDER', "Source", self._refresh_map_source))
        self._m_dat = self._path_field('map_analyzer_dat_path', 'open',
                                       filters=[("GTA dat (*.dat)", ["*.dat"]),
                                                ("All Files (*.*)", ["*"])],
                                       title="INU: .dat file",
                                       placeholder=".dat file")
        lay.addWidget(self._m_dat)
        self._m_folder = QtWidgets.QWidget()
        fl = QtWidgets.QHBoxLayout(self._m_folder)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(2)
        fl.addWidget(self._path_field('map_analyzer_folder', 'folder',
                                      title="INU: Folder with IDE/IPL",
                                      placeholder="Folder with IDE/IPL"), 1)
        rec = QtWidgets.QPushButton()
        rec.setCheckable(True)
        rec.setIcon(icon('folder'))
        rec.setFixedSize(BTN_H, BTN_H)
        rec.setStyleSheet("padding:0;")
        rec.setToolTip("Include subfolders: recursively walk subfolders in "
                       "FOLDER mode")
        rec.setChecked(bool(self._get('map_analyzer_recursive', True)))
        rec.toggled.connect(lambda v: self._set('map_analyzer_recursive', bool(v)))
        fl.addWidget(rec)
        lay.addWidget(self._m_folder)
        self._m_custom = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(self._m_custom)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(3)
        self._m_lists = {}
        for kind in ("IDE", "IPL"):
            b = self._box()
            head = QtWidgets.QHBoxLayout()
            head.addWidget(QtWidgets.QLabel("%s files:" % kind), 1)
            head.addWidget(icon_btn('add', "Add %s file to the Custom list" % kind,
                                    lambda k=kind: self._add_custom(k)))
            b.addLayout(head)
            rows = QtWidgets.QVBoxLayout()
            rows.setSpacing(1)
            b.addLayout(rows)
            self._m_lists[kind] = rows
            cl.addWidget(b.box)
        lay.addWidget(self._m_custom)
        lay.addWidget(self._check(
            "Check models in IMG", 'map_analyzer_check_img', False,
            "Auto-find all *.img in the scan area (DAT lines / FOLDER walk / "
            "CUSTOM parent dirs) and cross-check IDE entries — flag missing "
            "DFF/TXD"))
        lay.addLayout(self._labeled("Profile", self._profile_combo()))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(1)
        err = QtWidgets.QPushButton()
        err.setCheckable(True)
        err.setIcon(icon('warning'))
        err.setFixedSize(BTN_H + 6, BTN_H + 6)
        err.setStyleSheet("padding:0;")
        err.setToolTip("ERROR only: hide WARN/INFO in the list")
        err.setChecked(bool(self._get('map_analyzer_only_errors', True)))
        err.toggled.connect(lambda v: (self._set('map_analyzer_only_errors', bool(v)),
                                       self._refresh_map()))
        go = QtWidgets.QPushButton("Analyze")
        go.setIcon(icon('refresh'))
        go.setFixedHeight(BTN_H + 6)
        go.setToolTip("Cross-reference IDE/IPL files: orphans, conflicts, "
                      "missing assets")
        go.clicked.connect(self._analyze)
        row.addWidget(FusedBlock([[err, go]], height=BTN_H + 6), 1)
        lay.addLayout(row)

        self._m_box = self._box()
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(2)
        self._m_counts = QtWidgets.QLabel()
        head.addWidget(self._m_counts, 1)
        self._m_save = icon_btn('text', "Save analysis results to .txt "
                                "(next to the .max)", self._save_map_report)
        head.addWidget(self._m_save)
        head.addWidget(icon_btn('x', "Clear results list", self._clear_map))
        self._m_box.addLayout(head)
        self._m_stats = _wrap_label("", "#b8b8b8")
        self._m_box.addWidget(self._m_stats)
        self._m_list = _IssueList()
        self._m_list.currentRowChanged.connect(lambda _r: self._detail_map())
        self._m_box.addWidget(self._m_list)
        self._m_detail = self._box()
        self._m_box.addWidget(self._m_detail.box)
        lay.addWidget(self._m_box.box)
        self._refresh_map_source()
        self._refresh_map()
        return w

    def _refresh_map_source(self):
        mode = self._get('map_analyzer_mode', 'FOLDER')
        self._m_dat.setVisible(mode == 'DAT')
        self._m_folder.setVisible(mode == 'FOLDER')
        self._m_custom.setVisible(mode == 'CUSTOM')
        for kind, rows in self._m_lists.items():
            _clear(rows)
            key = 'map_analyzer_custom_%ss' % kind.lower()
            for i, p in enumerate(self._get(key, []) or []):
                r = QtWidgets.QHBoxLayout()
                r.setSpacing(2)
                lbl = ElideLabel(p)
                r.addWidget(lbl, 1)
                r.addWidget(icon_btn('x', "Remove an %s entry from the Custom "
                                     "list" % kind,
                                     lambda k=key, i=i: self._remove_custom(k, i)))
                rows.addLayout(r)

    def _add_custom(self, kind):
        from .file_dialog import INUFileDialog
        ext = kind.lower()
        dlg = INUFileDialog(self, "INU: Add %s" % kind, mode='open',
                            key='analyzer_' + ext, accept_label="Add",
                            filters=[("GTA %s (*.%s)" % (kind, ext), ["*." + ext])])
        if dlg.exec() and dlg.selected_files():
            key = 'map_analyzer_custom_%ss' % ext
            items = list(self._get(key, []) or [])
            p = dlg.selected_files()[0]
            if p in items:
                QtWidgets.QMessageBox.information(self, "INU Tools",
                                                  "Already in list: " + p)
                return
            self._set(key, items + [p])
            self._refresh_map_source()

    def _remove_custom(self, key, i):
        items = list(self._get(key, []) or [])
        if 0 <= i < len(items):
            del items[i]
        self._set(key, items)
        self._refresh_map_source()

    def _analyze(self):
        issues, stats, err = _busy(lambda: _checks().analyze_map(
            self._get, profile=self._get('lint_profile', 'STANDARD'),
            game=self._get('game', 'SA')))
        if err:
            QtWidgets.QMessageBox.warning(self, "INU Tools", err)
            return
        self._map_issues, self._map_stats = issues, stats
        self._refresh_map()

    def _clear_map(self):
        self._map_issues, self._map_stats = [], []
        self._refresh_map()

    def _refresh_map(self):
        issues = self._map_issues
        self._m_box.box.setVisible(bool(issues) or bool(self._map_stats))
        c = _counts(issues)
        self._m_counts.setText("E:%d  W:%d  Σ:%d" % (c['ERROR'], c['WARN'], len(issues)))
        self._m_save.setEnabled(bool(_scene_file()))
        self._m_stats.setText("\n".join(self._map_stats))
        self._m_stats.setVisible(bool(self._map_stats))
        self._m_list.set_issues(issues, bool(self._get('map_analyzer_only_errors', True)))
        self._detail_map()

    def _detail_map(self):
        _clear(self._m_detail)
        it = self._m_list.current_issue()
        self._m_detail.box.setVisible(it is not None)
        if it is None:
            return
        lbl = QtWidgets.QLabel("[%s] %s" % (it['severity'], it['code']))
        lbl.setStyleSheet("color:%s;" % SEVERITY_COLOR.get(it['severity'], C['text']))
        self._m_detail.addWidget(lbl)
        if it['file']:
            self._m_detail.addWidget(ElideLabel(os.path.basename(it['file'])))
        if it['where']:
            self._m_detail.addWidget(_wrap_label(it['where'], "#b8b8b8"))
        self._m_detail.addWidget(_wrap_label(it['message']))
        exp = _checks().explain_map_code(it['code'])
        if exp:
            self._m_detail.addWidget(_wrap_label(exp, "#b8b8b8"))

    def _save_map_report(self):
        scene = _scene_file()
        if not scene:
            QtWidgets.QMessageBox.warning(self, "INU Tools", "Scene not saved — "
                                          "save the .max, report is written next to it")
            return
        path = _checks().save_map_report(os.path.dirname(scene), self._map_issues,
                                         self._map_stats)
        QtWidgets.QMessageBox.information(self, "INU Tools", "Report saved: " + path)


# ══ «Текстуры (TXD)» ════════════════════════════════════════════════

class TextureBrowser(BuildMixin, QtWidgets.QWidget):
    """Панель INU «Текстуры (TXD)»: индекс текстур из gta.dat / папки /
    файлов, поиск, подробности и превью выбранной текстуры."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        tabs, self._tabs = self._seg_buttons(
            [("DAT", 'DAT', "From gta.dat via the scene paths — all *.img and *.txd"),
             ("Folder", 'FOLDER', "Scan a single folder recursively"),
             ("Files", 'CUSTOM', "Manually selected .img / .txd")],
            self._get('texture_browser_source', 'DAT'), self._on_source)
        lay.addWidget(FusedBlock([tabs]))
        self._dat = self._info("Uses gta.dat (DAT file of Map analysis + game "
                               "folder)")
        lay.addWidget(self._dat)
        self._folder = self._path_field('texture_browser_folder', 'folder',
                                        title="INU: Folder",
                                        placeholder="Folder with standalone TXD",
                                        tip="Folder with standalone TXD to scan")
        lay.addWidget(self._folder)
        self._custom = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(self._custom)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(1)
        head = QtWidgets.QHBoxLayout()
        head.addWidget(QtWidgets.QLabel("Files (.img / .txd):"), 1)
        head.addWidget(icon_btn('add', "Add .img / .txd to the Custom list",
                                self._add_file))
        cl.addLayout(head)
        self._rows = QtWidgets.QVBoxLayout()
        self._rows.setSpacing(1)
        cl.addLayout(self._rows)
        lay.addWidget(self._custom)
        lay.addWidget(self._check(
            "Cross-ref with IDE (used by)", 'texture_browser_check_ide', True,
            "Count how many IDE models use each TXD (uses the same IDE set as "
            "Map analysis)"))
        scan = QtWidgets.QPushButton("Scan")
        scan.setIcon(icon('refresh'))
        scan.setToolTip("Scan TXD from the chosen source and populate the "
                        "Texture Browser with metadata (without decoding pixels)")
        scan.clicked.connect(self._scan)
        clear = icon_btn('x', "Clear Texture Browser results", self._clear)
        lay.addWidget(FusedBlock([[scan, clear]], height=BTN_H + 6))

        self._search = QtWidgets.QLineEdit()
        self._search.setFixedHeight(BTN_H)
        self._search.setPlaceholderText("Filter by texture or TXD name")
        self._search.setText(self._get('texture_browser_search', ''))
        self._search.textChanged.connect(self._on_search)
        lay.addWidget(self._search)
        self._box_res = self._box()
        self._found = QtWidgets.QLabel()
        self._box_res.addWidget(self._found)
        self._list = QtWidgets.QListWidget()
        self._list.setTextElideMode(QtCore.Qt.ElideRight)
        self._list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._list.setFixedHeight(8 * 18 + 4)
        self._list.currentRowChanged.connect(lambda _r: self._detail())
        self._box_res.addWidget(self._list)
        self._det = self._box()
        self._box_res.addWidget(self._det.box)
        lay.addWidget(self._box_res.box)
        self._on_source(self._get('texture_browser_source', 'DAT'))

    def _on_source(self, mode):
        self._set('texture_browser_source', mode)
        self._dat.setVisible(mode == 'DAT')
        self._folder.setVisible(mode == 'FOLDER')
        self._custom.setVisible(mode == 'CUSTOM')
        _clear(self._rows)
        for i, p in enumerate(self._get('texture_browser_custom', []) or []):
            r = QtWidgets.QHBoxLayout()
            r.setSpacing(2)
            r.addWidget(ElideLabel(p), 1)
            r.addWidget(icon_btn('x', "Remove an entry from the Custom list",
                                 lambda i=i: self._remove(i)))
            self._rows.addLayout(r)
        self._refresh()

    def _add_file(self):
        from .file_dialog import INUFileDialog
        dlg = INUFileDialog(self, "INU: Add .img / .txd", mode='open',
                            key='texbrowser', accept_label="Add",
                            filters=[("IMG / TXD (*.img *.txd)", ["*.img", "*.txd"])])
        if dlg.exec() and dlg.selected_files():
            items = list(self._get('texture_browser_custom', []) or [])
            self._set('texture_browser_custom', items + dlg.selected_files()[:1])
            self._on_source('CUSTOM')

    def _remove(self, i):
        items = list(self._get('texture_browser_custom', []) or [])
        if 0 <= i < len(items):
            del items[i]
        self._set('texture_browser_custom', items)
        self._on_source('CUSTOM')

    def _scan(self):
        items, err = _busy(lambda: _checks().scan_textures(self._get))
        if err:
            QtWidgets.QMessageBox.warning(self, "INU Tools", err)
            return
        self._items = items
        self._refresh()

    def _clear(self):
        self._items = []
        self._refresh()

    def _on_search(self, text):
        self._set('texture_browser_search', text)
        self._refresh()

    def _refresh(self):
        has = bool(self._items)
        self._search.setVisible(has)
        self._box_res.box.setVisible(has)
        self._found.setText("Found: %d" % len(self._items))
        q = (self._get('texture_browser_search', '') or '').strip().lower()
        self._list.clear()
        for i, e in enumerate(self._items):
            text = "%s  %s  %d×%d  %s%s" % (
                e['txd_name'], e['texture_name'], e['width'], e['height'],
                e['format_label'],
                "  ×%d" % e['usage_count'] if e['usage_count'] else "")
            it = QtWidgets.QListWidgetItem(text)
            it.setData(QtCore.Qt.UserRole, i)
            self._list.addItem(it)
            hay = ("%s %s %s" % (e['txd_name'], e['texture_name'],
                                 e['format_label'])).lower()
            it.setHidden(bool(q) and q not in hay)
        self._detail()

    def _detail(self):
        _clear(self._det)
        it = self._list.currentItem()
        self._det.box.setVisible(it is not None)
        if it is None:
            return
        e = self._items[it.data(QtCore.Qt.UserRole)]
        self._det.addWidget(ElideLabel("%s → %s" % (e['txd_name'], e['texture_name'])))
        lines = ["%d × %d · %s · depth %d · mip %d" % (
            e['width'], e['height'], e['format_label'], e['depth'], e['num_levels']),
            "Archive: %s" % os.path.basename(e['archive_path'])]
        if self._get('texture_browser_check_ide', True):
            lines.append("Used by: %d models" % e['usage_count'])
        self._det.addWidget(_wrap_label("\n".join(lines), "#b8b8b8"))
        prev = QtWidgets.QLabel()
        prev.setAlignment(QtCore.Qt.AlignCenter)
        try:
            dec = _checks().decode_texture(e)
        except Exception as ex:                        # noqa: BLE001
            dec = None
            print("[INU] texture preview: %r" % (ex,))
        if dec:
            rgba, w, h = dec
            img = QtGui.QImage(rgba, w, h, w * 4, QtGui.QImage.Format_RGBA8888).copy()
            prev.setPixmap(QtGui.QPixmap.fromImage(img).scaled(
                160, 160, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
            self._det.addWidget(prev)


# ══ «Проверка перед экспортом» (роллаут окна DFF IO) ════════════════

_CATEGORY_LABEL = {
    'Paintjob': "Paintjob", 'Quaternions': "Quaternions",
    'UVAnimNightVcol': "UV-anim × Night", 'DamagePair': "_ok / _dam pairs",
    'OrphanModel': "Orphan LOD / COL", 'Orphan2DFX': "Unattached 2DFX",
    'DuplicateID': "Duplicate model_id", 'EmptyMesh': "Empty meshes",
    'LargeMesh': "Large meshes", 'NoTexture': "Material without texture",
    'SuffixMismatch': "Suffixes / prefixes", 'BadScale': "Object scale",
    'LightBeamASI': "Light Beam ASI", 'UntexturedModel': "Untextured mesh (COL)",
    'NonAsciiName': "Non-Latin name", 'LooseGeometry': "Loose geometry",
}


class PreExportCheck(BuildMixin, QtWidgets.QWidget):
    """Роллаут INU «Проверка перед экспортом»: Validate scene, сводка, группы
    проблем по объектам (раскрываются), у проблемы — «Normalise» / «Fix».
    issues — [dict(severity, category, message, target_kind, target_name,
    fix_op_id, fix_arg)]."""

    def __init__(self, dispatch, parent=None):
        super().__init__(parent)
        self._dispatch = dispatch
        self._issues = []
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        run = QtWidgets.QPushButton("Validate scene")
        run.setIcon(icon('refresh'))
        run.setToolTip("Run a full scene check: paintjob slots, quaternion "
                       "normalisation, Modulate Color on prelight meshes and "
                       "_ok/_dam pairing. Results are listed here — a click can "
                       "jump to the problem object or fix it automatically.")
        run.clicked.connect(lambda: self._dispatch("Validate scene", "validate_run"))
        self._clr = icon_btn('x', "Clear results list", lambda: self.set_issues([]))
        self._run_row = FusedBlock([[run, self._clr]])
        lay.addWidget(self._run_row)
        self._host = QtWidgets.QVBoxLayout()
        self._host.setSpacing(3)
        lay.addLayout(self._host)
        self.set_issues([])

    def set_issues(self, issues):
        self._issues = list(issues)
        self._render()

    def _render(self):
        _clear(self._host)
        has = bool(self._issues)
        self._clr.setVisible(has)
        self._run_row.update_corners()
        if not has:
            return
        c = {'ERROR': 0, 'WARNING': 0, 'INFO': 0}
        for i in self._issues:
            c[i['severity']] = c.get(i['severity'], 0) + 1
        b = self._box()
        row = QtWidgets.QHBoxLayout()
        for sev, text, name in (('ERROR', "%d Errors", 'error'),
                                ('WARNING', "%d Warnings", 'warning'),
                                ('INFO', "%d Info", 'info')):
            if c[sev]:
                lbl = QtWidgets.QLabel()
                lbl.setPixmap(icon(name, SEVERITY_COLOR[sev]).pixmap(14, 14))
                row.addWidget(lbl)
                row.addWidget(QtWidgets.QLabel(text % c[sev]))
        if not any(c.values()):
            row.addWidget(QtWidgets.QLabel("OK"))
        row.addStretch(1)
        b.addLayout(row)
        self._host.addWidget(b.box)

        groups, order = {}, []
        for i in self._issues:
            if i.get('target_name'):
                key = "O:%s:%s" % (i.get('target_kind', ''), i['target_name'])
                title = i['target_name']
            else:
                key = "C:%s" % i.get('category', '')
                title = _CATEGORY_LABEL.get(i.get('category', ''), i.get('category', ''))
            if key not in groups:
                groups[key] = (title, [])
                order.append(key)
            groups[key][1].append(i)
        expanded = set(self._get('validate_expanded', []) or [])
        for key in order:
            title, items = groups[key]
            self._host.addWidget(self._group_box(key, title, items, key in expanded))

    def _group_box(self, key, title, items, opened):
        b = self._box()
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(2)
        tog = QtWidgets.QPushButton("%s  (%d)" % (title, len(items)))
        tog.setFlat(True)
        tog.setStyleSheet("text-align:left; border:none; background:transparent;")
        tog.setIcon(icon('tri_down' if opened else 'tri_right'))
        tog.clicked.connect(lambda: self._toggle(key))
        head.addWidget(tog, 1)
        if key.startswith("O:"):
            head.addWidget(icon_btn('select', "Make the object/material from the "
                                    "result row active",
                                    lambda: self._dispatch("Select " + title,
                                                           "validate_goto", target_name=title,
                                                           target_kind=items[0].get('target_kind', 'OBJECT'))))
        b.addLayout(head)
        if opened:
            for it in items:
                ib = self._box()
                sev = it['severity']
                cat = QtWidgets.QHBoxLayout()
                ic = QtWidgets.QLabel()
                ic.setPixmap(_sev_icon(sev).pixmap(14, 14))
                cat.addWidget(ic)
                cat.addWidget(QtWidgets.QLabel(
                    _CATEGORY_LABEL.get(it.get('category', ''), it.get('category', ''))), 1)
                ib.addLayout(cat)
                ib.addWidget(_wrap_label(it['message']))
                fix = it.get('fix_op_id', '')
                if fix:
                    label = "Normalise" if 'quaternion' in fix else "Fix"
                    btn = QtWidgets.QPushButton(label)
                    btn.setFixedHeight(BTN_H)
                    btn.clicked.connect(lambda _c=False, f=fix, l=label:
                                        self._dispatch(l, f))
                    ib.addWidget(btn)
                b.addWidget(ib.box)
        return b.box

    def _toggle(self, key):
        exp = list(self._get('validate_expanded', []) or [])
        if key in exp:
            exp.remove(key)
        else:
            exp.append(key)
        self._set('validate_expanded', exp)
        self._render()
