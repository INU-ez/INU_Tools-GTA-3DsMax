-- INU Tools (3ds Max) — нативный лаунчер в командной панели (как Kam's).
--
-- Кнопки открывают Qt-окна инструментов (Python: inu_boot.launch).
-- Запуск: Scripting -> Run Script -> этот файл. Появится роллаут "INU Tools"
-- в командной панели (вкладка Utilities). Чтобы был всегда — положи копию в
-- папку ...\3ds Max 2026\scripts\Startup\ (как скрипты Kam's).
--
-- ВАЖНО: путь к проекту ниже. Если папка другая — поправь INU_ROOT.

global INU_ROOT = "F:/GitHub/INU_Tools-GTA-sa-3Ds Max"

fn INU_launch mode = (
	local guard = "(sys.path.insert(0,p) if p not in sys.path else None)"
	local cmd = "import sys; p=r'" + INU_ROOT + "'; " + guard + \
		"; sys.modules.pop('inu_boot',None); import inu_boot; inu_boot.launch('" + mode + "')"
	try ( python.execute cmd )
	catch ( messageBox ("INU: failed to open the window.\n" + (getCurrentException())) title:"INU Tools" )
)

try ( closeUtility INU_Tools_util ) catch ()

utility INU_Tools_util "INU Tools" width:162 (
	group "Models" (
		button b_dff "DFF IO  (DFF / TXD)" width:150 height:24 align:#center
		button b_veh "Vehicles"            width:150 height:24 align:#center
		button b_mat "GTA Material"        width:150 height:24 align:#center
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
	label l_ver "INU Tools" align:#left across:2
	label l_ver2 "v0.12.0" align:#right

	on b_dff   pressed do INU_launch "dff"
	on b_veh   pressed do INU_launch "veh"
	on b_mat   pressed do INU_launch "mat"
	on b_map   pressed do INU_launch "map"
	on b_fx    pressed do INU_launch "fx"
	on b_paths pressed do INU_launch "paths"
	on b_zones pressed do INU_launch "zones"
	on b_water pressed do INU_launch "water"
	on b_radar pressed do INU_launch "radar"
	on b_ifp   pressed do INU_launch "ifp"
	on b_util  pressed do INU_launch "util"
)

openUtility INU_Tools_util
