<div align="center">

# INU Tools — GTA SA (3ds Max)

**🧰 Набор инструментов для моддинга GTA III / VC / SA в 3ds Max. То же ядро правил движка, что и в Blender-аддоне INU, интерфейс в стиле Kam's.**

<p>
  <img src="https://img.shields.io/badge/3ds%20Max-2023%E2%80%932026-0696D7?logo=autodesk" alt="3ds Max">
  <img src="https://img.shields.io/badge/Python-3.9%2B%20%C2%B7%20PySide2%20%2F%206-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Game-GTA%20SA%20%C2%B7%20VC%20%C2%B7%20III-orange" alt="Games">
  <img src="https://img.shields.io/badge/Status-UI%20shell%20%C2%B7%20not%20ready-red" alt="Status">
  <img src="https://img.shields.io/badge/License-GPL--3.0-blue" alt="License">
</p>

**[🇬🇧 English version](../README.md)** · **[🧰 INU Tools для Blender](https://github.com/INU-ez/INU_Tools-GTA-Blender)** · **[🔎 INU_Check](https://github.com/INU-ez/INU_Check-GTA)**

</div>

---

> [!WARNING]
> 🚧 **Скрипт ещё не готов.** Сейчас это только **оболочка интерфейса без рабочего кода**: окна, роллауты и
> опции на месте, но большинство кнопок пока ничего не делают (появляется сообщение «not implemented»).
> Для реальной работы не используйте — берите [INU Tools для Blender](https://github.com/INU-ez/INU_Tools-GTA-Blender).
> Немногие ранние части, которые уже запускаются, — в разделе [Статус](#-статус).

## ✨ Возможности

- 🧠 **Одно ядро для Blender и Max** — `inu_gta_core` на чистом Python (без `bpy` и `pymxs`): чтение/запись DFF,
  TXD, COL, IFP, IDE, IPL, IMG, `timecyc.dat`, `water.dat`, `map.zon`, `effects.fxp` и линты по правилам движка.
  Исправление в ядре попадает в обе версии.
- 🎨 **Выглядит как Kam's, работает как INU** — нативный роллаут **INU Tools** в командной панели открывает окна
  инструментов из сворачиваемых роллаутов, серых кнопок и зелёных переключателей. Опции и кнопки — те же, что в
  панелях INU для Blender.
- 🎮 **III / VC / SA** — выбор игры переключает версии RW, флаги IDE, таблицы поверхностей и лимиты.
- 📂 **Своё окно выбора файлов** — список файлов как в Max, справа — опции импорта/экспорта INU (как сайдбар
  файлового браузера Blender).
- 🔁 **Горячая перезагрузка** — каждый запуск и каждое нажатие кнопки подхватывают свежий код без перезапуска Max.
- ✂️ **Blender-специфичное намеренно не переносится**: Texture Bake, живые превью, geometry nodes, рисование по
  картам, floater/gizmo.

## 🪟 Окна инструментов

| Группа | Окно | Что внутри |
|---|---|---|
| 🧊 **Модели** | **DFF IO** | Сводка выделения (DFF / LOD / COL), Import · Export, авто-TXD + DXT, проверка при экспорте, pipeline, генерация COL, флаги DFF |
| | **Vehicles** | Инструменты машин, иерархия фреймов (выделить / сменить родителя / отвязать / F2 — переименовать), Validate Vehicle, пары `_ok` / `_dam` |
| | **GTA Material** | RW-затенение, цвет/прозрачность, имя текстуры + фильтрация + адресация, слоты цвета машины, SA Vehicle defaults, paintjob, GTA-эффекты, UV-анимация, пикер поверхности COL, альфа-материалы |
| 🗺️ **Карта** | **Map IO** | IDE / IPL / IMG (вкладки Import · Export · Map), свойства IDE/IPL объекта, ID Manager |
| | **2DFX** | Создание эффектов из пресетов, все поля и флаги, применение к выделенным, привязка к модели / отвязка; системы частиц из `effects.fxp`, параметры эмиттера, спрайты `effectsPC.txd` |
| | **Paths** | Атрибуты `sapath_*`, выделение Peds / Vehs / All, Pick / Apply / Bulk |
| | **Zones** | `map.zon` — импорт боксами, экспорт с `.bak` и исходными строками, новая зона, правка параметров |
| | **Water** | Add Water, применение параметров к выделенным, сведения об активной воде |
| | **X Radar** | Опции X Radar Maker |
| 🏃 **Анимации** | **IFP IO** | IFP в библиотеку анимаций сцены, проверка round-trip, статус Handsign, состояние rig'а, To pivot / To root, иерархия фреймов педа |
| 🔎 **Сцена** | **Check** | Проверки сцены, анализ карты/файлов (скан DFF/COL/TXD + сверка IDE/IPL), индекс текстур TXD |

## 📊 Статус

| | Работает | Пока нет |
|---|---|---|
| 🧊 **DFF / TXD** | ✅ импорт DFF (геометрия, фреймы, текстуры из `.txd` рядом с моделью), ✅ TXD → PNG | ⏳ экспорт DFF, импорт COL / CST / IDE / IPL |
| 🎨 **Материал** | ✅ всё в окне | — |
| 🚗 **Машины / педы** | ✅ иерархия, валидация, `_ok`/`_dam` | ⏳ масштаб, создание `_dam`, зеркало L↔R |
| 🗺️ **Map IO** | ✅ списки файлов, пути, счётчики IDE/IPL, районы | ⏳ запись IDE/IPL/IMG |
| ✨ **2DFX** | ✅ эффекты, пресеты, чтение частиц | ⏳ запись `effects.fxp` |
| 🌊 **Мир** | ✅ `map.zon` целиком, добавление/применение воды, атрибуты путей | ⏳ импорт/экспорт воды, файлы путей, рендер радара |
| 🏃 **IFP** | ✅ импорт в библиотеку, round-trip | ⏳ ключи, IK, камера, веса |
| 🔎 **Check** | ✅ анализ файлов, индекс текстур | ⏳ операции над сценой |

## 📥 Установка

1. Склонируйте или скачайте репозиторий, например в `F:\GitHub\INU_Tools-GTA-sa-3Ds Max`.
2. Откройте `inu_launcher.ms` и поправьте `INU_ROOT`, если папка другая.
3. В 3ds Max: **Scripting → Run Script…** → `inu_launcher.ms`. В командной панели (вкладка Utilities) появится
   роллаут **INU Tools**.
4. Чтобы он был всегда, положите копию `inu_launcher.ms` в `…\3ds Max 20xx\scripts\Startup\`.

**Режим разработки:** **Scripting → Run Python Script…** → `run_inu.py` сразу открывает окно-лаунчер и
перезагружает все модули `inu_max` / `inu_gta_core`.

> 🔒 Без вашего действия в файлы игры ничего не пишется. Импорт TXD извлекает PNG в `<имя>_textures\` рядом с
> `.txd`; экспорт `map.zon` оставляет копию `.bak`.

## 🧪 Совместимость

| | |
|---|---|
| 🖥️ **3ds Max** | **2023–2026** (2023–2024: PySide2 / Qt5; 2025–2026: PySide6 / Qt6); нативные проверки ещё не завершены |
| 🎮 **Игра** | GTA San Andreas (основная цель), Vice City и III |
| 💻 **ОС** | Windows x64 |
| 📦 **Зависимости** | Qt из Max и NumPy (лаунчер устанавливает его при отсутствии) |

Установщик регистрирует общий пакет для Max 2023–2026. NumPy хранится отдельно
для каждой версии Python. Если в другом Max NumPy отсутствует, запустите
**Install / Update INU** из его лаунчера.

Нативному `.dli` нужен отдельный SDK соответствующего года. В репозитории есть
отдельные бинарники 2023, 2024, 2025 и 2026 в `plugins/<год>/`. Их версии SDK
и архитектура x64 проверены; нативная проверка внутри Max ещё не завершена. Без них доступны импорт из
окна INU и перетаскивание на окно. Перетаскивание во вьюпорт и операции,
требующие плагина (например, Bake with shadows), недоступны.

Проверки совместимости выполнены на harness; запуск инструментов внутри
каждой версии 3ds Max остаётся отдельной проверкой.

<details>
<summary>📁 Структура репозитория</summary>

```
inu_launcher.ms     нативный роллаут в командной панели (лаунчер в стиле Kam's)
inu_boot.py         launch(mode) — sys.path, горячая перезагрузка, открытие Qt-окна
run_inu.py          точка входа для разработки (Run Python Script)
inu_gta_core/       общее ядро: форматы + линты по правилам движка, чистый Python
  dff.py txd.py col.py ifp.py img.py ide.py ipl.py  …  чтение/запись форматов
  *_lint.py         линты (DFF, COL, TXD, IFP, карта, скин, текстовые данные)
  game_versions.py  константы и диспетчеризация III / VC / SA
  mapsync/          документы IDE/IPL с сохранением исходных строк
inu_max/            слой 3ds Max
  ui/               Qt-окна (panel.py — роутер окон, style.py / widgets.py — вид Kam's)
  adapter/          сцена Max ↔ структуры ядра (mesh, material, texture, anim, fx, world, zon)
  ops/              операции (импорт DFF/TXD, IFP, проверки, фреймы, 2DFX)
```

</details>

<details>
<summary>🔧 Правки ядра</summary>

`inu_gta_core/` — копия папки `core/` из Blender-репозитория. Ядро правится **там** и копируется сюда целиком
(`core/` → `inu_gta_core/`), чтобы обе версии были синхронны. Ядро не должно импортировать `bpy` или `pymxs`.

</details>

## 🔗 Ссылки

- 🧰 [INU Tools для Blender](https://github.com/INU-ez/INU_Tools-GTA-Blender) — исходный аддон, за которым следует этот порт
- 🔎 [INU_Check](https://github.com/INU-ez/INU_Check-GTA) — офлайн-проверка папки GTA SA/VC/III

## 🙏 Благодарности

- **Kam's GTA Scripts** — внешний вид интерфейса в Max.
- **[re3 / reVC](https://github.com/Jai-JAP/re-GTA)** и документация форматов от сообщества моддеров GTA.

**Автор:** INU (Discord `1.n.u` · [сервер](https://discord.gg/sqtGAVTGdy))

**Лицензия:** [GPL-3.0](../LICENSE)
