import copy
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from inu_gta_core import paths as P
from inu_max.ops import node_tools as N


def region(area, ped=True):
    return P.NodesFile(
        vehicle_nodes=[P.PathNode(x=800, area_id=area, node_id=0, flags=1, path_width=8)],
        ped_nodes=[P.PathNode(x=800, area_id=area, node_id=1, is_vehicle=False)] if ped else [],
        links=[P.PathLink(37, 1)],
        navi_nodes=[P.NaviNode(x=800, area_id=37, node_id=0, dir_x=7, flags=32),
                    P.NaviNode(x=800, area_id=37, node_id=1, dir_x=7, flags=32)],
        navi_links=[37 << 10], link_lengths=[5], path_intersections=[7] * 193,
        parsed_extras=True)


def all_regions():
    return [('NODES%d.DAT' % area,
             region(area, ped=area == 37) if area in (37, 38) else P.NodesFile(parsed_extras=True),
             b'') for area in range(64)]


class NodeMergeTests(unittest.TestCase):
    def test_full_map_reindexes_peds_and_neighbour_links_and_keeps_navigation(self):
        sources = all_regions()
        original = copy.deepcopy(sources)
        zones = P.split_nodes_by_area([('nodes_vehicle', 800, 0, 1)])
        extras_before = copy.deepcopy(zones)
        files, merged = N.prepare_node_merge(sources, zones)
        self.assertEqual(len(files), 64)
        self.assertEqual(merged, ['NODES37.DAT'])
        nf = files['NODES37.DAT']
        self.assertEqual([n.node_id for n in nf.vehicle_nodes], [0, 1])
        self.assertEqual(nf.ped_nodes[0].node_id, 2)
        self.assertEqual(nf.vehicle_nodes[0].flags, original[37][1].vehicle_nodes[0].flags)
        self.assertEqual(nf.vehicle_nodes[1].flags & 15, 0)
        for name in ('NODES37.DAT', 'NODES38.DAT'):
            self.assertEqual(files[name].links[0], P.PathLink(37, 2))
            self.assertEqual(files[name].navi_nodes[1].node_id, 2)
            self.assertEqual(files[name].navi_nodes[0].dir_x, 7)
            self.assertEqual(files[name].navi_links, [37 << 10])
            self.assertEqual(files[name].link_lengths, [5])
            self.assertEqual(files[name].path_intersections, [7] * 193)
        self.assertEqual(sources, original)
        self.assertEqual(zones, extras_before)
        with tempfile.TemporaryDirectory() as folder:
            N.write_node_batch(folder, files)
            a = P.read_nodes(str(Path(folder) / 'NODES37.DAT'))
            b = P.read_nodes(str(Path(folder) / 'NODES38.DAT'))
            self.assertEqual(a.ped_nodes[0].node_id, 2)
            self.assertEqual(b.links[0].node_id, 2)
            self.assertEqual(b.navi_links, [37 << 10])
            self.assertEqual(len(list(Path(folder).iterdir())), 64)

    def test_partial_vehicle_merge_fails_without_mutating_sources(self):
        sources = [all_regions()[37]]
        before = copy.deepcopy(sources)
        with self.assertRaisesRegex(ValueError, 'all 64'):
            N.prepare_node_merge(sources, P.split_nodes_by_area([('nodes_vehicle', 800, 0, 1)]))
        self.assertEqual(sources, before)

    def test_ped_append_keeps_old_ids_links_and_unknown_tail(self):
        nf = region(37)
        nf.parsed_extras = False
        nf.extra_data = b'opaque-original-tail'
        files, _ = N.prepare_node_merge([('nodes37.dat', nf, b'')],
            P.split_nodes_by_area([('nodes_ped', 800, 0, 1)]))
        result = files['nodes37.dat']
        self.assertEqual([n.node_id for n in result.ped_nodes], [1, 2])
        self.assertEqual(result.links, nf.links)
        self.assertEqual(result.extra_data, nf.extra_data)
        with tempfile.TemporaryDirectory() as folder:
            N.write_node_batch(folder, files)
            self.assertTrue((Path(folder) / 'nodes37.dat').read_bytes().endswith(nf.extra_data))

    def test_vehicle_append_without_existing_peds_does_not_require_full_map(self):
        nf = P.NodesFile(vehicle_nodes=[P.PathNode(area_id=37, node_id=0)], parsed_extras=True)
        files, _ = N.prepare_node_merge([('nodes37.dat', nf, b'')],
            P.split_nodes_by_area([('nodes_vehicle', 800, 0, 1)]))
        self.assertEqual([n.node_id for n in files['nodes37.dat'].vehicle_nodes], [0, 1])

    def test_case_variants_deduplicate_identical_imports_and_keep_destination_case(self):
        nf = P.NodesFile(ped_nodes=[P.PathNode(area_id=37, node_id=0, is_vehicle=False)], parsed_extras=True)
        files, _ = N.prepare_node_merge([('nodes37.dat', nf, b'')],
            P.split_nodes_by_area([('nodes_ped', 800, 0, 1)]))
        self.assertEqual(len(files), 1)
        with tempfile.TemporaryDirectory() as folder:
            old = Path(folder) / 'NODES37.DAT'
            old.write_bytes(b'previous')
            N.write_node_batch(folder, files)
            self.assertEqual([p.name for p in Path(folder).iterdir()], ['NODES37.DAT'])
            self.assertEqual(len(P.read_nodes(str(old)).ped_nodes), 2)
        conflict = copy.deepcopy(nf)
        conflict.ped_nodes[0].x = 99
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            N.prepare_node_merge([('nodes37.dat', nf, b''), ('NODES37.DAT', conflict, b'')], {})

    def test_reindex_rejects_unknown_tail_bad_identity_or_missing_target(self):
        for defect in ('tail', 'identity', 'link'):
            sources = all_regions()
            if defect == 'tail':
                sources[9][1].extra_data = b'unknown'
            elif defect == 'identity':
                sources[38][1].vehicle_nodes[0].node_id = 99
            else:
                sources[38][1].links[0].node_id = 999
            before = copy.deepcopy(sources)
            with self.assertRaises(ValueError):
                N.prepare_node_merge(sources, P.split_nodes_by_area([('nodes_vehicle', 800, 0, 1)]))
            self.assertEqual(sources, before)

    def test_connected_graph_is_not_mistaken_for_bare_nodes(self):
        graph = N.build_graph([([(800, 0, 0), (810, 0, 0)], {'sapath_type': 2}, False)])
        with self.assertRaisesRegex(ValueError, 'connected curve graph'):
            N.prepare_node_merge(all_regions(), graph)

    def test_fla4_import_is_not_silently_downgraded(self):
        nf = P.NodesFile(vehicle_nodes=[P.PathNode(area_id=37, node_id=0,
            spawn_probability=17, speed_limit_kmh=80, lane_count_override=2)], parsed_extras=True, fla4=True)
        files, _ = N.prepare_node_merge([('nodes37.dat', nf, b'')], {}, fla4=False)
        with tempfile.TemporaryDirectory() as folder:
            N.write_node_batch(folder, files)
            restored = P.read_nodes(str(Path(folder) / 'nodes37.dat'))
            self.assertTrue(restored.fla4)
            node = restored.vehicle_nodes[0]
            self.assertEqual((node.spawn_probability, node.speed_limit_kmh, node.lane_count_override), (17, 80, 2))

    def test_late_binary_error_does_not_replace_earlier_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'nodes37.dat'
            path.write_bytes(b'original')
            good = P.NodesFile(parsed_extras=True)
            bad = P.NodesFile(vehicle_nodes=[P.PathNode(x=1e9)], parsed_extras=True)
            with self.assertRaises(Exception):
                N.write_node_batch(folder, {'nodes37.dat': good, 'nodes38.dat': bad})
            self.assertEqual(path.read_bytes(), b'original')
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_late_replace_failure_rolls_back_the_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / 'nodes37.dat', Path(folder) / 'nodes38.dat'
            a.write_bytes(b'original-a')
            b.write_bytes(b'original-b')
            replace = os.replace
            def failing(source, destination):
                if str(destination) == str(b):
                    raise PermissionError('locked region')
                return replace(source, destination)
            with patch('inu_max.ops.file_write.os.replace', side_effect=failing):
                with self.assertRaises(PermissionError):
                    N.write_node_batch(folder, {a.name: P.NodesFile(parsed_extras=True), b.name: P.NodesFile(parsed_extras=True)})
            self.assertEqual(a.read_bytes(), b'original-a')
            self.assertEqual(b.read_bytes(), b'original-b')
            self.assertEqual(set(Path(folder).iterdir()), {a, b})

    def test_export_routes_selected_imported_and_bare_sources_into_one_file(self):
        source = P.NodesFile(ped_nodes=[P.PathNode(area_id=37, node_id=0, is_vehicle=False)], parsed_extras=True)
        zones = P.split_nodes_by_area([('nodes_ped', 800, 0, 1)])
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(N, '_selected_node_sources', return_value=(['owner'], zones)), \
             patch.object(N, '_scene_files', return_value=[('nodes37.dat', source, b'')]) as scene, \
             patch.object(N.settings, 'get', return_value=False):
            level, text = N.export_nodes(folder)
            scene.assert_called_once_with(['owner'])
            self.assertEqual(level, 'WARNING')
            self.assertIn('remain disconnected', text)
            self.assertEqual(len(P.read_nodes(str(Path(folder) / 'nodes37.dat')).ped_nodes), 2)

    def test_bare_export_does_not_erase_unselected_existing_source(self):
        zones = P.split_nodes_by_area([('nodes_ped', 800, 0, 1)])
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(N, '_selected_node_sources', return_value=([], zones)), \
             patch.object(N, '_scene_files', return_value=[]), \
             patch.object(N.settings, 'get', return_value=False):
            target = Path(folder) / 'NODES37.DAT'
            target.write_bytes(b'old-region')
            with self.assertRaisesRegex(ValueError, 'Select the imported source'):
                N.export_nodes(folder)
            self.assertEqual(target.read_bytes(), b'old-region')

    def test_selected_child_collects_whole_owner_once_and_splits_only_new_meshes(self):
        owner = SimpleNamespace(name='owner', parent=None, handle=1)
        child = SimpleNamespace(name='imported', parent=owner, handle=2, kind='MESH', path_type='nodes_vehicle')
        bare = SimpleNamespace(name='new', parent=None, handle=3, kind='MESH', path_type='nodes_ped', objectTransform='matrix')
        point = SimpleNamespace(x=800, y=0, z=1)
        class Vertex:
            def __mul__(self, matrix):
                if matrix != 'matrix':
                    raise AssertionError('Object transform was not applied')
                return point
        released = []
        rt = SimpleNamespace(selection=[child, owner, bare], getHandleByAnim=lambda n: n.handle,
            snapshotAsMesh=lambda node: 'snapshot', getNumVerts=lambda mesh: 1,
            getVert=lambda mesh, i: Vertex(), delete=released.append)
        with patch.object(N.S, '_rt', return_value=rt), \
             patch.object(N.S, 'get_data', side_effect=lambda n, k, d: {'raw': 'data'} if n is owner else d), \
             patch.object(N.S, 'get_field', return_value=0), \
             patch.object(N.S, 'node_kind', side_effect=lambda n: n.kind), \
             patch.object(N.W, 'path_type', side_effect=lambda n: n.path_type), \
             patch.object(N.settings, 'get', return_value=False):
            owners, zones = N._selected_node_sources()
        self.assertEqual(owners, [owner])
        self.assertEqual(len(zones[37].ped_nodes), 1)
        self.assertEqual(zones[37].ped_nodes[0].x, 800)
        self.assertEqual(released, ['snapshot'])

    def test_empty_selection_does_not_export_other_scene_regions(self):
        with patch.object(N, '_selected_node_sources', return_value=([], {})), \
             patch.object(N, '_scene_files', return_value=[]) as scene, \
             patch.object(N, 'write_node_batch') as write:
            level, _ = N.export_nodes('unused')
        scene.assert_called_once_with([])
        self.assertEqual(level, 'WARNING')
        write.assert_not_called()

    def test_unmodified_fla4_region_above_63_still_exports(self):
        source = P.NodesFile(parsed_extras=True, fla4=True)
        files, merged = N.prepare_node_merge([('NODES64.DAT', source, b'')], {})
        self.assertIn('NODES64.DAT', files)
        self.assertFalse(merged)
        self.assertTrue(files['NODES64.DAT'].fla4)

    def test_scene_collection_passes_complete_owner_to_compiled_adapter(self):
        import base64
        nf = region(37)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'NODES37.DAT'
            P.write_nodes(str(path), nf)
            raw = path.read_bytes()
        owner = SimpleNamespace(children=[])
        record = dict(filename='NODES37.DAT', raw=base64.b64encode(raw).decode('ascii'), source='source')
        with patch.object(N.S, '_rt', return_value=SimpleNamespace()), \
             patch.object(N.S, 'get_data', return_value=record), \
             patch('inu_max.ops.path_nodes_mesh.collect_owner', return_value=nf) as collect:
            files = N._scene_files([owner])
        self.assertIs(files[0][1], nf)
        self.assertEqual(files[0][2], raw)
        self.assertIs(collect.call_args.args[0], owner)
        self.assertEqual(collect.call_args.args[2], record)


if __name__ == '__main__':
    unittest.main()
