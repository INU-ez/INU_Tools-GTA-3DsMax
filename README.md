<div align="center">

# INU Tools — GTA SA (3ds Max)

**🧰 GTA III / VC / SA modding toolkit for 3ds Max. Same engine-rule core as the INU Blender addon, with a Kam's-style interface.**

<p>
  <img src="https://img.shields.io/badge/3ds%20Max-2025%2B-0696D7?logo=autodesk" alt="3ds Max">
  <img src="https://img.shields.io/badge/Python-3.12%20%C2%B7%20PySide6-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Game-GTA%20SA%20%C2%B7%20VC%20%C2%B7%20III-orange" alt="Games">
  <img src="https://img.shields.io/badge/Status-UI%20shell%20%C2%B7%20not%20ready-red" alt="Status">
  <img src="https://img.shields.io/badge/License-GPL--3.0-blue" alt="License">
</p>

**[🇷🇺 Русская версия](docs/README_rus.md)** · **[🧰 INU Tools for Blender](https://github.com/INU-ez/INU_Tools-GTA-Blender)** · **[🔎 INU_Check](https://github.com/INU-ez/INU_Check-GTA)**

</div>

---

> [!WARNING]
> 🚧 **The script is not ready yet.** Right now this is only an **interface shell without the working code**:
> the windows, rollouts and options are in place, but most buttons do nothing yet (a message box says
> "not implemented"). Do not use it for real work — use [INU Tools for Blender](https://github.com/INU-ez/INU_Tools-GTA-Blender)
> instead. See [Status](#-status) for the few early pieces that already run.

## ✨ Highlights

- 🧠 **One core for Blender and Max** — `inu_gta_core` is pure Python (no `bpy`, no `pymxs`): readers/writers for
  DFF, TXD, COL, IFP, IDE, IPL, IMG, `timecyc.dat`, `water.dat`, `map.zon`, `effects.fxp` and the lints built from
  the engine rules. Any fix in the core lands in both versions.
- 🎨 **Looks like Kam's, works like INU** — a native **INU Tools** rollout in the Command Panel opens tool windows made
  of collapsible rollouts, grey buttons and green toggles. The options and buttons are the ones from the INU Blender
  panels.
- 🎮 **III / VC / SA** — the game selector switches RW versions, IDE flags, surface tables and limits.
- 📂 **Own file dialog** — Max-style file list with the INU import/export options on the right, like the sidebar of
  Blender's file browser.
- 🔁 **Hot reload** — each launch and each button press picks up fresh code, no Max restart needed.
- ✂️ **Blender-only parts are left out on purpose**: Texture Bake, live previews, geometry nodes, map painting,
  floater/gizmo.

## 🪟 Tool windows

| Group | Window | What is inside |
|---|---|---|
| 🧊 **Models** | **DFF IO** | Selection summary (DFF / LOD / COL), Import · Export, auto TXD + DXT, check before export, pipeline, COL generation, DFF flags |
| | **Vehicles** | Vehicle tools, frame hierarchy (select / reparent / unparent / F2 rename), Validate Vehicle, `_ok` / `_dam` pairs |
| | **GTA Material** | RW shading, colour/alpha, texture name + filtering + addressing, vehicle colour slots, SA vehicle defaults, paintjobs, GTA effects, UV animation, COL surface picker, alpha materials |
| 🗺️ **Map** | **Map IO** | IDE / IPL / IMG (Import · Export · Map tabs), per-object IDE/IPL properties, ID Manager |
| | **2DFX** | Create effects from presets, all fields and flags, apply to selection, attach/detach to a model; particle systems from `effects.fxp`, emitter parameters, sprites from `effectsPC.txd` |
| | **Paths** | `sapath_*` attributes, select Peds / Vehs / All, Pick / Apply / Bulk |
| | **Zones** | `map.zon` — import as boxes, export with `.bak` and original lines, new zone, parameter editing |
| | **Water** | Add Water, apply parameters to selection, info on the active water plane |
| | **X Radar** | X Radar Maker options |
| 🏃 **Animations** | **IFP IO** | IFP into the scene animation library, round-trip check, Handsign status, rig state, To pivot / To root, ped frame hierarchy |
| 🔎 **Scene** | **Check** | Scene checks, map/file analysis (DFF/COL/TXD scan + IDE/IPL cross-check), TXD texture index |

## 📊 Status

| | Works | Not yet |
|---|---|---|
| 🧊 **DFF / TXD** | ✅ DFF import (geometry, frames, textures from `.txd` next to the model), ✅ TXD → PNG | ⏳ DFF export, COL / CST / IDE / IPL import |
| 🎨 **Material** | ✅ everything in the window | — |
| 🚗 **Vehicles / peds** | ✅ hierarchy, validation, `_ok`/`_dam` | ⏳ scale, create `_dam`, mirror L↔R |
| 🗺️ **Map IO** | ✅ file lists, paths, IDE/IPL counters, districts | ⏳ writing IDE/IPL/IMG |
| ✨ **2DFX** | ✅ effects, presets, particle reading | ⏳ writing `effects.fxp` |
| 🌊 **World** | ✅ `map.zon` fully, water add/apply, path attributes | ⏳ water import/export, path files, radar render |
| 🏃 **IFP** | ✅ import into library, round-trip | ⏳ keys, IK, camera, weights |
| 🔎 **Check** | ✅ file analysis, texture index | ⏳ scene operations |

## 📥 Installation

1. Clone or download the repository, e.g. to `F:\GitHub\INU_Tools-GTA-sa-3Ds Max`.
2. Open `inu_launcher.ms` and set `INU_ROOT` to that folder if it is different.
3. In 3ds Max: **Scripting → Run Script…** → `inu_launcher.ms`. The **INU Tools** rollout appears in the Command
   Panel (Utilities tab).
4. To have it on every start, copy `inu_launcher.ms` into `…\3ds Max 20xx\scripts\Startup\`.

**Dev mode:** **Scripting → Run Python Script…** → `run_inu.py` opens the launcher window directly and reloads all
`inu_max` / `inu_gta_core` modules.

> 🔒 Nothing is written to game files without your action. TXD import extracts PNGs into `<name>_textures\` next to
> the `.txd`; `map.zon` export keeps a `.bak` copy.

## 🧪 Compatibility

| | |
|---|---|
| 🖥️ **3ds Max** | 2025+ (Python 3, PySide6, `qtmax`); developed on **2026** / Python 3.12 |
| 🎮 **Game** | GTA San Andreas (main target), Vice City and III |
| 💻 **OS** | Windows x64 |
| 📦 **Dependencies** | none besides what ships with Max |

<details>
<summary>📁 Repository layout</summary>

```
inu_launcher.ms     native Command Panel rollout (Kam's-style launcher)
inu_boot.py         launch(mode) — sys.path, hot reload, opens a Qt window
run_inu.py          dev entry point (Run Python Script)
inu_gta_core/       shared core: formats + engine-rule lints, pure Python
  dff.py txd.py col.py ifp.py img.py ide.py ipl.py  …  format readers/writers
  *_lint.py         lints (DFF, COL, TXD, IFP, map, skin, text data)
  game_versions.py  III / VC / SA constants and dispatch
  mapsync/          line-preserving IDE/IPL documents
inu_max/            3ds Max layer
  ui/               PySide6 windows (panel.py = window router, style.py / widgets.py = Kam's look)
  adapter/          Max scene ↔ core structures (mesh, material, texture, anim, fx, world, zon)
  ops/              operations (import DFF/TXD, IFP, checks, frames, 2DFX)
```

</details>

<details>
<summary>🔧 Working on the core</summary>

`inu_gta_core/` is a copy of `core/` from the Blender repository. Change the core **there** and copy the whole
folder here (`core/` → `inu_gta_core/`) so both versions stay in sync. The core must not import `bpy` or `pymxs`.

</details>

## 🔗 Links

- 🧰 [INU Tools for Blender](https://github.com/INU-ez/INU_Tools-GTA-Blender) — the original addon this port follows
- 🔎 [INU_Check](https://github.com/INU-ez/INU_Check-GTA) — offline checker for a GTA SA/VC/III folder

## 🙏 Credits

- **Kam's GTA Scripts** — the look and feel of the Max interface.
- **[re3 / reVC](https://github.com/Jai-JAP/re-GTA)** and the GTA modding community's format documentation.

**Author:** INU (Discord `1.n.u` · [server](https://discord.gg/sqtGAVTGdy))

**License:** [GPL-3.0](LICENSE)
