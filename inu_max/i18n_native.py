"""Caption overlay for bundled Kam rollouts; material parameters stay original."""
import json
import re
import time
from functools import lru_cache
from pathlib import Path

_FILES = {'gta_mtl': 'GTA_Material.ms', 'gta_colsurface': 'GTA_COLplugin.ms',
          'gta_colshadow': 'GTA_COLplugin.ms'}
_ACTIVE = None
_LAST_POLL = 0


@lru_cache(maxsize=3)
def definition(class_name):
    source = (Path(__file__).parent/_FILES[class_name]).read_text(encoding='utf-8-sig', errors='replace')
    block = next(s for s in re.split(r'(?=plugin Material )', source)
                 if s.lower().startswith('plugin material '+class_name+'\n') or
                 s.lower().startswith('plugin material '+class_name+'\r\n'))
    controls = []
    for match in re.finditer(r'^\s*(label|button|checkbox|spinner|dropdownlist|groupBox)\s+(\w+)\s+"((?:[^"\\]|\\.)*)"([^\n]*)', block, re.M|re.I):
        kind, name, caption, tail = match.groups()
        caption = json.loads('"'+caption+'"')
        if 'By ' in caption or 'Thanks' in caption or 'GTAF' in caption:
            continue
        tip = re.search(r'tooltip:"((?:[^"\\]|\\.)*)"', tail)
        items = re.search(r'items:#\(([^)]*)\)', tail)
        choices = re.findall(r'"([^"\n]*)"', items.group(1)) if items else None
        controls.append((name, caption, json.loads('"'+tip.group(1)+'"') if tip else None, choices))
    title = re.search(r'rollout\s+params\s+"([^"]*)"', block).group(1)
    groups = re.findall(r'\bgroup\s+"([^"]*)"', block)
    return title, controls, groups


def localize_material(mat):
    from pymxs import runtime as rt
    from .i18n import tr, _translate
    class_name = str(rt.classOf(mat)).lower()
    if class_name not in _FILES:
        return False
    title, controls, groups = definition(class_name)
    rollout = mat.params
    rollout.title = tr(title)
    for name, caption, tip, choices in controls:
        control = getattr(rollout, name)
        if caption:control.caption = tr(caption)
        if tip:control.tooltip = tr(tip)
        if choices:
            field = {'colhpr':'colhprIdx', 'fxtype_':'matEffect',
                     'srcblend_':'p_srcblend', 'destblend_':'p_destblend'}.get(name)
            selected = int(getattr(mat, field)) if field else int(control.selection)
            control.items = rt.Array(*(tr(choice) for choice in choices))
            control.selection = selected
    for control in rollout.controls:
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
        key = int(rt.getHandleByAnim(mat)), str(mat.params.hwnd), language()
        if force or key!=_ACTIVE:
            localize_material(mat)
            _ACTIVE = key
    except (ImportError, AttributeError, RuntimeError):
        # Startup and closed parameter rollouts may not expose GUI controls yet.
        _ACTIVE = None
