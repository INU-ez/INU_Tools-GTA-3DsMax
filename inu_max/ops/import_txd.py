# INU Tools (Max) — импорт TXD: извлечь текстуры в PNG рядом с файлом.

import os

import pymxs


def import_txd(path):
    """Извлечь текстуры .txd в PNG в <имя>_textures/ рядом с файлом.
    Возвращает ({имя_текстуры.lower(): путь_png}, папка)."""
    from ..adapter.texture import extract_txd_file
    out = os.path.join(
        os.path.dirname(path),
        os.path.splitext(os.path.basename(path))[0] + "_textures")
    return extract_txd_file(path, out), out


def import_txd_interactive():
    rt = pymxs.runtime
    path = rt.getOpenFileName(
        caption="INU: Импорт TXD",
        types="GTA TXD (*.txd)|*.txd|All Files (*.*)|*.*|")
    if not path:
        return 0, "Отменено"
    m, out = import_txd(path)
    msg = "Извлечено текстур: %d\n%s" % (len(m), out)
    try:
        rt.messageBox(msg, title="INU Tools — Импорт TXD")
    except Exception:                                  # noqa: BLE001
        pass
    return len(m), msg
