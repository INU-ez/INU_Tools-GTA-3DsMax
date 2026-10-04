-- INU Tools (3ds Max) — нативный лаунчер в командной панели (как Kam's).
--
-- Кнопки открывают Qt-окна инструментов (Python: inu_boot.launch).
-- Запуск: Scripting -> Run Script -> этот файл. Появится роллаут "INU Tools"
-- в командной панели (вкладка Utilities). Кнопка Setup -> Install INU ставит
-- INU в Max: после перезапуска лаунчер, меню «INU Tools» и перетаскивание .dff
-- во вьюпорт есть сами (пакет INU_Tools.bundle грузит этот файл при старте).
--
-- Папка INU — та, где лежит этот файл (путь вручную задавать не нужно).

global INU_ROOT = pathConfig.removePathLeaf (getThisScriptFilename())
global INU_boot
global INU_translate
global INU_launch
global INU_LAUNCHER_NO_OPEN

fn INU_boot = (
	local cmd = "import sys\np = r'" + INU_ROOT + "'\nif p not in sys.path: sys.path.insert(0, p)\nsys.modules.pop('inu_boot', None)"
	python.execute cmd
	python.import "inu_boot"
)

fn INU_translate text = (
	try ((INU_boot()).translate text) catch (text)
)

fn INU_launch mode = (
	try ( (INU_boot()).launch mode )
	catch ( messageBox (INU_translate ("INU: failed to open the window.\n" + (getCurrentException()))) title:"INU Tools" )
)

try ( closeUtility INU_Tools_util ) catch ()

utility INU_Tools_util "INU Tools" width:162 (
	group "Models" (
		button b_dff "DFF IO  (DFF / TXD)" width:150 height:24 align:#center
		button b_veh "Vehicles"            width:150 height:24 align:#center
		button b_mat "GTA Material"        width:150 height:24 align:#center
		button b_light "Lighting"          width:150 height:24 align:#center
	)
	group "Map" (
		button b_map "Map IO  (IDE / IPL / IMG)" width:150 height:24 align:#center
		button b_fx    "2DFX"  width:150 height:24 align:#center
		button b_paths "Paths" width:150 height:24 align:#center
		button b_zones "Zones" width:150 height:24 align:#center
		button b_water "Water" width:150 height:24 align:#center
		button b_radar "X Radar" width:150 height:24 align:#center
	)
	group "Animations" (
		button b_ifp "IFP IO  (Animations)" width:150 height:24 align:#center
	)
	group "Scene" (
		button b_util "Check" width:150 height:24 align:#center
	)
	group "Setup" (
		dropdownlist languageSelect "Language" items:#("English", "Русский") width:150 align:#center
		label l_setup "" align:#left width:150
		button b_setup "Install INU" width:150 height:24 align:#center \
			tooltip:"Install INU into 3ds Max: drag & drop .dff into the viewport, INU Tools menu, launcher at startup, numpy. Needs a 3ds Max restart."
		button b_unset "Remove" width:150 height:20 align:#center \
			tooltip:"Remove INU Tools from 3ds Max (your INU folder is not touched)"
	)
	label l_ver "INU Tools" align:#left across:2
	label l_ver2 "" align:#right

	fn refreshSetup = (
		try (
			local inuBoot = INU_boot()
			l_setup.text = inuBoot.translate (inuBoot.setup_status())
			b_setup.text = inuBoot.setup_button()
			l_ver2.text = "v" + (inuBoot.version())
			languageSelect.selection = if inuBoot.language() == "RU" then 2 else 1
			languageSelect.caption = inuBoot.translate "Language"
			b_setup.text = inuBoot.translate b_setup.text
			b_unset.text = inuBoot.translate "Remove"
			b_veh.text = inuBoot.translate "Vehicles"
			b_light.text = inuBoot.translate "Lighting"
			b_paths.text = inuBoot.translate "Paths"
			b_zones.text = inuBoot.translate "Zones"
			b_water.text = inuBoot.translate "Water"
			b_util.text = inuBoot.translate "Check"
		) catch ( l_setup.text = INU_translate "Setup: see MAXScript Listener" )
	)

	on languageSelect selected index do (
		(INU_boot()).set_language (if index == 2 then "RU" else "EN")
		(INU_boot()).register_launcher INU_ROOT
	)
	on INU_Tools_util open do refreshSetup()
	on b_dff   pressed do INU_launch "dff"
	on b_veh   pressed do INU_launch "veh"
	on b_mat   pressed do INU_launch "mat"
	on b_light pressed do INU_launch "light"
	on b_map   pressed do INU_launch "map"
	on b_fx    pressed do INU_launch "fx"
	on b_paths pressed do INU_launch "paths"
	on b_zones pressed do INU_launch "zones"
	on b_water pressed do INU_launch "water"
	on b_radar pressed do INU_launch "radar"
	on b_ifp   pressed do INU_launch "ifp"
	on b_util  pressed do INU_launch "util"
	on b_setup pressed do (
		try ( (INU_boot()).setup_install() )
		catch ( messageBox (INU_translate ("INU: installation failed.\n" + (getCurrentException()))) title:"INU Tools" )
		refreshSetup()
	)
	on b_unset pressed do (
		try ( (INU_boot()).setup_remove() )
		catch ( messageBox (INU_translate ("INU: removal failed.\n" + (getCurrentException()))) title:"INU Tools" )
		refreshSetup()
	)
)

-- при запуске Max (пакет INU) роллаут только регистрируется, не открывается
if INU_LAUNCHER_NO_OPEN != true do openUtility INU_Tools_util
