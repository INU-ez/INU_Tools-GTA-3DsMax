"""Pipeline round trips and delayed Object TXD edits without the Max host."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from inu_max.ops import pipeline_flags as PF


class PipelineTests(unittest.TestCase):
    def apply(self, objects, old, new, default=None):
        for obj, values in PF.plan(objects, old, new, default):
            obj.update(values)

    def test_round_trip_restores_individual_flags(self):
        vehicle, dn = '0x53F2009A', '0x53F20098'
        a, b = {'light': True, 'uv_map1': False}, {'light': False, 'uv_map1': True}
        self.apply([a, b], vehicle, dn)
        self.assertFalse(a['light'])
        a['uv_map1'] = True
        self.apply([a, b], dn, vehicle)
        self.assertTrue(a['light'])
        self.assertFalse(a['uv_map1'])
        self.assertFalse(b['light'])
        self.assertTrue(b['uv_map1'])
        self.apply([a, b], vehicle, dn)
        self.assertTrue(a['uv_map1'])
        self.assertFalse(a['light'])

    def test_own_snapshot_beats_global_and_collision_is_untouched(self):
        a = {'flags_snap_ped': PF.pack({'uv_map1': False})}
        b = {}
        col = {'col_prim': 'sphere', 'light': True}
        self.apply([a, b, col], 'NONE', 'PED', {'uv_map1': True})
        self.assertFalse(a['uv_map1'])
        self.assertTrue(b.get('uv_map1', True))
        self.assertEqual(col, {'col_prim': 'sphere', 'light': True})

    def test_corrupt_and_older_snapshots(self):
        self.assertIsNone(PF.unpack('101bad'))
        self.assertEqual(PF.unpack('0'), {PF.FLAGS[0]: False})
        a = {'flags_snap_dn': 'bad', 'light': True}
        self.apply([a], 'PED', '0x53F20098', {'uv_map2': False, 'light': True})
        self.assertFalse(a['uv_map2'])
        self.assertFalse(a['light'])

    def test_partial_host_failure_records_active_pipeline(self):
        with patch.object(PF, 'scene_pipeline', return_value='PED'), \
             patch.object(PF, 'switch', side_effect=RuntimeError('host failure')), \
             patch.object(PF, 'set_scene_pipeline') as scene_save, \
             patch.object(PF.settings, 'set') as save:
            with self.assertRaises(RuntimeError):
                PF.set_pipeline('0x53F2009A')
            save.assert_called_once_with('export_pipeline', '0x53F2009A')
            scene_save.assert_called_once_with('0x53F2009A')

    def test_settings_only_fallback(self):
        with patch.object(PF, 'scene_pipeline', side_effect=ImportError), \
             patch.object(PF, 'switch', side_effect=ImportError), \
             patch.object(PF, 'set_scene_pipeline', side_effect=ImportError), \
             patch.object(PF.settings, 'get', return_value='PED'), \
             patch.object(PF.settings, 'set') as save:
            PF.set_pipeline('0x53F2009A')
            save.assert_called_once_with('export_pipeline', '0x53F2009A')


class ObjectEditTests(unittest.TestCase):
    def method(self, name, sel):
        tree = ast.parse(Path('inu_max/ui/map_io.py').read_text(encoding='utf-8-sig'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ObjectIdeIpl')
        fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
        scope = {'_sel': lambda: sel}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<ObjectIdeIpl>', 'exec'), scope)
        return scope[name]

    def test_txd_commit_targets_original_object_once(self):
        sel = SimpleNamespace(put_field=Mock())
        edit = Mock()
        edit.isModified.return_value = True
        edit.text.return_value = '  shared_wall  '
        old, active = object(), object()
        ui = SimpleNamespace(_txd=edit, _txd_target=old, _obj=active)
        commit = self.method('_commit_txd', sel)
        commit(ui)
        sel.put_field.assert_called_once_with([old], 'txd_name', 'shared_wall')
        edit.isModified.return_value = False
        commit(ui)
        self.assertEqual(sel.put_field.call_count, 1)

    def test_lod_distance_updates_both_partners(self):
        sel = SimpleNamespace(put_field=Mock())
        hd, lod = object(), object()
        ui = SimpleNamespace(_obj=hd, _partner_node=lod)
        self.method('_write', sel)(ui, 'lod_draw_distance', 450.0)
        self.assertEqual(sel.put_field.call_args_list[0].args, ([hd], 'lod_draw_distance', 450.0))
        self.assertEqual(sel.put_field.call_args_list[1].args, ([lod], 'lod_draw_distance', 450.0))
