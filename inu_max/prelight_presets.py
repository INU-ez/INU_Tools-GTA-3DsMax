# INU Tools (Max) — пресеты Prelight (как пресеты вкладки PreLight
# Blender-версии INU: тот же JSON — файлы можно переносить между версиями).
#
# Файл на пресет: %LOCALAPPDATA%\INU_Tools_Max\presets\<имя>.json. «Default»
# — встроенный (в коде, только чтение), всегда первый в списке.
# Лампы пресета — [{name, rel_offset [x,y,z], color [r,g,b], energy, radius}]:
# цвет — как в Blender (линейный 0..1), смещение — от центра ламп.

import json
import os
import tempfile

DEFAULT_NAME = "Default"

DEFAULT = {
    "name": DEFAULT_NAME,
    "ambient": 0.10,
    "intensity": 0.05,
    "gamma": 0.50,
    "shadows": True,
    "modulate_mode": "OFF",
    "modulate_mix": 0.002,
    "modulate_contrast": 0.0,
    "modulate_gamma": 0.8,
    "v_offset": 0.0,
    "scatter_strength": 1.0,
    "scatter_distance": 0.3,
    "vc_smooth_iter": 1,
    "vc_smooth_factor": 0.5,
    "vc_contrast": 1.0,
    "vc_brightness": 0.0,
    "vc_gamma": 1.0,
    "lift_shadows": 0.5,
    "v_offset_day": 0.0,
    "v_offset_night": 0.0,
    "has_day_attr": True,
    "has_night_attr": True,
    "lights": [],
}

# поле пресета → ключ настроек окна (settings.py)
SETTINGS_KEYS = {
    "ambient": 'bake_ambient', "intensity": 'bake_intensity', "gamma": 'bake_gamma',
    "scatter_strength": 'scatter_color_strength', "scatter_distance": 'scatter_color_distance',
    "vc_smooth_iter": 'vc_smooth_iterations', "vc_smooth_factor": 'vc_smooth_factor',
    "vc_contrast": 'vc_contrast', "vc_brightness": 'vc_brightness', "vc_gamma": 'vc_gamma',
    "lift_shadows": 'lift_shadows_strength',
}


def presets_dir():
    d = os.path.join(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir(),
                     'INU_Tools_Max', 'presets')
    os.makedirs(d, exist_ok=True)
    return d


def _safe(name):
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name)


def path_of(name):
    return os.path.join(presets_dir(), _safe(name) + ".json")


def load_all():
    """[пресет] — Default первым, затем файлы по имени файла."""
    out = [dict(DEFAULT)]
    d = presets_dir()
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith('.json'):
            continue
        try:
            with open(os.path.join(d, f), 'r', encoding='utf-8') as fh:
                p = json.load(fh)
            name = p.get('name')
            if not name or name == DEFAULT_NAME:
                continue
            out.append(p)
        except (OSError, ValueError, AttributeError):
            continue
    return out


def names():
    return [p['name'] for p in load_all()]


def get(name):
    return next((p for p in load_all() if p.get('name') == name), None)


def save(preset):
    with open(path_of(preset['name']), 'w', encoding='utf-8') as f:
        json.dump(preset, f, indent=2, ensure_ascii=False)


def delete(name):
    p = path_of(name)
    if os.path.isfile(p):
        os.remove(p)
        return True
    return False
