<div align="center">

# INU Tools — GTA SA (3ds Max)

**🧰 GTA SA / VC / III modding toolkit for 3ds Max. Same engine-rule core as the INU Blender addon, with a Kam's-style interface.**

<p>
  <img src="https://img.shields.io/badge/3ds%20Max-2023%E2%80%932026-0696D7?logo=autodesk" alt="3ds Max">
  <img src="https://img.shields.io/badge/Python-3.9%2B%20%C2%B7%20PySide2%20%2F%206-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Game-GTA%20SA%20%C2%B7%20VC%20%C2%B7%20III-orange" alt="Games">
  <img src="https://img.shields.io/badge/Status-Beta-orange" alt="Status">
  <img src="https://img.shields.io/badge/License-GPL--3.0-blue" alt="License">
</p>

**[🇷🇺 Русская версия](docs/README_rus.md)** · **[🧰 INU Tools for Blender](https://github.com/INU-ez/INU_Tools-GTA-Blender)** · **[🔎 INU_Check](https://github.com/INU-ez/INU_Check-GTA)**

</div>

---

> [!WARNING]
> **Version 0.28.0 — Beta.** Import, export and scene tools are implemented; the port has progressed beyond an interface shell.
> Automated checks do not replace testing inside 3ds Max and the game. Keep copies of important scenes and resources before processing them.

## ✨ Highlights

- 🧠 **One core for Blender and Max** — `inu_gta_core` is pure Python (no `bpy`, no `pymxs`): readers/writers for
  DFF, TXD, COL, IFP, IDE, IPL, IMG, `timecyc.dat`, `water.dat`, `map.zon`, `effects.fxp` and the lints built from
  the engine rules. Core updates are synchronized between the repositories.
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
| | **Paths** | SA Compiled NODES, graph and link editing; `sapath_*` attributes, Pick / Apply / Bulk |
| | **Zones** | `map.zon` — import as boxes, export with `.bak` and original lines, new zone, parameter editing |
| | **Water** | Water import/export, Add Water, apply parameters to selection |
| | **X Radar** | X Radar Maker and radar rendering tools |
| 🏃 **Animations** | **IFP IO** | IFP into the scene animation library, round-trip check, Handsign status, rig state, To pivot / To root, ped frame hierarchy |
| 🔎 **Scene** | **Check** | Scene checks, map/file analysis (DFF/COL/TXD scan + IDE/IPL cross-check), TXD texture index |

## 📊 Implemented features

| Area | Features |
|---|---|
| **DFF / TXD / COL** | Model import and export, TXD building, texture extraction, collisions and material properties |
| **Maps and archives** | IDE/IPL/IMG import and export, multi-mesh models, LOD links, shared TXDs, separate LOD IMG archives and COL library updates |
| **Compiled NODES (SA)** | Editable graphs, stable vertex IDs, point creation and deletion, link rebuilding, merging with existing maps, cross-area remapping across 64 areas and validation before writing |
| **ID Manager** | ID assignment, presets, conflict detection and protected game IDs |
| **Vehicles and peds** | Frame hierarchy, `_ok` / `_dam` pairs, scaling, mirroring, rig and weight tools |
| **Animation** | IFP, animation keys, SA character IK with 13 box controls, FK transfer, Bake & Clear, ground-plane foot limits and camera tools; SA UV animation with warnings for III/VC limitations |
| **World and effects** | Water, zones, paths, radar tools, 2DFX and `effects.fxp` writing |
| **Scene and lighting** | Scene checks and mesh operations, Prelight / Bake over, COL properties and separate pipeline settings |
| **Diagnostics** | File analysis, resource checks, extraction error recovery, logs and Extract/Import profiling |

**Validation:** 185 automated tests cover the core, file operations and adapters. The SA IK workflow was also checked in an isolated Max 2026 process using vanilla `army`/`bmycr` peds and `WALK_civi`: all four limb goals, elbow/knee bend directions and pole controls, floor limits, FK transfer, scene save/reload and Bake & Clear. Other native workflows, Max 2023–2025 and in-game results still need validation.

**SA IK:** select the ped skeleton and click **Add IK Rig** in IFP IO. The rig provides four hand/foot boxes, four elbow/knee boxes, two shoulders, spine, head and a root control. **Root motion** chooses Root instead of Pelvis. Existing FK animation transfers onto the controls; an unkeyed skeleton keeps its Max bind axes and the whole character is oriented upright. The boxes are larger and draw over the mesh for easier selection. Colour, size and visibility settings apply to the boxes. **Add Ground Plane** connects foot limits, including when the plane is added after the rig. **Bake & Clear IK** writes the evaluated animation back to the GTA bones and removes rig helpers. For an older four-chain rig, use **Bake & Clear IK** before adding the new rig. If the previous IK version distorted the initial pose, reimport the original DFF and add the rig again; baking would preserve that distorted pose.

The port excludes Blender-specific Texture Bake, geometry nodes and live previews. Some COL, LOD and adapter improvements remain; see the [transfer log](docs/MAX_TODO_2026-09-28.md) for details and limitations.

## 📥 Installation

1. Download and extract the repository, or clone it into a dedicated folder.
2. In 3ds Max, open **Scripting → Run Script…** and select `inu_launcher.ms` from that folder. Its location is detected automatically.
3. In the **INU Tools** rollout on the **Utilities** tab, click **Install INU** (or **Update INU** for an existing installation).
4. Wait for the bundle and any missing NumPy dependency to install, then restart Max. The installed bundle registers the INU Tools menu, launcher and matching native plugin.

To update, replace the source folder's files and click **Update INU** again. If you use multiple Max releases, run installation from each release that needs NumPy. You do not need to copy the launcher into Startup manually.

**Internet access:** installation needs access to PyPI to download NumPy if it is missing from the current Max Python environment. If `pip` is also missing, the installer automatically downloads a temporary pip, verifies its checksum and removes the temporary files after installation. If NumPy is already available, dependency installation does not need internet access; the installed tools run locally.

**Development mode:** run `run_inu.py` through Python in Max to open the launcher window and reload `inu_max` / `inu_gta_core` modules.

## 🧪 Compatibility

| | |
|---|---|
| 🖥️ **3ds Max** | **2023–2026** (2023–2024: PySide2 / Qt5; 2025–2026: PySide6 / Qt6); native runtime verification pending |
| 🎮 **Game** | GTA San Andreas (main target), Vice City and III |
| 💻 **OS** | Windows x64 |
| 📦 **Dependencies** | Max-provided Qt and NumPy (installed by the launcher if missing) |

The installer registers one bundle for Max 2023–2026. NumPy wheels are isolated
by Python version, so installing from another Max release does not overwrite them.
Run **Install / Update INU** in each Max whose Python needs NumPy.

Native `.dli` plugins require a matching SDK build for each Max year. The repository includes separate
2023, 2024, 2025 and 2026 binaries in `plugins/<year>/`. Their SDK versions and
x64 architecture have been checked; in-host runtime validation remains pending. Without
one, use the INU import UI or drop files on its window; viewport drag-and-drop and
plugin-dependent operations such as Bake with shadows are unavailable.

Developer build: `./max_plugin/build.ps1 -Year 2023,2024,2025,2026`, with matching
Autodesk SDKs and v142 (2023/2024) or v143 (2025/2026). `-SdkPath` selects an SDK
for a single target. For extracted SDK/compiler packages, use
`build_portable.ps1 -Year <year> -SdkPath <maxsdk> -ToolsPath <MSVC directory>`. Cross-version compatibility checks use harnesses; they do
not replace running the tools in each installed Max release.

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
  ui/               Qt windows (panel.py = window router, style.py / widgets.py = Kam's look)
  adapter/          Max scene ↔ core structures (mesh, material, texture, anim, fx, world, zon)
  ops/              model/map IO, NODES, scene, vehicle, animation and world tools
plugins/<year>/    native INU_Import.dli builds for Max 2023–2026
dev/tests/         automated regression tests and Max runtime smoke scripts
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
