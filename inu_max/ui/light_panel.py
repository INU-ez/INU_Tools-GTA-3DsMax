# INU Tools (Max) — окно Lighting: панель INU «Lighting» (вкладки PreLight /
# PreLight COL). Состав и подписи — как в Blender-версии (англ. из
# locale/eng.py), оформление — роллауты Kam's.
#
# Часть 1 (работает): пресеты, 8 ламп и солнце, слои Day / Night (выбор,
# создать, удалить, поле V), превью Prelight и альфы, запекание (Bake /
# Bake over, с тенями и без), фильтры ламп, Day ↔ Night, Advanced Settings,
# коррекция превью. Часть 2: роллауты Tools / Foliage / Tree /
# Post-Processing (ToolsPanel, FoliagePanel, PostPanel ниже). Дальше:
# PreLight COL (часть 3), LightMap UV2 (часть 4). Вкладки Itera нет —
# Itera Tools 3 работает только в Blender.

from PySide6 import QtWidgets, QtCore

from .style import BTN_H, icon
from .widgets import (BuildMixin, FusedBlock, Expander, NumEdit, IntEdit, ColorSwatch,
                      IconLabel, icon_btn)

LAYERS = ('Day', 'Night')


def _ps():
    from ..adapter import prelight_scene
    return prelight_scene


def _tools():
    from ..ops import prelight_tools
    return prelight_tools


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as e:                             # noqa: BLE001
        if 'pymxs' not in str(e):
            print("[INU] lighting: %r" % (e,))
        return default


def _btn(label, tip, slot=None, icon_name=None, checkable=False, height=BTN_H):
    b = QtWidgets.QPushButton(label)
    b.setToolTip(tip)
    b.setFixedHeight(height)
    b.setCheckable(checkable)
    if icon_name:
        b.setIcon(icon(icon_name))
    if slot is not None:
        b.clicked.connect(lambda _c=False: slot())
    return b


class LightingPanel(BuildMixin, QtWidgets.QWidget):
    """Вкладки PreLight / PreLight COL. run(label, функция, *аргументы) —
    вызов операции ops/prelight.py (окно показывает отчёт и зовёт refresh)."""

    _TABS = (("PreLight", 'PRELIGHT', "Prelight with vertex colors"),
             ("PreLight COL", 'COL', "Vertex colors → COL Day/Night"))

    def __init__(self, run, parent=None):
        super().__init__(parent)
        self._run = run
        self._node = None
        # активный слой могут сменить и в стеке Modify (выбран VertexPaint
        # другого слоя) — кнопки перечитываются по счётчику prelight_scene
        self._state_gen = None
        self._state_timer = QtCore.QTimer(self)
        self._state_timer.setInterval(700)
        self._state_timer.timeout.connect(self._poll_state)
        self._state_timer.start()
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        tabs, self._tab_group = self._seg_buttons(
            self._TABS, self._get('light_mode', 'PRELIGHT'), self._on_tab)
        lay.addWidget(FusedBlock([tabs], height=BTN_H + 3))
        self.pages = {'PRELIGHT': self._prelight_page(), 'COL': self._col_page()}
        for p in self.pages.values():
            lay.addWidget(p)
        self._on_tab(self._get('light_mode', 'PRELIGHT'))

    def _on_tab(self, mode):
        self._set('light_mode', mode)
        for m, p in self.pages.items():
            p.setVisible(m == mode)
        for fn in getattr(self, 'tab_handlers', ()):
            fn(mode)

    # ── PreLight ──────────────────────────────────────────────────────
    def _prelight_page(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        run = self._run

        # пресеты: [Apply][список][✎][+][−][⇪]
        self._preset = QtWidgets.QComboBox()
        self._preset.setFixedHeight(BTN_H)
        self._preset.setToolTip("Select prelight settings preset")
        self._preset.currentIndexChanged.connect(self._on_preset)
        apply_b = _btn("Apply", "Load the selected preset",
                       lambda: run("Load preset", 'preset_load'), 'check')
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(3)
        row.addWidget(apply_b)
        row.addWidget(self._preset, 1)
        row.addWidget(FusedBlock([[
            icon_btn('edit', "Rename the selected preset", self._rename_preset),
            icon_btn('add', "Save current settings as a preset", self._save_preset),
            icon_btn('remove', "Delete the selected preset",
                     lambda: run("Delete preset", 'preset_delete')),
            icon_btn('export', "Overwrite the selected preset with the current settings "
                     "(no name dialog)", lambda: run("Overwrite preset", 'preset_overwrite'))]]))
        lay.addLayout(row)

        # лампы
        self._b_lights = _btn("Light (8 lamps)", "Toggle 8-light setup: create if no lamps "
                              "exist, remove if they do",
                              lambda: run("Light (8 lamps)", 'toggle_lights'), checkable=True)
        self._b_sun = _btn("Sun", "Create/remove a 'sun' for prelight (separate from the 8 "
                           "points). A directional source at a 'top-front' angle (like the GTA "
                           "sun), colored like the 8 lamps. Baked with the same buttons (POINT "
                           "and SUN are counted together). Tune the multiplier if it's "
                           "brighter/darker than the eight.",
                           lambda: run("Sun", 'toggle_sun'), checkable=True)
        lay.addWidget(FusedBlock([[self._b_lights, self._b_sun]]))

        # слои Day / Night, превью, альфа
        b = self._box()
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(3)
        grid.setVerticalSpacing(2)
        self._eye = QtWidgets.QPushButton()
        self._eye.setCheckable(True)
        self._eye.setFixedSize(BTN_H + 4, BTN_H * 2 + 2)
        self._eye.setToolTip("Toggle prelight preview - show the active layer's vertex colors "
                             "(with the preview correction) unlit over the textures, like in the "
                             "game. While a VertexPaint modifier is open in the Modify panel, its "
                             "channel is shown directly (strokes appear at once, no correction). "
                             "Off - vertex colors are hidden, also while VertexPaint is open")
        self._eye.clicked.connect(lambda on: run("Prelight preview", 'preview', bool(on)))
        grid.addWidget(self._eye, 0, 0, 2, 1)
        self._rows = {}
        for i, layer in enumerate(LAYERS):
            sel = QtWidgets.QPushButton(layer)
            sel.setCheckable(True)
            sel.setFixedHeight(BTN_H)
            sel.setToolTip("Select color attribute and update prelight preview. To repaint the "
                           "layer, add a VertexPaint modifier (Vertex Color - Day, Vertex Illum "
                           "- Night)")
            sel.clicked.connect(lambda _c=False, l=layer: run("Select " + l, 'select_layer', l))
            v = NumEdit(decimals=0, lo=-100.0, hi=100.0, step=1.0, prefix="V ")
            v.setFixedHeight(BTN_H)
            v.setToolTip("V-offset for %s vcol — applied automatically when changed" % layer)
            v.editingFinished.connect(lambda l=layer, w=v: self._on_v(l, w))
            pm = icon_btn('add', "", None)
            pm.clicked.connect(lambda _c=False, l=layer: self._on_add_remove(l))
            grid.addWidget(sel, i, 1)
            grid.addWidget(v, i, 2)
            grid.addWidget(pm, i, 3)
            self._rows[layer] = (sel, v, pm)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 2)
        b.addLayout(grid)
        self._b_alpha = _btn("Vertex alpha (scene)", "Show vertex alpha (channel -2) in the "
                             "viewport as grayscale (white = opaque) on every model of the scene "
                             "that has it, independently of the prelight (RGB) preview",
                             None, 'eye', checkable=True)
        self._b_alpha.clicked.connect(lambda on: run("Vertex alpha", 'alpha_preview', bool(on)))
        arow = QtWidgets.QHBoxLayout()
        arow.setSpacing(3)
        arow.addWidget(self._b_alpha, 1)
        arow.addWidget(icon_btn('trash', "Completely remove vertex alpha (channel -2) from the "
                                "selected meshes, so the model exports without vertex alpha",
                                lambda: run("Clear vertex alpha", 'clear_alpha')))
        b.addLayout(arow)
        lay.addWidget(b.box)

        # запекание
        lay.addWidget(FusedBlock([[
            _btn("Bake over", "Bake lamp light ON TOP of the existing prelight (additive, "
                 "Add), without shadows. The current color is NOT erased — illumination is "
                 "added to it. Writes to the active channel (Day/Night), values are clamped to "
                 "0–1", lambda: run("Bake over", 'bake', False, True), 'add'),
            _btn("Bake over (shadows)", "Bake lamp and sun light ON TOP of the existing "
                 "prelight (additive, Add) with shadow computation. The current color is NOT "
                 "erased — illumination is added to it. Writes to the active channel "
                 "(Day/Night), values are clamped to 0–1",
                 lambda: run("Bake over (shadows)", 'bake', True, True), 'add')]]))
        lay.addWidget(FusedBlock([[
            _btn("Bake", "Quickly bake lamp light into the active channel (Day/Night), without "
                 "shadows. OVERWRITES the current color", lambda: run("Bake", 'bake', False, False)),
            _btn("Bake with shadows", "Bake lamp and sun light into the active channel "
                 "(Day/Night) with shadow computation. OVERWRITES the current color",
                 lambda: run("Bake with shadows", 'bake', True, False))]], height=BTN_H + 12))
        lay.addWidget(FusedBlock([[
            self._tbtn("Point", 'prelight_use_point', True, "Include Point lamps (Omni) when "
                       "baking prelight"),
            self._tbtn("Sun", 'prelight_use_sun', True, "Include the Sun (Direct lights) when "
                       "baking prelight"),
            self._tbtn("Spot", 'prelight_use_spot', True, "Include Spot lamps (with cone) when "
                       "baking prelight"),
            self._tbtn("Area", 'prelight_use_area', True, "Include Area lamps when baking "
                       "prelight (treated as a point source). 3ds Max photometric lights are "
                       "not used"),
            self._tbtn("HDRI", 'prelight_use_hdri', False, "Add world lighting: the scene "
                       "environment (Rendering > Environment) colour is added along the "
                       "normal. Can be combined with lamps via the Point/Sun/Spot/Area toggles")]]))
        lay.addWidget(FusedBlock([[
            _btn("Day → Night", "Copy vertex colors between attributes (Day ↔ Night)",
                 lambda: run("Day → Night", 'copy_layer', 'Day', 'Night')),
            _btn("Night → Day", "Copy vertex colors between attributes (Day ↔ Night)",
                 lambda: run("Night → Day", 'copy_layer', 'Night', 'Day'))]]))

        # LightMap UV2 — часть 4
        stub = self._stub
        lay.addWidget(FusedBlock([[
            icon_btn('eye_off', "Toggle LightMap UV2 display", stub("LightMap UV2 (toggle)")),
            _btn("Add LightMap", "Apply a LightMap texture on UV2 (Multiply) for selected "
                 "objects", stub("Add LightMap")),
            icon_btn('remove', "Remove LightMap UV2 from selected objects' materials",
                     stub("Remove LightMap UV2"))]]))
        lay.addWidget(FusedBlock([[
            _btn("LightMap from folder…", "Load LightMaps for the selected models from a "
                 "folder: <name>_d = day map, <name>_n = night map (matched by object name)",
                 stub("LightMap from folder")),
            _btn("Day", "Show the day LightMap on the models", stub("LightMap Day")),
            _btn("Night", "Show the night LightMap on the models", stub("LightMap Night"))]]))

        # коррекция превью
        b = self._box()
        ex = Expander(self, 'show_prelight_view', False, "Preview correction")
        ex.set_tip("Show the sliders for visual correction of the prelight preview "
                   "(brightness/contrast/gamma/saturation). Viewport only — does not affect "
                   "export")
        for label, key, lo, hi, dflt, tip in (
                ("Brightness", 'prelight_view_bright', -1.0, 1.0, 0.004,
                 "Viewport only: prelight brightness in the preview. Does NOT affect export"),
                ("Contrast", 'prelight_view_contrast', -1.0, 1.0, 0.0,
                 "Viewport only: prelight contrast in the preview. Does NOT affect export"),
                ("Gamma", 'prelight_view_gamma', 0.1, 4.0, 1.0,
                 "Viewport only: prelight gamma in the preview (<1 = brighter). Does NOT "
                 "affect export"),
                ("Saturation", 'prelight_view_saturation', 0.0, 2.0, 1.0,
                 "Viewport only: prelight saturation in the preview (1 = as-is, 0 = "
                 "grayscale). Does NOT affect export")):
            sp = NumEdit(decimals=3, lo=lo, hi=hi, step=0.01)
            sp.setValue(float(self._get(key, dflt)))
            sp.setToolTip(tip)
            sp.setFixedHeight(BTN_H)
            sp.valueChanged.connect(lambda v, k=key: self._on_view(k, v))
            ex.body.addLayout(self._labeled(label, sp, label_w=62))
            setattr(self, '_view_' + key, sp)
        ex.body.addWidget(_btn("Neutral", "Reset the preview correction to neutral — the "
                               "preview then shows the prelight exactly as it will go into "
                               "the game", lambda: run("Neutral", 'view_reset')))
        ex.body.addWidget(self._info("Viewport only, does not affect export"))
        b.addWidget(ex)
        lay.addWidget(b.box)
        return page

    # ── PreLight COL (часть 3; подпанель INU «PreLight COL») ──────────
    def _col_page(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        run = self._run
        self._col_src = IconLabel("", 'info')
        lay.addWidget(self._col_src)
        self._col_auto = IconLabel("", 'warning', wrap=True)
        self._col_auto.setToolTip("Export option 'Collision light' = 'Auto: day + night' sets "
                                  "the same day/night on the whole collision, overriding the "
                                  "materials. To export baked values, switch it to 'From "
                                  "material' in the export window")
        lay.addWidget(self._col_auto)
        for title, icon_name, tip, kmin, kmax, dmin, dmax, tmin, tmax in (
                ("Day light:", 'sun', "Daytime light range for COL materials\nMin/Max — values "
                 "from 0 to 15\nVertex-color brightness is mapped into this range",
                 'col_day_min', 'col_day_max', 10, 15, "Minimum Day Light value (shadow)",
                 "Maximum Day Light value (lit)"),
                ("Night light:", 'light', "Nighttime light range for COL materials\nMin/Max — "
                 "values from 0 to 15\nUses the Night color attribute if present",
                 'col_night_min', 'col_night_max', 0, 5, "Minimum Night Light value (shadow)",
                 "Maximum Night Light value (lit)")):
            b = self._box()
            lb = IconLabel(title, icon_name)
            lb.setToolTip(tip)
            b.addWidget(lb)
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(3)
            for key, dflt, tp, prefix in ((kmin, dmin, tmin, "Min. "), (kmax, dmax, tmax, "Max. ")):
                w = _int(self, key, 0, 15, dflt, tp, prefix=prefix)
                w.valueChanged.connect(lambda _v: self._col_changed())
                row.addWidget(w)
            b.addLayout(row)
            lay.addWidget(b.box)
        # превью + ползунки (видны при включённом превью, как в INU) + запекание
        self._col_prev = _btn("Preview COL Light", "Preview COL Night Light — green overlay and "
                              "per-face numbers (on the active mesh, by its active Day / Night "
                              "layer)", None, 'eye_off', checkable=True)
        self._col_prev.clicked.connect(lambda on: run("Preview COL Light", 'col_preview', bool(on)))
        lay.addWidget(self._col_prev)
        self._col_sliders = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(self._col_sliders)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(3)
        for key, lo, hi, dflt, prefix, tip in (
                ('col_light_edge', -5.0, 5.0, 0.0, "Edge ", "COL lighting boundary offset"),
                ('col_light_threshold', 0, 100, 0, "Threshold ", "Brightness threshold (also "
                 "used by Bake COL Light, so the result matches the preview)"),
                ('col_light_contrast', 0.0, 5.0, 0.0, "Contrast ", "Contrast")):
            w = (_int(self, key, lo, hi, dflt, tip, prefix=prefix) if isinstance(dflt, int)
                 else _num(self, key, lo, hi, dflt, tip, step=0.05, prefix=prefix))
            w.valueChanged.connect(lambda _v: self._col_changed())
            sl.addWidget(w)
        sl.addWidget(self._tbtn("Numbers", 'col_light_show_numbers', True,
                                "Show numbers on polygons (the viewport font; its size can't be "
                                "set in 3ds Max)", on_change=self._col_changed))
        lay.addWidget(self._col_sliders)
        lay.addWidget(FusedBlock([[
            _btn("Bake COL Light", "Convert vertex colors to COL Day / Night Light (split "
                 "materials by brightness)", lambda: run("Bake COL Light", 'col_bake')),
            icon_btn('x', "Delete COL light materials created by Bake COL Light",
                     lambda: run("Clear COL Light", 'col_clear'))]]))
        self._col_info = IconLabel("", 'check')
        lay.addWidget(self._col_info)
        return page

    def _col_changed(self):
        """Правка диапазона / «Края» / «Порога» / «Контраста» / «Цифр» —
        превью пересчитывается через 0.3 с после последней правки."""
        t = getattr(self, '_col_timer', None)
        if t is None:
            t = self._col_timer = QtCore.QTimer(self)
            t.setSingleShot(True)
            t.setInterval(300)
            t.timeout.connect(lambda: _safe(lambda: _tools().col_preview_update()))
        t.start()

    def _col_refresh(self, node):
        PS = _ps()
        has_d = bool(node is not None and _safe(lambda: PS.has_channel(node, 0), False))
        has_n = bool(node is not None and _safe(lambda: PS.has_channel(node, -1), False))
        if has_d or has_n:
            day_src = "Day" if has_d else _safe(lambda: PS.active_layer(node), 'Night')
            self._col_src.setText("Day: %s | Night: %s" % (day_src, "Night" if has_n else day_src))
            self._col_src.setIcon('eyedropper')
        else:
            self._col_src.setText("No vertex colors")
            self._col_src.setIcon('info')
        auto = self._get('col_light_mode', 'AUTO') == 'AUTO'
        self._col_auto.setVisible(auto)
        self._col_auto.setText("Export 'Collision light' = Auto: every face gets Day %d / "
                               "Night %d, baked values are ignored"
                               % (int(self._get('col_auto_day', 14)),
                                  int(self._get('col_auto_night', 4))))
        on = _safe(PS.col_preview_node, None) is not None
        self._col_prev.blockSignals(True)
        self._col_prev.setChecked(on)
        self._col_prev.setText("Hide preview" if on else "Preview COL Light")
        self._col_prev.setIcon(icon('eye' if on else 'eye_off'))
        self._col_prev.blockSignals(False)
        self._col_sliders.setVisible(on)
        n = len(_safe(lambda: PS.col_mats_created(node), []) or []) if node is not None else 0
        self._col_info.setVisible(n > 0)
        self._col_info.setText("COL light materials: %d" % n)
        if on:                                   # превью — на активном меше и его слое
            _safe(lambda: _tools().col_preview_update())

    def _stub(self, label):
        return lambda: QtWidgets.QMessageBox.information(
            self, "INU Tools", "\"%s\" is not implemented yet (LightMap UV2 — part 4)." % label)

    # ── пресеты ───────────────────────────────────────────────────────
    def fill_presets(self):
        from .. import prelight_presets as PP
        cur = self._get('prelight_preset', PP.DEFAULT_NAME)
        names = _safe(PP.names, [PP.DEFAULT_NAME]) or [PP.DEFAULT_NAME]
        self._preset.blockSignals(True)
        self._preset.clear()
        for n in names:
            self._preset.addItem(n, n)
        i = self._preset.findData(cur)
        self._preset.setCurrentIndex(max(0, i))
        self._preset.blockSignals(False)
        self._set('prelight_preset', self._preset.currentData())

    def _on_preset(self, i):
        self._set('prelight_preset', self._preset.itemData(i))

    def _save_preset(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "INU: Save Preset", "Name",
                                                  text="My Preset")
        if ok:
            self._run("Save preset", 'preset_save', name)

    def _rename_preset(self):
        cur = self._get('prelight_preset', 'Default')
        name, ok = QtWidgets.QInputDialog.getText(self, "INU: Rename Preset", "New name",
                                                  text=cur)
        if ok:
            self._run("Rename preset", 'preset_rename', name)

    # ── поля ──────────────────────────────────────────────────────────
    def _on_v(self, layer, w):
        if self._node is None:
            return
        cur = _safe(lambda: _ps().v_value(self._node, layer), 0.0)
        if abs(float(w.value()) - float(cur)) > 1e-6:
            self._run("V %s" % layer, 'set_v', layer, float(w.value()))

    def _on_add_remove(self, layer):
        has = self._rows[layer][2].property('has')
        if has:
            self._run("Remove " + layer, 'remove_layer', layer)
        else:
            self._run("Create " + layer, 'create_layer', layer)

    def _on_view(self, key, v):
        self._set(key, float(v))
        # коррекция — всем узлам с превью, через 0.3 с после последней правки
        # (пересчёт цвета — не на каждый шаг спиннера)
        t = getattr(self, '_view_timer', None)
        if t is None:
            t = self._view_timer = QtCore.QTimer(self)
            t.setSingleShot(True)
            t.setInterval(300)
            t.timeout.connect(lambda: _safe(lambda: _ps().update_view_all()))
        t.start()

    # ── состояние ─────────────────────────────────────────────────────
    def on_selection(self, snap):
        self._node = snap.get('active') if snap else None
        self.refresh()

    def _poll_state(self):
        gen = _safe(lambda: _ps().state_gen(), None)
        if gen is None or gen == self._state_gen:
            return
        first = self._state_gen is None
        self._state_gen = gen
        if not first:
            self.refresh()

    def refresh(self):
        """Состояние кнопок по сцене: лампы, слои активного меша, превью."""
        PS = _ps()
        has8, has_sun = _safe(PS.lights_state, (False, False)) or (False, False)
        for b, on in ((self._b_lights, has8), (self._b_sun, has_sun)):
            b.blockSignals(True)
            b.setChecked(bool(on))
            b.blockSignals(False)
        node = self._node
        mesh = node is not None and _safe(lambda: PS.is_mesh(node), False)
        active = _safe(lambda: PS.active_layer(node), 'Day') if mesh else 'Day'
        for layer, (sel, v, pm) in self._rows.items():
            has = bool(mesh and _safe(lambda l=layer: PS.has_channel(node, PS.LAYER_CHAN[l]), False))
            sel.blockSignals(True)
            sel.setChecked(has and active == layer)
            sel.blockSignals(False)
            sel.setEnabled(has)
            v.blockSignals(True)
            v.setValue(_safe(lambda l=layer: PS.v_value(node, l), 0.0) if mesh else 0.0)
            v.blockSignals(False)
            v.setEnabled(has)
            pm.setProperty('has', has)
            pm.setIcon(icon('remove' if has else 'add'))
            pm.setToolTip("Delete a color attribute by name across all selected objects" if has
                          else "Create color attribute")
            pm.setEnabled(bool(mesh))
        on = bool(mesh and _safe(lambda: PS.preview_on(node), False))
        self._eye.blockSignals(True)
        self._eye.setChecked(on)
        self._eye.setIcon(icon('eye' if on else 'eye_off'))
        self._eye.blockSignals(False)
        self._eye.setEnabled(bool(mesh))
        a_on = bool(_safe(PS.alpha_preview_on, False))
        self._b_alpha.blockSignals(True)
        self._b_alpha.setChecked(a_on)
        self._b_alpha.setIcon(icon('eye' if a_on else 'eye_off'))
        self._b_alpha.blockSignals(False)
        for key in ('prelight_view_bright', 'prelight_view_contrast', 'prelight_view_gamma',
                    'prelight_view_saturation'):
            sp = getattr(self, '_view_' + key)
            sp.blockSignals(True)
            sp.setValue(float(self._get(key, sp.value())))
            sp.blockSignals(False)
        self.fill_presets()
        self._col_refresh(node if mesh else None)


class AdvancedSettings(BuildMixin, QtWidgets.QWidget):
    """«Advanced Settings» PreLight: Ambient / Intensity / Gamma (только для
    «Bake» / «Bake over») + Reset to Default."""

    def __init__(self, run, parent=None):
        super().__init__(parent)
        self._run = run
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self._spins = {}
        for label, key, lo, hi, dflt, tip in (
                ("Ambient", 'bake_ambient', 0.0, 0.5, 0.10, "Base ambient light"),
                ("Intensity", 'bake_intensity', 0.0001, 0.5, 0.05, "Light intensity multiplier"),
                ("Gamma", 'bake_gamma', 0.1, 3.0, 0.50, "Gamma correction")):
            sp = NumEdit(decimals=4, lo=lo, hi=hi, step=0.01)
            sp.setValue(float(self._get(key, dflt)))
            sp.setToolTip(tip)
            sp.setFixedHeight(BTN_H)
            sp.valueChanged.connect(lambda v, k=key: self._set(k, float(v)))
            lay.addLayout(self._labeled(label, sp, label_w=62))
            self._spins[key] = (sp, dflt)
        lay.addWidget(_btn("Reset to Default", "Reset bake settings to default",
                           self._reset, 'refresh'))

    def _reset(self):
        self._run("Reset to Default", 'reset_bake_settings')
        self.refresh()

    def refresh(self):
        for key, (sp, dflt) in self._spins.items():
            sp.blockSignals(True)
            sp.setValue(float(self._get(key, dflt)))
            sp.blockSignals(False)


# ── часть 2: Tools / Foliage / Tree / Post-Processing ─────────────────
# Состав, подписи и подсказки — как в подпанелях INU «Инструменты», «Листва /
# Дерево», «Post-Processing» (англ. из locale/eng.py). «Свет → топология»
# (резак) — часть 5.

def _swatch(owner, key, default, title, tip):
    """Поле цвета (RGB 0..1, sRGB — как палитра Blender), привязанное к settings."""
    rgb = list(owner._get(key, list(default)))[:3]
    sw = ColorSwatch(tuple(float(c) for c in rgb) + (1.0,), title=title, tip=tip)
    sw.changed.connect(lambda rgba, k=key: owner._set(k, [float(c) for c in rgba[:3]]))
    return sw


def _num(owner, key, lo, hi, dflt, tip, decimals=3, step=0.01, prefix=''):
    sp = NumEdit(decimals=decimals, lo=lo, hi=hi, step=step, prefix=prefix)
    sp.setValue(float(owner._get(key, dflt)))
    sp.setToolTip(tip)
    sp.setFixedHeight(BTN_H)
    sp.valueChanged.connect(lambda v, k=key: owner._set(k, float(v)))
    return sp


def _int(owner, key, lo, hi, dflt, tip, prefix=''):
    sp = IntEdit(lo=lo, hi=hi, prefix=prefix, tip=tip)
    sp.setValue(int(owner._get(key, dflt)))
    sp.setFixedHeight(BTN_H)
    sp.valueChanged.connect(lambda v, k=key: owner._set(k, int(v)))
    return sp


class _Bound:
    """Контролы, привязанные к settings, — перечитать после пресета."""

    def _bind(self, key, dflt, w):
        self.__dict__.setdefault('_bound', []).append((key, dflt, w))
        return w

    def refresh(self):
        for key, dflt, w in getattr(self, '_bound', ()):
            v = self._get(key, dflt)
            w.blockSignals(True)
            if isinstance(w, ColorSwatch):
                w.set_rgba(tuple(float(c) for c in list(v)[:3]) + (1.0,))
            elif isinstance(w, QtWidgets.QCheckBox):
                w.setChecked(bool(v))
            elif isinstance(w, IntEdit):
                w.setValue(int(v))
            else:
                w.setValue(float(v))
            w.blockSignals(False)


class ToolsPanel(_Bound, BuildMixin, QtWidgets.QWidget):
    """Роллаут «Tools» (подпанель INU «Инструменты»)."""

    def __init__(self, run, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # ── Fill with one color ──
        b = self._box()
        b.addWidget(IconLabel("Fill with one color:", 'eyedropper'))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        for label, key, dflt, tip in (
                ("Day", 'fill_prelight_day', (124 / 255.0,) * 3,
                 "Day prelight color (Day). Default 124,124,124 — the dominant tone"),
                ("Night", 'fill_prelight_night', (83 / 255.0,) * 3,
                 "Night prelight color (Night). Default 83,83,83 — the dominant tone")):
            row.addLayout(self._labeled(label, self._bind(key, dflt, _swatch(
                self, key, dflt, label, tip)), label_w=34), 1)
        b.addLayout(row)
        b.addWidget(self._bind('fill_prelight_selected_only', False, self._check(
            "Selected only", 'fill_prelight_selected_only', False,
            "Fill only the selected meshes (otherwise — all meshes in the scene)")))
        b.addWidget(_btn("Apply", "Fill the prelight with one flat color: Day with its color, "
                         "Night with its own. Vertex alpha is preserved",
                         lambda: run("Fill prelight", 'fill_prelight'), 'check'))
        lay.addWidget(b.box)

        # ── Paint across several ──
        b = self._box()
        b.addWidget(IconLabel("Paint across several:", 'weights'))
        b.addWidget(FusedBlock([[
            _btn("Merge", "Merge the selected meshes into a temporary model to paint the "
                 "prelight with a brush across all of them at once. The originals are kept "
                 "(hidden); 'Split' returns them as they were - with their own names and "
                 "origins. Paint the model with a VertexPaint modifier",
                 lambda: run("Merge", 'merge_paint')),
            _btn("Split", "Split: transfer the prelight painting back onto the originals (Day "
                 "and Night), return them visible with their own names/origins, and delete "
                 "the temporary model.", lambda: run("Split", 'split_paint'))]]))
        lay.addWidget(b.box)

        # ── Scatter color ──
        b = self._box()
        b.addWidget(IconLabel("Scatter color:", 'particles'))
        b.addWidget(_btn("Apply", "Scatter the chosen colour around the selected polygons "
                         "with distance falloff", lambda: run("Scatter color", 'scatter_color'),
                         'check'))
        b.addLayout(self._labeled("Factor", self._bind('scatter_color_strength', 1.0, _num(
            self, 'scatter_color_strength', 0.0, 1.0, 1.0,
            "Strength of the color contribution at the center. 0 — do nothing, 1 — fully "
            "replace center vcols with the chosen color")), label_w=56))
        b.addLayout(self._labeled("Distance", self._bind('scatter_color_distance', 0.3, _num(
            self, 'scatter_color_distance', 0.0, 1.0, 0.3,
            "Radius as a fraction of half the mesh bbox diagonal. 0 — selected vertices only, "
            "1 — spreads across half the diagonal")), label_w=56))
        b.addLayout(self._labeled("Color", self._bind('scatter_color_color', (1.0, 1.0, 1.0), _swatch(
            self, 'scatter_color_color', (1.0, 1.0, 1.0), "Color",
            "Color used to fill vertices around the selected polygons. While a VertexPaint "
            "modifier is open, its brush color (Paint Color) is used")), label_w=56))
        lay.addWidget(b.box)

        # ── Between objects ──
        b = self._box()
        b.addWidget(IconLabel("Between objects:", 'link'))
        b.addWidget(_btn("Smooth between objects", "Smooth vertex colors across seams "
                         "between selected objects",
                         lambda: run("Smooth between objects", 'smooth_between')))
        lay.addWidget(b.box)


class FoliagePanel(_Bound, BuildMixin, QtWidgets.QWidget):
    """Роллаут «Foliage / Tree» (подпанель INU «Листва / Дерево»): прилайт
    листвы — радиальный градиент кроны и цвет листвы, без света сцены."""

    _NO_MAT = "(whole mesh)"

    def __init__(self, run, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._need = IconLabel("Select a tree mesh", 'error')
        lay.addWidget(self._need)
        self._body = QtWidgets.QWidget()
        body = QtWidgets.QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(4)
        lay.addWidget(self._body)

        # общие настройки
        b = self._box()
        b.addWidget(self._bind('foliage_select_only', False, self._check(
            "Selected faces only", 'foliage_select_only', False,
            "Paint only the selected faces (Editable Mesh face selection)")))
        b.addWidget(self._bind('foliage_both_sides', True, self._check(
            "Both sides (duplicates)", 'foliage_both_sides', True,
            "GTA leaves are often duplicated (two faces at the same point). Paint both sides "
            "equally — otherwise the leaf is painted on only one side")))
        btns, self._blend_group = self._seg_buttons(
            (("Over (×)", 'MULTIPLY', "Multiply by the existing prelight — shading and tint are "
              "applied on top, the baked light is preserved"),
             ("Replace", 'REPLACE', "Fully replace the vertex colors with the result")),
            self._get('foliage_blend', 'MULTIPLY'), lambda v: self._set('foliage_blend', v),
            "How to apply the result onto the current vertex colors")
        b.addWidget(FusedBlock([btns]))
        body.addWidget(b.box)

        # Крона (затенение)
        b = self._box()
        b.addWidget(IconLabel("Crown (shading):", 'sun'))
        self._mat_shade = self._mat_combo(
            'foliage_material_name', "Paint only faces with this material (empty = the whole "
            "mesh). A trunk with a different material is not affected")
        b.addLayout(self._labeled("Material", self._mat_shade, label_w=56))
        b.addLayout(self._labeled("Shape", self._combo(
            'foliage_metric', (("Sphere", 'SPHERE', "3D distance from the crown center — for "
                                "rounded crowns"),
                               ("Cylinder", 'CYLINDER', "Horizontal distance from the trunk "
                                "axis — for elongated/columnar shapes")), 'SPHERE',
            "How to compute \"inside/outside\""), label_w=56))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(3)
        row.addWidget(self._bind('foliage_inside', 0.25, _num(
            self, 'foliage_inside', 0.0, 1.0, 0.25, "Brightness at the crown center (darker)",
            prefix="Inside ")))
        row.addWidget(self._bind('foliage_outside', 1.0, _num(
            self, 'foliage_outside', 0.0, 1.0, 1.0, "Brightness at the crown periphery (lighter)",
            prefix="Outside ")))
        b.addLayout(row)
        b.addWidget(self._bind('foliage_gamma', 1.0, _num(
            self, 'foliage_gamma', 0.1, 4.0, 1.0, "Gradient curvature: >1 expands the light "
            "zone, <1 — the dark one", prefix="Curve ")))
        b.addWidget(self._bind('foliage_height_dark', 0.0, _num(
            self, 'foliage_height_dark', 0.0, 1.0, 0.0, "Extra darkening of the lower crown "
            "(self-shadowing from above). 0 — off", prefix="Darken bottom ")))
        b.addWidget(_btn("Prelight the crown", "Foliage prelight: darker in the center of the "
                         "crown, lighter at the edges. A geometric gradient, no scene light - "
                         "for billboard tree foliage", lambda: run("Prelight the crown",
                                                                   'foliage', 'SHADE')))
        body.addWidget(b.box)

        # Цвет листвы (свет / тень)
        b = self._box()
        b.addWidget(IconLabel("Foliage color (light / shadow):", 'eyedropper'))
        self._mat_color = self._mat_combo(
            'foliage_color_material_name', "Material for the \"Foliage Color\" operation (its "
            "own independent target; empty = the whole mesh)")
        b.addLayout(self._labeled("Material", self._mat_color, label_w=56))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(3)
        row.addWidget(self._bind('foliage_light_tint', (0.55, 0.8, 0.3), _swatch(
            self, 'foliage_light_tint', (0.55, 0.8, 0.3), "Light color",
            "Tint of lit leaves (periphery/outside of the crown)")))
        row.addWidget(self._bind('foliage_shadow_tint', (0.2, 0.35, 0.12), _swatch(
            self, 'foliage_shadow_tint', (0.2, 0.35, 0.12), "Shadow color",
            "Tint of shaded leaves (crown center) — usually darker and cooler")))
        b.addLayout(row)
        b.addWidget(self._bind('foliage_tint_strength', 1.0, _num(
            self, 'foliage_tint_strength', 0.0, 1.0, 1.0, "Tint strength. 0 — color unchanged "
            "(shading only), 1 — full tint", prefix="Color strength ")))
        self._top = self._bind('foliage_top_bright', 0.0, _num(
            self, 'foliage_top_bright', 0.0, 1.0, 0.0, "Extra highlight on the crown top "
            "(simulating sun from above). 0 — off", prefix="Highlight top "))
        b.addWidget(self._top)
        self._top_h = self._bind('foliage_top_height', 1.0, _num(
            self, 'foliage_top_height', 0.0, 1.0, 1.0, "How far up the Z axis the top "
            "highlight reaches: 1 — the whole crown, 0.3 — only the top 30%. Below that — no "
            "highlight", prefix="Highlight height "))
        b.addWidget(self._top_h)
        self._top.valueChanged.connect(lambda v: self._top_h.setEnabled(v > 0.0))
        self._top_h.setEnabled(self._top.value() > 0.0)
        b.addWidget(self._bind('foliage_color_height_dark', 0.0, _num(
            self, 'foliage_color_height_dark', 0.0, 1.0, 0.0, "Extra darkening of the lower "
            "crown for the \"Color\" operation (separate from the crown setting). 0 — off",
            prefix="Darken bottom ")))
        b.addWidget(self._bind('foliage_variation', 0.0, _num(
            self, 'foliage_variation', 0.0, 1.0, 0.0, "Random brightness variation per vertex "
            "— foliage is non-uniform. 0 — off; the higher it is, the more individual leaves "
            "darken", prefix="Spread ")))
        b.addWidget(FusedBlock([[
            _btn("Bake color", "Bake the foliage color (shadow in the center → light at the "
                 "edges) into the active layer. The layer before baking is saved for 'Reset'",
                 lambda: run("Bake color", 'foliage', 'COLOR')),
            _btn("Reset", "Reset the model's prelight to the state saved at 'Bake color'.",
                 lambda: run("Reset", 'foliage_reset'), 'refresh')]]))
        body.addWidget(b.box)
        self.on_selection(None)

    def _mat_combo(self, key, tip):
        cb = QtWidgets.QComboBox()
        cb.setFixedHeight(BTN_H)
        cb.setToolTip(tip)
        cb.currentIndexChanged.connect(
            lambda i, k=key, c=cb: self._set(k, c.itemData(i) or ''))
        return cb

    def _fill_mats(self, cb, key, names):
        cur = str(self._get(key, '') or '')
        cb.blockSignals(True)
        cb.clear()
        cb.addItem(self._NO_MAT, '')
        for n in names:
            cb.addItem(n, n)
        if cur and cur not in names:
            cb.addItem("%s (not on the object)" % cur, cur)
        idx = cb.findData(cur)
        cb.setCurrentIndex(idx if idx >= 0 else 0)
        cb.blockSignals(False)

    def on_selection(self, snap):
        node = snap.get('active') if snap else None
        mesh = node is not None and _safe(lambda: _ps().is_mesh(node), False)
        self._need.setVisible(not mesh)
        self._body.setVisible(bool(mesh))
        names = [n for n, _i in (_safe(lambda: _ps().material_slots(node), []) or [])] if mesh else []
        self._fill_mats(self._mat_shade, 'foliage_material_name', names)
        self._fill_mats(self._mat_color, 'foliage_color_material_name', names)


class PostPanel(_Bound, BuildMixin, QtWidgets.QWidget):
    """Роллаут «Post-Processing» (подпанель INU): сглаживание, контраст,
    яркость, гамма, подтянуть тени — активный слой выделенных мешей."""

    def __init__(self, run, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        b = self._box()
        b.addWidget(IconLabel("Smooth:", 'curve'))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(3)
        row.addWidget(self._bind('vc_smooth_iterations', 1, _int(
            self, 'vc_smooth_iterations', 1, 50, 1, "Smooth vertex colors between neighbouring "
            "vertices.\nIterations — number of passes.\nMore passes = smoother transitions",
            prefix="Iterations ")))
        row.addWidget(self._bind('vc_smooth_factor', 0.5, _num(
            self, 'vc_smooth_factor', 0.0, 1.0, 0.5, "Smoothing strength per pass (0-1).\n0 — "
            "no effect, 1 — vertex takes the full average of neighbours", prefix="Factor ")))
        b.addLayout(row)
        b.addWidget(_btn("Smooth", "Smooth vertex colors between neighboring vertex",
                         lambda: run("Smooth", 'vc_smooth')))
        for key, lo, hi, dflt, prefix, tip, fn, op_tip in (
                ('vc_contrast', 0.0, 3.0, 1.0, "Contrast ", "Vertex color contrast.\n1.0 — "
                 "unchanged\n< 1.0 — less contrast\n> 1.0 — more contrast", 'vc_contrast',
                 "Apply contrast to vertex colors"),
                ('vc_brightness', -1.0, 1.0, 0.0, "Brightness ", "Vertex color brightness "
                 "(additive offset).\n0.0 — unchanged\n> 0 — lighter\n< 0 — darker",
                 'vc_brightness', "Apply brightness to vertex colors"),
                ('vc_gamma', 0.1, 3.0, 1.0, "Gamma ", "Vertex color gamma correction.\n1.0 — "
                 "unchanged\n< 1.0 — lighter (lift shadows)\n> 1.0 — darker (deepen shadows)",
                 'vc_gamma', "Apply gamma correction to vertex colors"),
                ('lift_shadows_strength', 0.0, 1.0, 0.5, "Pull up shadows ", "Pulls dark areas "
                 "towards the brightest point while preserving the step between faces.\n0 — "
                 "unchanged\n0.3-0.5 — recommended range\n1 — all colors reach max (the visual "
                 "step is lost)", 'lift_shadows', "Lift dark areas towards the bright ones while "
                 "preserving the step between faces")):
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(3)
            row.addWidget(self._bind(key, dflt, _num(self, key, lo, hi, dflt, tip,
                                                     prefix=prefix)), 1)
            row.addWidget(_btn("Apply", op_tip, lambda f=fn, p=prefix: run(p.strip(), f),
                               'check'))
            b.addLayout(row)
        lay.addWidget(b.box)
