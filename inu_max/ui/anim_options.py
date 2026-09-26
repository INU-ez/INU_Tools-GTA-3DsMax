# INU Tools (Max) — опции окон выбора файлов и диалоги окна «IFP IO»: как
# сайдбары файлового браузера и props-диалоги операторов Blender-версии INU
# (Export IFP, Merge Into IFP, Batch Import, камера катсцены, жест
# ghands.ifp, Export Animated Object, Add Pivot). Значения — в settings.

import os

from PySide6 import QtWidgets

from .style import C
from .widgets import BuildMixin, Rollout, FusedBlock, IconLabel, PropsDialog

IFP_FILTERS = [("GTA IFP (*.ifp)", ["*.ifp"]), ("All Files (*.*)", ["*"])]
CAMERA_FILTERS = [("GTA cutscene camera (*.dat)", ["*.dat"]),
                  ("All Files (*.*)", ["*"])]

_ANPK = ("ANPK / ANP2 (III, VC, SA)", 'ANPK',
         "Chunked float32 — III, VC, also loaded by SA")
_ANP3 = ("ANP3 (SA compressed)", 'ANP3',
         "Flat int16-compressed — native GTA SA format, smallest file size")
_FORMAT_TIP = ("On-disk IFP encoding. ANP3 — compact GTA SA format (int16). "
               "ANPK / ANP2 — chunked float32 (GTA III, VC, also loadable in SA)")
_DECIMATE_TIP = ("Drop keyframes that lie on a linear interpolation between "
                 "neighbours. Reduces .ifp size without quality loss — first "
                 "and last keyframe of every bone are always preserved")
_ROT_TOL_TIP = ("Max-norm tolerance on XYZW quaternion. 1e-3 is safe — ANP3 "
                "quantises rotation at 1/4096 ≈ 2.4e-4, going below that "
                "brings no benefit")
_TRANS_TOL_TIP = ("Max-norm tolerance on XYZ translation in DFF units "
                  "(usually metres). 1e-3 ≈ 1 mm — invisible at typical scene "
                  "scales")


def default_format(game):
    """Формат IFP по игре — как invoke экспорта INU: ANP3 для SA."""
    return 'ANP3' if game == 'SA' else 'ANPK'


class _Options(BuildMixin, QtWidgets.QWidget):
    """Основа сайдбара окна выбора файлов: роллаут с опциями."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        r = Rollout(title, opened=True)
        lay.addWidget(r)
        lay.addStretch(1)
        self.body = r.body

    def _decimate(self, prefix):
        """«Decimate keyframes» + допуски (видны, когда включено)."""
        g = self._group("Keyframes")
        tol = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(tol)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(3)
        vl.addLayout(self._labeled("Rotation tol.", self._dspin(
            prefix + 'tol_rot', 0.0, 1.0, 0.001, 5, 0.0001, _ROT_TOL_TIP), 70))
        vl.addLayout(self._labeled("Position tol.", self._dspin(
            prefix + 'tol_trans', 0.0, 1.0, 0.001, 5, 0.0001, _TRANS_TOL_TIP), 70))
        g.addWidget(self._check(
            "Decimate keyframes", prefix + 'decimate', False, _DECIMATE_TIP,
            lambda: tol.setVisible(bool(self._get(prefix + 'decimate', False)))))
        g.addWidget(tol)
        tol.setVisible(bool(self._get(prefix + 'decimate', False)))
        return g.box


class IfpExportOptions(_Options):
    """Сайдбар «Export IFP» INU: пакет, только активная, формат, прореживание."""

    def __init__(self, parent=None):
        super().__init__("Export IFP", parent)
        g = self._group("IFP")
        g.addLayout(self._labeled("Package", self._line(
            'ifp_package', "custom", "IFP package name (written into the file)")))
        g.addWidget(self._check(
            "Active animation only", 'ifp_active_only', False,
            "Export ONLY the skeleton's current animation — a single animation, "
            "not the whole pack. By default export gathers every imported "
            "animation plus the current one; with this on, exactly the current "
            "one, whether it's your new animation OR an existing one from an "
            "imported ped.ifp."))
        g.addLayout(self._labeled("Format", self._combo(
            'ifp_format', [_ANPK, _ANP3], 'ANP3', _FORMAT_TIP)))
        self.body.addWidget(g.box)
        self.body.addWidget(self._decimate('ifp_'))


class IfpMergeOptions(_Options):
    """Сайдбар «Merge Into IFP» INU (кнопка Add)."""

    def __init__(self, parent=None):
        super().__init__("Add to IFP", parent)
        g = self._group("IFP")
        g.addLayout(self._labeled("Package", self._line(
            'merge_package', "keep the file's name",
            "Package name (leave empty to keep the existing file's name)")))
        g.addWidget(self._check(
            "Current animation only", 'merge_current_only', True,
            "Export only the skeleton's current animation. Otherwise — every "
            "imported animation plus the current one"))
        self.body.addWidget(g.box)
        self.body.addWidget(self._decimate('merge_'))
        self.body.addWidget(self._info(
            "Animations with the same name are replaced (case-insensitive), "
            "new ones are appended; the rest of the pack stays intact. A new "
            "file is written as ANPK."))


class IfpBatchOptions(_Options):
    """Сайдбар «Batch Import IFP Folder» INU."""

    def __init__(self, parent=None):
        super().__init__("Batch import", parent)
        g = self._group("Animations")
        g.addLayout(self._labeled("Name Prefix", self._line(
            'batch_prefix', "",
            "Only apply animations whose name starts with this prefix "
            "(case-insensitive)"), 64))
        g.addLayout(self._labeled("Mode", self._combo(
            'batch_mode',
            [("Sequential", 'NLA',
              "Lay clips one after another on one track with a gap between them"),
             ("Animations only", 'ACTIONS',
              "Create animations only, no sequence")],
            'NLA'), 64))
        g.addLayout(self._labeled("Gap", self._dspin(
            'batch_gap', 0.0, 100000.0, 10.0, 1, 1.0,
            "Gap between clips, frames"), 64))
        g.addLayout(self._labeled("Start index", self._spin(
            'batch_start', 0, 1000000, 0,
            "0-based index of the first animation in the filtered list. Handy "
            "for slicing ped.ifp: run 0..49, then 50..99, instead of dumping "
            "all 294 clips into the scene at once"), 64))
        g.addLayout(self._labeled("Count", self._spin(
            'batch_count', 0, 1000000, 0,
            "Maximum animations to process in this run. 0 = all remaining "
            "after Start index"), 64))
        self.body.addWidget(g.box)
        self.body.addWidget(self._info("Every *.ifp in the folder is read."))


class CameraOptions(_Options):
    """Сайдбар импорта / экспорта камеры катсцены (.dat)."""

    def __init__(self, export=False, parent=None):
        super().__init__("Export camera" if export else "Import camera", parent)
        if export:
            self.body.addWidget(self._check(
                "Z-offset +1.0", 'cam_z_export', True,
                "Add 1.0 back to Z on export (paired with import)"))
            self.body.addWidget(self._info(
                "Scene frame rate must be 30; the camera and its target need "
                "≥2 position keys."))
        else:
            self.body.addWidget(self._check(
                "Z-offset −1.0", 'cam_z_import', True,
                "Engine Z-bug workaround: subtract 1.0 from Z on import (and "
                "add it back on export). As in the original SetCamera"))


class GestureOptions(_Options):
    """Сайдбар «Export gesture → ghands.ifp» INU."""

    def __init__(self, parent=None):
        super().__init__("Export gesture", parent)
        g = self._group("IFP")
        g.addLayout(self._labeled("Format", self._combo(
            'hs_format',
            [("ANP3 (SA compressed)", 'ANP3',
              "Native SA — like vanilla ghands.ifp"), _ANPK],
            'ANP3',
            "ANP3 — native GTA SA format (int16, like vanilla ghands.ifp; read "
            "by the game AND by tools like GTA Anim Manager). ANPK / ANP2 — "
            "chunked float32 (III/VC, also read by SA)")))
        self.body.addWidget(g.box)
        self.body.addWidget(self._decimate('hs_'))
        self.body.addWidget(self._info(
            "Blocks with the same name are replaced, the vanilla ones stay "
            "byte-for-byte."))


# ── props-диалоги (invoke_props_dialog INU) ──────────────────────────

class _PropsDialog(BuildMixin, PropsDialog):
    """Диалог с полями, привязанными к settings."""


class AnimObjExportDialog(_PropsDialog):
    """«DFF+IFP+IDE» — диалог Export Animated Object INU. anim — имя
    анимации первого pivot'а ('' — нет pivot'ов), n_pivots — их число."""

    def __init__(self, parent, anim, n_pivots):
        super().__init__(parent, "INU: Export Animated Object", 400)
        f = self.form
        if anim:
            f.addWidget(IconLabel("Animation: %s" % anim
                                  + ("  (%d pivots)" % n_pivots
                                     if n_pivots > 1 else ""), 'action'))
        else:
            f.addWidget(IconLabel("No animated pivots — IFP would be empty",
                                  'error', icon_color=C['err']))
        L = 84
        f.addLayout(self._labeled("Folder", self._path_field(
            'ao_directory', 'folder', title="INU: Folder for .dff and .ifp",
            tip="Where to put .dff and .ifp"), L))
        f.addLayout(self._labeled("Base name", self._line(
            'ao_base_name', "mill", "File name without extension (e.g. 'mill')"), L))
        f.addLayout(self._labeled("TXD", self._line(
            'ao_txd_name', "mill",
            "TXD name for the IDE entry (usually matches Base name)"), L))
        f.addLayout(self._labeled("Model ID", self._spin(
            'ao_model_id', 0, 65535, 18000,
            "Model ID for the IDE — must be free in the map.\n0 = not set (fix "
            "it in Map IO → Object IDE / IPL → Model ID)"), L))
        self._id_warn = IconLabel(
            "Model ID = 0 — set it in Map IO → Object IDE / IPL → Model ID",
            'error', wrap=True, icon_color=C['err'])
        f.addWidget(self._id_warn)
        f.addLayout(self._labeled("Draw distance", self._dspin(
            'ao_draw_distance', 10.0, 100000.0, 300.0, 1, 10.0), L))

        g = self._group("IFP file")
        g.addLayout(self._labeled("Append to file", self._path_field(
            'ao_existing_ifp', 'open', IFP_FILTERS, "INU: IFP to append to",
            tip="A specific .ifp file to append the animation to. When set, "
                "Folder and Name are ignored and the animation is written "
                "HERE. Handy for merging into <game>/anim/myhood.ifp or other "
                "shared files outside the DFF export folder"), L))
        self._w_name = QtWidgets.QWidget()
        self._w_name.setLayout(self._labeled("Name", self._line(
            'ao_ifp_name', "", "Base name for the .ifp (without extension). "
            "Empty = take Base name. You can enter a shared name like "
            "'myhood_anims' to keep the windmill, crane and weather vane "
            "animations in one file"), L))
        g.addWidget(self._w_name)
        self._arrow = IconLabel("", 'text')
        g.addWidget(self._arrow)
        g.addLayout(self._labeled("Mode", self._combo(
            'ao_ifp_mode',
            [("New", 'NEW', "Overwrite the file — old animations are removed"),
             ("Append", 'APPEND', "Load the existing file, add new animations, "
              "replace ones with the same name"),
             ("Refresh matches", 'UPDATE', "Load the existing file, replace "
              "ONLY animations with a matching name, do NOT add new ones")],
            'APPEND', "What to do if this .ifp already exists on disk"), L))
        g.addLayout(self._labeled("IFP format", self._combo(
            'ao_ifp_format', [_ANPK[:2] + (None,), _ANP3[:2] + (None,)],
            'ANPK'), L))
        f.addWidget(g.box)
        f.addWidget(self._check(
            "Append IDE entry", 'ao_write_ide', True,
            "Add the anim entry to the IDE file set in Map IO (Export → IDE)",
            self._refresh))
        self._ide = IconLabel("", 'text', wrap=True)
        f.addWidget(self._ide)
        # подписи «→ имя.ifp» и предупреждение Model ID — по ходу ввода
        for w in self.findChildren(QtWidgets.QLineEdit) + \
                self.findChildren(QtWidgets.QSpinBox):
            sig = w.textChanged if isinstance(w, QtWidgets.QLineEdit) \
                else w.valueChanged
            sig.connect(lambda *_a: self._refresh())
        self._refresh()

    def _refresh(self):
        g = self._get
        self._id_warn.setVisible(int(g('ao_model_id', 18000)) == 0)
        existing = str(g('ao_existing_ifp', '') or '')
        self._w_name.setVisible(not existing)
        if existing:
            self._arrow.setText("→ %s" % os.path.basename(existing))
        else:
            name = g('ao_ifp_name', '') or g('ao_base_name', '') or "<empty>"
            self._arrow.setText("→ %s.ifp" % name)
        write = bool(g('ao_write_ide', True))
        self._ide.setVisible(write)
        ide = str(g('ide_path', '') or '')
        if ide:
            self._ide.setText("IDE: %s" % ide)
            self._ide.setIcon('text')
        else:
            self._ide.setText("The IDE path is not set (Map IO → Export → IDE) "
                              "— the anim entry will not be written")
            self._ide.setIcon('error', C['err'])


class AddPivotDialog(_PropsDialog):
    """«+Pivot» — диалог Add Pivot to Empty Rig INU."""

    def __init__(self, parent):
        super().__init__(parent, "INU: Add Pivot to Empty Rig", 360)
        f = self.form
        L = 100
        f.addLayout(self._labeled("Pivot name", self._line(
            'pv_name', "pivot2", "Suffix for the new Empty: <rig>_<name>. The "
            "animation name is taken the same"), L))
        axis, self._axis_group = self._seg_buttons(
            [("X", 'X'), ("Y", 'Y'), ("Z", 'Z')], self._get('pv_axis', 'Z'),
            lambda d: self._set('pv_axis', d), "Rotation axis")
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(2, 0, 0, 0)
        row.setSpacing(4)
        lab = QtWidgets.QLabel("Rotation axis")
        lab.setFixedWidth(L)
        row.addWidget(lab)
        row.addWidget(FusedBlock([axis]), 1)
        f.addLayout(row)
        f.addLayout(self._labeled("Turns per cycle", self._spin(
            'pv_turns', 1, 1000, 1), L))
        f.addLayout(self._labeled("Duration (frames)", self._spin(
            'pv_duration', 2, 100000, 60), L))
        f.addWidget(self._check(
            "Parent active mesh", 'pv_parent_mesh', True,
            "Immediately hang the active mesh under the new pivot"))
