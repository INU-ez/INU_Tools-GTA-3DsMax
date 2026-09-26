# INU Tools (Max) — окна инструментов (PySide6).
#
# Внешний вид повторяет скрипты Kam's (GTA_DFF_IO.ms и др.): окно = стопка
# сворачиваемых роллаутов, внутри — группы (group), чекбоксы, серые кнопки,
# зелёные checkbutton'ы для выбора варианта (style.py, widgets.py). Состав
# кнопок и опций — как в Blender-версии INU. Подписи — на английском.
#
# Файлы выбираются в своём окне (file_dialog.py): раскладка как у диалога
# Max, справа — опции INU (как сайдбар файлового браузера Blender).
#
# Из порта исключено (Blender-специфично): Texture Bake, живые превью,
# geo-nodes, рисование по картам — этих секций тут НЕТ намеренно.

from PySide6 import QtWidgets, QtCore

try:
    import qtmax           # родитель = главное окно Max (Max 2025+)
except Exception:          # noqa: BLE001
    qtmax = None

from .style import C, qss, BTN_H, SB_W, SB_GAP
from .widgets import (ElideLabel, Rollout, BuildMixin, FusedBlock, scrolled,
                      content_min_width)
from . import dff_options as dffo

# Версия сборки панели. Бампаем при заметных правках UI — печатается в
# консоль Max при показе, чтобы видеть, что грузится СВЕЖИЙ код (а не старая
# копия из другого пути / кэша).
_VERSION = "0.12.0-material"

# Окна инструментов (как у Kam's: лаунчер + отдельные окна под задачи).
# mode -> (заголовок, ширина px; окно расширится, если содержимому тесно).
_WIN_META = {
    'launcher': ("INU Tools", 214),
    'dff':      ("INU · DFF IO", 214),
    'veh':      ("INU · Vehicles", 214),
    'mat':      ("INU · GTA Material", 214),
    'map':      ("INU · Map IO", 240),
    'fx':       ("INU · 2DFX", 214),
    'ifp':      ("INU · IFP IO", 214),
    'water':    ("INU · Water IO", 214),
    'zones':    ("INU · Zones", 214),
    'paths':    ("INU · Paths", 214),
    'radar':    ("INU · X Radar", 214),
    'util':     ("INU · Check", 214),
}


def _main_window():
    """QMainWindow 3ds Max как родитель окна (чтобы панель жила поверх Max)."""
    if qtmax is not None:
        try:
            return qtmax.GetQMaxMainWindow()
        except Exception:                              # noqa: BLE001
            pass
    return None


def _no_max_hotkeys(w):
    """Пока фокус в окне, горячие клавиши Max не срабатывают (иначе ввод в
    поля и F2 в дереве фреймов уходят в шорткаты Max)."""
    if qtmax is not None:
        try:
            qtmax.DisableMaxAcceleratorsOnFocus(w, True)
        except Exception:                              # noqa: BLE001
            pass


def _core_status():
    """Проверить, что общее ядро (inu_gta_core) импортируется в Max-Python.

    numpy требуется для DFF и TXD; COL/IPL/IDE работают и без него."""
    avail = []

    def _try(mod, label):
        try:
            __import__(mod)
            avail.append(label)
            return True
        except Exception:                              # noqa: BLE001
            return False

    _try('inu_gta_core.col', 'COL')
    _try('inu_gta_core.ipl', 'IPL')
    _try('inu_gta_core.ide', 'IDE')
    dff_ok = _try('inu_gta_core.dff', 'DFF')
    txd_ok = _try('inu_gta_core.txd', 'TXD')

    has_numpy = True
    try:
        import numpy  # noqa: F401
    except Exception:                                  # noqa: BLE001
        has_numpy = False

    if not has_numpy:
        return False, (
            "numpy is missing in 3ds Max Python: DFF/TXD unavailable.\n"
            "Without numpy: " + (" · ".join(avail) or "—") + "\n"
            "Install (admin PowerShell):\n"
            '"…\\3ds Max 2026\\Python\\python.exe" -m pip install "numpy<2"')

    if dff_ok and txd_ok and len(avail) >= 5:
        return True, "Core: " + " · ".join(avail)

    return False, ("Core loaded partially: " + (" · ".join(avail) or "—")
                   + ". See the Max console.")


class INUToolsPanel(BuildMixin, QtWidgets.QWidget):
    """Окно инструмента. mode: 'launcher' (кнопки открывают окна) | 'dff' |
    'map' | ... — как у Kam's (лаунчер + отдельные окна под задачи)."""

    def __init__(self, mode='launcher', parent=None):
        super().__init__(parent)
        self._mode = mode
        title, width = _WIN_META.get(mode, _WIN_META['launcher'])
        self.setWindowTitle(title)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setObjectName("inuWin")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        # Шрифт НЕ задаём: виджеты берут шрифт интерфейса Max (Segoe UI 8pt),
        # тот же, что у роллаутов Kam's.
        self.setFixedWidth(width)
        self.setStyleSheet(qss())
        _no_max_hotkeys(self)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(3)

        # верхний блок: платформа + игра (в каждом окне, кроме лаунчера);
        # справа отступ под колонку полосы — край совпадает с роллаутами
        if mode != 'launcher':
            top = QtWidgets.QHBoxLayout()
            top.setContentsMargins(0, 0, SB_W + SB_GAP, 0)
            top.addWidget(self._build_top_cluster())
            outer.addLayout(top)

        # прокручиваемая область с роллаутами и своей колонкой под полосу
        host = QtWidgets.QWidget()
        host.setObjectName("scrollHost")
        root = QtWidgets.QVBoxLayout(host)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)
        lay, self._view, self._vbar = scrolled(host)
        outer.addLayout(lay, 1)

        # секции подписываются на смену выделения и игры (см. _start_polling)
        self._sel_handlers = []
        self._game_handlers = []

        {'launcher': self._sections_launcher, 'dff': self._sections_dff,
         'map': self._sections_map,
         'util': self._sections_util, 'veh': self._sections_veh,
         'mat': self._sections_mat,
         'fx': self._sections_fx, 'ifp': self._sections_ifp,
         'water': self._sections_water, 'zones': self._sections_zones,
         'paths': self._sections_paths, 'radar': self._sections_radar}.get(
            mode, self._sections_stub)(root)

        root.addStretch(1)
        root.addWidget(self._footer(mode != 'launcher'))

        # Страховка от обрезки справа: если роллаутам (включая скрытые группы
        # и свёрнутые роллауты) нужно шире, чем даёт окно, — расширяем окно.
        need = (content_min_width(host) + outer.contentsMargins().left()
                + outer.contentsMargins().right() + SB_W + SB_GAP)
        self.setFixedWidth(max(width, need))

    # ---- подвал: статус ядра + версия ------------------------------------
    def _footer(self, with_status):
        foot = QtWidgets.QLabel()
        foot.setWordWrap(True)
        text = "v%s" % _VERSION
        color = "#9a9a9a"
        if with_status:
            ok, msg = _core_status()
            if ok:
                foot.setToolTip(msg)
                text = "Core OK · v%s" % _VERSION
            else:
                text = msg + "\nv%s" % _VERSION
                color = C['err']
        foot.setText(text)
        foot.setStyleSheet("color:%s; padding:2px 2px 0 2px;" % color)
        return foot

    # ---- верхний блок: платформа / игра ----------------------------------
    def _build_top_cluster(self):
        """Платформа + игра — два ряда checkbutton'ов (зелёный = выбран),
        слитые в один блок, как в Blender."""
        box = QtWidgets.QFrame()
        box.setObjectName("rollout")
        box.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(5, 5, 5, 5)
        lay.setSpacing(3)
        plat, self._plat_group = self._seg_buttons(
            [("PC", "PC"), ("Mobile", "MOBILE")], self._get('platform', 'PC'),
            lambda d: self._set('platform', d),
            "PC / Mobile: on mobile textures R and B are swapped.")
        game, self._game_group = self._seg_buttons(
            [("SA", "SA"), ("III", "III"), ("VC", "VC")], self._get('game', 'SA'),
            self._on_game,
            "Target game (SA / GTA III / VC): RW version on export.")
        lay.addWidget(FusedBlock([plat, game]))
        return box

    def _on_game(self, game):
        self._set('game', game)
        for fn in self._game_handlers:
            fn()

    # ---- ЛАУНЧЕР: кнопки открывают окна (как у Kam's) --------------------
    # (запасной Qt-лаунчер; основной — нативный inu_launcher.ms в командной
    # панели. Держим синхронным с ним по составу.)
    def _sections_launcher(self, root):
        mk = self._mkbtn
        s = Rollout("Models", opened=True)
        for label, key in (("DFF IO  (DFF / TXD)", "open:dff"),
                           ("Vehicles", "open:veh"),
                           ("GTA Material", "open:mat")):
            s.body.addWidget(mk(label, key))
        root.addWidget(s)
        s = Rollout("Map", opened=True)
        for label, key in (("Map IO  (IDE / IPL / IMG)", "open:map"),
                           ("2DFX", "open:fx"), ("Paths", "open:paths"),
                           ("Zones", "open:zones"), ("Water", "open:water"),
                           ("X Radar", "open:radar")):
            s.body.addWidget(mk(label, key))
        root.addWidget(s)
        s = Rollout("Other", opened=True)
        s.body.addWidget(mk("IFP IO  (Animations)", "open:ifp"))
        s.body.addWidget(mk("Check", "open:util"))
        root.addWidget(s)

    # ---- окно-заглушка (раздел ещё не реализован) ------------------------
    def _sections_stub(self, root):
        s = Rollout("In progress", opened=True)
        s.body.addWidget(self._hint("Window layout only, logic comes next."))
        root.addWidget(s)

    # ---- ОКНО «DFF IO»: как панель «Экспорт / Импорт» INU ----------------
    # Раскладка как в Blender: выделение, Import | Export, Авто TXD + DXT,
    # проверка при экспорте, pipeline, генерация COL, DFF Flags. Опции
    # импорта/экспорта — в окне выбора файлов (как сайдбар браузера Blender).
    def _sections_dff(self, root):
        s = Rollout("Export / Import", opened=True)
        box = QtWidgets.QFrame()           # рамка без заголовка, как бокс INU
        box.setObjectName("box")
        g = QtWidgets.QVBoxLayout(box)
        g.setContentsMargins(6, 4, 6, 4)
        g.setSpacing(3)
        self.lb_sel = ElideLabel()
        g.addWidget(self.lb_sel)
        self.lb_kind = {}
        for kind in ('DFF', 'LOD', 'COL'):
            lb = ElideLabel()
            g.addWidget(lb)
            self.lb_kind[kind] = lb
        s.body.addWidget(box)

        imp = self._mkbtn("Import", "inu_import")
        imp.setToolTip("Import .dff .col .cst .txd .ide .ipl: each by its own "
                       "type. Options are in the file window.")
        exp = self._mkbtn("Export", "inu_export")
        exp.setToolTip("Export selected models (DFF + COL + LOD + TXD). "
                       "Options are in the file window.")
        s.body.addWidget(FusedBlock([[imp, exp]], height=BTN_H + 3))

        auto = self._check(
            "Auto TXD", 'auto_txd', True,
            "Load the model's TXD automatically on DFF import:\n"
            "1. .txd files covering the DFF textures (max coverage first)\n"
            "2. more .txd until all textures are found\n"
            "A .txd selected in the same import is used as well.")
        dxt = self._combo(
            'dxt_backend',
            [("Numpy", 'numpy',
              "Recommended for final export into IMG: range-fit on mip 0, "
              "best quality without external binaries."),
             ("Numpy fast", 'numpy_fast',
              "For quick test runs: ~1.7× faster. Visible artifacts possible "
              "on sharp alpha edges (fences, foliage). Switch back to Numpy "
              "before release.")],
            'numpy', "DXT texture compression backend")
        row = self._row(auto, dxt)
        row.setStretch(0, 0)
        s.body.addLayout(row)
        s.body.addWidget(self._check(
            "Audit models on export", 'audit_on_export', False,
            "After writing each DFF, check it for game crashes/bugs (vertex/"
            "material indices, vehicle dummies, skin, 2DFX, names...). Turn "
            "off for MASS export of already checked models: it is slow."))
        pipe, self._pipe_group = dffo.pipeline_buttons(self, self._on_pipeline)

        gen = QtWidgets.QPushButton("Generate COL")
        gen.setToolTip("Generate collision (<name>_COL) from the selected "
                       "model: a convex hull or a bounding box. The mesh is "
                       "editable and goes on to COL export.")
        menu = QtWidgets.QMenu(gen)
        for lbl, key in (("Convex hull", "auto_col_convex"),
                         ("Bounding box", "auto_col_box")):
            act = menu.addAction(lbl)
            act.triggered.connect(
                lambda _c=False, l=lbl, k=key: self._dispatch(
                    "Generate COL: " + l, k))
        gen.setMenu(menu)
        # как в Blender: ряд pipeline и «Generate COL» слиты в один блок
        s.body.addWidget(FusedBlock([pipe, [gen]], pad=3))
        root.addWidget(s)

        # DFF Flags активного объекта — сворачиваемо, как в INU
        s = Rollout("DFF Flags")
        self.flags = dffo.FlagsBox()
        s.body.addWidget(self.flags)
        root.addWidget(s)

        # «Проверка перед экспортом» — подпанель «Экспорт / Импорт» INU
        from .check_panel import PreExportCheck
        s = Rollout("Pre-export check")
        self.pre_check = PreExportCheck(self._dispatch)
        s.body.addWidget(self.pre_check)
        root.addWidget(s)

        self._sel_handlers.append(self._dff_selection)
        self._game_handlers.append(self.flags.refresh)
        self._start_polling()

    def _on_pipeline(self):
        self.flags.refresh()

    def _dff_selection(self, snap):
        self._apply_selection(snap['info'])
        self.flags.load(snap['active'])

    # ---- выделение сцены: опрос и раздача секциям ------------------------
    def _start_polling(self):
        """Сводку выделения обновляем опросом (как redraw панели в Blender);
        секции получают снимок только при смене выделения."""
        self._sel_key = object()
        self._sel_err = False
        self._sel_timer = QtCore.QTimer(self)
        self._sel_timer.setInterval(700)
        self._sel_timer.timeout.connect(self._poll_selection)
        # пока окно тянут за край — Max не опрашиваем, продолжаем после паузы
        self._sel_resume = QtCore.QTimer(self)
        self._sel_resume.setSingleShot(True)
        self._sel_resume.setInterval(400)
        self._sel_resume.timeout.connect(self._sel_timer.start)
        self._poll_selection(force=True)

    def _poll_selection(self, force=False):
        from ..adapter import selection as sel
        snap = dict(n=0, active=None, active_type=None, info=None, node=None,
                    sel_names=[])
        try:
            key = sel.selection_key()
            if not force and key == self._sel_key:
                return
            self._sel_key = key
            meshes = sel.selected_meshes()
            snap.update(n=len(meshes), info=sel.summary(),
                        active=meshes[0] if meshes else None,
                        node=sel.active_node(), sel_names=sel.selected_names())
            if meshes:
                snap['active_type'] = sel.classify(meshes[0])[0]
        except Exception as e:                         # noqa: BLE001
            # вне Max (нет pymxs) или ошибка опроса — показываем пустое
            if not self._sel_err and 'pymxs' not in str(e):
                print("[INU] selection poll: %r" % (e,))
            self._sel_err = True
        for fn in self._sel_handlers:
            fn(snap)

    def _apply_selection(self, info):
        if info is None:
            info = dict(n=0, first={}, counts={}, too_many=False)
        self.lb_sel.setText("Selected: %d mesh(es)" % info['n'])
        for kind, lb in self.lb_kind.items():
            name = info['first'].get(kind)
            n = info['counts'].get(kind, 0)
            if info['too_many']:
                lb.setText("%s: …" % kind)
            elif name is None:
                lb.setText("✗  %s: -" % kind)
            elif n <= 1:
                lb.setText("✓  %s: %s" % (kind, name))
            else:
                lb.setText("✓  %s: %s +%d" % (kind, name, n - 1))

    def _sync_from_settings(self):
        """После окна выбора файлов: там могли поменять игру, платформу и
        pipeline, а на объектах — DFF-флаги."""
        for group, key, dflt in ((getattr(self, '_plat_group', None), 'platform', 'PC'),
                                 (getattr(self, '_game_group', None), 'game', 'SA'),
                                 (getattr(self, '_pipe_group', None),
                                  'export_pipeline', 'NONE')):
            if group is not None:
                self._seg_sync(group, self._get(key, dflt))
        flags = getattr(self, 'flags', None)
        if flags is not None:
            flags.refresh()
            self._sel_key = object()          # перечитать флаги объекта

    def showEvent(self, e):                            # noqa: N802
        super().showEvent(e)
        t = getattr(self, '_sel_timer', None)
        if t is not None:
            t.start()

    def resizeEvent(self, e):                          # noqa: N802
        super().resizeEvent(e)
        # пока тянут размер — опрос выделения (pymxs) на паузе
        t = getattr(self, '_sel_timer', None)
        if t is not None and (t.isActive() or self._sel_resume.isActive()):
            t.stop()
            self._sel_resume.start()

    def _stop_polling(self):
        for name in ('_sel_timer', '_sel_resume'):
            t = getattr(self, name, None)
            if t is not None:
                t.stop()

    def hideEvent(self, e):                            # noqa: N802
        self._stop_polling()
        super().hideEvent(e)

    def closeEvent(self, e):                           # noqa: N802
        self._stop_polling()
        super().closeEvent(e)

    # ---- DFF IO: импорт / экспорт через окно выбора файлов ---------------
    def _do_import(self):
        """Окно выбора (много файлов) с опциями импорта INU справа; импорт
        каждого файла по типу."""
        from .file_dialog import INUFileDialog
        opts = dffo.ImportOptions()
        dlg = INUFileDialog(self, "INU: Import", mode='open_multi',
                            filters=opts.filters(), key='import',
                            accept_label="Import", options=opts)
        opts.formats_changed.connect(lambda: dlg.set_filters(opts.filters()))
        ok = dlg.exec()
        self._sync_from_settings()
        if not ok:
            return
        paths = dlg.selected_files()
        self._reload_dev()
        from inu_max.ops.inu_import import import_files
        report = import_files(paths, auto_txd=bool(self._get('auto_txd', True)))
        self._sel_key = object()          # после импорта обновить сводку
        QtWidgets.QMessageBox.information(self, "INU Tools: Import", report)

    def _do_export(self):
        """Окно выбора (папка + имя) с опциями Export All INU справа."""
        from .file_dialog import INUFileDialog
        info, active = dffo.selection_snapshot()
        opts = dffo.ExportOptions(info, active)
        dlg = INUFileDialog(self, "INU: Export", mode='export',
                            filters=opts.filters(), key='export',
                            accept_label="Export", options=opts,
                            filename=opts.export_name())
        opts.formats_changed.connect(lambda: dlg.set_filters(opts.filters()))
        ok = dlg.exec()
        self._sync_from_settings()
        if not ok:
            return
        folder, name = dlg.target()
        QtWidgets.QMessageBox.information(
            self, "INU Tools: Export",
            "Export is not implemented yet.\n\nFolder: %s\nName: %s"
            % (folder, name or "(per model)"))

    # ---- ОКНО «MAP IO»: панели INU «IDE / IPL / IMG», «Object IDE / IPL»,
    # «ID Manager» (состав и подписи — как в Blender, см. map_io.py) ------
    def _sections_map(self, root):
        from . import map_io
        s = Rollout("IDE / IPL / IMG", opened=True)
        self.ide_ipl = map_io.IdeIplImg(self._dispatch)
        s.body.addWidget(self.ide_ipl)
        root.addWidget(s)

        s = Rollout("Object IDE / IPL")
        self.obj_ide = map_io.ObjectIdeIpl(self._dispatch)
        s.body.addWidget(self.obj_ide)
        root.addWidget(s)

        s = Rollout("ID Manager")
        self.id_mgr = map_io.IdManager(self._dispatch)
        s.body.addWidget(self.id_mgr)
        root.addWidget(s)

        self._sel_handlers += [self.ide_ipl.on_selection, self.obj_ide.on_selection]
        self._game_handlers += [self.ide_ipl.pages['EXPORT'].flags.rebuild,
                                self.obj_ide.flags.rebuild]
        self._start_polling()

    # ---- ОКНО «CHECK»: панели INU «Проверка», «Анализ карты/файлов»,
    # «Текстуры (TXD)» (см. check_panel.py) ------------------------------
    def _sections_util(self, root):
        from . import check_panel
        s = Rollout("Check", opened=True)
        self.check_tools = check_panel.CheckTools(self._dispatch)
        s.body.addWidget(self.check_tools)
        root.addWidget(s)

        s = Rollout("Map/file analysis")
        self.file_analysis = check_panel.FileAnalysis()
        s.body.addWidget(self.file_analysis)
        root.addWidget(s)

        s = Rollout("Textures (TXD)")
        self.tex_browser = check_panel.TextureBrowser()
        s.body.addWidget(self.tex_browser)
        root.addWidget(s)

        self._sel_handlers.append(self.check_tools.on_selection)
        self._start_polling()

    # ---- ОКНО «VEHICLES»: панели INU «Машины» и «Иерархия фреймов» ------
    def _sections_veh(self, root):
        from . import vehicle_panel
        s = Rollout("Vehicles", opened=True)
        self.veh_tools = vehicle_panel.VehicleTools(self._dispatch,
                                                    lambda: self._run(
                                                        self._do_export, "Export"))
        s.body.addWidget(self.veh_tools)
        root.addWidget(s)

        s = Rollout("Frame hierarchy")
        self.frames = vehicle_panel.FrameHierarchy(self._dispatch, 'VEHICLE')
        s.body.addWidget(self.frames)
        root.addWidget(s)

        self._sel_handlers += [self.veh_tools.on_selection, self.frames.on_selection]
        self._start_polling()

    # ---- ОКНО «GTA MATERIAL»: панель INU «GTA Material» для материала
    # выделенного объекта (см. material_panel.py) -------------------------
    def _sections_mat(self, root):
        from . import material_panel
        s = Rollout("GTA Material", opened=True)
        self.material = material_panel.MaterialTools(
            self._dispatch, lambda: self._poll_selection(force=True))
        s.body.addWidget(self.material)
        root.addWidget(s)
        self._sel_handlers.append(self.material.on_selection)
        self._start_polling()

    # ---- ОКНО «2DFX»: панели INU «Эффекты» и «GTA SA: <тип>» (настройки
    # активного эффекта; роллаут виден, когда выделен 2DFX) — fx_panel.py --
    def _sections_fx(self, root):
        from . import fx_panel
        s = Rollout("Effects", opened=True)
        self.fx = fx_panel.EffectsPanel(
            self._dispatch, lambda: self._poll_selection(force=True), s)
        s.body.addWidget(self.fx)
        root.addWidget(s)

        s = Rollout("GTA SA: 2DFX", opened=True)
        self.fx_settings = fx_panel.FxSettings(self._dispatch, s)
        s.body.addWidget(self.fx_settings)
        root.addWidget(s)

        self._sel_handlers += [self.fx.on_selection, self.fx_settings.on_selection]
        self._start_polling()

    # ---- ОКНО «IFP IO»: панель INU «Анимации» (вкладки Characters /
    # Objects) и «Иерархия фреймов» в режиме педа (см. anim_panel.py) ----
    def _sections_ifp(self, root):
        from . import anim_panel, vehicle_panel
        s = Rollout("Animations", opened=True)
        self.anim = anim_panel.AnimTools(
            self._dispatch, lambda: self._run(self._do_export, "Export"))
        s.body.addWidget(self.anim)
        root.addWidget(s)

        s = Rollout("Frame hierarchy")
        self.frames = vehicle_panel.FrameHierarchy(self._dispatch, 'PED')
        s.body.addWidget(self.frames)
        root.addWidget(s)

        self._sel_handlers += [self.anim.on_selection, self.frames.on_selection]
        self._start_polling()

    # ---- ОКНА «WATER IO», «ZONES», «PATHS», «X RADAR»: панели INU «Water»,
    # «map.zon», «Пути», «X Radar Maker» (см. world_panel.py) -------------
    def _sections_water(self, root):
        from . import world_panel
        s = Rollout("Water", opened=True)
        self.water = world_panel.WaterTools(self._dispatch)
        s.body.addWidget(self.water)
        root.addWidget(s)
        self._sel_handlers.append(self.water.on_selection)
        self._start_polling()

    def _sections_zones(self, root):
        from . import world_panel
        s = Rollout("map.zon", opened=True)
        self.zones = world_panel.ZonTools(
            self._dispatch, lambda: self._poll_selection(force=True))
        s.body.addWidget(self.zones)
        root.addWidget(s)
        self._sel_handlers.append(self.zones.on_selection)
        self._start_polling()

    def _sections_paths(self, root):
        from . import world_panel
        s = Rollout("Paths", opened=True)
        self.paths = world_panel.PathTools(
            self._dispatch, lambda: self._poll_selection(force=True))
        s.body.addWidget(self.paths)
        root.addWidget(s)
        self._sel_handlers.append(self.paths.on_selection)
        self._start_polling()

    def _sections_radar(self, root):
        from . import world_panel
        s = Rollout("X Radar Maker", opened=True)
        self.radar = world_panel.RadarTools(self._dispatch)
        s.body.addWidget(self.radar)
        root.addWidget(s)

    # ---- вспомогательные конструкторы ------------------------------------
    def _mkbtn(self, label, key):
        """Обычная кнопка-действие (высота как у Kam's), привязанная к роутингу."""
        btn = QtWidgets.QPushButton(label)
        btn.setFixedHeight(BTN_H)
        btn.clicked.connect(
            lambda _c=False, lbl=label, k=key: self._dispatch(lbl, k))
        return btn

    def _hint(self, text):
        lbl = QtWidgets.QLabel(text)
        lbl.setWordWrap(True)
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        return lbl

    # ---- роутинг и запуск -------------------------------------------------
    @staticmethod
    def _reload_dev():
        """Dev: сбросить наши ops/adapter-модули из sys.modules, чтобы каждое
        нажатие кнопки исполняло свежий код (правки без перезапуска run_inu).
        Ядро (inu_gta_core) не трогаем — оно тяжёлое и стабильное."""
        import sys
        for name in [m for m in list(sys.modules)
                     if m.startswith('inu_max.ops')
                     or m.startswith('inu_max.adapter')]:
            del sys.modules[name]

    # ключ операции → (модуль, функция) в inu_max.ops
    _OPS = {
        'import_dff': ('inu_max.ops.import_dff', 'import_dff_interactive'),
        'import_txd': ('inu_max.ops.import_txd', 'import_txd_interactive'),
    }

    def _dispatch(self, label, key):
        """Роутинг кнопок: open:<mode> — открыть окно; реализованные — в
        операции; остальные — заглушка."""
        if key.startswith("open:"):
            open_window(key.split(":", 1)[1])
            return
        if key == "inu_import":
            self._run(self._do_import, label)
            return
        if key == "inu_export":
            self._run(self._do_export, label)
            return
        self._reload_dev()
        op = self._OPS.get(key)
        if op is not None:
            mod, fn = op
            self._run(lambda: getattr(__import__(mod, fromlist=[fn]), fn)(), label)
            return
        self._stub(label, key)

    def _run(self, fn, label):
        try:
            fn()
        except Exception as e:                         # noqa: BLE001
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(
                self, "INU Tools",
                "Error in \"%s\":\n%s: %s\n\nSee the Max console for details."
                % (label, type(e).__name__, e))

    def _stub(self, label, key):
        QtWidgets.QMessageBox.information(
            self, "INU Tools",
            "\"%s\" (%s) is not implemented yet." % (label, key))


# Реестр открытых окон (mode -> окно). Держим ссылки, иначе GC закроет.
_WINDOWS = {}


def open_window(mode):
    """Открыть (или пере-открыть) окно инструмента по режиму."""
    global _WINDOWS
    old = _WINDOWS.get(mode)
    try:
        if old is not None:
            old.close()
            old.deleteLater()
    except Exception:                                  # noqa: BLE001
        pass
    w = INUToolsPanel(mode, _main_window())
    _WINDOWS[mode] = w
    w.show()
    w.raise_()
    # одна строка в Listener: какая версия открыта и сколько прокручивать
    QtCore.QTimer.singleShot(300, lambda: print(
        "[INU] %s v%s: content %d / view %d px" % (
            mode, _VERSION, w._view.content_height(), w._view.height())))
    return w


def show_panel():
    """Точка входа: показать лаунчер (кнопки открывают окна инструментов)."""
    print("=" * 60)
    print("[INU Tools] panel version %s" % _VERSION)
    print("[INU Tools] module: %s" % __file__)
    print("=" * 60)
    return open_window('launcher')
