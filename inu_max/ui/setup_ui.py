# INU Tools (Max) — окна установки INU в Max (кнопки Setup лаунчера): прогресс
# (numpy качается pip'ом — Max при этом отзывчив), итог и просьба перезапустить
# Max, подтверждение удаления.

from ..qt import QtWidgets, QtCore

from .style import qss


def _parent(parent):
    if parent is not None:
        return parent
    try:
        import qtmax
        return qtmax.GetQMaxMainWindow()
    except Exception:                                  # noqa: BLE001
        return None


def _box(parent, icon, title, text, buttons=QtWidgets.QMessageBox.Ok):
    box = QtWidgets.QMessageBox(icon, title, text, buttons, _parent(parent))
    box.setStyleSheet(qss())
    return box


def _wait_with_progress(parent, label):
    """wait(proc) для setup.install_numpy: ждёт процесс, крутя цикл событий Qt
    (окно Max не «висит»), с бегущей полосой."""
    def wait(proc):
        dlg = QtWidgets.QProgressDialog(label, None, 0, 0, _parent(parent))
        dlg.setWindowTitle("INU Tools")
        dlg.setStyleSheet(qss())
        dlg.setWindowModality(QtCore.Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.show()
        loop = QtCore.QEventLoop()
        timer = QtCore.QTimer()
        timer.timeout.connect(lambda: proc.poll() is not None and loop.quit())
        timer.start(200)
        if proc.poll() is None:
            loop.exec()
        timer.stop()
        dlg.close()
        dlg.deleteLater()
    return wait


def install_interactive(parent=None):
    """Установить / обновить INU в Max и попросить перезапустить Max."""
    from .. import setup
    from ..version import VERSION
    QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
    try:
        report = setup.install(wait=_wait_with_progress(
            parent, "Installing numpy for INU Tools (downloading, ~15 MB)…"))
    except Exception as e:                             # noqa: BLE001
        QtWidgets.QApplication.restoreOverrideCursor()
        import traceback
        traceback.print_exc()
        _box(parent, QtWidgets.QMessageBox.Critical, "INU Tools",
             "Installation failed:\n%s: %s" % (type(e).__name__, e)).exec()
        return False
    QtWidgets.QApplication.restoreOverrideCursor()
    text = ("INU Tools v%s is installed into 3ds Max.\n\n• %s\n\n"
            "Restart 3ds Max to activate it:\n"
            "• drag & drop .dff files into the viewport\n"
            "• INU Tools menu in the main menu bar\n"
            "• INU Tools launcher in the Utilities panel (MAXScript list)"
            % (VERSION, "\n• ".join(report)))
    _box(parent, QtWidgets.QMessageBox.Information, "INU Tools: installed", text).exec()
    return True


def remove_interactive(parent=None):
    from .. import setup
    ask = _box(parent, QtWidgets.QMessageBox.Question, "INU Tools",
               "Remove INU Tools from 3ds Max?\n\n"
               "This removes the drag & drop plugin, the INU Tools menu and the "
               "startup registration. Your INU folder is not touched.",
               QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
    if ask.exec() != QtWidgets.QMessageBox.Yes:
        return False
    full = setup.remove()
    _box(parent, QtWidgets.QMessageBox.Information, "INU Tools: removed",
         "INU Tools is removed from 3ds Max.\n\nRestart 3ds Max to finish."
         + ("" if full else "\n(Files in use are deleted after the restart.)")).exec()
    return True
