# INU Tools user guide for 3ds Max

[Русский](USER_GUIDE_rus.md) · [Overview and compatibility](../README.md)

This guide covers installation, model import/export, materials, maps and animations in 3ds Max. Button names are given in English. Select **Setup → Language** to switch between English and Russian.

## Installation and updates

1. Extract INU Tools into a dedicated folder.
2. In Max, choose **Scripting → Run Script…** and run `inu_launcher.ms`.
3. Under **Utilities → INU Tools**, click **Install INU**. To update, replace the source folder files and click **Update INU**.
4. Wait for installation to finish, then restart Max.

If NumPy is missing, installation downloads it from PyPI and needs internet access. If pip is missing too, the installer downloads a temporary pip and removes it afterwards. Installed tools run locally. If you use multiple Max releases, install from each release whose Python needs NumPy.

Max 2023–2026 is supported; working UI checks were performed in Max 2026. Native plugins use the matching year's binary from `plugins/<year>/`.

## Getting started

Open the INU Tools launcher and choose a tool. Use **DFF IO** for individual models, **Map IO** for IDE/IPL/IMG maps and **IFP IO** for animations. Choose **SA**, **III** or **VC**, and **PC** or **Mobile**. The import file dialog's **Auto** option detects the game from the RenderWare version.

Save a separate copy of your scene before editing. Changing the UI language preserves object, material, texture and file names.

## Importing models and textures

1. Open **DFF IO**.
2. Below Import / Export, choose **Import materials → Standard** or **GTA Material**. This affects newly created DFF materials.
3. Enable **Auto TXD** if you want textures.
4. Click **Import**, select files and review the options on the right.
5. Click **Import** in the file dialog and read the resulting report.

Only selected files are imported. DFF, COL, CST, TXD, IDE and IPL each use their own importer. Selecting IDE/IPL in ordinary import does not replace loading map resources through Map IO.

**Standard GTA SA model (vanilla)** enables welding and sharp-edge processing for standard SA geometry. Leave it off for custom models unless you specifically need that processing. **Import 2DFX** creates the DFF's effect helpers.

### Texture lookup

Auto TXD searches the DFF folder and subfolders for matching texture names: PNG, DDS, TGA, BMP, JPG/JPEG and TIFF. Nearby folders win. Loose images take priority over automatically found TXD textures; matching TXDs fill missing textures. A TXD explicitly selected in the same import has the highest priority.

If textures are missing, check image names and locations or select the correct TXD together with the DFF. Choosing a material type does not supply missing images.

### Importing multiple models

Select multiple files using Ctrl/Shift. The progress window shows a percentage, processed-file count and current filename. Updates occur between files, so a large DFF may take time without changing the percentage.

**Cancel** stops before the next file. Already imported objects remain in the scene; cancellation does not roll back the batch. On a retry, exclude files already imported unless you want duplicates.

## Exporting models

1. Select your models and open **DFF IO**. Check the DFF / LOD / COL selection summary.
2. Run **Pre-export check** as needed; **Audit models on export** checks DFF files after writing.
3. Click **Export** and choose the folder, target game and required DFF / COL / LOD / TXD formats in the dialog options.
4. Read the report and check the result in the game.

**Single DFF** writes one output DFF and cannot be combined with **All → IMG**. In IFP IO, **Export skin (single DFF)…** opens export for a single character or vehicle using this mode.

Choose **Numpy** for final texture compression. **Numpy fast** is useful for quick checks but can produce artifacts along sharp alpha edges. Mobile export writes native geometry, but TXDs are written in PC format and need separate PVRTC/ETC conversion for the device.

## GTA and COL materials

**Standard** creates a native Standard material with INU GTA properties. **GTA Material** uses the bundled original Kam/GoldFish `GTA_Mtl`. A separate Kam’s installation is unnecessary; existing original classes are reused.

The material editor offers **GTA Material**, **GTA COL Surface** and **GTA COL Shadow**. DFF materials contain colour, alpha, maps and effects; COL materials contain surface and related collision settings. INU's **GTA Material** window provides material tools and GTA properties.

Legacy INU materials remain available for earlier scenes. Translation and the compact layout preserve their classes and assigned maps. Empty map captions are translated; assigned map names are preserved.

**DK Normal Map**, effect 6, imports/exports normal and reflection textures plus reflection strength through chunk `0x133`. In-game rendering requires the third-party DK plugin. When targeting III/VC, account for limitations of SA effects and UV animation.

## Maps and archives

IDE defines models and IDs, IPL defines instances and placement, and IMG stores resources. A single DFF does not contain a whole map's placement.

1. Open **Map IO → Import** and set **Game folder** to the game root folder.
2. Add the required IPL files using the file or folder button.
3. Run **IMG** and **IDE** searches for the selected IPLs. These buttons find resources without importing them.
4. Choose whether to load **LOD**, **TXD** and **COL**, then click **Import**.

IPL-based import places models using IPL data. IDE-based import lays defined models out in a grid. Before exporting a map, check IDs, LOD links and resource paths. Use **ID Manager** to assign IDs and find conflicts. Map and IMG export options are in Map IO.

## Characters and animations

1. Import the character DFF through DFF IO.
2. Open **IFP IO → Characters** and import an IFP into the scene animation library.
3. Select the skeleton, choose an animation and click **Apply**.
4. Click **Add IK Rig** to edit with IK. For an animation that moves the character, choose **Root motion (walk/run)** before creating the rig.
5. After editing, run **Bake & Clear IK**, then export the IFP.

The SA rig has 13 boxes: hands and feet, elbows and knees, shoulders, spine, head and root. Elbow/knee boxes control bend direction. The panel provides control colour, size and visibility settings. **Add Ground Plane** connects foot limits.

Bake & Clear IK writes evaluated animation onto GTA bones and removes the controls. Run it before IFP export so IK movement reaches the file. Clear an older rig before creating a new one. If an older version already distorted the initial pose, reimport the original DFF: baking preserves the distorted pose.

**Export** saves an IFP. **Add** adds animations to an existing pack or replaces matching names case-insensitively, preserving other animations. Back up a game animation pack before modifying it.

## Other tools

| Window | Purpose |
|---|---|
| Vehicles | Vehicle frame hierarchy, `_ok` / `_dam` pairs and vehicle checks |
| 2DFX | DFF effects and `effects.fxp` particle parameters |
| Paths | SA Compiled NODES points, links and graph attributes |
| Zones | Box-based `map.zon` editing and export with a `.bak` |
| Water | Import, create and export water |
| X Radar | Radar creation tools |
| Check | Scene/file checks, IDE/IPL references and texture lookup |

When editing Compiled NODES, keep related areas available: changing point IDs can require remapping external links. Do not bypass graph validation on export.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Tools do not open after installation | Restart Max; if needed, run Update INU from the current source folder |
| NumPy was not installed | PyPI access and the Install / Update INU report in the Max release being used |
| Missing textures | Auto TXD, image names, the DFF folder and selected TXD |
| Import percentage temporarily stays unchanged | The current file is being processed; updates and cancellation occur between files |
| Viewport drag-and-drop is unavailable | The native plugin for the correct Max year; use Import or drop onto the INU window |
| Exported animation differs from IK | Bake & Clear IK must run before exporting IFP |

Save the operation report and MAXScript Listener messages when an error occurs. Ordinary import writes its stage log to `%LOCALAPPDATA%\INU_Tools_Max\freeze_trace.txt`; starting a new trace replaces the previous log. Settings are stored alongside it in `settings.json`.

For a bug report, include Max and INU versions, game/platform, the action, options and a file that reproduces the error. For bulk import, include file count and the last filename shown. After a crash, preserve the dump and log before retrying.

## Blender documentation and limitations

[INU Tools for Blender](https://github.com/INU-ez/INU_Tools-GTA-Blender) provides additional information about shared GTA formats, IDs, LODs and engine rules. Use this guide for Max operations: materials, selection, hierarchy, IK controls and file dialogs depend on the host application. Blender-specific Texture Bake, geometry nodes and live previews are not ported to Max.

See the [transfer log](MAX_TODO_2026-09-28.md) for validation details and known limitations. Max 2026 checks do not guarantee the same results in Max 2023–2025 or in the game.
