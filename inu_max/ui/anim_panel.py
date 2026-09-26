# INU Tools (Max) — окно «IFP IO»: панель Blender-версии INU «Анимации»
# (вкладки «Персонажи» / «Объекты»). Подпанель «Иерархия фреймов» — общий
# FrameHierarchy из vehicle_panel в режиме 'PED'.
#
# Работает: импорт IFP в библиотеку анимаций сцены (счётчик и список),
# проверка round-trip, статус Handsign, состояние rig'а анимированного
# объекта (подсказки, структура, настройки pivot'а в user properties),
# «To pivot» / «To root». Остальное — окна с опциями INU и заглушки: логика
# сцены (ключи, IK, камера, веса) — следующий этап.

from PySide6 import QtWidgets, QtCore, QtGui

from .style import C, BTN_H, icon, SEVERITY_COLOR
from .widgets import (BuildMixin, FusedBlock, Expander, IconLabel, icon_btn)
from . import anim_options as ao

_ERR = SEVERITY_COLOR['ERROR']


def _anim():
    from ..adapter import anim
    return anim


def _sel():
    from ..adapter import selection
    return selection


def _safe(fn, default=None):
    """Запрос к сцене; вне Max (нет pymxs) или при ошибке — default."""
    try:
        return fn()
    except Exception as e:                             # noqa: BLE001
        if 'pymxs' not in str(e):
            print("[INU] animations: %r" % (e,))
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


# «Куда добавить» меш в rig (пипетка сцены и бокс «Add mesh to rig»)
_PICK_TARGETS = [
    ("New pivot", 'NEW_PIVOT',
     "Create a new pivot and attach the mesh to it — it will rotate separately"),
    ("To existing pivot", 'PIVOT',
     "To the first pivot — shared animation with the other meshes under it"),
    ("To root (static)", 'ROOT', "Static part, does not rotate"),
]
_PICK_TIP = ("Where to attach the eyedropper-picked mesh:\n"
             "  New pivot — animated part (own axis/speed)\n"
             "  To existing pivot — same pivot as the previous one\n"
             "  To root — static part without animation")


class AnimTools(BuildMixin, QtWidgets.QWidget):
    """Панель INU «Анимации»: слитный верх (вкладки + первый ряд действий)
    и тело вкладки Characters или Objects."""

    def __init__(self, dispatch, export_skin_cb, parent=None):
        super().__init__(parent)
        self._dispatch = dispatch
        self._export_skin_cb = export_skin_cb
        self._node = None
        self._pivot = None
        self._rig_root = None       # root rig'а над pivot'ом (бокс Add mesh)
        self._names = None          # анимации в списке Animation
        lay = _vbox(self)

        # верх — один слитный блок, как top = column(align=True) в INU
        tabs, self._tab_group = self._seg_buttons(
            [("Characters", 'CHAR', "IFP import/export, IK Rig"),
             ("Objects", 'OBJ', "Animated Map Object")],
            self._get('anim_tab', 'CHAR'), self._on_tab)
        # первая кнопка ряда своя у вкладки: Import (Characters) или
        # DFF+IFP+IDE (Objects) — одна кнопка, иначе ряд мерился бы по четырём
        self._b_first = _btn("", self._first_action, "")
        exp = _btn("Export", self._export_ifp,
                   "Export IFP — GTA SA animations", 'export')
        add = _btn("Add", self._merge_ifp,
                   "Add or replace animations in an existing IFP pack. Opens "
                   "ped.ifp / anim.ifp (or any other .ifp), overwrites "
                   "animations by name (case-insensitive) or appends them, "
                   "then saves the file back. Other animations in the pack "
                   "stay intact. Lets you skip external IFP editors when "
                   "editing a single animation in a vanilla pack", 'refresh')
        self._b_skin = _btn(
            "Export skin (single DFF)…", self._export_skin,
            "Quick export of a single model (vehicle / ped) to ONE .dff: "
            "turns on 'Single DFF' + DFF format and opens the export window — "
            "pick a folder/name and press Export.", 'export')
        self._top = FusedBlock([tabs, [self._b_first, exp, add], [self._b_skin]],
                               pad=3)
        lay.addWidget(self._top)

        self._char = QtWidgets.QWidget()
        self._build_char(self._char)
        lay.addWidget(self._char)
        self._obj = QtWidgets.QWidget()
        self._build_obj(self._obj)
        lay.addWidget(self._obj)
        self._apply_tab()

    # ════════════════════ вкладка Characters ══════════════════════════
    def _build_char(self, w):
        v = _vbox(w)
        stub = self._stub

        # Weight Paint: швы — в INU в режиме Weight Paint, в Max у меша со
        # Skin (веса красят в нём)
        wp = self._box()
        wp.addWidget(IconLabel("Weight Paint: seams", 'weights'))
        self._wp_idle = QtWidgets.QWidget()
        vl = _vbox(self._wp_idle)
        vl.addWidget(IconLabel("Merge co-located vertices for painting:",
                               'info', wrap=True))
        vl.addWidget(FusedBlock([[_btn(
            "Merge for painting", stub("Merge for painting", "weight_merge_start"),
            "Temporarily merge co-located vertices for weight editing. Backs "
            "up the mesh, averages weights between cluster-mates and welds "
            "the vertices. One object stays in the scene.", 'weights')]],
            height=BTN_H + 6))
        wp.addWidget(self._wp_idle)
        self._wp_merge = QtWidgets.QWidget()
        vl = _vbox(self._wp_merge)
        for text in ("MERGE MODE: don't modify geometry!",
                     "Don't press Ctrl+Z — Undo breaks the backup-mesh!"):
            vl.addWidget(IconLabel(text, 'error', wrap=True, icon_color=_ERR))
        vl.addWidget(FusedBlock([
            [_btn("Apply and restore seams",
                  stub("Apply and restore seams", "weight_merge_apply"),
                  "Apply the painted weights back onto the original split "
                  "geometry: reads the weights from the merged mesh, swaps the "
                  "mesh back to the backup (with split vertices) and "
                  "distributes the weights to the cluster-mates by "
                  "position-match.", 'check')],
            [_btn("Roll back", stub("Roll back", "weight_merge_cancel"),
                  "Roll back the merge without saving the painted weights: "
                  "swaps the mesh back to the backup and deletes the merged "
                  "copy. Weights painted in merged mode are lost.", 'x')]],
            height=BTN_H + 6))
        wp.addWidget(self._wp_merge)
        self._wp = wp.box
        v.addWidget(self._wp)

        # камера катсцены
        cam = self._box()
        cam.addWidget(IconLabel("Camera (cutscene .dat)", 'camera'))
        self._cam_exp = _btn("Export", self._camera_export,
                             "Export the active camera to a GTA cutscene .dat.",
                             'export')
        cam.addWidget(FusedBlock([[_btn(
            "Import", self._camera_import,
            "Import a GTA cutscene camera (.dat) - FOV, position, target.",
            'import'), self._cam_exp]]))
        v.addWidget(cam.box)

        # загруженные анимации (блок виден, когда библиотека не пуста)
        self._lb_count = QtWidgets.QLabel()
        v.addWidget(self._lb_count)
        self._act = QtWidgets.QWidget()
        vl = _vbox(self._act)
        self._cmb = QtWidgets.QComboBox()
        self._cmb.setEditable(True)
        self._cmb.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self._cmb.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self._cmb.setMinimumContentsLength(6)
        self._cmb.setFixedHeight(BTN_H)
        self._cmb.lineEdit().setPlaceholderText("Search…")
        self._cmb.setToolTip("Select IFP animation to apply")
        comp = self._cmb.completer()
        comp.setFilterMode(QtCore.Qt.MatchContains)
        comp.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        comp.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        self._cmb.currentTextChanged.connect(self._on_anim)
        vl.addLayout(self._labeled("Animation", self._cmb, 56))
        self._b_apply = _btn("Apply", stub("Apply", "apply_ifp"),
                             "Apply an IFP animation to the selected skeleton",
                             'play')
        self._b_preview = QtWidgets.QPushButton("Preview")
        self._b_preview.setCheckable(True)
        self._b_preview.setIcon(icon('eye'))
        self._b_preview.setToolTip(
            "Toggle live IFP animation preview without committing keys. Lets "
            "you quickly browse through the 294 vanilla ped.ifp animations by "
            "switching the Animation list. A repeated click turns preview off "
            "and restores the skeleton's previous animation.")
        self._b_preview.toggled.connect(self._on_preview)
        vl.addWidget(FusedBlock([[self._b_apply, self._b_preview]]))
        self._cur = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(self._cur)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(2)
        self._lb_cur = IconLabel("", 'bone')
        hl.addWidget(self._lb_cur, 1)
        hl.addWidget(icon_btn(
            'trash', "Delete the skeleton's current animation from the scene "
            "entirely — so forgotten animations don't end up in the IFP export.",
            stub("Delete current animation", "delete_active_action")))
        vl.addWidget(self._cur)
        v.addWidget(self._act)
        self._act_hint = IconLabel("Select a skeleton to apply", 'info', wrap=True)
        v.addWidget(self._act_hint)

        # IK Rig
        v.addWidget(IconLabel("IK Rig", 'ik'))
        self._ik = QtWidgets.QWidget()
        vl = _vbox(self._ik)
        self._fb_bake = FusedBlock([[_btn(       # && — иначе & станет мнемоникой
            "Bake && Clear IK", stub("Bake & Clear IK", "bake_ik_rig"),
            "Bake the visual IK pose onto the deform bones and remove "
            "IK-constraints and control bones. Do this BEFORE Export IFP — "
            "otherwise IFP would get raw rotations without IK applied.", 'rec')]])
        vl.addWidget(self._fb_bake)
        self._ik_root = self._check(
            "Root motion (walk/run)", 'ik_root_motion', False,
            "Enable for animations that move the character")
        vl.addWidget(self._ik_root)
        self._fb_add_ik = FusedBlock([[_btn(
            "Add IK Rig", stub("Add IK Rig", "add_ik_rig"),
            "Apply bone-based IK to the standard SA-ped chains: creates control "
            "bones for wrists, feet, head and root; deform bones get "
            "IK-constraints and Copy Rotation/Location targeting the matching "
            "control. Controls are coloured green. Before Export IFP — Bake & "
            "Clear IK, which removes everything and deletes the control bones.",
            'ik')]])
        vl.addWidget(self._fb_add_ik)
        v.addWidget(self._ik)

        # Handsign Tools
        hs = self._box()
        hs.addWidget(IconLabel("Handsign Tools", 'hand'))
        self._hs_status = IconLabel("", 'bone')
        hs.addWidget(self._hs_status)
        self._hs_attach = _btn(
            "Attach hands", stub("Attach hands", "handsign_attach"),
            "Attach the hands (shandl/shandr) to the player skeleton AT BONE "
            "LEVEL (ligabesar's tip): the hand forearm bone ' L ForeArm01' "
            "follows the player's ' L ForeArm', and ' L Hand01' follows "
            "' L Hand' (same for R). The hand stays a SEPARATE skeleton; only "
            "the matching bones are linked → auto position and orientation "
            "without manual alignment. Fingers (children of ' L Hand01') are "
            "not linked — you animate them yourself.", 'ik')
        hs.addWidget(FusedBlock([
            [self._hs_attach],
            [_btn("Detach", stub("Detach hands", "handsign_detach"),
                  "Detach the hands — remove all Handsign bindings, the hands "
                  "are free again. Nothing is deleted, only the constraints.",
                  'x')],
            [_btn("Export gesture → ghands.ifp", self._export_gesture,
                  "Export a gesture in ONE go: takes the current animation of "
                  "each of the three skeletons (arm → gsignN, left fingers → "
                  "lhgsignN, right → rhgsignN), builds the blocks and merges "
                  "them into ghands.ifp — blocks matching by name are "
                  "replaced, the rest (all the vanilla ones) stay "
                  "byte-for-byte. The animation name = the block name in the "
                  "IFP, so name your animations correctly (gsign6/lhgsign6/…).",
                  'export')]]))
        v.addWidget(hs.box)

        # «Дополнительно»: пол, коллизия, цвет / размер / видимость IK
        adv = Expander(self, 'ik_extras_show', False, "Advanced")
        adv.set_tip("Floor, collision and IK color settings")
        b = self._box()
        b.addWidget(FusedBlock([[_btn(
            "Floor", stub("Floor", "add_ground_plane"),
            "Create a 'floor' — a 10×10 m plane with a grid that acts as a "
            "clamp for the IK-rig legs. After Add IK Rig the feet get a Floor "
            "constraint with this plane as target — move the plane along Z "
            "and the feet are clamped above it. The gap above the plane is "
            "set by Collision.", 'plane')]]))
        b.addWidget(self._dspin(
            'floor_offset', 0.0, 1.0, 0.05, 3, 0.01,
            "Height of the virtual collision above the floor plane",
            prefix="Collision: ", suffix=" m"))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(1)
        row.addWidget(self._color_button(), 1)
        row.addWidget(self._dspin('ik_size', 0.1, 5.0, 1.0, 2, 0.1,
                                  "Size multiplier for all IK controls",
                                  prefix="Size: "), 1)
        b.addLayout(row)
        eyes = [self._eye(label, key, tip) for label, key, tip in (
            ("Hands/feet", 'ik_show_chain', "Show wrist and foot cubes"),
            ("Elbows/knees", 'ik_show_pole',
             "Show marker cubes on elbows and knees"),
            ("Head/torso", 'ik_show_rot',
             "Show head, upper torso and clavicle cubes"),
            ("Root", 'ik_show_root', "Show the root cube"))]
        b.addWidget(FusedBlock([eyes[:2], eyes[2:]], pad=3))
        b.addWidget(FusedBlock([
            [_btn("Validate round-trip", self._roundtrip,
                  "Round-trip diagnostics for IFP — checks that read → write "
                  "→ read doesn't lose animations, mix up bones or break "
                  "quaternions. The selected file is not modified: export "
                  "goes to a temp file, the result is compared with the "
                  "original and deleted. Report shows counters and maximum "
                  "numerical deltas (dRot, dTrans, dTime)", 'check')],
            [_btn("Batch Folder…", self._batch,
                  "Import every *.ifp in a folder and lay the animations one "
                  "after another on the active skeleton", 'folder')]]))
        adv.body.addWidget(b.box)
        v.addWidget(adv)

        # «Настройка анимации»: кватернионы, сглаживание, зеркало
        st = Expander(self, 'anim_tools_show', False, "Animation setup")
        st.set_tip("Utilities to fix sign discontinuities")
        b = self._box()
        b.addLayout(self._row(
            self._spin('anim_fix_start', 0, 99999, 0,
                       "First frame of the range", prefix="Start: "),
            self._spin('anim_fix_end', 0, 99999, 10000,
                       "Last frame of the range", prefix="End: "), spacing=1))
        axis_tip = ("Axis along which to smooth keys between anchors. All — "
                    "all channels in the bone's local space; X/Y/Z — "
                    "translation only, in world space (slower, but accounts "
                    "for parent rotation)")
        axis, self._smooth_group = self._seg_buttons(
            [("All", 'ALL', "All channels (local)\n\n" + axis_tip),
             ("X", 'WORLD_X', "World X (translation only)\n\n" + axis_tip),
             ("Y", 'WORLD_Y', "World Y (translation only)\n\n" + axis_tip),
             ("Z", 'WORLD_Z', "World Z (translation only)\n\n" + axis_tip)],
            self._get('smooth_axis_mode', 'ALL'),
            lambda d: self._set('smooth_axis_mode', d))
        b.addWidget(FusedBlock([
            [_btn("Fix quaternions (sign-flip)",
                  stub("Fix quaternions", "fix_quat_signs"),
                  "Fix quaternion sign-discontinuities over the Start–End "
                  "range. Between two adjacent keys with dot < 0 the bone "
                  "takes the long path through 360°: the second key's sign is "
                  "flipped — q and -q are the same rotation, but interpolation "
                  "then takes the short path. Idempotent; sometimes a 2nd pass "
                  "is needed for earlier-hidden discontinuities.", 'gimbal')],
            axis,
            [_btn("Smooth between anchor keys",
                  stub("Smooth between anchor keys", "smooth_between_anchors"),
                  "Smooth between selected anchor keys. Use-case: a baked "
                  "animation with a key on every frame. To lower a bone at "
                  "frame 70, move it there, select 3 keys (50, 70, 90: first, "
                  "edited, last) and press this button: the keys in between "
                  "are overwritten with smooth-step interpolation between the "
                  "anchors. Minimum 2 anchors; the «key on every frame» "
                  "structure is preserved (important for IFP round-trip).",
                  'curve')]], pad=3))
        b.addWidget(self._check(
            "Mirror Root rotation", 'mirror_root_rotation', True,
            "Also mirror the root bone rotation. If the character ends up "
            "upside-down after mirroring, turn this off: then the Root "
            "rotation stays as in the original and only the offset "
            "(forward/backward motion) is mirrored."))
        fb = self._box()
        fb.addWidget(IconLabel("Auto-turn Root by 180°", 'turn'))
        fb.addWidget(self._check(
            "Enable", 'mirror_flip_root_180', True,
            "Automatically adds a 180° rotation to Root on every frame "
            "(replaces the manual fix after mirroring). Compensates for the "
            "difference between the rest and in-game orientation of the GTA "
            "skeleton", self._refresh_flip))
        self._flip_rows = []
        for label, combo in (
                ("Axis", self._combo(
                    'mirror_flip_root_axis',
                    [("X", 'X', None), ("Y", 'Y', None), ("Z", 'Z', None)], 'X',
                    "Axis around which Root is turned 180°")),
                ("Space", self._combo(
                    'mirror_flip_root_space',
                    [("Local", 'LOCAL', "rot = rot @ flip (relative to the bone "
                      "itself)"),
                     ("Global", 'GLOBAL', "rot = flip @ rot (relative to the "
                      "skeleton)")], 'GLOBAL',
                    "Which space to apply the 180° turn in. If the result is "
                    "wrong, switch the option"))):
            rw = QtWidgets.QWidget()
            rw.setLayout(self._labeled(label, combo, 40))
            fb.addWidget(rw)
            self._flip_rows.append(rw)
        b.addWidget(fb.box)
        lb = self._box()
        lb.addWidget(IconLabel("Root Location invert", 'arrows'))
        lb.addLayout(self._labeled("Axis", self._combo(
            'mirror_invert_root_loc',
            [("Do not invert", 'NONE', None), ("X", 'X', None), ("Y", 'Y', None),
             ("Z", 'Z', None)], 'Y', "Negate one Root offset coordinate"), 40))
        b.addWidget(lb.box)
        b.addWidget(FusedBlock([[_btn(
            "Mirror animation (L/R)", stub("Mirror animation", "mirror_anim"),
            "Mirror the active animation (in-place). GTA rigs don't name bones "
            ".L/.R and have their own roll/rest, so built-in mirrors break GTA "
            "animation. Here every frame's bone world matrices are reflected "
            "(position and rotation, no negative scale) and assigned to the "
            "PAIRED L/R bone — 'turn left' becomes 'turn right' instead of an "
            "inside-out pose.", 'mirror')]]))
        st.body.addWidget(b.box)
        v.addWidget(st)
        self._refresh_flip()

    def _color_button(self):
        """Образец цвета IK-контролов (клик — выбрать цвет)."""
        b = QtWidgets.QPushButton()
        b.setFixedHeight(BTN_H)
        b.setToolTip("Color of all IK control bones")

        def paint():
            r, g, bl = [int(round(max(0.0, min(1.0, c)) * 255))
                        for c in self._get('ik_color', [0.2, 1.0, 0.2, 1.0])[:3]]
            b.setStyleSheet("QPushButton{background:rgb(%d,%d,%d); border:1px "
                            "solid %s; border-radius:2px;}" % (r, g, bl, C['ctlbd']))

        def pick():
            cur = self._get('ik_color', [0.2, 1.0, 0.2, 1.0])
            col = QtWidgets.QColorDialog.getColor(
                QtGui.QColor.fromRgbF(*cur), self, "IK control colour",
                QtWidgets.QColorDialog.ShowAlphaChannel)
            if col.isValid():
                self._set('ik_color', [col.redF(), col.greenF(), col.blueF(),
                                       col.alphaF()])
                paint()
        b.clicked.connect(lambda _c=False: pick())
        paint()
        return b

    def _eye(self, label, key, tip):
        """Переключатель видимости группы IK-контролов (глаз как в INU)."""
        b = self._tbtn(label, key, True, tip)
        b.toggled.connect(lambda on: b.setIcon(icon('eye' if on else 'eye_off')))
        b.setIcon(icon('eye' if b.isChecked() else 'eye_off'))
        return b

    def _refresh_flip(self):
        on = bool(self._get('mirror_flip_root_180', True))
        for rw in self._flip_rows:
            rw.setEnabled(on)

    # ════════════════════ вкладка Objects ═════════════════════════════
    def _build_obj(self, w):
        v = _vbox(w)
        stub = self._stub
        self._lb_count_obj = QtWidgets.QLabel()
        v.addWidget(self._lb_count_obj)
        amo = self._box(margins=(4, 4, 4, 4))
        amo.addWidget(IconLabel("Animated Map Object", 'screw'))
        self._hint1 = IconLabel("", 'info', wrap=True)
        self._hint2 = IconLabel("Pick the animated part with the eyedropper ↓",
                                'eyedropper', wrap=True)
        amo.addWidget(self._hint1)
        amo.addWidget(self._hint2)
        # пипетка: куда добавить (когда rig уже есть) + выбор меша
        self._pick = QtWidgets.QWidget()
        pl = _vbox(self._pick)
        tgt, self._pick_group = self._seg_buttons(
            _PICK_TARGETS, self._get('animobj_picker_target', 'NEW_PIVOT'),
            lambda d: self._set('animobj_picker_target', d))
        for b in tgt:
            b.setToolTip(b.toolTip() + "\n\n" + _PICK_TIP)
        self._pick_targets = FusedBlock([[b] for b in tgt])
        pl.addWidget(self._pick_targets)
        pl.addWidget(FusedBlock([[_btn(
            "Pick mesh…", stub("Pick mesh", "animobj_pick"),
            "Click and pick a mesh in the viewport. If there's no rig yet — "
            "it's created automatically. After picking you can pick the next "
            "one right away.", 'eyedropper')]]))
        amo.addWidget(self._pick)
        self._b_validate = _btn(
            "Validate", stub("Validate", "animobj_validate"),
            "Validate an Empty-rig: presence of root + pivot, correct BoneIDs, "
            "animation on the pivot, parented meshes. Reports the first issue "
            "found.", 'check')
        amo.addWidget(FusedBlock([[self._b_validate]]))
        self._pv = self._build_pivot()
        amo.addWidget(self._pv)
        # rig есть, а выделение не в pivot'е — дети rig'а
        self._rig_list = self._box(margins=(4, 3, 4, 3))
        self._rig_list.setSpacing(1)
        amo.addWidget(self._rig_list.box)
        v.addWidget(amo.box)

    def _build_pivot(self):
        """Настройки pivot'а, в котором лежит выделение (бокс INU ed_box)."""
        stub = self._stub
        b = self._box(margins=(4, 4, 4, 4))
        self._pv_title = IconLabel("", 'pivot')
        self._pv_counts = IconLabel("", 'mesh', wrap=True)
        self._pv_warn = IconLabel(
            "Pivot has no mesh — animation will not be visible. Select a mesh "
            "and press «To pivot»", 'error', wrap=True, icon_color=_ERR)
        for w in (self._pv_title, self._pv_counts, self._pv_warn):
            b.addWidget(w)
        b.addWidget(FusedBlock([[
            _btn("To pivot", lambda: self._parent_to('PIVOT'),
                 "Parent selected meshes to the rig pivot — they will rotate "
                 "with the rig. If several rigs exist, the one containing the "
                 "active object is preferred."),
            _btn("To root", lambda: self._parent_to('ROOT'),
                 "Parent selected meshes to the rig root — they stay static as "
                 "the base (e.g. the windmill body without its blades)."),
            _btn("+Pivot", self._add_pivot,
                 "Add another pivot Empty to an existing Empty-rig — for models "
                 "with several animated parts (e.g. windmill + counterweight). "
                 "Each pivot gets its own BoneID and animation. If a mesh is "
                 "selected it is parented to the new pivot right away.")]], pad=3))
        # добавить меш в rig (настройка «куда» — на root rig'а)
        ad = self._box(margins=(4, 3, 4, 4))
        ad.addWidget(IconLabel("Add mesh to rig:", 'eyedropper'))
        tgt, self._attach_group = self._seg_buttons(
            [("New pivot", 'NEW_PIVOT', "Create a new pivot and parent the mesh "
              "to it"),
             ("To existing pivot", 'PIVOT', "Parent to the first pivot (one "
              "shared animation)"),
             ("To root (static)", 'ROOT', "Static part — will not rotate")],
            'NEW_PIVOT', self._on_attach_target)
        ad.addWidget(FusedBlock([[t] for t in tgt]))
        ad.addWidget(FusedBlock([[_btn(
            "Pick mesh…", stub("Pick mesh", "animobj_attach_mesh"),
            "Click and pick a mesh in the viewport. It will be attached to the "
            "rig according to «Where to add»", 'eyedropper')]]))
        self._pv_add = ad.box
        b.addWidget(ad.box)
        # структура rig'а: root, дети, внуки
        tr = self._box(margins=(4, 3, 4, 3))
        tr.setSpacing(1)
        tr.addWidget(IconLabel("Rig structure:", 'outliner'))
        self._pv_rows = QtWidgets.QVBoxLayout()
        self._pv_rows.setSpacing(1)
        tr.addLayout(self._pv_rows)
        self._pv_tree = tr.box
        b.addWidget(tr.box)
        # режим: Auto (ключи цикла строятся сами) / Manual
        auto_tip = ("Auto: sliders rebuild the cycle keyframes themselves.\n"
                    "Manual: sliders frozen, you place keyframes yourself")
        self._b_auto = QtWidgets.QPushButton("Auto")
        self._b_auto.setCheckable(True)
        self._b_auto.setIcon(icon('curve'))
        self._b_auto.setToolTip(auto_tip)
        self._b_auto.toggled.connect(lambda on: self._pv_set('auto_mode', bool(on)))
        self._b_manual = QtWidgets.QPushButton("Manual")
        self._b_manual.setCheckable(True)
        self._b_manual.setIcon(icon('hand'))
        self._b_manual.setToolTip(auto_tip)
        self._b_manual.setEnabled(False)        # как в INU: всегда серая
        b.addWidget(FusedBlock([[self._b_auto, self._b_manual]]))
        self._pv_auto = QtWidgets.QWidget()
        vl = _vbox(self._pv_auto)
        axis, self._axis_group = self._seg_buttons(
            [("X", 'X'), ("Y", 'Y'), ("Z", 'Z')], 'Z',
            lambda d: self._pv_set('axis', d), "Axis")
        vl.addWidget(FusedBlock([[a] for a in axis]))
        self._pv_rev = QtWidgets.QCheckBox("Reverse direction")
        self._pv_rev.toggled.connect(lambda on: self._pv_set('reverse', bool(on)))
        vl.addWidget(self._pv_rev)
        self._pv_turns = QtWidgets.QSpinBox()
        self._pv_turns.setRange(1, 999)
        self._pv_turns.setPrefix("Turns per cycle: ")
        self._pv_turns.valueChanged.connect(
            lambda n: self._pv_set('turns_per_cycle', int(n)))
        self._pv_dur = QtWidgets.QSpinBox()
        self._pv_dur.setRange(2, 9999)
        self._pv_dur.setPrefix("Duration (frames): ")
        self._pv_dur.valueChanged.connect(
            lambda n: self._pv_set('duration_frames', int(n)))
        for sp in (self._pv_turns, self._pv_dur):
            sp.setFixedHeight(BTN_H)
            vl.addWidget(sp)
        self._lb_rps = IconLabel("", 'info')
        vl.addWidget(self._lb_rps)
        b.addWidget(self._pv_auto)
        self._pv_manual = QtWidgets.QWidget()
        vl = _vbox(self._pv_manual, 1)
        vl.addWidget(IconLabel("Manual mode — keyframes are managed by hand",
                               'hand', wrap=True))
        vl.addWidget(IconLabel("Track View — Dope Sheet", None))
        vl.addWidget(IconLabel("Switching to Auto will overwrite your keyframes",
                               'error', wrap=True, icon_color=_ERR))
        b.addWidget(self._pv_manual)
        return b.box

    # ════════════════════ вкладки и выделение ═════════════════════════
    def _on_tab(self, tab):
        self._set('anim_tab', tab)
        self._seg_sync(self._tab_group, tab)
        self._apply_tab()
        self._refresh()

    def _apply_tab(self):
        char = self._get('anim_tab', 'CHAR') != 'OBJ'
        if char:
            self._b_first.setText("Import")
            self._b_first.setIcon(icon('import'))
            self._b_first.setToolTip("Import IFP — GTA SA animations")
        else:
            self._b_first.setText("DFF+IFP+IDE")
            self._b_first.setIcon(icon('export'))
            self._b_first.setToolTip(
                "Export an animated map object in one click: writes "
                "<base>.dff + <base>.ifp to the chosen folder. Optionally "
                "appends or updates the anim entry in the specified IDE file.")
        self._b_skin.setVisible(char)
        self._top.update_corners()
        self._char.setVisible(char)
        self._obj.setVisible(not char)

    def _first_action(self):
        if self._get('anim_tab', 'CHAR') == 'OBJ':
            self._animobj_export()
        else:
            self._import_ifp()

    def on_selection(self, snap):
        self._node = snap.get('node') if snap else None
        self._refresh()

    def _refresh(self):
        names = _safe(lambda: _anim().library_names(), []) or []
        if self._get('anim_tab', 'CHAR') == 'OBJ':
            self._refresh_obj(names)
        else:
            self._refresh_char(names)

    def _count_text(self, n):
        return "%d animations loaded" % n

    def _refresh_char(self, names):
        a, node = _anim(), self._node
        mesh = node if node is not None and \
            _safe(lambda: _sel().node_kind(node)) == 'MESH' else None
        skin = mesh is not None and bool(_safe(lambda: a.has_skin(mesh), False))
        self._wp.setVisible(skin)
        if skin:
            merged = bool(_safe(lambda: _sel().get_prop(
                mesh, 'weight_edit_backup', ''), ''))
            self._wp_idle.setVisible(not merged)
            self._wp_merge.setVisible(merged)
        self._cam_exp.setEnabled(bool(_safe(lambda: a.is_camera(node), False)))

        n = len(names)
        skel = _safe(lambda: a.skeleton_root(node))
        self._lb_count.setVisible(n > 0)
        self._lb_count.setText(self._count_text(n))
        self._act.setVisible(n > 0 and skel is not None)
        self._act_hint.setVisible(n > 0 and skel is None)
        if names != self._names:
            self._names = list(names)
            self._cmb.blockSignals(True)
            self._cmb.clear()
            self._cmb.addItems(names)
            self._cmb.setCurrentText(str(self._get('ifp_action', '') or ''))
            self._cmb.blockSignals(False)
        self._b_apply.setEnabled(bool(self._get('ifp_action', '')))
        cur = _safe(lambda: _sel().get_prop(skel, 'ifp_current', ''), '') \
            if skel is not None else ''
        self._cur.setVisible(bool(cur))
        self._lb_cur.setText("Current: %s" % cur)

        self._ik.setVisible(skel is not None)
        rigged = skel is not None and bool(_safe(lambda: _sel().get_prop(
            skel, 'ik_rigged', False), False))
        self._fb_bake.setVisible(rigged)
        self._ik_root.setVisible(not rigged)
        self._fb_add_ik.setVisible(not rigged)

        ped, lh, rh = _safe(a.handsign_status, (None, None, None))
        self._hs_status.setText("%s · L:%s · R:%s" % (
            str(ped.name) if ped is not None else "—",
            "✓" if lh is not None else "—", "✓" if rh is not None else "—"))
        self._hs_attach.setEnabled(ped is not None and
                                   (lh is not None or rh is not None))

    def _refresh_obj(self, names):
        a, node = _anim(), self._node
        n = len(names)
        self._lb_count_obj.setVisible(n > 0)
        self._lb_count_obj.setText(self._count_text(n))
        rig = _safe(a.find_rig)
        mesh = node if node is not None and \
            _safe(lambda: _sel().node_kind(node)) == 'MESH' else None
        in_rig = mesh is not None and _safe(lambda: a.rig_of(mesh)) is not None
        if rig is not None:
            self._hint1.setText("Target rig: %s" % rig.name)
            self._hint1.setIcon('outliner')
        elif mesh is not None and not in_rig:
            self._hint1.setText("Static: %s" % mesh.name)
            self._hint1.setIcon('mesh')
        else:
            self._hint1.setText("Select a base mesh (will become the static part)")
            self._hint1.setIcon('info')
        self._hint2.setVisible(rig is None and mesh is not None and not in_rig)
        self._pick.setEnabled(rig is not None or (mesh is not None and not in_rig))
        self._pick_targets.setVisible(rig is not None)
        self._b_validate.setEnabled(rig is not None)

        self._pivot = _safe(lambda: a.pivot_of(node))
        self._pv.setVisible(self._pivot is not None)
        self._rig_list.box.setVisible(self._pivot is None and rig is not None)
        if self._pivot is not None:
            _safe(lambda: self._fill_pivot(self._pivot))
        elif rig is not None:
            _safe(lambda: self._fill_rows(
                self._rig_list, [(c, 1) for c in rig.children]))

    def _fill_rows(self, lay, items, first=0):
        """Строки rig'а «имя [метка]» с иконкой и отступом по глубине."""
        a = _anim()
        while lay.count() > first:
            it = lay.takeAt(first)
            if it.widget() is not None:
                it.widget().deleteLater()
        for o, depth in items:
            ic, tag = a.node_tag(o)
            lay.addWidget(IconLabel(("%s %s" % (o.name, tag)).strip(), ic,
                                    indent=depth * 10))

    def _fill_pivot(self, pivot):
        a, sel = _anim(), _sel()
        self._pv_title.setText("Settings: %s" % pivot.name)
        n_piv = a.mesh_count(pivot)
        parent = pivot.parent
        n_root = a.mesh_count(parent) if a.is_rig_root(parent) else 0
        self._pv_counts.setText("Meshes under pivot: %d  /  under root: %d"
                                % (n_piv, n_root))
        self._pv_warn.setVisible(n_piv == 0)
        self._rig_root = parent
        self._pv_add.setVisible(parent is not None)
        self._pv_tree.setVisible(parent is not None)
        if parent is not None:
            self._seg_sync(self._attach_group,
                           sel.get_prop(parent, 'attach_target', 'NEW_PIVOT'))
            self._fill_rows(self._pv_rows, a.rig_tree(parent))
        s = a.pivot_settings(pivot)
        for w in (self._b_auto, self._pv_rev, self._pv_turns, self._pv_dur):
            w.blockSignals(True)
        self._b_auto.setChecked(bool(s['auto_mode']))
        self._pv_rev.setChecked(bool(s['reverse']))
        self._pv_turns.setValue(int(s['turns_per_cycle']))
        self._pv_dur.setValue(int(s['duration_frames']))
        for w in (self._b_auto, self._pv_rev, self._pv_turns, self._pv_dur):
            w.blockSignals(False)
        self._seg_sync(self._axis_group, str(s['axis']))
        self._show_mode(bool(s['auto_mode']))

    def _show_mode(self, auto):
        self._b_manual.setChecked(not auto)
        self._pv_auto.setVisible(auto)
        self._pv_manual.setVisible(not auto)
        # ≈ об/сек: (−1 если обратно) × обороты × FPS / длительность
        fps = max(1, _safe(lambda: _anim().frame_rate(), 30) or 30)
        rps = (-1 if self._pv_rev.isChecked() else 1) * self._pv_turns.value() \
            * fps / float(max(1, self._pv_dur.value()))
        self._lb_rps.setText("≈ %+.2f rev/s at FPS %d" % (rps, fps))

    def _pv_set(self, key, value):
        """Правка настройки pivot'а → user property pivot'а (ключи цикла
        перестроит логика сцены — следующий этап)."""
        if self._pivot is None:
            return
        _safe(lambda: _sel().set_prop([self._pivot], key, value))
        self._show_mode(self._b_auto.isChecked())

    def _on_attach_target(self, target):
        if self._rig_root is not None:
            _safe(lambda: _sel().set_prop([self._rig_root], 'attach_target',
                                          target))

    # ════════════════════ действия ════════════════════════════════════
    def _stub(self, label, key):
        """Кнопка, логика которой ещё не перенесена: заглушка панели."""
        return lambda: self._dispatch(label, key)

    def _not_yet(self, title, what, lines):
        QtWidgets.QMessageBox.information(
            self, "INU: " + title,
            "%s is not implemented yet.\n\n%s" % (what, "\n".join(lines)))

    def _skeleton(self):
        return _safe(lambda: _anim().skeleton_root(self._node))

    def _need_skeleton(self):
        if self._skeleton() is None:
            QtWidgets.QMessageBox.warning(self, "INU Tools",
                                          "Select a skeleton (armature)")
            return False
        return True

    def _dialog(self, title, mode, filters, key, accept, options=None,
                filename='', confirm=True):
        from .file_dialog import INUFileDialog
        return INUFileDialog(self, title, mode=mode, filters=filters, key=key,
                             accept_label=accept, options=options,
                             filename=filename, confirm_overwrite=confirm)

    def _import_ifp(self):
        dlg = self._dialog("INU: Import IFP", 'open', ao.IFP_FILTERS, 'ifp',
                           "Import")
        if not dlg.exec():
            return
        path = dlg.selected_files()[0]
        try:
            from ..ops import anim as ops
            n = ops.import_ifp(path)
        except Exception as e:                         # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "INU: Import IFP",
                                           "IFP import error: %s" % e)
            return
        self._names = None
        self._refresh()
        QtWidgets.QMessageBox.information(self, "INU: Import IFP",
                                          "IFP: %d animations imported" % n)

    def _export_ifp(self):
        game = self._get('game', 'SA')
        self._set('ifp_format', ao.default_format(game))
        dlg = self._dialog("INU: Export IFP", 'save', ao.IFP_FILTERS,
                           'ifp_export', "Export", ao.IfpExportOptions(),
                           "custom.ifp")
        if not dlg.exec():
            return
        fmt = self._get('ifp_format', 'ANPK')
        lines = ["File: %s" % dlg.save_path()]
        if fmt == 'ANP3' and game != 'SA':
            lines.append("ANP3 is not supported in %s — switching to ANPK" % game)
            fmt = 'ANPK'
        lines.append("Format: %s" % fmt)
        self._not_yet("Export IFP", "IFP export", lines)

    def _merge_ifp(self):
        if not self._need_skeleton():
            return
        dlg = self._dialog("INU: Add to IFP", 'save', ao.IFP_FILTERS, 'ifp_merge',
                           "Add", ao.IfpMergeOptions(), "ped.ifp", confirm=False)
        if dlg.exec():
            self._not_yet("Add to IFP", "Merging into IFP",
                          ["File: %s" % dlg.save_path()])

    def _export_skin(self):
        # как quick_single_export INU: «Один DFF» + формат DFF, окно экспорта
        self._set('exp_single_dff', True)
        self._set('exp_dff', True)
        self._export_skin_cb()

    def _camera_import(self):
        dlg = self._dialog("INU: Import Camera .dat", 'open', ao.CAMERA_FILTERS,
                           'camera', "Import", ao.CameraOptions(False))
        if dlg.exec():
            self._not_yet("Import Camera", "Camera import",
                          ["File: %s" % dlg.selected_files()[0]])

    def _camera_export(self):
        node = self._node
        name = str(node.name) if node is not None else "camera"
        dlg = self._dialog("INU: Export Camera .dat", 'save', ao.CAMERA_FILTERS,
                           'camera', "Export", ao.CameraOptions(True),
                           name + ".dat")
        if dlg.exec():
            self._not_yet("Export Camera", "Camera export",
                          ["File: %s" % dlg.save_path()])

    def _on_anim(self, text):
        self._set('ifp_action', text.strip())
        self._b_apply.setEnabled(bool(text.strip()))

    def _on_preview(self, on):
        self._b_preview.setText("Preview ●" if on else "Preview")
        if on:
            self._b_preview.blockSignals(True)
            self._b_preview.setChecked(False)
            self._b_preview.setText("Preview")
            self._b_preview.blockSignals(False)
            self._dispatch("Preview", "ifp_preview_toggle")

    def _roundtrip(self):
        dlg = self._dialog("INU: Validate IFP Round-trip", 'open',
                           ao.IFP_FILTERS, 'ifp', "Validate")
        if not dlg.exec():
            return
        try:
            from ..ops import anim as ops
            ok, text = ops.roundtrip(dlg.selected_files()[0])
        except Exception as e:                         # noqa: BLE001
            ok, text = None, "IFP round-trip: %s" % e
        box = (QtWidgets.QMessageBox.information if ok else
               QtWidgets.QMessageBox.warning if ok is False else
               QtWidgets.QMessageBox.critical)
        box(self, "INU: IFP Round-trip", text)

    def _batch(self):
        if not self._need_skeleton():
            return
        dlg = self._dialog("INU: Batch Import IFP Folder", 'folder', None,
                           'ifp_batch', "Import", ao.IfpBatchOptions())
        if not dlg.exec():
            return
        g = self._get
        self._not_yet("Batch Import IFP", "Batch import", [
            "Folder: %s" % dlg.selected_folder(),
            "Prefix: %s · Mode: %s · Gap: %g" % (
                g('batch_prefix', '') or "—", g('batch_mode', 'NLA'),
                g('batch_gap', 10.0)),
            "Start: %d · Count: %s" % (g('batch_start', 0),
                                       g('batch_count', 0) or "all")])

    def _export_gesture(self):
        self._set('hs_format', ao.default_format(self._get('game', 'SA')))
        dlg = self._dialog("INU: Export gesture to ghands.ifp", 'save',
                           ao.IFP_FILTERS, 'ifp_gesture', "Export",
                           ao.GestureOptions(), "ghands.ifp", confirm=False)
        if dlg.exec():
            self._not_yet("Export gesture", "Gesture export",
                          ["File: %s" % dlg.save_path()])

    def _animobj_export(self):
        if self._node is None:
            QtWidgets.QMessageBox.warning(self, "INU Tools", "Select an object")
            return
        a, sel = _anim(), _sel()
        rig = _safe(lambda: a.rig_of(self._node) or a.find_rig())
        anim, n_piv = '', 0
        if rig is not None:
            # как invoke INU: имена — от анимации первого pivot'а, Model ID /
            # Draw distance / TXD — от первого меша rig'а
            piv = _safe(lambda: a.pivots(rig), []) or []
            n_piv = len(piv)
            if piv:
                anim = _safe(lambda: a.anim_name(piv[0]), '') or ''
                self._set('ao_base_name', anim)
                self._set('ao_txd_name', anim)
            mesh = _safe(lambda: a.first_mesh(rig))
            if mesh is not None:
                self._set('ao_model_id', _safe(
                    lambda: sel.get_prop(mesh, 'model_id', 0), 0))
                self._set('ao_draw_distance', max(10.0, float(_safe(
                    lambda: sel.get_prop(mesh, 'draw_distance', 300.0), 300.0))))
                txd = _safe(lambda: sel.get_prop(mesh, 'txd_name', ''), '')
                if txd:
                    self._set('ao_txd_name', txd)
        dlg = ao.AnimObjExportDialog(self, anim, n_piv)
        if dlg.exec():
            g = self._get
            self._not_yet("Export Animated Object", "Animated object export", [
                "Folder: %s" % (g('ao_directory', '') or "—"),
                "Base name: %s · Model ID: %d" % (g('ao_base_name', ''),
                                                  g('ao_model_id', 0))])

    def _add_pivot(self):
        if _safe(_anim().find_rig) is None:
            QtWidgets.QMessageBox.warning(self, "INU Tools",
                                          "No Empty-rig in the scene")
            return
        if ao.AddPivotDialog(self).exec():
            self._not_yet("Add Pivot", "Adding a pivot", [
                "Name: %s · Axis: %s" % (self._get('pv_name', 'pivot2'),
                                         self._get('pv_axis', 'Z'))])

    def _parent_to(self, to):
        res = _safe(lambda: _anim().parent_selected(to))
        if res is None:
            return
        msg, err = res
        if err:
            QtWidgets.QMessageBox.warning(self, "INU Tools", msg)
        else:
            print("[INU] %s" % msg)
        self._refresh()
