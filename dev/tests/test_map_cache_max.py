"""Map resource/cache regressions with real IMG files and a mocked Max progress UI."""
import contextlib
import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from inu_gta_core import img, map_files as MF
from dev.tests.test_img_ops_max import archive

with patch.dict(sys.modules, {'pymxs': SimpleNamespace(runtime=Mock())}):
    MT = importlib.import_module('inu_max.ops.map_tab')


class MapCacheTests(unittest.TestCase):
    @contextlib.contextmanager
    def extraction(self, root, archive_path, decode):
        rt = Mock()
        rt.progressUpdate.return_value = True
        rt.getProgressCancel.return_value = False
        with patch.dict(sys.modules, {'pymxs': SimpleNamespace(runtime=rt)}), \
             patch.object(MT, 'pymxs', SimpleNamespace(runtime=rt)), \
             patch.object(MT, 'cache_dir', return_value=str(root / 'cache')), \
             patch.object(MT, '_root', return_value=str(root)), \
             patch.object(MT, '_archives', return_value=[archive_path]), \
             patch.object(MT.settings, 'get', side_effect=lambda k, d=None: d), \
             patch('inu_gta_core.txd.read_txd', side_effect=decode):
            yield

    def test_deleted_png_is_restored_and_unchanged_archive_is_not_decoded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = archive(root, 2, **{'house.txd': b'TXD', 'house.dff': b'DFF'})
            tex = SimpleNamespace(name='walls', width=1, height=1,
                                  pixels=b'\x01\x02\x03\xff', platform_id=9)
            decode = Mock(return_value=[tex])
            with self.extraction(root, a, decode):
                self.assertEqual(MT.extract_textures()[0], 'INFO')
                png = root / 'cache' / 'textures' / 'walls.png'
                self.assertTrue(png.is_file())
                self.assertEqual(MT.extract_textures()[0], 'INFO')
                self.assertEqual(decode.call_count, 1)
                png.unlink()
                self.assertEqual(MT.extract_textures()[0], 'INFO')
                self.assertTrue(png.is_file())
                self.assertEqual(decode.call_count, 2)
            idx = MF.load_index(str(root / 'cache'))
            self.assertEqual(len(idx['txd']['house.txd']), 4)
            self.assertEqual(idx['txd_png']['house.txd'], ['walls.png'])

    def test_same_offset_size_resource_replacement_refreshes_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = archive(root, 2, **{'house.dff': b'OLD'})
            with self.extraction(root, a, Mock(return_value=[])):
                self.assertEqual(MT.extract_textures()[0], 'INFO')
                entry = img.read_directory(a)[0]
                before = MF.load_index(str(root / 'cache'))['files']['house.dff']
                with open(a, 'r+b') as stream:
                    stream.seek(entry.offset * img.SECTOR)
                    stream.write(b'NEW')
                st = os.stat(a)
                os.utime(a, ns=(st.st_atime_ns, st.st_mtime_ns + 1000000))
                self.assertEqual(MT.extract_textures()[0], 'INFO')
                after = MF.load_index(str(root / 'cache'))['files']['house.dff']
            self.assertEqual(before[:3], after[:3])
            self.assertNotEqual(before[3], after[3])
            self.assertTrue((root / 'cache' / 'house.dff').read_bytes().startswith(b'NEW'))

    def test_region_files_does_not_let_install_folder_named_maps_choose_region(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'Maps' / 'Game'
            path = root / 'data' / 'maps' / 'LA' / 'lan.ipl'
            path.parent.mkdir(parents=True)
            path.write_text('inst\nend\n')
            resources = SimpleNamespace(ipl_paths=[str(path)])
            entry = SimpleNamespace(name='lan_stream0.ipl', offset=1, size=2)
            with patch.object(MT, '_root', return_value=str(root)), \
                 patch.object(MT, '_archives', return_value=['a']), \
                 patch('inu_gta_core.gta_dat.find_all_resources', return_value=resources), \
                 patch('inu_gta_core.img.read_directory', return_value=[entry]):
                text, binary = MT.region_files('LA')
            self.assertEqual(text, [str(path)])
            self.assertEqual(binary, [(entry.name, 'a', entry)])

    def test_empty_first_record_does_not_shadow_real_data(self):
        empty = SimpleNamespace(name='house.dff', offset=0, size=0)
        live = SimpleNamespace(name='house.dff', offset=5, size=1)
        winner = MF.extract_winners(['a', 'b'], lambda a: [empty] if a == 'a' else [live])
        self.assertEqual(winner['house.dff'], ('b', live))

    def test_errors_are_logged_and_do_not_stop_other_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cache' / 'x.dff').mkdir(parents=True)
            a = archive(root, 2, **{'x.dff': b'X', 'y.dff': b'Y',
                                   'good.txd': b'GOOD', 'empty.txd': b'EMPTY', 'bad.txd': b'BAD'})
            def decode(data):
                if data.startswith(b'BAD'):
                    raise ValueError('broken TXD')
                return [SimpleNamespace(name='' if data.startswith(b'EMPTY') else 'wall',
                                        width=1, height=1, pixels=b'\x01\x02\x03\xff', platform_id=9)]
            with self.extraction(root, a, decode):
                self.assertEqual(MT.extract_textures()[0], 'WARNING')
                cache = root / 'cache'
                self.assertTrue((cache / 'y.dff').is_file())
                self.assertTrue((cache / 'textures' / 'wall.png').is_file())
                self.assertFalse((cache / 'textures' / 'tex.png').exists())
                skips = (cache / '_extract_skipped.log').read_text(encoding='utf-8')
                self.assertIn('no_name', skips)
                self.assertIn('parse_error', skips)
                errors = (cache / '_txd_errors.log').read_text(encoding='utf-8')
                self.assertIn('bad.txd', errors)
                self.assertIn('x.dff', errors)
                self.assertNotIn('bad.txd', MF.load_index(str(cache))['txd'])
                (cache / '_txd_errors.log').write_text('old run', encoding='utf-8')
                MT.extract_textures()
                errors = (cache / '_txd_errors.log').read_text(encoding='utf-8')
                self.assertIn('bad.txd', errors)
                self.assertNotIn('old run', errors)

    def test_png_write_failure_is_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = archive(root, 2, **{'house.txd': b'TXD'})
            tex = SimpleNamespace(name='wall', width=1, height=1,
                                  pixels=b'\x01\x02\x03\xff', platform_id=9)
            with self.extraction(root, a, Mock(return_value=[tex])):
                with patch('inu_max.adapter.texture.write_png', side_effect=OSError('disk failure')):
                    self.assertEqual(MT.extract_textures()[0], 'WARNING')
                self.assertNotIn('house.txd', MF.load_index(str(root / 'cache'))['txd'])
                self.assertEqual(MT.extract_textures()[0], 'INFO')
                self.assertTrue((root / 'cache' / 'textures' / 'wall.png').is_file())

    def test_profiler_enabled_and_disabled_preserve_extraction(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                a = archive(root, 2, **{'house.dff': b'DFF'})
                with self.extraction(root, a, Mock(return_value=[])), \
                     patch.object(MT.settings, 'get', side_effect=lambda k, d=None: enabled if k == 'profile_enabled' else d), \
                     patch('builtins.print'):
                    self.assertEqual(MT.extract_textures()[0], 'INFO')
                log = root / 'cache' / '_profile.log'
                self.assertEqual(log.exists(), enabled)
                if enabled:
                    report = log.read_text(encoding='utf-8')
                    self.assertIn('PROFILER: Extract Resources', report)
                    self.assertIn('extract DFF/COL', report)
                self.assertTrue((root / 'cache' / 'house.dff').is_file())


if __name__ == '__main__':
    unittest.main()
