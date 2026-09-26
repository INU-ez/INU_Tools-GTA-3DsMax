# INU Tools — 3ds Max adapter package.
#
# Хост-специфичный слой (pymxs / PySide6) поверх общего ядра inu_gta_core.
# Ядро (чтение/запись форматов GTA + линты) НЕ знает про Max — этот пакет
# конвертирует сцену Max ↔ нейтральные структуры ядра (DffClump/ColModel/…)
# и рисует UI. Зеркало Blender-аддона, но без bake/превью/geo-nodes.

__version__ = (0, 1, 0)
