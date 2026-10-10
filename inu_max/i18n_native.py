"""Caption overlay for bundled Kam rollouts; material parameters stay original."""
import json
import re
import time
from functools import lru_cache
from pathlib import Path

_FILES = {'gta_mtl': 'GTA_Material.ms', 'gta_colsurface': 'GTA_COLplugin.ms',
          'gta_colshadow': 'GTA_COLplugin.ms', 'inu_gta_mtl': 'Legacy_GTA_Material.ms',
          'inu_gta_colsurface': 'Legacy_GTA_COLplugin.ms',
          'inu_gta_colshadow': 'Legacy_GTA_COLplugin.ms'}
_ROLLOUTS = {'inu_gta_mtl': 'mainUI', 'inu_gta_colsurface': 'colUI',
             'inu_gta_colshadow': 'colUI'}
_ACTIVE = None
_LAST_POLL = 0


@lru_cache(maxsize=6)
def definition(class_name):
    source = (Path(__file__).parent/_FILES[class_name]).read_text(encoding='utf-8-sig', errors='replace')
    block = next(s for s in re.split(r'(?=plugin\s+material\s+)', source, flags=re.I)
                 if re.match(r'plugin\s+material\s+'+class_name+r'\b', s, re.I))
    bindings = {control: field for field, control in re.findall(
        r'^\s*(\w+)\s+type:[^\n]*?\bui:(\w+)', block, re.M|re.I)}
    controls = []
    for match in re.finditer(r'^\s*(label|button|checkbox|spinner|dropdownlist|groupBox|colorpicker|mapbutton)\s+(\w+)\s+"((?:[^"\\]|\\.)*)"([^\n]*)', block, re.M|re.I):
        kind, name, caption, tail = match.groups()
        caption = json.loads('"'+caption+'"')
        if 'By ' in caption or 'Thanks' in caption or 'GTAF' in caption:
            continue
        tip = re.search(r'tooltip:"((?:[^"\\]|\\.)*)"', tail)
        items = re.search(r'items:#\(([^)]*)\)', tail)
        choices = re.findall(r'"([^"\n]*)"', items.group(1)) if items else None
        controls.append((name, caption, json.loads('"'+tip.group(1)+'"') if tip else None,
                         choices, kind.lower(), bindings.get(name)))
    title = re.search(r'rollout\s+'+_ROLLOUTS.get(class_name, 'params')+r'\s+"([^"]*)"', block, re.I).group(1)
    groups = re.findall(r'\bgroup\s+"([^"]*)"', block)
    return title, controls, groups


def localize_material(mat):
    from pymxs import runtime as rt
    from .i18n import tr, _translate, language
    class_name = str(rt.classOf(mat)).lower()
    if class_name not in _FILES:
        return False
    title, controls, groups = definition(class_name)
    rollout = getattr(mat, _ROLLOUTS.get(class_name, 'params'))
    rollout.title = tr(title)
    named_controls = []
    for name, caption, tip, choices, kind, field in controls:
        control = getattr(rollout, name)
        named_controls.append(control)
        if kind == 'mapbutton':
            # A populated button displays a map name, which is user data.
            if field and getattr(mat, field) is None:
                control.caption = tr('None')
        elif caption:
            control.caption = tr(caption)
        if field == 'dif' and kind == 'spinner':
            control.caption = 'Дифф.' if language() == 'RU' else caption
        if class_name == 'gta_mtl' and language() == 'RU' and name in ('infodkN', 'infodkN2'):
            control.caption = 'Нормали' if name == 'infodkN' else 'Отражение'
        if class_name == 'gta_mtl' and name in ('lbl_t1', 'lbl_t2'):
            control.caption = ''
        if tip:control.tooltip = tr(tip)
        if choices:
            selected = int(getattr(mat, field)) if field else int(control.selection)
            control.items = rt.Array(*(tr(choice) for choice in choices))
            control.selection = selected
    for control in rollout.controls:
        if any(control == named for named in named_controls):
            continue
        # Anonymous group boxes have no script variable. Match only group titles.
        for original in groups:
            if str(control.caption) in (original, _translate(original, 'RU')):
                control.caption = tr(original)
                break
    return True


def refresh_editor(force=False):
    """Inspect only the edited material, never scan the scene's material library."""
    global _ACTIVE, _LAST_POLL
    now = time.monotonic()
    if not force and now-_LAST_POLL < 1:
        return
    _LAST_POLL = now
    try:
        from pymxs import runtime as rt
        from .i18n import language
        if not rt.MatEditor.isOpen():
            _ACTIVE = None
            return
        mat = rt.medit.GetCurMtl() if str(rt.MatEditor.mode).lower().lstrip('#')=='basic' else rt.sme.GetMtlInParamEditor()
        if mat is None or str(rt.classOf(mat)).lower() not in _FILES:
            _ACTIVE = None
            return
        class_name = str(rt.classOf(mat)).lower()
        rollout = getattr(mat, _ROLLOUTS.get(class_name, 'params'))
        empty_maps = tuple(getattr(mat, field) is None for _, _, _, _, kind, field
                           in definition(class_name)[1] if kind == 'mapbutton' and field)
        key = int(rt.getHandleByAnim(mat)), str(rollout.hwnd), language(), empty_maps
        if force or key!=_ACTIVE:
            localize_material(mat)
            _ACTIVE = key
    except (ImportError, AttributeError, RuntimeError):
        # Startup and closed parameter rollouts may not expose GUI controls yet.
        _ACTIVE = None
