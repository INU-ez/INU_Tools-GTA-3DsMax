# INU Tools (Max) — окно «Vehicles»: панели Blender-версии INU «Машины» и
# «Иерархия фреймов». FrameHierarchy общий: окно анимаций использует его в
# режиме 'PED' (как GTATOOLS_PT_frame_hierarchy_anim в INU).
# Работает: дерево иерархии сцены (выделить / сменить родителя / снять
# родителя / F2 — переименовать), Validate Vehicle/Ped, проверка пар и показ
# _ok/_dam. Заглушки: масштаб, создание _dam, зеркало L↔R.

from ..qt import QtWidgets, QtCore

from .style import C, BTN_H, icon
from .widgets import BuildMixin, FusedBlock, ElideLabel

_TREE_MAX = 80                  # как в INU: не больше 80 строк


def _sel():
    from ..adapter import selection
    return selection


def _frames():
    from ..ops import frames
    return frames


def _names_under(node):
    try:
        _root, items = _sel().hierarchy(node)
        return [str(o.name) for o, _d in items], items
    except Exception:                                  # noqa: BLE001
        return [], []


class VehicleTools(BuildMixin, QtWidgets.QWidget):
    """Кнопки панели INU «Машины»."""

    def __init__(self, dispatch, export_cb, parent=None):
        super().__init__(parent)
        self._dispatch = dispatch
        self._export_cb = export_cb
        self._node = None
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        exp = self._btn("Export vehicle (single DFF)…", self._export,
                        "Quick export of a single model (vehicle / ped) to ONE "
                        ".dff: turns on 'Single DFF' + DFF format and opens the "
                        "export window — pick a folder/name and press Export. "
                        "The vehicle's collision is embedded into the .dff.",
                        'export')
        self._scale = self._btn("Vehicle Scale…", self._scale_dialog,
                                "Uniformly scale the whole vehicle hierarchy "
                                "(root + meshes + dummies) while preserving "
                                "structure.")
        lay.addWidget(FusedBlock([[exp], [self._scale]]))
        lay.addWidget(QtWidgets.QLabel("Damage variants:"))
        self._dam = self._btn("Create _dam", lambda: self._dispatch(
            "Create _dam", "vehicle_add_damage_variant"),
            "Create a damaged (_dam) duplicate of the active mesh. If the source "
            "has no suffix, _ok is assigned to it. The damaged variant is placed "
            "in the same hierarchy and hidden in the viewport.")
        lay.addWidget(FusedBlock([[self._dam]]))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QtWidgets.QLabel("Show:"))
        row.addWidget(FusedBlock([[
            self._btn(label, lambda s=state: self._show(s),
                      "Toggle OK / Damaged vehicle parts display in the "
                      "viewport (scans the active vehicle's hierarchy, or the "
                      "whole scene). Does not affect DFF export.")
            for label, state in (("OK", 'OK'), ("Dam", 'DAM'), ("Both", 'BOTH'))]]), 1)
        lay.addLayout(row)
        lay.addWidget(FusedBlock([[self._btn(
            "Check pairs", self._pairs,
            "Find and report _ok / _dam pairs in the active hierarchy. Warns "
            "when a mesh has _ok without _dam (or vice versa) — such a mesh is "
            "skipped by the engine on damage.", 'check')]]))
        self.on_selection(None)

    @staticmethod
    def _btn(label, slot, tip, icon_name=None):
        b = QtWidgets.QPushButton(label)
        b.setToolTip(tip)
        if icon_name:
            b.setIcon(icon(icon_name))
        b.clicked.connect(lambda _c=False: slot())
        return b

    def on_selection(self, snap):
        self._node = snap.get('node') if snap else None
        mesh = snap.get('active') if snap else None
        self._scale.setEnabled(self._node is not None)
        self._dam.setEnabled(mesh is not None)

    def _export(self):
        # как quick_single_export INU: «Один DFF» + формат DFF, окно экспорта
        self._set('exp_single_dff', True)
        self._set('exp_dff', True)
        self._export_cb()

    def _scale_dialog(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("INU: Vehicle Scale")
        form = QtWidgets.QFormLayout(dlg)
        f = QtWidgets.QDoubleSpinBox()
        f.setLocale(QtCore.QLocale.c())
        f.setRange(0.01, 100.0)
        f.setDecimals(3)
        f.setValue(1.0)
        f.setToolTip("Uniform scale factor — applied to positions and vertices")
        d = QtWidgets.QCheckBox("Dummies Only")
        d.setToolTip("Move dummy helpers only, leave meshes untouched")
        form.addRow("Factor", f)
        form.addRow(d)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                        | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec():
            self._dispatch("Vehicle Scale ×%g" % f.value(), "vehicle_scale",
                           factor=f.value(), dummies_only=d.isChecked())

    def _scope_meshes(self):
        """Меши иерархии активной машины (или всей сцены, если ничего не
        выделено) — как область vehicle_show_damage / pair_report INU."""
        sel = _sel()
        if self._node is not None:
            _names, items = _names_under(self._node)
            nodes = [o for o, _d in items]
        else:
            import pymxs
            nodes = list(pymxs.runtime.objects)
        return [o for o in nodes if sel.node_kind(o) == 'MESH']

    def _show(self, state):
        try:
            meshes = self._scope_meshes()
        except Exception as e:                         # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "INU Tools", str(e))
            return
        oks = [o for o in meshes if str(o.name).endswith('_ok')]
        dams = [o for o in meshes if str(o.name).endswith('_dam')]
        sel = _sel()
        sel.set_hidden(oks, state == 'DAM')
        sel.set_hidden(dams, state == 'OK')
        print("[INU] %s: OK=%d Damaged=%d" % (state, len(oks), len(dams)))

    def _pairs(self):
        try:
            names = [str(o.name) for o in self._scope_meshes()]
        except Exception as e:                         # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, "INU Tools", str(e))
            return
        pairs, lone_ok, lone_dam = _frames().pair_report(names)
        lines = ["Pairs: %d | lonely _ok: %d | lonely _dam: %d"
                 % (len(pairs), len(lone_ok), len(lone_dam))]
        if lone_ok:
            lines.append("\n_ok without pair:\n  " + "\n  ".join(lone_ok))
        if lone_dam:
            lines.append("\n_dam without pair:\n  " + "\n  ".join(lone_dam))
        box = (QtWidgets.QMessageBox.warning if (lone_ok or lone_dam)
               else QtWidgets.QMessageBox.information)
        box(self, "INU Tools: Check pairs", "\n".join(lines))


class FrameHierarchy(BuildMixin, QtWidgets.QWidget):
    """«Иерархия фреймов» INU: Validate + Mirror L↔R, корень, подсказка и
    дерево от корня активного объекта. Строка: отступ, имя (клик —
    выделить; активный — подсвечен), ⤴ (сделать родителем выделенного),
    ⛓ (снять родителя). F2 на выделенной строке — переименовать."""

    def __init__(self, dispatch, template='VEHICLE', parent=None):
        super().__init__(parent)
        self._dispatch = dispatch
        self._template = template
        self._node = None
        self._rows = {}
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        is_veh = template == 'VEHICLE'
        self._validate = QtWidgets.QPushButton(
            "Validate Vehicle" if is_veh else "Validate Ped")
        self._validate.setIcon(icon('check'))
        self._validate.setToolTip("Validate the active object's hierarchy against "
                                  "the vanilla SA template.")
        self._validate.clicked.connect(self._run_validate)
        self._mirror = QtWidgets.QPushButton("Mirror L↔R")
        self._mirror.setIcon(icon('mirror'))
        self._mirror.setToolTip("Create a mirrored copy of selected frames: _lf → "
                                "_rf, _lb → _rb (X is mirrored). If the mirrored "
                                "twin already exists — it is left alone.")
        self._mirror.clicked.connect(
            lambda: self._dispatch("Mirror L↔R", "frame_mirror_lr"))
        lay.addWidget(FusedBlock([[self._validate, self._mirror]]))
        self._empty = self._info("Select an object to see the hierarchy")
        lay.addWidget(self._empty)
        self._root = ElideLabel()
        lay.addWidget(self._root)
        self._hint = self._info("Click = select · ⤴ = parent of selected · "
                                "⛓ = unparent · F2 = rename")
        lay.addWidget(self._hint)
        self._tree = self._box(margins=(3, 3, 3, 3))
        self._tree.setSpacing(1)
        lay.addWidget(self._tree.box)
        self.on_selection(None)

    # — данные —
    def on_selection(self, snap):
        self._node = snap.get('node') if snap else None
        names = (snap or {}).get('sel_names', []) or []
        self._validate.setEnabled(self._node is not None)
        self._mirror.setEnabled(any('_lf' in n or '_lb' in n for n in names))
        self.rebuild()

    def rebuild(self):
        while self._tree.count():
            it = self._tree.takeAt(0)
            if it.widget() is not None:
                it.widget().deleteLater()
        self._rows = {}
        node = self._node
        self._empty.setVisible(node is None)
        for w in (self._root, self._hint, self._tree.box):
            w.setVisible(node is not None)
        if node is None:
            return
        sel = _sel()
        try:
            root, items = sel.hierarchy(node, limit=_TREE_MAX)
        except Exception as e:                         # noqa: BLE001
            print("[INU] frame hierarchy: %r" % (e,))
            return
        self._root.setText("Root: %s" % root.name)
        active = str(node.name)
        parent_name = str(node.parent.name) if node.parent is not None else ''
        for o, depth in items[:_TREE_MAX]:
            self._tree.addWidget(self._row(o, depth, active, parent_name))
        if len(items) > _TREE_MAX:
            self._tree.addWidget(self._info("… more rows not shown"))

    def _row(self, o, depth, active, parent_name):
        name = str(o.name)
        kind = _sel().node_kind(o)
        w = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(w)
        hl.setContentsMargins(depth * 10, 0, 0, 0)
        hl.setSpacing(1)
        b = QtWidgets.QPushButton(name)
        b.setIcon(icon({'MESH': 'mesh', 'BONE': 'bone'}.get(kind, 'empty')))
        b.setFixedHeight(BTN_H - 2)
        is_active = name == active
        b.setStyleSheet(
            "QPushButton{text-align:left; padding:0 4px; border:none; "
            "background:%s;} QPushButton:hover{background:#5a5a5a;}"
            % ("#5b7fa6" if is_active else "transparent"))
        b.setToolTip(name)
        b.clicked.connect(lambda _c=False, n=name: self._select(n))
        hl.addWidget(b, 1)
        btns = []
        if not is_active:
            up = QtWidgets.QPushButton()
            up.setIcon(icon('parent'))
            up.setCheckable(True)
            up.setChecked(name == parent_name)       # текущий родитель
            up.setToolTip("Make «%s» the parent of the selected frame" % name)
            up.clicked.connect(lambda _c=False, n=name: self._reparent(n, ''))
            btns.append(up)
        if o.parent is not None:
            un = QtWidgets.QPushButton()
            un.setIcon(icon('unlink'))
            un.setToolTip("Unparent — make «%s» a root" % name)
            un.clicked.connect(lambda _c=False, n=name: self._reparent('', n))
            btns.append(un)
        for x in btns:
            x.setFixedSize(BTN_H, BTN_H - 2)
        if btns:
            hl.addWidget(FusedBlock([btns], height=BTN_H - 2))
        self._rows[name] = b
        return w

    # — действия —
    def _select(self, name):
        try:
            _sel().select_node(name)
        except Exception as e:                         # noqa: BLE001
            print("[INU] select frame: %r" % (e,))

    def _reparent(self, parent_name, child_name):
        """⤴: parent_name — строка, ребёнок — активный объект;
        ⛓: child_name — строка, родитель — нет."""
        try:
            err = _sel().set_parent(child_name, parent_name)
        except Exception as e:                         # noqa: BLE001
            err = str(e)
        if err:
            QtWidgets.QMessageBox.warning(self, "INU Tools", err)
        self.rebuild()

    def keyPressEvent(self, e):                        # noqa: N802
        # F2 — переименовать активный фрейм (как F2 в Blender)
        if e.key() == QtCore.Qt.Key_F2 and self._node is not None:
            old = str(self._node.name)
            new, ok = QtWidgets.QInputDialog.getText(
                self, "INU: Rename Frame",
                "New frame name (exact match required for vehicles and peds)",
                text=old)
            if ok and new.strip() and new.strip() != old:
                _sel().rename_node(old, new.strip())
                self.rebuild()
            return
        super().keyPressEvent(e)

    def _run_validate(self):
        names, _items = _names_under(self._node) if self._node is not None \
            else ([], [])
        fr = _frames()
        if self._template == 'VEHICLE':
            fatal, warns = fr.check_vehicle_names(names)
            if fatal:
                QtWidgets.QMessageBox.critical(
                    self, "INU: Validate Vehicle",
                    "Vehicle: the game will crash —\n  " + "\n  ".join(fatal)
                    + ("\n\nSuspicious:\n  " + "\n  ".join(warns) if warns else ""))
            elif warns:
                QtWidgets.QMessageBox.warning(
                    self, "INU: Validate Vehicle",
                    "Vehicle: missing=0, suspicious=%d\n  %s"
                    % (len(warns), "\n  ".join(warns)))
            else:
                QtWidgets.QMessageBox.information(self, "INU: Validate Vehicle",
                                                  "Vehicle hierarchy OK")
        else:
            missing = fr.check_ped_names(names)
            if missing:
                QtWidgets.QMessageBox.warning(
                    self, "INU: Validate Ped", "Ped: missing=%d\n  %s"
                    % (len(missing), "\n  ".join(missing)))
            else:
                QtWidgets.QMessageBox.information(self, "INU: Validate Ped",
                                                  "Ped hierarchy OK")
