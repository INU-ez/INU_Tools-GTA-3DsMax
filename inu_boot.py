# INU Tools (Max) — бутстрап для MaxScript-лаунчера.
#
# MaxScript-роллаут (inu_launcher.ms) в командной панели вызывает отсюда
# launch(mode) — добавляет корень проекта в sys.path, сбрасывает наши модули
# (dev hot-reload: свежий код без рестарта Max) и открывает Qt-окно.

import os
import sys


def _root():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.path.abspath(os.getcwd())


def launch(mode='launcher'):
    """Открыть окно инструмента INU по режиму (dff|map|col|util|launcher)."""
    root = _root()
    if root not in sys.path:
        sys.path.insert(0, root)
    # hot-reload только нашего пакета (ядро inu_gta_core не трогаем — тяжёлое).
    for name in [m for m in list(sys.modules) if m.split('.')[0] == 'inu_max']:
        del sys.modules[name]
    from inu_max.ui import panel
    return panel.open_window(mode)
