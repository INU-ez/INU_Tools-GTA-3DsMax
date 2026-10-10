"""Synthetic UI checks in Max Batch; preferences are never saved."""
import json
import os
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from pymxs import runtime as rt
from inu_max import settings, i18n
from inu_max.adapter import material as M
from inu_max.i18n_native import localize_material, definition, _FILES, _ROLLOUTS, refresh_editor
from inu_max.ui.import_progress import FileImportProgress
from inu_max.qt import QtCore, QtWidgets

settings._save = lambda: None
result = {'success': False, 'materials': [], 'progress': []}
OUTPUT = ROOT/'dev/tests/e2e'

try:
    M.ensure_materials()
    app = QtWidgets.QApplication.instance()
    if os.environ.get('INU_TEST_GUI') == '1':
        rt.windows.showWindow(rt.windows.getMAXHWND(), rt.Name('maximize'))
        rt.windows.processPostedMessages()
    for lang in ('RU', 'EN'):
        settings._STATE['ui_language'] = lang
        with FileImportProgress(None, 80) as progress:
            assert progress.update_progress(35, 80, 'C:/models/Body.dff')
            app.processEvents()
            progress.grab().save(str(OUTPUT/('material_progress_'+lang+'.png')))
            assert progress.bar.value() == 35 and progress.bar.maximum() == 80
            assert progress.filename.full_text() == 'Body.dff'
            assert progress.width() >= 400
            assert progress.height() >= progress.minimumSizeHint().height()
            result['progress'].append({'language': lang, 'width': progress.width(),
                                       'height': progress.height(), 'label': progress.summary.text()})
            progress.cancel_button.click()
            assert not progress.update_progress(35, 80, 'C:/models/Body.dff')
    for name in _FILES:
        mat = getattr(rt, name)()
        rollout = getattr(mat, _ROLLOUTS.get(name, 'params'))
        if name in ('gta_mtl', 'inu_gta_mtl'):
            mat.matEffect = 4
            mat.p_srcblend = 5
            mat.p_destblend = 6
            mat.colhprIdx = 3
            mat.color = rt.Color(40, 80, 120)
            mat.alpha = 167
            mat.colormap = rt.Bitmaptexture(name='Reflection', fileName='C:/textures/Body.dds')
        before = M.props(mat)
        before_color = M.color(mat)
        settings._STATE['ui_language'] = 'RU'
        rt.createDialog(rollout, width=330, height=750)
        app.processEvents()
        rt.windows.processPostedMessages()
        assert localize_material(mat)
        if name == 'gta_mtl':
            assert str(rollout.infodkN.caption) == 'Нормали'
            assert str(rollout.infodkN2.caption) == 'Отражение'
        assert M.props(mat) == before
        assert M.color(mat) == before_color
        controls = definition(name)[1]
        for control, caption, _, _, kind, field in controls:
            widget = getattr(rollout, control)
            if kind == 'mapbutton' and field and getattr(mat, field) is None:
                assert str(widget.caption) == 'Нет', (name, control, widget.caption)
        if name in ('gta_mtl', 'inu_gta_mtl'):
            assert int(mat.matEffect) == 4 and int(mat.p_srcblend) == 5
            assert str(mat.colormap.name) == 'Reflection'
            result.setdefault('rollout_geometry', {})[name] = [
                {'name': control, 'position': str(getattr(rollout, control).pos),
                 'width': getattr(getattr(rollout, control), 'width', None)}
                for control, _, _, _, _, _ in controls]
            assert int(rollout.hwnd) != 0
            bitmap = rt.windows.snapshot(rollout.hwnd, captureScreenPixels=False, gammaCorrect=False)
            bitmap.filename = str(OUTPUT/('material_ui_'+name+'_RU.png'))
            rt.save(bitmap)
            rt.close(bitmap)
        settings._STATE['ui_language'] = 'EN'
        assert localize_material(mat)
        assert M.props(mat) == before
        assert M.color(mat) == before_color
        result['materials'].append(name)
        rt.destroyDialog(rollout)
    # The same overlay must be reached through the actual Slate editor poll.
    settings._STATE['ui_language'] = 'RU'
    rt.sme.Open()
    for classname in ('INU_GTA_Mtl', 'GTA_Mtl'):
        mat = getattr(rt, classname)()
        mat.matEffect = 4
        rt.sme.SetMtlInParamEditor(mat)
        app.processEvents()
        rt.windows.processPostedMessages()
        refresh_editor(force=True)
        rollout = mat.mainUI if classname == 'INU_GTA_Mtl' else mat.params
        assert str((rollout.reflection_label if classname == 'INU_GTA_Mtl' else rollout.prlbl).caption) == 'Отраж.'
        app.processEvents()
        rt.windows.processPostedMessages()
        for window in app.topLevelWidgets():
            if 'Slate Material Editor' in window.windowTitle():
                window.resize(1100, 1000)
                for dock in window.findChildren(QtWidgets.QDockWidget):
                    if 'Material Parameter Editor' in dock.windowTitle():
                        dock.setFloating(True)
                        dock.resize(430, 920)
                        dock.show()
                for splitter in window.findChildren(QtWidgets.QSplitter):
                    if splitter.orientation() == QtCore.Qt.Vertical and splitter.count() == 2:
                        splitter.setSizes([70, 850])
                app.processEvents()
                rt.windows.processPostedMessages()
                window.grab().save(str(OUTPUT/('material_ui_slate_'+classname+'_RU.png')))
        bitmap = rt.windows.snapshot(rollout.hwnd, captureScreenPixels=False, gammaCorrect=False)
        bitmap.filename = str(OUTPUT/('material_ui_editor_'+classname+'_RU.png'))
        rt.save(bitmap)
        rt.close(bitmap)
        for window in app.topLevelWidgets():
            if 'Slate Material Editor' in window.windowTitle():
                bars = [bar for bar in window.findChildren(QtWidgets.QScrollBar)
                        if bar.orientation() == QtCore.Qt.Vertical and bar.maximum() > 0]
                result.setdefault('editor_scrollbars', {})[classname] = len(bars)
                for bar in bars:
                    bar.setValue(bar.maximum())
                app.processEvents()
                rt.windows.processPostedMessages()
                bitmap = rt.windows.snapshot(rollout.hwnd, captureScreenPixels=False, gammaCorrect=False)
                bitmap.filename = str(OUTPUT/('material_ui_editor_'+classname+'_bottom_RU.png'))
                rt.save(bitmap)
                rt.close(bitmap)
    rt.sme.Close()
    result['success'] = True
except Exception:
    result['error'] = traceback.format_exc()
(OUTPUT/'material_ui_runtime_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
