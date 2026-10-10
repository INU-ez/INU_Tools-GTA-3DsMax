"""Bounded UI updates between files; no nested exec or worker scene access."""
import os

from ..qt import QtCore, QtWidgets
from ..i18n import tr, install
from .style import qss, C
from .widgets import ElideLabel


class FileImportProgress(QtWidgets.QDialog):
    def __init__(self, parent, total):
        super().__init__(parent)
        self.setObjectName('inuImportProgress')
        self.setWindowTitle(tr('INU: Import'))
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setStyleSheet(qss())
        self.setMinimumWidth(400)
        self.cancelled = False
        layout = QtWidgets.QVBoxLayout(self)
        self.summary = QtWidgets.QLabel()
        self.filename = ElideLabel('')
        self.filename.setProperty('inu_i18n_data', True)
        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, total)
        self.bar.setValue(0)
        self.bar.setFormat('%p%')
        self.bar.setStyleSheet('QProgressBar { border: 1px solid '+C['grpbd']+
                              '; background: '+C['ctl']+'; text-align: center; height: 18px; }'
                              'QProgressBar::chunk { background: '+C['green']+'; }')
        self.cancel_button = QtWidgets.QPushButton(tr('Cancel'))
        self.cancel_button.setToolTip(tr('Stop after the current file. Imported objects remain in the scene.'))
        self.cancel_button.clicked.connect(self.reject)
        for widget in (self.summary, self.filename, self.bar):
            layout.addWidget(widget)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        install()

    def reject(self):
        # Closing the dialog requests cancellation rather than deleting a live UI.
        self.cancelled = True
        self.cancel_button.setEnabled(False)

    def update_progress(self, done, total, path):
        self.summary.setText(tr('Importing files: %d/%d') % (done, total))
        self.filename.setText(os.path.basename(path))
        self.filename.setToolTip(path)
        self.bar.setRange(0, total)
        self.bar.setValue(done)
        # Application modality prevents another tool action during these updates.
        # QProgressDialog.setValue() would start its own event processing if modal.
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 5)
        return not self.cancelled

    def __enter__(self):
        self.show()
        return self

    def __exit__(self, *error):
        self.hide()
        self.deleteLater()
