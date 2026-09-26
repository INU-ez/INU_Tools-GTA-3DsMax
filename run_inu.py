# INU Tools (3ds Max) — точка входа для разработки.
#
# Запуск в 3ds Max: Scripting → Run Python Script… → выбрать этот файл.
# Откроет панель INU Tools. При повторном запуске модули перезагружаются
# (dev-режим), чтобы правки подхватывались без перезапуска Max.

import os
import sys


def _project_root():
    """Корень проекта (папка с этим файлом) — чтобы импортировались и
    inu_gta_core, и inu_max. __file__ доступен при Run Script; на всякий
    случай есть фолбэк на текущую директорию."""
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.path.abspath(os.getcwd())


def main():
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    # Dev-hot-reload: сбросить наши модули, чтобы Run Script подхватывал
    # свежий код без рестарта Max.
    for name in [m for m in list(sys.modules)
                 if m.split('.')[0] in ('inu_max', 'inu_gta_core')]:
        del sys.modules[name]

    from inu_max.ui import panel
    panel.show_panel()


if __name__ == '__main__':
    main()
else:
    # Run Script может исполнять модуль не как __main__ — всё равно стартуем.
    main()
