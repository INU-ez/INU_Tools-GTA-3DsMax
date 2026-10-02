"""Max IMG bridge regressions, using real temporary VER1/VER2 archives."""
import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from inu_gta_core import img
from inu_gta_core.col import ColModel, ColSphere, Vec3, write_col
from inu_gta_core.col_library import col_chunks

# Import settings against an isolated directory; never write the user's settings.
with tempfile.TemporaryDirectory() as _settings_dir:
    with patch.dict(os.environ, {'LOCALAPPDATA': _settings_dir}):
        from inu_max.ops import img_ops as ops
from inu_max.ops import dff_export as DE
from inu_max.adapter import scene_read as sr


class Rec:
    def __init__(self, handle, kind, base, archive='', name=None, **props):
        self.handle, self.kind, self.base = handle, kind, base
        self.name = name or base
        self.props = dict(img_target_file=archive, **props)
        self.node = SimpleNamespace(inode=SimpleNamespace(handle=handle), children=[])

    def get(self, key, default):
        return self.props.get(key, default)

    def put(self, props):
        self.props.update(props)


class Scene:
    def __init__(self, recs):
        self.recs = recs
        self.by_handle = {r.handle: r for r in recs}

    def model_type(self, r):
        return r.kind, r.base

    def model_name(self, r):
        return r.base

    def is_col(self, r):
        return r.get('type', '').upper() in ('COL', 'SHA')

    def rec(self, node):
        return self.by_handle.get(node.inode.handle)

    def main_of(self, r):
        return r

    def pick(self, nodes):
        return [self.rec(n) for n in nodes]

    def models(self):
        return [r for r in self.recs if not self.is_col(r)]


@contextlib.contextmanager
def host(recs, selected, game='SA', ides=()):
    sc = Scene(recs)
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(ops.ML, 'Scene', return_value=sc))
        stack.enter_context(patch.object(ops, '_selected', return_value=[r.node for r in selected]))
        stack.enter_context(patch.object(ops.settings, 'get',
                                        side_effect=lambda k, d=None: game if k == 'game' else d))
        stack.enter_context(patch.object(ops, '_txd_ide_files', return_value=list(ides)))
        stack.enter_context(patch.object(ops, '_undo', side_effect=lambda _: contextlib.nullcontext()))
        stack.enter_context(patch.object(ops, '_drop_caches'))
        yield sc


def col_record(name, mid=0, radius=1.0):
    return write_col([ColModel(model_name=name, model_id=mid,
                               spheres=[ColSphere(center=Vec3(), radius=radius)])])


def archive(root, version, name='test', **files):
    path = str(root / (name + '.img'))
    img.create_img(path, version=version)
    with img.ImgWriter(path) as writer:
        for entry, data in files.items():
            writer.add(entry, data)
    return path


def entries(path):
    return {e.name.lower() for e in img.read_directory(path)}


def item(dff, lod=None, **changes):
    data = dict(dff=dff, lod=lod, name=dff.base if dff else 'LODhouse',
                lod_name='LODhouse' if lod else '', own='', txd='house', lod_txd='house',
                col_meshes=[], col_prims=[], inc_dff=dff is not None, inc_lod=lod is not None,
                inc_col=False, stub_col=False, stub_lod=False, inc_txd=False)
    data.update(changes)
    return data


class RemoveTests(unittest.TestCase):
    def test_game_ide_sources_use_startup_dat_and_explicit_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'data'
            data.mkdir()
            loaded = data / 'loaded.ide'
            listed = root / 'listed.ide'
            box = root / 'box.ide'
            unused = data / 'unused.ide'
            for path in (loaded, listed, box, unused):
                path.write_text('objs\nend\n')
            (data / 'gta3.dat').write_text('IDE data/loaded.ide\n')
            values = {'game_root': str(root), 'ide_sync_list': [str(listed)],
                      'ide_path': str(box)}
            with patch.object(ops.settings, 'get', side_effect=lambda k, d=None: values.get(k, d)):
                paths = ops._txd_ide_files()
            self.assertEqual(set(map(Path, paths)), {loaded, listed, box})

    def test_real_max_name_normalization_resolves_lod_copies(self):
        from inu_max.adapter.link_scene import Rec as MaxRec
        records = [
            MaxRec(None, 1, 'house_DFF', {'inu_lod_object': '2'}, 1, 0),
            MaxRec(None, 2, 'LODhouse_LOD', {}, 2, 0),
            MaxRec(None, 3, 'LODhouse_LOD001', {}, 3, 0),
        ]
        sc = ops.ML.Scene(recs=records)
        names, kinds, owners, *_ = ops._remove_scene(sc)
        self.assertEqual(names, {1: 'house', 2: 'LODhouse', 3: 'LODhouse'})
        self.assertEqual(kinds[3], 'lod')
        self.assertIs(owners['lodhouse'], records[0])

    def test_selected_lod_uses_own_archive_and_leaves_hd_resources(self):
        for version in (1, 2):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                hd_arch = archive(root, version, 'hd', **{
                    'house.dff': b'HD', 'house.txd': b'TXD',
                    'house.col': col_record('house'), 'LODhouse.dff': b'old LOD'})
                lo_arch = archive(root, version, 'lod', **{
                    'LODhouse.dff': b'LOD', 'lodhouse.txd': b'LOD TXD'})
                hd = Rec(1, 'DFF', 'house', hd_arch, lod_object=2)
                lod = Rec(2, 'LOD', 'house', lo_arch, name='LODhouse', txd_name='lodhouse')
                hd_before = Path(hd_arch).read_bytes()
                with host([hd, lod], [lod]):
                    todo, _notes = ops._remove_plan()
                    self.assertEqual(set(todo), {lo_arch})
                    self.assertEqual(todo[lo_arch]['libs'], {})
                    self.assertEqual(todo[lo_arch]['recs'], [lod])
                    ops.remove_from_img()
                self.assertEqual(entries(lo_arch), set())
                self.assertEqual(Path(hd_arch).read_bytes(), hd_before)
                self.assertEqual(hd.get('img_target_file', ''), hd_arch)
                self.assertEqual(lod.get('img_target_file', ''), '')

    def test_lod_without_own_archive_keeps_shared_txd(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = archive(Path(tmp), 2, **{
                'house.dff': b'HD', 'LODhouse.dff': b'LOD', 'house.txd': b'TXD',
                'house.col': col_record('house')})
            hd = Rec(1, 'DFF', 'house', path, lod_object=2)
            for own in ('', str(Path(tmp) / 'missing.img')):
                lod = Rec(2, 'LOD', 'house', own, name='LODhouse')
                with host([hd, lod], [lod]):
                    todo, _notes = ops._remove_plan()
                self.assertEqual(todo[path]['entries'], ['LODhouse.dff'])
                self.assertEqual(todo[path]['libs'], {})
                self.assertEqual(todo[path]['kept_txd'], [('house.txd', 'house', 1)])

    def test_lod_owner_is_found_by_resource_name_for_scene_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = archive(Path(tmp), 2, **{
                'house.dff': b'HD', 'LODhouse.dff': b'LOD', 'house.txd': b'TXD'})
            hd = Rec(1, 'DFF', 'house', path, lod_object=2)
            original = Rec(2, 'LOD', 'house', path, name='LODhouse')
            copy = Rec(3, 'LOD', 'house', '', name='LODhouse_LOD001')
            with host([hd, original, copy], [copy]):
                todo, _notes = ops._remove_plan()
            self.assertEqual(todo[path]['entries'], ['LODhouse.dff'])

    def test_hd_keeps_unselected_lod_and_its_shared_txd(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = archive(Path(tmp), 2, **{
                'house.dff': b'HD', 'LODhouse.dff': b'LOD', 'house.txd': b'TXD'})
            hd = Rec(1, 'DFF', 'house', path, lod_object=2)
            lod = Rec(2, 'LOD', 'house', path, name='LODhouse')
            with host([hd, lod], [hd]):
                todo, _notes = ops._remove_plan()
                self.assertEqual(todo[path]['entries'], ['house.dff'])
                self.assertEqual(todo[path]['kept_lod'], ['LODhouse'])
                shown = Mock(return_value=False)
                ops.remove_from_img(confirm=shown)
                self.assertIn('select the LOD', '\n'.join(shown.call_args.args[1]))
                ops.remove_from_img()
            self.assertEqual(entries(path), {'lodhouse.dff', 'house.txd'})
            self.assertEqual(lod.get('img_target_file', ''), path)

    def test_untextured_model_and_own_scene_ide_keep_txd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = archive(root, 2, **{'house.dff': b'HD', 'shared.txd': b'TXD'})
            hd = Rec(1, 'DFF', 'house', path, txd_name='shared')
            bare = Rec(2, 'COL', 'bare', txd_name='shared')
            with host([hd, bare], [hd]):
                todo, _notes = ops._remove_plan()
            self.assertEqual(todo[path]['entries'], ['house.dff'])
            self.assertEqual(todo[path]['kept_txd'][0][1], 'bare')
            ide = root / 'own.ide'
            ide.write_text('objs\n50, other, shared, 1, 100, 0\nend\n')
            tagged_col = Rec(3, 'COL', 'other', type='COL', ide_linked=True,
                             ide_target_file=str(ide))
            with host([hd, tagged_col], [hd]):
                todo, _notes = ops._remove_plan()
            self.assertEqual(todo[path]['entries'], ['house.dff'])
            self.assertEqual(todo[path]['kept_txd'][0][1], 'other')

    def test_ide_txd_parent_and_same_named_remaining_dff_keep_txd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = archive(root, 2, **{'house.dff': b'HD', 'shared.txd': b'TXD'})
            hd = Rec(1, 'DFF', 'house', path, txd_name='shared')
            ide = root / 'parent.ide'
            ide.write_text('txdp\nchild, shared\nend\n')
            with host([hd], [hd], ides=[str(ide)]):
                todo, _notes = ops._remove_plan()
            self.assertEqual(todo[path]['entries'], ['house.dff'])
            self.assertEqual(todo[path]['kept_txd'][0][1], 'txdp child')
            with img.ImgWriter(path) as writer:
                writer.add('shared.dff', b'other model')
            with host([hd], [hd]):
                todo, _notes = ops._remove_plan()
            self.assertEqual(todo[path]['entries'], ['house.dff'])
            self.assertEqual(todo[path]['kept_txd'][0][1], 'shared')

    def test_shared_lod_txd_is_kept_for_another_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = archive(Path(tmp), 2, **{
                'house.dff': b'HD', 'LODhouse.dff': b'LOD', 'lodtx.txd': b'TXD'})
            hd = Rec(1, 'DFF', 'house', path, lod_object=2)
            lod = Rec(2, 'LOD', 'house', path, name='LODhouse', txd_name='lodtx')
            other = Rec(3, 'DFF', 'other', txd_name='lodtx')
            with host([hd, lod, other], [lod]):
                todo, _notes = ops._remove_plan()
            self.assertEqual(todo[path]['entries'], ['LODhouse.dff'])
            self.assertEqual(todo[path]['kept_txd'], [('lodtx.txd', 'other', 1)])

    def test_missing_dff_keeps_txd_and_collision_even_when_col_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = archive(Path(tmp), 2, **{
                'house.txd': b'TXD', 'house.col': col_record('house')})
            hd = Rec(1, 'DFF', 'house', path)
            col = Rec(2, 'COL', 'house', type='COL')
            before = Path(path).read_bytes()
            with host([hd, col], [hd, col]):
                todo, notes = ops._remove_plan()
                self.assertEqual(todo[path]['entries'], [])
                self.assertEqual(todo[path]['libs'], {})
                self.assertTrue(any('not in test.img' in n for n in notes))
                ops.remove_from_img()
            self.assertEqual(Path(path).read_bytes(), before)
            self.assertEqual(hd.get('img_target_file', ''), path)

    def test_col_only_removes_record_and_keeps_foreign_record(self):
        for version in (1, 2):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                other = col_record('other', 25)
                path = archive(Path(tmp), version, **{
                    'house.dff': b'HD', 'house.txd': b'TXD',
                    'library.col': col_record('house') + other + b'\0' * 3000})
                hd = Rec(1, 'DFF', 'house', path)
                col = Rec(2, 'COL', 'house', type='COL')
                with host([hd, col], [col]):
                    ops.remove_from_img()
                self.assertEqual(entries(path), {'house.dff', 'house.txd', 'library.col'})
                with img.ImgReader(path) as rd:
                    data = rd.read('library.col')
                self.assertEqual([c[2] for c in col_chunks(data)], ['other'])
                self.assertEqual(data[:len(other)], other)
                self.assertLess(len(data) - len(other), img.SECTOR)
                self.assertEqual(hd.get('img_target_file', ''), path)

    def test_removal_clears_all_same_archive_copies_but_not_other_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = archive(root, 2, 'a', **{'house.dff': b'HD'})
            b = archive(root, 2, 'b', **{'house.dff': b'other HD'})
            first = Rec(1, 'DFF', 'house', a)
            copy = Rec(2, 'DFF', 'house', a, name='house_DFF001')
            other = Rec(3, 'DFF', 'house', b)
            with host([first, copy, other], [first]):
                ops.remove_from_img()
            self.assertEqual(first.get('img_target_file', ''), '')
            self.assertEqual(copy.get('img_target_file', ''), '')
            self.assertEqual(other.get('img_target_file', ''), b)
            self.assertIn('house.dff', entries(b))

    def test_partial_failure_clears_only_dff_that_was_removed(self):
        from inu_gta_core import img_remove
        with tempfile.TemporaryDirectory() as tmp:
            path = archive(Path(tmp), 2, **{'house.dff': b'HD', 'tree.dff': b'TREE'})
            hd = Rec(1, 'DFF', 'house', path)
            tree = Rec(2, 'DFF', 'tree', path)
            def partial(arch, files, libs, done):
                img.remove_file(arch, 'house.dff')
                done.append('house.dff')
                raise PermissionError('locked')
            with host([hd, tree], [hd, tree]), patch.object(img_remove, 'remove_entries', partial):
                level, text = ops.remove_from_img()
            self.assertEqual(level, 'WARNING')
            self.assertIn('locked', text)
            self.assertEqual(hd.get('img_target_file', ''), '')
            self.assertEqual(tree.get('img_target_file', ''), path)


class ExportTests(unittest.TestCase):
    def test_orphan_lod_uses_its_model_name_for_txd(self):
        lod = Rec(1, 'LOD', 'house', name='LODhouse')
        with host([lod], [lod]):
            result = ops.plan()[0]
        self.assertEqual(result['name'], 'LODhouse')
        self.assertEqual(result['txd'], 'LODhouse')
        self.assertEqual(result['lod_txd'], 'LODhouse')
        bad = []
        ops._check_name('.txd', bad)
        self.assertEqual(bad, ['.txd'])

    def test_orphan_lod_writes_named_txd_into_real_archives(self):
        for game, version in (('SA', 2), ('VC', 1)):
            with self.subTest(game=game), tempfile.TemporaryDirectory() as tmp:
                path = archive(Path(tmp), version)
                lod = Rec(1, 'LOD', 'house', name='LODhouse')
                with host([lod], [lod], game=game), \
                     patch.object(DE, '_opts', return_value={'game': game, 'pipeline': 'NONE'}), \
                     patch.object(DE, '_nodes_for', return_value=[]), \
                     patch.object(DE, 'dff_bytes', return_value=b'LOD'), \
                     patch.object(DE, 'txd_data', return_value=(b'TXD', 'test')) as txd, \
                     patch.object(sr, 'full_result', side_effect=contextlib.nullcontext):
                    level, _text = ops.export_to_img(ops.plan(), path)
                self.assertEqual(level, 'INFO')
                self.assertEqual(entries(path), {'lodhouse.dff', 'lodhouse.txd'})
                self.assertEqual(txd.call_args.args[0], 'LODhouse.txd')
                self.assertEqual(lod.get('img_target_file', ''), path)

    @contextlib.contextmanager
    def export_host(self, recs):
        with host(recs, recs), \
             patch.object(DE, '_opts', return_value={'game': 'SA', 'pipeline': 'NONE', 'col_version': 3}), \
             patch.object(DE, '_nodes_for', return_value=[]), \
             patch.object(DE, '_fx_entries', return_value=[]), \
             patch.object(DE, 'dff_bytes', return_value=b'DFF'), \
             patch.object(sr, 'full_result', side_effect=contextlib.nullcontext):
            yield

    def test_shared_txd_uses_all_models_and_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = archive(Path(tmp), 2, 'a')
            b = archive(Path(tmp), 2, 'b', **{'shared.txd': b'OLD'})
            ra, rb = Rec(1, 'DFF', 'a', a), Rec(2, 'DFF', 'b', b)
            with self.export_host([ra, rb]), \
                 patch.object(DE, 'txd_data', return_value=(b'COMPLETE', 'merged')) as build:
                level, text = ops.export_to_img([item(ra, own=a, txd='Shared', inc_txd=True),
                                                item(rb, own=b, txd='shared', inc_txd=True)], a)
            self.assertEqual(level, 'INFO', text)
            self.assertNotIn('shared.txd', entries(a))
            self.assertEqual(build.call_count, 1)
            self.assertEqual(build.call_args.args[1], [ra.node, rb.node])
            with img.ImgReader(b) as reader:
                self.assertTrue(reader.read('shared.txd').startswith(b'COMPLETE'))

    def test_lod_archive_receives_complete_shared_txd(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = archive(Path(tmp), 2, 'a'), archive(Path(tmp), 2, 'b')
            hd, lod = Rec(1, 'DFF', 'house', a), Rec(2, 'LOD', 'house', b)
            with self.export_host([hd, lod]), \
                 patch.object(DE, 'txd_data', return_value=(b'TXD', 'test')) as build:
                level, text = ops.export_to_img([item(hd, lod, own=a, txd='shared',
                                                      lod_txd='shared', inc_txd=True)], a)
            self.assertEqual(level, 'INFO', text)
            self.assertEqual(entries(a), {'house.dff', 'shared.txd'})
            self.assertEqual(entries(b), {'lodhouse.dff', 'shared.txd'})
            self.assertTrue(all(c.args[1] == [hd.node, lod.node] for c in build.call_args_list))
            self.assertEqual(lod.get('img_target_file', ''), b)

    def test_rejected_shared_target_never_creates_shadow_and_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = archive(Path(tmp), 2, 'a')
            b = archive(Path(tmp), 1, 'b', **{'shared.txd': b'ORIGINAL'})
            before = Path(b).read_bytes()
            ra, rb = Rec(1, 'DFF', 'a', a), Rec(2, 'DFF', 'b', b)
            with self.export_host([ra, rb]), patch.object(DE, 'txd_data') as build:
                level, text = ops.export_to_img([item(ra, own=a, txd='shared', inc_txd=True),
                                                item(rb, own=b, txd='shared', inc_txd=True)], a)
            self.assertEqual(level, 'ERROR', text)
            build.assert_not_called()
            self.assertNotIn('shared.txd', entries(a))
            self.assertEqual(Path(b).read_bytes(), before)

    def test_shared_lod_without_own_archive_keeps_all_owner_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = archive(Path(tmp), 2, 'a'), archive(Path(tmp), 2, 'b')
            first, second = Rec(1, 'DFF', 'first', a), Rec(2, 'DFF', 'second', b)
            lod = Rec(3, 'LOD', 'shared')
            with self.export_host([first, second, lod]):
                for _ in range(2):
                    level, text = ops.export_to_img([item(first, lod, own=a),
                                                    item(second, lod, own=b)], a)
                    self.assertEqual(level, 'INFO', text)
                    self.assertEqual(lod.get('img_target_file', ''), '')
            self.assertIn('lodhouse.dff', entries(a))
            self.assertIn('lodhouse.dff', entries(b))

    def test_missing_explicit_lod_destination_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = archive(Path(tmp), 2)
            hd = Rec(1, 'DFF', 'house', a)
            lod = Rec(2, 'LOD', 'house', str(Path(tmp) / 'missing.img'))
            with self.export_host([hd, lod]):
                level, text = ops.export_to_img([item(hd, lod, own=a)], a)
            self.assertEqual(level, 'ERROR', text)
            self.assertNotIn('lodhouse.dff', entries(a))

    def test_failed_txd_build_leaves_archive_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = archive(Path(tmp), 2, **{'original.dff': b'KEEP'})
            hd = Rec(1, 'DFF', 'house', a)
            before = Path(a).read_bytes()
            with self.export_host([hd]), patch.object(DE, 'txd_data', return_value=(None, 'failed')):
                level, text = ops.export_to_img([item(hd, own=a, inc_txd=True)], a)
            self.assertEqual(level, 'ERROR', text)
            self.assertEqual(Path(a).read_bytes(), before)

    def test_col_is_updated_in_other_models_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = archive(Path(tmp), 2, 'a')
            foreign = col_record('foreign', 99)
            b = archive(Path(tmp), 2, 'b', **{'library.col': col_record('house', 7) + foreign})
            hd, other = Rec(1, 'DFF', 'house', a), Rec(2, 'DFF', 'other', b)
            with self.export_host([hd, other]), \
                 patch.object(DE, '_col_model', return_value=ColModel(model_name='house')):
                level, text = ops.export_to_img([item(hd, own=a, inc_col=True), item(other, own=b)], a)
            self.assertEqual(level, 'INFO', text)
            self.assertNotIn('house.col', entries(a))
            with img.ImgReader(b) as reader:
                data = reader.read('library.col')
            chunks = col_chunks(data)
            self.assertEqual(chunks[0][3], 7)
            self.assertEqual(data[chunks[1][0]:chunks[1][1]], foreign)

    def test_unused_txd_name_does_not_block_collision_only_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = archive(Path(tmp), 2)
            data = item(Rec(1, 'DFF', 'house'), inc_dff=False, inc_col=True,
                        inc_txd=True, txd='', lod_txd='')
            with patch.object(DE, '_opts', return_value={'game': 'SA'}), \
                 patch.object(ops, '_export_archive', return_value={'line': 'OK', 'recs': []}), \
                 patch.object(ops, '_drop_caches'), \
                 patch.object(sr, 'full_result', side_effect=contextlib.nullcontext):
                level, _text = ops.export_to_img([data], path)
            self.assertEqual(level, 'INFO')

    def test_ver1_dir_write_lock_is_checked_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = archive(Path(tmp), 1, **{'original.dff': b'keep'})
            dir_path = str(Path(path).with_suffix('.dir'))
            original_open = open
            def busy_dir(name, mode='r', *args, **kwargs):
                if str(name) == dir_path and mode == 'r+b':
                    raise PermissionError('directory locked')
                return original_open(name, mode, *args, **kwargs)
            with patch.object(DE, '_opts', return_value={'game': 'VC'}), \
                 patch('builtins.open', side_effect=busy_dir), \
                 patch.object(ops, '_export_archive') as build:
                level, text = ops.export_to_img([item(Rec(1, 'DFF', 'house'))], path)
            self.assertEqual(level, 'ERROR')
            self.assertIn('close the game', text)
            build.assert_not_called()

    def test_truncated_header_reports_error_and_keeps_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'broken.img')
            Path(path).write_bytes(b'VER2')
            with patch.object(DE, '_opts', return_value={'game': 'SA'}), \
                 patch.object(ops, '_export_archive') as build:
                level, _text = ops.export_to_img([item(Rec(1, 'DFF', 'house'))], path)
            self.assertEqual(level, 'ERROR')
            self.assertEqual(Path(path).read_bytes(), b'VER2')
            build.assert_not_called()

    def test_mismatched_game_refused_before_build_or_scene_access(self):
        for game, version in (('SA', 1), ('III', 2), ('VC', 2)):
            with self.subTest(game=game), tempfile.TemporaryDirectory() as tmp:
                path = archive(Path(tmp), version, **{'original.dff': b'keep'})
                before = Path(path).read_bytes()
                dff = Rec(1, 'DFF', 'house')
                with patch.object(DE, '_opts', return_value={'game': game}), \
                     patch.object(ops, '_export_archive') as build, \
                     patch.object(sr, 'full_result') as scene_access:
                    level, text = ops.export_to_img([item(dff)], path)
                self.assertEqual(level, 'ERROR')
                self.assertIn('archive is VER', text)
                build.assert_not_called()
                scene_access.assert_not_called()
                self.assertEqual(Path(path).read_bytes(), before)

    def test_empty_archive_initialized_for_export_game(self):
        for game, version in (('SA', 2), ('III', 1), ('VC', 1)):
            with self.subTest(game=game), tempfile.TemporaryDirectory() as tmp:
                path = str(Path(tmp) / 'empty.img')
                Path(path).touch()
                with patch.object(DE, '_opts', return_value={'game': game}), \
                     patch.object(ops, '_export_archive', return_value={'line': 'OK', 'recs': []}), \
                     patch.object(ops, '_drop_caches'), \
                     patch.object(sr, 'full_result', side_effect=contextlib.nullcontext):
                    level, _text = ops.export_to_img([item(Rec(1, 'DFF', 'house'))], path)
                self.assertEqual(level, 'INFO')
                self.assertEqual(img.detect_img_version(path), version)
                self.assertEqual(img.read_directory(path), [])

    def test_invalid_or_locked_archive_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'invalid.img')
            Path(path).write_bytes(b'not an IMG')
            with patch.object(DE, '_opts', return_value={'game': 'SA'}), \
                 patch.object(ops, '_export_archive') as build:
                level, text = ops.export_to_img([item(Rec(1, 'DFF', 'house'))], path)
            self.assertEqual(level, 'ERROR')
            self.assertIn('neither VER1 nor VER2', text)
            build.assert_not_called()
            with patch.object(DE, '_opts', return_value={'game': 'SA'}), \
                 patch.object(ops, '_prepare_archive', side_effect=PermissionError), \
                 patch.object(ops, '_export_archive') as build:
                level, text = ops.export_to_img([item(Rec(1, 'DFF', 'house'))], path)
            self.assertEqual(level, 'ERROR')
            self.assertIn('close the game', text)
            build.assert_not_called()

    def test_existing_named_col_library_is_extended_once_and_foreign_bytes_kept(self):
        for order in (('x', 'a'), ('a', 'x')):
            with self.subTest(order=order), tempfile.TemporaryDirectory() as tmp:
                a, b = col_record('a', 12), col_record('b', 34)
                path = archive(Path(tmp), 2, **{'X.COL': a + b + b'\0' * 3000})
                def make_model(name, *args, **kwargs):
                    return ColModel(model_name=name,
                                    spheres=[ColSphere(center=Vec3(), radius=2.0)])
                exporter = SimpleNamespace(_col_model=make_model)
                items = [item(Rec(i + 1, 'DFF', name), inc_dff=False, inc_col=True)
                         for i, name in enumerate(order)]
                with patch.object(img.ImgWriter, 'add', autospec=True,
                                  wraps=None, side_effect=img.ImgWriter.add) as add:
                    ops._export_archive(path, items, {'game': 'SA', 'col_version': 3},
                                        [], exporter, None, img)
                self.assertEqual([call.args[1] for call in add.call_args_list], ['X.COL'])
                with img.ImgReader(path) as rd:
                    data = rd.read('X.COL')
                chunks = col_chunks(data)
                self.assertEqual([c[2] for c in chunks], ['a', 'b', 'x'])
                self.assertEqual(chunks[0][3], 12)
                self.assertEqual(data[chunks[1][0]:chunks[1][1]], b)
                self.assertLess(len(data) - chunks[-1][1], img.SECTOR)

    def test_col_splice_drops_padding_and_keeps_other_record_exactly(self):
        first, second = col_record('a', 10), col_record('b', 20)
        out, hits, left = ops.col_splice(first + second + b'\0' * 3000, 'a', lambda _: None)
        self.assertEqual((out, hits, left), (second, 1, 1))


if __name__ == '__main__':
    unittest.main()
