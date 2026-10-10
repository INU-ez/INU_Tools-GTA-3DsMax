-- INU Tools: original standalone scripted GTA material.
-- Separate class ID allows coexistence with Kam's GTA_Mtl.
plugin material INU_GTA_Mtl name:"INU GTA Material" classID:#(0x6a415521,0x37b06912) extends:Standard replaceUI:true version:1
(
parameters main rollout:mainUI
(
amb type:#float default:1 ui:ui_amb
spc type:#float default:0 ui:ui_spc
dif type:#float default:1 ui:ui_dif
alpha type:#integer default:255 ui:ui_alpha
Reflection type:#float default:100 ui:ui_Reflection
spec_power type:#float default:100 ui:ui_spec_power
blend type:#float default:0 ui:ui_blend
p_srcblend type:#integer default:5 ui:ui_p_srcblend
p_destblend type:#integer default:6 ui:ui_p_destblend
matEffect type:#integer default:1 ui:ui_matEffect
color type:#color default:white ui:ui_color
colhprIdx type:#integer default:1 ui:ui_slot
use_colormap type:#boolean default:true ui:ui_use_colormap
use_alphamap type:#boolean default:true ui:ui_use_alphamap
use_RF type:#boolean default:false ui:ui_use_RF
use_SI type:#boolean default:false ui:ui_use_SI
use_SAS type:#boolean default:false ui:ui_use_SAS
colormap type:#texturemap ui:ui_colormap
alphamap type:#texturemap ui:ui_alphamap
reflectionmap type:#texturemap ui:ui_reflectionmap
bumpMap type:#texturemap ui:ui_bumpMap
specularmap type:#texturemap ui:ui_specularmap
dualMap type:#texturemap ui:ui_dualMap
on color set value do delegate.diffuse=value
on alpha set value do delegate.opacity=value/255.0*100.0
on colormap set value do (delegate.diffuseMap=value; delegate.diffuseMapEnable=use_colormap; delegate.diffuseMapAmount=100)
on use_colormap set value do delegate.diffuseMapEnable=value
on alphamap set value do (delegate.opacityMap=value; delegate.opacityMapEnable=use_alphamap)
on use_alphamap set value do delegate.opacityMapEnable=value
on reflectionmap set value do delegate.reflectionMap=value
on Reflection set value do delegate.reflectionMapAmount=value
on specularmap set value do delegate.specularMap=value
on use_RF set value do delegate.reflectionMapEnable=value
on use_SI set value do delegate.specularMapEnable=value
)
rollout mainUI "GTA Parameters"
(
label description "INU GTA / RenderWare material" width:315
label slot_label "Vehicle color" pos:[10,35] width:95
dropdownlist ui_slot "" pos:[115,32] width:200 items:#("None", "Primary", "Secondary", "Third", "Fourth", "Left headlight", "Right headlight", "Left taillight", "Right taillight")
group "Main" (
label main_space ""
spinner ui_amb "Ambient" pos:[10,80] width:95 range:[0,1,1] type:#float fieldwidth:45
spinner ui_spc "Specular" pos:[115,80] width:95 range:[0,1,0] type:#float fieldwidth:45
spinner ui_dif "Diffuse" pos:[220,80] width:95 range:[0,1,1] type:#float fieldwidth:45
label color_label "Color" pos:[10,108] width:55
colorpicker ui_color "" pos:[65,103] width:45 height:21
checkbox ui_use_colormap "" pos:[130,105]
mapbutton ui_colormap "None" pos:[150,103] width:165
label alpha_label "Alpha" pos:[10,133] width:55
spinner ui_alpha "" pos:[65,130] range:[0,255,255] type:#integer fieldwidth:45
checkbox ui_use_alphamap "" pos:[130,130]
mapbutton ui_alphamap "None" pos:[150,128] width:165
)
group "Material Effects" (
label type_label "TYPE:" pos:[10,183] width:45
dropdownlist ui_matEffect "" pos:[56,180] width:260 height:21 items:#("NONE","Reflection map","Bump map","Reflection + Bump map","Dual map")
checkbox ui_use_RF "Reflection Export" pos:[10,205] width:300
label reflection_label "Reflection" pos:[10,233] width:55
spinner ui_Reflection "" pos:[65,230] range:[0,100,100] type:#float fieldwidth:45
mapbutton ui_reflectionmap "None" pos:[150,227] width:165
label bump_title "BUMP Export" pos:[10,263] width:305
label bump_label "Bump" pos:[10,290] width:100
mapbutton ui_bumpMap "None" pos:[150,286] width:165
label dual_title "DUAL Texture Export" pos:[10,325] width:305
label source_label "Source blend" pos:[10,350] width:95
dropdownlist ui_p_srcblend "" pos:[110,345] width:205 height:21 items:#("rpBLENDZERO", "rpBLENDONE", "rpBLENDSRCCOLOR", "rpBLENDINVSRCCOLOR", "rpBLENDSRCALPHA", "rpBLENDINVSRCALPHA", "rpBLENDDESTALPHA", "rpBLENDINVDESTALPHA", "rpBLENDDESTCOLOR", "rpBLENDINVDESTCOLOR", "rpBLENDSRCALPHASAT")
label destination_label "Destination blend" pos:[10,379] width:95
dropdownlist ui_p_destblend "" pos:[110,373] width:205 height:21 items:#("rpBLENDZERO", "rpBLENDONE", "rpBLENDSRCCOLOR", "rpBLENDINVSRCCOLOR", "rpBLENDSRCALPHA", "rpBLENDINVSRCALPHA", "rpBLENDDESTALPHA", "rpBLENDINVDESTALPHA", "rpBLENDDESTCOLOR", "rpBLENDINVDESTCOLOR", "rpBLENDSRCALPHASAT")
mapbutton ui_dualMap "None" pos:[10,408] width:305
)
group "Specular Image" (
checkbox ui_use_SI "Export Specular Image section" pos:[10,454] width:305
label specular_label "Glossiness" pos:[10,484] width:55
spinner ui_spec_power "" pos:[65,484] range:[0,100,100] type:#float fieldwidth:45
mapbutton ui_specularmap "None" pos:[150,479] width:165
)
group "SA Specular" (
checkbox ui_use_SAS "Export SA Specular section" pos:[10,530] width:305
label blend_label "SA reflection intensity" pos:[10,560] width:210
spinner ui_blend "" pos:[225,557] range:[0,1,0] type:#float fieldwidth:55
)
button generic "Other default" width:145 across:2
button vehicle "SA Vehicle default" width:145
on ui_slot selected index do (
local colors=#([255,255,255], [60,255,0], [255,0,175], [0,255,255], [255,0,255], [255,175,0], [0,255,200], [185,255,0], [255,60,0])
local tint=copy white
tint.r=colors[index].x; tint.g=colors[index].y; tint.b=colors[index].z
color=tint
)
on generic pressed do (amb=1; spc=0; dif=1; alpha=255; use_RF=false; use_SI=false; use_SAS=false; matEffect=1)
on vehicle pressed do (amb=1; spc=1; dif=1; use_RF=true; use_SI=true; use_SAS=true; Reflection=20; spec_power=100; blend=0.05; matEffect=2; reflectionmap=bitmaptexture filename:"xvehicleenv128.png"; specularmap=bitmaptexture filename:"vehiclespecdot64.png")
)
on create do (delegate.twoSided=true; delegate.diffuseMapAmount=100; delegate.reflectionMapEnable=false; delegate.specularMapEnable=false)
)
