import copy
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from inu_gta_core import paths as P
from inu_gta_core.paths_graph import graph_edges, navi_address, validate_graph_batch
from inu_max.ops.path_nodes_mesh import identity_token, collect_graph, read_mesh, collect_owner
from inu_max.ops.node_tools import prepare_node_merge, write_node_batch


def road(peds=True):
    return P.NodesFile(vehicle_nodes=[
        P.PathNode(x=800, y=100, z=1, area_id=37, node_id=0, flags=1, node_type=1, path_width=8),
        P.PathNode(x=820, y=100, z=1, area_id=37, node_id=1, link_id=1, flags=1, node_type=1, path_width=8)],
        ped_nodes=[P.PathNode(x=805, y=110, z=1, area_id=37, node_id=2, is_vehicle=False)] if peds else [],
        navi_nodes=[P.NaviNode(x=810, y=100, area_id=37, node_id=0, dir_x=-100,
            flags=P.encode_navi_flags(left_lanes=0, right_lanes=2))],
        links=[P.PathLink(37, 1), P.PathLink(37, 0)],
        navi_links=[navi_address(37, 0)] * 2, link_lengths=[20, 20],
        path_intersections=[3, 4] + [7] * 192, parsed_extras=True)


def mesh(nodes, edges=()):
    points = [(n.x, n.y, getattr(n, 'z', 0)) for n in nodes]
    return dict(local=points[:], world=points[:], identities=[identity_token(i) for i in range(len(nodes))],
                selected=[False] * len(nodes), edges=set(edges))


def meshes(nf):
    count = len(nf.vehicle_nodes)
    edges = graph_edges(nf, 37)
    return dict(nodes_vehicle=mesh(nf.vehicle_nodes, [(a, b) for a, b in edges if b < count]),
                nodes_ped=mesh(nf.ped_nodes, [(a-count, b-count) for a, b in edges if a >= count]),
                nodes_navi=mesh(nf.navi_nodes))


def add(m, x, copied=None, y=100):
    point = (x, y, 1)
    m['local'].append(point)
    m['world'].append(point)
    m['identities'].append(m['identities'][copied] if copied is not None else (0, 0))
    m['selected'].append(True)


def full_files(edited):
    neighbour = P.NodesFile(ped_nodes=[P.PathNode(area_id=38, node_id=0, is_vehicle=False, flags=2)],
        links=[P.PathLink(37, 0), P.PathLink(37, 2)], navi_links=[0, 0], link_lengths=[11, 12],
        path_intersections=[1, 2] + [9]*192, parsed_extras=True)
    return [('nodes%d.dat' % area, edited if area == 37 else neighbour if area == 38
             else P.NodesFile(parsed_extras=True), b'') for area in range(64)]


class CompiledGraphTests(unittest.TestCase):
    def test_tokens_are_unique_and_exactly_representable_in_float32(self):
        tokens = [identity_token(i) for i in range(65536)]
        self.assertEqual(len(set(tokens)), 65536)
        for pair in tokens:
            self.assertNotEqual(pair, (0, 0))
            for value in pair:
                self.assertEqual(struct.unpack('<f', struct.pack('<f', value))[0], value)

    def test_unchanged_roundtrip_preserves_binary(self):
        nf = road()
        result = collect_graph(nf, meshes(nf), 37)
        self.assertFalse(result.topology_changed)
        self.assertEqual(result.node_remap, {})
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/'a.dat', Path(folder)/'b.dat'
            P.write_nodes(str(a), nf)
            P.write_nodes(str(b), result)
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_extrude_with_default_or_copied_identity_builds_navigation(self):
        for copied in (None, 1):
            nf = road()
            before = copy.deepcopy(nf)
            data = meshes(nf)
            add(data['nodes_vehicle'], 840, copied)
            data['nodes_vehicle']['edges'] = {(0, 1), (1, 2)}
            result = collect_graph(nf, data, 37)
            self.assertEqual(result.node_remap, {(37, 2): 3})
            self.assertEqual(graph_edges(result, 37), {(0, 1), (1, 2)})
            self.assertEqual(len(result.navi_nodes), 2)
            nav = result.navi_nodes[1]
            self.assertEqual((nav.x, nav.y, nav.node_id, nav.dir_x), (830, 100, 1, -100))
            self.assertEqual(nav.flags & 0x3F00, P.encode_navi_flags(left_lanes=1, right_lanes=1))
            validate_graph_batch({37: result})
            self.assertEqual(nf, before)
            with self.assertRaisesRegex(ValueError, 'all 64'):
                prepare_node_merge([('nodes37.dat', result, b'')], {})

    def test_reordered_vertices_keep_metadata_and_original_game_ids(self):
        nf = road()
        data = meshes(nf)
        m = data['nodes_vehicle']
        for key in ('local', 'world', 'identities', 'selected'):
            m[key].reverse()
        result = collect_graph(nf, data, 37)
        self.assertFalse(result.topology_changed)
        self.assertEqual([(n.x, n.node_id) for n in result.vehicle_nodes], [(800, 0), (820, 1)])

    def test_subdivision_retains_one_way_lanes_and_direction(self):
        nf = road(False)
        nf.vehicle_nodes[1].flags = 0
        nf.links = nf.links[:1]
        nf.navi_links = nf.navi_links[:1]
        nf.link_lengths = nf.link_lengths[:1]
        nf.path_intersections = [3] + [7]*192
        data = meshes(nf)
        add(data['nodes_vehicle'], 810, 0)
        data['nodes_vehicle']['edges'] = {(0, 2), (1, 2)}
        result = collect_graph(nf, data, 37)
        self.assertEqual(result.node_remap, {})
        self.assertEqual(result.links, [P.PathLink(37, 2), P.PathLink(37, 1)])
        self.assertEqual(len(result.navi_nodes), 3)
        self.assertTrue(all(n.flags == nf.navi_nodes[0].flags for n in result.navi_nodes[1:]))
        files, _ = prepare_node_merge([('nodes37.dat', result, b'')], {})
        validate_graph_batch({37: files['nodes37.dat']})

    def test_deletion_removes_neighbour_links_and_parallel_tail_entries(self):
        nf = road()
        data = meshes(nf)
        m = data['nodes_vehicle']
        for key in ('local', 'world', 'identities', 'selected'):
            m[key].pop(0)
        m['edges'] = set()
        result = collect_graph(nf, data, 37)
        self.assertEqual(result.node_remap, {(37, 0): None, (37, 1): 0, (37, 2): 1})
        files, _ = prepare_node_merge(full_files(result), {})
        neighbour = files['nodes38.dat']
        self.assertEqual(neighbour.links, [P.PathLink(37, 1)])
        self.assertEqual(neighbour.link_lengths, [12])
        self.assertEqual(neighbour.path_intersections, [2] + [9]*192)
        self.assertEqual(neighbour.ped_nodes[0].flags & 15, 1)
        self.assertEqual(files['nodes37.dat'].navi_nodes[0].area_id, 0xFFFF)
        with tempfile.TemporaryDirectory() as folder:
            write_node_batch(folder, files)
            validate_graph_batch({i: P.read_nodes(str(Path(folder)/('nodes%d.dat' % i))) for i in range(64)})

    def test_edited_graph_and_bare_merge_compose_original_to_final_ids(self):
        nf = road()
        data = meshes(nf)
        add(data['nodes_vehicle'], 840)
        data['nodes_vehicle']['edges'] = {(0, 1), (1, 2)}
        edited = collect_graph(nf, data, 37)
        zones = P.split_nodes_by_area([('nodes_vehicle', 860, 100, 1)])
        files, _ = prepare_node_merge(full_files(edited), zones)
        self.assertEqual(files['nodes37.dat'].ped_nodes[0].node_id, 4)
        self.assertEqual(files['nodes38.dat'].links[-1], P.PathLink(37, 4))
        validate_graph_batch({i: files['nodes%d.dat' % i] for i in range(64)})

    def test_edge_only_edit_and_bare_merge_reindexes_original_ped_reference(self):
        nf = road()
        data = meshes(nf)
        data['nodes_vehicle']['edges'] = set()
        edited = collect_graph(nf, data, 37)
        self.assertTrue(edited.topology_changed)
        self.assertFalse(edited.node_remap)
        files, _ = prepare_node_merge(full_files(edited), P.split_nodes_by_area([('nodes_vehicle', 840, 100, 1)]))
        self.assertEqual(files['nodes38.dat'].links[-1], P.PathLink(37, 3))

    def test_connected_road_can_be_created_in_empty_region(self):
        nf = P.NodesFile(parsed_extras=True)
        data = meshes(nf)
        add(data['nodes_vehicle'], 800)
        add(data['nodes_vehicle'], 820)
        data['nodes_vehicle']['edges'] = {(0, 1)}
        result = collect_graph(nf, data, 37)
        self.assertEqual(graph_edges(result, 37), {(0, 1)})
        self.assertEqual(len(result.navi_nodes), 1)
        files, _ = prepare_node_merge([('nodes37.dat', result, b'')], {})
        validate_graph_batch({37: files['nodes37.dat']})

    def test_ambiguous_duplicates_outside_region_and_navigation_edits_fail(self):
        for defect in ('duplicate', 'outside', 'navigation', 'missing'):
            nf = road()
            data = meshes(nf)
            if defect == 'duplicate':
                add(data['nodes_vehicle'], 820, 1)
                data['nodes_vehicle']['selected'][1] = True
            elif defect == 'outside':
                add(data['nodes_vehicle'], 100)
            elif defect == 'navigation':
                add(data['nodes_navi'], 840)
            else:
                del data['nodes_ped']
            with self.assertRaises(ValueError):
                collect_graph(nf, data, 37)

    def test_unknown_tail_blocks_topology_change_and_preserves_source(self):
        nf = road()
        nf.parsed_extras = False
        nf.extra_data = b'opaque'
        before = copy.deepcopy(nf)
        data = meshes(nf)
        data['nodes_vehicle']['edges'] = set()
        with self.assertRaisesRegex(ValueError, 'parsed link sections'):
            collect_graph(nf, data, 37)
        self.assertEqual(nf, before)

    def test_empty_and_zero_sector_padding_parse_but_nonzero_tail_is_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'nodes37.dat'
            for nf in (road(), P.NodesFile(parsed_extras=True)):
                P.write_nodes(str(path), nf)
                original = path.read_bytes()
                path.write_bytes(original + bytes(2048))
                result = P.read_nodes(str(path))
                self.assertTrue(result.parsed_extras)
                self.assertFalse(result.extra_data)
                path.write_bytes(original + b'unknown-nonzero')
                result = P.read_nodes(str(path))
                self.assertFalse(result.parsed_extras)
                self.assertTrue(result.extra_data.endswith(b'unknown-nonzero'))

    def test_foreign_stub_cannot_be_redirected_after_target_deletion(self):
        nf = road()
        data = meshes(nf)
        m = data['nodes_vehicle']
        for key in ('local', 'world', 'identities', 'selected'):
            m[key].pop(0)
        m['edges'] = set()
        edited = collect_graph(nf, data, 37)
        sources = full_files(edited)
        sources[38][1].ped_nodes[0].area_id = 37
        sources[38][1].ped_nodes[0].node_id = 0
        with self.assertRaisesRegex(ValueError, 'foreign stub'):
            prepare_node_merge(sources, {})

    def test_interpolated_two_channel_pair_does_not_become_an_old_identity(self):
        nf = road()
        data = meshes(nf)
        add(data['nodes_vehicle'], 810)
        a, b = identity_token(0), identity_token(1)
        data['nodes_vehicle']['identities'][-1] = tuple((x+y)/2 for x, y in zip(a, b))
        data['nodes_vehicle']['edges'] = {(0, 2), (1, 2)}
        result = collect_graph(nf, data, 37)
        self.assertEqual(result.original_node_indices, [0, 1, None, 2])

    def test_reimport_required_for_older_max_scene(self):
        with self.assertRaisesRegex(ValueError, 'Reimport'):
            collect_owner(SimpleNamespace(children=[]), road(), {'filename': 'nodes37.dat'})

    def test_live_poly_read_keeps_loose_edges_skips_dead_vertices_and_reads_vdata(self):
        poly = SimpleNamespace(GetNumEdges=lambda: 2,
            GetEdgeVertex=lambda edge, endpoint: {1: (1, 3), 2: (1, 2)}[edge][endpoint-1])
        class Point:
            x, y, z = 800, 100, 1
            def __mul__(self, matrix):
                if matrix != 'object-transform':
                    raise AssertionError('Object transform missing')
                return SimpleNamespace(x=810, y=100, z=1)
        op = SimpleNamespace(getVDataChannelSupport=lambda obj, channel: True,
            getDeadVerts=lambda obj: [2], getVertSelection=lambda obj: [3],
            getNumVerts=lambda obj: 3, getVert=lambda obj, index: Point(),
            getVDataValue=lambda obj, channel, index: identity_token(index-1)[channel-11],
            getDeadEdges=lambda obj: [2])
        rt = SimpleNamespace(polyop=op, classOf=lambda obj: 'poly', Editable_Poly='poly')
        node = SimpleNamespace(name='vehicle', baseObject=poly, modifiers=[], objectTransform='object-transform')
        with patch('inu_max.ops.path_nodes_mesh.S._rt', return_value=rt), \
             patch('inu_max.ops.path_nodes_mesh.S.get_data', return_value=dict(version=1, channels=[11, 12], source='source')):
            result = read_mesh(node, 'source')
        self.assertEqual(result['edges'], {(0, 1)})
        self.assertEqual(result['world'], [(810, 100, 1)] * 2)
        self.assertEqual(result['identities'], [identity_token(0), identity_token(2)])
        self.assertEqual(result['selected'], [False, True])

    def test_live_reader_rejects_modifier_stack_missing_channels_and_other_import(self):
        node = SimpleNamespace(name='vehicle', modifiers=['Edit Poly'])
        with patch('inu_max.ops.path_nodes_mesh.S._rt', return_value=SimpleNamespace()):
            with self.assertRaisesRegex(ValueError, 'directly'):
                read_mesh(node, 'source')
        node.modifiers = []
        node.baseObject = object()
        rt = SimpleNamespace(classOf=lambda obj: 'poly', Editable_Poly='poly',
            polyop=SimpleNamespace(getVDataChannelSupport=lambda obj, channel: False))
        with patch('inu_max.ops.path_nodes_mesh.S._rt', return_value=rt), \
             patch('inu_max.ops.path_nodes_mesh.S.get_data', return_value=dict(version=1, channels=[11, 12], source='source')):
            with self.assertRaisesRegex(ValueError, 'missing'):
                read_mesh(node, 'source')
            with self.assertRaisesRegex(ValueError, 'different import'):
                read_mesh(node, 'other')

    def test_rebuild_enforces_link_navi_and_quantized_xy_limits(self):
        # More than 15 neighbours cannot fit the low four flag bits.
        nf = P.NodesFile(parsed_extras=True)
        data = meshes(nf)
        for i in range(17):
            add(data['nodes_ped'], 800 + i)
        data['nodes_ped']['edges'] = {(0, i) for i in range(1, 17)}
        with self.assertRaisesRegex(ValueError, '15 outgoing'):
            collect_graph(nf, data, 37)
        nf = road(False)
        nf.navi_nodes *= 1024
        data = meshes(nf)
        add(data['nodes_vehicle'], 840)
        data['nodes_vehicle']['edges'] = {(0, 1), (1, 2)}
        with self.assertRaisesRegex(ValueError, 'capacity'):
            collect_graph(nf, data, 37)
        nf = P.NodesFile(parsed_extras=True)
        data = meshes(nf)
        add(data['nodes_vehicle'], 800)
        add(data['nodes_vehicle'], 800.01)
        data['nodes_vehicle']['edges'] = {(0, 1)}
        with self.assertRaisesRegex(ValueError, 'distinct XY'):
            collect_graph(nf, data, 37)

    def test_repeated_imports_of_same_file_cannot_be_mixed_even_if_unmodified(self):
        nf = road()
        with self.assertRaisesRegex(ValueError, 'one source'):
            prepare_node_merge([('nodes37.dat', nf, b''), ('NODES37.DAT', copy.deepcopy(nf), b'')], {})

    def test_fla4_conversion_with_bare_merge_reencodes_navigation_and_extended_positions(self):
        nf = road(False)
        zones = P.split_nodes_by_area([('nodes_vehicle', 840, 100, 1)], fla4=True)
        files, _ = prepare_node_merge([('nodes37.dat', nf, b'')], zones, fla4=True)
        result = files['nodes37.dat']
        self.assertTrue(result.fla4)
        self.assertEqual(result.navi_links, [navi_address(37, 0, True)] * 2)
        self.assertEqual(result.vehicle_nodes[-1].spawn_probability, 840 * 8)
        self.assertEqual(result.vehicle_nodes[0].speed_limit_kmh, 100 * 8)
        validate_graph_batch({37: result})



class VanillaCompiledGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive = Path('D:/Grand Theft Auto San Andreas/models/gta3.img')
        if not archive.is_file():
            raise unittest.SkipTest('Vanilla SA IMG is unavailable')
        cls.regions = {}
        with archive.open('rb') as stream, tempfile.TemporaryDirectory() as folder:
            magic, count = struct.unpack('<4sI', stream.read(8))
            if magic != b'VER2':
                raise ValueError('Expected VER2 vanilla archive')
            directory = stream.read(count * 32)
            for offset in range(0, len(directory), 32):
                sector, size, _, name = struct.unpack_from('<IHH24s', directory, offset)
                name = name.split(b'\0')[0].decode('ascii').lower()
                if name.startswith('nodes') and name.endswith('.dat') and name[5:-4].isdigit():
                    area = int(name[5:-4])
                    stream.seek(sector * 2048)
                    path = Path(folder)/name
                    path.write_bytes(stream.read(size * 2048))
                    cls.regions[area] = P.read_nodes(str(path))
        if set(cls.regions) != set(range(64)):
            raise ValueError('Expected all 64 vanilla node regions')

    def test_vanilla_all_regions_have_decoded_tails_and_roundtrip_unchanged(self):
        from inu_max.ops.path_nodes_mesh import collect_graph
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/'old.dat', Path(folder)/'new.dat'
            for area, nf in self.regions.items():
                self.assertTrue(nf.parsed_extras, area)
                data = self._meshes(nf, area)
                result = collect_graph(nf, data, area)
                self.assertFalse(result.topology_changed, area)
                P.write_nodes(str(a), nf)
                P.write_nodes(str(b), result)
                self.assertEqual(a.read_bytes(), b.read_bytes(), area)

    @staticmethod
    def _meshes(nf, area):
        edges = graph_edges(nf, area)
        count = len(nf.vehicle_nodes)
        return dict(nodes_vehicle=mesh(nf.vehicle_nodes, [(a, b) for a, b in edges if b < count]),
            nodes_ped=mesh(nf.ped_nodes, [(a-count, b-count) for a, b in edges if a >= count]),
            nodes_navi=mesh(nf.navi_nodes))

    def test_vanilla_branch_export_remaps_all_64_and_verifies_written_graph(self):
        nf = self.regions[37]
        data = self._meshes(nf, 37)
        first = nf.vehicle_nodes[0]
        m = data['nodes_vehicle']
        point = (first.x + 1, first.y, first.z)
        m['local'].append(point)
        m['world'].append(point)
        m['identities'].append(identity_token(0))
        m['selected'].append(True)
        m['edges'].add((0, len(m['world']) - 1))
        edited = collect_graph(nf, data, 37)
        sources = [('nodes%d.dat' % area, edited if area == 37 else source, b'')
                   for area, source in self.regions.items()]
        files, _ = prepare_node_merge(sources, {})
        result = files['nodes37.dat']
        self.assertEqual(len(result.vehicle_nodes), len(nf.vehicle_nodes) + 1)
        self.assertEqual(len(result.navi_nodes), len(nf.navi_nodes) + 1)
        with tempfile.TemporaryDirectory() as folder:
            write_node_batch(folder, files)
            restored = {area: P.read_nodes(str(Path(folder)/('nodes%d.dat' % area))) for area in range(64)}
            validate_graph_batch(restored)
            self.assertEqual(len(restored[37].vehicle_nodes), len(nf.vehicle_nodes) + 1)

    def test_vanilla_delete_own_point_and_validate_incoming_references(self):
        nf = self.regions[37]
        data = self._meshes(nf, 37)
        m = data['nodes_vehicle']
        for key in ('local', 'world', 'identities', 'selected'):
            m[key].pop(0)
        m['edges'] = {(a-1, b-1) for a, b in m['edges'] if a and b}
        edited = collect_graph(nf, data, 37)
        files, _ = prepare_node_merge([('nodes%d.dat' % area, edited if area == 37 else source, b'')
                    for area, source in self.regions.items()], {})
        self.assertEqual(len(files['nodes37.dat'].vehicle_nodes), len(nf.vehicle_nodes) - 1)
        validate_graph_batch({area: files['nodes%d.dat' % area] for area in range(64)})
        with tempfile.TemporaryDirectory() as folder:
            write_node_batch(folder, files)
            restored = {area: P.read_nodes(str(Path(folder)/('nodes%d.dat' % area))) for area in range(64)}
            validate_graph_batch(restored)
            self.assertEqual(len(restored[37].vehicle_nodes), len(nf.vehicle_nodes) - 1)


if __name__ == '__main__':
    unittest.main()
