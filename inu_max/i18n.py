"""English/Russian UI localization; identifiers and user data stay unchanged."""
import json
import re
from functools import lru_cache
from pathlib import Path
from . import settings

_CATALOG = None
_FORWARD = None
_PATTERNS = None
_PATTERNS_EN = None
_PREFIXES = None
_PREFIXES_EN = None
_NORMAL = None
_SERVICE = None


def language():
    return settings.get('ui_language', 'EN')


def _patterns(catalog):
    patterns=[]
    for source,target in catalog.items():
        pieces=re.split(r'(%(?:\([^)]*\))?[-+0-9.#]*[sdfgr]|\{\w*\})',source.replace('%%','%'))
        if len(pieces)<3:
            continue
        pattern=''
        for i,piece in enumerate(pieces):
            if not i%2:
                pattern += re.escape(piece)
            elif piece.endswith('d'):
                pattern += r'([+-]?\d+)'
            elif piece.endswith(('f','g')):
                pattern += r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)'
            else:
                pattern += '(.*?)'
        if not re.search(r'[A-Za-zА-Яа-я]{3}', ''.join(pieces[::2])):
            continue
        patterns.append((re.compile('^'+pattern+'$',re.S),target.replace('%%','%')))
    return sorted(patterns,key=lambda item:len(item[0].pattern),reverse=True)


def _prefixes(catalog):
    # Concatenated reports append identifiers to a phrase ending in whitespace.
    return sorted(((s,t+(' ' if s.endswith(' ') and not t.endswith(' ') else ''))
                   for s,t in catalog.items() if len(s)>10 and s.endswith((' ', '\n'))
                   and re.search(r'[A-Za-zА-Яа-я]{3}',s)),key=lambda item:len(item[0]),reverse=True)


def _load():
    global _CATALOG, _FORWARD, _PATTERNS, _PATTERNS_EN, _PREFIXES, _PREFIXES_EN, _NORMAL
    if _CATALOG is not None:
        return
    folder=Path(__file__).parent/'locale'
    _CATALOG={}
    for name in ('ru_blender.json','ru_max.json'):
        path=folder/name
        if path.exists():
            _CATALOG.update(json.loads(path.read_text(encoding='utf-8')))
    _FORWARD={v:k for k,v in _CATALOG.items()}
    _NORMAL={re.sub(r'[^\w]+',' ',k.casefold()).strip():v for k,v in _CATALOG.items()}
    _PATTERNS=_patterns(_CATALOG)
    _PATTERNS_EN=_patterns(_FORWARD)
    _PREFIXES=_prefixes(_CATALOG)
    _PREFIXES_EN=_prefixes(_FORWARD)


def tr(text):
    if not isinstance(text,str) or not text:
        return text
    _load()
    return _translate(text, language())


@lru_cache(maxsize=8192)
def _translate(text, code):
    if code!='RU':
        if not re.search('[А-Яа-я]',text):return text
        catalog,patterns,prefixes=_FORWARD,_PATTERNS_EN,_PREFIXES_EN
    else:
        catalog,patterns,prefixes=_CATALOG,_PATTERNS,_PREFIXES
    direct=catalog.get(text)
    if direct is not None:
        return direct
    normal=_NORMAL.get(re.sub(r'[^\w]+',' ',text.casefold()).strip()) if code=='RU' else None
    if normal is not None:
        return normal
    for pattern,target in patterns:
        match=pattern.fullmatch(text)
        if match:
            values=iter(match.groups())
            return re.sub(r'%(?:\([^)]*\))?[-+0-9.#]*[sdfgr]|\{\w*\}',lambda m:next(values),target)
    for source,target in prefixes:
        if text.startswith(source):return target+text[len(source):]
    # Multi-line reports are assembled at runtime. Translate each existing phrase.
    lines=text.splitlines(keepends=True)
    if len(lines)>1:
        return ''.join(tr(line.rstrip('\r\n'))+line[len(line.rstrip('\r\n')):] for line in lines)
    return text


def set_language(code):
    if code not in ('EN','RU'):
        raise ValueError('Unknown INU language: '+str(code))
    settings.set('ui_language',code)
    install()
    if _SERVICE is not None:
        _SERVICE.refresh()


def install():
    """Translate only INU-owned widgets, including dynamically refreshed labels."""
    global _SERVICE
    from .qt import QtCore,QtWidgets,QtGui
    app=QtWidgets.QApplication.instance()
    if app is None:
        return
    existing=getattr(app,'_inu_i18n_service',None)
    app._inu_i18n_tr=tr
    app._inu_i18n_language=language
    if existing is not None:
        _SERVICE=existing
        return

    class Service(QtCore.QObject):
        def __init__(self):
            super().__init__(app)
            self.busy=False
            self.code=None
            self.timer=QtCore.QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(200)
            app.installEventFilter(self)

        def owned(self,w):
            current=w
            while current is not None:
                if str(current.objectName()).startswith('inu'):
                    return True
                current=current.parent()
            return str(w.windowTitle()).startswith(('INU','ИНУ'))

        def text(self,obj,getter,setter,key):
            try:
                value=getter()
                if not isinstance(value,str):return
                cache=getattr(obj,'_inu_text_sources',{})
                source,previous=cache.get(key,(value,None))
                if value!=previous:source=value
                translated=app._inu_i18n_tr(source)
                cache[key]=(source,translated)
                obj._inu_text_sources=cache
                if translated!=value:setter(translated)
            except (RuntimeError,AttributeError):
                pass

        def widget(self,w):
            self.text(w,w.windowTitle,w.setWindowTitle,'title')
            self.text(w,w.toolTip,w.setToolTip,'tip')
            if isinstance(w,(QtWidgets.QLabel,QtWidgets.QAbstractButton)) and not w.property('inu_i18n_data'):
                self.text(w,getattr(w,'full_text',w.text),w.setText,'text')
            if isinstance(w,QtWidgets.QLineEdit):
                self.text(w,w.placeholderText,w.setPlaceholderText,'placeholder')
            if isinstance(w,(QtWidgets.QSpinBox,QtWidgets.QDoubleSpinBox)):
                self.text(w,w.prefix,w.setPrefix,'prefix')
                self.text(w,w.suffix,w.setSuffix,'suffix')
            if isinstance(w,QtWidgets.QGroupBox):
                self.text(w,w.title,w.setTitle,'group')
            if type(w).__name__=='RolloutHeader':
                def header(value):
                    w.title=value
                    w.updateGeometry()
                    w.update()
                self.text(w,lambda:w.title,header,'rollout')
            if type(w).__name__=='_ExpanderHeader':
                def expander(value):
                    w.text=value
                    w.update()
                self.text(w,lambda:w.text,expander,'expander')
            if isinstance(w,QtWidgets.QComboBox) and not w.property('inu_i18n_data'):
                for i in range(w.count()):
                    data=w.itemData(i)
                    # Preset names and region names are identifiers, not captions.
                    if isinstance(data,str) and (data==w.itemText(i) or '/' in data or '\\' in data):
                        continue
                    self.text(w,lambda i=i:w.itemText(i),lambda v,i=i:w.setItemText(i,v),('item',i))
                    tip=w.itemData(i,QtCore.Qt.ToolTipRole)
                    if isinstance(tip,str):
                        self.text(w,lambda i=i:w.itemData(i,QtCore.Qt.ToolTipRole),lambda v,i=i:w.setItemData(i,v,QtCore.Qt.ToolTipRole),('itemtip',i))
            if isinstance(w,QtWidgets.QTabWidget):
                for i in range(w.count()):
                    self.text(w,lambda i=i:w.tabText(i),lambda v,i=i:w.setTabText(i,v),('tab',i))
            if isinstance(w,QtWidgets.QMessageBox):
                self.text(w,w.text,w.setText,'message')
                self.text(w,w.informativeText,w.setInformativeText,'messageinfo')
            if isinstance(w,QtWidgets.QTreeWidget):
                def item(it):
                    source=it.data(0,QtCore.Qt.UserRole+1)
                    if isinstance(source,str):it.setText(0,app._inu_i18n_tr(source))
                    for j in range(it.childCount()):item(it.child(j))
                for j in range(w.topLevelItemCount()):item(w.topLevelItem(j))
            for action in w.actions():
                self.text(action,action.text,action.setText,'text')
                self.text(action,action.toolTip,action.setToolTip,'tip')

        def refresh(self):
            if self.busy:return
            self.busy=True
            try:
                code=app._inu_i18n_language()
                changed=code!=self.code
                self.code=code
                from .i18n_native import refresh_editor
                refresh_editor(force=changed)
                for window in app.topLevelWidgets():
                    if self.owned(window):
                        self.widget(window)
                        for child in window.findChildren(QtWidgets.QWidget):
                            self.widget(child)
                            if changed:QtWidgets.QWidget.update(child)
                        if changed and hasattr(window,'_refit_translation'):window._refit_translation()
            finally:self.busy=False

        def eventFilter(self,obj,event):
            if event.type() in (QtCore.QEvent.Show,QtCore.QEvent.Polish):
                self.refresh()
            return False

    _SERVICE=Service()
    app._inu_i18n_service=_SERVICE
