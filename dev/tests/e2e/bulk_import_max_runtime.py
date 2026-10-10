"""Import 80 map DFFs per material mode in an isolated Max Batch scene."""
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from pymxs import runtime as rt
from inu_gta_core.img import read_directory, extract_file
from inu_gta_core.dff import read_dff
from inu_max import diag, settings
from inu_max.adapter.texture import write_png
from inu_max.qt import QtCore, QtWidgets
from inu_max.ui.panel import INUToolsPanel
from inu_max.ui.import_progress import FileImportProgress

REPORT = ROOT/'dev/tests/e2e/bulk_import_runtime_result.json'
GAME = Path(os.environ.get('INU_TEST_GAME_ROOT', 'D:/Grand Theft Auto San Andreas'))
result = {'success': False, 'runs': []}
settings._save = lambda: None


def save():
    REPORT.write_text(json.dumps(result, indent=2), encoding='utf-8')


try:
    archive = str(GAME/'models/gta3.img')
    entries = [entry for entry in read_directory(archive)
               if entry.name.lower().endswith('.dff')
               and any(part in entry.name.lower() for part in ('road', 'land', 'build', 'block', 'a51_', 'int', 'airport', 'ap_', 'cunt', 'vgn', 'vge', 'vgw', 'ce_', 'cn_', 'cj_', 'ab_', 'kb_'))
               and not entry.name.lower().startswith(('lod', 'sb'))][:80]
    assert len(entries) == 80
    with tempfile.TemporaryDirectory(prefix='inu_bulk_import_') as folder:
        directory = Path(folder)
        paths = []
        names = set()
        for entry in entries:
            data = extract_file(archive, entry.name)
            clump = read_dff(data)
            assert not any(geometry.skin for geometry in clump.geometries)
            for geometry in clump.geometries:
                for material in geometry.materials:
                    if material.texture and material.texture.name:
                        names.add(material.texture.name)
            path = directory/entry.name
            path.write_bytes(data)
            paths.append(str(path))
        # Loose PNG fixtures exercise Auto TXD and native viewport bitmap loading.
        for name in names:
            write_png(str(directory/(name+'.png')), bytes((96, 144, 192, 255))*256, 16, 16)
        settings._STATE.update(auto_txd=True, import_weld_sharpen=False)
        original_update = FileImportProgress.update_progress
        updates = []
        def observed_update(dialog, done, total, path):
            updates.append((done, total, Path(path).name))
            result = original_update(dialog, done, total, path)
            if done == 40:
                dialog.grab().save(str(ROOT/'dev/tests/e2e/material_progress_bulk_RU.png'))
            return result
        with patch.object(diag, 'path', return_value=str(directory/'import_trace.txt')), \
                patch('faulthandler.dump_traceback_later') as watchdog, \
                patch.object(FileImportProgress, 'update_progress', observed_update):
            for mode in ('STANDARD', 'GTA'):
                rt.resetMaxFile(rt.Name('noPrompt'))
                settings._STATE.update(import_material_type=mode, ui_language='RU')
                panel = INUToolsPanel(mode='dff')
                panel.show()
                start = time.perf_counter()
                panel._import_paths(paths)
                QtWidgets.QApplication.instance().processEvents()
                boxes = panel.findChildren(QtWidgets.QMessageBox)
                report = next(box.text() for box in boxes if 'Import' in box.windowTitle() or 'Импорт' in box.windowTitle())
                lines = report.splitlines()
                assert len(lines) == 80, report
                assert not any('error' in line.lower() or 'ошибка' in line.lower() for line in lines), report
                assert len(rt.objects) >= 80
                assert updates[-1][0:2] == (80, 80)
                trace = Path(diag.path()).read_text(encoding='utf-8')
                assert 'DFF 80/80: '+entries[-1].name in trace
                watchdog.assert_not_called()
                result['runs'].append({'material': mode, 'models': 80,
                                       'objects': len(rt.objects),
                                       'seconds': round(time.perf_counter()-start, 2)})
                save()
                # Wait through all post-import timers using Qt's event loop.
                loop = QtCore.QEventLoop()
                QtCore.QTimer.singleShot(42500, loop.quit)
                loop.exec()
                assert diag._FILE is None
                watchdog.assert_not_called()
                panel.close()
                panel.deleteLater()
                QtWidgets.QApplication.instance().processEvents()
            rt.resetMaxFile(rt.Name('noPrompt'))
            def cancel_update(dialog, done, total, path):
                if done == 3:
                    dialog.cancel_button.click()
                return original_update(dialog, done, total, path)
            with patch.object(FileImportProgress, 'update_progress', cancel_update):
                panel = INUToolsPanel(mode='dff')
                panel.show()
                panel._import_paths(paths[:8])
                QtWidgets.QApplication.instance().processEvents()
                assert len(rt.objects) > 0
                boxes = panel.findChildren(QtWidgets.QMessageBox)
                assert any('3/8' in box.text() for box in boxes)
                assert any(sum(line.startswith('DFF ') for line in box.text().splitlines()) == 3
                           for box in boxes)
                result['cancelled_after'] = 3
                panel.close()
                diag.stop()
        result.update(success=True, texture_fixtures=len(names), max_version=list(rt.maxVersion()))
except Exception:
    result['error'] = traceback.format_exc()
finally:
    diag.stop()
    save()
