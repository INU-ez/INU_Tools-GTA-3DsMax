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
label description "INU GTA / RenderWare material"
group "Main" (
dropdownlist ui_slot "Vehicle color" items:#("None", "Primary", "Secondary", "Third", "Fourth", "Left headlight", "Right headlight", "Left taillight", "Right taillight")
colorpicker ui_color "Color"
spinner ui_amb "Ambient" range:[0,1,1] type:#float fieldwidth:55
spinner ui_spc "Specular" range:[0,1,0] type:#float fieldwidth:55
spinner ui_dif "Diffuse" range:[0,1,1] type:#float fieldwidth:55
spinner ui_alpha "Alpha" range:[0,255,255] type:#integer fieldwidth:55
)
group "Effects" (
spinner ui_Reflection "Environment strength" range:[0,100,100] type:#float fieldwidth:55
spinner ui_spec_power "Specular strength" range:[0,100,100] type:#float fieldwidth:55
spinner ui_blend "SA reflection intensity" range:[0,1,0] type:#float fieldwidth:55
spinner ui_p_srcblend "Source blend" range:[1,11,5] type:#integer fieldwidth:55
spinner ui_p_destblend "Destination blend" range:[1,11,6] type:#integer fieldwidth:55
spinner ui_matEffect "Effect type (1-5)" range:[1,5,1] type:#integer fieldwidth:55
checkbox ui_use_colormap "Diffuse texture" checked:true
checkbox ui_use_alphamap "Alpha texture" checked:true
checkbox ui_use_RF "Export environment map" checked:false
checkbox ui_use_SI "Export specular" checked:false
checkbox ui_use_SAS "Export SA reflection" checked:false
mapbutton ui_colormap "Diffuse" width:220
mapbutton ui_alphamap "Alpha" width:220
mapbutton ui_reflectionmap "Environment" width:220
mapbutton ui_bumpMap "Bump" width:220
mapbutton ui_specularmap "Specular" width:220
mapbutton ui_dualMap "Dual texture" width:220
)
label help "Effects: 1 None, 2 Env, 3 Bump, 4 Both, 5 Dual"
button generic "Other default" across:2
button vehicle "SA Vehicle default"
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
