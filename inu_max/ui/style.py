# INU Tools (Max) — палитра и QSS в стиле роллаутов Kam's / Max 2026.
#
# Палитра снята со скриншотов: фон окна #444, роллаут #515151, контролы
# #646464, выбранный checkbutton — зелёный #00BD00 (color 0 189 0 у Kam's).
# Шрифт НЕ задаём: виджеты берут шрифт интерфейса Max (Segoe UI 8pt), тот
# же, что у роллаутов Kam's (setFont окна при stylesheet до детей не доходит).

import os
import tempfile

from PySide6 import QtCore, QtGui

C = dict(
    win="#444444",        # фон окна (между роллаутами)
    roll="#515151",       # тело и заголовок роллаута
    rollbd="#3e3e3e",     # рамка роллаута
    ctl="#646464",        # кнопки, чекбоксы, поля
    ctlbd="#4a4a4a",      # рамка контролов
    grpbd="#383838",      # рамка групп (group "..." у Kam's)
    hover="#6e6e6e",
    press="#5a5a5a",
    dis="#595959",
    text="#dcdcdc",
    textdis="#808080",
    green="#00BD00",
    greenhv="#10CC10",
    greendis="#3f6a3f",   # нажатый, но недоступный (как «Manual» у pivot'а)
    err="#E08A8A",
    list="#3a3a3a",       # фон списков (файлы, места)
    sel="#5b7fa6",        # выделение в списках
)

# Высота обычной кнопки как у Kam's (задаём setFixedHeight: QSS max-height в
# Max не зажимает).
BTN_H = 21

# Колонка полосы прокрутки справа от роллаутов: ширина полосы и зазор.
SB_W = 8
SB_GAP = 2

# Иконки для QSS (галка чекбокса, стрелки спиннера/комбо): если стилизовать
# индикатор через QSS, родная галка пропадает — рисуем свою и даём url().
_ICON_DIR = None


def icons():
    global _ICON_DIR
    if _ICON_DIR and os.path.isfile(os.path.join(_ICON_DIR, "check.png")):
        return _ICON_DIR
    d = os.path.join(tempfile.gettempdir(), "inu_max_ui")
    os.makedirs(d, exist_ok=True)
    col = QtGui.QColor(C['text'])

    def _save(name, w, h, draw):
        pm = QtGui.QPixmap(w, h)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        draw(p)
        p.end()
        pm.save(os.path.join(d, name))

    def _check(p):
        pen = QtGui.QPen(col, 2.0)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QtCore.QPointF(2.5, 6.5), QtCore.QPointF(5, 9),
                        QtCore.QPointF(9.5, 3)])

    def _tri(points):
        def draw(p):
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(col)
            p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(*xy) for xy in points]))
        return draw

    _save("check.png", 12, 12, _check)
    _save("up.png", 7, 4, _tri([(0, 4), (7, 4), (3.5, 0)]))
    _save("down.png", 7, 4, _tri([(0, 0), (7, 0), (3.5, 4)]))
    _ICON_DIR = d
    return d


_ICON_CACHE = {}


SEVERITY_COLOR = {'ERROR': "#E06C6C", 'WARN': "#E0B040", 'WARNING': "#E0B040",
                  'INFO': "#9ab0c8"}


def icon(name, color=None):
    """Иконка для маленьких кнопок (как иконки INU в Blender): add, remove,
    x, trash, folder, refresh, text, forward, check, edit, archive, import,
    export, eye, eye_off, select, warning, info, error; окно анимаций —
    camera, eyedropper, play, hand, ik, plane, weights, screw, turn, action,
    rec, gimbal, curve, arrows, pivot, outliner; 2DFX — light, particles,
    ped, sun, stairs, lock, image, link, paste, tri_left. Рисуем сами —
    одинаково в любом стиле Max. color — цвет (по умолчанию цвет текста)."""
    ic = _ICON_CACHE.get((name, color))
    if ic is not None:
        return ic
    pm = QtGui.QPixmap(32, 32)                 # 2× для чёткости на HiDPI
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.scale(2, 2)
    col = QtGui.QColor(color or C['text'])
    pen = QtGui.QPen(col, 1.4)
    pen.setCapStyle(QtCore.Qt.RoundCap)
    pen.setJoinStyle(QtCore.Qt.RoundJoin)
    p.setPen(pen)
    P = QtCore.QPointF
    R = QtCore.QRectF
    if name == 'add':
        p.drawLine(P(8, 3.5), P(8, 12.5))
        p.drawLine(P(3.5, 8), P(12.5, 8))
    elif name == 'remove':
        p.drawLine(P(3.5, 8), P(12.5, 8))
    elif name == 'x':
        p.drawLine(P(4.5, 4.5), P(11.5, 11.5))
        p.drawLine(P(11.5, 4.5), P(4.5, 11.5))
    elif name == 'trash':
        p.drawLine(P(3, 4.5), P(13, 4.5))
        p.drawLine(P(6.5, 4.5), P(6.5, 3))
        p.drawLine(P(6.5, 3), P(9.5, 3))
        p.drawLine(P(9.5, 3), P(9.5, 4.5))
        p.drawPolyline([P(4.5, 4.5), P(5.2, 13), P(10.8, 13), P(11.5, 4.5)])
        p.drawLine(P(8, 6.5), P(8, 11))
    elif name == 'folder':
        p.drawPolyline([P(2.5, 12.5), P(2.5, 4), P(6, 4), P(7.5, 5.5),
                        P(13.5, 5.5), P(13.5, 12.5), P(2.5, 12.5)])
        p.drawLine(P(2.5, 7.5), P(13.5, 7.5))
    elif name == 'refresh':
        p.drawArc(R(3.5, 3.5, 9, 9), 30 * 16, 290 * 16)
        p.drawPolyline([P(12.8, 2.8), P(12.2, 6.2), P(8.9, 5.3)])
    elif name == 'text':
        p.drawPolyline([P(4, 2.5), P(9.5, 2.5), P(12, 5), P(12, 13.5),
                        P(4, 13.5), P(4, 2.5)])
        for y in (7, 9.5, 12):
            p.drawLine(P(6, y), P(10, y))
    elif name == 'forward':
        p.drawLine(P(3, 8), P(12.5, 8))
        p.drawPolyline([P(8.5, 4), P(12.5, 8), P(8.5, 12)])
    elif name == 'check':
        p.drawPolyline([P(3.5, 8.5), P(6.5, 11.5), P(12.5, 4.5)])
    elif name == 'edit':
        p.drawPolyline([P(3.5, 12.5), P(3.8, 10), P(10.5, 3.3), P(12.7, 5.5),
                        P(6, 12.2), P(3.5, 12.5)])
    elif name == 'archive':
        p.drawRect(R(3, 5, 10, 8))
        p.drawPolyline([P(2.5, 5), P(4.5, 2.5), P(11.5, 2.5), P(13.5, 5)])
        p.drawLine(P(6.5, 8), P(9.5, 8))
    elif name in ('eye', 'eye_off'):
        path = QtGui.QPainterPath()
        path.moveTo(1.5, 8)
        path.quadTo(8, 1.5, 14.5, 8)
        path.quadTo(8, 14.5, 1.5, 8)
        p.drawPath(path)
        p.drawEllipse(P(8, 8), 2.2, 2.2)
        if name == 'eye_off':
            p.drawLine(P(3, 13.5), P(13, 2.5))
    elif name == 'select':
        p.drawPolyline([P(4, 2.5), P(4, 13), P(7, 10), P(9.5, 14),
                        P(11, 13.2), P(8.7, 9.3), P(12.5, 9.3), P(4, 2.5)])
    elif name == 'warning':
        p.drawPolyline([P(8, 2), P(14.5, 13.5), P(1.5, 13.5), P(8, 2)])
        p.drawLine(P(8, 6), P(8, 9.5))
        p.drawPoint(P(8, 11.8))
    elif name == 'info':
        p.drawEllipse(P(8, 8), 6, 6)
        p.drawLine(P(8, 7), P(8, 11.5))
        p.drawPoint(P(8, 4.8))
    elif name == 'error':
        p.drawEllipse(P(8, 8), 6, 6)
        p.drawLine(P(5.5, 5.5), P(10.5, 10.5))
        p.drawLine(P(10.5, 5.5), P(5.5, 10.5))
    elif name == 'parent':                      # ⤴ сделать родителем
        p.drawPolyline([P(4, 13), P(4, 5), P(12, 5)])
        p.drawPolyline([P(9, 2), P(12, 5), P(9, 8)])
    elif name == 'unlink':                      # ⛓ снять родителя
        p.drawArc(R(1.5, 5, 6, 6), 90 * 16, 180 * 16)
        p.drawLine(P(4.5, 5), P(6.5, 5))
        p.drawLine(P(4.5, 11), P(6.5, 11))
        p.drawArc(R(8.5, 5, 6, 6), -90 * 16, 180 * 16)
        p.drawLine(P(9.5, 5), P(11.5, 5))
        p.drawLine(P(9.5, 11), P(11.5, 11))
    elif name == 'mesh':
        p.drawPolyline([P(3, 5), P(8, 2.5), P(13, 5), P(13, 11), P(8, 13.5),
                        P(3, 11), P(3, 5), P(8, 7.5), P(13, 5)])
        p.drawLine(P(8, 7.5), P(8, 13.5))
    elif name == 'empty':
        p.drawLine(P(8, 2), P(8, 14))
        p.drawLine(P(2, 8), P(14, 8))
        p.drawLine(P(4, 12), P(12, 4))
    elif name == 'bone':
        p.drawEllipse(P(4.5, 11.5), 2, 2)
        p.drawEllipse(P(11.5, 4.5), 2, 2)
        p.drawLine(P(6, 10), P(10, 6))
    elif name == 'mirror':
        p.drawLine(P(8, 2), P(8, 14))
        p.drawPolyline([P(6, 4), P(2, 8), P(6, 12), P(6, 4)])
        p.drawPolyline([P(10, 4), P(14, 8), P(10, 12), P(10, 4)])
    elif name in ('tri_right', 'tri_down'):
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#a8a8a8"))
        pts = ([(6, 4), (6, 12), (11, 8)] if name == 'tri_right'
               else [(4, 6), (12, 6), (8, 11)])
        p.drawPolygon(QtGui.QPolygonF([P(*xy) for xy in pts]))
    elif name in ('import', 'export'):
        p.drawPolyline([P(3, 10), P(3, 13), P(13, 13), P(13, 10)])
        if name == 'import':
            p.drawLine(P(8, 2.5), P(8, 10))
            p.drawPolyline([P(5, 7), P(8, 10), P(11, 7)])
        else:
            p.drawLine(P(8, 10), P(8, 2.5))
            p.drawPolyline([P(5, 5.5), P(8, 2.5), P(11, 5.5)])
    elif name == 'camera':
        p.drawRoundedRect(R(2, 5, 8.5, 7), 1.2, 1.2)
        p.drawPolyline([P(10.5, 7.5), P(14, 5.5), P(14, 11.5), P(10.5, 9.5)])
    elif name == 'eyedropper':
        p.drawLine(P(3, 13), P(9, 7))
        p.drawLine(P(7, 5), P(11, 9))
        p.drawEllipse(P(11.5, 4.5), 2, 2)
    elif name == 'play':
        p.drawPolyline([P(5, 3.5), P(12.5, 8), P(5, 12.5), P(5, 3.5)])
    elif name == 'hand':
        for x in (5, 7.3, 9.6, 11.9):
            p.drawLine(P(x, 3.5), P(x, 8))
        p.drawRoundedRect(R(4, 7.5, 9, 6), 2, 2)
    elif name == 'ik':                          # цепочка сустава
        p.drawPolyline([P(3, 13), P(8, 7), P(13, 13)])
        for xy in ((3, 13), (8, 7), (13, 13)):
            p.drawEllipse(P(*xy), 1.3, 1.3)
        p.drawLine(P(8, 2.5), P(8, 4.5))
    elif name == 'plane':
        p.drawPolyline([P(2, 11.5), P(5.5, 5), P(14, 5), P(10.5, 11.5),
                        P(2, 11.5)])
    elif name == 'weights':                     # группа вершин
        p.drawPolyline([P(3, 12.5), P(8, 3.5), P(13, 12.5), P(3, 12.5)])
        p.setBrush(col)
        for xy in ((3, 12.5), (8, 3.5), (13, 12.5)):
            p.drawEllipse(P(*xy), 1.4, 1.4)
    elif name in ('screw', 'turn'):             # вращение вокруг оси
        if name == 'screw':
            p.drawLine(P(8, 1.5), P(8, 14.5))
        p.drawArc(R(2.5, 4, 11, 8), 210 * 16, 280 * 16)
        p.drawPolyline([P(10.2, 3), P(12.4, 4.9), P(10, 6.4)])
    elif name == 'action':                      # ключ (ромб)
        p.drawPolyline([P(8, 3), P(13, 8), P(8, 13), P(3, 8), P(8, 3)])
    elif name == 'rec':
        p.setBrush(col)
        p.drawEllipse(P(8, 8), 3.8, 3.8)
    elif name == 'gimbal':
        p.drawEllipse(P(8, 8), 6, 6)
        p.drawEllipse(P(8, 8), 6, 2.4)
        p.drawEllipse(P(8, 8), 2.4, 6)
    elif name == 'curve':
        path = QtGui.QPainterPath()
        path.moveTo(2, 12.5)
        path.cubicTo(7, 12.5, 9, 3.5, 14, 3.5)
        p.drawPath(path)
    elif name == 'arrows':                      # ← →
        p.drawLine(P(2.5, 8), P(13.5, 8))
        p.drawPolyline([P(5, 5.5), P(2.5, 8), P(5, 10.5)])
        p.drawPolyline([P(11, 5.5), P(13.5, 8), P(11, 10.5)])
    elif name == 'pivot':                       # Empty-оси
        p.drawEllipse(P(8, 8), 2.2, 2.2)
        for a, b in (((8, 1.5), (8, 5.8)), ((8, 10.2), (8, 14.5)),
                     ((1.5, 8), (5.8, 8)), ((10.2, 8), (14.5, 8))):
            p.drawLine(P(*a), P(*b))
    elif name == 'outliner':
        p.drawLine(P(4, 3), P(4, 12))
        p.drawLine(P(4, 6), P(8, 6))
        p.drawLine(P(4, 12), P(8, 12))
        p.drawRect(R(9, 4.5, 4.5, 3))
        p.drawRect(R(9, 10.5, 4.5, 3))
    elif name == 'light':                       # лампа
        p.drawEllipse(P(8, 6.5), 4, 4)
        p.drawLine(P(6.5, 11.5), P(9.5, 11.5))
        p.drawLine(P(7, 13.5), P(9, 13.5))
    elif name == 'particles':
        p.setBrush(col)
        for xy, r in (((4, 11.5), 1.3), ((7.5, 6), 1.6), ((11.5, 9.5), 1.3),
                      ((12, 3.5), 1.0), ((4.5, 4), 1.0), ((8.5, 13), 1.0)):
            p.drawEllipse(P(*xy), r, r)
    elif name == 'ped':                         # человечек
        p.drawEllipse(P(8, 3.5), 1.8, 1.8)
        p.drawLine(P(8, 5.5), P(8, 10))
        p.drawLine(P(4.5, 7.5), P(11.5, 7.5))
        p.drawLine(P(8, 10), P(5.5, 14))
        p.drawLine(P(8, 10), P(10.5, 14))
    elif name == 'sun':
        p.drawEllipse(P(8, 8), 2.8, 2.8)
        for a, b in (((8, 1.5), (8, 3.5)), ((8, 12.5), (8, 14.5)),
                     ((1.5, 8), (3.5, 8)), ((12.5, 8), (14.5, 8)),
                     ((3.4, 3.4), (4.8, 4.8)), ((11.2, 11.2), (12.6, 12.6)),
                     ((3.4, 12.6), (4.8, 11.2)), ((11.2, 4.8), (12.6, 3.4))):
            p.drawLine(P(*a), P(*b))
    elif name == 'stairs':
        p.drawPolyline([P(2, 13), P(5, 13), P(5, 10), P(8, 10), P(8, 7),
                        P(11, 7), P(11, 4), P(14, 4)])
    elif name == 'lock':
        p.drawRoundedRect(R(3.5, 7.5, 9, 6), 1, 1)
        p.drawArc(R(5.5, 3, 5, 8), 0, 180 * 16)
    elif name == 'image':
        p.drawRect(R(2.5, 3.5, 11, 9))
        p.drawPolyline([P(3.5, 11), P(6.5, 7.5), P(9, 10), P(10.8, 8.3),
                        P(12.5, 10)])
        p.drawEllipse(P(10.5, 6), 0.9, 0.9)
    elif name == 'link':                        # звенья цепи
        p.drawRoundedRect(R(1.5, 5.5, 7.5, 5), 2.4, 2.4)
        p.drawRoundedRect(R(7, 5.5, 7.5, 5), 2.4, 2.4)
    elif name == 'paste':                       # планшет
        p.drawRect(R(3.5, 3, 9, 11))
        p.drawRect(R(6, 1.8, 4, 2.4))
        for y in (7.5, 10):
            p.drawLine(P(5.5, y), P(10.5, y))
    elif name == 'tri_left':
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#a8a8a8"))
        p.drawPolygon(QtGui.QPolygonF([P(10, 4), P(10, 12), P(5, 8)]))
    p.end()
    ic = QtGui.QIcon(pm)
    _ICON_CACHE[(name, color)] = ic
    return ic


def qss():
    ic = icons().replace("\\", "/")
    return """
QWidget#inuWin { background: %(win)s; }
QWidget { color: %(text)s; }
QWidget#scrollHost { background: transparent; }

QFrame#rollout { background: %(roll)s; border: 1px solid %(rollbd)s;
                 border-radius: 3px; }

QFrame#box { border: 1px solid %(grpbd)s; border-radius: 3px; }
QFrame#fused { background: %(ctlbd)s; border-radius: 3px; }
QGroupBox { border: 1px solid %(grpbd)s; border-radius: 3px;
            margin-top: 8px; padding: 5px 3px 3px 3px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
                   left: 6px; top: 0px; padding: 0 3px; background: %(roll)s; }

QPushButton { background: %(ctl)s; color: %(text)s;
              border: 1px solid %(ctlbd)s; border-radius: 2px; padding: 0 4px; }
QPushButton:hover { background: %(hover)s; }
QPushButton:pressed { background: %(press)s; }
QPushButton:checked { background: %(green)s; color: #f2f2f2; }
QPushButton:checked:hover { background: %(greenhv)s; }
QPushButton:disabled { background: %(dis)s; color: %(textdis)s; }
QPushButton:checked:disabled { background: %(greendis)s; color: %(textdis)s; }

QCheckBox { spacing: 5px; }
QCheckBox::indicator { width: 13px; height: 13px; background: %(ctl)s;
                       border: 1px solid %(ctlbd)s; border-radius: 2px; }
QCheckBox::indicator:hover { background: %(hover)s; }
QCheckBox::indicator:checked { image: url(%(ic)s/check.png); }
QCheckBox:disabled { color: %(textdis)s; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: %(ctl)s; color: %(text)s; border: 1px solid %(ctlbd)s;
    border-radius: 2px; padding: 1px 3px; selection-background-color: %(sel)s; }
QSpinBox, QDoubleSpinBox { padding-right: 14px; }
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border; width: 12px; border: none; background: transparent; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-position: top right; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-position: bottom right; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(%(ic)s/up.png); width: 7px; height: 4px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(%(ic)s/down.png); width: 7px; height: 4px; }
QComboBox::drop-down { border: none; width: 14px; }
QComboBox::down-arrow { image: url(%(ic)s/down.png); width: 7px; height: 4px; }
QComboBox QAbstractItemView { background: %(ctl)s; color: %(text)s;
                              selection-background-color: %(sel)s; }
QPushButton::menu-indicator { image: url(%(ic)s/down.png); width: 7px; height: 4px;
                              subcontrol-origin: padding; subcontrol-position: right center;
                              right: 4px; }
QMenu { background: %(roll)s; color: %(text)s; border: 1px solid %(rollbd)s; }
QMenu::item { padding: 3px 16px 3px 12px; }
QMenu::item:selected { background: %(sel)s; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QComboBox:disabled { color: %(textdis)s; background: %(dis)s; }
QLabel:disabled { color: %(textdis)s; }

/* — окно выбора файлов — */
QTreeView, QListView { background: %(list)s; color: %(text)s;
                       border: 1px solid %(rollbd)s; outline: 0;
                       selection-background-color: %(sel)s; selection-color: #ffffff; }
QTreeView::item, QListView::item { padding: 1px 2px; }
QTreeView::item:hover, QListView::item:hover { background: #4a4a4a; }
QTreeView::item:selected, QListView::item:selected { background: %(sel)s; color: #ffffff; }
QHeaderView { background: %(roll)s; }
QHeaderView::section { background: %(roll)s; color: %(text)s; border: none;
                       border-right: 1px solid %(win)s;
                       border-bottom: 1px solid %(rollbd)s; padding: 2px 6px; }
QScrollBar:vertical { background: #383838; width: 10px; margin: 0; }
QScrollBar:horizontal { background: #383838; height: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #5a5a5a; border: 1px solid #383838;
                              border-radius: 4px; min-height: 24px; }
QScrollBar::handle:horizontal { background: #5a5a5a; border: 1px solid #383838;
                                border-radius: 4px; min-width: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QToolButton { background: transparent; border: 1px solid transparent;
              border-radius: 2px; padding: 2px; }
QToolButton:hover { background: %(hover)s; border-color: %(ctlbd)s; }
QToolButton:pressed { background: %(press)s; }
QToolButton:disabled { background: transparent; }
QToolButton::menu-indicator { image: none; }
""" % dict(C, ic=ic)
