# INU Tools (Max) — своё окно выбора файлов (вместо диалога Max).
#
# Раскладка как у диалога Max: History, Look in + кнопки (назад / вверх /
# новая папка / вид), места слева (Рабочий стол, Документы, диски), список
# файлов, File name, Files of type. Справа — панель опций INU (как боковая
# панель файлового браузера Blender в диалогах импорта/экспорта). Палитра —
# как у роллаутов Kam's (тёмная, без белого списка Windows).
#
# Режимы: 'open' — один файл, 'open_multi' — несколько, 'folder' — папка,
# 'save' — путь нового файла, 'export' — папка + имя экспорта (как Export
# All в INU: клик по файлу задаёт имя).

import json
import os
import tempfile

from PySide6 import QtWidgets, QtCore, QtGui

from .style import qss, BTN_H, SB_W, SB_GAP
from .widgets import scrolled, content_min_width

# История папок и последняя папка по назначению — в файле, чтобы
# переживать перезапуск окон (настройки панели сбрасываются при каждом).
_STATE_FILE = os.path.join(
    os.environ.get('LOCALAPPDATA') or tempfile.gettempdir(),
    'INU_Tools_Max', 'file_dialog.json')
_HISTORY_MAX = 15
_PLACES_W = 92
_THIS_PC = ''              # корень «Этот компьютер» (список дисков)


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


class _Places(QtWidgets.QListWidget):
    """Места слева, как у диалога Max: крупная иконка, подпись под ней."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QtWidgets.QListView.IconMode)
        self.setFlow(QtWidgets.QListView.TopToBottom)
        self.setMovement(QtWidgets.QListView.Static)
        self.setWrapping(False)
        self.setIconSize(QtCore.QSize(32, 32))
        self.setGridSize(QtCore.QSize(_PLACES_W - 6, 64))
        self.setWordWrap(True)
        self.setFixedWidth(_PLACES_W)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        prov = QtWidgets.QFileIconProvider()
        std = QtCore.QStandardPaths
        for label, loc in (("Desktop", std.DesktopLocation),
                           ("Documents", std.DocumentsLocation)):
            p = std.writableLocation(loc)
            if p:
                self._add(label, _clean(p), prov.icon(QtCore.QFileInfo(p)))
        self._add("This PC", _THIS_PC,
                  prov.icon(QtWidgets.QFileIconProvider.Computer))
        for d in QtCore.QDir.drives():
            root = _clean(d.absoluteFilePath())
            self._add(_drive_label(root), root, prov.icon(d))

    def _add(self, label, path, icon):
        it = QtWidgets.QListWidgetItem(icon, label)
        it.setData(QtCore.Qt.UserRole, path)
        it.setTextAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        it.setToolTip(path or "This PC")
        self.addItem(it)


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
        self._cwd = None
        self._files = []
        self._target = None
        self._folder = None
        self._save_path = None
        self._prov = QtWidgets.QFileIconProvider()

        self._model = QtWidgets.QFileSystemModel(self)
        self._model.setReadOnly(False)          # «новая папка» и переименование
        filt = (QtCore.QDir.AllDirs | QtCore.QDir.NoDotAndDotDot
                | QtCore.QDir.Drives)
        if mode != 'folder':
            filt |= QtCore.QDir.Files
        self._model.setFilter(filt)
        self._model.setNameFilterDisables(False)   # не подходящие — скрыть

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        outer.addLayout(self._build_top())

        mid = QtWidgets.QHBoxLayout()
        mid.setSpacing(4)
        outer.addLayout(mid, 1)          # сразу в окно: виджеты получают QSS
        self._places = _Places()
        self._places.itemClicked.connect(
            lambda it: self._go(it.data(QtCore.Qt.UserRole)))
        mid.addWidget(self._places)
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

        self.resize(700 + self._opts_w, 540)
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
        g = QtWidgets.QGridLayout()
        g.setHorizontalSpacing(6)
        g.setVerticalSpacing(6)
        for r, text in enumerate(("History:", "Look in:")):
            lab = QtWidgets.QLabel(text)
            lab.setFixedWidth(_PLACES_W - 8)
            lab.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            g.addWidget(lab, r, 0)
        self._history = QtWidgets.QComboBox()
        self._history.setFixedHeight(BTN_H)
        self._history.activated.connect(
            lambda i: self._go(self._history.itemData(i)))
        g.addWidget(self._history, 0, 1, 1, 2)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(2)
        self._lookin = QtWidgets.QComboBox()
        self._lookin.setFixedHeight(BTN_H)
        self._lookin.setMinimumWidth(240)
        self._lookin.activated.connect(
            lambda i: self._go(self._lookin.itemData(i)))
        row.addWidget(self._lookin)
        sp = QtWidgets.QStyle
        self._btn_back = self._tool(sp.SP_ArrowBack, "Back (Alt+Left)", self._go_back)
        self._btn_up = self._tool(sp.SP_FileDialogToParent, "Up one level (Backspace)",
                                  self._go_up)
        self._btn_new = self._tool(sp.SP_FileDialogNewFolder, "New folder",
                                   self._new_folder)
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
        for b in (self._btn_back, self._btn_up, self._btn_new, self._btn_view):
            row.addWidget(b)
        row.addStretch(1)
        g.addLayout(row, 1, 1, 1, 2)
        g.setColumnStretch(1, 1)
        return g

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
        for col, w in ((0, 240), (3, 130), (2, 90)):
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
        self._cwd = path
        self._model.setRootPath(path)
        root = self._model.index(path) if path else QtCore.QModelIndex()
        for v in (self._tree, self._list):
            v.setRootIndex(root)
            v.clearSelection()
        self._btn_back.setEnabled(bool(self._back))
        self._btn_up.setEnabled(bool(path))
        self._btn_new.setEnabled(bool(path))
        self._fill_lookin()
        self._fill_history()

    def _go_back(self):
        if self._back:
            self._go(self._back.pop(), push=False)

    def _go_up(self):
        if self._cwd:
            self._go(_parent(self._cwd))

    def _fill_lookin(self):
        """Look in: «Этот компьютер», диски, а под диском текущей папки —
        цепочка её родителей (как у диалога Max)."""
        cb = self._lookin
        cb.blockSignals(True)
        cb.clear()
        chain = []
        p = self._cwd
        while p:
            chain.insert(0, p)
            p = _parent(p)
        cb.addItem(self._prov.icon(QtWidgets.QFileIconProvider.Computer),
                   "This PC", _THIS_PC)
        cur = 0
        for d in QtCore.QDir.drives():
            root = _clean(d.absoluteFilePath())
            cb.addItem(self._prov.icon(d), "  " + _drive_label(root), root)
            if chain and chain[0].lower() == root.lower():
                if len(chain) == 1:
                    cur = cb.count() - 1
                for depth, sub in enumerate(chain[1:], start=2):
                    cb.addItem(self._prov.icon(QtCore.QFileInfo(sub)),
                               "  " * depth + os.path.basename(sub), sub)
                    cur = cb.count() - 1
        cb.setCurrentIndex(cur)
        cb.blockSignals(False)

    def _fill_history(self):
        cb = self._history
        cb.blockSignals(True)
        cb.clear()
        items = [self._cwd] if self._cwd else []
        items += [h for h in self._state.get('history', [])
                  if h and h != self._cwd and os.path.isdir(h)]
        for p in items:
            cb.addItem(QtCore.QDir.toNativeSeparators(p), p)
        cb.setCurrentIndex(0 if items else -1)
        cb.blockSignals(False)

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
        rows = v.selectionModel().selectedRows(0) if v is self._tree else \
            v.selectionModel().selectedIndexes()
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
            if k in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                idx = obj.currentIndex()
                if idx.isValid() and self._model.isDir(idx):
                    self._go(self._model.filePath(idx))
                else:
                    self._accept()
                return True
        return super().eventFilter(obj, ev)

    # — результат —
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
