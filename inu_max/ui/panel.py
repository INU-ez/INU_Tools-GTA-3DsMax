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

import os

from ..qt import QtWidgets, QtCore

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
from ..version import VERSION as _V, TAG as _T
_VERSION = "%s-%s" % (_V, _T)

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
    'light':    ("INU · Lighting", 240),
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
            "Open the INU launcher and click Install / Update INU to install numpy "
            "for this Max Python version.")

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
         'paths': self._sections_paths, 'radar': self._sections_radar,
         'light': self._sections_light}.get(
            mode, self._unknown_section)(root)

        root.addStretch(1)
        root.addWidget(self._footer(mode != 'launcher'))
        if mode == 'dff':
            self.setAcceptDrops(True)       # файлы из Проводника — импорт

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
                           ("GTA Material", "open:mat"),
                           ("Lighting", "open:light")):
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
        # установка INU в Max: пакет INU_Tools.bundle (перетаскивание .dff во
        # вьюпорт, меню INU Tools, лаунчер при запуске, numpy) — inu_max/setup.py
        s = Rollout("Setup", opened=True)
        self._setup_lb = self._hint("")
        s.body.addWidget(self._setup_lb)
        self._setup_btn = mk("Install INU", "setup:install")
        self._setup_btn.setToolTip(
            "Install INU into 3ds Max: drag & drop .dff into the viewport, INU Tools "
            "menu, launcher at startup, numpy. Needs a 3ds Max restart.")
        rm = mk("Remove", "setup:remove")
        rm.setToolTip("Remove INU Tools from 3ds Max (your INU folder is not touched)")
        s.body.addWidget(FusedBlock([[self._setup_btn], [rm]]))
        root.addWidget(s)
        self._refresh_setup()

    def _refresh_setup(self):
        try:
            from .. import setup
            st = setup.status()
            self._setup_lb.setText(st['text'])
            self._setup_btn.setText(st['button'])
        except Exception as e:                         # noqa: BLE001
            self._setup_lb.setText("Setup: %s" % e)

    # ---- unknown window identifier ------------------------
    def _unknown_section(self, root):
        s = Rollout("Unknown tool", opened=True)
        s.body.addWidget(self._hint("This tool has no registered window."))
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
        self._poll_selection(force=True)

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
        cb = getattr(self, 'cb_auto_txd', None)          # мог поменяться в диалоге сброса
        if cb is not None:
            cb.blockSignals(True)
            cb.setChecked(bool(self._get('auto_txd', True)))
            cb.blockSignals(False)
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
        dlg.deleteLater()
        self._import_paths(paths)

    def _import_paths(self, paths):
        """Импорт файлов (окно Import или перетаскивание) + отчёт."""
        self._reload_dev()
        from .. import diag
        gen = diag.start("import %d file(s)" % len(paths))
        diag.mark("import start")
        from inu_max.ops.inu_import import import_files
        report = import_files(paths, auto_txd=bool(self._get('auto_txd', True)))
        diag.mark("import done")
        self._sync_from_settings()        # pipeline and object flags after import
        # отчёт — НЕмодально: модальный цикл Qt поверх Max мешал Max догружать
        # текстуры вьюпорта (зависание на десятки секунд после импорта)
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information,
                                    "INU Tools: Import", report,
                                    QtWidgets.QMessageBox.Ok, self)
        box.setModal(False)
        box.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        box.show()
        diag.mark("report shown")
        # тики после импорта: задержка между ними = сколько висел Max
        for sec in (1, 3, 6, 10, 20, 40):
            QtCore.QTimer.singleShot(sec * 1000, lambda s=sec: diag.generation() == gen
                                     and diag.mark("tick %ds" % s))
        QtCore.QTimer.singleShot(41000, lambda: diag.stop(gen))

    # ---- перетаскивание файлов на окно (drop_dff INU) ---------------------
    # Во вьюпорт Max файлы из Python не принять: сброс туда обрабатывает сам
    # Max (C++). Поэтому файлы бросают на окно INU.
    _DROP_EXT = ('.dff', '.txd', '.col', '.cst', '.ide', '.ipl')

    def _drop_paths(self, ev):
        md = ev.mimeData()
        if not md.hasUrls():
            return []
        return [u.toLocalFile() for u in md.urls() if u.isLocalFile()
                and os.path.isfile(u.toLocalFile())
                and os.path.splitext(u.toLocalFile())[1].lower() in self._DROP_EXT]

    def _drop_hint(self, on):
        hint = getattr(self, '_drop_label', None)
        if hint is None:
            hint = QtWidgets.QLabel("Drop to import\n.dff .txd .col .cst .ide .ipl", self)
            hint.setAlignment(QtCore.Qt.AlignCenter)
            hint.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            hint.setStyleSheet("background: rgba(0, 189, 0, 60); color: white;"
                               "border: 2px dashed #00BD00; font-weight: bold;")
            self._drop_label = hint
        hint.setGeometry(self.rect().adjusted(4, 4, -4, -4))
        hint.setVisible(on)
        if on:
            hint.raise_()

    def dragEnterEvent(self, ev):                      # noqa: N802
        if self._drop_paths(ev):
            ev.acceptProposedAction()
            self._drop_hint(True)
        else:
            ev.ignore()

    def dragMoveEvent(self, ev):                       # noqa: N802
        if self._drop_paths(ev):
            ev.acceptProposedAction()

    def dragLeaveEvent(self, ev):                      # noqa: N802
        self._drop_hint(False)

    def dropEvent(self, ev):                           # noqa: N802
        self._drop_hint(False)
        paths = self._drop_paths(ev)
        if not paths:
            return
        ev.acceptProposedAction()
        # импорт — ПОСЛЕ возврата из события: Проводник ждёт окончания сброса
        # и висел бы, пока открыт наш диалог
        QtCore.QTimer.singleShot(0, lambda p=paths: self._run(
            lambda: self._on_dropped(p), "Drop import"))

    def _on_dropped(self, paths):
        """Как drop_dff INU: для DFF — маленький диалог «как импортировать»
        (vanilla / 2DFX / Auto TXD), затем импорт всех файлов."""
        if any(p.lower().endswith('.dff') for p in paths):
            if not self._drop_dialog(len(paths)):
                return
        self._import_paths(paths)

    def _drop_dialog(self, count):
        from .drop_dialog import ask
        ok = ask(self, count, at_cursor=True)
        self._sync_from_settings()
        return ok

    def _do_auto_col(self, mode):
        """«Generate COL» (auto_col INU): <имя>_COL выделенных моделей."""
        self._reload_dev()
        from inu_max.ops import gen_col
        made = gen_col.generate(mode)
        self._sel_key = object()
        if not made:
            text = "No model for collision: select the models (DFF / LOD)."
        else:
            kinds = {'CONVEX': "convex hull", 'BOX': "bounding box"}
            text = "Collision created: %d\n\n%s" % (len(made), "\n".join(
                "%s — %s" % (n, kinds.get(u, u)) for n, u in made))
            if mode == 'CONVEX' and any(u == 'BOX' for _n, u in made):
                text += "\n\n(flat models get a bounding box instead of a hull)"
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information,
                                    "INU Tools: Generate COL", text,
                                    QtWidgets.QMessageBox.Ok, self)
        box.setModal(False)
        box.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        box.show()

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
        if self._get('export_to_img', False):
            if self._get('exp_single_dff', False):
                self._show_result('Export', 'ERROR', 'Single DFF cannot be combined with All → IMG')
                return
            self._do_img_op('export_to_img', 'Export All to IMG', use_export_options=True)
            return
        self._reload_dev()
        from inu_max.ops import dff_export
        done, errors, warnings = dff_export.export(folder, (name or '').strip())
        lines = []
        if done:
            lines.append("Exported to %s:\n  %s" % (folder, "\n  ".join(done)))
        if errors:
            lines.append("Errors:\n  " + "\n  ".join(errors))
        if warnings:
            for w in warnings:
                print("[INU export] %s" % w)
            lines.append("Warnings (%d):\n  %s" % (
                len(warnings), "\n  ".join(warnings[:12])
                + ("\n  … see the Max Listener" if len(warnings) > 12 else "")))
        box = (QtWidgets.QMessageBox.warning if errors
               else QtWidgets.QMessageBox.information)
        box(self, "INU Tools: Export", "\n\n".join(lines) or "Nothing exported")

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
        # слежение за связанными IDE / IPL (map_watch INU): файл изменён
        # снаружи → связи перечитываются, статусы окна обновляются
        self._link_watch = None
        self._watch_err = False
        self._watch_timer = QtCore.QTimer(self)
        self._watch_timer.setInterval(2000)
        self._watch_timer.timeout.connect(self._watch_tick)
        self._watch_timer.start()

    def _watch_tick(self):
        import time
        try:
            from ..ops import map_link
            if self._link_watch is None or not isinstance(self._link_watch, map_link.Watch):
                self._link_watch = map_link.Watch()
            if self._link_watch.tick(time.monotonic()):
                self._sel_key = object()               # статусы — заново
                self._poll_selection(force=True)
        except Exception as e:                         # noqa: BLE001
            if not self._watch_err and 'pymxs' not in str(e):
                print("[INU] link watch: %r" % (e,))
            self._watch_err = True

    # ---- ОКНО «LIGHTING»: панель INU «Lighting» (вкладки PreLight /
    # PreLight COL; подпанели PreLight — отдельными роллаутами, см.
    # light_panel.py) --------------------------------------------------
    def _sections_light(self, root):
        from . import light_panel
        s = Rollout("Lighting", opened=True)
        self.light = light_panel.LightingPanel(self._light_op)
        s.body.addWidget(self.light)
        root.addWidget(s)
        subs = []
        s = Rollout("Advanced Settings")
        self.light_adv = light_panel.AdvancedSettings(self._light_op)
        s.body.addWidget(self.light_adv)
        root.addWidget(s)
        subs.append(s)
        self.light_tools = light_panel.ToolsPanel(self._light_op)
        self.light_foliage = light_panel.FoliagePanel(self._light_op)
        self.light_post = light_panel.PostPanel(self._light_op)
        for title, w in (("Tools", self.light_tools), ("Foliage / Tree", self.light_foliage),
                         ("Post-Processing", self.light_post)):
            s = Rollout(title)
            s.body.addWidget(w)
            root.addWidget(s)
            subs.append(s)
        # подпанели PreLight видны только на вкладке PreLight (как в INU)
        self.light.tab_handlers = [lambda m, rs=subs: [r.setVisible(m == 'PRELIGHT') for r in rs]]
        self.light._on_tab(self._get('light_mode', 'PRELIGHT'))
        self._sel_handlers.append(self.light.on_selection)
        self._sel_handlers.append(self.light_foliage.on_selection)
        self._start_polling()

    def _light_op(self, label, fn, *args):
        """Операция окна Lighting (ops/prelight.py) + отчёт + обновление."""
        def go():
            self._reload_dev()
            from inu_max.ops import prelight, prelight_tools
            from inu_max.adapter import prelight_scene
            # часть 1 — ops/prelight.py, часть 2 (Tools / Foliage /
            # Post-Processing) — ops/prelight_tools.py
            op = getattr(prelight, fn, None) or getattr(prelight_tools, fn)
            level, text = op(*args)
            # вьюпорт — сразу (иначе новый показ цвета вершин виден только
            # после поворота вида)
            prelight_scene.redraw()
            self._show_result(label, level, text)
            for w in (getattr(self, 'light', None), getattr(self, 'light_adv', None),
                      getattr(self, 'light_tools', None), getattr(self, 'light_post', None),
                      getattr(self, 'light_foliage', None)):
                if w is not None:
                    w.refresh()
        self._run(go, label)

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

    def _dispatch(self, label, key, **options):
        """Роутинг кнопок: open:<mode> — открыть окно; реализованные — в
        операции; unknown keys report a registration error."""
        if key.startswith("open:"):
            open_window(key.split(":", 1)[1])
            return
        if key == "inu_import":
            self._run(self._do_import, label)
            return
        if key == "inu_export":
            self._run(self._do_export, label)
            return
        if key in ("auto_col_convex", "auto_col_box"):
            mode = 'CONVEX' if key == "auto_col_convex" else 'BOX'
            self._run(lambda: self._do_auto_col(mode), label)
            return
        if key in self._MAP_OPS:
            self._run(lambda: self._do_map_op(key, label), label)
            return
        if key.startswith('id_manager_'):
            self._run(lambda: self._do_id_op(key, label), label)
            return
        if key in ('export_to_img', 'remove_from_img', 'verify_img_link', 'rebuild_img'):
            self._run(lambda: self._do_img_op(key, label), label)
            return
        if key in ('scan_binary_ipls', 'extract_textures', 'import_map', 'map_export',
                   'toggle_bbox'):
            self._run(lambda: self._do_maptab_op(key, label), label)
            return
        if key in ("setup:install", "setup:remove"):
            from . import setup_ui
            fn = (setup_ui.install_interactive if key == "setup:install"
                  else setup_ui.remove_interactive)
            self._run(lambda: fn(self), label)
            self._refresh_setup()
            return
        self._reload_dev()
        from inu_max.ops import vehicle_tools, scene_tools, water_tools, anim_tools, camera_tools, radar_tools, path_tools, mesh_tools, node_tools, ipl_tools, rig_tools, weight_tools
        operations = dict(vehicle_tools.OPERATIONS, **scene_tools.OPERATIONS,
                          **water_tools.OPERATIONS, **anim_tools.OPERATIONS,
                          **camera_tools.OPERATIONS, **radar_tools.OPERATIONS,
                          **path_tools.OPERATIONS, **mesh_tools.OPERATIONS, **node_tools.OPERATIONS,
                          **ipl_tools.OPERATIONS, **rig_tools.OPERATIONS, **weight_tools.OPERATIONS)
        if key in ('import_ipl_sections', 'export_ipl_sections') and 'path' not in options:
            from .file_dialog import INUFileDialog
            exporting = key.startswith('export')
            dialog = INUFileDialog(self, label, mode='save' if exporting else 'open',
                key='ipl_sections', filename='sections.ipl',
                filters=[('GTA IPL (*.ipl)', ['*.ipl'])], accept_label='Export' if exporting else 'Import')
            if not dialog.exec():
                return
            options['path'] = dialog.save_path() if exporting else dialog.selected_files()[0]
        if key == 'batch_set_distance' and 'values' not in options:
            from ..adapter import selection
            active = selection.active_node()
            if active is None:
                self._show_result(label, 'WARNING', 'Select models first')
                return
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle('INU: Batch IDE properties')
            form = QtWidgets.QFormLayout(dialog)
            fields = {}
            for caption, field, default in (
                ('Draw distance', 'draw_distance', 300.0), ('LOD distance', 'lod_draw_distance', 999.0),
                ('Starting Model ID', 'model_id', 0), ('Interior', 'interior_id', 0),
                ('IDE flags', 'ide_flags', 0), ('TXD', 'txd_name', ''), ('COL Library', 'col_library', '')):
                enabled = QtWidgets.QCheckBox(caption)
                enabled.setChecked(field in ('draw_distance', 'lod_draw_distance'))
                value = selection.get_field(active, field, default)
                if isinstance(default, str):
                    widget = QtWidgets.QLineEdit(value)
                    getter = widget.text
                elif isinstance(default, float):
                    widget = QtWidgets.QDoubleSpinBox()
                    widget.setRange(0, 100000)
                    widget.setValue(value)
                    getter = widget.value
                else:
                    widget = QtWidgets.QSpinBox()
                    widget.setRange(0, 2**31-1)
                    widget.setValue(value)
                    getter = widget.value
                form.addRow(enabled, widget)
                fields[field] = enabled, getter
            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            form.addRow(buttons)
            if not dialog.exec():
                return
            options['values'] = {key: getter() for key, (enabled, getter) in fields.items() if enabled.isChecked()}
        if key == 'validate_run':
            self._run(lambda: self.pre_check.set_issues(scene_tools.validate_scene()), label)
            return
        if key in operations:
            def go():
                level, text = operations[key](**options)
                self._show_result(label, level, text)
                self._poll_selection(force=True)
            self._run(go, label)
            return
        op = self._OPS.get(key)
        if op is not None:
            mod, fn = op
            self._run(lambda: getattr(__import__(mod, fromlist=[fn]), fn)(), label)
            return
        self._unknown_operation(label, key)

    # операции окна Map IO: ключ → модуль inu_max.ops; функция возвращает
    # (уровень, текст отчёта)
    _MAP_OPS = {
        'auto_find_lod': 'map_link_ops',
        'scan_img_for_ipl': 'map_import',
        'scan_ide_for_ipl': 'map_import',
        'import_from_img': 'map_import',
        # связь IDE / IPL (вкладка Export)
        'upsert_ide': 'map_link_ops', 'remove_ide': 'map_link_ops',
        'export_ide': 'map_link_ops', 'upsert_ipl': 'map_link_ops',
        'remove_ipl': 'map_link_ops', 'export_ipl': 'map_link_ops',
        'link_verify': 'map_link_ops', 'link_unlink': 'map_link_ops',
        'ide_sync_from_file': 'map_link_ops', 'ide_sync_export': 'map_link_ops',
        'ide_remove_link': 'map_link_ops', 'ipl_restore_coords': 'map_link_ops',
        'ipl_sync_export': 'map_link_ops', 'ipl_remove_link': 'map_link_ops',
        'ipl_sync_from_file': 'map_link_ops',
    }
    # операции с окном подтверждения (пробный прогон → проблемы / удаление)
    _CONFIRM_OPS = {'upsert_ide', 'remove_ide', 'upsert_ipl', 'remove_ipl',
                    'link_unlink', 'ide_sync_export', 'ide_remove_link',
                    'ipl_sync_export', 'ipl_remove_link'}

    def _do_map_op(self, key, label):
        self._reload_dev()
        import importlib
        mod = importlib.import_module('inu_max.ops.' + self._MAP_OPS[key])
        fn = getattr(mod, key)
        if key in self._CONFIRM_OPS:
            res = fn(confirm=self._confirm)
        elif key in ('export_ide', 'export_ipl'):
            args = self._export_path(key)
            if args is None:
                return
            res = fn(*args)
        else:
            res = fn()
        self._after_map_op()
        if res is None:                                # отменено в подтверждении
            return
        level, text = res
        self._show_result(label, level, text, popup=key == 'import_from_img')

    def _do_id_op(self, key, label):
        """Кнопки ID Manager (ops/id_manager_ops): диалоги From ID... и Extend
        FLA, подтверждения Create ID / Clear All, ✕ «id_manager_release:<ID>»."""
        self._reload_dev()
        from ..ops import id_manager_ops as IM
        if key.startswith('id_manager_release:'):
            res = IM.id_manager_release(int(key.split(':', 1)[1]), confirm=self._confirm)
        elif key == 'id_manager_assign_from':
            args = self._id_dialog(
                "INU: Assign IDs from...",
                [("Start ID", 321, 1, 999999, "Starting ID for assignment")],
                ("Skip occupied IDs", True, "On — skip already-occupied IDs (like "
                 "auto-assign). Off — strictly sequential from the start ID, even if "
                 "occupied"))
            if args is None:
                return
            res = IM.id_manager_assign_from(args[0], args[1])
        elif key == 'id_manager_extend':
            args = self._id_dialog("INU: Extend IDs",
                                   [("Count", 1000, 100, 50000, "Number of IDs to add")])
            if args is None:
                return
            res = IM.id_manager_extend(args[0])
        elif key in ('id_manager_create', 'id_manager_clear'):
            res = getattr(IM, key)(confirm=self._confirm)
        else:
            fn = getattr(IM, key, None)
            if fn is None:
                self._unknown_operation(label, key)
                return
            res = fn()
        id_mgr = getattr(self, 'id_mgr', None)
        if id_mgr is not None:
            id_mgr.refresh()
        self._sel_key = object()                       # Model ID в окнах — заново
        if res is None:
            return
        level, text = res
        self._show_result(label, level, text)

    def _do_img_op(self, key, label, use_export_options=False):
        """Строка IMG (ops/img_ops): Export — окно с моделями и архивом,
        Remove / Rebuild — подтверждение, Verify — сразу."""
        self._reload_dev()
        from ..ops import img_ops as IO
        if key == 'export_to_img':
            items = IO.plan()
            if use_export_options:
                for item in items:
                    for option, setting in (('inc_dff', 'exp_dff'), ('inc_lod', 'exp_lod'),
                                            ('inc_col', 'exp_col'), ('inc_txd', 'exp_txd')):
                        item[option] = bool(item[option] and self._get(setting, True))
            if not items:
                self._show_result(label, 'ERROR', "Select mesh objects")
                return
            args = self._img_export_dialog(items, IO.archive_choices())
            if args is None:
                return
            res = IO.export_to_img(*args)
            if use_export_options and res[0] != 'ERROR' and self._get('exp_ide_ipl', False):
                from ..ops import map_link_ops
                reports = [map_link_ops.upsert_ide(), map_link_ops.upsert_ipl()]
                level = 'ERROR' if any(r and r[0] == 'ERROR' for r in reports) else res[0]
                res = level, res[1] + '\n' + '\n'.join(r[1] for r in reports if r)
        elif key == 'remove_from_img':
            res = IO.remove_from_img(confirm=self._confirm)
        elif key == 'rebuild_img':
            res = IO.rebuild_img(confirm=self._confirm)
        else:
            res = IO.verify_img_link()
        self._after_map_op()
        if res is None:
            return
        level, text = res
        self._show_result(label, level, text, popup=key == 'export_to_img')

    def _do_maptab_op(self, key, label):
        """Вкладка Map (ops/map_tab, ops/map_export)."""
        self._reload_dev()
        from ..ops import map_tab as MT
        if key == 'map_export':
            from ..ops import map_export as MX
            args = self._map_export_dialog(MX)
            if args is None:
                return
            res = MX.export_map(args[0], args[1], confirm=self._confirm)
        else:
            res = getattr(MT, key)()
        self._after_map_op()
        if res is None:
            return
        level, text = res
        self._show_result(label, level, text,
                          popup=key in ('import_map', 'extract_textures', 'map_export'))

    def _map_export_dialog(self, MX):
        """Окно Export Map: папка + опции справа (как диалог INU). (папка,
        opts) или None."""
        from .file_dialog import INUFileDialog
        from .. import settings
        g = settings.get
        info = MX.plan_info()
        opts_w = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(opts_w)
        form.setContentsMargins(4, 4, 4, 4)
        what = QtWidgets.QLabel("%s: %d placement(s), %d model(s)%s" % (
            "Selection" if info['scope'] == 'selection' else "Whole scene",
            info['placements'], info['models'],
            ("\n%d model(s) without ID — from ID Manager" % info['zero']) if info['zero'] else ""))
        what.setWordWrap(True)
        form.addRow(what)
        base = QtWidgets.QLineEdit(g('map_exp_base', 'district') or 'district')
        base.setToolTip("Name of the IDE / IPL files (and of the cells)")
        form.addRow("Base Name", base)
        cbs = {}
        for key, text, dflt, tip in (
                ('dff', "DFF", True, "Models (.dff) and their LOD<model>.dff"),
                ('col', "COL", True, "Collision (.col)"),
                ('txd', "TXD", True, "Textures (.txd, merged with an existing file)"),
                ('ide', "IDE", True, "Object definitions (.ide)"),
                ('ipl', "IPL", True, "Placements (.ipl): every placement + LOD rows"),
                ('col_library', "COL Library", False,
                 "All collision of a cell into one <cell>.col instead of one .col per model"),
                ('binary', "Binary IPL", False,
                 "SA: <cell>.ipl (text, LOD rows) + <cell>_stream0.ipl (binary, models) — "
                 "put the stream file into an IMG"),
                ('fla', "FLA: real_interior", False,
                 "Write the 12th realInterior column (Fastman92 Limit Adjuster)")):
            c = QtWidgets.QCheckBox(text)
            c.setChecked(bool(g('map_exp_' + key, dflt)))
            c.setToolTip(tip)
            form.addRow(c)
            cbs[key] = c
        split = QtWidgets.QComboBox()
        for k, t in MX.SPLITS:
            split.addItem(t, k)
        split.setCurrentIndex(max(0, split.findData(g('map_exp_split', 'NONE'))))
        form.addRow("Split", split)
        spins = {}
        for key, text, dflt, lo, hi in (('cell_size', "Cell size (m)", 256, 16, 8192),
                                        ('max_per_cell', "Max DFFs per cell", 200, 1, 100000),
                                        ('min_cell_size', "Min cell size (m)", 16, 1, 8192)):
            s = QtWidgets.QSpinBox()
            s.setRange(lo, hi)
            s.setValue(int(g('map_exp_' + key, dflt)))
            form.addRow(text, s)
            spins[key] = s
        dlg = INUFileDialog(self, "INU: Export Map — target folder", mode='folder',
                            key='map_export', options=opts_w, accept_label="Export")
        if not dlg.exec() or not dlg.selected_folder():
            return None
        opts = dict(base_name=base.text().strip() or 'district', split=split.currentData())
        for k, c in cbs.items():
            opts[k] = c.isChecked()
            settings.set('map_exp_' + k, opts[k])
        for k, s in spins.items():
            opts[k] = s.value()
            settings.set('map_exp_' + k, opts[k])
        settings.set('map_exp_base', opts['base_name'])
        settings.set('map_exp_split', opts['split'])
        return dlg.selected_folder(), opts

    def _img_export_dialog(self, items, choices):
        """Окно Export to IMG (как диалог INU): архив для моделей без своего,
        по модели — DFF / LOD / COL / TXD, заглушки LOD / COL (выкл),
        «Rebuild after export». (items, архив, rebuild) или None."""
        import os
        from .file_dialog import INUFileDialog
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("INU: Export to IMG")
        v = QtWidgets.QVBoxLayout(dlg)
        need = [it for it in items if not it['own']]
        combo = QtWidgets.QComboBox()
        for p in choices:
            combo.addItem(os.path.basename(p), p)
            combo.setItemData(combo.count() - 1, p, QtCore.Qt.ToolTipRole)
        combo.addItem("Browse…", '')
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("IMG archive:"))
        row.addWidget(combo, 1)
        v.addLayout(row)
        hint = QtWidgets.QLabel("For models that are not in an IMG yet (%d). Models with "
                                "their own IMG are written into it." % len(need))
        hint.setWordWrap(True)
        v.addWidget(hint)

        def browse(i):
            if combo.itemData(i) != '':
                return
            d = INUFileDialog(self, "INU: IMG archive", mode='open', key='img_export',
                              accept_label="Select",
                              filters=[("GTA IMG (*.img)", ["*.img"]), ("All Files (*.*)", ["*"])])
            if d.exec() and d.selected_files():
                p = d.selected_files()[0]
                combo.insertItem(0, os.path.basename(p), p)
                combo.setCurrentIndex(0)
            else:
                combo.setCurrentIndex(0 if combo.count() > 1 else -1)
        combo.currentIndexChanged.connect(browse)

        area = QtWidgets.QScrollArea()
        area.setWidgetResizable(True)
        host = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(host)
        lay.setContentsMargins(4, 4, 4, 4)
        boxes = []
        for it in items:
            where = os.path.basename(it['own']) if it['own'] else "chosen archive"
            lay.addWidget(QtWidgets.QLabel("<b>%s</b> → %s" % (it['name'], where)))
            cbs = {}

            def cb(key, text, on, enabled=True, tip=''):
                c = QtWidgets.QCheckBox(text)
                c.setChecked(on)
                c.setEnabled(enabled)
                c.setToolTip(tip)
                lay.addWidget(c)
                cbs[key] = c
            if it['dff'] is not None:
                cb('inc_dff', "DFF: %s.dff" % it['name'], it['inc_dff'])
            if it['lod'] is not None:
                cb('inc_lod', "LOD: %s.dff" % it['lod_name'], it['inc_lod'])
            elif it['dff'] is not None:
                cb('stub_lod', "LOD stub: LOD%s.dff = copy of the model" % it['name'], False,
                   tip="No LOD mesh in the scene — write a copy of the model as its LOD")
            if it['dff'] is not None:
                if it['col_meshes'] or it['col_prims']:
                    cb('inc_col', "COL: %d mesh(es), %d sphere/box — into its COL library in "
                       "the archive (or %s.col)" % (len(it['col_meshes']), len(it['col_prims']),
                                                    it['name']), it['inc_col'])
                else:
                    cb('stub_col', "COL stub: empty collision", False,
                       tip="No collision in the scene — write an empty COL record")
            txds = sorted({it['txd'], it['lod_txd']} - {''})
            cb('inc_txd', "TXD: %s (merged with the archive TXD)"
               % ", ".join(t + ".txd" for t in txds), it['inc_txd'])
            boxes.append((it, cbs))
        lay.addStretch(1)
        area.setWidget(host)
        area.setMinimumSize(420, 260)
        v.addWidget(area, 1)
        rb = QtWidgets.QCheckBox("Rebuild after export")
        rb.setToolTip("After writing, compact the IMG archive (dead space left by replaced "
                      "entries is removed)")
        v.addWidget(rb)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                        | QtWidgets.QDialogButtonBox.Cancel)
        bb.button(QtWidgets.QDialogButtonBox.Ok).setText("Export")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if not dlg.exec():
            return None
        for it, cbs in boxes:
            for key, c in cbs.items():             # остальные — как в плане
                it[key] = c.isChecked()
        arch = combo.currentData() or ''
        if need and not arch:
            self._show_result("Export to IMG", 'ERROR', "Choose an IMG archive")
            return None
        return items, arch, rb.isChecked()

    def _id_dialog(self, title, spins, check=None):
        """Маленький диалог: числа [(подпись, умолч., мин, макс, подсказка)] +
        галочка (подпись, умолч., подсказка). None — отмена."""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(title)
        form = QtWidgets.QFormLayout(dlg)
        boxes = []
        for lbl, dflt, lo, hi, tip in spins:
            sb = QtWidgets.QSpinBox()
            sb.setRange(lo, hi)
            sb.setValue(dflt)
            sb.setToolTip(tip)
            form.addRow(lbl, sb)
            boxes.append(sb)
        cb = None
        if check is not None:
            cb = QtWidgets.QCheckBox(check[0])
            cb.setChecked(check[1])
            cb.setToolTip(check[2])
            form.addRow(cb)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                        | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if not dlg.exec():
            return None
        out = [b.value() for b in boxes]
        if cb is not None:
            out.append(cb.isChecked())
        return out

    def _confirm(self, title, lines, question):
        """Окно подтверждения (ConfirmOnProblems INU): строки + вопрос."""
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Warning, "INU Tools: " + title,
                                    "\n".join(lines) + "\n\n" + question,
                                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, self)
        box.setDefaultButton(QtWidgets.QMessageBox.No)
        return box.exec() == QtWidgets.QMessageBox.Yes

    def _export_path(self, key):
        """Export IDE / IPL: путь нового файла (+ «Binary» для IPL)."""
        from .file_dialog import INUFileDialog
        ext = 'ide' if key == 'export_ide' else 'ipl'
        opts, binary = None, None
        if ext == 'ipl':
            opts = QtWidgets.QWidget()
            ol = QtWidgets.QVBoxLayout(opts)
            ol.setContentsMargins(4, 4, 4, 4)
            binary = QtWidgets.QCheckBox("Binary (bnry)")
            binary.setToolTip("Write the IPL in binary format (inst + cars only)")
            ol.addWidget(binary)
            ol.addStretch(1)
        dlg = INUFileDialog(self, "INU: Export %s (.%s)" % (ext.upper(), ext), mode='save',
                            key='export_' + ext, accept_label="Export", options=opts,
                            filename='model.' + ext,
                            filters=[("GTA %s (*.%s)" % (ext.upper(), ext), ["*." + ext])])
        if not dlg.exec() or not dlg.save_path():
            return None
        path = dlg.save_path()
        return (path,) if ext == 'ide' else (path, binary.isChecked())

    def _show_result(self, label, level, text, popup=False):
        '''Отчёт операции: INFO — строкой в статусе Max (и в Listener),
        предупреждение / ошибка (или popup) — немодальным окном.'''
        if not text:
            return
        print("[INU] %s: %s" % (label, text.replace("\n", " | ")))
        if popup or level != 'INFO':
            icon = {'ERROR': QtWidgets.QMessageBox.Critical,
                    'WARNING': QtWidgets.QMessageBox.Warning}.get(
                        level, QtWidgets.QMessageBox.Information)
            # немодально: модальный цикл Qt поверх Max мешал догрузке
            # текстур вьюпорта (см. _import_paths)
            box = QtWidgets.QMessageBox(icon, "INU Tools: " + label, text,
                                        QtWidgets.QMessageBox.Ok, self)
            box.setModal(False)
            box.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            box.show()
        else:
            try:
                import pymxs
                pymxs.runtime.displayTempPrompt(text, 6000)
            except Exception:                          # noqa: BLE001
                pass

    def _after_map_op(self):
        """После операции Map IO: списки файлов, найденные IMG / IDE, игра
        (импорт мог её переключить), статусы выделения."""
        ide_ipl = getattr(self, 'ide_ipl', None)
        if ide_ipl is not None:
            imp, exp = ide_ipl.pages['IMPORT'], ide_ipl.pages['EXPORT']
            for lst in (imp.ipls, exp.ipls, exp.ides):
                lst.rebuild()
            imp.refresh()
            exp.refresh()
            ide_ipl.pages['MAP'].refresh()
        self._sync_from_settings()
        for fn in self._game_handlers:
            fn()
        self._sel_key = object()

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

    def _unknown_operation(self, label, key):
        QtWidgets.QMessageBox.information(
            self, "INU Tools",
            "\"%s\" (%s) has no registered handler." % (label, key))


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
