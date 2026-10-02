"""Placement and frame export regressions; no native Max runtime needed."""
import ast
import contextlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from inu_gta_core.ipl import IplInstance
from inu_max.ops import dff_build as DB, map_link as ML, map_link_ops as MO
from inu_max.ops.frames import game_frame_name


class PlacementTests(unittest.TestCase):
    def test_scale_is_ignored_in_both_import_and_new_export_rows(self):
        inst = IplInstance(model_id=1, model_name='house', scale_x=2, scale_y=3, scale_z=4, pos_x=5)
        rows = ML.inst_rows(inst)
        self.assertEqual(rows[:9], [1, 0, 0, 0, 1, 0, 0, 0, 1])
        self.assertEqual(rows[9:], [5, 0, 0])
        rec = SimpleNamespace(node=1, name='house', get=lambda k, d: d)
        sc = SimpleNamespace(LS=SimpleNamespace(world=lambda n: ((5, 0, 0), (0, 0, 0, 1), (2, 3, 4))),
                             model_name=lambda r: 'house')
        entry = ML.ipl_entry(sc, rec)
        self.assertEqual((entry.scale_x, entry.scale_y, entry.scale_z), (1, 1, 1))
        for game in ('III', 'VC', 'SA'):
            report = ML.Report()
            ML._scale_note(sc, rec, game, report)
            self.assertEqual(report.messages[0][0], 'WARNING')

    def test_delete_without_rows_asks_about_problems(self):
        report = ML.Report()
        report.msg('WARNING', 'missing IPL')
        confirm = Mock(return_value=False)
        result = MO._with_confirm(lambda dry: report, confirm, 'Remove', 'IPL', always=True)
        self.assertIsNone(result)
        self.assertEqual(confirm.call_args.args[1][0], 'Problems found before writing:')

    def test_delete_confirmation_is_bounded(self):
        report = ML.Report()
        for i in range(20):
            report.plan('%s.ipl' % i, 'remove LOD link of 1 placement(s)')
        confirm = Mock(return_value=False)
        MO._with_confirm(lambda dry: report, confirm, 'Remove', 'IPL', always=True)
        lines = confirm.call_args.args[1]
        self.assertEqual(len(lines), 14)
        self.assertEqual(lines[-1], '… 8 more')

    def test_unreadable_ipl_preserves_links_and_warns_once(self):
        recs = [SimpleNamespace(node=i, name='house%s' % i, handle=i,
                                get=lambda k, d: 'uuid' if k == 'ipl_uuid' else d)
                for i in range(2)]
        sc = SimpleNamespace(reset_copies=lambda: None, model_type=lambda r: ('DFF', 'house'),
                             is_copy=lambda r: False, linked_models=lambda: recs)
        with patch.object(ML, 'ipl_locate', return_value=('broken.ipl', -1)), \
             patch.object(ML.IplCache, 'get', return_value=None), patch.object(ML, 'clear_ipl') as clear:
            report = ML.ipl_pull(sc, recs, [], clear_lost=True)
        clear.assert_not_called()
        self.assertEqual(len(report.messages), 1)
        self.assertIn('links of 2 models kept', report.messages[0][1])


class FrameTests(unittest.TestCase):
    def test_only_copy_suffixes_are_removed(self):
        for source, expected in [('wheel_lf_dummy001', 'wheel_lf_dummy'),
                                 ('door_lhs_dummy003', 'door_lhs_dummy'),
                                 ('misc_a001', 'misc_a'), ('L UpperArm001', 'L UpperArm'),
                                 ('house.001.002', 'house'), ('cunte_roads303', 'cunte_roads303'),
                                 ('CEgroundT202', 'CEgroundT202')]:
            self.assertEqual(game_frame_name(source), expected)

    def test_collision_keeps_original_and_skin_node_names(self):
        nodes = [DB.ExportNode(name='wheel_lf_dummy'), DB.ExportNode(name='wheel_lf_dummy001'),
                 DB.ExportNode(name='wheel_rf_dummy001')]
        clump = DB.build_clump(nodes)
        self.assertEqual([f.name for f in clump.frames],
                         ['wheel_lf_dummy', 'wheel_lf_dummy001', 'wheel_rf_dummy'])
        self.assertEqual(nodes[2].name, 'wheel_rf_dummy001')

    def test_multiple_copies_do_not_make_duplicate_engine_names(self):
        clump = DB.build_clump([DB.ExportNode(name='wheel_lf_dummy001'),
                               DB.ExportNode(name='wheel_lf_dummy002')])
        self.assertEqual([f.name for f in clump.frames], ['wheel_lf_dummy', 'wheel_lf_dummy002'])


class VecPrecisionTests(unittest.TestCase):
    def test_rounding_display_does_not_change_other_components(self):
        # Load the actual widget class with a small rounding spinner harness;
        # this checks its bookkeeping, not Qt/native Max integration.
        path = Path(__file__).resolve().parents[2] / 'inu_max' / 'ui' / 'widgets.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'VecEdit')
        class Signal:
            def connect(self, callback): self.callback = callback
            def emit(self, value): self.value = value
        class Spinner:
            def __init__(self, decimals, *args): self.decimals, self.valueChanged = decimals, Signal()
            def setToolTip(self, value): pass
            def blockSignals(self, value): pass
            def setValue(self, value): self.shown = round(value, self.decimals)
        class Widget:
            def __init__(self, *args): pass
        class Layout:
            def __init__(self, *args): pass
            def setContentsMargins(self, *args): pass
            def setSpacing(self, *args): pass
            def addWidget(self, *args): pass
        scope = {'QtWidgets': SimpleNamespace(QWidget=Widget, QGridLayout=Layout),
                 'QtCore': SimpleNamespace(Signal=lambda *args: Signal()), 'NumEdit': Spinner}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), 'exec'), scope)
        vector = scope['VecEdit']()
        vector.set_values((2233.80322, 1.23456789, -0.00012))
        vector._sp[1].valueChanged.callback(5)
        self.assertEqual(vector.changed.value, (2233.80322, 5, -0.00012))
        matrix = scope['VecEdit'](9, 3, cols=3)
        matrix.set_values([0.70710678] * 9)
        matrix._sp[4].valueChanged.callback(1)
        self.assertEqual(matrix.values(), tuple(1 if i == 4 else 0.70710678 for i in range(9)))


if __name__ == '__main__':
    unittest.main()
