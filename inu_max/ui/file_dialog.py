# INU Tools (Max) — своё окно выбора файлов (вместо диалога Max).
#
# Обзор папок как в файловом браузере Blender: сверху — назад / вперёд / вверх /
# обновить / новая папка, редактируемая строка пути и фильтр по имени; слева —
# разделы Volumes (диски), System (Home, Desktop…), Bookmarks (свои закладки)
# и Recent (недавние папки). Внизу, как у диалога Max, — File name и Files of
# type. Справа — панель опций INU (как боковая
# панель файлового браузера Blender в диалогах импорта/экспорта). Палитра —
# как у роллаутов Kam's (тёмная, без белого списка Windows).
#
# Режимы: 'open' — один файл, 'open_multi' — несколько, 'folder' — папка,
# 'save' — путь нового файла, 'export' — папка + имя экспорта (как Export
# All в INU: клик по файлу задаёт имя).

import json
import os
import tempfile

from ..qt import QtWidgets, QtCore, QtGui

from .style import qss, BTN_H, SB_W, SB_GAP
from .widgets import scrolled, content_min_width

# История папок и последняя папка по назначению — в файле, чтобы
# переживать перезапуск окон (настройки панели сбрасываются при каждом).
_STATE_FILE = os.path.join(
    os.environ.get('LOCALAPPDATA') or tempfile.gettempdir(),
    'INU_Tools_Max', 'file_dialog.json')
_HISTORY_MAX = 15
_PLACES_W = 92             # ширина подписей нижних полей
_SIDE_W = 176              # боковая панель (как в Blender)
_THIS_PC = ''              # корень «Этот компьютер» (список дисков)


class _DirModel(QtCore.QAbstractTableModel):
    """Список одной папки — синхронно, через os.scandir, в главном потоке.

    QFileSystemModel здесь не годится: он читает папку и зовёт провайдер
    иконок/типов в СВОЁМ потоке и следит за папкой. Стандартный провайдер
    Qt6 берёт «Type» через QMimeDatabase — для незнакомых .txd/.col он
    читает каждый файл (папка на тысячи моделей вешала Max), а свой
    Python-провайдер из чужого потока упирается в GIL, который держит Max,
    — зависание после импорта (PNG пишутся в отслеживаемую папку). Здесь
    потоков нет: scandir отдаёт размер и дату без открытия файлов, иконка
    оболочки — одна на расширение (кэш), тип — по расширению.

    Колонки как у QFileSystemModel: 0 Name, 1 Size, 2 Type, 3 Date Modified."""

    _HEAD = ("Name", "Size", "Type", "Date Modified")

    def __init__(self, parent=None, dirs_only=False):
        super().__init__(parent)
        self._root = _THIS_PC
        self._rows = []          # (имя, папка?, размер, mtime, путь) — показанные
        self._all = []           # все строки папки (до фильтра по имени)
        self._text = ''          # фильтр по имени (поле поиска, как в Blender)
        self._pats = []
        self._dirs_only = dirs_only
        self._sort = (0, QtCore.Qt.AscendingOrder)
        self._prov = QtWidgets.QFileIconProvider()
        self._icons = {}
        self._loc = QtCore.QLocale()

    # — API, которым пользуется окно (подмножество QFileSystemModel) —
    def setRootPath(self, path):                       # noqa: N802
        self._root = path or _THIS_PC
        self._reload()

    def setNameFilters(self, pats):                    # noqa: N802
        self._pats = [p.lower() for p in pats]
        self._reload()

    def setTextFilter(self, text):                     # noqa: N802
        """Фильтр по части имени (без повторного чтения папки)."""
        self._text = (text or '').strip().lower()
        self.beginResetModel()
        self._filter_text()
        self.endResetModel()

    def refresh(self):
        self._reload()

    def _filter_text(self):
        t = self._text
        self._rows = [r for r in self._all if t in r[0].lower()] if t else list(self._all)
        self._apply_sort()

    def index(self, *args):
        if len(args) == 1 and isinstance(args[0], str):
            path = _clean(args[0])
            for r, row in enumerate(self._rows):
                if _clean(row[4]) == path:
                    return self.createIndex(r, 0)
            return QtCore.QModelIndex()     # корень списка = сама папка
        return super().index(*args)

    def filePath(self, idx):                           # noqa: N802
        return self._rows[idx.row()][4] if idx.isValid() else self._root

    def fileName(self, idx):                           # noqa: N802
        return self._rows[idx.row()][0] if idx.isValid() else ''

    def isDir(self, idx):                              # noqa: N802
        return self._rows[idx.row()][1] if idx.isValid() else True

    def mkdir(self, _parent, name):
        path = os.path.join(self._root, name)
        try:
            os.mkdir(path)
        except OSError:
            return QtCore.QModelIndex()
        self._reload()
        return self.index(_clean(path))

    # — чтение папки —
    def _reload(self):
        import fnmatch
        rows = []
        if not self._root:
            for d in QtCore.QDir.drives():
                p = _clean(d.absoluteFilePath())
                rows.append((_drive_label(p), True, -1, 0.0, p))
        else:
            try:
                it = list(os.scandir(self._root))
            except OSError:
                it = []
            for e in it:
                try:
                    is_dir = e.is_dir()
                    if not is_dir and self._dirs_only:
                        continue
                    if not is_dir and self._pats and not any(
                            fnmatch.fnmatchcase(e.name.lower(), p) for p in self._pats):
                        continue
                    st = e.stat()
                    rows.append((e.name, is_dir, -1 if is_dir else st.st_size,
                                 st.st_mtime, _clean(e.path)))
                except OSError:
                    continue
        self.beginResetModel()
        self._all = rows
        self._filter_text()
        self.endResetModel()

    def _apply_sort(self):
        col, order = self._sort
        keys = {0: (lambda r: r[0].lower()) if self._root else (lambda r: r[4]),
                1: lambda r: r[2],
                2: lambda r: self._type(r).lower(), 3: lambda r: r[3]}
        rev = order == QtCore.Qt.DescendingOrder
        self._rows.sort(key=keys.get(col, keys[0]), reverse=rev)
        self._rows.sort(key=lambda r: not r[1])        # папки — всегда сверху

    def sort(self, column, order=QtCore.Qt.AscendingOrder):
        self._sort = (column, order)
        self.layoutAboutToBeChanged.emit()
        self._apply_sort()
        self.layoutChanged.emit()

    # — отображение —
    def _type(self, r):
        if not self._root:
            return "Drive"
        if r[1]:
            return "Folder"
        ext = os.path.splitext(r[0])[1][1:]
        return (ext.upper() + " File") if ext else "File"

    def _icon(self, r):
        key = r[4] if not self._root else ('/dir' if r[1] else
                                          os.path.splitext(r[0])[1].lower())
        ic = self._icons.get(key)
        if ic is None:
            ic = self._prov.icon(QtCore.QFileInfo(r[4]))
            self._icons[key] = ic
        return ic

    def rowCount(self, parent=QtCore.QModelIndex()):   # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QtCore.QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else 4

    def headerData(self, s, orient, role=QtCore.Qt.DisplayRole):  # noqa: N802
        if orient == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._HEAD[s]
        return None

    def data(self, idx, role=QtCore.Qt.DisplayRole):
        if not idx.isValid():
            return None
        r, c = self._rows[idx.row()], idx.column()
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            if c == 0:
                return r[0]
            if c == 1:
                return "" if r[2] < 0 else self._loc.formattedDataSize(r[2])
            if c == 2:
                return self._type(r)
            if c == 3 and r[3]:
                return QtCore.QDateTime.fromSecsSinceEpoch(int(r[3])).toString(
                    "dd.MM.yyyy HH:mm")
            return ""
        if role == QtCore.Qt.DecorationRole and c == 0:
            return self._icon(r)
        if role == QtCore.Qt.TextAlignmentRole and c == 1:
            return int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        return None

    def flags(self, idx):
        f = super().flags(idx)
        if idx.isValid() and idx.column() == 0 and self._root:
            f |= QtCore.Qt.ItemIsEditable              # F2 — переименовать
        return f

    def setData(self, idx, value, role=QtCore.Qt.EditRole):  # noqa: N802
        if role != QtCore.Qt.EditRole or not idx.isValid():
            return False
        name = str(value).strip()
        r = self._rows[idx.row()]
        if not name or name == r[0] or any(ch in name for ch in '\\/:*?"<>|'):
            return False
        new = os.path.join(self._root, name)
        try:
            os.rename(r[4], new)
        except OSError:
            return False
        new_row = (name, r[1], r[2], r[3], _clean(new))
        self._all = [new_row if x is r else x for x in self._all]
        self._rows[idx.row()] = new_row
        self.dataChanged.emit(idx, idx)
        return True


def _load_state():
    try:
        with open(_STATE_FILE, 'r', encoding='utf-8') as f:
            st = json.load(f)
        return st if isinstance(st, dict) else {}
    except Exception:                                  # noqa: BLE001
        return {}


def _save_state(st):
    try:
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        with open(_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
    except Exception as e:                             # noqa: BLE001
        print("[INU] file dialog state: %r" % (e,))


def _clean(path):
    """Путь в виде Qt (прямые слэши), '' — «Этот компьютер»."""
    if not path:
        return _THIS_PC
    return QtCore.QDir.cleanPath(QtCore.QDir.fromNativeSeparators(path))


def _is_drive_root(path):
    p = _clean(path)
    return len(p) <= 3 and p.endswith(':/') or (len(p) == 2 and p.endswith(':'))


def _parent(path):
    if not path or _is_drive_root(path):
        return _THIS_PC
    return _clean(os.path.dirname(path.rstrip('/')))


def _drive_label(root):
    """«Local Disk (C:)» — метка тома и буква диска."""
    letter = root.rstrip('/\\')
    try:
        name = QtCore.QStorageInfo(root).displayName()
    except Exception:                                  # noqa: BLE001
        name = ''
    name = name if name and name.rstrip('/\\') != letter else "Local Disk"
    return "%s (%s)" % (name, letter)


def _parse_names(text):
    """'"a.dff" "b.txd"' → [a.dff, b.txd]; одиночное имя — как есть."""
    text = text.strip()
    if '"' not in text:
        return [text] if text else []
    out, cur, inq = [], '', False
    for ch in text:
        if ch == '"':
            if inq and cur:
                out.append(cur)
            cur, inq = '', not inq
        elif inq:
            cur += ch
    return out


class _Sidebar(QtWidgets.QWidget):
    """Боковая панель как у Blender: сворачиваемые разделы Volumes, System,
    Bookmarks (+ / − под списком), Recent. Клик по строке — перейти."""

    def __init__(self, state, go, parent=None):
        super().__init__(parent)
        self._state, self._go = state, go
        self._prov = QtWidgets.QFileIconProvider()
        self.setFixedWidth(_SIDE_W)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(10)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIconSize(QtCore.QSize(16, 16))
        self.tree.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemExpanded.connect(lambda it: self._remember_open(it, True))
        self.tree.itemCollapsed.connect(lambda it: self._remember_open(it, False))
        lay.addWidget(self.tree, 1)
        # закладки: добавить текущую папку / удалить выбранную (+ / − Blender)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(2)
        from .style import icon
        self.btn_add = QtWidgets.QToolButton()
        self.btn_add.setIcon(icon('add'))
        self.btn_add.setToolTip("Add the current folder to Bookmarks")
        self.btn_del = QtWidgets.QToolButton()
        self.btn_del.setIcon(icon('remove'))
        self.btn_del.setToolTip("Remove the selected bookmark")
        for b in (self.btn_add, self.btn_del):
            b.setAutoRaise(True)
            b.setFixedSize(24, BTN_H)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.btn_add.clicked.connect(lambda: self.add_bookmark(self.cwd))
        self.btn_del.clicked.connect(lambda: self.remove_bookmark())
        self.cwd = None
        self.rebuild()

    # — наполнение —
    def _section(self, title):
        it = QtWidgets.QTreeWidgetItem([title])
        f = it.font(0)
        f.setBold(True)
        it.setFont(0, f)
        it.setFlags(QtCore.Qt.ItemIsEnabled)
        self.tree.addTopLevelItem(it)
        return it

    def _place(self, sec, label, path, icon=None):
        it = QtWidgets.QTreeWidgetItem([label])
        it.setData(0, QtCore.Qt.UserRole, path)
        it.setToolTip(0, QtCore.QDir.toNativeSeparators(path) if path else "This PC")
        it.setIcon(0, icon or self._prov.icon(QtCore.QFileInfo(path)))
        sec.addChild(it)
        return it

    def rebuild(self):
        self.tree.clear()
        opened = self._state.get('side_open', {})
        vol = self._section("Volumes")
        for d in QtCore.QDir.drives():
            root = _clean(d.absoluteFilePath())
            self._place(vol, _drive_label(root), root, self._prov.icon(d))
        sysx = self._section("System")
        std = QtCore.QStandardPaths
        for label, loc in (("Home", std.HomeLocation), ("Desktop", std.DesktopLocation),
                           ("Documents", std.DocumentsLocation),
                           ("Downloads", std.DownloadLocation)):
            p = std.writableLocation(loc)
            if p and os.path.isdir(p):
                self._place(sysx, label, _clean(p))
        bm = self._section("Bookmarks")
        for p in self._state.get('bookmarks', []):
            self._place(bm, os.path.basename(p.rstrip('/')) or p, p)
        rec = self._section("Recent")
        for p in [h for h in self._state.get('history', []) if h and os.path.isdir(h)]:
            self._place(rec, os.path.basename(p.rstrip('/')) or p, p)
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            it.setExpanded(opened.get(it.text(0), True))
        self.mark(self.cwd)

    def mark(self, cwd):
        """Подсветить строку текущей папки (как активный пункт в Blender)."""
        self.cwd = cwd
        self.tree.clearSelection()
        key = (cwd or '').lower()
        if not key:
            return
        for i in range(self.tree.topLevelItemCount()):
            sec = self.tree.topLevelItem(i)
            for j in range(sec.childCount()):
                it = sec.child(j)
                if (it.data(0, QtCore.Qt.UserRole) or '').lower() == key:
                    it.setSelected(True)
                    return

    # — действия —
    def _clicked(self, it, _col):
        if it.parent() is not None:
            self._go(it.data(0, QtCore.Qt.UserRole))

    def _remember_open(self, it, value):
        if it.parent() is None:
            self._state.setdefault('side_open', {})[it.text(0)] = value
            _save_state(self._state)

    def add_bookmark(self, path):
        if not path:
            return
        marks = self._state.setdefault('bookmarks', [])
        if path.lower() not in [m.lower() for m in marks]:
            marks.append(path)
            _save_state(self._state)
            self.rebuild()

    def remove_bookmark(self, path=None):
        if path is None:
            it = self.tree.currentItem()
            if it is not None and it.parent() is not None \
                    and it.parent().text(0) == "Bookmarks":
                path = it.data(0, QtCore.Qt.UserRole)
        marks = self._state.get('bookmarks', [])
        if path and path in marks:
            marks.remove(path)
            _save_state(self._state)
            self.rebuild()

    def _menu(self, pos):
        it = self.tree.itemAt(pos)
        if it is None or it.parent() is None:
            return
        sec = it.parent().text(0)
        path = it.data(0, QtCore.Qt.UserRole)
        m = QtWidgets.QMenu(self)
        if sec == "Bookmarks":
            m.addAction("Remove bookmark", lambda: self.remove_bookmark(path))
        else:
            m.addAction("Add to Bookmarks", lambda: self.add_bookmark(path))
        if sec == "Recent":
            m.addAction("Clear recent", self._clear_recent)
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def _clear_recent(self):
        self._state['history'] = []
        _save_state(self._state)
        self.rebuild()


class INUFileDialog(QtWidgets.QDialog):
    """Окно выбора файлов INU (см. шапку модуля).

    filters — [(подпись, [маски])]; key — под каким ключом помнить последнюю
    папку; options — панель опций справа (или None); filename — имя по
    умолчанию; start_dir — начальная папка (иначе последняя по key);
    confirm_overwrite — спрашивать о замене существующего файла (save;
    False — файл дополняется, как пак IFP)."""

    def __init__(self, parent=None, title="INU: Open", mode='open',
                 filters=None, key='default', accept_label="Open",
                 options=None, filename='', start_dir=None,
                 confirm_overwrite=True):
        super().__init__(parent)
        self.setObjectName("inuWin")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet(qss())
        self.setWindowTitle(title)
        self.setModal(True)
        try:                     # ввод имени файла не уходит в шорткаты Max
            import qtmax
            qtmax.DisableMaxAcceleratorsOnFocus(self, True)
        except Exception:                              # noqa: BLE001
            pass
        self._mode = mode
        self._key = key
        self._confirm = confirm_overwrite
        self._filters = filters or [("All Files (*.*)", ["*"])]
        self._state = _load_state()
        self._back = []
        self._fwd = []
        self._cwd = None
        self._files = []
        self._target = None
        self._folder = None
        self._save_path = None
        self._prov = QtWidgets.QFileIconProvider()

        self._model = _DirModel(self, dirs_only=(mode == 'folder'))

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        outer.addLayout(self._build_top())

        mid = QtWidgets.QHBoxLayout()
        mid.setSpacing(4)
        outer.addLayout(mid, 1)          # сразу в окно: виджеты получают QSS
        self._side = _Sidebar(self._state, self._go)
        mid.addWidget(self._side)
        mid.addWidget(self._build_views(), 1)
        self._opts_w = 0
        if options is not None:
            lay, _view, _strip = scrolled(options)
            box = QtWidgets.QWidget()
            box.setLayout(lay)
            mid.addWidget(box)
            # ширину меряем уже внутри окна: без нашего QSS кнопки Qt
            # считаются по 80px и панель выходит вдвое шире
            self._opts_w = content_min_width(options) + SB_W + SB_GAP
            box.setFixedWidth(self._opts_w)
        outer.addLayout(self._build_bottom(accept_label, filename))

        self.resize(760 + self._opts_w, 540)
        self._apply_filter()
        start = start_dir if start_dir and os.path.isdir(start_dir) else \
            self._state.get('last', {}).get(key)
        if not (start and os.path.isdir(start)):
            start = QtCore.QStandardPaths.writableLocation(
                QtCore.QStandardPaths.DocumentsLocation)
        self._go(_clean(start), push=False)

    # — построение —
    def _tool(self, icon, tip, slot):
        b = QtWidgets.QToolButton()
        b.setIcon(self.style().standardIcon(icon))
        b.setToolTip(tip)
        b.setAutoRaise(True)
        b.setFixedSize(24, BTN_H + 1)
        b.clicked.connect(slot)
        return b

    def _build_top(self):
        """Верх как у Blender: ◀ ▶ ⤴ ⟳ 📁+ | путь (редактируется) | фильтр | вид."""
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(2)
        sp = QtWidgets.QStyle
        self._btn_back = self._tool(sp.SP_ArrowBack, "Back (Alt+Left)", self._go_back)
        self._btn_fwd = self._tool(sp.SP_ArrowForward, "Forward (Alt+Right)", self._go_forward)
        self._btn_up = self._tool(sp.SP_FileDialogToParent, "Parent folder (Backspace)",
                                  self._go_up)
        self._btn_refresh = self._tool(sp.SP_BrowserReload, "Refresh (F5)", self._refresh)
        self._btn_new = self._tool(sp.SP_FileDialogNewFolder, "New folder",
                                   self._new_folder)
        for b in (self._btn_back, self._btn_fwd, self._btn_up, self._btn_refresh,
                  self._btn_new):
            row.addWidget(b)
        row.addSpacing(4)
        self._path = QtWidgets.QLineEdit()
        self._path.setFixedHeight(BTN_H)
        self._path.setToolTip("Folder path — type or paste a path and press Enter")
        self._path.returnPressed.connect(self._go_path)
        row.addWidget(self._path, 1)
        row.addSpacing(4)
        self._search = QtWidgets.QLineEdit()
        self._search.setFixedHeight(BTN_H)
        self._search.setFixedWidth(150)
        self._search.setPlaceholderText("Filter")
        self._search.setClearButtonEnabled(True)
        self._search.setToolTip("Show only files and folders whose name contains this text")
        self._search.textChanged.connect(self._model.setTextFilter)
        row.addWidget(self._search)
        self._btn_view = QtWidgets.QToolButton()
        self._btn_view.setIcon(self.style().standardIcon(sp.SP_FileDialogDetailedView))
        self._btn_view.setToolTip("View")
        self._btn_view.setAutoRaise(True)
        self._btn_view.setFixedSize(24, BTN_H + 1)
        self._btn_view.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu = QtWidgets.QMenu(self._btn_view)
        menu.addAction("Details", lambda: self._set_view(0))
        menu.addAction("List", lambda: self._set_view(1))
        self._btn_view.setMenu(menu)
        row.addWidget(self._btn_view)
        return row

    def _build_views(self):
        self._stack = QtWidgets.QStackedWidget()
        multi = self._mode == 'open_multi'
        sel_mode = (QtWidgets.QAbstractItemView.ExtendedSelection if multi
                    else QtWidgets.QAbstractItemView.SingleSelection)
        edit = QtWidgets.QAbstractItemView.EditKeyPressed  # F2 — переименовать

        tree = QtWidgets.QTreeView()
        tree.setModel(self._model)
        tree.setRootIsDecorated(False)
        tree.setItemsExpandable(False)
        tree.setUniformRowHeights(True)
        tree.setSortingEnabled(True)
        tree.sortByColumn(0, QtCore.Qt.AscendingOrder)
        tree.setSelectionMode(sel_mode)
        tree.setEditTriggers(edit)
        h = tree.header()
        # порядок колонок как у Max: Name, Date Modified, Type, Size
        h.moveSection(h.visualIndex(3), 1)
        h.moveSection(h.visualIndex(2), 2)
        h.setStretchLastSection(True)      # Size — до правого края, как у Max
        for col, w in ((0, 220), (3, 118), (2, 74)):
            tree.setColumnWidth(col, w)

        lst = QtWidgets.QListView()
        lst.setModel(self._model)
        lst.setViewMode(QtWidgets.QListView.ListMode)
        lst.setFlow(QtWidgets.QListView.TopToBottom)
        lst.setWrapping(True)
        lst.setResizeMode(QtWidgets.QListView.Adjust)
        lst.setSelectionMode(sel_mode)
        lst.setEditTriggers(edit)

        for v in (tree, lst):
            v.doubleClicked.connect(self._activate)
            v.selectionModel().selectionChanged.connect(self._on_selection)
            v.installEventFilter(self)
            self._stack.addWidget(v)
        self._tree, self._list = tree, lst
        return self._stack

    def _build_bottom(self, accept_label, filename):
        g = QtWidgets.QGridLayout()
        g.setHorizontalSpacing(6)
        g.setVerticalSpacing(6)
        labs = []
        for r, text in enumerate(("Folder:" if self._mode == 'folder'
                                  else "File name:", "Files of type:")):
            lab = QtWidgets.QLabel(text)
            lab.setFixedWidth(_PLACES_W - 8)
            lab.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            g.addWidget(lab, r, 0)
            labs.append(lab)
        self._name = QtWidgets.QComboBox()
        self._name.setEditable(True)
        self._name.setFixedHeight(BTN_H)
        self._name.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self._name.setEditText(filename or '')
        # Enter в поле имени нажимает кнопку по умолчанию (accept) — отдельно
        # returnPressed не подключаем, иначе принятие сработает дважды
        g.addWidget(self._name, 0, 1)
        self._type = QtWidgets.QComboBox()
        self._type.setFixedHeight(BTN_H)
        for label, _p in self._filters:
            self._type.addItem(label)
        self._type.currentIndexChanged.connect(lambda _i: self._apply_filter())
        g.addWidget(self._type, 1, 1)
        if self._mode == 'folder':          # тип файлов папке не нужен
            labs[1].setVisible(False)
            self._type.setVisible(False)
        ok = QtWidgets.QPushButton(accept_label)
        ok.setFixedSize(84, BTN_H + 2)
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setFixedSize(84, BTN_H + 2)
        cancel.clicked.connect(self.reject)
        g.addWidget(ok, 0, 2)
        g.addWidget(cancel, 1, 2)
        g.setColumnStretch(1, 1)
        return g

    # — фильтры —
    def set_filters(self, filters):
        """Пересобрать «Files of type» (например, по галочкам форматов)."""
        keep = self._type.currentIndex()
        self._filters = filters or [("All Files (*.*)", ["*"])]
        self._type.blockSignals(True)
        self._type.clear()
        for label, _p in self._filters:
            self._type.addItem(label)
        self._type.setCurrentIndex(max(0, min(keep, len(self._filters) - 1)))
        self._type.blockSignals(False)
        self._apply_filter()

    def _apply_filter(self):
        i = max(0, self._type.currentIndex())
        pats = self._filters[i][1] if i < len(self._filters) else ["*"]
        self._model.setNameFilters([] if pats == ["*"] else list(pats))

    # — навигация —
    def _view(self):
        return self._stack.currentWidget()

    def _set_view(self, i):
        self._stack.setCurrentIndex(i)
        self._btn_view.setIcon(self.style().standardIcon(
            QtWidgets.QStyle.SP_FileDialogDetailedView if i == 0
            else QtWidgets.QStyle.SP_FileDialogListView))

    def _go(self, path, push=True):
        path = _clean(path)
        if path and not os.path.isdir(path):
            return
        if push and self._cwd is not None and path != self._cwd:
            self._back.append(self._cwd)
            self._fwd = []
        self._cwd = path
        self._model.setRootPath(path)
        root = self._model.index(path) if path else QtCore.QModelIndex()
        for v in (self._tree, self._list):
            v.setRootIndex(root)
            v.clearSelection()
        self._btn_back.setEnabled(bool(self._back))
        self._btn_fwd.setEnabled(bool(self._fwd))
        self._btn_up.setEnabled(bool(path))
        self._btn_new.setEnabled(bool(path))
        self._path.setText(QtCore.QDir.toNativeSeparators(path) if path else "This PC")
        self._path.setStyleSheet("")
        self._side.mark(path)

    def _go_back(self):
        if self._back:
            self._fwd.append(self._cwd)
            self._go(self._back.pop(), push=False)

    def _go_forward(self):
        if self._fwd:
            self._back.append(self._cwd)
            self._go(self._fwd.pop(), push=False)

    def _go_up(self):
        if self._cwd:
            self._go(_parent(self._cwd))

    def _refresh(self):
        self._model.refresh()

    def _go_path(self):
        """Enter в строке пути: папка — перейти; файл — перейти в его папку и
        подставить имя; иначе — подсветить строку красным."""
        text = self._path.text().strip().strip('"')
        text = os.path.expandvars(os.path.expanduser(text))
        if not text or text.lower() == "this pc":
            self._go(_THIS_PC)
        elif os.path.isdir(text):
            self._go(text)
        elif os.path.isfile(text):
            self._go(os.path.dirname(text))
            self._name.setEditText(os.path.basename(text))
        else:
            self._path.setStyleSheet("border: 1px solid #E06C6C;")
            return
        self._view().setFocus()

    def _new_folder(self):
        if not self._cwd:
            return
        base, name, i = "New folder", "New folder", 2
        while os.path.exists(os.path.join(self._cwd, name)):
            name = "%s (%d)" % (base, i)
            i += 1
        idx = self._model.mkdir(self._model.index(self._cwd), name)
        if idx.isValid():
            v = self._view()
            v.setCurrentIndex(idx)
            v.edit(idx)

    # — выбор —
    def _selected_paths(self):
        v = self._view()
        sm = v.selectionModel()
        if sm is None or v.model() is None:            # окно закрывается
            return []
        rows = sm.selectedRows(0) if v is self._tree else sm.selectedIndexes()
        return [self._model.filePath(i) for i in rows]

    def _on_selection(self, *_a):
        if self._mode == 'folder':
            dirs = [p for p in self._selected_paths() if os.path.isdir(p)]
            if dirs:
                self._name.setEditText(os.path.basename(dirs[0].rstrip('/'))
                                       or dirs[0])
            return
        files = [p for p in self._selected_paths() if os.path.isfile(p)]
        if not files:
            return
        names = [os.path.basename(p) for p in files]
        if self._mode == 'export':
            n = names[0]
            # как в INU: клик по файлу задаёт имя экспорта; .txd — «все
            # текстуры в этот TXD», поэтому его имя оставляем с расширением
            if not n.lower().endswith('.txd'):
                n = os.path.splitext(n)[0]
            self._name.setEditText(n)
        elif len(names) == 1 or self._mode == 'save':
            self._name.setEditText(names[0])
        else:
            self._name.setEditText(" ".join('"%s"' % n for n in names))

    def _activate(self, index):
        path = self._model.filePath(index)
        if self._model.isDir(index) or not path:
            self._go(path)
        elif self._mode not in ('export', 'folder'):
            self._name.setEditText(os.path.basename(path))
            self._accept()

    def _resolve(self, name):
        return _clean(name if os.path.isabs(name) else
                      os.path.join(self._cwd or '', name))

    def _accept(self):
        text = self._name.currentText().strip()
        if self._mode == 'folder':
            self._accept_folder(text)
            return
        names = _parse_names(text)
        # имя — папка (или путь к папке): перейти в неё
        if len(names) == 1 and os.path.isdir(self._resolve(names[0])):
            self._go(self._resolve(names[0]))
            self._name.setEditText('')
            return
        if self._mode == 'export':
            if not self._cwd:
                self._warn("Choose a folder to export to.")
                return
            self._target = (QtCore.QDir.toNativeSeparators(self._cwd), text)
        elif self._mode == 'save':
            if not self._cwd or not text:
                self._warn("Enter a file name.")
                return
            path = self._resolve(text)
            pats = self._filters[max(0, self._type.currentIndex())][1]
            if (not os.path.splitext(path)[1] and len(pats) == 1
                    and pats[0].startswith('*.')):
                path += pats[0][1:]           # имя без расширения — добавить
            if self._confirm and os.path.exists(path) and QtWidgets.QMessageBox.question(
                    self, self.windowTitle(),
                    "%s already exists.\nReplace it?"
                    % os.path.basename(path)) != QtWidgets.QMessageBox.Yes:
                return
            self._save_path = QtCore.QDir.toNativeSeparators(path)
        else:
            if not names:
                dirs = [p for p in self._selected_paths() if os.path.isdir(p)]
                if dirs:
                    self._go(dirs[0])
                return
            paths = [self._resolve(n) for n in names]
            missing = [p for p in paths if not os.path.isfile(p)]
            if missing:
                self._warn("File not found:\n" + "\n".join(
                    QtCore.QDir.toNativeSeparators(p) for p in missing))
                return
            if self._mode == 'open':
                paths = paths[:1]
            self._files = [QtCore.QDir.toNativeSeparators(p) for p in paths]
        self._remember()
        self.accept()

    def _warn(self, text):
        QtWidgets.QMessageBox.warning(self, self.windowTitle(), text)

    def _remember(self):
        if not self._cwd:
            return
        st = self._state
        st.setdefault('last', {})[self._key] = self._cwd
        hist = [h for h in st.get('history', []) if h != self._cwd]
        st['history'] = ([self._cwd] + hist)[:_HISTORY_MAX]
        _save_state(st)
        self._side.rebuild()

    # — клавиши в списке: Backspace — вверх, Alt+Left — назад, Enter —
    #   открыть папку / принять файл —
    def eventFilter(self, obj, ev):                    # noqa: N802
        if ev.type() == QtCore.QEvent.KeyPress and obj in (self._tree, self._list):
            k = ev.key()
            if k == QtCore.Qt.Key_Backspace:
                self._go_up()
                return True
            if k == QtCore.Qt.Key_Left and ev.modifiers() & QtCore.Qt.AltModifier:
                self._go_back()
                return True
            if k == QtCore.Qt.Key_Right and ev.modifiers() & QtCore.Qt.AltModifier:
                self._go_forward()
                return True
            if k == QtCore.Qt.Key_F5:
                self._refresh()
                return True
            if k in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                idx = obj.currentIndex()
                if idx.isValid() and self._model.isDir(idx):
                    self._go(self._model.filePath(idx))
                else:
                    self._accept()
                return True
        return super().eventFilter(obj, ev)

    # — результат —
    def done(self, result):
        """Закрытие окна: сначала отвязать модель от списков. Модель — на
        Python и создана раньше списков, поэтому Qt удаляет её первой, а
        списки ещё зовут её rowCount → краш Max. Результаты (_files,
        _target, …) к этому моменту уже сохранены."""
        self.removeEventFilter(self)
        for v in (self._tree, self._list):
            try:
                v.removeEventFilter(self)
                v.setModel(None)
            except Exception:                          # noqa: BLE001
                pass
        super().done(result)

    def selected_files(self):
        """Выбранные файлы (режимы open / open_multi)."""
        return list(self._files)

    def target(self):
        """(папка, имя экспорта) — режим export; имя может быть пустым."""
        return self._target

    def selected_folder(self):
        """Выбранная папка — режим folder."""
        return self._folder

    def save_path(self):
        """Путь нового файла — режим save."""
        return self._save_path

    def _accept_folder(self, text):
        """Папка: выделенная в списке, иначе введённая, иначе текущая."""
        dirs = [p for p in self._selected_paths() if os.path.isdir(p)]
        if dirs:
            path = dirs[0]
        elif text and os.path.isdir(self._resolve(text)):
            path = self._resolve(text)
        else:
            path = self._cwd
        if not path:
            self._warn("Choose a folder.")
            return
        self._folder = QtCore.QDir.toNativeSeparators(path)
        self._remember()
        self.accept()


def filters_from_max(spec):
    """«GTA IDE (*.ide)|*.ide» (формат типов Max) → [(подпись, [маски])] +
    «All Files»."""
    parts = [p for p in (spec or '').split('|')]
    out = []
    for i in range(0, len(parts) - 1, 2):
        label, pats = parts[i].strip(), parts[i + 1].strip()
        if label and pats:
            out.append((label, [p.strip() for p in pats.split(';') if p.strip()]))
    if not any(p == ["*"] or p == ["*.*"] for _l, p in out):
        out.append(("All Files (*.*)", ["*"]))
    return out
