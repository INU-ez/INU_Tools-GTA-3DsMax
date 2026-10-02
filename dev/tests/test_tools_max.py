import tempfile
from unittest.mock import patch
import unittest
from pathlib import Path
from types import SimpleNamespace

from inu_gta_core.water import WaterVertex as V, WaterPolygon as P, check_quad_fit
from inu_max.ops.water_tools import split_polygon
from inu_max.ops.radar_tools import radar_plan
from inu_max.ops.camera_tools import read_camera, write_camera
from inu_max.ops.vehicle_tools import mirror_name
from inu_max.ops.dff_build import uv_anim_dict
from inu_max.ops.weight_tools import weld_weights
from inu_max.ops.node_tools import build_graph
from inu_max.ops.anim_tools import _bones, keyed_controllers
from inu_gta_core.paths import write_nodes, read_nodes


class ToolTests(unittest.TestCase):
    def test_water_split_interpolates_parameters_and_preserves_area(self):
        poly = P([V(250, 250, 0, speed_x=0), V(750, 250, 10, speed_x=10),
                  V(750, 750, 10, speed_x=10), V(250, 750, 0, speed_x=0)], 3)
        pieces = split_polygon(poly)
        self.assertEqual(len(pieces), 4)
        area = 0
        for part in pieces:
            verts = part.vertices
            self.assertEqual(part.flag, 3)
            self.assertEqual(check_quad_fit(min(v.x for v in verts), min(v.y for v in verts),
                                           max(v.x for v in verts), max(v.y for v in verts)), 'ok')
            area += abs(sum(a.x * b.y - b.x * a.y for a, b in zip(verts, verts[1:] + verts[:1]))) / 2
            for vertex in verts:
                if vertex.x == 500:
                    self.assertAlmostEqual(vertex.speed_x, 5)
                    self.assertAlmostEqual(vertex.z, 5)
        self.assertAlmostEqual(area, 250000)

    def test_water_boundary_and_negative_coordinates(self):
        for x in (-500, 0, 500):
            parts = split_polygon(P([V(x, 0), V(x + 500, 0), V(x + 500, 500), V(x, 500)]))
            self.assertEqual(len(parts), 1)

    def test_radar_layout_and_explicit_modes(self):
        self.assertEqual(len(radar_plan('ALL', 'SA')), 144)
        self.assertEqual(len(radar_plan('ALL', 'VC')), 64)
        first = radar_plan('ALL', 'SA')[0]
        self.assertEqual(first, ('radar00', -2750, 2750, 500))
        self.assertEqual(len(radar_plan('MENU', 'SA')), 9)
        self.assertEqual(radar_plan('MENU', 'SA')[0][0], 'MapTop01')
        self.assertEqual(len(radar_plan('SPECIFIC', 'SA', specific='0,10,10')), 2)
        with self.assertRaises(ValueError):
            radar_plan('SPECIFIC', 'VC', specific='64')

    def test_camera_roundtrip_keeps_roll_and_padding(self):
        keys = dict(fov=[(0, 45), (1, 60)], roll=[(0, 10), (1, 20)],
                    pos=[(0, 1, 2, 3), (1, 4, 5, 6)], target=[(0, 0, 0, 0), (1, 1, 1, 1)])
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'camera.dat')
            write_camera(path, keys)
            self.assertEqual(read_camera(path), keys)
            self.assertEqual(Path(path).stat().st_size % 2048, 0)

    def test_mirror_side_tokens(self):
        for name in ('wheel_lf_dummy', 'door_lb_ok', 'wheel_rm'):
            self.assertNotEqual(mirror_name(name), name)
            self.assertEqual(mirror_name(mirror_name(name)), name)
        self.assertEqual(mirror_name('shelf_model'), 'shelf_model')

    def test_uv_keys_are_written_instead_of_scroll(self):
        md = SimpleNamespace(name='uv', props=dict(uv_anim_write=True, uv_anim_mode='KEYFRAME',
            uv_anim_speed_u=99, uv_keyframes=[dict(time=0, scale_u=2, trans_v=.25),
                                           dict(time=2, scale_u=3, trans_v=.75)]))
        animation = uv_anim_dict([md]).anims[0]
        self.assertEqual(animation.duration, 2)
        self.assertEqual(animation.keyframes[-1].scale_u, 3)
        self.assertEqual(animation.keyframes[-1].trans_v, .75)
        self.assertEqual(animation.keyframes[-1].trans_u, 0)


if __name__ == '__main__':
    unittest.main()


class AdapterRegressionTests(unittest.TestCase):
    def test_welded_proxy_preserves_seam_mapping_and_normalizes_weights(self):
        points = [(0, 0, 0), (1, 0, 0), (0.000001, 0, 0)]
        positions, weights, mapping = weld_weights(points,
            [[('a', 1)], [('b', 1)], [('b', 1)]])
        self.assertEqual(mapping, [0, 1, 0])
        self.assertEqual(len(positions), 2)
        self.assertEqual(dict(weights[0]), {'a': .5, 'b': .5})
        with self.assertRaises(ValueError):
            weld_weights(points, [[]])

    def test_graph_preserves_cross_region_links_and_physical_ped_ids(self):
        graph = build_graph([
            ([(0, 0, 0), (900, 0, 0)], {'sapath_type': 2}, False),
            ([(0, 1, 0), (100, 1, 0)], {'sapath_type': 1}, False)])
        lookup = {(node.area_id, node.node_id): node for nf in graph.values()
                  for node in nf.vehicle_nodes + nf.ped_nodes}
        cross = 0
        with tempfile.TemporaryDirectory() as folder:
            for area, nf in graph.items():
                self.assertEqual([node.node_id for node in nf.vehicle_nodes + nf.ped_nodes],
                                 list(range(len(nf.vehicle_nodes) + len(nf.ped_nodes))))
                for node in nf.vehicle_nodes + nf.ped_nodes:
                    for link in nf.links[node.link_id:node.link_id + (node.flags & 15)]:
                        self.assertIn((link.area_id, link.node_id), lookup)
                        cross += link.area_id != area
                path = str(Path(folder) / ('NODES%d.DAT' % area))
                write_nodes(path, nf)
                restored = read_nodes(path)
                self.assertEqual(len(restored.links), len(nf.links))
                self.assertEqual(restored.navi_links, nf.navi_links)
                self.assertEqual(len(restored.ped_nodes), len(nf.ped_nodes))
        self.assertGreater(cross, 0)

    def test_hand_export_stays_below_hand_root(self):
        other = SimpleNamespace(name='ped', children=[])
        hand = SimpleNamespace(name='hand', children=[], parent=other)
        finger = SimpleNamespace(name='finger', children=[], parent=hand)
        other.children = [hand]
        hand.children = [finger]
        with patch('inu_max.ops.anim_tools.S.node_kind', return_value='BONE'):
            self.assertEqual([n.name for n in _bones(hand)], ['hand', 'finger'])

    def test_compound_controller_exposes_selected_euler_tracks(self):
        leaf = SimpleNamespace(count=3, children=[])
        root = SimpleNamespace(count=-1, children=[leaf], numSubs=1)
        rt = SimpleNamespace(numKeys=lambda c: c.count, numSubs=lambda c: len(c.children),
            getSubAnim=lambda c, i: SimpleNamespace(controller=c.children[i-1]))
        with patch('inu_max.ops.anim_tools.S._rt', return_value=rt):
            self.assertEqual(list(keyed_controllers(root)), [(leaf, 3)])


class BatchWriteTests(unittest.TestCase):
    def test_failed_second_replace_restores_first_and_leaves_no_temps(self):
        import os
        from inu_max.ops.file_write import write_batch
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / 'a.dff', Path(folder) / 'b.ifp'
            a.write_bytes(b'old-a')
            b.write_bytes(b'old-b')
            replace = os.replace
            def failing(source, destination):
                if str(destination) == str(b):
                    raise PermissionError('locked IFP')
                return replace(source, destination)
            with patch('inu_max.ops.file_write.os.replace', side_effect=failing):
                with self.assertRaises(PermissionError):
                    write_batch({str(a): b'new-a', str(b): b'new-b'})
            self.assertEqual(a.read_bytes(), b'old-a')
            self.assertEqual(b.read_bytes(), b'old-b')
            self.assertEqual(set(Path(folder).iterdir()), {a, b})


class AnimatedIDETests(unittest.TestCase):
    def test_animated_entry_replaces_static_registration_without_duplicate_id(self):
        from inu_max.ops.rig_tools import _write_anim_ide
        from inu_gta_core.ide import read_ide
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'map.ide'
            path.write_bytes(b'# keep comment\r\nobjs\r\n2000, fan, fan, 300, 0\r\n2001, wall, wall, 300, 0\r\nend\r\n')
            _write_anim_ide(str(path), 2000, 'fan', 'fan', 'fananim', 400)
            result = read_ide(str(path))
            self.assertEqual([entry.model_id for entry in result.objects], [2001])
            self.assertEqual([entry.model_id for entry in result.anims], [2000])
            self.assertIn(b'# keep comment\r\n', path.read_bytes())
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                _write_anim_ide(str(path), 2001, 'fan', 'fan', 'fananim', 400)
            self.assertEqual(before, path.read_bytes())
