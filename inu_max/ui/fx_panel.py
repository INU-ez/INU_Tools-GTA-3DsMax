# INU Tools (Max) — окно «2DFX»: панели Blender-версии INU «Эффекты»
# (N-панель) и «GTA SA: <тип>» (настройки эффекта в свойствах пустышки).
#
# Эффект — хелпер Point с user properties (adapter/fx.py). Работает: создание
# эффектов, пресеты, все поля и флаги, «Apply settings» на выделенные,
# привязка к модели / отвязка, линии связи; частица — системы effects.fxp,
# параметры эмиттера, спрайты effectsPC.txd, кривые (чтение). Заглушки —
# запись в effects.fxp (новый / удалить / сохранить / кривая). Живое превью
# эффектов и симуляция частиц исключены из порта.

from PySide6 import QtWidgets, QtCore

from .style import BTN_H, icon, SEVERITY_COLOR
from .widgets import (BuildMixin, FusedBlock, Expander, IconLabel, icon_btn,
                      NumEdit, IntEdit, VecEdit, ColorSwatch, PropsDialog,
                      FieldBinder)

_ERR = SEVERITY_COLOR['ERROR']

TITLES = {'LIGHT': "Light", 'PARTICLE': "Particle",
          'PED_ATTRACTOR': "Ped Attractor", 'SUN_GLARE': "Sun Glare",
          'ENTER_EXIT': "Enter/Exit", 'ROAD_SIGN': "Road sign",
          'ESCALATOR': "Escalator", 'RAW_2DFX': "Raw"}

# меню «Create effect» (GTATOOLS_MT_create_2dfx); None — разделитель
_CREATE = [
    ("Light", 'LIGHT', 'light',
     "Point light source / corona / neon.\nStreet lamps, car headlights, "
     "glowing building windows, neon signs. In-game it is drawn as a 2D corona "
     "with alpha blending, visible from a distance."),
    ("Particle", 'PARTICLE', 'particles',
     "Particle emitter anchor point from models/effects.fxp.\nSmoke from "
     "chimneys, water splashes at piers, sparks on power poles, fire in "
     "barrels, steam from vents."),
    ("Ped Attractor", 'PED_ATTRACTOR', 'ped',
     "Point of interest for NPCs.\nPedestrians walk up to this point and play "
     "an animation: ATM, bench, stall vendor, graffiti, a 'look around' spot."),
    ("Sun Glare", 'SUN_GLARE', 'sun',
     "Sun reflection point on a surface.\nA bright glint when the camera looks "
     "toward the sun through this point (car roofs, window glass, metal)."),
    None,
    ("Enter/Exit", 'ENTER_EXIT', 'arrows',
     "Interior enter/exit marker (type 6).\nThe entry at the object's position "
     "and the exit at the exit position; angle, radius, interior number and "
     "name, on/off time."),
    ("Road sign", 'ROAD_SIGN', 'text',
     "Text sign on a mesh (type 7).\nUp to 4 lines of text drawn by the engine "
     "over the geometry (street signs)."),
    ("Escalator", 'ESCALATOR', 'stairs',
     "Escalator (type 10).\nThree points — bottom, top and end — and a "
     "direction (up/down). The engine moves peds along this path."),
]

_PRESETS = [
    ('DEFAULT', "Default", "Default light settings"),
    ('ONALLDAY', "OnAllDay", "Always visible light"),
    ('LAMP_POST', "Lamp Post", "Standard lamp post"),
    ('LAMP_POST_COAST', "Lamp Post Coast", "Coastal lamp post (warm)"),
    ('BB_PICKUP', "BB Pickup", "Red pickup marker"),
    ('FLASHING_MAV1', "Flashing (Maverick1)", "Red blinking helicopter light"),
    ('FLASHING_MAV2', "Flashing (Maverick2)", "Green blinking helicopter light"),
    ('FLASHING_TUG', "Flashing (Tug)", "Orange blinking tug light"),
    ('TRAIN_CROSSING', "Train Crossing", "Red blinking train crossing"),
    ('TRAFFIC', "Traffic", "Traffic light"),
]

_CORONA_TEX = [
    ('coronastar', "Classic flare star — the standard corona for street lamps. "
                   "A universal choice"),
    ('coronamoon', "Soft round glow without rays (like the moon)"),
    ('coronaringb', "Glowing ring"),
    ('coronareflect', "Blurred halo/reflection — a diffuse soft glow"),
    ('coronaheadlightline', "Horizontal flare line (like from headlights)"),
    ('headlight', "Headlight corona"),
    ('headlight1', "Headlight corona, variant 2"),
    ('lockon', "Target lock marker (crosshair)"),
    ('lockonFire', "Target lock marker, ready to fire"),
    ('lunar', "Moon halo — a large soft glow"),
    ('roadsignfont', "Road sign font texture (special use)"),
    ('particleskid', "Skid mark (special use)"),
    ('finishFlag', "Finish flag (special use)"),
    ('handman', "Pointer sprite (special use)"),
    ('seabd32', "Small sea foam particle (special use)"),
    ('shad_exp', "Soft round spot (usually for a shadow, not a corona)"),
    ('shad_car', "Car silhouette (usually for a shadow)"),
    ('shad_bike', "Motorcycle silhouette (usually for a shadow)"),
    ('shad_heli', "Helicopter silhouette (usually for a shadow)"),
    ('shad_ped', "Pedestrian silhouette (usually for a shadow)"),
    ('shad_rcbaron', "RC plane silhouette (usually for a shadow)"),
    ('lamp_shad_64', "Lamp light circle (usually for a shadow)"),
    ('bloodpool_64', "Blood pool (usually as a decal)"),
    ('target256', "Large target marker"),
    ('white', "Solid white circle — a pure glow with no pattern"),
    ('cloud1', "Cloud texture (special use)"),
    ('cloudhigh', "High-altitude cloud (special use)"),
    ('cloudmasked', "Cloud with mask (special use)"),
    ('carfx1', "Vehicle effect (special use)"),
    ('wincrack_32', "Glass crack (special use)"),
    ('waterclear256', "Clear water texture (special use)"),
    ('waterwake', "Water trail (special use)"),
    ('txgrassbig0', "Grass texture (special use)"),
    ('txgrassbig1', "Grass texture, variant 2 (special use)"),
]

_SHADOW_TEX = [
    ('shad_exp', "Soft round spot — a universal \"light circle\" under a lamp. "
                 "The standard choice for lamps"),
    ('shad_car', "Car shadow silhouette"),
    ('shad_bike', "Motorcycle shadow silhouette"),
    ('shad_heli', "Helicopter shadow silhouette"),
    ('shad_ped', "Pedestrian shadow silhouette"),
    ('shad_rcbaron', "RC plane shadow silhouette"),
    ('lamp_shad_64', "Light circle under a street lamp (64×64), a bit sharper "
                     "than shad_exp"),
    ('bloodpool_64', "Blood pool (decal on the ground)"),
    ('coronastar', "Use the corona star as a light spot on the ground"),
    ('coronamoon', "Soft round glow as a spot on the ground"),
    ('coronaringb', "Ring as a spot on the ground"),
    ('coronareflect', "Blurred halo/reflection as a spot on the ground"),
    ('white', "Solid white circle — a pure light spot with no pattern"),
]

_SHOW_MODE = [
    ('0', "0 DEFAULT", "Normal mode: the lamp glows constantly (day/night — by "
                       "visibility flags). Suitable for most street lamps"),
    ('1', "1 RANDOM_FLASHING", "Random on/off flicker at random intervals — a "
                               "faulty/blinking lamp, hazard lights"),
    ('2', "2 FLASH_RAIN", "Flickers ONLY during rain, glows steadily in dry "
                          "weather"),
    ('3', "3 ONLY_RAIN", "Visible only during rain, fully off in dry weather"),
    ('4', "4 NO_RAIN", "Hides during rain, visible only in dry weather"),
    ('5', "5 FLASH_5", "Fast strobe flashing (~5 Hz) — beacons, emergency "
                       "lights, flashing lights"),
]

_FLARE = [
    ('0', "0 None", "No lens flares. The usual choice for street lamps"),
    ('1', "1 Type 1", "Lens flare — rays/halo as from a bright source when "
                      "looking at it. Style 1"),
    ('2', "2 Type 2", "Lens flare, style 2 (a different set of rays/rings)"),
    ('3', "3 Type 3", "Lens flare, style 3"),
]

# флаги света по смыслу (как _2DFX_GROUP_* INU): (поле, бит, подпись)
_FLAG_GROUPS = [
    ("Visibility:", [("2dfx_flags1", 5, "AT_DAY"), ("2dfx_flags1", 6, "AT_NIGHT"),
                     ("2dfx_flags1", 3, "Without Corona"),
                     ("2dfx_flags1", 0, "Check Obstacles")]),
    ("Corona effects:", [("2dfx_flags1", 4, "Corona Reflects")]),
    ("Blinking:", [("2dfx_flags2", 0, "Blink 1"), ("2dfx_flags2", 1, "Blink 2"),
                   ("2dfx_flags2", 2, "Blink 3"), ("2dfx_flags2", 7, "Police Light"),
                   ("2dfx_flags2", 3, "Traffic Light"),
                   ("2dfx_flags2", 4, "Train Crossing")]),
    ("Misc.:", [("2dfx_flags1", 1, "Fog Type 1"), ("2dfx_flags1", 2, "Fog Type 2"),
                ("2dfx_flags2", 5, "Update Height"),
                ("2dfx_flags2", 6, "Check Direction")]),
]

_BIT_TIPS = {
    ('2dfx_flags1', 0): "Check Obstacles — the corona hides behind obstacles "
                        "(raycast from the camera). Realistic, but more expensive",
    ('2dfx_flags1', 1): "Fog Type 1 — fog type bit 1 (combined with bit 2: "
                        "00=none, 01=type1, 10=type2, 11=type3)",
    ('2dfx_flags1', 2): "Fog Type 2 — fog type bit 2 (see Fog Type 1)",
    ('2dfx_flags1', 3): "Without Corona — turns the corona off, only the point "
                        "light stays. Useful for invisible sources",
    ('2dfx_flags1', 4): "Corona Reflects — the corona reflects off car bodies "
                        "(like headlights)",
    ('2dfx_flags1', 5): "AT_DAY — the source is visible by day (06:00–20:00)",
    ('2dfx_flags1', 6): "AT_NIGHT — the source is visible at night (20:00–06:00)",
    ('2dfx_flags2', 0): "Blink 1 — flickers with pattern 1 (short flashes)",
    ('2dfx_flags2', 1): "Blink 2 — flickers with pattern 2 (even)",
    ('2dfx_flags2', 2): "Blink 3 — flickers with pattern 3 (long flashes)",
    ('2dfx_flags2', 3): "Traffic Light — traffic light (color driven by the "
                        "game script)",
    ('2dfx_flags2', 4): "Train Crossing — blinks like a railway crossing",
    ('2dfx_flags2', 5): "Update Height — recomputes the height above ground "
                        "every frame (for moving sources)",
    ('2dfx_flags2', 6): "Check Direction — takes the camera view direction "
                        "into account (Look Vector)",
    ('2dfx_flags2', 7): "Police Light — police flasher (alternating red/blue)",
}


def _fx():
    from ..adapter import fx
    return fx


def _ops():
    from ..ops import fx
    return fx


def _sel():
    from ..adapter import selection
    return selection


def _safe(fn, default=None):
    """Запрос к сцене; вне Max (нет pymxs) или при ошибке — default."""
    try:
        return fn()
    except Exception as e:                             # noqa: BLE001
        if 'pymxs' not in str(e):
            print("[INU] 2DFX: %r" % (e,))
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


def _enum_combo(items):
    """Выпадающий список (значение, подпись[, подсказка]) узкий по ширине."""
    cb = QtWidgets.QComboBox()
    cb.setFixedHeight(BTN_H)
    cb.setSizeAdjustPolicy(
        QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
    cb.setMinimumContentsLength(6)
    for i, it in enumerate(items):
        cb.addItem(it[1] if len(it) > 2 else it[0], it[0])
        tip = it[-1] if len(it) > 1 else None
        if tip:
            cb.setItemData(i, tip, QtCore.Qt.ToolTipRole)
    return cb


def _search_combo(tip):
    """Список с поиском по подстроке (как prop_search Blender)."""
    cb = QtWidgets.QComboBox()
    cb.setEditable(True)
    cb.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
    cb.setSizeAdjustPolicy(
        QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
    cb.setMinimumContentsLength(6)
    cb.setFixedHeight(BTN_H)
    cb.setToolTip(tip)
    comp = cb.completer()
    comp.setFilterMode(QtCore.Qt.MatchContains)
    comp.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
    comp.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
    return cb


def _pair(a, b):
    hl = QtWidgets.QHBoxLayout()
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(1)
    hl.addWidget(a, 1)
    hl.addWidget(b, 1)
    return hl


# ═════════════════════ панель «Эффекты» ══════════════════════════════

class EffectsPanel(BuildMixin, QtWidgets.QWidget):
    """Панель INU «Эффекты»: линии связи, источник текстур, «Create effect»,
    «Apply settings» + привязать / отвязать, активный эффект, «Detach All»."""

    def __init__(self, dispatch, refresh, roll, parent=None):
        super().__init__(parent)
        self._dispatch, self._refresh_sel, self._roll = dispatch, refresh, roll
        self._node = None
        lay = _vbox(self)
        lay.addWidget(self._check(
            "Relationship lines", 'fx_show_links', False,
            "Show the link lines from 2DFX helpers to their model (Display "
            "Links) — uncheck to hide them.", self._on_links))

        box = self._box()
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(1)
        self._txd = IconLabel("", 'image')
        row.addWidget(self._txd, 1)
        row.addWidget(icon_btn(
            'folder', "Choose a .txd with effect textures (particle.txd etc.). "
            "If none is chosen, they are found in the game folder (Game Root).",
            self._pick_txd))
        box.addLayout(row)
        self._create = QtWidgets.QPushButton("Create effect")
        self._create.setIcon(icon('add'))
        self._create.setToolTip("Create a 2DFX effect with default properties "
                                "— at the selection (or at the scene origin)")
        menu = QtWidgets.QMenu(self._create)
        menu.setToolTipsVisible(True)
        for it in _CREATE:
            if it is None:
                menu.addSeparator()
                continue
            label, kind, ic, tip = it
            act = menu.addAction(icon(ic), label)
            act.setToolTip(tip)
            act.triggered.connect(lambda _c=False, k=kind: self._create_fx(k))
        self._create.setMenu(menu)
        self._apply = _btn(
            "Apply settings", self._apply_settings,
            "Copy the active 2DFX's settings onto all OTHER selected 2DFX "
            "helpers. Multi-editing: tweak one 2DFX (select it first), add the "
            "targets to the selection and apply — color, corona/shadow sizes, "
            "textures, flags go to all of them at once.", 'paste')
        self._attach = _btn("", self._attach_fx,
                            "Attach 2DFX to mesh model (make it a child): select "
                            "the mesh together with the 2DFX", 'link')
        self._detach = _btn("", self._detach_fx, "Detach 2DFX from parent model",
                            'unlink')
        fb = FusedBlock([[self._create], [self._apply, self._attach, self._detach]],
                        height=BTN_H + 8)
        for b in (self._attach, self._detach):
            b.setFixedWidth(BTN_H + 8)
        box.addWidget(fb)
        self._name = IconLabel("", 'light')
        self._model = IconLabel("", 'link')
        self._hint = IconLabel("", 'info', wrap=True)
        for w in (self._name, self._model, self._hint):
            box.addWidget(w)
        lay.addWidget(box.box)

        mb = self._box()
        self._att = IconLabel("", 'link')
        mb.addWidget(self._att)
        mb.addWidget(FusedBlock([[_btn(
            "Detach All", self._detach_all,
            "Detach every 2DFX / particle from the selected mesh", 'unlink')]]))
        self._att_box = mb.box
        lay.addWidget(mb.box)
        self.on_selection(None)

    def on_selection(self, snap):
        a = _fx()
        node = self._node = snap.get('node') if snap else None
        active = bool(_safe(lambda: a.is_2dfx(node), False))
        for b in (self._apply, self._attach, self._detach):
            b.setEnabled(active)
        # как draw_header INU: галочка, когда активный объект — 2DFX
        self._roll.hdr.title = "Effects ✓" if active else "Effects"
        self._roll.hdr.update()
        self._name.setVisible(active)
        self._model.setVisible(False)
        if active:
            eff = a.effect_of(node)
            self._name.setText(str(node.name))
            self._name.setIcon(a.TYPE_ICON.get(eff, 'check'))
            parent = node.parent
            if parent is not None and _safe(
                    lambda: _sel().node_kind(parent)) == 'MESH':
                self._model.setText("Model: %s" % parent.name)
                self._model.setVisible(True)
            self._hint.setText("Settings — in «GTA SA: %s» below"
                               % TITLES.get(eff, "2DFX"))
            self._hint.setIcon('info')
        else:
            self._hint.setText("Select a 2DFX helper to edit")
            self._hint.setIcon('select')
        n = 0
        if not active and node is not None and \
                _safe(lambda: _sel().node_kind(node)) == 'MESH':
            n = len(_safe(lambda: a.attached(node), []) or [])
        self._att_box.setVisible(n > 0)
        self._att.setText("Attached 2DFX: %d" % n)
        self._update_txd()

    def _update_txd(self):
        _p, _i, label = _ops().fx_txd(self._get('fx_txd_path', ''),
                                      self._get('game_root', ''))
        self._txd.setText(label or "Not selected")

    # — действия —
    def _pick_txd(self):
        from .file_dialog import INUFileDialog
        dlg = INUFileDialog(self, "INU: Pick FX TXD", mode='open',
                            filters=[("GTA TXD (*.txd)", ["*.txd"]),
                                     ("All Files (*.*)", ["*"])],
                            key='fx_txd', accept_label="Open")
        if dlg.exec() and dlg.selected_files():
            self._set('fx_txd_path', dlg.selected_files()[0])
            self._update_txd()

    def _report(self, res):
        if res is None:
            return
        msg, err = res
        if err:
            QtWidgets.QMessageBox.warning(self, "INU Tools", msg)
        else:
            print("[INU] %s" % msg)
        self._refresh_sel()

    def _create_fx(self, kind):
        node = _safe(lambda: _fx().create_effect(kind))
        if node is not None:
            print("[INU] 2DFX %s created: %s" % (kind, node.name))
        self._refresh_sel()

    def _apply_settings(self):
        self._report(_safe(lambda: _fx().copy_to_selected()))

    def _attach_fx(self):
        self._report(_safe(lambda: _fx().attach_selected()))

    def _detach_fx(self):
        self._report(_safe(lambda: _fx().detach(self._node)))

    def _detach_all(self):
        self._report(_safe(lambda: _fx().detach_all(self._node)))

    def _on_links(self):
        on = bool(self._get('fx_show_links', False))
        n = _safe(lambda: _fx().show_links(on), 0)
        print("[INU] 2DFX links %s: %s helper(s)" % ("on" if on else "off", n))


# ═════════════════════ панель «GTA SA: <тип>» ════════════════════════

class FxSettings(BuildMixin, QtWidgets.QWidget):
    """Настройки активного 2DFX — страница на каждый тип эффекта (как
    GTATOOLS_PT_2dfx_settings INU). roll — роллаут: заголовок «GTA SA:
    <тип>», скрыт, пока не выделен 2DFX."""

    def __init__(self, dispatch, roll, parent=None):
        super().__init__(parent)
        self._dispatch, self._roll = dispatch, roll
        self._node = None
        self._bind = FieldBinder(lambda node, k, v: _fx().put([node], k, v))
        self._flag_btns = []
        self._sprites = None          # спрайты effectsPC.txd (лениво)
        self._curve = ''
        self._keys = []               # буфер ключей кривой [[t, v]]
        self._key_i = 0
        lay = _vbox(self)
        self._pages = {}
        for eff, build in (('LIGHT', self._page_light),
                           ('PARTICLE', self._page_particle),
                           ('PED_ATTRACTOR', self._page_attractor),
                           ('SUN_GLARE', self._page_sun),
                           ('ENTER_EXIT', self._page_enex),
                           ('ROAD_SIGN', self._page_sign),
                           ('ESCALATOR', self._page_escalator),
                           ('RAW_2DFX', self._page_raw)):
            w = QtWidgets.QWidget()
            build(_vbox(w))
            w.hide()
            lay.addWidget(w)
            self._pages[eff] = w
        self.on_selection(None)

    def _game_root(self):
        return self._get('game_root', '')

    # — выделение —
    def on_selection(self, snap):
        a = _fx()
        node = snap.get('node') if snap else None
        active = bool(_safe(lambda: a.is_2dfx(node), False))
        self._roll.setVisible(active)
        if not active:
            self._node = self._bind.node = None
            return
        self._node = node
        eff = a.effect_of(node)
        self._roll.hdr.title = "GTA SA: " + TITLES.get(eff, "2DFX")
        self._roll.hdr.update()
        for k, w in self._pages.items():
            w.setVisible(k == eff)
        self.reload()

    def reload(self):
        """Перечитать поля активного 2DFX в контролы."""
        a, node = _fx(), self._node
        if node is None:
            return
        vals = _safe(lambda: a.fields(node), {}) or {}
        eff = a.effect_of(node)
        if eff == 'LIGHT':
            look = _safe(lambda: a.get(node, '2dfx_look_direction', ''), '')
            self._look.setVisible(bool(look))
            vals['2dfx_look_direction'] = a.get(node, '2dfx_look_direction',
                                                (0.0, 0.0, 0.0))
        self._bind.load(node, vals)
        if eff == 'LIGHT':
            self._load_flags(vals)
        elif eff == 'PARTICLE':
            self._load_particle(vals)
        elif eff == 'ROAD_SIGN':
            self._sign_lines()
        elif eff == 'RAW_2DFX':
            self._raw.setText("type %s, %s B" % (vals.get('2dfx_raw_effect_id', '?'),
                                                 vals.get('2dfx_raw_size', 0)))

    # — общие части —
    def _section(self, lay, key, title):
        """Сворачиваемый раздел (как _section INU) → layout бокса."""
        ex = Expander(self, key, False, title)
        bx = self._box()
        ex.body.addWidget(bx.box)
        lay.addWidget(ex)
        return bx

    # ── LIGHT ──────────────────────────────────────────────────────────
    def _page_light(self, v):
        b = self._bind
        pb = self._box()
        pb.addWidget(IconLabel("Presets:", 'action'))
        preset = b.add('preset_2dfx', 'DEFAULT', _enum_combo(_PRESETS))
        preset.setToolTip("2DFX Preset")
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(1)
        row.addWidget(preset, 1)
        row.addWidget(FusedBlock([[_btn("Apply", self._apply_preset,
                                        "Apply 2DFX preset to active object",
                                        'check')]]))
        pb.addLayout(row)
        v.addWidget(pb.box)

        s = self._section(v, 'fx_show_props', "Light properties")
        s.addLayout(self._labeled("Color", b.add(
            'color_2dfx', (1.0, 1.0, 0.784, 1.0),
            ColorSwatch(title="2DFX Color", tip="Corona and light color")), 40))
        s.addWidget(b.add('corona_size_2dfx', 1.0, NumEdit(
            3, 0.0, 1000.0, 0.1, "Corona Size: ",
            "Corona size — the glowing sprite that always faces the camera (the "
            "visible \"glow\" of the lamp). 0 — the corona is invisible. This is "
            "the visible light itself")))
        s.addWidget(b.add('2dfx_corona_far_clip', 100.0, NumEdit(
            1, 0.0, 100000.0, 10.0, "Draw Distance: ",
            "Corona draw distance (meters). Beyond this distance from the camera "
            "the corona is no longer drawn. Larger — visible from afar")))
        s.addWidget(b.add('2dfx_pointlight_range', 18.0, NumEdit(
            1, 0.0, 100000.0, 1.0, "Light Range: ",
            "Radius of the lamp's fill light (meters) — how far the lamp lights "
            "up its surroundings in game. 0 — does not light geometry")))
        s.addWidget(QtWidgets.QLabel("Corona Name:"))
        cb = b.add('corona_tex_2dfx', 'coronastar', _enum_combo(_CORONA_TEX))
        cb.setToolTip("Corona Texture")
        s.addWidget(cb)

        s = self._section(v, 'fx_show_behavior', "Behaviour")
        s.addWidget(QtWidgets.QLabel("Show Mode:"))
        s.addWidget(b.add('show_mode_2dfx', '0', _enum_combo(_SHOW_MODE)))
        s.addWidget(QtWidgets.QLabel("Flare Type:"))
        s.addWidget(b.add('flare_type_2dfx', '0', _enum_combo(_FLARE)))
        cb = QtWidgets.QCheckBox("Corona Reflection")
        cb.setToolTip("1 — the corona reflects on wet asphalt/water; 0 — no "
                      "reflection")
        s.addWidget(b.add('2dfx_corona_enable_reflection', 0, cb))

        s = self._section(v, 'fx_show_shadow', "Shadow")
        s.addWidget(b.add('shadow_size_2dfx', 8.0, NumEdit(
            3, 0.0, 1000.0, 0.5, "Spot size: ",
            "Size of the light spot (shadow) on the ground under the lamp and "
            "the brightness of the surrounding fill light. TO KEEP ONLY THE "
            "CORONA without a spot and fill — set 0")))
        s.addWidget(b.add('2dfx_shadow_z_distance', 0, IntEdit(
            0, 255, "Distance: ",
            "How many meters down the light spot (shadow) is projected from the "
            "lamp. 0 — the spot is right at the lamp's level")))
        s.addWidget(b.add('2dfx_shadow_color_multiplier', 40, IntEdit(
            0, 255, "Multiplier: ",
            "Brightness/saturation of the light spot on the ground (0–255). "
            "Higher — a brighter, more contrasting spot")))
        s.addWidget(QtWidgets.QLabel("Shadow Name:"))
        cb = b.add('shadow_tex_2dfx', 'shad_exp', _enum_combo(_SHADOW_TEX))
        cb.setToolTip("Shadow Texture")
        s.addWidget(cb)
        s.addWidget(IconLabel("Size = 0 → only corona, no spot", 'info', wrap=True))

        s = self._section(v, 'fx_show_flags', "Flags")
        for header, group in _FLAG_GROUPS:
            s.addWidget(IconLabel(header, 'light'))
            btns = [self._flag_btn(*it) for it in group]
            rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
            fb = FusedBlock(rows, pad=3)
            if len(btns) == 1:        # одна кнопка — на половину ширины
                hl = QtWidgets.QHBoxLayout()
                hl.setContentsMargins(0, 0, 0, 0)
                hl.addWidget(fb, 1)
                hl.addStretch(1)
                s.addLayout(hl)
            else:
                s.addWidget(fb)

        lb = self._box()
        lb.addWidget(IconLabel("Look Direction:", 'arrows'))
        lb.addWidget(b.add('2dfx_look_direction', (0.0, 0.0, 0.0), VecEdit(3, 3)))
        self._look = lb.box
        v.addWidget(lb.box)

    def _flag_btn(self, prop, bit, label):
        btn = QtWidgets.QPushButton(label)
        btn.setCheckable(True)
        btn.setToolTip(_BIT_TIPS.get((prop, bit), "Toggle 2DFX flag bit"))
        btn.toggled.connect(lambda on, p=prop, i=bit: self._set_bit(p, i, on))
        self._flag_btns.append((prop, bit, btn))
        return btn

    def _set_bit(self, prop, bit, on):
        node = self._node
        if node is None:
            return
        a = _fx()
        cur = int(_safe(lambda: a.get(node, prop, 0), 0) or 0)
        new = (cur | (1 << bit)) if on else (cur & ~(1 << bit))
        _safe(lambda: a.put([node], prop, new & 0xFF))

    def _load_flags(self, vals):
        for prop, bit, btn in self._flag_btns:
            btn.blockSignals(True)
            btn.setChecked(bool(int(vals.get(prop, 0) or 0) & (1 << bit)))
            btn.blockSignals(False)

    def _apply_preset(self):
        node = self._node
        if node is None:
            return
        key = self._bind_value('preset_2dfx') or 'DEFAULT'
        msg = _safe(lambda: _fx().apply_preset(node, key))
        if msg:
            print("[INU] %s" % msg)
        self.reload()

    def _bind_value(self, key):
        return _safe(lambda: _fx().get(self._node, key, ''), '')

    # ── PARTICLE ───────────────────────────────────────────────────────
    def _page_particle(self, v):
        b = self._bind
        box = self._box()
        box.addWidget(IconLabel("Particle Properties:", 'particles'))
        self._effect = _search_combo("Effect name from effects.fxp")
        self._effect.activated.connect(
            lambda _i: self._pick_effect(self._effect.currentText().strip()))
        self._effect.lineEdit().returnPressed.connect(
            lambda: self._pick_effect(self._effect.currentText().strip()))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(1)
        row.addLayout(self._labeled("Effect", self._effect, 36), 1)
        self._b_new = icon_btn('add', "Create a new empty effect in effects.fxp",
                               self._new_effect)
        self._b_del = icon_btn('remove', "Delete the current effect from "
                               "effects.fxp (with auto-backup)", self._del_effect)
        row.addWidget(FusedBlock([[self._b_new, self._b_del, icon_btn(
            'refresh', "Reload effects.fxp from disk (flush cache)",
            self._reload_fxp)]]))
        box.addLayout(row)
        # эмиттеры (у систем с несколькими)
        self._em = QtWidgets.QWidget()
        el = _vbox(self._em)
        er = QtWidgets.QHBoxLayout()
        er.setSpacing(1)
        er.addWidget(icon_btn('tri_left', "Switch the editable emitter in a "
                              "multi-emitter system", lambda: self._emitter(-1)))
        self._em_lb = QtWidgets.QLabel()
        self._em_lb.setAlignment(QtCore.Qt.AlignCenter)
        er.addWidget(self._em_lb, 1)
        er.addWidget(icon_btn('tri_right', "Switch the editable emitter in a "
                              "multi-emitter system", lambda: self._emitter(1)))
        el.addLayout(er)
        el.addWidget(IconLabel("Switching will reset edits — save first", 'info',
                               wrap=True))
        box.addWidget(self._em)
        v.addWidget(box.box)

        s = self._section(v, 'fx_pfx_texture', "Sprite & blending")
        self._tex = b.add('particle_texture', '', _search_combo(
            "Sprite name from effectsPC.txd"))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(1)
        row.addLayout(self._labeled("Texture", self._tex, 44), 1)
        row.addWidget(icon_btn('refresh', "Reload the sprite list from "
                               "effectsPC.txd", self._reload_sprites))
        s.addLayout(row)
        s.addLayout(_pair(
            b.add('particle_src_blend', 4, IntEdit(
                0, 17, "SRC: ", "D3D9 source blend factor (4=SRCALPHA, 2=ONE, ...)")),
            b.add('particle_dst_blend', 5, IntEdit(
                0, 17, "DST: ", "D3D9 dest blend factor (5=INVSRCALPHA, 2=ONE "
                "for additive)"))))

        s = self._section(v, 'fx_pfx_color', "Color (start → end)")
        s.addLayout(self._labeled("Start", b.add(
            'particle_color_start', (1.0, 1.0, 1.0, 1.0),
            ColorSwatch(title="Color (start)")), 40))
        mid = QtWidgets.QPushButton("Middle")
        mid.setCheckable(True)
        mid.setToolTip("Add intermediate key for smooth fade-in/fade-out")
        s.addWidget(FusedBlock([[b.add('particle_color_mid_enabled', False, mid,
                                       self._mid_visible)]]))
        self._mid = QtWidgets.QWidget()
        ml = _vbox(self._mid)
        ml.addLayout(self._labeled("Middle", b.add(
            'particle_color_mid', (1.0, 1.0, 1.0, 1.0),
            ColorSwatch(title="Color (mid)")), 40))
        ml.addWidget(b.add('particle_color_mid_time', 0.5, NumEdit(
            3, 0.01, 0.99, 0.05, "Mid time: ",
            "Intermediate key position over lifetime (0..1)")))
        s.addWidget(self._mid)
        s.addLayout(self._labeled("End", b.add(
            'particle_color_end', (1.0, 1.0, 1.0, 0.0),
            ColorSwatch(title="Color (end)")), 40))
        self._mid_btn = mid

        s = self._section(v, 'fx_pfx_size', "Size")
        s.addLayout(_pair(
            b.add('particle_size_start', 0.3, NumEdit(
                3, 0.0, 1000.0, 0.05, "Start: ", "Particle size at start of life")),
            b.add('particle_size_end', 0.5, NumEdit(
                3, 0.0, 1000.0, 0.05, "End: ", "Particle size at end of life"))))

        s = self._section(v, 'fx_pfx_emission', "Emission")
        for key, dflt, dec, step, label, tip in (
                ('particle_life', 1.0, 3, 0.1, "Life: ", "Particle lifetime in seconds"),
                ('particle_life_bias', 0.0, 3, 0.1, "Life bias: ",
                 "EMLIFE BIAS — random lifetime scatter"),
                ('particle_rate', 10.0, 2, 1.0, "Rate: ", "Particles per second"),
                ('particle_speed', 1.0, 3, 0.1, "Speed: ", "Particle initial speed"),
                ('particle_speed_bias', 0.0, 3, 0.1, "Speed bias: ",
                 "EMSPEED BIAS — random initial-speed scatter")):
            s.addWidget(b.add(key, dflt, NumEdit(dec, 0.0, 100000.0, step, label, tip)))
        s.addLayout(self._labeled("Direction", b.add(
            'particle_direction', (0.0, 0.0, 1.0),
            VecEdit(3, 3, tip="Emission direction")), 50))
        s.addLayout(_pair(
            b.add('particle_angle_min', 0.0, NumEdit(
                2, 0.0, 360.0, 1.0, "Angle min: ",
                "EMANGLE MIN — minimum emission cone angle")),
            b.add('particle_angle_max', 0.0, NumEdit(
                2, 0.0, 360.0, 1.0, "Angle max: ",
                "EMANGLE MAX — maximum emission cone angle"))))
        s.addLayout(self._labeled("Box", b.add(
            'particle_volume', (0.0, 0.0, 0.0),
            VecEdit(3, 3, 0.0, 1e6, tip="EMSIZE — half-extent of the emission "
                    "box (centered)")), 50))
        s.addLayout(self._labeled("Offset", b.add(
            'particle_offset', (0.0, 0.0, 0.0),
            VecEdit(3, 3, tip="EMPOS X/Y/Z — spawn point offset")), 50))
        s.addLayout(_pair(
            b.add('particle_rotation_min', 0.0, NumEdit(
                1, -3600.0, 3600.0, 5.0, "Rot min: ",
                "EMROTATION ANGLEMIN — min initial sprite rotation")),
            b.add('particle_rotation_max', 0.0, NumEdit(
                1, -3600.0, 3600.0, 5.0, "Rot max: ",
                "EMROTATION ANGLEMAX — max initial sprite rotation"))))

        s = self._section(v, 'fx_pfx_physics', "Physics")
        s.addLayout(self._labeled("Force", b.add(
            'particle_force', (0.0, 0.0, 0.0),
            VecEdit(3, 3, tip="FORCE X/Y/Z — constant acceleration (e.g. -9.8 "
                    "on Z = gravity)")), 50))
        # знаков после запятой меньше, чем у INU: поля в паре узкие
        for (k1, l1, t1, d1), (k2, l2, t2, d2), dec in (
                (('particle_friction', "Friction: ", "FRICTION — air resistance", 0.0),
                 ('particle_wind', "Wind: ", "WIND WINDFACTOR — game wind "
                  "responsiveness", 0.0), 3),
                (('particle_noise', "Noise: ", "NOISE — smoothed random motion", 0.0),
                 ('particle_jitter', "Jitter: ", "JITTER JITTERFACTOR — sharp "
                  "random jitter", 0.0), 3),
                (('particle_rotspeed_min', "RotSpd min: ", "ROTSPEED MINCW — min "
                  "sprite rotation speed", 0.0),
                 ('particle_rotspeed_max', "RotSpd max: ", "ROTSPEED MAXCW — max "
                  "sprite rotation speed", 0.0), 1),
                (('particle_ground_bounce', "Bounce: ", "GROUNDCOLLIDE BOUNCE — "
                  "bounce factor on ground hit", 0.0),
                 ('particle_ground_speedmult', "SpeedMult: ", "GROUNDCOLLIDE "
                  "SPEEDMULT — speed loss on impact", 1.0), 2)):
            s.addLayout(_pair(
                b.add(k1, d1, NumEdit(dec, -100000.0, 100000.0, 0.1, l1, t1)),
                b.add(k2, d2, NumEdit(dec, -100000.0, 100000.0, 0.1, l2, t2))))

        s = self._section(v, 'fx_pfx_system', "System")
        s.addWidget(b.add('particle_sys_length', 1.0, NumEdit(
            3, 0.0, 100000.0, 0.1, "Length: ",
            "LENGTH — system cycle duration in seconds")))
        s.addWidget(b.add('particle_sys_playmode', 2, IntEdit(
            0, 3, "Play mode: ", "PLAYMODE — play mode (0-3)")))
        s.addWidget(b.add('particle_sys_culldist', 50.0, NumEdit(
            1, 0.0, 100000.0, 5.0, "Cull dist: ",
            "CULLDIST — effect cull distance in game")))

        s = self._section(v, 'fx_pfx_curves', "Curves (keyframes)")
        self._b_curve = QtWidgets.QPushButton("Select curve...")
        self._b_curve.setIcon(icon('select'))
        self._b_curve.setToolTip("Pick a curve to edit")
        self._curve_menu = QtWidgets.QMenu(self._b_curve)
        self._curve_menu.aboutToShow.connect(self._fill_curves)
        self._b_curve.setMenu(self._curve_menu)
        s.addWidget(FusedBlock([[self._b_curve]]))
        self._keys_w = QtWidgets.QWidget()
        kl = _vbox(self._keys_w, 1)
        hdr = QtWidgets.QHBoxLayout()
        hdr.setSpacing(1)
        self._keys_lb = QtWidgets.QLabel()
        hdr.addWidget(self._keys_lb, 1)
        hdr.addWidget(FusedBlock([[
            icon_btn('add', "Append a keyframe to the end of the curve",
                     self._key_add),
            icon_btn('remove', "Delete the active keyframe", self._key_remove)]]))
        kl.addLayout(hdr)
        self._keys_rows = QtWidgets.QVBoxLayout()
        self._keys_rows.setSpacing(1)
        kl.addLayout(self._keys_rows)
        kl.addWidget(FusedBlock([[_btn(
            "Write curve to effects.fxp",
            lambda: self._not_yet("Write curve to effects.fxp"),
            "Write the keyframe buffer back to effects.fxp for the selected curve",
            'export')]], height=BTN_H + 4))
        s.addWidget(self._keys_w)

        v.addWidget(FusedBlock([[_btn(
            "Save to effects.fxp", self._save_effect,
            "Save effect edits back to effects.fxp (with auto-backup)",
            'export')]], height=BTN_H + 6))

    def _load_particle(self, vals):
        names, err = _ops().systems(self._game_root())
        self._effect.blockSignals(True)
        self._effect.clear()
        self._effect.addItems(names)
        cur = str(vals.get('2dfx_effect_name', '') or '')
        self._effect.setEditText(cur or err)
        self._effect.blockSignals(False)
        self._b_del.setEnabled(bool(cur))
        n = _ops().emitter_count(self._game_root(), cur) if cur else 0
        idx = int(vals.get('particle_emitter_index', 0) or 0)
        self._em.setVisible(n > 1)
        self._em_lb.setText("Emitter %d / %d" % (idx + 1, n))
        if self._sprites is None:
            self._reload_sprites(keep=True)
        self._tex.blockSignals(True)
        self._tex.clear()
        self._tex.addItems(self._sprites or [])
        self._tex.setEditText(str(vals.get('particle_texture', '') or ''))
        self._tex.blockSignals(False)
        self._mid_visible()
        self._show_keys()

    def _mid_visible(self):
        self._mid.setVisible(self._mid_btn.isChecked())

    def _reload_sprites(self, keep=False):
        self._sprites = _safe(lambda: _ops().sprite_names(
            self._get('fx_txd_path', ''), self._game_root()), []) or []
        if not keep and self._node is not None:
            self.reload()

    def _write_params(self, name, index):
        """Параметры эмиттера из effects.fxp → поля объекта (как populate
        INU при выборе эффекта / эмиттера)."""
        node = self._node
        vals = _safe(lambda: _ops().particle_params(self._game_root(), name, index))
        a = _fx()
        _safe(lambda: a.put([node], '2dfx_effect_name', name))
        _safe(lambda: a.put([node], 'particle_emitter_index', index))
        if vals:
            for k, val in vals.items():
                _safe(lambda k=k, val=val: a.put([node], k, val))
        self._curve, self._keys = '', []
        self.reload()

    def _pick_effect(self, name):
        if self._node is None or not name or name.startswith('<'):
            return
        names, _err = _ops().systems(self._game_root())
        if name not in names:
            QtWidgets.QMessageBox.warning(self, "INU Tools",
                                          "Effect '%s' not found in effects.fxp" % name)
            return
        self._write_params(name, 0)

    def _emitter(self, step):
        node = self._node
        name = str(_safe(lambda: _fx().get(node, '2dfx_effect_name', ''), '') or '')
        n = _ops().emitter_count(self._game_root(), name) if name else 0
        if n <= 1:
            return
        cur = int(_safe(lambda: _fx().get(node, 'particle_emitter_index', 0), 0) or 0)
        self._write_params(name, (cur + step) % n)

    def _reload_fxp(self):
        _safe(lambda: _ops().reload())
        self.reload()
        print("[INU] effects.fxp cache cleared")

    # — кривые (чтение effects.fxp; запись — позже) —
    def _fill_curves(self):
        self._curve_menu.clear()
        node = self._node
        name = str(_safe(lambda: _fx().get(node, '2dfx_effect_name', ''), '') or '')
        idx = int(_safe(lambda: _fx().get(node, 'particle_emitter_index', 0), 0) or 0)
        items = _safe(lambda: _ops().curves(self._game_root(), name, idx), []) or []
        if not items:
            self._curve_menu.addAction("<no curves>").setEnabled(False)
        for c in items:
            self._curve_menu.addAction(c, lambda c=c: self._pick_curve(c))

    def _pick_curve(self, curve):
        node = self._node
        name = str(_safe(lambda: _fx().get(node, '2dfx_effect_name', ''), '') or '')
        idx = int(_safe(lambda: _fx().get(node, 'particle_emitter_index', 0), 0) or 0)
        self._curve = curve
        self._keys = [list(k) for k in (_safe(lambda: _ops().curve_keys(
            self._game_root(), name, idx, curve), []) or [])]
        self._key_i = 0
        self._show_keys()

    def _show_keys(self):
        self._b_curve.setText(self._curve or "Select curve...")
        self._keys_w.setVisible(bool(self._curve))
        while self._keys_rows.count():
            it = self._keys_rows.takeAt(0)
            if it.widget() is not None:
                it.widget().deleteLater()
        self._keys_lb.setText("Keys (%d):" % len(self._keys))
        if not self._keys:
            self._keys_rows.addWidget(IconLabel("No keys", 'info'))
        for i, (t, val) in enumerate(self._keys):
            w = QtWidgets.QWidget()
            hl = QtWidgets.QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(1)
            rb = QtWidgets.QRadioButton()
            rb.setChecked(i == self._key_i)
            rb.setToolTip("Select the active keyframe for removal")
            rb.toggled.connect(lambda on, i=i: on and setattr(self, '_key_i', i))
            hl.addWidget(rb)
            te = NumEdit(4, 0.0, 1.0, 0.05, "t ")
            te.setValue(t)
            te.valueChanged.connect(lambda x, i=i: self._keys[i].__setitem__(0, x))
            ve = NumEdit(4, -1e6, 1e6, 0.1, "v ")
            ve.setValue(val)
            ve.valueChanged.connect(lambda x, i=i: self._keys[i].__setitem__(1, x))
            hl.addWidget(te, 1)
            hl.addWidget(ve, 1)
            self._keys_rows.addWidget(w)

    def _key_add(self):
        if self._keys:
            t, val = self._keys[-1]
            self._keys.append([min(t + 0.1, 1.0), val])
        else:
            self._keys.append([0.0, 0.0])
        self._key_i = len(self._keys) - 1
        self._show_keys()

    def _key_remove(self):
        if self._keys:
            del self._keys[min(self._key_i, len(self._keys) - 1)]
            self._key_i = max(0, min(self._key_i, len(self._keys) - 1))
            self._show_keys()

    # — effects.fxp: новый / удалить / сохранить (диалоги; запись — позже) —
    def _not_yet(self, what):
        QtWidgets.QMessageBox.information(
            self, "INU Tools", "%s is not implemented yet." % what)

    def _new_effect(self):
        dlg = _NameDialog(self, "INU: New Particle Effect", 340, 'fx_new_name',
                          "prt_custom", "New effect name (must be unique)")
        dlg.form.addWidget(IconLabel(
            "An empty system with one emitter will be created", 'info', wrap=True))
        dlg.form.addWidget(QtWidgets.QLabel(
            "Texture: sphere. Life 1s, rate 10/s, color white"))
        if not dlg.exec():
            return
        name = str(self._get('fx_new_name', '') or '').strip()
        names, err = _ops().systems(self._game_root())
        if err and not names:
            msg = "Game Root is not set" if 'Root' in err else err.strip('<>')
        elif not name:
            msg = "Name is empty"
        elif name in names:
            msg = "Effect '%s' already exists" % name
        else:
            return self._not_yet("Writing effects.fxp")
        QtWidgets.QMessageBox.warning(self, "INU Tools", msg)

    def _del_effect(self):
        node = self._node
        name = str(_safe(lambda: _fx().get(node, '2dfx_effect_name', ''), '') or '')
        if not name:
            return
        dlg = PropsDialog(self, "INU: Delete Particle Effect", 380)
        dlg.form.addWidget(IconLabel("Delete '%s' from effects.fxp?" % name,
                                     'error', icon_color=_ERR))
        dlg.form.addWidget(IconLabel("Action is irreversible (though .bak is "
                                     "available)", 'info', wrap=True))
        users = _safe(lambda: _fx().effect_users(name), 0) or 0
        if users > 1:
            dlg.form.addWidget(IconLabel(
                "⚠ %d objects in the scene use this effect" % users, 'error',
                icon_color=_ERR))
        confirm = QtWidgets.QCheckBox("I understand this will overwrite effects.fxp")
        dlg.form.addWidget(confirm)
        if not dlg.exec():
            return
        if not confirm.isChecked():
            QtWidgets.QMessageBox.warning(self, "INU Tools",
                                          "Confirmation not given")
            return
        self._not_yet("Writing effects.fxp")

    def _save_effect(self):
        node = self._node
        cur = str(_safe(lambda: _fx().get(node, '2dfx_effect_name', ''), '') or '')
        self._set('fx_save_name', cur)
        dlg = _NameDialog(self, "INU: Save Particle Effect", 360, 'fx_save_name',
                          "", "System name in effects.fxp (new name clones from "
                          "current)", label="Effect Name")
        dlg.form.addWidget(dlg._check(
            "Overwrite existing", 'fx_save_overwrite', True,
            "Overwrite existing system with this name"))
        dlg.form.addWidget(IconLabel("effects.fxp.bak is created on the first "
                                     "save", 'info', wrap=True))
        if dlg.exec():
            self._not_yet("Writing effects.fxp")

    # ── PED_ATTRACTOR ──────────────────────────────────────────────────
    def _page_attractor(self, v):
        b = self._bind
        box = self._box()
        box.addWidget(IconLabel("Ped Attractor:", 'ped'))
        box.addWidget(b.add('2dfx_attractor_type', 0, IntEdit(
            0, 255, "Attractor Type: ", "Behaviour type (SCRIPTED / SEAT / STOP "
            "/ TRIGGER_SCRIPT / LOOK_AT / SCRIPTED_2 / PARK / STEP)")))
        box.addWidget(QtWidgets.QLabel("Rotation Matrix"))
        box.addWidget(b.add('2dfx_rotation_matrix',
                            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
                            VecEdit(9, 3, -1e6, 1e6, 0.1, cols=3,
                                    labels=('X', 'Y', 'Z'))))
        ed = QtWidgets.QLineEdit()
        ed.setMaxLength(8)
        ed.setFixedHeight(BTN_H)
        box.addLayout(self._labeled("External Script", b.add(
            '2dfx_external_script', '', ed), 80))
        box.addWidget(b.add('2dfx_ped_probability', 0, IntEdit(
            0, 100, "Ped Probability: ")))
        v.addWidget(box.box)

    # ── SUN_GLARE ──────────────────────────────────────────────────────
    def _page_sun(self, v):
        box = self._box()
        box.addWidget(IconLabel("Sun Glare", 'sun'))
        box.addWidget(QtWidgets.QLabel("Position only (no extra data)"))
        v.addWidget(box.box)

    # ── ENTER_EXIT ─────────────────────────────────────────────────────
    def _page_enex(self, v):
        b = self._bind
        box = self._box()
        box.addWidget(IconLabel("Enter/Exit (interior):", 'arrows'))
        box.addWidget(b.add('ee_interior', 0, IntEdit(
            0, 65535, "Interior #: ", "Interior world number (0 = normal world)")))
        ed = QtWidgets.QLineEdit()
        ed.setMaxLength(8)
        ed.setFixedHeight(BTN_H)
        box.addLayout(self._labeled("Interior name", b.add(
            'ee_interior_name', '', ed), 76))
        box.addWidget(b.add('ee_enter_angle', 0.0, NumEdit(
            1, -3600.0, 3600.0, 5.0, "Entry angle: ",
            "Direction the player faces on entry (degrees)")))
        box.addWidget(b.add('ee_exit_angle', 0.0, NumEdit(
            1, -3600.0, 3600.0, 5.0, "Exit angle: ",
            "Player facing when exiting the interior (degrees)")))
        box.addLayout(self._labeled("Exit position", b.add(
            'ee_exit_loc', (0.0, 0.0, 0.0), VecEdit(
                3, 3, tip="Where it teleports the player (interior "
                          "coordinates)")), 76))
        box.addLayout(_pair(
            b.add('ee_radius_x', 1.5, NumEdit(2, 0.0, 1000.0, 0.1, "Radius X: ")),
            b.add('ee_radius_y', 1.5, NumEdit(2, 0.0, 1000.0, 0.1, "Radius Y: "))))
        box.addLayout(_pair(
            b.add('ee_time_on', 0, IntEdit(0, 24, "On: ", "Time on")),
            b.add('ee_time_off', 24, IntEdit(0, 24, "Off: ", "Time off"))))
        box.addWidget(b.add('ee_sky_color', 0, IntEdit(0, 255, "Sky color: ")))
        v.addWidget(box.box)

    # ── ROAD_SIGN ──────────────────────────────────────────────────────
    def _page_sign(self, v):
        b = self._bind
        box = self._box()
        box.addWidget(IconLabel("Road sign (text):", 'text'))
        self._sign_rows = []
        for i in range(4):
            ed = QtWidgets.QLineEdit()
            ed.setMaxLength(16)
            ed.setFixedHeight(BTN_H)
            w = QtWidgets.QWidget()
            w.setLayout(self._labeled("Line %d" % (i + 1), b.add(
                'sign_text%d' % i, '', ed), 40))
            box.addWidget(w)
            self._sign_rows.append(w)
        self._sign_n = b.add('sign_lines', 1, IntEdit(
            1, 4, "Lines: ", "How many text lines are used"), self._sign_lines)
        box.addWidget(self._sign_n)
        box.addLayout(self._labeled("Chars/line", b.add(
            'sign_maxchars', '16', _enum_combo(
                [('16', "16"), ('2', "2"), ('4', "4"), ('8', "8")])), 64))
        box.addLayout(self._labeled("Color", b.add(
            'sign_color', 'WHITE', _enum_combo(
                [('WHITE', "White"), ('BLACK', "Black"), ('GREY', "Gray"),
                 ('RED', "Red")])), 64))
        box.addLayout(self._labeled("Size", b.add(
            'sign_size', (2.0, 1.0), VecEdit(
                2, 3, 0.0, 1e6, labels=('Width', 'Height'),
                tip="Width and height of the text area on the mesh")), 64))
        box.addLayout(self._labeled("Rotation", b.add(
            'sign_rotation', (90.0, 0.0, 0.0), VecEdit(
                3, 1, -3600.0, 3600.0, 5.0,
                tip="Sign plane orientation (degrees)")), 64))
        v.addWidget(box.box)

    def _sign_lines(self):
        n = max(1, min(4, self._sign_n.value()))
        for i, w in enumerate(self._sign_rows):
            w.setVisible(i < n)

    # ── ESCALATOR ──────────────────────────────────────────────────────
    def _page_escalator(self, v):
        b = self._bind
        box = self._box()
        box.addWidget(IconLabel("Escalator:", 'stairs'))
        for key, label, dflt, tip in (
                ('esc_bottom', "Bottom", (0.0, 0.0, 0.0),
                 "Escalator bottom point (model space)"),
                ('esc_top', "Top", (0.0, 2.0, 3.0), "Escalator top point"),
                ('esc_end', "End", (0.0, 3.0, 3.0),
                 "Vanishing point (Z as the top when going up, as the bottom "
                 "when going down)")):
            box.addLayout(self._labeled(label, b.add(key, dflt, VecEdit(
                3, 3, tip=tip)), 44))
        seg, group = self._seg_buttons([("Up", '1', "Goes up"),
                                        ("Down", '0', "Goes down")], '1',
                                       lambda _d: None)
        b.add('esc_direction', '1', group)
        self._esc_group = group
        box.addWidget(FusedBlock([seg]))
        v.addWidget(box.box)

    # ── RAW_2DFX ───────────────────────────────────────────────────────
    def _page_raw(self, v):
        box = self._box()
        box.addWidget(IconLabel("Saved effect", 'lock'))
        self._raw = QtWidgets.QLabel()
        box.addWidget(self._raw)
        box.addWidget(IconLabel("Byte-exact round-trip, not editable", 'info',
                                wrap=True))
        v.addWidget(box.box)


class _NameDialog(BuildMixin, PropsDialog):
    """Диалог с одним полем имени (settings[key])."""

    def __init__(self, parent, title, width, key, placeholder, tip,
                 label="Name"):
        super().__init__(parent, title, width)
        self.form.addLayout(self._labeled(label, self._line(
            key, placeholder, tip), 80))
