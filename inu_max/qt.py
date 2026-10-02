"""Use the Qt binding supplied by Max: PySide2 (2023/24), PySide6 (2025/26)."""
def _qt5_host():
    try:
        import pymxs
        return int(pymxs.runtime.maxVersion()[0]) < 27000
    except (ImportError, AttributeError, TypeError, IndexError):
        return False


if _qt5_host():
    from PySide2 import QtCore, QtGui, QtWidgets
    BINDING = 'PySide2'
else:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        BINDING = 'PySide6'
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
        BINDING = 'PySide2'


if BINDING == 'PySide2':
    # Qt5 names blocking event loops exec_; expose the API used by the UI.
    for cls in (QtCore.QEventLoop, QtWidgets.QDialog, QtWidgets.QMenu,
                QtWidgets.QMessageBox, QtWidgets.QApplication):
        if not hasattr(cls, 'exec'):
            cls.exec = cls.exec_
    for name in ('QAction', 'QActionGroup', 'QShortcut'):
        if not hasattr(QtGui, name):
            setattr(QtGui, name, getattr(QtWidgets, name))


def mouse_position(event):
    return event.position() if hasattr(event, 'position') else event.localPos()
