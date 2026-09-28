# INU Tools (Max) — диалог «Как импортировать DFF?» при перетаскивании
# (как drop_dff INU): vanilla / Import 2DFX / Auto TXD. Галочки пишутся сразу в
# settings. Используют окно DFF IO (сброс на окно) и C++ импортёр (сброс во
# вьюпорт, File → Import).

from PySide6 import QtWidgets, QtCore

from .. import settings
from .style import qss


def _get(key, default):
    cur = settings.get(key)
    return default if cur is None else cur


def _at_cursor(dlg):
    """Окно у курсора (как всплывающий диалог Blender при перетаскивании),
    не выходя за край экрана."""
    from PySide6 import QtGui
    dlg.adjustSize()
    cur = QtGui.QCursor.pos()
    screen = QtGui.QGuiApplication.screenAt(cur) or QtGui.QGuiApplication.primaryScreen()
    area = screen.availableGeometry()
    x = min(max(cur.x() - dlg.width() // 2, area.left()), area.right() - dlg.width())
    y = min(max(cur.y() - 16, area.top()), area.bottom() - dlg.height())
    dlg.move(x, y)


def ask(parent=None, count=1, at_cursor=False):
    """True — импортировать (галочки уже в settings), False — отмена.
    at_cursor — открыть у курсора (перетаскивание)."""
    if parent is None:
        try:
            import qtmax
            parent = qtmax.GetQMaxMainWindow()
        except Exception:                              # noqa: BLE001
            parent = None
    dlg = QtWidgets.QDialog(parent)
    dlg.setObjectName("inuWin")
    dlg.setAttribute(QtCore.Qt.WA_StyledBackground, True)
    dlg.setStyleSheet(qss())
    dlg.setWindowTitle("INU: Import DFF")
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.setContentsMargins(10, 10, 10, 10)
    lay.setSpacing(6)
    lay.addWidget(QtWidgets.QLabel("How to import DFF? (%d file%s)"
                                   % (count, "" if count == 1 else "s")))
    custom = QtWidgets.QLabel("Custom: connect + keep fences")
    custom.setStyleSheet("color: #9a9a9a;")

    def check(label, key, dflt, tip, after=None):
        cb = QtWidgets.QCheckBox(label)
        cb.setChecked(bool(_get(key, dflt)))
        cb.setToolTip(tip)
        cb.toggled.connect(lambda v: (settings.set(key, bool(v)), after and after()))
        return cb
    lay.addWidget(check(
        "Standard GTA SA model (vanilla)", 'import_weld_sharpen', False,
        "ON: treat as a STANDARD GTA SA model (weld + sharp edges). "
        "OFF: CUSTOM model: connect loose geometry and keep double-sided "
        "fences.", lambda: custom.setVisible(not _get('import_weld_sharpen', False))))
    lay.addWidget(custom)
    custom.setVisible(not _get('import_weld_sharpen', False))
    lay.addWidget(check(
        "Import 2DFX", 'import_2dfx', True,
        "Create 2DFX effect helpers from the DFF (lights/coronas, particles, "
        "ped attractors, sun glare, signs, etc.)."))
    lay.addWidget(check(
        "Auto TXD", 'auto_txd', True,
        "Load the model's TXD automatically from the model's folder."))
    box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok
                                     | QtWidgets.QDialogButtonBox.Cancel)
    box.button(QtWidgets.QDialogButtonBox.Ok).setText("Import")
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    lay.addWidget(box)
    if at_cursor:
        _at_cursor(dlg)
    ok = dlg.exec() == QtWidgets.QDialog.Accepted
    dlg.deleteLater()
    return ok
