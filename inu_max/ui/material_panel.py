# INU Tools (Max) — окно «GTA Material»: панель Blender-версии INU «GTA
# Material» (вкладки Effects / Collision Material / Alpha) для материала
# выделенного объекта; у Multi/Sub-Object — выбор подматериала («слота»).
#
# Всё работает на свойствах материала (adapter/material.py, AppData): RW-
# затенение, цвет/прозрачность (diffuse / opacity Standard), текстура
# (имя, фильтрация, адресация, маска), копирование на выделенные, пресеты
# машины, слот цвета («волшебный» RGB), SA Vehicle defaults, paintjob + их
# проверка, GTA-эффекты, UV-анимация (свойства), поверхность COL с пикером
# (поиск, избранное, категории), альфа-материалы (поиск, режимы, выделение).

import os

from PySide6 import QtWidgets, QtCore, QtGui

from .style import BTN_H, icon, SEVERITY_COLOR
from .widgets import (BuildMixin, FusedBlock, Expander, IconLabel, icon_btn,
                      NumEdit, IntEdit, ColorSwatch, PropsDialog, FieldBinder,
                      scrolled)
from .. import data_surfaces as surf

_ERR = SEVERITY_COLOR['ERROR']

_FILTER = [('0', "None"), ('1', "Nearest"), ('2', "Linear"), ('3', "Mip Nearest"),
           ('4', "Mip Linear"), ('5', "Linear Mip Nearest"),
           ('6', "Linear Mip Linear")]
_ADDR = [('0', "None"), ('1', "Wrap"), ('2', "Mirror"), ('3', "Clamp"),
         ('4', "Border")]
_BLEND = [('1', "Zero"), ('2', "One"), ('3', "Src Color"), ('4', "Inv Src Color"),
          ('5', "Src Alpha"), ('6', "Inv Src Alpha"), ('7', "Dest Alpha"),
          ('8', "Inv Dest Alpha"), ('9', "Dest Color"), ('10', "Inv Dest Color"),
          ('11', "Src Alpha Sat")]
_SLOTS = [
    ('NONE', "None", "Plain material, unrelated to carcols"),
    ('PRIMARY', "Primary", "Primary color (first in carcols.dat)"),
    ('SECONDARY', "Secondary", "Secondary color"),
    ('THIRD', "Third color", "Third color (some vehicles)"),
    ('FOURTH', "Fourth color", "Fourth color"),
    ('HL_LEFT', "Left Headlight", "Left headlight"),
    ('HL_RIGHT', "Right Headlight", "Right headlight"),
    ('TL_LEFT', "Left Taillight", "Left tail light"),
    ('TL_RIGHT', "Right Taillight", "Right tail light"),
]
_ALPHA_MODES = [('OPAQUE', "Opaque"), ('CLIP', "Alpha Clip"),
                ('HASHED', "Alpha Hashed"), ('BLEND', "Alpha Blend")]
_IMAGES = [("Images (*.png *.tga *.bmp *.dds *.jpg)",
            ["*.png", "*.tga", "*.bmp", "*.dds", "*.jpg"]), ("All Files (*.*)", ["*"])]
_ALPHA_ROWS_MAX = 200


def _mat():
    from ..adapter import material
    return material


def _safe(fn, default=None):
    """Запрос к сцене; вне Max (нет pymxs) или при ошибке — default."""
    try:
        return fn()
    except Exception as e:                             # noqa: BLE001
        if 'pymxs' not in str(e):
            print("[INU] material: %r" % (e,))
        return default


def _btn(label, slot, tip, icon_name=None):
    b = QtWidgets.QPushButton(label)
    b.setToolTip(tip)
    if icon_name:
        b.setIcon(icon(icon_name))
    b.clicked.connect(lambda _c=False: slot())
    return b


def _vbox(w, spacing=3):
    lay = QtWidgets.QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    return lay


def _combo(items, tip=None):
    cb = QtWidgets.QComboBox()
    cb.setFixedHeight(BTN_H)
    cb.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
    cb.setMinimumContentsLength(5)
    for i, it in enumerate(items):
        cb.addItem(it[1], it[0])
        if len(it) > 2 and it[2]:
            cb.setItemData(i, it[2], QtCore.Qt.ToolTipRole)
    if tip:
        cb.setToolTip(tip)
    return cb


def _line(tip=None, placeholder=''):
    ed = QtWidgets.QLineEdit()
    ed.setFixedHeight(BTN_H)
    ed.setPlaceholderText(placeholder)
    if tip:
        ed.setToolTip(tip)
    return ed


def _pair(a, b):
    hl = QtWidgets.QHBoxLayout()
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(1)
    hl.addWidget(a, 1)
    hl.addWidget(b, 1)
    return hl


class MaterialTools(BuildMixin, QtWidgets.QWidget):
    """Панель INU «GTA Material»."""

    def __init__(self, dispatch, refresh, parent=None):
        super().__init__(parent)
        self._dispatch, self._refresh_sel = dispatch, refresh
        self._node = None
        self._mat = None
        self._slots = []
        self._alpha = []              # найденные альфа-материалы
        self._bind = FieldBinder(lambda m, k, v: _mat().set_prop(m, k, v))
        lay = _vbox(self)

        # материал выделенного объекта / подматериал Multi/Sub («слот»)
        self._slot_cb = QtWidgets.QComboBox()
        self._slot_cb.setFixedHeight(BTN_H)
        self._slot_cb.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self._slot_cb.setMinimumContentsLength(6)
        self._slot_cb.setToolTip("Material of the selected object (a sub-material "
                                 "of a Multi/Sub-Object — like Blender's slots)")
        self._slot_cb.currentIndexChanged.connect(self._on_slot)
        self._slot_row = QtWidgets.QWidget()
        self._slot_row.setLayout(self._labeled("Material", self._slot_cb, 48))
        lay.addWidget(self._slot_row)
        self._none = IconLabel("Select an object with a material", 'info', wrap=True)
        lay.addWidget(self._none)

        tabs, self._tab_group = self._seg_buttons(
            [("Effects", 'EFFECTS', "Material RW effects: env map, bump, specular, "
              "reflection, dual texture, UV anim + presets"),
             ("Collision Material", 'SURFACE', "COL Surface Type — physical "
              "surface type and Day/Night Light"),
             ("Alpha", 'ALPHA', "Bulk-change the blend mode of the scene's alpha "
              "materials")],
            self._get('mat_tab', 'EFFECTS'), self._on_tab)
        self._tabs = FusedBlock([tabs], pad=3)
        lay.addWidget(self._tabs)
        self._pages = {}
        for key, build in (('EFFECTS', self._page_effects),
                           ('SURFACE', self._page_surface),
                           ('ALPHA', self._page_alpha)):
            w = QtWidgets.QWidget()
            build(_vbox(w))
            lay.addWidget(w)
            self._pages[key] = w
        self._apply_tab()
        self.on_selection(None)

    # ════════════════════ вкладка Effects ═════════════════════════════
    def _page_effects(self, v):
        b = self._bind
        v.addWidget(IconLabel("RW shading:", 'light'))
        for key, label, tip in (
                ('ambient', "Ambient: ", "Ambient Shading"),
                ('surf_specular', "Specular: ", "Surface Specular"),
                ('surf_diffuse', "Diffuse: ", "Surface Diffuse — 0.5 instead of 1.0 "
                 "renders the model at half brightness")):
            v.addWidget(b.add(key, 1.0, NumEdit(3, 0.0, 10.0, 0.05, label, tip)))

        v.addWidget(IconLabel("Color / transparency:", 'image'))
        self._swatch = ColorSwatch(title="Material color",
                                   tip="Material color and transparency (diffuse "
                                       "+ opacity of the Standard material)")
        self._swatch.changed.connect(self._on_color)
        v.addLayout(self._labeled("Color (RGBA)", self._swatch, 72))

        tb = self._box()
        tb.addWidget(IconLabel("Texture:", 'image'))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)
        self._preview = QtWidgets.QLabel()
        self._preview.setFixedSize(48, 48)
        self._preview.setAlignment(QtCore.Qt.AlignCenter)
        self._preview.setStyleSheet("background:#3a3a3a; border:1px solid #383838;")
        row.addWidget(self._preview)
        self._tex_file = QtWidgets.QLabel()
        self._tex_file.setWordWrap(True)
        self._tex_file.setStyleSheet("color:#b8b8b8;")
        row.addWidget(self._tex_file, 1)
        tb.addLayout(row)
        tb.addLayout(self._labeled("Name", b.add(
            'texture_name', '', _line("Texture name in the DFF (authoritative for "
                                      "export)")), 48))
        tb.addLayout(self._labeled("Filtering", b.add(
            'tex_filter', '2', _combo(_FILTER, "Texture filtering")), 48))
        tb.addLayout(_pair(b.add('tex_addr_u', '1', _combo(_ADDR, "Address U")),
                           b.add('tex_addr_v', '1', _combo(_ADDR, "Address V"))))
        tb.addLayout(self._labeled("Mask", b.add(
            'mask_texture', '', _line("Mask Texture")), 48))
        v.addWidget(tb.box)
        v.addWidget(FusedBlock([[_btn(
            "Copy to selected", self._copy,
            "Copy the active material's GTA settings onto the materials of all "
            "selected objects (effects, texture filter, RW shading, color).",
            'paste')]]))

        # «Машина»: пресеты, слот цвета, Paintjob
        ex = Expander(self, 'mat_show_vehicle', False, "Vehicle")
        ex.set_tip("Collapse/expand the vehicle block (color slot + Paintjob)")
        ex.body.addWidget(IconLabel("Quick presets:", 'action'))
        ex.body.addWidget(FusedBlock([[
            _btn("Glass", lambda: self._preset('VEHICLE_GLASS'),
                 "Transparent glass with env map"),
            _btn("Chrome", lambda: self._preset('CHROME'),
                 "Strong environment reflection + specular (bumpers/trim)"),
            _btn("Paint", lambda: self._preset('VEHICLE'),
                 "xvehicleenv128 + vehiclespecdot64 + reflection blend"),
            _btn("Reset", lambda: self._preset('GENERIC'),
                 "Plain textured material, no effects")]], pad=2))
        sb = self._box()
        sb.addWidget(IconLabel("Vehicle color slot:", 'paste'))
        self._slot_color = _combo(_SLOTS, "Vehicle color slot: the SA engine "
                                  "substitutes the color from carcols.dat. "
                                  "Replaces the material's base RGB with the "
                                  "magic marker.")
        self._slot_color.currentIndexChanged.connect(self._on_color_slot)
        sb.addWidget(self._slot_color)
        self._sa_defaults = _btn(
            "Apply SA Vehicle defaults", self._sa_vehicle,
            "Apply standard SA vehicle body settings: env map = xvehicleenv128, "
            "specular = vehiclespecdot64, blend = 0.05, + Vehicle pipeline. "
            "Equivalent to Kam's GTA_Material 'SA Vehicle default' button.",
            'light')
        self._sa_fb = FusedBlock([[self._sa_defaults]])
        sb.addWidget(self._sa_fb)
        ex.body.addWidget(sb.box)
        pb = self._box()
        prow = QtWidgets.QHBoxLayout()
        prow.setSpacing(1)
        prow.addWidget(IconLabel("Paintjob (Pay'n'Spray):", 'image'), 1)
        self._pj_check = icon_btn(
            'check', "Validate all materials with Paintjob slots: both slots "
            "must be filled, and the material must have a main texture — "
            "otherwise the game won't pick up the paintjob in Pay'n'Spray.",
            self._validate_paintjobs)
        prow.addWidget(self._pj_check)
        pb.addLayout(prow)
        self._pj = {}
        for key, label, tip in (
                ('paintjob_alt_1', "Paint 1", "Alternate texture for Pay'n'Spray "
                 "paintjob 1.\nPacked into TXD as <base>_paintjob1, where <base> "
                 "is the name of this material's main texture."),
                ('paintjob_alt_2', "Paint 2", "Alternate texture for Pay'n'Spray "
                 "paintjob 2.\nPacked into TXD as <base>_paintjob2.")):
            pb.addLayout(self._labeled(label, self._pj_field(key, tip), 48))
        self._pj_warn = IconLabel("Both alternatives (1 and 2) are required",
                                  'error', wrap=True, icon_color=_ERR)
        pb.addWidget(self._pj_warn)
        ex.body.addWidget(pb.box)
        v.addWidget(ex)

        # «GTA-эффекты»
        ex = Expander(self, 'mat_show_fx', False, "GTA effects")
        ex.set_tip("Collapse/expand GTA effects (env map, bump, reflection, "
                   "specular, dual, UV anim)")
        self._fx_details = {}

        def effect(key, label, tip, build):
            bx = self._box(margins=(4, 3, 4, 3))
            cb = QtWidgets.QCheckBox(label)
            cb.setToolTip(tip)
            bx.addWidget(b.add(key, False, cb, self._show_details))
            det = QtWidgets.QWidget()
            build(_vbox(det, 2))
            bx.addWidget(det)
            self._fx_details[key] = (cb, det)
            ex.body.addWidget(bx.box)

        def env(d):
            d.addLayout(self._labeled("Texture", b.add('env_map_tex', '', _line()), 56))
            d.addWidget(b.add('env_map_coef', 0.5, NumEdit(3, 0.0, 10.0, 0.05,
                                                           "Coefficient: ")))
            d.addWidget(b.add('env_map_fb_alpha', False,
                              QtWidgets.QCheckBox("Use FB Alpha")))

        def bump(d):
            d.addLayout(self._labeled("Height Map", b.add(
                'bump_map_tex', '', _line("Height Map Texture")), 64))

        def refl(d):
            d.addLayout(_pair(
                b.add('reflection_scale_x', 0.0, NumEdit(3, -1e3, 1e3, 0.1, "Scale X: ")),
                b.add('reflection_scale_y', 0.0, NumEdit(3, -1e3, 1e3, 0.1, "Y: "))))
            d.addLayout(_pair(
                b.add('reflection_offset_x', 0.0, NumEdit(3, -1e3, 1e3, 0.1, "Offset X: ")),
                b.add('reflection_offset_y', 0.0, NumEdit(3, -1e3, 1e3, 0.1, "Y: "))))
            d.addWidget(b.add('reflection_intensity', 0.0, NumEdit(
                3, 0.0, 100.0, 0.05, "Intensity: ")))

        def spec(d):
            d.addWidget(b.add('specular_level', 0.0, NumEdit(
                3, 0.0, 100.0, 0.1, "Specular Level: ")))
            d.addLayout(self._labeled("Texture", b.add('specular_texture', '',
                                                       _line()), 56))

        def dual(d):
            d.addLayout(self._labeled("Src", b.add(
                'dual_tex_src_blend', '5', _combo(_BLEND, "Src Blend")), 30))
            d.addLayout(self._labeled("Dst", b.add(
                'dual_tex_dst_blend', '6', _combo(_BLEND, "Dst Blend")), 30))
            d.addLayout(self._labeled("Texture", b.add(
                'dual_tex_texture', '', _line("Dual Texture")), 56))

        def uv(d):
            d.addLayout(self._labeled("Name", b.add(
                'animation_name', '', _line("Animation name")), 40))
            seg, group = self._seg_buttons(
                [("Scroll", 'SCROLL', "Constant linear scrolling by Speed U/V"),
                 ("Keyframes", 'KEYFRAME', "Custom animation: keys on the "
                  "diffuse map coordinates (not implemented in 3ds Max yet — "
                  "ignored: SA export writes Scroll with Speed U/V, III/VC "
                  "none)")],
                'SCROLL', lambda _d: None, "UV animation mode")
            b.add('uv_anim_mode', 'SCROLL', group, self._show_details)
            self._uv_group = group
            d.addWidget(FusedBlock([seg]))
            self._uv_scroll = QtWidgets.QWidget()
            sl = _vbox(self._uv_scroll, 2)
            sl.addLayout(_pair(
                b.add('uv_anim_speed_u', 0.0, NumEdit(
                    4, -1e3, 1e3, 0.01, "Speed U: ", "UV scroll speed along U "
                    "per second")),
                b.add('uv_anim_speed_v', 0.0, NumEdit(
                    4, -1e3, 1e3, 0.01, "Speed V: ", "UV scroll speed along V "
                    "per second"))))
            sl.addWidget(b.add('uv_anim_duration', 1.0, NumEdit(
                3, 0.01, 1e4, 0.1, "Duration: ", "Duration of the UV animation "
                "cycle (s)")))
            d.addWidget(self._uv_scroll)
            # режим ключей в Max ещё не сделан: экспорт SA пишет Scroll
            self._uv_keys = IconLabel(
                "Keys are not implemented in 3ds Max yet — ignored: SA export "
                "writes Scroll with the Speed U/V / Duration set in Scroll mode "
                "(III/VC write no UV animation)",
                'error', wrap=True, icon_color=_ERR)
            d.addWidget(self._uv_keys)

        effect('export_env_map', "Environment Map",
               "Environment reflection map (env map)", env)
        effect('export_bump_map', "Bump Map", "Bump map", bump)
        effect('export_reflection', "Reflection Material", "Material reflection",
               refl)
        effect('export_specular', "Specular Material", "Specular material", spec)
        effect('export_dual_tex', "Blend Mode (Src/Dst)",
               "Dual Texture / Blend Mode", dual)
        effect('uv_anim_write', "UV Animation",
               "Embed UV animation into the exported DFF", uv)
        v.addWidget(ex)

    def _pj_field(self, key, tip):
        """Путь к картинке paintjob (в INU — слот картинки) + «…»."""
        w = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(1)
        ed = self._bind.add(key, '', _line(tip), self._pj_state)
        hl.addWidget(ed, 1)

        def browse():
            from .file_dialog import INUFileDialog
            dlg = INUFileDialog(self, "INU: Paintjob texture", mode='open',
                                filters=_IMAGES, key='paintjob', accept_label="Open")
            if dlg.exec() and dlg.selected_files():
                ed.setText(dlg.selected_files()[0])
                ed.editingFinished.emit()
        hl.addWidget(icon_btn('folder', "Browse…", browse))
        self._pj[key] = ed
        return w

    # ════════════════════ вкладка Collision Material ══════════════════
    def _page_surface(self, v):
        b = self._bind
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(1)
        self._sid = b.add('col_mat_index', 0, IntEdit(
            0, 178, "ID: ", "COL surface type ID (0-178)"), self._show_surface)
        row.addWidget(self._sid, 1)
        row.addWidget(icon_btn(
            'select', "Choose the surface type for a COL material (search, "
            "favorites, categories).", self._pick_surface))
        v.addLayout(row)
        self._sname = IconLabel("", 'mesh')
        v.addWidget(self._sname)
        v.addLayout(_pair(
            b.add('col_day_light', 0, IntEdit(0, 15, "Day Light: ")),
            b.add('col_night_light', 0, IntEdit(0, 15, "Night Light: "))))
        v.addWidget(b.add('col_brightness', 0, IntEdit(
            0, 255, "Brightness: ", "Brightness for Sphere/Cone")))

    def _show_surface(self):
        self._sname.setText(surf.surface_name(self._sid.value()))

    def _pick_surface(self):
        if self._mat is None:
            return
        dlg = SurfacePicker(self, self._mat)
        if dlg.exec():
            self._load()

    # ════════════════════ вкладка Alpha ═══════════════════════════════
    def _page_alpha(self, v):
        scope, self._scope_group = self._seg_buttons(
            [("Whole scene", 'SCENE', "Collect across the whole scene"),
             ("Selected only", 'SELECTED', "Only materials of selected objects")],
            self._get('alpha_scope', 'SCENE'),
            lambda d: self._set('alpha_scope', d), "Scope")
        v.addWidget(FusedBlock([scope], pad=3))
        v.addLayout(self._labeled("Mode", self._combo(
            'alpha_filter_mode',
            [("By alpha node", 'NODE', "The material has an opacity map: the "
              "texture alpha drives the opacity"),
             ("Has alpha channel", 'CHANNEL', "The texture has a significant "
              "alpha channel"),
             ("Already transparent", 'TRANSPARENT', "Opacity below 100 or an "
              "opacity map is on"),
             ("All", 'ALL', "Any of the criteria above")], 'NODE'), 40))
        v.addWidget(FusedBlock([[_btn(
            "Refresh", self._scan, "Collect the scene's (or selection's) alpha "
            "materials into a list by the chosen filter mode.", 'refresh')]]))
        self._found = QtWidgets.QLabel("Found: 0")
        v.addWidget(self._found)
        lb = self._box(margins=(3, 3, 3, 3))
        lb.setSpacing(1)
        self._alpha_rows = lb
        v.addWidget(lb.box)
        bb = self._box()
        bb.addLayout(self._labeled("Mode for all", self._combo(
            'alpha_bulk_blend', [(t, k, None) for k, t in _ALPHA_MODES], 'CLIP'), 72))
        bb.addWidget(FusedBlock([[_btn(
            "Apply to all", self._apply_all,
            "Apply the chosen transparency mode to every material in the list.",
            'check')]]))
        v.addWidget(bb.box)
        v.addWidget(FusedBlock([[_btn(
            "Select objects", self._select_users,
            "Select objects that use the materials from the list.", 'select')]]))

    def _fill_alpha(self):
        lay = self._alpha_rows
        while lay.count():
            old = lay.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        self._found.setText("Found: %d" % len(self._alpha))
        self._alpha_rows.box.setVisible(bool(self._alpha))
        m = _mat()
        for mat in self._alpha[:_ALPHA_ROWS_MAX]:
            w = QtWidgets.QWidget()
            hl = QtWidgets.QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(2)
            hl.addWidget(IconLabel(str(mat.name), 'image'), 1)
            cb = _combo([(k, t) for k, t in _ALPHA_MODES])
            cur = _safe(lambda mat=mat: m.props(mat).get('alpha_blend', 'OPAQUE'),
                        'OPAQUE')
            cb.setCurrentIndex(max(0, cb.findData(cur)))
            cb.currentIndexChanged.connect(
                lambda i, c=cb, mat=mat: _safe(lambda: m.set_blend(mat, c.itemData(i))))
            hl.addWidget(cb)
            lay.addWidget(w)
        if len(self._alpha) > _ALPHA_ROWS_MAX:
            lay.addWidget(IconLabel("… %d more" % (len(self._alpha) - _ALPHA_ROWS_MAX),
                                    'info'))

    def _scan(self):
        self._alpha = _safe(lambda: _mat().scan_alpha(
            self._get('alpha_scope', 'SCENE'),
            self._get('alpha_filter_mode', 'NODE')), []) or []
        print("[INU] Alpha materials found: %d" % len(self._alpha))
        self._fill_alpha()

    def _apply_all(self):
        if not self._alpha:
            return QtWidgets.QMessageBox.warning(
                self, "INU Tools", "No alpha materials — press “Refresh”")
        mode = self._get('alpha_bulk_blend', 'CLIP')
        for mat in self._alpha:
            _safe(lambda mat=mat: _mat().set_blend(mat, mode))
        print("[INU] Blend mode changed on %d material(s)" % len(self._alpha))
        self._fill_alpha()

    def _select_users(self):
        if not self._alpha:
            return QtWidgets.QMessageBox.warning(
                self, "INU Tools", "No alpha materials — press “Refresh”")
        n = _safe(lambda: _mat().select_users(self._alpha), 0)
        print("[INU] Objects selected: %s" % n)
        self._refresh_sel()

    # ════════════════════ выделение и материал ════════════════════════
    def _on_tab(self, tab):
        self._set('mat_tab', tab)
        self._apply_tab()

    def _apply_tab(self):
        tab = self._get('mat_tab', 'EFFECTS')
        for k, w in self._pages.items():
            w.setVisible(k == tab and (self._mat is not None or k == 'ALPHA'))

    def on_selection(self, snap):
        node = snap.get('node') if snap else None
        slots = _safe(lambda: _mat().slots(node), []) or [] if node is not None else []
        same = node is not None and node == self._node and \
            [s[0] for s in slots] == [s[0] for s in self._slots]
        self._node, self._slots = node, slots
        if not same:
            self._slot_cb.blockSignals(True)
            self._slot_cb.clear()
            self._slot_cb.addItems([s[0] for s in slots])
            self._slot_cb.blockSignals(False)
        self._slot_row.setVisible(bool(slots))
        self._none.setVisible(not slots)
        self._on_slot(self._slot_cb.currentIndex())

    def _on_slot(self, i):
        self._mat = self._slots[i][1] if 0 <= i < len(self._slots) else None
        self._apply_tab()
        self._load()

    def _load(self):
        mat = self._mat
        if mat is None:
            self._bind.node = None
            return
        m = _mat()
        vals = _safe(lambda: m.props(mat), {}) or {}
        self._bind.load(mat, vals)
        rgba = _safe(lambda: m.color(mat))
        self._swatch.setEnabled(rgba is not None)
        if rgba is not None:
            self._swatch.set_rgba(rgba)
        self._slot_color.blockSignals(True)
        self._slot_color.setCurrentIndex(max(0, self._slot_color.findData(
            vals.get('vehicle_color_slot', 'NONE'))))
        self._slot_color.blockSignals(False)
        self._sa_fb.setVisible(vals.get('vehicle_color_slot', 'NONE') != 'NONE')
        f = _safe(lambda: m.texture_file(mat), '') or ''
        self._tex_file.setText(os.path.basename(f) if f else "No diffuse texture")
        pm = QtGui.QPixmap(f) if f and os.path.isfile(f) else QtGui.QPixmap()
        self._preview.setPixmap(pm.scaled(46, 46, QtCore.Qt.KeepAspectRatio,
                                          QtCore.Qt.SmoothTransformation)
                                if not pm.isNull() else QtGui.QPixmap())
        self._show_details()
        self._show_surface()
        self._pj_state()

    def _show_details(self):
        for cb, det in self._fx_details.values():
            det.setVisible(cb.isChecked())
        keyframe = any(b.isChecked() and b.property("seg_data") == 'KEYFRAME'
                       for b in self._uv_group.buttons())
        self._uv_scroll.setVisible(not keyframe)
        self._uv_keys.setVisible(keyframe)

    def _pj_state(self):
        a, b = (self._pj[k].text().strip() for k in ('paintjob_alt_1', 'paintjob_alt_2'))
        self._pj_check.setVisible(bool(a or b))
        self._pj_warn.setVisible(bool(a or b) and not (a and b))

    # — действия —
    def _on_color(self, rgba):
        if self._mat is not None:
            _safe(lambda: _mat().set_color(self._mat, rgba))

    def _copy(self):
        if self._mat is None:
            return
        n = _safe(lambda: _mat().copy_to_selected(self._mat), 0)
        print("[INU] copied to %s material(s)" % n)

    def _preset(self, preset):
        if self._mat is None:
            return
        print("[INU] %s" % _safe(lambda: _mat().apply_preset(self._mat, preset), ''))
        self._load()

    def _on_color_slot(self, i):
        if self._mat is None:
            return
        _safe(lambda: _mat().set_color_slot(self._mat, self._slot_color.itemData(i)))
        self._load()

    def _sa_vehicle(self):
        if self._mat is None:
            return
        print("[INU] %s" % _safe(lambda: _mat().sa_vehicle_defaults(self._mat), ''))
        self._set('export_pipeline', '0x53F2009A')     # Vehicle pipeline
        self._load()

    def _validate_paintjobs(self):
        ok, problems = _safe(lambda: _mat().paintjob_report(), (0, [])) or (0, [])
        if not ok and not problems:
            return QtWidgets.QMessageBox.information(
                self, "INU: Validate Paintjobs", "No paintjobs in the scene")
        if problems:
            for p in problems:
                print("[INU] paintjob: %s" % p)
            QtWidgets.QMessageBox.warning(
                self, "INU: Validate Paintjobs",
                "Paintjob problems: %d, OK: %d\n\n%s"
                % (len(problems), ok, "\n".join(problems[:12])))
        else:
            QtWidgets.QMessageBox.information(
                self, "INU: Validate Paintjobs", "All paintjob materials OK: %d" % ok)


class SurfacePicker(BuildMixin, PropsDialog):
    """Выбор типа поверхности COL (col_surface_menu INU): «ко всем
    выделенным COL», поиск, избранное (★), категории по 2 колонки."""

    def __init__(self, parent, mat):
        super().__init__(parent, "INU: Surface Type", 380)
        self._mat_ref = mat
        self.ok.hide()                  # выбор — кликом по поверхности
        self.buttons.update_corners()
        f = self.form
        f.addWidget(self._check(
            "To all selected COL", 'surf_all_selected', False,
            "Assign the surface to the materials of ALL selected COL objects, not "
            "only the current one"))
        self._search = QtWidgets.QLineEdit()
        self._search.setFixedHeight(BTN_H)
        self._search.setPlaceholderText("Search…")
        self._search.setToolTip("Filter surface types")
        self._search.textChanged.connect(lambda _t: self._rebuild())
        f.addWidget(self._search)
        self._host = QtWidgets.QWidget()
        self._host.setObjectName("scrollHost")
        self._lay = _vbox(self._host)
        lay, self._view, _strip = scrolled(self._host)
        box = QtWidgets.QWidget()
        box.setLayout(lay)
        box.setMinimumHeight(360)
        f.addWidget(box, 1)
        self._rebuild()

    def _rebuild(self):
        while self._lay.count():
            it = self._lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        favs = _safe(lambda: _mat().favorites(), set()) or set()
        text = self._search.text().strip().lower()
        if text:
            ids = [sid for sid, name in surf.SURFACES
                   if text in name.lower() or text in str(sid)]
            if ids:
                self._lay.addWidget(self._grid(ids, favs))
            else:
                self._lay.addWidget(IconLabel("Nothing found", 'info'))
        else:
            if favs:
                b = self._box()
                b.addWidget(IconLabel("Favorites", 'check'))
                b.addWidget(self._grid(sorted(favs), favs))
                self._lay.addWidget(b.box)
            for cat, ids in surf.CATEGORIES:
                ex = Expander(self, 'surf_cat_' + cat.lower(), False,
                              "%s (%d)" % (cat, len(ids)))
                ex.body.addWidget(self._grid(ids, favs))
                self._lay.addWidget(ex)
        self._lay.addStretch(1)

    def _grid(self, ids, favs):
        w = QtWidgets.QWidget()
        g = QtWidgets.QGridLayout(w)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(1)
        for i, sid in enumerate(ids):
            star = QtWidgets.QPushButton("★" if sid in favs else "☆")
            star.setFixedSize(BTN_H, BTN_H)
            star.setToolTip("Add/remove a material from favorites (star). "
                            "Favorites show first and persist between sessions.")
            star.clicked.connect(lambda _c=False, s=sid: self._fav(s))
            pick = QtWidgets.QPushButton("%d: %s" % (sid, surf.surface_name(sid)))
            pick.setFixedHeight(BTN_H)
            pick.setStyleSheet("text-align:left; padding:0 4px;")
            pick.clicked.connect(lambda _c=False, s=sid: self._choose(s))
            g.addWidget(star, i // 2, (i % 2) * 2)
            g.addWidget(pick, i // 2, (i % 2) * 2 + 1)
        return w

    def _fav(self, sid):
        _safe(lambda: _mat().toggle_favorite(sid))
        self._rebuild()

    def _choose(self, sid):
        n = _safe(lambda: _mat().set_surface(
            self._mat_ref, sid, bool(self._get('surf_all_selected', False))), 0)
        print("[INU] Surface ID %d (%s) → %s material(s)"
              % (sid, surf.surface_name(sid), n))
        self.accept()
