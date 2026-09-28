# INU Tools (Max) — бутстрап для MaxScript-лаунчера.
#
# MaxScript-роллаут (inu_launcher.ms) в командной панели вызывает отсюда
# launch(mode) — добавляет корень проекта в sys.path, сбрасывает наши модули
# (dev hot-reload: свежий код без рестарта Max) и открывает Qt-окно. Отсюда же —
# установка INU в Max (кнопки Setup лаунчера) и вход C++ импортёра .dff.

import os
import sys


def _root():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.path.abspath(os.getcwd())


def _ensure_paths():
    """Корень INU и numpy из пакета INU (если ставился туда) — в sys.path."""
    root = _root()
    if root not in sys.path:
        sys.path.insert(0, root)
    libs = os.path.join(os.environ.get('APPDATA') or '', 'Autodesk', 'ApplicationPlugins',
                        'INU_Tools.bundle', 'Contents', 'python_libs')
    if os.path.isdir(libs) and libs not in sys.path:
        sys.path.append(libs)


def _reload_inu_max():
    # hot-reload только нашего пакета (ядро inu_gta_core не трогаем — тяжёлое).
    for name in [m for m in list(sys.modules) if m.split('.')[0] == 'inu_max']:
        del sys.modules[name]


# состояние импортёра между вызовами (модули inu_max перезагружаются)
_DROP_STATE = {}


def import_dropped(path, quiet=False, count=1, key='', from_drop=False):
    """Точка входа C++ импортёра INU_Import.dli (перетаскивание .dff во
    вьюпорт, File → Import, importFile). count / key — сколько .dff сброшено
    вместе и «номер» сброса (первый файл пакета). True — импортировано."""
    _ensure_paths()
    try:
        from inu_max import drop
        return bool(drop.import_file(path, bool(quiet), _DROP_STATE, int(count or 1),
                                     str(key or ''), bool(from_drop)))
    except Exception:                                  # noqa: BLE001
        import traceback
        traceback.print_exc()
        return False


def launch(mode='launcher'):
    """Открыть окно инструмента INU по режиму (dff|map|col|util|launcher)."""
    _ensure_paths()
    _reload_inu_max()
    try:
        from inu_max import setup
        setup.cleanup_orphan()          # остатки удалённого пакета
    except Exception:                                  # noqa: BLE001
        pass
    from inu_max.ui import panel
    return panel.open_window(mode)


# ── установка INU в Max (группа Setup лаунчера) ──────────────────────

def version():
    _ensure_paths()
    from inu_max.version import VERSION
    return VERSION


def setup_status():
    """Строка состояния для лаунчера."""
    _ensure_paths()
    from inu_max import setup
    return setup.status()['text']


def setup_button():
    """Подпись кнопки установки (Install / Update / Reinstall INU)."""
    _ensure_paths()
    from inu_max import setup
    return setup.status()['button']


def setup_install():
    _ensure_paths()
    _reload_inu_max()
    from inu_max.ui import setup_ui
    setup_ui.install_interactive()
    return setup_status()


def setup_remove():
    _ensure_paths()
    _reload_inu_max()
    from inu_max.ui import setup_ui
    setup_ui.remove_interactive()
    return setup_status()
