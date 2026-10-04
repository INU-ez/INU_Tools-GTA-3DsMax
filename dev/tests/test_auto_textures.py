import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from inu_max.adapter import texture as T


class AutoTextureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dff = str(self.root / 'model.dff')
        self.cache = self.root / 'model_textures'

    def image(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture')
        return str(path)

    def test_all_image_formats_and_case_insensitive_names(self):
        expected = {f'tex{i}': self.image(f'Textures/TEX{i}{ext.upper()}')
                    for i, ext in enumerate(T._IMAGE_EXTENSIONS)}
        with patch.object(T, '_txd_index') as txds:
            self.assertEqual(T.build_tex_map(self.dff, set(expected)), expected)
        txds.assert_not_called()

    def test_nearest_folder_wins_then_png_before_dds(self):
        expected = self.image('body.DDS')
        self.image('Textures/body.png')
        self.assertEqual(T._loose_tex_map(str(self.root), {'body'}, str(self.cache)), {'body': expected})
        expected = self.image('body.png')
        self.assertEqual(T._loose_tex_map(str(self.root), {'body'}, str(self.cache)), {'body': expected})

    def test_texture_name_with_extension_or_path(self):
        expected = self.image('textures/BODY.TGA')
        names = {'body.tga', r'textures\body.tga'}
        self.assertEqual(T._loose_tex_map(str(self.root), names, str(self.cache)),
                         dict.fromkeys(names, expected))

    def test_exact_filename_wins_over_another_format_in_same_folder(self):
        self.image('body.png')
        expected = self.image('body.dds')
        self.assertEqual(T._loose_tex_map(str(self.root), {'body.dds'}, str(self.cache)),
                         {'body.dds': expected})

    def test_loose_image_overrides_old_extracted_png(self):
        self.image('model_textures/body.png')
        expected = self.image('body.dds')
        with patch.object(T, '_txd_index') as txds:
            self.assertEqual(T.build_tex_map(self.dff, {'body'})['body'], expected)
        txds.assert_not_called()

    def test_existing_current_png_cache_still_works(self):
        expected = self.image('model_textures/body.png')
        T._ver_mark(str(self.cache))
        with patch.object(T, '_txd_index') as txds:
            self.assertEqual(T.build_tex_map(self.dff, {'body'})['body'], expected)
        txds.assert_not_called()

    def test_txd_fills_missing_textures_without_replacing_loose_images(self):
        expected = self.image('body.tga')
        txd = str(self.root / 'different.txd')
        def extract(path, out_dir, **kwargs):
            self.image('model_textures/body.png')
            self.image('model_textures/detail.png')
        with patch.object(T, '_txd_index', return_value=[(txd, {'body', 'detail'})]), \
             patch.object(T, 'extract_txd_file', side_effect=extract) as decode:
            result = T.build_tex_map(self.dff, {'body', 'detail'})
        self.assertEqual(result['body'], expected)
        self.assertEqual(result['detail'], str(self.cache / 'detail.png'))
        decode.assert_called_once_with(txd, str(self.cache), only_swapped=False)

    def test_old_cache_colour_refresh_is_preserved_for_missing_images(self):
        self.image('model_textures/body.png')
        txd = str(self.root / 'model.txd')
        with patch.object(T, '_txd_index', return_value=[(txd, {'body'})]), \
             patch.object(T, 'extract_txd_file') as decode:
            T.build_tex_map(self.dff, {'body'})
        decode.assert_called_once_with(txd, str(self.cache), only_swapped=True)

    def test_directories_non_images_and_scan_limit(self):
        (self.root / 'body.png').mkdir()
        self.image('body.txt')
        self.image('a.bmp')
        self.image('nested/body.png')
        self.assertEqual(T._loose_tex_map(str(self.root), {'body'}, str(self.cache), cap=1), {})
        self.assertEqual(T._loose_tex_map(str(self.root), {'body'}, str(self.cache)),
                         {'body': str(self.root / 'nested/body.png')})


if __name__ == '__main__':
    unittest.main()
