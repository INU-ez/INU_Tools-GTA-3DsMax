# INU Tools (Max) — установка INU в 3ds Max одной кнопкой (лаунчер → Setup).
#
# Собирает пакет Autodesk %APPDATA%\Autodesk\ApplicationPlugins\INU_Tools.bundle
# (так же устроены пакеты самой Autodesk — USD, Flow Retopology), Max при
# запуске загружает его сам, права администратора не нужны:
#   • plugins parts          — C++ импортёр .dff (перетаскивание во вьюпорт);
#   • post-start-up scripts  — INU_Startup.ms: пути Python, лаунчер в Utilities;
#   • macroscripts parts     — макросы окон INU;
#   • menu parts             — меню «INU Tools» в главном меню Max (.mnx);
#   • код INU                — КОПИЯ в пакете (папку загрузки можно удалить) или
#                              ССЫЛКА на папку разработки (есть .git: правки
#                              видны сразу, без переустановки);
#   • numpy                  — в пакет через pip Max, только если его нет.
# После установки нужен перезапуск Max.

import json
import os
import shutil
import subprocess
import sys
import time
import uuid

from .version import VERSION

BUNDLE_NAME = 'INU_Tools.bundle'
PLUGIN_NAME = 'INU_Import.dli'
# что из папки INU нужно в Max (копия): код и лаунчер
CODE_ITEMS = ('inu_boot.py', 'inu_launcher.ms', 'run_inu.py', 'inu_max', 'inu_gta_core')
MAIN_MENU_BAR = 'b4779ebb-a6f0-4815-9777-57c01c0b584c'   # главное меню Max 2025+
MACRO_TABLE = '647394'                                      # таблица действий макросов
# окна INU: (макрос, подпись в меню, режим inu_boot.launch)
WINDOWS = (
    ('INU_Launcher', 'INU Tools', 'launcher'),
    ('INU_DFF', 'DFF IO (DFF / TXD)', 'dff'),
    ('INU_Vehicles', 'Vehicles', 'veh'),
    ('INU_Material', 'GTA Material', 'mat'),
    ('INU_Lighting', 'Lighting', 'light'),
    ('INU_MapIO', 'Map IO (IDE / IPL / IMG)', 'map'),
    ('INU_2DFX', '2DFX', 'fx'),
    ('INU_Paths', 'Paths', 'paths'),
    ('INU_Zones', 'Zones', 'zones'),
    ('INU_Water', 'Water', 'water'),
    ('INU_Radar', 'X Radar', 'radar'),
    ('INU_IFP', 'IFP IO (Animations)', 'ifp'),
    ('INU_Check', 'Check', 'util'),
)
_NS = uuid.UUID('6f1d2c3b-4a5e-4f70-8a91-b2c3d4e5f607')   # постоянные GUID меню


def _guid(name):
    return str(uuid.uuid5(_NS, name)).upper()


# ── где что лежит ────────────────────────────────────────────────────

def bundle_dir():
    return os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'),
                        'Autodesk', 'ApplicationPlugins', BUNDLE_NAME)


def code_root():
    """Папка INU, из которой запущен этот код (там inu_boot.py)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def libs_dir():
    """Папка пакета для numpy (добавляется в sys.path при запуске Max)."""
    return os.path.join(bundle_dir(), 'Contents', 'python_libs')


def _rt():
    try:
        import pymxs
        return pymxs.runtime
    except ImportError:
        return None


def max_year():
    """Год версии Max (2026…); вне Max — 2026."""
    rt = _rt()
    if rt is None:
        return 2026
    try:
        v = list(rt.maxVersion())
        if len(v) > 7 and int(v[7]) > 2000:
            return int(v[7])
        return 2000 + int(v[0]) // 1000 - 2          # 28000 → 2026
    except Exception:                                  # noqa: BLE001
        return 2026


def max_python():
    """python.exe Max (для pip) или None."""
    rt = _rt()
    if rt is None:
        return None
    try:
        p = os.path.join(str(rt.getDir(rt.Name('maxroot'))), 'Python', 'python.exe')
        return p if os.path.isfile(p) else None
    except Exception:                                  # noqa: BLE001
        return None


def is_dev(root):
    return os.path.isdir(os.path.join(root, '.git'))


def plugin_source(root, year):
    for rel in (('max_plugin', 'bin', str(year)), ('plugins', str(year))):
        p = os.path.join(root, *rel, PLUGIN_NAME)
        if os.path.isfile(p):
            return p
    return None


def numpy_ok():
    try:
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


# ── состояние ────────────────────────────────────────────────────────

def _manifest():
    try:
        with open(os.path.join(bundle_dir(), 'Contents', 'install.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def status():
    """{'state': NOT_INSTALLED | INSTALLED | UPDATE, 'text': для лаунчера,
    'button': подпись кнопки}."""
    man = _manifest()
    installed = man is not None and os.path.isfile(
        os.path.join(bundle_dir(), 'PackageContents.xml'))
    if not installed:
        return dict(state='NOT_INSTALLED', text='Not installed', button='Install INU')
    root = code_root()
    stale = man.get('version') != VERSION or man.get('year') != max_year()
    if man.get('mode') == 'link':
        stale = stale or os.path.normcase(man.get('root', '')) != os.path.normcase(root)
    if not man.get('plugin') and plugin_source(root, max_year()):
        stale = True
    if stale:
        return dict(state='UPDATE', button='Update INU',
                    text='Update: v%s → v%s' % (man.get('version', '?'), VERSION))
    dev = ' (dev link)' if man.get('mode') == 'link' else ''
    return dict(state='INSTALLED', text='Installed v%s%s' % (VERSION, dev),
                button='Reinstall INU')


# ── установка ────────────────────────────────────────────────────────

def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _copy_plugin(src, dst_dir):
    """.dli загруженного Max перезаписать нельзя, но переименовать можно:
    открытый Max работает со старой копией, новый запуск берёт новую."""
    os.makedirs(dst_dir, exist_ok=True)
    target = os.path.join(dst_dir, PLUGIN_NAME)
    for f in os.listdir(dst_dir):
        if f.startswith(PLUGIN_NAME + '.old'):
            try:
                os.remove(os.path.join(dst_dir, f))
            except OSError:
                pass
    try:
        shutil.copy2(src, target)
    except PermissionError:
        os.rename(target, target + '.old%d' % int(time.time()))
        shutil.copy2(src, target)


def _copy_code(src_root, dst):
    """Копия кода INU в пакет (без кэшей и файлов разработки)."""
    new = dst + '.new'
    shutil.rmtree(new, ignore_errors=True)
    os.makedirs(new)
    skip = shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo')
    for item in CODE_ITEMS:
        s = os.path.join(src_root, item)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(new, item), ignore=skip)
        elif os.path.isfile(s):
            shutil.copy2(s, os.path.join(new, item))
    shutil.rmtree(dst, ignore_errors=True)
    if os.path.exists(dst):                # что-то занято — оставляем, кладём поверх
        shutil.copytree(new, dst, dirs_exist_ok=True)
        shutil.rmtree(new, ignore_errors=True)
    else:
        os.rename(new, dst)


def _startup_ms():
    return r'''-- INU Tools: регистрация при запуске 3ds Max (пакет INU_Tools.bundle).
-- Файл пишет установщик INU (inu_max/setup.py) — вручную не править.
(
    local contents = pathConfig.removePathLeaf (pathConfig.removePathLeaf (getThisScriptFilename()))
    local rootFile = pathConfig.appendPath contents "inu_root.txt"
    local root = undefined
    if doesFileExist rootFile do (
        local f = openFile rootFile
        if f != undefined do (root = trimRight (trimLeft (readLine f)); close f)
    )
    if root != undefined and doesFileExist (pathConfig.appendPath root "inu_boot.py") then (
        local libs = pathConfig.appendPath contents "python_libs"
        python.Execute ("import sys\nfor p in (r'" + libs + "', r'" + root + "'):\n    if p not in sys.path: sys.path.insert(0, p)")
        global INU_LAUNCHER_NO_OPEN = true
        fileIn (pathConfig.appendPath root "inu_launcher.ms")
        INU_LAUNCHER_NO_OPEN = false
    ) else (
        format "[INU Tools] INU folder not found (%): reinstall INU from its launcher\n" root
    )
)
'''


def _macros_mcr():
    out = ['-- INU Tools: окна INU для меню «INU Tools» и панелей инструментов.',
           '-- Файл пишет установщик INU (inu_max/setup.py) — вручную не править.', '']
    for macro, label, mode in WINDOWS:
        out.append('''macroScript %s
    category:"INU Tools" internalCategory:"INU_Tools"
    buttonText:"%s" tooltip:"INU Tools: %s"
(
    on execute do (
        if INU_launch != undefined then INU_launch "%s"
        else messageBox "INU Tools is not loaded: restart 3ds Max." title:"INU Tools"
    )
)
''' % (macro, label, label, mode))
    return "\n".join(out)


def _menu_mnx():
    menu = _guid('inu.menu')
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<MaxMenuTransformations>',
             '    <CreateMenu ParentId="%s" MenuId="%s" Title="INU Tools"/>'
             % (MAIN_MENU_BAR, menu)]
    for macro, _label, _mode in WINDOWS:
        lines.append('    <CreateMenuAction MenuId="%s" Id="%s" ActionId="%s-%s`INU_Tools"/>'
                     % (menu, _guid('inu.menu.' + macro), MACRO_TABLE, macro))
    lines.append('</MaxMenuTransformations>')
    return "\n".join(lines) + "\n"


def _package_xml(year, with_plugin):
    def comp(kind, module):
        return ('  <Components Description="%s">\n'
                '    <RuntimeRequirements OS="Win64" Platform="3ds Max" SeriesMin="%d" SeriesMax="%d" />\n'
                '    <ComponentEntry AppName="INU Tools" Version="%s" ModuleName="%s" />\n'
                '  </Components>\n' % (kind, year, year, VERSION, module))
    parts = ''
    if with_plugin:
        parts += comp('plugins parts', './Contents/%d/%s' % (year, PLUGIN_NAME))
    parts += comp('post-start-up scripts parts', './Contents/scripts/INU_Startup.ms')
    parts += comp('macroscripts parts', './Contents/scripts/INU_Macros.mcr')
    parts += comp('menu parts', './Contents/cui/INU_Menu.mnx')
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<ApplicationPackage SchemaVersion="1.0" AutodeskProduct="3ds Max" ProductType="Application"\n'
            '    Name="INU Tools" Description="GTA SA / VC / III tools for 3ds Max"\n'
            '    AppVersion="%s" Author="INU"\n'
            '    ProductCode="{7C2E5B41-3A9D-4F68-8B1E-2D4C6A9F0E13}"\n'
            '    UpgradeCode="{9E4A1C27-5B3F-4D82-A6C0-8F1D3E5B7A24}">\n'
            '  <RuntimeRequirements OS="Win64" Platform="3ds Max" SeriesMin="%d" SeriesMax="%d" />\n'
            '  <CompanyDetails Name="INU" />\n%s'
            '</ApplicationPackage>\n' % (VERSION, year, year, parts))


def install_numpy(log=print, wait=None):
    """numpy в пакет (pip Max, --target). wait(proc) — ожидание с живым UI
    (иначе обычное). Возвращает (ok, текст)."""
    py = max_python()
    if py is None:
        return False, "Max python.exe not found"
    spec = 'numpy>=2.1,<3' if sys.version_info >= (3, 13) else 'numpy==1.26.4'
    cmd = [py, '-m', 'pip', 'install', '--disable-pip-version-check',
           '--no-warn-script-location', '--upgrade', '--target', libs_dir(), spec]
    log("[INU setup] %s" % " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except OSError as e:
        return False, str(e)
    if wait is not None:
        wait(proc)
    out = proc.communicate()[0].decode('utf-8', 'replace') if proc.stdout else ''
    if proc.returncode != 0:
        return False, out.strip().splitlines()[-1] if out.strip() else "pip failed"
    if libs_dir() not in sys.path:
        sys.path.insert(0, libs_dir())
    return True, spec


def install(mode=None, year=None, with_numpy=True, log=print, wait=None):
    """Установить / обновить INU в Max. mode: 'copy' | 'link' (None — link
    для папки с .git, иначе copy). Возвращает список строк отчёта."""
    root = code_root()
    year = year or max_year()
    mode = mode or ('link' if is_dev(root) else 'copy')
    b = bundle_dir()
    contents = os.path.join(b, 'Contents')
    os.makedirs(contents, exist_ok=True)
    report = []
    if mode == 'copy':
        _copy_code(root, os.path.join(contents, 'INU'))
        inu_root = os.path.join(contents, 'INU')
        report.append("INU code copied into the package")
    else:
        inu_root = root
        report.append("INU code linked: %s" % root)
    plugin = plugin_source(root, year)
    if plugin:
        _copy_plugin(plugin, os.path.join(contents, str(year)))
        _write(os.path.join(contents, str(year), 'inu_root.txt'), inu_root + '\n')
        report.append("Drag & drop plugin for 3ds Max %d" % year)
    else:
        report.append("No drag & drop plugin for 3ds Max %d (drop files on the "
                      "INU window instead)" % year)
    _write(os.path.join(contents, 'inu_root.txt'), inu_root + '\n')
    _write(os.path.join(contents, 'scripts', 'INU_Startup.ms'), _startup_ms())
    _write(os.path.join(contents, 'scripts', 'INU_Macros.mcr'), _macros_mcr())
    _write(os.path.join(contents, 'cui', 'INU_Menu.mnx'), _menu_mnx())
    if with_numpy and not numpy_ok():
        ok, msg = install_numpy(log, wait)
        report.append("numpy installed (%s)" % msg if ok else
                      "numpy NOT installed: %s — DFF/TXD need numpy" % msg)
    _write(os.path.join(contents, 'install.json'), json.dumps(dict(
        version=VERSION, mode=mode, root=root, year=year, plugin=bool(plugin),
        time=time.strftime('%Y-%m-%d %H:%M:%S')), indent=1))
    # PackageContents — последним: без него Max пакет не грузит
    _write(os.path.join(b, 'PackageContents.xml'), _package_xml(year, bool(plugin)))
    for line in report:
        log("[INU setup] " + line)
    return report


def remove():
    """Удалить пакет. Файлы, занятые открытым Max (плагин, numpy), удалятся
    при следующем запуске INU. Возвращает True, если удалено полностью."""
    b = bundle_dir()
    if not os.path.isdir(b):
        return True
    try:
        os.remove(os.path.join(b, 'PackageContents.xml'))   # Max больше не грузит пакет
    except OSError:
        pass
    shutil.rmtree(b, ignore_errors=True)
    return not os.path.exists(b)


def cleanup_orphan():
    """Остатки удалённого пакета (без PackageContents.xml) — удалить: при
    новом запуске Max они уже не заняты."""
    b = bundle_dir()
    if os.path.isdir(b) and not os.path.isfile(os.path.join(b, 'PackageContents.xml')):
        shutil.rmtree(b, ignore_errors=True)
