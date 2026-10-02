import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from inu_gta_core import fxp
from inu_max.ops import fx_write as W
from inu_max.adapter.fx import PARTICLE_DEFAULTS


class FXWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'models').mkdir()
        self.path = self.root / 'models/effects.fxp'
        self.project = fxp.FXFile(systems=[W.blank_system('original')])
        fxp.write_fxp(str(self.path), self.project)
        self.before = self.path.read_bytes()

    def test_create_delete_and_original_backup(self):
        W.create(str(self.root), 'new_effect')
        self.assertEqual(fxp.read_fxp(str(self.path)).find('new_effect').name, 'new_effect')
        self.assertEqual(Path(str(self.path) + '.bak').read_bytes(), self.before)
        W.delete(str(self.root), 'new_effect')
        self.assertIsNone(fxp.read_fxp(str(self.path)).find('new_effect'))
        self.assertEqual(Path(str(self.path) + '.bak').read_bytes(), self.before)

    def test_failed_replace_preserves_original(self):
        with patch.object(W.os, 'replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                W.create(str(self.root), 'new')
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertEqual(list((self.root / 'models').glob('.inu_fx_*')), [])

    def test_invalid_curve_preserves_file(self):
        with self.assertRaises(ValueError):
            W.write_curve(str(self.root), 'original', 0, 'COLOUR.RED', [(0, 1), (0, 2)])
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_curve_aligns_other_channels_and_preserves_values(self):
        W.write_curve(str(self.root), 'original', 0, 'COLOUR.RED', [(0, 10), (.5, 20), (1, 30)])
        info = fxp.read_fxp(str(self.path)).find('original').emitters[0].info('COLOUR')
        self.assertTrue(all(len(c.keys) == 3 for c in info.curves.values()))
        self.assertEqual(info.curves['ALPHA'].sample(.5), 127.5)

    def test_clone_keeps_source_and_other_emitters(self):
        source = self.project.systems[0]
        source.emitters.append(W.blank_system('other').emitters[0])
        W._curve(source.emitters[0], 'EMRATE', 'RATE', [(0, 10), (.5, 30), (1, 10)])
        fxp.write_fxp(str(self.path), self.project)
        values = dict(PARTICLE_DEFAULTS, **W._sample(source.emitters[0]))
        values['particle_life'] = 2
        W.save(str(self.root), 'original', 'clone', 0, values)
        project = fxp.read_fxp(str(self.path))
        self.assertEqual(project.find('original').emitters[0].info('EMLIFE').curves['LIFE'].sample(0), 1)
        clone = project.find('clone')
        self.assertEqual(len(clone.emitters), 2)
        self.assertEqual(clone.emitters[0].info('EMLIFE').curves['LIFE'].sample(0), 2)
        self.assertEqual(len(clone.emitters[0].info('EMRATE').curves['RATE'].keys), 3)
        self.assertEqual(clone.emitters[1], source.emitters[1])

    def test_missing_and_duplicate_names_are_rejected(self):
        for name in ('original', 'bad name', 'кириллица'):
            with self.assertRaises(ValueError):
                W.create(str(self.root), name)
        self.assertEqual(self.path.read_bytes(), self.before)


if __name__ == '__main__':
    unittest.main()
