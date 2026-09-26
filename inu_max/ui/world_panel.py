# INU Tools (Max) — окна «Water IO», «Zones», «Paths», «X Radar»: панели
# Blender-версии INU «Water», «map.zon», «Пути», «X Radar Maker».
#
# Работает: map.zon целиком (импорт боксами, экспорт с .bak и исходными
# строками, новая зона, строки в буфер обмена, счётчик, правка параметров);
# вода — Add Water, Apply параметров на выделенные, сведения об активной
# воде; пути — атрибуты sapath_*, выделение Peds / Vehs / All, Pick / Apply /
# Bulk, сведения о пути. Остальное — окна с опциями INU и заглушки: импорт /
# экспорт воды (нужны данные на вершинах), инструменты воды, файлы путей,
# рендер радара.

import os

from PySide6 import QtWidgets, QtCore

from .style import BTN_H, icon, SEVERITY_COLOR
from .widgets import (BuildMixin, FusedBlock, IconLabel, NumEdit, IntEdit,
                      PropsDialog)

_ERR = SEVERITY_COLOR['ERROR']


def _world():
    from ..adapter import world
    return world


def _zon():
    from ..adapter import zon
    return zon


def _safe(fn, default=None):
    """Запрос к сцене; вне Max (нет pymxs) или при ошибке — default."""
    try:
        return fn()
    except Exception as e:                             # noqa: BLE001
        if 'pymxs' not in str(e):
            print("[INU] world: %r" % (e,))
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


class _Tool(BuildMixin, QtWidgets.QWidget):
    """Основа окна: заглушки кнопок и окно выбора файлов."""

    def __init__(self, dispatch, parent=None):
        super().__init__(parent)
        self._dispatch = dispatch
        self._node = None

    def _stub(self, label, key):
        return lambda: self._dispatch(label, key)

    def _file(self, title, mode, filters, key, accept, filename='', options=None,
              start=None, confirm=True):
        from .file_dialog import INUFileDialog
        dlg = INUFileDialog(self, title, mode=mode, filters=filters, key=key,
                            accept_label=accept, options=options,
                            filename=filename, start_dir=start,
                            confirm_overwrite=confirm)
        if not dlg.exec():
            return None
        if mode == 'folder':
            return dlg.selected_folder()
        if mode == 'save':
            return dlg.save_path()
        files = dlg.selected_files()
        return files if mode == 'open_multi' else (files[0] if files else None)

    def _not_yet(self, what, path=''):
        QtWidgets.QMessageBox.information(
            self, "INU Tools", "%s is not implemented yet.%s"
            % (what, ("\n\n" + path) if path else ""))

    def _report(self, msg, err=False):
        if err:
            QtWidgets.QMessageBox.warning(self, "INU Tools", msg)
        else:
            print("[INU] %s" % msg)


_DAT = [("GTA data (*.dat)", ["*.dat"]), ("All Files (*.*)", ["*"])]


# ═════════════════════ Water ════════════════════════════════════════

class WaterTools(_Tool):
    """Панель INU «Water»: Import / Export + Add Water, параметры воды,
    инструменты, сведения об активном водном меше."""

    def __init__(self, dispatch, parent=None):
        super().__init__(dispatch, parent)
        lay = _vbox(self)
        stub = self._stub
        lay.addWidget(FusedBlock([
            [_btn("Import", self._import, "Import water.dat", 'import'),
             _btn("Export", self._export, "Export water.dat", 'export')],
            [_btn("Add Water", self._add,
                  "Create a water polygon with GTA SA parameters: a 500×500 "
                  "quad snapped to the water block grid (otherwise water "
                  "renders untextured)", 'add')]]))

        pb = self._box()
        pb.addWidget(IconLabel("Water Parameters:", 'edit'))
        flag = self._combo('water_flag', [
            ("Default / Invisible", '0', "Deep water, not rendered"),
            ("Default / Visible", '1', "Deep water with waves"),
            ("Shallow / Invisible", '2', "Shallow water, not rendered"),
            ("Shallow / Visible", '3', "Shallow water, rendered")], '1',
            "Water polygon visibility and depth type")
        pb.addWidget(flag)
        pb.addWidget(QtWidgets.QLabel("Flow Speed:"))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(1)
        for axis, dflt in (('x', 0.0), ('y', 0.0), ('z', 0.05)):
            row.addWidget(self._num('water_speed_' + axis, dflt,
                                    NumEdit(3, -5.0, 5.0, 0.01, axis.upper() + ": ",
                                            "Speed " + axis.upper())), 1)
        pb.addLayout(row)
        pb.addWidget(self._num('water_wave_height', 0.1, NumEdit(
            3, 0.0, 10.0, 0.05, "Waves: ", "Wave Height")))
        pb.addWidget(FusedBlock([[_btn("Apply", self._apply,
                                       "Set water parameters on selected objects",
                                       'check')]]))
        lay.addWidget(pb.box)

        tb = self._box()
        tb.addWidget(IconLabel("Tools:", 'edit'))
        self._limits = _btn("Show Limits (500)", stub("Show Limits (500)",
                                                      "toggle_water_limits"),
                            "Show the 500×500 water block grid and highlight "
                            "faces: green — fits, orange — on the border, red — "
                            "larger than 500.", 'eye')
        tb.addWidget(FusedBlock([
            [_btn("Snap to Grid (x4)", stub("Snap to Grid (x4)", "water_snap_grid"),
                  "Snap water vertices to multiples of 4 (GTA SA requirement)")],
            [_btn("Snap to Block (500)", stub("Snap to Block (500)",
                                              "water_snap_block"),
                  "Snap water vertices to the nearest node of the limit grid "
                  "(multiples of 500 — GTA SA water block corners).")],
            [_btn("Split by Blocks (500)", stub("Split by Blocks (500)",
                                                "water_split_blocks"),
                  "Cut water along the 500×500 block grid so every face sits "
                  "inside a single block (otherwise water renders untextured)")],
            [_btn("Stitch Edges", stub("Stitch Edges", "water_stitch"),
                  "Stitch the edges of two water planes (align nearest vertices)")],
            [self._limits]]))
        lay.addWidget(tb.box)

        ib = self._box()
        self._info = IconLabel("", 'info', wrap=True)
        ib.addWidget(self._info)
        self._info_box = ib.box
        lay.addWidget(ib.box)
        self.on_selection(None)

    def _num(self, key, default, w):
        w.setValue(float(self._get(key, default)))
        w.valueChanged.connect(lambda v, k=key: self._set(k, float(v)))
        return w

    def on_selection(self, snap):
        node = self._node = snap.get('node') if snap else None
        w = _world()
        flag = _safe(lambda: w.water_flag(node)) if node is not None else None
        self._info_box.setVisible(flag is not None)
        if flag is not None:
            self._info.setText("%s: %s (flag=%d)" % (
                node.name, w.WATER_FLAGS.get(flag, "?"), flag))

    def _import(self):
        path = self._file("INU: Import Water", 'open', _DAT, 'water', "Import")
        if path:
            self._not_yet("Water import", path)

    def _export(self):
        path = self._file("INU: Export Water", 'save', _DAT, 'water', "Export",
                          "water.dat")
        if path:
            self._not_yet("Water export", path)

    def _add(self):
        node = _safe(lambda: _world().add_water())
        if node is not None:
            self._report("Water plane created (500x500): %s" % node.name)

    def _apply(self):
        g = self._get
        n = _safe(lambda: _world().set_water_params(
            g('water_flag', '1'), g('water_speed_x', 0.0), g('water_speed_y', 0.0),
            g('water_speed_z', 0.05), g('water_wave_height', 0.1)), 0) or 0
        self._report("Water Parameters: %d objects" % n)
        self.on_selection({'node': self._node})


# ═════════════════════ map.zon ══════════════════════════════════════

_ZON = [("GTA zones (*.zon)", ["*.zon"]), ("All Files (*.*)", ["*"])]


class ZonTools(_Tool):
    """Панель INU «map.zon»: файл, Import / Export, New zone, Lines to
    clipboard, число зон, параметры активного бокса."""

    def __init__(self, dispatch, refresh, parent=None):
        super().__init__(dispatch, parent)
        self._refresh_sel = refresh
        lay = _vbox(self)
        self._pf = self._path_field(
            'zon_path', 'open', _ZON, "INU: Zone file",
            "data/map.zon or data/info.zon",
            "Path to the zone file (data/map.zon or data/info.zon)")
        lay.addWidget(self._pf)
        self._lines = _btn(
            "Lines to clipboard", self._copy_lines,
            "Generate zone lines for the selected objects and put them on the "
            "clipboard — paste them straight into map.zon. For an ordinary "
            "mesh the zone is computed from its bounds.", 'paste')
        lay.addWidget(FusedBlock([
            [_btn("Import", self._import,
                  "Import zones from map.zon / info.zon — each zone becomes a "
                  "box frame in the scene. Re-importing the same file replaces "
                  "the old boxes.", 'import'),
             _btn("Export", self._export,
                  "Export zones back to map.zon / info.zon. The selected boxes "
                  "are written, and if nothing is selected — the whole "
                  "ZON_<filename> layer. Untouched zones are preserved line by "
                  "line, the old file is copied next to it as .bak.", 'export')],
            [_btn("New zone", self._add,
                  "Create a new zone — a 100×100×100 box at the selection. The "
                  "name, type, level and GXT key are edited below.", 'add')],
            [self._lines]]))
        self._count = IconLabel("", 'info')
        lay.addWidget(self._count)
        self._hint = IconLabel("Select a zone box to edit its parameters", 'info',
                               wrap=True)
        lay.addWidget(self._hint)

        b = self._box()
        self._name_lb = IconLabel("", 'mesh')
        b.addWidget(self._name_lb)
        self._ed = {}
        self._ed['zon_name'] = QtWidgets.QLineEdit()
        self._ed['zon_type'] = IntEdit(0, 255, "Type: ")
        self._type_lb = QtWidgets.QLabel()
        self._ed['zon_level'] = IntEdit(0, 255, "Level: ",
                                        "Island / region id: 0 generic, 1 LS, "
                                        "2 SF, 3 LV")
        self._ed['zon_gxt'] = QtWidgets.QLineEdit()
        self._ed['zon_gxt'].setToolTip("Key of the on-screen zone name, "
                                       "UNUSED when there is none")
        for key, w in self._ed.items():
            if isinstance(w, QtWidgets.QLineEdit):
                w.setFixedHeight(BTN_H)
                w.editingFinished.connect(lambda k=key, e=w: self._edit(k, e.text()))
            else:
                w.valueChanged.connect(lambda v, k=key: self._edit(k, int(v)))
        b.addLayout(self._labeled("Name", self._ed['zon_name'], 40))
        b.addWidget(self._ed['zon_type'])
        b.addWidget(self._type_lb)
        b.addWidget(self._ed['zon_level'])
        b.addLayout(self._labeled("GXT", self._ed['zon_gxt'], 40))
        self._zero = IconLabel("Zero size on one of the axes", 'error',
                               icon_color=_ERR)
        b.addWidget(self._zero)
        self._box_w = b.box
        lay.addWidget(b.box)
        self.on_selection(None)

    def on_selection(self, snap):
        node = self._node = snap.get('node') if snap else None
        z = _zon()
        self._count.setText("Zones in scene: %d" % (_safe(z.zone_count, 0) or 0))
        self._lines.setEnabled(bool(snap and snap.get('sel_names')))
        active = bool(_safe(lambda: z.is_zone(node), False))
        self._hint.setVisible(not active)
        self._box_w.setVisible(active)
        if not active:
            return
        self._name_lb.setText(str(node.name))
        vals = {k: _safe(lambda k=k, d=d: z.get_field(node, k, d), d)
                for k, d in (('zon_name', ''), ('zon_type', 0), ('zon_level', 0),
                             ('zon_gxt', 'UNUSED'))}
        for key, w in self._ed.items():
            w.blockSignals(True)
            if isinstance(w, QtWidgets.QLineEdit):
                w.setText(str(vals[key]))
            else:
                w.setValue(int(vals[key] or 0))
            w.blockSignals(False)
        self._type_lb.setText(z.TYPES.get(int(vals['zon_type'] or 0), "custom type"))
        self._zero.setVisible(bool(_safe(lambda: z.zero_size(node), False)))

    def _edit(self, key, value):
        if self._node is None:
            return
        if key == 'zon_name':
            # имя зоны при экспорте берётся с объекта, если он переименован,
            # поэтому правка поля переименовывает и бокс (Zone_<имя>)
            _safe(lambda: _zon().rename(self._node, value.strip()))
            self._name_lb.setText(str(self._node.name))
            return
        _safe(lambda: _zon().put_field([self._node], key, value))
        if key == 'zon_type':
            self._type_lb.setText(_zon().TYPES.get(int(value), "custom type"))

    def _start(self):
        cur = str(self._get('zon_path', '') or '')
        return (os.path.dirname(cur) if cur else None), os.path.basename(cur)

    def _import(self):
        start, name = self._start()
        path = self._file("INU: Import Zones (.zon)", 'open', _ZON, 'zon',
                          "Import", name, start=start)
        if not path:
            return
        try:
            n, zf = _zon().import_zon(path)
        except Exception as e:                         # noqa: BLE001
            self._report("Read error: %s" % e, True)
            return
        self._pf.edit.setText(path)             # → settings zon_path
        bad = [z.name for z in zf.zones if z.is_reversed]
        msg = "%d zones imported from %s" % (n, os.path.basename(path))
        if bad:
            msg += ("\n\nZones with a reversed bbox (never match in game): %d — %s"
                    % (len(bad), ", ".join(bad[:4]) + ("…" if len(bad) > 4 else "")))
        QtWidgets.QMessageBox.information(self, "INU: Import Zones", msg)
        self._refresh_sel()

    def _export(self):
        start, name = self._start()
        path = self._file("INU: Export Zones (.zon)", 'save', _ZON, 'zon',
                          "Export", name or "map.zon", start=start, confirm=False)
        if not path:
            return
        z = _zon()
        objs, note = _safe(lambda: z.collect_for_export(path), ([], ''))
        if note == 'ambiguous':
            return self._report("The scene has several zone sets — select the "
                                "boxes to write or name the file after a ZON_* "
                                "layer", True)
        if not objs:
            return self._report("No zones to export", True)
        try:
            zf, dups = z.export_zon(path, objs)
        except Exception as e:                         # noqa: BLE001
            return self._report("Write error: %s" % e, True)
        msg = "%d zones written to %s" % (len(zf.zones), path)
        if dups:
            msg += "\n\nDuplicate zone names: %s" % ", ".join(sorted(set(dups))[:4])
        QtWidgets.QMessageBox.information(self, "INU: Export Zones", msg)

    def _add(self):
        box = _safe(lambda: _zon().add_zone(self._get('zon_path', '')))
        if box is not None:
            self._report("Zone created: %s" % box.name)
        self._refresh_sel()

    def _copy_lines(self):
        res = _safe(lambda: _zon().lines_for_selection())
        if not res or not res[0]:
            return self._report("Nothing selected", True)
        lines, n_bbox = res
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))
        msg = "Lines in clipboard: %d" % len(lines)
        if n_bbox:
            msg += "  (by bounds: %d)" % n_bbox
        self._report(msg)
        QtWidgets.QMessageBox.information(self, "INU: Copy zone lines", msg)


# ═════════════════════ Paths ════════════════════════════════════════

_IPL = [("GTA paths (*.ipl)", ["*.ipl"]), ("All Files (*.*)", ["*"])]


class PathTools(_Tool):
    """Панель INU «Пути»: paths.ipl, ж/д пути, NODES, Curve workflow
    (Kam's / ZZPuma), атрибуты кривой, сведения о пути."""

    def __init__(self, dispatch, refresh, parent=None):
        super().__init__(dispatch, parent)
        self._refresh_sel = refresh
        self._clip = {}              # буфер Pick / Apply (sapath_*)
        lay = _vbox(self)
        stub = self._stub
        self._convert = _btn("Convert to Path", stub("Convert to Path",
                                                     "convert_to_path"),
                             "Convert a spline or mesh edges into a paths.ipl path",
                             'forward')
        self._fb_convert = FusedBlock([[self._convert]])
        lay.addWidget(self._fb_convert)

        # paths.ipl
        b = self._box()
        b.addWidget(IconLabel("Paths (paths.ipl):", 'outliner'))
        b.addWidget(FusedBlock([
            [_btn("Import", lambda: self._io("Paths IPL import", 'open', _IPL,
                                             'paths_ipl', "Import"),
                  "Import paths.ipl — paths listed in gta.dat", 'import'),
             _btn("Export", lambda: self._io("Paths IPL export", 'save', _IPL,
                                             'paths_ipl', "Export", "paths.ipl"),
                  "Export paths.ipl — paths listed in gta.dat", 'export')],
            [_btn("Add Path", stub("Add Path", "add_path_ipl"),
                  "Create a new path for paths.ipl (max 12 points)", 'add')]]))
        self._flags = QtWidgets.QWidget()
        fl = _vbox(self._flags)
        fl.addWidget(IconLabel("Flags on selected points:", 'edit'))
        traffic = QtWidgets.QPushButton("Traffic light")
        traffic.setIcon(icon('light'))
        menu = QtWidgets.QMenu(traffic)
        menu.setToolTipsVisible(True)
        for label, key, tip in (
                ("No traffic light", 'TRAFFIC_NONE', "traffic_light=0 on each "
                 "selected point"),
                ("Normal", 'TRAFFIC_NORMAL', "traffic_light=1 on each selected point"),
                ("Railroad", 'TRAFFIC_RAIL', "traffic_light=2 on each selected point"),
                ("Bus", 'TRAFFIC_BUS', "traffic_light=3 on each selected point")):
            act = menu.addAction(label)
            act.setToolTip(tip)
            act.triggered.connect(lambda _c=False, l=label, k=key:
                                  self._dispatch("Traffic light: " + l, k))
        traffic.setMenu(menu)
        fl.addWidget(FusedBlock([
            [_btn("Toggle Roadblock", stub("Toggle Roadblock", "TOGGLE_ROADBLOCK"),
                  "Toggle bit 12 (cop barrier) on each selected point")],
            [traffic]]))
        b.addWidget(self._flags)
        lay.addWidget(b.box)

        # ж/д пути
        b = self._box()
        b.addWidget(IconLabel("Train Tracks:", 'stairs'))
        b.addWidget(FusedBlock([
            [_btn("Import", lambda: self._io("Track import", 'open', _DAT,
                                             'tracks', "Import"),
                  "Import tracks.dat — railway paths", 'import'),
             _btn("Export", lambda: self._io("Track export", 'save', _DAT,
                                             'tracks', "Export", "tracks.dat"),
                  "Export tracks.dat — railway paths", 'export')],
            [_btn("Add Train Track", stub("Add Train Track", "add_track"),
                  "Create a new railway path (spline)", 'add')]]))
        self._station = _btn("Station (toggle)", stub("Station (toggle)",
                                                      "mark_station"),
                             "Toggle the station flag (flag=1) on the selected "
                             "spline points", 'check')
        self._markers = _btn("Refresh Station Markers",
                             stub("Refresh Station Markers",
                                  "refresh_station_markers"),
                             "Recreate the visible markers for every station on "
                             "the active railway path", 'refresh')
        self._track_fb = FusedBlock([[self._station], [self._markers]])
        b.addWidget(self._track_fb)
        lay.addWidget(b.box)

        # NODES
        b = self._box()
        b.addWidget(IconLabel("Compiled (NODES):", 'archive'))
        b.addWidget(FusedBlock([
            [_btn("Import", self._import_nodes,
                  "Import nodes.dat — pedestrian / vehicle paths (multi-select)",
                  'import'),
             _btn("Export", self._export_nodes,
                  "Export nodes.dat — group by filename or auto-split by zones",
                  'export')],
            [_btn("Path geometry", stub("Path geometry", "toggle_nodes_viz"),
                  "Create or hide path visualisation geometry", 'eye')]]))
        lay.addWidget(b.box)

        # Curve workflow (Kam's / ZZPuma)
        b = self._box()
        b.addWidget(IconLabel("Curve workflow (Kams / ZZPuma):", 'curve'))
        self._pick = _btn("Pick", self._pick_props,
                          "Copy sapath_* properties of the active spline into "
                          "the clipboard")
        self._apply = _btn("Apply", self._apply_props,
                           "Apply the previously picked sapath_* properties to "
                           "every selected spline")
        self._bulk = _btn("Bulk", self._bulk_props,
                          "Bulk-set sapath_* properties on all selected splines. "
                          "Options with a -1 / «No change» value keep the "
                          "current value.")
        b.addWidget(FusedBlock([
            [_btn("Mesh → Curves", stub("Mesh → Curves", "nodes_to_curves"),
                  "Split an imported nodes mesh into one spline per lane chain, "
                  "with sapath_* properties from the node flags. The original "
                  "mesh is left untouched."),
             _btn("Curves → .dat", self._curves_to_dat,
                  "Bake the selected splines into nodes*.dat: each spline "
                  "becomes a sequence of path nodes; cross-spline links are "
                  "stitched where knots coincide.")],
            [_btn("Peds", lambda: self._select('PED'),
                  "Select all spline paths of type Ped (sapath_type=1)"),
             _btn("Vehs", lambda: self._select('VEH'),
                  "Select all spline paths of type Vehicle (sapath_type=2)"),
             _btn("All", lambda: self._select('ALL'),
                  "Select every spline path that carries sapath_* properties")],
            [self._pick, self._apply, self._bulk,
             _btn("Colors", stub("Colors", "refresh_path_colors"),
                  "Recolour the wireframe of the selected spline paths "
                  "according to their type/flags")],
            [_btn("+TL/RB/CO", self._add_accessory,
                  "Add a TrafficLight / RoadBlock / Connector / SpecialNode on a "
                  "knot of the selected spline"),
             _btn("Remove", stub("Remove accessory", "remove_path_accessory"),
                  "Remove the selected path accessory objects"),
             _btn("Sync", stub("Sync", "start_accessory_sync"),
                  "Enable background sync of path accessory positions with "
                  "their parent splines")],
            [_btn("Node IDs", stub("Node IDs", "toggle_path_debug"),
                  "Toggle the path debug overlay: NodeID labels on nodes"),
             _btn("Navi IDs", stub("Navi IDs", "toggle_path_debug"),
                  "Toggle the path debug overlay: navi node IDs"),
             _btn("Off", stub("Debug overlay off", "toggle_path_debug"),
                  "Turn the path debug overlay off")]], pad=2))
        # атрибуты активной кривой
        ab = self._box(margins=(4, 3, 4, 4))
        self._attr_lb = IconLabel("", 'edit')
        ab.addWidget(self._attr_lb)
        self._attr_rows = QtWidgets.QVBoxLayout()
        self._attr_rows.setSpacing(1)
        ab.addLayout(self._attr_rows)
        self._attr_box = ab.box
        b.addWidget(ab.box)
        lay.addWidget(b.box)

        ib = self._box()
        self._info = IconLabel("", 'info', wrap=True)
        ib.addWidget(self._info)
        self._info_box = ib.box
        lay.addWidget(ib.box)
        self.on_selection(None)

    # — выделение —
    def on_selection(self, snap):
        node = self._node = snap.get('node') if snap else None
        w = _world()
        ptype = _safe(lambda: w.path_type(node), '') if node is not None else ''
        shape = bool(node is not None and _safe(lambda: w.is_shape(node), False))
        # меш без полигонов (рёбра пути) тоже конвертируется
        mesh_no_faces = bool(node is not None and not shape and _safe(
            lambda: int(node.numfaces) == 0, False))
        self._fb_convert.setVisible((shape or mesh_no_faces) and ptype != 'path_ipl')
        self._flags.setVisible(shape and ptype == 'path_ipl')
        self._track_fb.setVisible(shape and ptype == 'track')
        n_sel = len(snap.get('sel_names', []) or []) if snap else 0
        attrs = _safe(lambda: w.sapath(node), {}) if shape else {}
        self._pick.setEnabled(bool(attrs))
        self._apply.setEnabled(n_sel > 0 and bool(self._clip))
        self._bulk.setEnabled(n_sel > 0)
        self._fill_attrs(node, attrs)
        self._fill_info(node, ptype, shape)

    def _fill_attrs(self, node, attrs):
        while self._attr_rows.count():
            old = self._attr_rows.takeAt(0).widget()
            if old is not None:
                old.setParent(None)             # убрать сразу, не ждать цикла
                old.deleteLater()
        self._attr_box.setVisible(bool(attrs))
        if not attrs:
            return
        self._attr_lb.setText("Attributes: %s" % node.name)
        for key in _world().SAPATH_KEYS:
            if key not in attrs:
                continue
            v = attrs[key]
            label = key.replace('sapath_', '') + ": "
            if isinstance(v, float):
                ed = NumEdit(3, -1e6, 1e6, 0.1, label)
                ed.setValue(v)
            else:
                ed = IntEdit(-1000000, 1000000, label)
                ed.setValue(int(v) if not isinstance(v, str) else 0)
            ed.valueChanged.connect(lambda x, k=key: _safe(
                lambda: _world().apply_sapath({k: x}, [self._node])))
            self._attr_rows.addWidget(ed)

    def _fill_info(self, node, ptype, shape):
        self._info_box.setVisible(bool(ptype))
        if not ptype:
            return
        w = _world()
        label = w.PATH_TYPES.get(ptype, ptype)
        if ptype == 'path_ipl':
            gt = _safe(lambda: w.get_prop(node, 'group_type', 1), 1)
            text = "%s: %s (%d/12 pts)" % (node.name, "Vehicle" if gt == 1
                                           else "Pedestrian",
                                           _safe(lambda: w.knot_count(node), 0))
        elif shape:
            import ast
            raw = _safe(lambda: w.get_field(node, 'station_indices', '[]'), '[]')
            try:
                n_st = len(ast.literal_eval(str(raw)))
            except (ValueError, SyntaxError):
                n_st = 0
            text = "%s: %s (%d pts, %d stations)" % (
                node.name, label, _safe(lambda: w.knot_count(node), 0), n_st)
        else:
            text = "%s: %s (%d nodes)" % (node.name, label,
                                          _safe(lambda: w.vert_count(node), 0))
        self._info.setText(text)

    # — действия —
    def _io(self, what, mode, filters, key, accept, filename=''):
        path = self._file("INU: " + what, mode, filters, key, accept, filename)
        if path:
            self._not_yet(what, path if isinstance(path, str) else "\n".join(path))

    def _import_nodes(self):
        paths = self._file("INU: Import Path Nodes", 'open_multi', _DAT, 'nodes',
                           "Import")
        if paths:
            self._not_yet("Nodes import", "\n".join(paths))

    def _export_nodes(self):
        opts = _Opts("Export nodes")
        opts.body.addWidget(opts._check(
            "FLA4 Format", 'nodes_fla4', False,
            "Write nodes*.dat in the extended FLA4 format (spawn/speed/lanes "
            "per-node)"))
        folder = self._file("INU: Export Path Nodes", 'folder', None, 'nodes',
                            "Export", options=opts)
        if folder:
            self._not_yet("Nodes export", folder)

    def _curves_to_dat(self):
        opts = _Opts("Curves → .dat")
        opts.body.addWidget(opts._check(
            "FLA4", 'curves_fla4', False,
            "Write in the extended FLA4 format (for Fastman92 limit adjuster)"))
        opts.body.addLayout(opts._labeled("Path set", opts._combo(
            'curves_path_set', [("64 (Vanilla)", '64', None), ("256", '256', None),
                                ("1024", '1024', None), ("4096", '4096', None),
                                ("16384", '16384', None), ("65536", '65536', None)],
            '64', "Region grid size. 64 = vanilla SA. Larger values need the "
            "Fastman92 limit adjuster (FLA4)"), 56))
        opts.body.addWidget(opts._check(
            "Write entire map", 'curves_entire_map', False,
            "Create empty nodes*.dat for every region of the path set, not only "
            "those with splines. Vanilla SA needs all 64 files"))
        path = self._file("INU: Curves → nodes*.dat", 'save', _DAT, 'nodes',
                          "Export", "NODES0.DAT", options=opts)
        if path:
            self._not_yet("Curves → nodes*.dat", path)

    def _select(self, kind):
        n = _safe(lambda: _world().select_nodes(_world().path_shapes(kind)), 0)
        self._report("%s spline(s) selected" % n)
        self._refresh_sel()

    def _pick_props(self):
        self._clip = dict(_safe(lambda: _world().sapath(self._node), {}) or {})
        self._report("Props copied: %d" % len(self._clip))
        self._apply.setEnabled(bool(self._clip))

    def _apply_props(self):
        if not self._clip:
            return self._report("The clipboard is empty — Pick on the source "
                                "spline first", True)
        n = _safe(lambda: _world().apply_sapath(self._clip), 0)
        self._report("Props applied to %s spline(s)" % n)
        self._refresh_sel()

    def _bulk_props(self):
        dlg = _BulkDialog(self)
        if not dlg.exec():
            return
        g = self._get
        vals = {}
        for key, prop in (('bulk_type', 'sapath_type'),
                          ('bulk_traffic', 'sapath_traffic'),
                          ('bulk_highway', 'sapath_highway'),
                          ('bulk_boats', 'sapath_boats'),
                          ('bulk_parking', 'sapath_parking')):
            v = g(key, 'NONE')
            if v != 'NONE':
                vals[prop] = int(v)
        for key, prop in (('bulk_spawn', 'sapath_spawn'),
                          ('bulk_width', 'sapath_width')):
            v = float(g(key, -1.0))
            if v >= 0:
                vals[prop] = v
        n = _safe(lambda: _world().apply_sapath(vals), 0) if vals else 0
        self._report("Bulk-set applied to %s spline(s)" % n)
        self._refresh_sel()

    def _add_accessory(self):
        dlg = PropsDialog(self, "INU: Add Path Accessory", 300)
        b = BuildMixin()
        dlg.form.addLayout(b._labeled("Type", b._combo(
            'acc_type', [("TrafficLight", 'TL', "Traffic light: spawns on the "
                          "segment between knot and knot+1"),
                         ("RoadBlock", 'RB', "Cop roadblock on the knot itself"),
                         ("Connector", 'CO', "Connector node (for inter-region "
                          "FLA4 paths)"),
                         ("SpecialNode", 'SP', "Generic marker for special "
                          "logic")], 'TL'), 64))
        dlg.form.addLayout(b._labeled("Knot index", b._spin(
            'acc_knot', 0, 100000, 0, "Index of the knot on the parent spline "
            "(0-based)"), 64))
        if dlg.exec():
            self._dispatch("Add Path Accessory", "add_path_accessory")


class _Opts(BuildMixin, QtWidgets.QWidget):
    """Сайдбар опций окна выбора файлов (как у операторов INU)."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        from .widgets import Rollout
        lay = _vbox(self)
        r = Rollout(title, opened=True)
        lay.addWidget(r)
        lay.addStretch(1)
        self.body = r.body


class _BulkDialog(BuildMixin, PropsDialog):
    """«Bulk» — диалог bulk_set_path_props INU."""

    def __init__(self, parent):
        super().__init__(parent, "INU: Bulk Set Path Props", 320)
        keep = [("No change", 'NONE', None)]
        yes_no = keep + [("No", '0', None), ("Yes", '1', None)]
        f = self.form
        for label, key, items in (
                ("Type", 'bulk_type', keep + [("Ped", '1', None),
                                              ("Vehicle", '2', None)]),
                ("Traffic", 'bulk_traffic', keep + [("Enabled", '1', None),
                                                    ("Disabled", '2', None)])):
            f.addLayout(self._labeled(label, self._combo(key, items, 'NONE'), 70))
        f.addWidget(self._dspin('bulk_spawn', -1.0, 1.0, -1.0, 2, 0.1,
                                "Spawn probability 0.0-1.0. Enter -1 to keep",
                                prefix="Spawn rate: "))
        f.addWidget(self._dspin('bulk_width', -1.0, 100.0, -1.0, 2, 0.5,
                                "Path width. Enter -1 to keep", prefix="Width: "))
        for label, key in (("Highway", 'bulk_highway'), ("Boats", 'bulk_boats'),
                           ("Parking", 'bulk_parking')):
            f.addLayout(self._labeled(label, self._combo(key, yes_no, 'NONE'), 70))


# ═════════════════════ X Radar Maker ════════════════════════════════

class RadarTools(_Tool):
    """Панель INU «X Radar Maker»: папка, сетка, размер, высота, индексы,
    Generate (5 режимов), Pack to TXD."""

    def __init__(self, dispatch, parent=None):
        super().__init__(dispatch, parent)
        lay = _vbox(self)
        lay.addLayout(self._labeled("Folder", self._path_field(
            'radar_output', 'folder', title="INU: Radar output folder",
            tip="Folder for saving radar tiles"), 40))
        lay.addWidget(self._int('radar_grid', 8, IntEdit(
            1, 16, "Grid: ", "Grid size (8 = 64 tiles)")))
        lay.addWidget(self._int('radar_size', 256, IntEdit(
            64, 4096, "Size: ", "Tile size in pixels")))
        h = NumEdit(1, 100.0, 1e6, 100.0, "Height: ", "Camera height")
        h.setValue(float(self._get('radar_height', 3000.0)))
        h.valueChanged.connect(lambda v: self._set('radar_height', float(v)))
        lay.addWidget(h)
        lay.addSpacing(4)
        lay.addLayout(self._labeled("Indices", self._line(
            'radar_specific', "0,1,5,63",
            "Tile indices comma-separated (0,1,5,63)"), 40))
        gen = QtWidgets.QPushButton("Generate")
        gen.setIcon(icon('image'))
        gen.setToolTip("Generate GTA SA radar tiles")
        menu = QtWidgets.QMenu(gen)
        for item in (("Generate Radar", 'ALL'), ("Radar menu (3x3)", 'MENU'),
                     None, ("Full Radar", 'FULL'), ("Full Menu", 'FULL_MENU'),
                     None, ("Specified tiles", 'SPECIFIC')):
            if item is None:
                menu.addSeparator()
                continue
            label, mode = item
            menu.addAction(label).triggered.connect(
                lambda _c=False, l=label, m=mode: self._generate(l, m))
        gen.setMenu(menu)
        lay.addWidget(FusedBlock([[gen]], height=BTN_H + 4))
        lay.addSpacing(4)
        lay.addWidget(FusedBlock([[_btn(
            "Pack to TXD", self._pack,
            "Pack radar tiles into TXD archives (1 tile = 1 TXD)", 'archive')]]))

    def _int(self, key, default, w):
        w.setValue(int(self._get(key, default)))
        w.valueChanged.connect(lambda v, k=key: self._set(k, int(v)))
        return w

    def _generate(self, label, mode):
        if mode == 'SPECIFIC' and not str(self._get('radar_specific', '')).strip():
            return self._report("Enter tile indices (e.g. 0,1,8,9)", True)
        if not str(self._get('radar_output', '') or '').strip():
            return self._report("Set the output folder", True)
        self._dispatch(label, "radar_generate")

    def _pack(self):
        if not str(self._get('radar_output', '') or '').strip():
            return self._report("Set the output folder", True)
        self._dispatch("Pack to TXD", "radar_pack_txd")
