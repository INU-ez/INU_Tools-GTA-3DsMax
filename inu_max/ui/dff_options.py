# INU Tools (Max) — опции импорта/экспорта DFF (как в Blender-версии INU).
#
# ImportOptions / ExportOptions — боковые панели окна выбора файлов (как
# сайдбар файлового браузера Blender в диалогах «Импорт» и «Export All»).
# FlagsBox и pipeline_buttons — общие для окна DFF IO и панели экспорта.
# Оформление — роллауты и группы Kam's (widgets.py).

from PySide6 import QtWidgets, QtCore

from .style import C
from .widgets import BuildMixin, Rollout, ElideLabel, FusedBlock

# Pipeline экспорта DFF — как gtatools_export_pipeline в INU.
PIPELINES = [
    ("None", 'NONE', "No pipeline"),
    ("Vehicle", '0x53F2009A', "Vehicle body pipeline"),
    ("Day/Night", '0x53F20098', "Building pipeline with day/night vertex colors"),
    ("Building", '0x53F2009C', "Plain building pipeline"),
    ("Ped", 'PED', "Character preset: pipeline ID = 0, Skin PLG required, "
                   "MatFX and day/night vertex colors off. For skinned peds."),
]
# Флаги, которые НЕ подходят выбранному pipeline: строка красная (как
# row.alert в INU) независимо от того, включён ли флаг.
PIPE_FORBIDDEN = {
    '0x53F2009A': {'day_cols', 'night_cols', 'light_beam_asi'},
    '0x53F20098': {'uv_map2', 'light', 'export_normals',
                   'set_material_alpha', 'light_beam_asi'},
    '0x53F2009C': {'night_cols', 'uv_map2', 'light_beam_asi'},
    'PED': {'day_cols', 'night_cols', 'modulate_color',
            'set_material_alpha', 'light_beam_asi', 'uv_map2'},
}
# DFF-флаги объекта (obj.inu.* в INU): ключ → (подпись, подсказка).
FLAG_UI = {
    'export_normals': ("Normals",
        "Write vertex normals into the DFF. On for skinned objects (peds, "
        "vehicles) and anything that must react to dynamic lighting. Off for "
        "map objects: they are lit by vertex prelight, normals only double "
        "the vertex stream."),
    'light': ("Light",
        "rpGEOMETRYLIGHT: geometry receives dynamic engine lighting (sun + "
        "ambient). Without it the mesh renders unlit (prelight × material "
        "color only): signs, windows with baked glow."),
    'modulate_color': ("Modulate Color",
        "rpGEOMETRYMODULATEMATERIALCOLOR: prelight is multiplied by the "
        "material color and ambient at runtime. Off to use prelight as-is "
        "(baked night lighting, prelight flicker). Vanilla buildings: on."),
    'set_material_alpha': ("Set Material Alpha",
        "Set material alpha to 254 when any vertex alpha is below 255, so the "
        "engine treats the mesh as alpha-blended (glass, smoke, foliage)."),
    'light_beam_asi': ("Light Beam (SA_Light.asi)", ""),
    'uv_map1': ("UV1",
        "Export the first UV map (main texture coordinates). Almost always "
        "on."),
    'uv_map2': ("UV2",
        "Export the second UV map (lightmaps, dual-pass materials). Safe to "
        "leave on: no extra chunk if the mesh has no second UV map."),
    'day_cols': ("Day",
        "Export day vertex colors (vanilla prelight, multiplied by ambient at "
        "runtime)."),
    'night_cols': ("Night",
        "Export night vertex colors (RpExtraVertColors); the game blends them "
        "in at night via timecyc. Night vertex colors break UV animation in "
        "retail SA."),
}

_IMPORT_FORMATS = ('dff', 'col', 'cst', 'txd', 'ide', 'ipl')


def _selection():
    """Модуль выделения сцены (адаптер Max); вне Max его функции бросают."""
    from ..adapter import selection
    return selection


def selection_snapshot():
    """(сводка выделения, первый выделенный меш) или (None, None) вне Max."""
    try:
        sel = _selection()
        meshes = sel.selected_meshes()
        return sel.summary(), (meshes[0] if meshes else None)
    except Exception:                                  # noqa: BLE001
        return None, None


def pipeline_buttons(owner, on_change=None):
    """Кнопки pipeline как в INU (None | Vehicle | Day/Night | Building |
    Ped) — для слитого блока FusedBlock(..., pad=3). Возвращает (кнопки,
    QButtonGroup)."""
    def _changed(d):
        owner._set('export_pipeline', d)
        if on_change is not None:
            on_change()
    return owner._seg_buttons(
        PIPELINES, owner._get('export_pipeline', 'NONE'), _changed)


class FlagsBox(BuildMixin, QtWidgets.QWidget):
    """DFF-флаги активного объекта (obj.inu.* в INU): чекбоксы + подсказка,
    если меш не выделен. Правка флага пишется на все выделенные меши;
    флаги, чуждые выбранному pipeline, — красным; Light Beam и Night —
    только для SA."""

    _ROWS = (('export_normals', 'light'), ('modulate_color',),
             ('set_material_alpha',), ('light_beam_asi',),
             ('uv_map1', 'uv_map2'), ('day_cols', 'night_cols'))

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._grid_w = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(self._grid_w)
        grid.setContentsMargins(2, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        self.cb = {}
        for r, keys in enumerate(self._ROWS):
            for c, key in enumerate(keys):
                label, tip = FLAG_UI[key]
                box = QtWidgets.QCheckBox(label)
                box.setToolTip(tip)
                box.toggled.connect(lambda v, k=key: self._on_flag(k, v))
                self.cb[key] = box
                grid.addWidget(box, r, c, 1, 2 if len(keys) == 1 else 1)
        lay.addWidget(self._grid_w)
        self.hint = self._info("Select a mesh object to edit DFF flags")
        lay.addWidget(self.hint)
        self.refresh()
        self.load(None)

    def load(self, obj):
        """Показать флаги объекта (или умолчания, если меш не выделен)."""
        has = obj is not None
        self._grid_w.setEnabled(has)
        self.hint.setVisible(not has)
        try:
            sel = _selection()
            vals = sel.get_flags(obj) if has else dict(sel.FLAG_DEFAULTS)
        except Exception as e:                         # noqa: BLE001
            if has:
                print("[INU] read DFF flags: %r" % (e,))
            vals = {}
        for key, box in self.cb.items():
            box.blockSignals(True)
            box.setChecked(bool(vals.get(key)))
            box.blockSignals(False)

    def refresh(self):
        is_sa = self._get('game', 'SA') == 'SA'
        self.cb['light_beam_asi'].setVisible(is_sa)
        self.cb['night_cols'].setVisible(is_sa)
        bad = PIPE_FORBIDDEN.get(self._get('export_pipeline', 'NONE'), set())
        for key, box in self.cb.items():
            box.setStyleSheet("color:%s;" % C['err'] if key in bad else "")

    @staticmethod
    def _on_flag(key, value):
        """Правка флага → на все выделенные меши (как в INU)."""
        try:
            sel = _selection()
            sel.set_flag(sel.selected_meshes(), key, value)
        except Exception as e:                         # noqa: BLE001
            print("[INU] write DFF flag %s: %r" % (key, e))


class ImportOptions(BuildMixin, QtWidgets.QWidget):
    """Опции импорта — как боковая панель диалога «Импорт» INU (Blender):
    игра импорта, фильтр форматов, опции DFF, подсказки."""

    formats_changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        r = Rollout("Import", opened=True)
        lay.addWidget(r)

        g = self._group("Import from game:")
        auto = self._tbtn(
            "Auto", 'import_auto_game', True,
            "Detect the game automatically from the file's RW version",
            self._refresh)
        plat, self._plat_group = self._seg_buttons(
            [("PC", "PC"), ("Mobile", "MOBILE")], self._get('platform', 'PC'),
            lambda d: self._set('platform', d),
            "PC / Mobile: on mobile textures R and B are swapped.")
        self._games, self._game_group = self._seg_buttons(
            [("SA", "SA"), ("III", "III"), ("VC", "VC")],
            self._get('import_game', 'SA'),
            lambda d: self._set('import_game', d),
            "Which game to import from (when Auto is off)")
        # как в INU: Auto, платформа и игры — один слитный блок
        g.addWidget(FusedBlock([[auto], plat, self._games]))
        r.body.addWidget(g.box)

        g = self._group("Show formats:")
        fmts = [self._tbtn(ext.upper(), 'imp_f_' + ext, True,
                           "Show .%s files in the list" % ext, self._on_formats)
                for ext in _IMPORT_FORMATS]
        g.addWidget(FusedBlock([fmts[:3], fmts[3:]]))
        r.body.addWidget(g.box)

        self._g_dff = g = self._group("DFF")
        g.addWidget(self._check(
            "Standard GTA SA model (vanilla)", 'import_weld_sharpen', False,
            "ON: treat as a STANDARD GTA SA model (weld + sharp edges). "
            "OFF: CUSTOM model: connect loose geometry and keep double-sided "
            "fences.", self._refresh))
        self._lb_custom = self._info("Custom: connect + keep fences")
        g.addWidget(self._lb_custom)
        g.addWidget(self._check(
            "Import 2DFX", 'import_2dfx', True,
            "Create 2DFX effect helpers from the DFF (lights/coronas, "
            "particles, ped attractors, sun glare, signs, etc.). Turn off to "
            "import the model without effects."))
        r.body.addWidget(g.box)

        r.body.addWidget(self._info(
            "Only selected files are imported\n"
            ".dff .col .cst .txd .ide .ipl: each by its own type\n"
            "Textures needed: select a .txd in the list"))
        lay.addStretch(1)
        self._refresh()

    def _refresh(self):
        auto = bool(self._get('import_auto_game', True))
        for b in self._games:
            b.setEnabled(not auto)
        self._g_dff.box.setVisible(bool(self._get('imp_f_dff', True)))
        self._lb_custom.setVisible(not self._get('import_weld_sharpen', False))

    def _on_formats(self):
        self._refresh()
        self.formats_changed.emit()

    def filters(self):
        """Фильтры «Files of type» по включённым форматам."""
        exts = [e for e in _IMPORT_FORMATS if self._get('imp_f_' + e, True)]
        out = []
        if exts:
            out.append(("GTA files (%s)" % " ".join("*." + e for e in exts),
                        ["*." + e for e in exts]))
            out += [("%s (*.%s)" % (e.upper(), e), ["*." + e]) for e in exts]
        out.append(("All Files (*.*)", ["*"]))
        return out


class ExportOptions(BuildMixin, QtWidgets.QWidget):
    """Опции экспорта — как боковая панель диалога «Export All» INU:
    игра, что экспортировать, настройки COL / TXD / DFF, All → IMG.
    info / active — сводка выделения и активный меш на момент открытия."""

    formats_changed = QtCore.Signal()

    def __init__(self, info=None, active=None, parent=None):
        super().__init__(parent)
        self._n_groups = (info or {}).get('n_groups', 0)
        self._name = (info or {}).get('name', '')
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        r = Rollout("Export", opened=True)
        lay.addWidget(r)

        g = self._group("Export to game:")
        plat, self._plat_group = self._seg_buttons(
            [("PC", "PC"), ("Mobile", "MOBILE")], self._get('platform', 'PC'),
            lambda d: self._set('platform', d),
            "PC / Mobile: Mobile writes Native Data PLG geometry. Mobile TXD "
            "is not implemented in 3ds Max yet — ignored: TXD stays PC format.")
        game, self._game_group = self._seg_buttons(
            [("SA", "SA"), ("III", "III"), ("VC", "VC")], self._get('game', 'SA'),
            self._on_game, "Target game: RW version of the DFF/COL/TXD.")
        g.addWidget(FusedBlock([plat, game]))
        r.body.addWidget(g.box)

        g = self._group("What to export:")
        g.addWidget(FusedBlock([[
            self._tbtn(lbl, key, dflt, tip, self._on_formats)
            for lbl, key, dflt, tip in (
                ("DFF", 'exp_dff', True, "Export DFF"),
                ("COL", 'exp_col', True, "Export COL"),
                ("LOD", 'exp_lod', True, "Export LOD (LOD<name>.dff)"),
                ("TXD", 'exp_txd', True, "Export TXD"),
                ("CST", 'exp_cst', False,
                 "Export collision as text .cst (Collision File Editor II)"),
            )]], pad=3))
        g.addWidget(self._check(
            "Also to IDE / IPL (paths from Map IO)", 'exp_ide_ipl', False,
            "After export also write the models into the IDE and IPL files "
            "set in the Map IO window (id, name, TXD, draw distance + "
            "placement and lod_index)."))
        g.addWidget(self._check(
            "Single DFF (vehicle / ped)", 'exp_single_dff', False,
            "Export the WHOLE selected hierarchy into ONE .dff (vehicle, ped, "
            "any multi-part model) instead of splitting by names. TXD/COL go "
            "into one shared file. The name comes from File name below."))
        name = ElideLabel()
        if self._n_groups > 1:
            name.setText("Multiple models: named per model")
        elif self._name:
            name.setText("Export name: %s" % self._name)
        else:
            name.setText("No model selected")
        g.addWidget(name)
        r.body.addWidget(g.box)

        # COL / CST — общие настройки коллизии
        self._g_col = g = self._group("COL")
        self._w_col_lib = QtWidgets.QWidget()
        hl = self._row(
            self._check("Library", 'col_library', False,
                        "Write every collision into a single .col file "
                        "(multi-entry library). Each record has its own "
                        "model_id and links to a DFF by matching ID."),
            self._line('col_library_name', "collision",
                       "Library .col name (without extension)"))
        hl.setStretch(0, 0)
        self._w_col_lib.setLayout(hl)
        g.addWidget(self._w_col_lib)
        g.addWidget(self._check(
            "Empty collision", 'col_empty', False,
            "Write COL/CST without geometry (zero faces/vertices/spheres/"
            "boxes, zero bounds) but with the model name. For models that "
            "need no collision but must have a COL record.", self._refresh))
        self._w_col_light = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(self._w_col_light)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(4)
        vl.addWidget(QtWidgets.QLabel("Collision light"))
        vl.addWidget(self._combo(
            'col_light_mode',
            [("From material", 'MATERIAL',
              "Use day/night set on the model's COL materials (Day Light / "
              "Night Light fields). Faces without settings stay at zero. "
              "Keeps imported values."),
             ("Auto: day + night", 'AUTO',
              "Set the same day/night on the WHOLE collision, overriding "
              "materials. Kam's standard (day 14 / night 4 = old 78).")],
            'AUTO', "Where to take collision lighting (day/night) from on export",
            self._refresh))
        self._w_auto_light = QtWidgets.QWidget()
        self._w_auto_light.setLayout(self._row(
            self._spin('col_auto_day', 0, 15, 14,
                       "Collision day light for 'Auto' mode. 0–15 (low nibble "
                       "of the light byte). 14 = standard (old 78)", prefix="Day: "),
            self._spin('col_auto_night', 0, 15, 4,
                       "Collision night light for 'Auto' mode. 0–15 (high nibble "
                       "of the light byte). 4 = standard (old 78)", prefix="Night: ")))
        vl.addWidget(self._w_auto_light)
        g.addWidget(self._w_col_light)
        r.body.addWidget(g.box)

        # TXD
        self._g_txd = g = self._group("TXD")
        g.addWidget(self._check(
            "Shared TXD: all models in one file", 'txd_shared', False,
            "Write all textures of all models into one shared .txd",
            self._refresh))
        self._ed_shared = self._line('txd_shared_name', "textures",
                                     "Shared .txd name (without extension)")
        g.addLayout(self._labeled("Name", self._ed_shared))
        g.addWidget(self._check(
            "Append to existing TXD", 'txd_merge', False,
            "If the .txd already exists: add/update the model's textures and "
            "keep the other textures of the file. Otherwise the .txd is "
            "overwritten."))
        self._lb_txd_note = self._info("Textures go to separate .txd per model")
        g.addWidget(self._lb_txd_note)
        r.body.addWidget(g.box)

        # DFF: pipeline, vertex alpha, флаги активного объекта
        self._g_dff = g = self._group("DFF")
        g.addWidget(QtWidgets.QLabel("Pipeline:"))
        pipe, self._pipe_group = pipeline_buttons(self, self._on_pipeline)
        g.addWidget(FusedBlock([pipe], pad=3))
        g.addWidget(self._check(
            "Vertex Alpha", 'export_vertex_alpha', False,
            "Write vertex alpha (vertex color transparency) into the DFF. Off "
            "by default: rarely needed and can leak stray alpha (e.g. on "
            "LODs). Use it for glass/foliage/fences; when off, alpha is "
            "always 255."))
        fg = self._group("DFF Flags (active object):")
        self.flags = FlagsBox()
        self.flags.load(active)
        fg.addWidget(self.flags)
        g.addWidget(fg.box)
        r.body.addWidget(g.box)

        # All → IMG — в Max ещё не сделано: галка есть, экспорт её не читает
        g = self._group("Output")
        g.addWidget(self._check(
            "All → IMG", 'export_to_img', False,
            "Export straight into the .img archive (not implemented in 3ds Max "
            "yet — ignored: export goes to the chosen folder). For .img use "
            "Map IO → IMG → Export.", self._refresh))
        self._lb_img = self._info("Not implemented in 3ds Max yet — ignored: "
                                  "export goes to the chosen folder.\nFor .img: "
                                  "Map IO → IMG → Export")
        self._lb_img.setStyleSheet("color:%s;" % C['err'])
        g.addWidget(self._lb_img)
        r.body.addWidget(g.box)
        lay.addStretch(1)
        self._refresh()

    def export_name(self):
        """Имя экспорта для поля File name (пусто при нескольких моделях)."""
        return self._name if self._n_groups == 1 else ''

    def _on_game(self, game):
        self._set('game', game)
        self.flags.refresh()

    def _on_pipeline(self):
        self.flags.refresh()

    def _on_formats(self):
        self._refresh()
        self.formats_changed.emit()

    def _refresh(self):
        g = self._get
        col, cst = bool(g('exp_col', True)), bool(g('exp_cst', False))
        self._g_col.box.setVisible(col or cst)
        self._w_col_lib.setVisible(col)           # library — только для .col
        self._w_col_light.setEnabled(not g('col_empty', False))
        self._w_auto_light.setVisible(g('col_light_mode', 'AUTO') == 'AUTO')
        self._g_txd.box.setVisible(bool(g('exp_txd', True)))
        self._ed_shared.setEnabled(bool(g('txd_shared', False)))
        self._lb_txd_note.setVisible(
            not g('txd_shared', False) and self._n_groups > 1)
        self._g_dff.box.setVisible(bool(g('exp_dff', True) or g('exp_lod', True)))
        self._lb_img.setVisible(bool(g('export_to_img', False)))

    def filters(self):
        """Фильтры «Files of type» по включённым форматам (LOD — тоже .dff)."""
        g = self._get
        parts = []
        for flag, glob in ((g('exp_dff', True), '*.dff'),
                           (g('exp_lod', True), '*.dff'),
                           (g('exp_col', True), '*.col'),
                           (g('exp_txd', True), '*.txd'),
                           (g('exp_cst', False), '*.cst')):
            if flag and glob not in parts:
                parts.append(glob)
        out = []
        if parts:
            out.append(("Export formats (%s)" % " ".join(parts), parts))
        out.append(("All Files (*.*)", ["*"]))
        return out
