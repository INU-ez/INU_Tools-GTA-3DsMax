# INU Tools (Max) — настройки окон (игра, платформа, опции импорта/экспорта,
# пути, раскрытые блоки...). UI читает/пишет через get/set.
#
# Хранятся в %LOCALAPPDATA%\INU_Tools_Max\settings.json: читаются при
# загрузке модуля, пишутся при каждой правке — переживают и повторное
# открытие окна (лаунчер перезагружает модули inu_max), и перезапуск Max.
# Ключи и умолчания повторяют scene-настройки Blender-версии INU; ключи
# файла, которых нет в _DEFAULTS, игнорируются, новые ключи берут умолчание.

import copy
import json
import os

_DEFAULTS = {
    'game': 'SA',            # 'SA' | 'VC' | 'III' — игра проекта (экспорт)
    'platform': 'PC',        # 'PC' | 'MOBILE'

    # — Импорт (диалог «Импорт» INU) —
    'import_auto_game': True,   # определять игру по RW-версии файла
    'import_game': 'SA',        # игра импорта, когда Auto выключен
    'imp_f_dff': True,          # «Показывать форматы» — фильтр диалога
    'imp_f_col': True,
    'imp_f_cst': True,
    'imp_f_txd': True,
    'imp_f_ide': True,
    'imp_f_ipl': True,
    'import_weld_sharpen': False,  # «Стандартная модель GTA SA (vanilla)»
    'import_2dfx': True,        # создавать 2DFX-эффекты из DFF
    'auto_txd': True,           # авто-подбор TXD при импорте DFF

    # — Экспорт (Export All INU) —
    'exp_dff': True,
    'exp_col': True,
    'exp_lod': True,
    'exp_txd': True,
    'exp_cst': False,
    'exp_ide_ipl': False,       # дописать в IDE / IPL (пути из окна Map IO)
    'exp_single_dff': False,    # вся иерархия в один DFF (машина / пед)
    'col_library': False,       # все коллизии в один .col
    'col_library_name': 'collision',
    'col_empty': False,
    'col_light_mode': 'AUTO',   # свет COL: 'AUTO' (день/ночь ниже на всё) | 'MATERIAL'
    'col_auto_day': 14,         # 14 / 4 = старый байт Kam's 78
    'col_auto_night': 4,
    'txd_shared': False,        # все текстуры в один .txd
    'txd_shared_name': 'textures',
    'txd_merge': False,         # дописать в существующий .txd
    'dxt_backend': 'numpy',     # 'numpy' | 'numpy_fast'
    'pipe_flag_defaults': {},
    'export_pipeline': 'NONE',  # NONE | 0x53F2009A | 0x53F20098 | 0x53F2009C | PED
    'export_vertex_alpha': False,
    'export_to_img': False,     # All → IMG (путь img_path)
    'audit_on_export': False,

    # — Map IO: IDE / IPL / IMG (как панель INU) —
    'ide_ipl_mode': 'IMPORT',   # вкладка: IMPORT | EXPORT | MAP
    'game_root': '',            # папка игры (Import и Map)
    'map_load_lod': False,      # LOD (в INU skip_lod=True → кнопка отжата)
    'map_load_2dfx': False,     # 2DFX (в INU skip_2dfx=True → отжата)
    'map_load_txd': False,
    'map_load_col': False,
    'map_skip_dupes': False,    # «Без дублей»
    'map_group_by_ipl': True,   # «Группировать по IPL»
    'map_region': 'ALL',
    'ipl_sync_list': [],        # IPL для импорта / экспорта (один список)
    'ide_sync_list': [],        # IDE для экспорта
    'found_imgs': [],           # IMG с моделями из IPL (результат поиска)
    'found_ides': [],           # IDE с моделями из IPL
    'binary_ipls': [],          # [{name, enabled, img_source}]
    'text_ipls': [],            # [{name, enabled, path, img_source}]
    'profile_enabled': False,
    # раскрытые блоки (как в INU)
    'show_import_ipl_list': True,
    'show_found_imgs': True,
    'show_found_ides': True,
    'show_sync_ipl': False,
    'show_sync_ide': False,
    'show_ide_flags_box': False,
    'show_ipl_extra': False,
    'show_binary_ipls': False,
    'show_text_ipls': False,
    'show_ide_flags': False,    # флаги в «Object IDE / IPL»
    'show_id_service': False,
    # ID Manager
    'id_preset': 'default',
    'id_search': '',
    'id_page': 0,

    # — Check: «Проверка» (как панель INU) —
    'hide_dff': False, 'hide_lod': False, 'hide_col': False, 'hide_sha': False,
    'links_active': False,
    # «Анализ карты/файлов»
    'analysis_mode': 'FILES',   # FILES | MAP
    'scan_dir': '',
    'scan_recursive': False,
    'scan_dff': True, 'scan_col': True, 'scan_txd': True,
    'lint_profile': 'STANDARD', # STANDARD | FLA | STRICT | LENIENT
    'scan_only_errors': True,
    'scan_report_target': 'SCENE',   # SCENE (рядом с .max) | SCAN | CUSTOM
    'scan_report_custom_path': '',
    'map_analyzer_mode': 'FOLDER',   # DAT | FOLDER | CUSTOM
    'map_analyzer_dat_path': '',
    'map_analyzer_folder': '',
    'map_analyzer_recursive': True,
    'map_analyzer_custom_ides': [],
    'map_analyzer_custom_ipls': [],
    'map_analyzer_check_img': False,
    'map_analyzer_only_errors': True,
    # «Текстуры (TXD)»
    'texture_browser_source': 'DAT',  # DAT | FOLDER | CUSTOM
    'texture_browser_folder': '',
    'texture_browser_custom': [],
    'texture_browser_check_ide': True,
    'texture_browser_search': '',
    # «Проверка перед экспортом»: раскрытые группы
    'validate_expanded': [],

    # — Анимации (панель INU «Анимации») —
    'anim_tab': 'CHAR',             # CHAR | OBJ
    'ifp_action': '',               # анимация библиотеки для Apply / Preview
    'ik_root_motion': False,
    'ik_extras_show': False,        # «Дополнительно»
    'floor_offset': 0.05,
    'ik_color': [0.2, 1.0, 0.2, 1.0],
    'ik_size': 1.0,
    'ik_show_chain': True, 'ik_show_pole': True,
    'ik_show_rot': True, 'ik_show_root': True,
    'anim_tools_show': False,       # «Настройка анимации»
    'anim_fix_start': 0,
    'anim_fix_end': 10000,
    'smooth_axis_mode': 'ALL',      # ALL | WORLD_X | WORLD_Y | WORLD_Z
    'mirror_root_rotation': True,
    'mirror_flip_root_180': True,
    'mirror_flip_root_axis': 'X',
    'mirror_flip_root_space': 'GLOBAL',   # LOCAL | GLOBAL
    'mirror_invert_root_loc': 'Y',  # NONE | X | Y | Z
    'animobj_picker_target': 'NEW_PIVOT',  # NEW_PIVOT | PIVOT | ROOT
    # окна выбора файлов: Export IFP / Add (merge) / Batch / камера / жест
    'ifp_package': 'custom',
    'ifp_active_only': False,
    'ifp_format': 'ANP3',           # при открытии: ANP3 для SA, иначе ANPK
    'ifp_decimate': False,
    'ifp_tol_rot': 0.001,
    'ifp_tol_trans': 0.001,
    'merge_package': '',
    'merge_current_only': True,
    'merge_decimate': False,
    'merge_tol_rot': 0.001,
    'merge_tol_trans': 0.001,
    'batch_prefix': '',
    'batch_mode': 'NLA',            # NLA (подряд с зазором) | ACTIONS
    'batch_gap': 10.0,
    'batch_start': 0,
    'batch_count': 0,
    'cam_z_import': True,
    'cam_z_export': True,
    'hs_format': 'ANP3',
    'hs_decimate': False,
    'hs_tol_rot': 0.001,
    'hs_tol_trans': 0.001,
    # диалоги «DFF+IFP+IDE» (Export Animated Object) и «+Pivot»
    'ao_directory': '',
    'ao_base_name': 'mill',
    'ao_txd_name': 'mill',
    'ao_model_id': 18000,
    'ao_draw_distance': 300.0,
    'ao_existing_ifp': '',
    'ao_ifp_name': '',
    'ao_ifp_mode': 'APPEND',        # NEW | APPEND | UPDATE
    'ao_ifp_format': 'ANPK',
    'ao_write_ide': True,
    'pv_name': 'pivot2',
    'pv_axis': 'Z',
    'pv_turns': 1,
    'pv_duration': 60,
    'pv_parent_mesh': True,

    # — 2DFX (панели INU «Эффекты» и «GTA SA: <тип>») —
    'fx_show_links': False,         # «Relationship lines» (Display Links)
    'fx_txd_path': '',              # явный .txd текстур эффектов
    'fx_show_props': False,         # раскрытые разделы настроек света
    'fx_show_behavior': False,
    'fx_show_shadow': False,
    'fx_show_flags': False,
    'fx_pfx_texture': False,        # раскрытые разделы настроек частицы
    'fx_pfx_color': False,
    'fx_pfx_size': False,
    'fx_pfx_emission': False,
    'fx_pfx_physics': False,
    'fx_pfx_system': False,
    'fx_pfx_curves': False,
    'fx_new_name': 'prt_custom',    # диалоги effects.fxp
    'fx_save_name': '',
    'fx_save_overwrite': True,

    # — Water (панель INU «Water») —
    'water_flag': '1',              # 0..3: Default/Shallow × Invisible/Visible
    'water_speed_x': 0.0,
    'water_speed_y': 0.0,
    'water_speed_z': 0.05,
    'water_wave_height': 0.1,
    # — map.zon —
    'zon_path': '',                 # data/map.zon или data/info.zon
    # — Paths —
    'nodes_fla4': False,            # Export nodes: FLA4
    'curves_fla4': False,           # Curves → .dat
    'curves_path_set': '64',
    'curves_entire_map': False,
    'bulk_type': 'NONE', 'bulk_traffic': 'NONE', 'bulk_spawn': -1.0,
    'bulk_width': -1.0, 'bulk_highway': 'NONE', 'bulk_boats': 'NONE',
    'bulk_parking': 'NONE',
    'acc_type': 'TL', 'acc_knot': 0,
    # — GTA Material (панель INU «GTA Material») —
    'mat_tab': 'EFFECTS',           # EFFECTS | SURFACE | ALPHA
    'mat_show_vehicle': False,      # раскрытые блоки вкладки Effects
    'mat_show_fx': False,
    'alpha_scope': 'SCENE',         # SCENE | SELECTED
    'alpha_filter_mode': 'NODE',    # NODE | CHANNEL | TRANSPARENT | ALL
    'alpha_bulk_blend': 'CLIP',     # OPAQUE | CLIP | HASHED | BLEND
    'surf_all_selected': False,     # пикер поверхности: ко всем COL
    # — X Radar Maker —
    'radar_output': '',
    'radar_grid': 0,
    'radar_size': 256,
    'radar_height': 3000.0,
    'radar_specific': '',
    # — Lighting (панель INU «Lighting»: PreLight / PreLight COL) —
    'light_mode': 'PRELIGHT',       # PRELIGHT | COL
    'prelight_preset': 'Default',
    'bake_ambient': 0.10,           # Advanced Settings (только «Bake»)
    'bake_intensity': 0.05,
    'bake_gamma': 0.50,
    'prelight_use_point': True,     # какие лампы запекать
    'prelight_use_sun': True,
    'prelight_use_spot': True,
    'prelight_use_area': True,
    'prelight_use_hdri': False,
    'show_prelight_view': False,    # «Preview correction»
    'prelight_view_bright': 0.004,
    'prelight_view_contrast': 0.0,
    'prelight_view_gamma': 1.0,
    'prelight_view_saturation': 1.0,
    # Tools / Post-Processing (часть 2; значения — как в INU, для пресетов)
    'fill_prelight_day': [124 / 255.0] * 3,     # sRGB (байт 124)
    'fill_prelight_night': [83 / 255.0] * 3,    # sRGB (байт 83)
    'fill_prelight_selected_only': False,
    'scatter_color_color': [1.0, 1.0, 1.0],     # sRGB
    'scatter_color_strength': 1.0,
    'scatter_color_distance': 0.3,
    'vc_smooth_iterations': 1,
    'vc_smooth_factor': 0.5,
    'vc_contrast': 1.0,
    'vc_brightness': 0.0,
    'vc_gamma': 1.0,
    'lift_shadows_strength': 0.5,
    # Foliage / Tree (часть 2)
    'foliage_material_name': '',
    'foliage_color_material_name': '',
    'foliage_select_only': False,
    'foliage_both_sides': True,
    'foliage_blend': 'MULTIPLY',                # MULTIPLY | REPLACE
    'foliage_metric': 'SPHERE',                 # SPHERE | CYLINDER
    'foliage_inside': 0.25,
    'foliage_outside': 1.0,
    'foliage_gamma': 1.0,
    'foliage_height_dark': 0.0,
    'foliage_color_height_dark': 0.0,
    'foliage_top_bright': 0.0,
    'foliage_top_height': 1.0,
    'foliage_variation': 0.0,
    'foliage_light_tint': [0.55, 0.8, 0.3],     # sRGB
    'foliage_shadow_tint': [0.2, 0.35, 0.12],   # sRGB
    'foliage_tint_strength': 1.0,
    # PreLight COL (часть 3)
    'col_day_min': 10, 'col_day_max': 15,
    'col_night_min': 0, 'col_night_max': 5,
    'col_light_edge': 0.0,          # «Край»: гамма яркости
    'col_light_threshold': 0,       # «Порог» 0..100 (100 — без порога)
    'col_light_contrast': 0.0,      # S-контраст
    'col_light_show_numbers': True,

    'ide_path': '',
    'ipl_path': '',
    'img_path': '',
}


# глубокая копия: списки умолчаний правятся «на месте» — не должны
# портить сами умолчания (reset вернул бы испорченное)
_STATE = copy.deepcopy(_DEFAULTS)


def path():
    """Файл настроек (рядом с file_dialog.json и id_presets)."""
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'INU_Tools_Max', 'settings.json')


def _load():
    try:
        with open(path(), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return                      # нет файла / испорчен — умолчания
    if isinstance(data, dict):
        _STATE.update({k: v for k, v in data.items() if k in _DEFAULTS})


def _save():
    """Записать через временный файл: сбой посреди записи не портит
    прежние настройки."""
    p = path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(_STATE, f, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, p)
    except (OSError, TypeError, ValueError) as e:
        print("[INU] settings not saved: %r" % (e,))


_load()


def get(key, default=None):
    return _STATE.get(key, default)


def set(key, value):        # noqa: A003  (умышленно как в bpy props)
    # сохраняем всегда: список мог измениться «на месте» и прийти тем же
    # объектом — сравнение со старым значением его бы пропустило
    _STATE[key] = value
    _save()


def reset():
    """Вернуть все настройки к умолчаниям (и в файле)."""
    _STATE.clear()
    _STATE.update(copy.deepcopy(_DEFAULTS))
    _save()


def as_dict():
    return dict(_STATE)
