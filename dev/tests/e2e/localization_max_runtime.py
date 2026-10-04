"""Run in Max Batch; synthetic widgets only, never saves user preferences."""
import json
import re
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from pymxs import runtime as rt
from inu_max import i18n, settings
from inu_max.qt import QtCore, QtWidgets
from inu_max.ui.panel import INUToolsPanel, _WIN_META
from inu_max.ui.widgets import ElideLabel, RolloutHeader
import inu_boot

settings._save = lambda: None
rt.INU_LAUNCHER_NO_OPEN = True
result = {}
try:
    settings._STATE['ui_language'] = 'RU'
    inu_boot.register_launcher(str(ROOT))
    assert str(rt.INU_Tools_util.b_paths.text) == 'Пути'
    assert str(rt.INU_Tools_util.languageSelect.caption) == 'Язык'
    app = QtWidgets.QApplication.instance()
    missing = set()
    sizes = {}
    for mode in _WIN_META:
        panel = INUToolsPanel(mode=mode)
        panel.show()
        app.processEvents()
        i18n._SERVICE.refresh()
        sizes[mode] = [panel.width(), panel.height()]
        for w in [panel]+panel.findChildren(QtWidgets.QWidget):
            texts = [w.toolTip()]
            if isinstance(w, (QtWidgets.QLabel, QtWidgets.QAbstractButton)):
                texts.append(getattr(w, 'full_text', w.text)())
            if isinstance(w, QtWidgets.QGroupBox):texts.append(w.title())
            if isinstance(w, RolloutHeader):texts.append(w.title)
            if isinstance(w, QtWidgets.QLineEdit):texts.append(w.placeholderText())
            if isinstance(w, QtWidgets.QComboBox) and not w.property('inu_i18n_data'):
                texts.extend(w.itemText(i) for i in range(w.count()))
            for text in texts:
                if text and re.search(r'[A-Za-z]{3}', text) and not re.search(r'[А-Яа-я]', text):
                    missing.add(text)
        if mode in ('dff', 'launcher', 'ifp', 'mat'):
            panel.grab().save(str(ROOT/('dev/tests/e2e/localization_'+mode+'.png')))
        panel.close()
        panel.deleteLater()
        app.processEvents()
    result.update(missing=sorted(missing), sizes=sizes)
    from inu_max.ui.file_dialog import INUFileDialog
    from inu_max.ui.dff_options import ImportOptions, ExportOptions
    for options in (ImportOptions(), ExportOptions()):
        is_export = isinstance(options, ExportOptions)
        dialog = INUFileDialog(options=options, start_dir=str(ROOT/'dev/tests'), filename='Body',
                              mode='save' if is_export else 'open',
                              accept_label='Export' if is_export else 'Import')
        dialog.show()
        app.processEvents()
        i18n._SERVICE.refresh()
        assert dialog._model.headerData(0, QtCore.Qt.Horizontal) == i18n.tr('Name')
        assert dialog._model.headerData(0, QtCore.Qt.Horizontal) != 'Name'
        assert dialog._name.currentText() == 'Body'
        for spinner in dialog.findChildren(QtWidgets.QSpinBox):
            assert spinner.prefix() not in ('Day: ', 'Night: ')
        dialog.grab().save(str(ROOT/'dev/tests/e2e/localization_file.png'))
        dialog.reject()
        app.processEvents()
    parent = QtWidgets.QWidget()
    parent.setObjectName('inuLocalizationTest')
    parent.setWindowTitle('INU Tools')
    label = ElideLabel('Selected: 5 mesh(es)', parent)
    label.resize(50, 20)
    data = QtWidgets.QLineEdit('Body', parent)
    data.setPlaceholderText('File name:')
    spinner = QtWidgets.QSpinBox(parent)
    spinner.setPrefix('Day: ')
    spinner.setValue(14)
    combo = QtWidgets.QComboBox(parent)
    combo.setProperty('inu_i18n_data', True)
    combo.addItems(['Import', 'Body'])
    parent.show()
    i18n._SERVICE.refresh()
    assert label.full_text() == 'Выбрано сеток: 5'
    assert spinner.prefix() == 'День: ' and spinner.value() == 14
    assert data.text() == 'Body' and combo.itemText(0) == 'Import'
    i18n.set_language('EN')
    assert label.full_text() == 'Selected: 5 mesh(es)'
    assert spinner.prefix() == 'Day: ' and spinner.value() == 14
    assert data.text() == 'Body' and combo.itemText(0) == 'Import'
    inu_boot.register_launcher(str(ROOT))
    assert str(rt.INU_Tools_util.b_paths.text) == 'Paths'
    assert str(rt.INU_Tools_util.languageSelect.caption) == 'Language'
    import importlib
    importlib.reload(i18n)
    i18n.install()
    i18n.set_language('RU')
    assert label.full_text() == 'Выбрано сеток: 5'
    i18n.set_language('EN')
    parent.close()
    result.update(success=True, missing=sorted(missing), sizes=sizes)
except Exception:
    result.update(success=False, error=traceback.format_exc())
(ROOT/'dev/tests/e2e/localization_runtime_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
