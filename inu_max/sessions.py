"""Transient UI timers survive developer reloads of ops and adapters."""
timers = {}


def stop(name):
    timer = timers.pop(name, None)
    if timer is not None:
        timer.stop()
        timer.deleteLater()


def start(name, callback, interval=500):
    from .qt import QtCore, QtWidgets
    stop(name)
    timer = QtCore.QTimer(QtWidgets.QApplication.instance())
    def tick():
        try:
            callback()
        except Exception as error:
            stop(name)
            print('[INU] %s stopped: %s' % (name, error))
    timer.timeout.connect(tick)
    timer.start(interval)
    timers[name] = timer
