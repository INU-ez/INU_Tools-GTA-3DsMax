"""COL lighting/frame, prelight fallback and zone-name regressions."""
import contextlib
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import numpy as np
from inu_gta_core.col import ColModel
from inu_max.ops import col_build as CB, dff_build as DB, dff_export as DE
from inu_max.ops import prelight as PL, prelight_math as PM
from inu_max.adapter import zon as Z, selection as S, scene_read as SR


class CollisionTests(unittest.TestCase):
    def test_surface_bytes_clamp(self):
        self.assertEqual(CB.surface_of({'col_mat_index': -3, 'col_flags': 300,
                                       'col_brightness': -2})[:3], (0, 255, 0))
        self.assertEqual(CB.clamp_light(300), 255)
        self.assertEqual(CB.clamp_light(-2), 0)

    def test_auto_uses_version_lighting_byte(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                model = ColModel(version=version)
                CB._add_prim(CB.ColPrim(radius=2, surface=(10, 11, 0xBB, 0xCC)),
                             model, ('AUTO', 14, 4))
                surface = model.spheres[0].surface
                self.assertEqual((surface.brightness, surface.light),
                                 (0xBB, 0x4E) if version == 1 else (0x4E, 0xCC))
                self.assertEqual(model.bounds.radius, 0)

    def test_material_primitive_routes_day_night_and_mirror_radius(self):
        node = NS(material=object(), objecttransform=NS(scalepart=NS(x=-2, y=1, z=1)), radius=3)
        props = {'col_flags': 300, 'col_day_light': 14, 'col_night_light': 4}
        material = NS(is_multi=lambda m: False, props=lambda m: props)
        with patch.object(SR, 'col_prim', return_value='SPHERE'), \
             patch.object(SR, 'get_prop', side_effect=lambda n, k, d: 123 if k == 'col_light' else d), \
             patch.object(SR, 'world_pos', return_value=(2, 0, 0)), \
             patch('inu_max.adapter.material.is_multi', material.is_multi), \
             patch('inu_max.adapter.material.props', material.props):
            p = SR.col_prim_data(node, version=3)
        self.assertEqual(p.surface, (0, 255, 0x4E, 123))
        self.assertEqual(p.radius, 6)

    def test_reference_keeps_rotation_translation_without_scale(self):
        class Point:
            def __init__(self, values):
                self.values = np.array(values)
                self.x, self.y, self.z = values
            def __mul__(self, matrix):
                return Point(self.values @ matrix.r + matrix.t)
        class Matrix:
            def __init__(self, r):
                self.r = np.array(r)
                self.t = np.zeros(3)
            @property
            def row4(self):
                return self.t
            @row4.setter
            def row4(self, point):
                self.t = point.values
        rot = np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]])
        def inverse(frame):
            out = Matrix(frame.r.T)
            out.t = -frame.t @ out.r
            return out
        ref = NS(transform=NS(rotationpart=rot, translationpart=Point((10, 0, 0)), scale=2))
        node = NS(pos=Point((10, 2, 0)))
        rt = NS(matrix3=Matrix, inverse=inverse)
        with patch.object(S, '_rt', return_value=rt), \
             patch.object(DE, '_sr', return_value=NS(col_prim_data=lambda n, version: CB.ColPrim(radius=6))):
            p = DE._prim_in(node, ref, 3)
        np.testing.assert_allclose(p.center, (2, 0, 0))
        self.assertEqual(p.radius, 6)


class BakeTests(unittest.TestCase):
    def bake(self, old, over):
        node = NS(name='test')
        faces = np.array([[0, 1, 2]])
        geo = (np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]]), faces,
               np.array([[[0, 0, 1]] * 3]))
        lamp = {'type': 'SUN', 'color': (1, 1, 1), 'energy': 1,
                'to_light': (0, 0, 1)}
        ps = NS(selected_meshes=lambda: ([node], []), lights=lambda allowed: ([lamp], {}),
                active_layer=lambda n: 'day', LAYER_CHAN={'day': 0},
                bake_geometry=lambda n: geo, get_corners=lambda n, c: old,
                v_value=lambda n, l: 20, set_v=Mock(), set_corners=Mock(), env_release=Mock())
        with patch.object(PL, '_ps', return_value=ps), patch.object(PL, '_pm', return_value=PM), \
             patch.object(PL, '_absorb', return_value=''), \
             patch.object(PL, 'undo_block', side_effect=lambda label: contextlib.nullcontext()), \
             patch.object(PL.settings, 'get', side_effect=lambda k, d=None: d):
            self.assertEqual(PL.bake(over=over)[0], 'INFO')
        return ps.set_corners.call_args.args[-1], ps

    def test_missing_or_wrong_size_over_matches_fresh_bake(self):
        fresh, _ = self.bake(None, False)
        self.assertGreater(float(fresh.min()), 0)
        for old in (None, np.zeros((2, 3))):
            values, ps = self.bake(old, True)
            np.testing.assert_array_equal(values, fresh)
            ps.set_v.assert_called_once()

    def test_valid_base_is_added_without_reapplying_v(self):
        old = np.full((3, 3), .2)
        values, ps = self.bake(old, True)
        self.assertTrue(np.all(values > old))
        ps.set_v.assert_not_called()


class ZoneTests(unittest.TestCase):
    def test_backup_failure_preserves_existing_zone_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'map.zon')
            Path(path).write_bytes(b'original zones')
            with patch.object(Z, '_rt', return_value=NS()), \
                 patch.object(Z.shutil, 'copy2', side_effect=PermissionError('backup denied')):
                with self.assertRaises(PermissionError):
                    Z.export_zon(path, [])
            self.assertEqual(Path(path).read_bytes(), b'original zones')

    def test_names_normalize_commas_and_whitespace(self):
        for name in ('A  B', 'A,B', ' A\tB '):
            node = NS(name='old')
            with patch.object(Z, 'is_zone', return_value=True), \
                 patch.object(Z, '_undo', side_effect=lambda label: contextlib.nullcontext()), \
                 patch.object(Z, 'put_field') as write:
                Z.rename(node, name)
                write.assert_called_once_with([node], 'zon_name', 'A_B')
                self.assertEqual(node.name, 'Zone_A_B')

    def test_empty_names_and_non_zones_are_ignored(self):
        for name, zone in ((' , ', True), ('house', False)):
            node = NS(name='old')
            with patch.object(Z, 'is_zone', return_value=zone), patch.object(Z, 'put_field') as write:
                Z.rename(node, name)
                write.assert_not_called()
                self.assertEqual(node.name, 'old')


class UVTests(unittest.TestCase):
    def mat(self, name, mode):
        return DB.MatData(name=name, props={'uv_anim_write': True, 'uv_anim_mode': mode})

    def test_old_rw_warns_for_scroll_and_keys_merges_names(self):
        warnings = []
        DE._uv_anim_notes(warnings, [self.mat('water', 'SCROLL')], 0x34003)
        DE._uv_anim_notes(warnings, [self.mat('glass', 'KEYFRAME')], 0x34003)
        self.assertEqual(len(warnings), 1)
        self.assertIn('not written', warnings[0])
        self.assertTrue(warnings[0].endswith('water, glass'))

    def test_sa_scroll_no_warning_missing_keys_reported(self):
        warnings = []
        DE._uv_anim_notes(warnings, [self.mat('water', 'SCROLL')], 0x36003)
        self.assertEqual(warnings, [])
        DE._uv_anim_notes(warnings, [self.mat('glass', 'KEYFRAME')], 0x36003)
        self.assertIn('no sampled keys', warnings[0])

    def test_unsupported_keyframes_do_not_abort_build(self):
        node = DB.ExportNode(kind='DUMMY', materials=[self.mat('glass', 'KEYFRAME')])
        clump = DB.build_clump([node], version=0x34003)
        self.assertIsNone(clump.uv_anim_dict)
