"""Localization preserves format arguments, persisted codes and user data."""
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from inu_max import i18n, settings


class LocalizationTests(unittest.TestCase):
    def translate(self, text, code):
        with patch.object(i18n, 'language', return_value=code):
            return i18n.tr(text)

    def test_english_is_default(self):
        self.assertEqual(settings._DEFAULTS['ui_language'], 'EN')
        self.assertEqual(self.translate('Import', 'EN'), 'Import')

    def test_native_max_and_blender_phrases(self):
        self.assertEqual(self.translate('Language', 'RU'), 'Язык')
        self.assertEqual(self.translate('Selected: 7 mesh(es)', 'RU'), 'Выбрано сеток: 7')
        self.assertEqual(self.translate('Install INU', 'RU'), 'Установить INU')

    def test_paths_and_identifiers_stay_unchanged(self):
        for text in ('army_f0', 'L Knee', r'F:\Models\Body.dff', 'xvehicleenv128', 'IMG/TXD_name'):
            self.assertEqual(self.translate(text, 'RU'), text)

    def test_formatted_message_keeps_model_name(self):
        self.assertEqual(self.translate('Model: Open', 'RU'), 'Модель: Open')
        self.assertEqual(self.translate('Zone created: Body', 'RU'), 'Создана зона: Body')

    def test_multiline_report_and_float_formats(self):
        text = 'Found: 3\nCurrent: army_f0'
        self.assertEqual(self.translate(text, 'RU'), 'Найдено: 3\nТекущая: army_f0')
        self.assertEqual(self.translate('Vehicle Scale ×1.2', 'RU'), 'Масштаб автомобиля ×1.2')

    def test_catalog_preserves_format_placeholders(self):
        pattern = r'%(?:\([^)]*\))?[-+0-9.#]*[sdfgr]|\{\w*\}'
        for filename in ('ru_blender.json', 'ru_max.json'):
            data = json.loads((Path('inu_max/locale')/filename).read_text(encoding='utf-8'))
            for source, target in data.items():
                self.assertEqual(re.findall(pattern, source), re.findall(pattern, target), source)

    def test_language_setting_is_saved_and_invalid_code_rejected(self):
        with patch.object(settings, '_save') as save, patch.object(i18n, 'install'), \
                patch.object(i18n, '_SERVICE', None), patch.dict(settings._STATE):
            i18n.set_language('RU')
            self.assertEqual(settings.get('ui_language'), 'RU')
            save.assert_called_once()
            with self.assertRaises(ValueError):i18n.set_language('DE')

    def test_concatenated_errors_keep_identifiers(self):
        self.assertEqual(self.translate('Missing Skin bones: L Hand, R Hand', 'RU'),
                         'Отсутствующие кости Skin: L Hand, R Hand')

    def test_existing_russian_formatted_reports_can_be_shown_in_english(self):
        self.assertEqual(self.translate('Импортировано: 3', 'EN'), 'Imported: 3')

    def test_two_stage_percent_formatting(self):
        self.assertEqual(self.translate("Baked to 'Day' from 5 objects", 'RU'),
                         'Запечено в «Day» из 5 объектов')
