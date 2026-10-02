# INU Tools (Max) — общие виджеты окон: роллауты Kam's, своя прокрутка,
# конструкторы контролов, привязанных к settings.

from PySide6 import QtWidgets, QtCore, QtGui

from .style import C, BTN_H, SB_W, SB_GAP, icon, qss

try:
    from .. import settings
except Exception:          # noqa: BLE001
    settings = None


class ElideLabel(QtWidgets.QLabel):
    """Однострочная подпись, которая обрезается «…» по ширине (имена моделей
    бывают длинными, а ширина окна фиксирована). Полный текст — в подсказке."""

    def __init__(self, text='', parent=None):
        super().__init__(parent)
        self._full = ''
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                           QtWidgets.QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text):                           # noqa: N802
        self._full = text
        self.setToolTip(text)
        self._elide()

    def full_text(self):
        return self._full

    def resizeEvent(self, e):                          # noqa: N802
        super().resizeEvent(e)
        self._elide()

    def _elide(self):
        w = max(10, self.width())
        QtWidgets.QLabel.setText(self, self.fontMetrics().elidedText(
            self._full, QtCore.Qt.ElideRight, w))


class IconLabel(QtWidgets.QWidget):
    """Подпись с иконкой слева (как label(text=..., icon=...) в INU).
    wrap — переносить по словам, иначе одна строка с «…»; icon_color —
    цвет иконки (красный у ошибок); indent — отступ слева (строки дерева)."""

    def __init__(self, text='', icon_name=None, wrap=False, icon_color=None,
                 indent=0, parent=None):
        super().__init__(parent)
        self._hl = QtWidgets.QHBoxLayout(self)
        self._hl.setContentsMargins(indent, 0, 0, 0)
        self._hl.setSpacing(4)
        self._ic = QtWidgets.QLabel()
        self._ic.setFixedSize(14, 14)
        self._hl.addWidget(self._ic, 0, QtCore.Qt.AlignTop if wrap
                           else QtCore.Qt.AlignVCenter)
        if wrap:
            self._lb = QtWidgets.QLabel()
            self._lb.setWordWrap(True)
        else:
            self._lb = ElideLabel()
        self._hl.addWidget(self._lb, 1)
        self.setText(text)
        self.setIcon(icon_name, icon_color)

    def setText(self, text):                           # noqa: N802
        self._lb.setText(text)

    def text(self):
        return self._lb.full_text() if isinstance(self._lb, ElideLabel) \
            else self._lb.text()

    def setIcon(self, name, color=None):               # noqa: N802
        self._ic.setVisible(bool(name))
        if name:
            self._ic.setPixmap(icon(name, color).pixmap(14, 14))


class ScrollView(QtWidgets.QWidget):
    """Прокручиваемая область — БЕЗ QScrollArea/QScrollBar.

    В Max стандартная прокрутка Qt живёт своей жизнью: полоса QScrollArea
    не видна, а её диапазон нам недоступен (своя полоса, читавшая его, в Max
    ничего не рисовала, хотя колесо крутило). Поэтому прокрутку ведём сами:
    host лежит внутри и сдвигается на -offset, колесо мыши и полоса
    ScrollStrip меняют offset. Сигнал changed — для перерисовки полосы."""

    changed = QtCore.Signal()
    _WHEEL_PX = 60                  # сдвиг на один щелчок колеса

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self._host = host
        self._off = 0
        self._content_h = 0
        host.setParent(self)
        host.move(0, 0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Expanding)

    def host(self):
        return self._host

    # — желаемый размер: окно открывается по высоте содержимого (не выше ¾
    #   экрана), дальше его можно сузить — появится полоса —
    def sizeHint(self):                                # noqa: N802
        lay = self._host.layout()
        h = lay.totalSizeHint().height() if lay is not None else 300
        try:
            cap = int(self.screen().availableGeometry().height() * 0.75)
        except Exception:                              # noqa: BLE001
            cap = 700
        return QtCore.QSize(self._host.sizeHint().width(), min(h, cap))

    def minimumSizeHint(self):                         # noqa: N802
        return QtCore.QSize(0, 60)

    # — состояние для полосы —
    def offset(self):
        return self._off

    def max_offset(self):
        return max(0, self._content_h - self.height())

    def page(self):
        return self.height()

    def content_height(self):
        return self._content_h

    # — раскладка —
    def _measure(self):
        """Естественная высота содержимого при текущей ширине."""
        lay = self._host.layout()
        w = self.width()
        if lay is None:
            return self._host.sizeHint().height()
        if lay.hasHeightForWidth():
            h = lay.totalHeightForWidth(w)
        else:
            h = lay.totalSizeHint().height()
        return max(h, lay.totalMinimumSize().height())

    def relayout(self):
        self._content_h = self._measure()
        self._off = min(self._off, self.max_offset())
        # host не ниже области — нижние элементы прижаты к низу
        self._host.setGeometry(0, -self._off, self.width(),
                               max(self._content_h, self.height()))
        self.changed.emit()

    def scroll_to(self, off):
        off = max(0, min(int(round(off)), self.max_offset()))
        if off != self._off:
            self._off = off
            self._host.move(0, -off)
            self.changed.emit()

    def resizeEvent(self, e):                          # noqa: N802
        super().resizeEvent(e)
        self.relayout()

    def event(self, e):
        # содержимое поменялось (роллаут свернули, группа появилась): host
        # сообщает родителю без layout через LayoutRequest
        if e.type() == QtCore.QEvent.LayoutRequest:
            self.relayout()
        return super().event(e)

    def wheelEvent(self, e):                           # noqa: N802
        dy = e.angleDelta().y()
        if dy and self.max_offset() > 0:
            self.scroll_to(self._off - dy / 120.0 * self._WHEEL_PX)
            e.accept()
        else:
            e.ignore()


class ScrollStrip(QtWidgets.QWidget):
    """Полоса прокрутки в своей колонке справа (как у rolloutFloater Kam's).
    Рисуем сами, состояние берём из ScrollView. Когда прокручивать нечего —
    колонка пустая, но место за ней сохраняется."""

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self._view = view
        self._drag = None           # (y нажатия, offset на момент нажатия)
        self._hover = False
        self.setFixedWidth(SB_W)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                           QtWidgets.QSizePolicy.Expanding)
        view.changed.connect(self.update)

    def _geom(self):
        """(y, высота) ползунка или None, если прокручивать нечего."""
        v = self._view
        mx = v.max_offset()
        if mx <= 0:
            return None
        track = self.height()
        page = max(1, v.page())
        hh = min(track, max(20, int(round(track * page / float(mx + page)))))
        y = int(round((track - hh) * v.offset() / float(mx)))
        return y, hh

    def paintEvent(self, _e):                          # noqa: N802
        g = self._geom()
        if g is None:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#383838"))            # дорожка
        p.drawRoundedRect(QtCore.QRectF(self.rect()), 3, 3)
        y, hh = g
        p.setBrush(QtGui.QColor("#6a6a6a" if (self._hover or self._drag)
                                else "#5a5a5a"))       # ползунок
        p.drawRoundedRect(QtCore.QRectF(1, y + 1, self.width() - 2, hh - 2),
                          2.5, 2.5)
        p.end()

    def mousePressEvent(self, e):                      # noqa: N802
        g = self._geom()
        if g is None or e.button() != QtCore.Qt.LeftButton:
            return
        y, hh = g
        py = e.position().y()
        if y <= py <= y + hh:
            self._drag = (py, self._view.offset())
        else:
            # клик по дорожке — на страницу вверх/вниз, как у QScrollBar
            page = self._view.page()
            self._view.scroll_to(self._view.offset()
                                 + (page if py > y + hh else -page))
        self.update()

    def mouseMoveEvent(self, e):                       # noqa: N802
        if self._drag is None:
            return
        g = self._geom()
        if g is None:
            return
        span = self.height() - g[1]
        if span <= 0:
            return
        dy = e.position().y() - self._drag[0]
        self._view.scroll_to(self._drag[1]
                             + dy * self._view.max_offset() / float(span))

    def mouseReleaseEvent(self, _e):                   # noqa: N802
        self._drag = None
        self.update()

    def wheelEvent(self, e):                           # noqa: N802
        self._view.wheelEvent(e)

    def enterEvent(self, _e):                          # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, _e):                          # noqa: N802
        self._hover = False
        self.update()


def scrolled(host):
    """(layout, view, strip): прокручиваемая область с host и своей колонкой
    под полосу справа (полоса не наезжает на содержимое и не сужает его)."""
    view = ScrollView(host)
    strip = ScrollStrip(view)
    lay = QtWidgets.QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(SB_GAP)
    lay.addWidget(view, 1)
    lay.addWidget(strip)
    return lay, view, strip


def content_min_width(host):
    """Минимальная ширина содержимого с учётом скрытых сейчас виджетов
    (группы, которые появляются по галочкам, свёрнутые роллауты)."""
    widgets = host.findChildren(QtWidgets.QWidget)
    hidden = [w for w in widgets if w.isHidden() and not w.isWindow()]

    def _reset():
        # размеры кэшируются и в элементах раскладки (сбрасывает только
        # updateGeometry виджета), и в самих раскладках (invalidate)
        for w in widgets:
            w.updateGeometry()
        for lay in host.findChildren(QtWidgets.QLayout):
            lay.invalidate()

    for w in hidden:
        w.setVisible(True)
    _reset()
    host.layout().activate()
    need = host.minimumSizeHint().width()
    for w in hidden:
        w.setVisible(False)
    _reset()
    return need


class RolloutHeader(QtWidgets.QWidget):
    """Заголовок роллаута как в Max: треугольник, жирный заголовок, «грип»
    из точек справа. Клик — свернуть/развернуть."""

    clicked = QtCore.Signal()

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        self.opened = False
        self.setFixedHeight(22)
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):                    # noqa: N802
        if e.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _e):                          # noqa: N802
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        h = self.height()
        cy = h / 2.0
        # треугольник
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#a8a8a8"))
        if self.opened:
            pts = [(7, cy - 2), (13, cy - 2), (10, cy + 2)]
        else:
            pts = [(8, cy - 3), (8, cy + 3), (12, cy)]
        p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(*xy) for xy in pts]))
        # грип (3×3 точки)
        p.setBrush(QtGui.QColor("#6c6c6c"))
        gx = self.width() - 16
        for i in range(3):
            for j in range(3):
                p.drawRect(QtCore.QRectF(gx + i * 3, cy - 4 + j * 3, 1.5, 1.5))
        # заголовок
        f = QtGui.QFont(self.font())
        f.setBold(True)
        p.setFont(f)
        p.setPen(QtGui.QColor("#f0f0f0"))
        p.drawText(QtCore.QRectF(20, 0, self.width() - 40, h),
                   QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, self.title)
        p.end()


class Rollout(QtWidgets.QFrame):
    """Сворачиваемый роллаут (как addRollout у Kam's). Содержимое — в
    self.body (QVBoxLayout)."""

    def __init__(self, title, opened=False, parent=None):
        super().__init__(parent)
        self.setObjectName("rollout")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        self.hdr = RolloutHeader(title)
        self.hdr.clicked.connect(self.toggle)
        lay.addWidget(self.hdr)

        self._content = QtWidgets.QWidget()
        self.body = QtWidgets.QVBoxLayout(self._content)
        self.body.setContentsMargins(5, 0, 5, 6)
        self.body.setSpacing(4)
        lay.addWidget(self._content)
        self.set_opened(opened)

    def set_opened(self, opened):
        self.hdr.opened = opened
        self._content.setVisible(opened)
        self.hdr.update()

    def toggle(self):
        self.set_opened(not self.hdr.opened)


def _fused_btn_qss(corners, pad=4):
    """QSS кнопки внутри FusedBlock: своей рамки нет, ВСЕ 4 угла заданы
    явно (незаданные наследуют скругление темы Max → на стыках видны
    «полумесяцы»). corners = (tl, tr, br, bl) — скруглять ли угол;
    pad — отступ текста слева/справа."""
    tl, tr, br, bl = (2 if c else 0 for c in corners)
    rad = ("border-top-left-radius:%dpx; border-top-right-radius:%dpx;"
           " border-bottom-right-radius:%dpx; border-bottom-left-radius:%dpx;"
           % (tl, tr, br, bl))
    return ("QPushButton{background:%(ctl)s; color:%(text)s; border:none;"
            " margin:0; " % C + "padding:0 %dpx; " % pad + rad + "}"
            "QPushButton:hover{background:%(hover)s;}"
            "QPushButton:pressed{background:%(press)s;}"
            "QPushButton:checked{background:%(green)s; color:#f2f2f2;}"
            "QPushButton:checked:hover{background:%(greenhv)s;}"
            "QPushButton:disabled{background:%(dis)s; color:%(textdis)s;}"
            "QPushButton:checked:disabled{background:%(greendis)s;}" % C)


class FusedBlock(QtWidgets.QFrame):
    """Слитный блок кнопок, как row(align=True) в Blender: кнопки вплотную,
    между ними линия 1px, скруглены только внешние углы блока.

    Линии и рамку рисует сам контейнер: его фон — цвет линии, а отступы и
    промежутки по 1px (по обеим осям) оставляют этот фон видимым; у кнопок
    своих рамок нет, поэтому зазоров не бывает. Стиль вешаем на каждую
    кнопку (селекторы по динамическим свойствам в Max не работают).
    rows — список рядов кнопок; ряды тоже слиты между собой. height —
    высота кнопок, pad — отступ текста (3 — чтобы влез ряд из пяти)."""

    def __init__(self, rows, height=BTN_H, pad=4, parent=None):
        super().__init__(parent)
        self.setObjectName("fused")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._rows = [list(r) for r in rows]
        self._pad = pad
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(1)
        for row in self._rows:
            hl = QtWidgets.QHBoxLayout()
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(1)
            for b in row:
                b.setFixedHeight(height)
                b.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                QtWidgets.QSizePolicy.Fixed)
                hl.addWidget(b)
            outer.addLayout(hl)
        self.update_corners()

    def update_corners(self):
        """Скруглить внешние углы по ВИДИМЫМ кнопкам (кнопку можно скрыть —
        например, корзину у пустого списка)."""
        rows = [[b for b in r if not b.isHidden()] for r in self._rows]
        rows = [r for r in rows if r]
        n = len(rows)
        for ri, row in enumerate(rows):
            m = len(row)
            for ci, b in enumerate(row):
                b.setStyleSheet(_fused_btn_qss((ri == 0 and ci == 0,
                                                ri == 0 and ci == m - 1,
                                                ri == n - 1 and ci == m - 1,
                                                ri == n - 1 and ci == 0),
                                               self._pad if b.text() else 0))


def icon_btn(name, tip, slot=None):
    """Квадратная кнопка-иконка (как icon-only кнопки INU): add, trash,
    refresh, folder, text, forward, x, check, edit, archive..."""
    b = QtWidgets.QPushButton()
    b.setIcon(icon(name))
    b.setIconSize(QtCore.QSize(14, 14))
    b.setFixedSize(BTN_H, BTN_H)
    b.setStyleSheet("padding: 0;")
    b.setToolTip(tip)
    if slot is not None:
        b.clicked.connect(lambda _c=False: slot())
    return b


class _ExpanderHeader(QtWidgets.QWidget):
    """Плоский заголовок-переключатель (как prop с иконкой-треугольником и
    emboss=False в Blender): треугольник + текст, клик — развернуть."""

    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ''
        self.opened = False
        self.setFixedHeight(BTN_H)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Fixed)

    def minimumSizeHint(self):                         # noqa: N802
        return QtCore.QSize(40, BTN_H)

    def mouseReleaseEvent(self, e):                    # noqa: N802
        if e.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _e):                          # noqa: N802
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        cy = self.height() / 2.0
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#a8a8a8"))
        if self.opened:
            pts = [(3, cy - 2), (9, cy - 2), (6, cy + 2)]
        else:
            pts = [(4, cy - 3), (4, cy + 3), (8, cy)]
        p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(*xy) for xy in pts]))
        p.setPen(QtGui.QColor(C['text']))
        rect = QtCore.QRectF(14, 0, self.width() - 14, self.height())
        p.drawText(rect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                   self.fontMetrics().elidedText(self.text, QtCore.Qt.ElideRight,
                                                 int(rect.width())))
        p.end()


class Expander(QtWidgets.QWidget):
    """Сворачиваемый блок как в INU: плоский заголовок (треугольник + текст)
    с кнопками справа и тело (self.body). Состояние — в settings[key]."""

    def __init__(self, owner, key, default, title='', right=(), parent=None):
        super().__init__(parent)
        self._owner, self._key = owner, key
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(1)
        self._hdr = _ExpanderHeader()
        self._hdr.clicked.connect(self.toggle)
        row.addWidget(self._hdr, 1)
        for w in right:
            row.addWidget(w)
        lay.addLayout(row)
        self._body_w = QtWidgets.QWidget()
        self.body = QtWidgets.QVBoxLayout(self._body_w)
        self.body.setContentsMargins(4, 0, 0, 2)
        self.body.setSpacing(2)
        lay.addWidget(self._body_w)
        self.set_title(title)
        self._apply(bool(owner._get(key, default)))

    def set_title(self, text):
        self._hdr.text = text
        self._hdr.setToolTip(text)
        self._hdr.update()

    def set_tip(self, tip):
        """Подсказка заголовка (описание свойства-переключателя INU)."""
        self._hdr.setToolTip(tip)

    def is_open(self):
        return self._hdr.opened

    def _apply(self, opened):
        self._hdr.opened = opened
        self._body_w.setVisible(opened)
        self._hdr.update()

    def toggle(self):
        self._owner._set(self._key, not self._hdr.opened)
        self._apply(not self._hdr.opened)


def _fit_spin(sp, lo, hi):
    """Общее для числовых полей в стиле Blender: без стрелок, «Имя: число»
    внутри, значение — по Enter / уходу фокуса, колесо — только в фокусе
    (иначе колесо над полем не прокручивает окно)."""
    sp.setRange(lo, hi)
    sp.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
    sp.setKeyboardTracking(False)
    sp.setFocusPolicy(QtCore.Qt.StrongFocus)
    sp.setFixedHeight(BTN_H)
    # у спиннеров Qt политика Minimum (минимум = sizeHint) — ряд XYZ не
    # ужимался уже 3×60; Expanding сжимает до minimumSizeHint
    sp.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
    # селектор обязателен: без него правило уйдёт и во внутренний QLineEdit
    sp.setStyleSheet("QAbstractSpinBox{padding:1px 3px;}")


class NumEdit(QtWidgets.QDoubleSpinBox):
    """Дробное поле как в Blender (см. _fit_spin); ужимается по ряду."""

    def __init__(self, decimals=3, lo=-1e6, hi=1e6, step=0.1, prefix='',
                 tip=None, parent=None):
        super().__init__(parent)
        self.setLocale(QtCore.QLocale.c())
        self.setDecimals(decimals)
        self.setSingleStep(step)
        self.setPrefix(prefix)
        _fit_spin(self, lo, hi)
        if tip:
            self.setToolTip(tip)

    def minimumSizeHint(self):                         # noqa: N802
        return QtCore.QSize(30, BTN_H)

    def sizeHint(self):                                # noqa: N802
        return QtCore.QSize(60, BTN_H)

    def wheelEvent(self, e):                           # noqa: N802
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class IntEdit(QtWidgets.QSpinBox):
    """Целое поле как в Blender (см. _fit_spin)."""

    def __init__(self, lo=0, hi=255, prefix='', tip=None, parent=None):
        super().__init__(parent)
        self.setPrefix(prefix)
        _fit_spin(self, lo, hi)
        if tip:
            self.setToolTip(tip)

    def minimumSizeHint(self):                         # noqa: N802
        return QtCore.QSize(30, BTN_H)

    def sizeHint(self):                                # noqa: N802
        return QtCore.QSize(60, BTN_H)

    def wheelEvent(self, e):                           # noqa: N802
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class VecEdit(QtWidgets.QWidget):
    """Вектор полей в ряд (XYZ-поля Blender); cols — по столько в ряд
    (матрица 3×3: n=9, cols=3). changed(tuple)."""

    changed = QtCore.Signal(tuple)

    def __init__(self, n=3, decimals=3, lo=-1e6, hi=1e6, step=0.1,
                 labels=('X', 'Y', 'Z'), tip=None, cols=None, parent=None):
        super().__init__(parent)
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(1)
        cols = cols or n
        self._sp = []
        self._vals = [0.0] * n
        for i in range(n):
            sp = NumEdit(decimals, lo, hi, step)
            sp.setToolTip(((tip + "\n") if tip else "") + labels[i % len(labels)])
            sp.valueChanged.connect(lambda v, i=i: self._edited(i, v))
            grid.addWidget(sp, i // cols, i % cols)
            self._sp.append(sp)

    def _edited(self, i, value):
        self._vals[i] = float(value)
        self.changed.emit(tuple(self._vals))

    def values(self):
        return tuple(self._vals)

    def set_values(self, vals):
        for i, (sp, v) in enumerate(zip(self._sp, vals)):
            self._vals[i] = float(v)
            sp.blockSignals(True)
            sp.setValue(float(v))
            sp.blockSignals(False)


class ColorSwatch(QtWidgets.QPushButton):
    """Поле цвета (образец; клик — выбор). Цвет RGBA 0..1, changed(tuple)."""

    changed = QtCore.Signal(tuple)

    def __init__(self, rgba=(1.0, 1.0, 1.0, 1.0), title="Color", tip=None,
                 parent=None):
        super().__init__(parent)
        self._rgba = tuple(rgba)
        self._title = title
        self.setFixedHeight(BTN_H)
        if tip:
            self.setToolTip(tip)
        self.clicked.connect(lambda _c=False: self._pick())
        self._paint()

    def rgba(self):
        return self._rgba

    def set_rgba(self, rgba):
        self._rgba = tuple(float(c) for c in rgba)
        self._paint()

    def _paint(self):
        r, g, b = [int(round(max(0.0, min(1.0, c)) * 255)) for c in self._rgba[:3]]
        self.setStyleSheet(
            "QPushButton{background:rgb(%d,%d,%d); border:1px solid %s; "
            "border-radius:2px;} QPushButton:disabled{background:%s;}"
            % (r, g, b, C['ctlbd'], C['dis']))

    def _pick(self):
        col = QtWidgets.QColorDialog.getColor(
            QtGui.QColor.fromRgbF(*(list(self._rgba) + [1.0] * 4)[:4]), self,
            self._title, QtWidgets.QColorDialog.ShowAlphaChannel)
        if col.isValid():
            self._rgba = (col.redF(), col.greenF(), col.blueF(), col.alphaF())
            self._paint()
            self.changed.emit(self._rgba)


class FieldBinder:
    """Контролы ↔ поля объекта сцены (2DFX, материал). add() привязывает
    контрол к ключу, load() заполняет контролы из словаря значений, правка
    контрола вызывает write(цель, ключ, значение); цель — self.node."""

    def __init__(self, write):
        self.node = None
        self._write = write
        self._items = []

    def add(self, key, default, w, after=None):
        """Привязать контрол к полю key; after() — после записи."""
        self._items.append((key, default, w))

        def write(value, k=key):
            if self.node is not None:
                try:
                    self._write(self.node, k, value)
                except Exception as e:                 # noqa: BLE001
                    if 'pymxs' not in str(e):
                        print("[INU] write %s: %r" % (k, e))
            if after is not None:
                after()
        if isinstance(w, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
            w.valueChanged.connect(write)
        elif isinstance(w, QtWidgets.QCheckBox) or (
                isinstance(w, QtWidgets.QPushButton) and w.isCheckable()):
            as_int = isinstance(default, int) and not isinstance(default, bool)
            w.toggled.connect(lambda on: write(int(on) if as_int else bool(on)))
        elif isinstance(w, (ColorSwatch, VecEdit)):
            w.changed.connect(lambda t: write(tuple(t)))
        elif isinstance(w, QtWidgets.QComboBox):
            if w.isEditable():
                w.lineEdit().editingFinished.connect(
                    lambda c=w: write(c.currentText().strip()))
                w.activated.connect(lambda _i, c=w: write(c.currentText().strip()))
            else:
                w.currentIndexChanged.connect(lambda i, c=w: write(c.itemData(i)))
        elif isinstance(w, QtWidgets.QLineEdit):
            w.editingFinished.connect(lambda e=w: write(e.text()))
        elif isinstance(w, QtWidgets.QButtonGroup):
            w.buttonClicked.connect(lambda b: write(b.property("seg_data")))
        return w

    def load(self, node, vals):
        self.node = node
        for key, default, w in self._items:
            v = vals.get(key, default)
            w.blockSignals(True)
            try:
                if isinstance(w, QtWidgets.QDoubleSpinBox):
                    w.setValue(float(v))
                elif isinstance(w, QtWidgets.QSpinBox):
                    w.setValue(int(v))
                elif isinstance(w, ColorSwatch):
                    w.set_rgba(v)
                elif isinstance(w, (QtWidgets.QCheckBox, QtWidgets.QPushButton)):
                    w.setChecked(bool(v))
                elif isinstance(w, VecEdit):
                    w.set_values(v)
                elif isinstance(w, QtWidgets.QComboBox):
                    i = w.findData(str(v))
                    if i >= 0:
                        w.setCurrentIndex(i)
                    elif w.isEditable():
                        w.setEditText(str(v))
                elif isinstance(w, QtWidgets.QLineEdit):
                    w.setText(str(v))
                elif isinstance(w, QtWidgets.QButtonGroup):
                    for b in w.buttons():
                        if b.property("seg_data") == str(v):
                            b.setChecked(True)
            finally:
                w.blockSignals(False)


class PropsDialog(QtWidgets.QDialog):
    """Небольшой модальный диалог с полями и OK / Cancel (как
    invoke_props_dialog операторов INU). Поля — в self.form."""

    def __init__(self, parent, title, width):
        super().__init__(parent)
        self.setObjectName("inuWin")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet(qss())
        self.setWindowTitle(title)
        self.setModal(True)
        try:                     # ввод в поля не уходит в шорткаты Max
            import qtmax
            qtmax.DisableMaxAcceleratorsOnFocus(self, True)
        except Exception:                              # noqa: BLE001
            pass
        self.setFixedWidth(width)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        self.form = QtWidgets.QVBoxLayout()
        self.form.setSpacing(4)
        outer.addLayout(self.form)
        outer.addStretch(1)
        self.ok = QtWidgets.QPushButton("OK")
        self.ok.setDefault(True)
        self.ok.clicked.connect(self.accept)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        self.buttons = FusedBlock([[self.ok, cancel]])
        row.addWidget(self.buttons)
        outer.addLayout(row)


class BuildMixin:
    """Конструкторы контролов, привязанных к settings, — общие для окон
    инструментов и панелей опций в окне выбора файлов. Класс-примесь:
    ставится ПЕРЕД Qt-классом (class X(BuildMixin, QtWidgets.QWidget))."""

    # — настройки —
    def _get(self, key, default):
        cur = settings.get(key) if settings else None
        return default if cur is None else cur

    def _set(self, key, value):
        if settings is not None:
            try:
                settings.set(key, value)
            except Exception:                          # noqa: BLE001
                pass

    # — раскладка —
    @staticmethod
    def _row(*widgets, spacing=4):
        hl = QtWidgets.QHBoxLayout()
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(spacing)
        for w in widgets:
            hl.addWidget(w, 1)
        return hl

    @staticmethod
    def _center(widget):
        hl = QtWidgets.QHBoxLayout()
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addStretch(1)
        hl.addWidget(widget)
        hl.addStretch(1)
        return hl

    @staticmethod
    def _group(title):
        """Группа как group "..." ( ) у Kam's. Возвращает layout с .box."""
        box = QtWidgets.QGroupBox(title)
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(4, 6, 4, 4)
        lay.setSpacing(4)
        lay.box = box
        return lay

    @staticmethod
    def _box(margins=(5, 4, 5, 4)):
        """Рамка без заголовка (box в INU). Возвращает layout с .box."""
        box = QtWidgets.QFrame()
        box.setObjectName("box")
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(*margins)
        lay.setSpacing(3)
        lay.box = box
        return lay

    def _path_field(self, key, mode='folder', filters=None, title="INU: Select",
                    placeholder='', tip=None, on_change=None):
        """Поле пути + кнопка «…» (наше окно выбора): mode 'folder' —
        папка, 'open' — файл. Путь хранится в settings[key]."""
        w = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(1)
        ed = QtWidgets.QLineEdit()
        ed.setFixedHeight(BTN_H)
        ed.setPlaceholderText(placeholder)
        ed.setText(str(self._get(key, '') or ''))
        if tip:
            ed.setToolTip(tip)

        def _changed(t, k=key):
            self._set(k, t)
            if on_change is not None:
                on_change()
        ed.textChanged.connect(_changed)
        hl.addWidget(ed, 1)

        def _browse():
            from .file_dialog import INUFileDialog
            cur = ed.text().strip()
            start = cur if (mode == 'folder' and cur) else \
                (QtCore.QFileInfo(cur).absolutePath() if cur else None)
            dlg = INUFileDialog(self, title, mode=mode, filters=filters,
                                key='path_' + key, start_dir=start,
                                accept_label="Select" if mode == 'folder' else "Open")
            if dlg.exec():
                res = dlg.selected_folder() if mode == 'folder' else \
                    (dlg.selected_files() or [''])[0]
                if res:
                    ed.setText(res)
        hl.addWidget(icon_btn('folder', "Browse…", _browse))
        w.edit = ed
        return w

    @staticmethod
    def _labeled(text, widget, label_w=46):
        """Ряд «подпись + контрол» (как spinner "VC" у Kam's)."""
        hl = QtWidgets.QHBoxLayout()
        hl.setContentsMargins(2, 0, 0, 0)
        hl.setSpacing(4)
        lab = QtWidgets.QLabel(text)
        lab.setFixedWidth(label_w)
        hl.addWidget(lab)
        hl.addWidget(widget, 1)
        return hl

    @staticmethod
    def _info(text, center=False):
        """Пояснение приглушённым текстом (как «Mass export is supported !»
        у Kam's)."""
        lbl = QtWidgets.QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#b8b8b8;")
        if center:
            lbl.setAlignment(QtCore.Qt.AlignCenter)
        return lbl

    # — контролы —
    def _seg_buttons(self, options, current, on_change, tooltip=None):
        """Взаимоисключающий ряд checkbutton'ов (зелёный = выбран).
        options — (подпись, значение[, подсказка]). Возвращает (кнопки,
        QButtonGroup); группу держим ссылкой, иначе GC."""
        group = QtWidgets.QButtonGroup(self)
        group.setExclusive(True)
        btns = []
        for opt in options:
            label, data = opt[0], opt[1]
            b = QtWidgets.QPushButton(label)
            b.setCheckable(True)
            b.setFixedHeight(BTN_H)
            b.setProperty("seg_data", data)
            tip = opt[2] if len(opt) > 2 else tooltip
            if tip:
                b.setToolTip(tip)
            if data == current:
                b.setChecked(True)
            group.addButton(b)
            btns.append(b)
        group.buttonClicked.connect(
            lambda btn: on_change(btn.property("seg_data")))
        return btns, group

    @staticmethod
    def _seg_sync(group, value):
        """Отметить в ряду checkbutton'ов кнопку со значением value."""
        for b in group.buttons():
            if b.property("seg_data") == value:
                b.setChecked(True)

    def _check(self, label, key, default, tip, on_change=None):
        """Чекбокс булевой опции, привязанный к settings."""
        cb = QtWidgets.QCheckBox(label)
        cb.setChecked(bool(self._get(key, default)))
        cb.setToolTip(tip)

        def _changed(v, k=key):
            self._set(k, bool(v))
            if on_change is not None:
                on_change()
        cb.toggled.connect(_changed)
        setattr(self, "cb_" + key, cb)
        return cb

    def _checks(self, items, cols=2):
        """Чекбоксы опций в сетке по 2 (как across:2 у Kam's).
        items — (подпись, ключ settings, по умолчанию, подсказка)."""
        grid = QtWidgets.QGridLayout()
        grid.setContentsMargins(2, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        for i, (label, key, default, tip) in enumerate(items):
            grid.addWidget(self._check(label, key, default, tip),
                           i // cols, i % cols)
        return grid

    def _tbtn(self, label, key, default, tip, on_change=None):
        """Checkbutton (зелёный = вкл) булевой опции, привязанный к settings —
        для коротких тумблеров в ряд (форматы, Auto)."""
        b = QtWidgets.QPushButton(label)
        b.setCheckable(True)
        b.setFixedHeight(BTN_H)
        b.setChecked(bool(self._get(key, default)))
        b.setToolTip(tip)

        def _changed(v, k=key):
            self._set(k, bool(v))
            if on_change is not None:
                on_change()
        b.toggled.connect(_changed)
        return b

    def _combo(self, key, items, default, tip=None, on_change=None):
        """Выпадающий список, привязанный к settings. items — (подпись,
        значение, подсказка пункта)."""
        cb = QtWidgets.QComboBox()
        cb.setFixedHeight(BTN_H)
        cur = self._get(key, default)
        for i, (label, data, itip) in enumerate(items):
            cb.addItem(label, data)
            if itip:
                cb.setItemData(i, itip, QtCore.Qt.ToolTipRole)
            if data == cur:
                cb.setCurrentIndex(i)
        if tip:
            cb.setToolTip(tip)

        def _changed(i, k=key):
            self._set(k, cb.itemData(i))
            if on_change is not None:
                on_change()
        cb.currentIndexChanged.connect(_changed)
        return cb

    def _line(self, key, placeholder, tip=None):
        """Строка ввода, привязанная к settings."""
        ed = QtWidgets.QLineEdit()
        ed.setFixedHeight(BTN_H)
        ed.setPlaceholderText(placeholder)
        ed.setText(str(self._get(key, '') or ''))
        if tip:
            ed.setToolTip(tip)
        ed.textChanged.connect(lambda t, k=key: self._set(k, t))
        return ed

    def _spin(self, key, lo, hi, default, tip=None, prefix=''):
        """Целочисленный спиннер, привязанный к settings. prefix — подпись
        внутри поля («Start: 0»), как числовые поля Blender."""
        sp = QtWidgets.QSpinBox()
        sp.setFixedHeight(BTN_H)
        sp.setRange(lo, hi)
        sp.setPrefix(prefix)
        sp.setValue(int(self._get(key, default)))
        if tip:
            sp.setToolTip(tip)
        sp.valueChanged.connect(lambda v, k=key: self._set(k, int(v)))
        return sp

    def _dspin(self, key, lo, hi, default, decimals=3, step=0.01, tip=None,
               prefix='', suffix=''):
        """Дробный спиннер, привязанный к settings (точка — разделитель)."""
        sp = QtWidgets.QDoubleSpinBox()
        sp.setLocale(QtCore.QLocale.c())
        sp.setFixedHeight(BTN_H)
        sp.setRange(lo, hi)
        sp.setDecimals(decimals)
        sp.setSingleStep(step)
        sp.setPrefix(prefix)
        sp.setSuffix(suffix)
        sp.setValue(float(self._get(key, default)))
        if tip:
            sp.setToolTip(tip)
        sp.valueChanged.connect(lambda v, k=key: self._set(k, float(v)))
        return sp


def err_color():
    return C['err']
