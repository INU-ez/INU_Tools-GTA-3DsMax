"""Cross-version Qt selection and isolated Autodesk bundle installation."""
import ast
import builtins
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from inu_max import setup as SU


class QtCompatibilityTests(unittest.TestCase):
    def binding(self, qt6, year=None):
        def event_loop(self):
            return 42
        classes = {n: type(n, (), {'exec_': event_loop}) for n in
                   ('QDialog', 'QMenu', 'QMessageBox', 'QApplication', 'QEventLoop')}
        widgets = NS(**{n: c for n, c in classes.items() if n != 'QEventLoop'},
                     QAction=object(), QActionGroup=object(), QShortcut=object())
        qt = NS(QtCore=NS(QEventLoop=classes['QEventLoop']), QtGui=NS(), QtWidgets=widgets)
        real_import = builtins.__import__
        def importing(name, *args, **kwargs):
            if name == 'pymxs':
                if year is None:
                    raise ModuleNotFoundError('No host')
                return NS(runtime=NS(maxVersion=lambda: [(year - 1998) * 1000]))
            if name == 'PySide6':
                if qt6:
                    return qt
                raise ModuleNotFoundError("No module named 'PySide6'")
            if name == 'PySide2':
                return qt
            return real_import(name, *args, **kwargs)
        scope = {}
        with patch('builtins.__import__', side_effect=importing):
            exec(compile(Path('inu_max/qt.py').read_text(encoding='utf-8'), '<qt>', 'exec'), scope)
        return qt, scope

    def test_qt5_exec_and_action_aliases(self):
        qt, scope = self.binding(False)
        self.assertEqual(scope['BINDING'], 'PySide2')
        for cls in (qt.QtCore.QEventLoop, qt.QtWidgets.QDialog, qt.QtWidgets.QMenu,
                    qt.QtWidgets.QMessageBox, qt.QtWidgets.QApplication):
            self.assertEqual(cls().exec(), 42)
        self.assertIs(qt.QtGui.QAction, qt.QtWidgets.QAction)
        self.assertEqual(scope['mouse_position'](NS(localPos=lambda: 5)), 5)

    def test_qt6_is_preferred_and_position_uses_new_api(self):
        _, scope = self.binding(True)
        self.assertEqual(scope['BINDING'], 'PySide6')
        self.assertEqual(scope['mouse_position'](NS(position=lambda: 7)), 7)

    def test_old_host_never_loads_external_qt6(self):
        for year in (2023, 2024):
            _, scope = self.binding(True, year=year)
            self.assertEqual(scope['BINDING'], 'PySide2')

    def test_all_production_imports_use_compatibility_module(self):
        for p in Path('inu_max').rglob('*.py'):
            if p.name == 'qt.py':
                continue
            tree = ast.parse(p.read_text(encoding='utf-8-sig'))
            for n in ast.walk(tree):
                if isinstance(n, ast.ImportFrom):
                    self.assertNotIn(n.module, ('PySide2', 'PySide6'), str(p))


class InstallerTests(unittest.TestCase):
    def test_max_year_detection_for_each_release(self):
        for year in SU.SUPPORTED_YEARS:
            with patch.object(SU, '_rt', return_value=NS(maxVersion=lambda: [(year - 1998) * 1000])):
                self.assertEqual(SU.max_year(), year)

    def test_dependency_paths_are_distinct_for_each_python(self):
        with patch.object(SU, 'bundle_dir', return_value='bundle'):
            paths = {SU.libs_dir(v) for v in ((3, 9), (3, 10), (3, 11), (3, 13))}
            self.assertEqual(len(paths), 4)
            self.assertTrue(SU.libs_dir((3, 9)).endswith('py39'))
        self.assertIn('sys.version_info[:2]', SU._startup_ms())
        self.assertIn('sys.version_info[:2]', Path('inu_boot.py').read_text(encoding='utf-8'))

    def test_manifest_dlls_are_year_specific_and_menu_is_2025_plus(self):
        tree = ET.fromstring(SU._package_xml(2023, False, [2024, 2026]))
        requirements = tree.find('RuntimeRequirements')
        self.assertEqual(requirements.get('SeriesMin'), '2023')
        self.assertEqual(requirements.get('SeriesMax'), '2026')
        for comp in tree.findall('Components'):
            rr = comp.find('RuntimeRequirements')
            module = comp.find('ComponentEntry').get('ModuleName')
            if module.endswith('.dli'):
                year = module.split('/')[2]
                self.assertEqual(rr.get('SeriesMin'), year)
                self.assertEqual(rr.get('SeriesMax'), year)
            elif module.endswith('.mnx'):
                self.assertEqual(rr.get('SeriesMin'), '2025')
                self.assertEqual(rr.get('SeriesMax'), '2026')
            else:
                self.assertEqual(rr.get('SeriesMin'), '2023')

    def test_installing_another_year_preserves_available_native_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'src'
            bundle = Path(tmp) / 'bundle'
            for year in (2024, 2026):
                p = root / 'plugins' / str(year) / SU.PLUGIN_NAME
                p.parent.mkdir(parents=True)
                p.write_bytes(str(year).encode())
            with patch.object(SU, 'code_root', return_value=str(root)), \
                 patch.object(SU, 'bundle_dir', return_value=str(bundle)):
                SU.install(mode='link', year=2026, with_numpy=False, log=lambda s: None)
                SU.install(mode='link', year=2023, with_numpy=False, log=lambda s: None)
            manifest = json.loads((bundle / 'Contents' / 'install.json').read_text())
            self.assertEqual(manifest['plugins'], {'2024': True, '2026': True})
            self.assertFalse(manifest['plugin'])
            self.assertEqual((bundle / 'Contents' / '2026' / SU.PLUGIN_NAME).read_bytes(), b'2026')
            self.assertTrue((bundle / 'Contents' / 'scripts' / 'INU_MenuLegacy.ms').is_file())

    def test_unsupported_year_fails_before_writing(self):
        with patch.object(SU, 'bundle_dir') as bundle:
            with self.assertRaises(ValueError):
                SU.install(year=2022)
            bundle.assert_not_called()

    def test_old_bundle_requires_upgrade_but_year_switch_does_not(self):
        manifest = {'version': SU.VERSION, 'mode': 'copy', 'year': 2026, 'plugins': {}}
        with patch.object(SU, '_manifest', return_value=manifest), \
             patch.object(SU.os.path, 'isfile', return_value=True), \
             patch.object(SU, 'max_year', return_value=2023), \
             patch.object(SU, 'plugin_source', return_value=None):
            self.assertEqual(SU.status()['state'], 'UPDATE')
            manifest['schema'] = SU.INSTALL_SCHEMA
            self.assertEqual(SU.status()['state'], 'INSTALLED')


class MissingPipTests(unittest.TestCase):
    def test_missing_pip_uses_verified_temporary_wheel_and_cleans_up(self):
        import hashlib
        import io
        data = b'test wheel'
        metadata = {'urls': [{'filename': 'pip-25.3-py3-none-any.whl',
                             'url': 'https://files.pythonhosted.org/pip.whl',
                             'digests': {'sha256': hashlib.sha256(data).hexdigest()}}]}
        failed = Mock(stdout=True, returncode=1)
        failed.communicate.return_value = (b'No module named pip',)
        success = Mock(stdout=True, returncode=0)
        success.communicate.return_value = (b'Installed numpy',)
        with tempfile.TemporaryDirectory() as destination:
            with patch.object(SU, 'max_python', return_value='Max Python.exe'), \
                 patch.object(SU, 'libs_dir', return_value=destination), \
                 patch.object(SU.subprocess, 'Popen', side_effect=[failed, success]) as popen, \
                 patch.object(SU.urllib.request, 'urlopen', side_effect=[
                     io.BytesIO(json.dumps(metadata).encode()), io.BytesIO(data)]):
                ok, _ = SU.install_numpy(log=lambda line: None)
                self.assertTrue(ok)
                command = popen.call_args_list[1].args[0]
                self.assertEqual(command[0], 'Max Python.exe')
                self.assertIn('--target', command)
                self.assertFalse(os.path.exists(command[3]))
            if destination in SU.sys.path:
                SU.sys.path.remove(destination)

    def test_network_error_is_reported(self):
        failed = Mock(stdout=True, returncode=1)
        failed.communicate.return_value = (b"No module named 'pip'",)
        with patch.object(SU, 'max_python', return_value='Max Python.exe'), \
             patch.object(SU.subprocess, 'Popen', return_value=failed), \
             patch.object(SU.urllib.request, 'urlopen', side_effect=OSError('offline')):
            self.assertEqual(SU.install_numpy(log=lambda line: None), (False, 'offline'))


class MenuBootstrapTests(unittest.TestCase):
    def test_every_macro_resolves_global_launcher_and_recovers_startup(self):
        macros = SU._macros_mcr()
        self.assertEqual(macros.count('global INU_launch'), len(SU.WINDOWS))
        self.assertEqual(macros.count('if doesFileExist startup do fileIn startup'), len(SU.WINDOWS))
        self.assertIn(r'Contents\\scripts\\INU_Startup.ms', macros)
        self.assertNotIn('is not loaded: restart', macros)
        self.assertNotIn('messageBox', macros)
        self.assertIn('[INU Tools] Startup failed:', macros)
        launcher = Path('inu_launcher.ms').read_text(encoding='utf-8')
        self.assertIn('global INU_launch', launcher)
        self.assertIn('global INU_boot', launcher)
