import sys, json, traceback
sys.dont_write_bytecode=True
from pathlib import Path
import pymxs
from pymxs import runtime as rt
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from inu_max import settings
from inu_max.adapter import material as M
settings._save=lambda:None
result={}
try:
    rt.resetMaxFile(rt.Name('noPrompt'))
    settings._STATE['import_material_type']='GTA'
    mat=M.create_import_material('test_GTA')
    assert str(rt.classOf(mat))=='GTA_Mtl'
    M.set_color(mat,(.2,.4,.6,.5))
    assert abs(M.color(mat)[3]-.5)<.003
    M.set_diffuse(mat,rt.Bitmaptexture(fileName='body.png'))
    assert M.texture_stem(mat)=='body'
    M.set_props(mat,dict(ambient=.7,surf_specular=.3,surf_diffuse=.8,export_env_map=True,env_map_coef=.2,env_map_tex='env',export_specular=True,specular_level=.8,export_reflection=True,reflection_intensity=.05))
    assert abs(float(mat.Reflection)-20)<.001
    mat.amb=.4
    assert abs(M.props(mat)['ambient']-.4)<.001
    M.set_blend(mat,'BLEND')
    assert mat.alphamap is not None and M._opacity_on(mat)
    M.set_blend(mat,'OPAQUE')
    assert not M._opacity_on(mat)
    obj=rt.Box(); obj.material=mat
    scene=ROOT/'dev/tests/e2e/material_roundtrip.max'
    rt.saveMaxFile(str(scene),quiet=True)
    rt.resetMaxFile(rt.Name('noPrompt'))
    rt.loadMaxFile(str(scene),quiet=True)
    mat=rt.objects[0].material
    assert str(rt.classOf(mat))=='GTA_Mtl' and M.texture_stem(mat)=='body'
    settings._STATE['import_material_type']='STANDARD'
    assert str(rt.classOf(M.create_import_material('test_standard'))) in ('Standardmaterial','Standard')
    settings._STATE['import_material_type']='GTA'
    from inu_max.adapter import scene_build as B
    from types import SimpleNamespace
    md=SimpleNamespace(name='imported',color=(40,80,120,200),texture='body',props={'ambient':.6,'export_env_map':True,'env_map_tex':'env','env_map_coef':.3})
    imported=B._material(md,{'body':'C:/textures/body.dds','env':'C:/textures/env.tga'},0)
    assert str(rt.classOf(imported))=='GTA_Mtl'
    assert str(imported.colormap.fileName).replace('\\','/')=='C:/textures/body.dds'
    assert str(imported.reflectionmap.fileName).replace('\\','/')=='C:/textures/env.tga'
    assert abs(M.color(imported)[3]-200/255)<.001
    from inu_max.ui.panel import INUToolsPanel
    from inu_max.qt import QtWidgets
    panel=INUToolsPanel(mode='dff')
    choices=[w for w in panel.findChildren(QtWidgets.QComboBox) if w.findData('GTA')>=0]
    assert len(choices)==1
    choices[0].setCurrentIndex(choices[0].findData('STANDARD'))
    assert settings.get('import_material_type')=='STANDARD'
    choices[0].setCurrentIndex(choices[0].findData('GTA'))
    assert settings.get('import_material_type')=='GTA'
    panel.close()
    from inu_max.adapter import scene_read as R
    from inu_max.ops import dff_read
    from inu_max.ops.col_build import surface_of
    from inu_gta_core.col import ColModel, ColFace, ColSphere, ColBox, Surface, Vec3
    M.ensure_materials()
    expected=dict(col_mat_index=9,col_flags=7,col_brightness=125,col_day_light=3,col_night_light=11)
    colmat=M.create_collision_material('surface_check',expected)
    assert str(rt.classOf(colmat))=='GTA_COLSurface'
    assert surface_of(M.props(colmat))==(9,7,125,179)
    colmat.surface=178; colmat.u2=17; colmat.u1=180
    assert surface_of(M.props(colmat))==(178,17,125,180)
    M.set_props(colmat,dict(col_mat_index=9,col_flags=7,col_day_light=3))
    shamat=M.create_collision_material('shadow_check',expected,shadow=True)
    assert str(rt.classOf(shamat))=='GTA_COLShadow'
    assert int(shamat.u2)==125
    model=ColModel(model_name='material_probe',version=3)
    model.vertices=[Vec3(0,0,0),Vec3(1,0,0),Vec3(0,1,0)]
    model.faces=[ColFace(0,1,2,Surface(9,7,125,179))]
    model.shadow_vertices=list(model.vertices)
    model.shadow_faces=[ColFace(0,1,2,Surface(9,7,125,179))]
    model.spheres=[ColSphere(Vec3(0,0,1),.5,Surface(9,7,125,179))]
    model.boxes=[ColBox(Vec3(-1,-1,-1),Vec3(1,1,1),Surface(9,7,125,179))]
    meshes,prims=dff_read.col_models([model])
    B._ensure()
    nodes=B.build_collision(meshes,prims)
    assert len(nodes)==4
    assert str(rt.classOf(nodes[0].material))=='GTA_COLSurface'
    assert str(rt.classOf(nodes[1].material))=='GTA_COLShadow'
    assert R.col_mesh(nodes[0]).surfaces==[(9,7,125,179)]
    assert R.col_mesh(nodes[1]).shadow
    for node in nodes[2:]:
        assert R.col_prim_data(node,version=3).surface==(9,7,125,179)
    rt.saveMaxFile(str(scene),quiet=True)
    rt.resetMaxFile(rt.Name('noPrompt'))
    rt.loadMaxFile(str(scene),quiet=True)
    colnode=rt.getNodeByName('material_probe_COL')
    assert str(rt.classOf(colnode.material))=='GTA_COLSurface'
    assert surface_of(M.props(colnode.material))==(9,7,125,179)
    shanode=rt.getNodeByName('material_probe_sha')
    assert str(rt.classOf(shanode.material))=='GTA_COLShadow'
    assert surface_of(M.props(shanode.material))==(9,7,125,179)
    from inu_max.ops.dff_build import MatData,build_material
    from inu_gta_core.dff import DKNormalMapEffect,DffMaterial,DffTexture
    dkplan=dff_read.material(DffMaterial(dk_normal_map=DKNormalMapEffect(DffTexture(name='body_normal'),.65,DffTexture(name='env'))))
    dkmat=B._material(dkplan,{'body_normal':'C:/textures/body_normal.dds','env':'C:/textures/env.tga'},0)
    assert int(dkmat.matEffect)==6
    assert str(dkmat.dkpNmap.fileName).replace('\\','/')=='C:/textures/body_normal.dds'
    assert abs(float(dkmat.dkpRAmount)-.65)<.001
    dkmat.dkpRAmount=.8
    dkwrite=build_material(MatData(props=M.props(dkmat)))
    assert dkwrite.dk_normal_map.normal_texture.name=='body_normal'
    assert abs(dkwrite.dk_normal_map.reflection_amount-.8)<.001
    from inu_max import i18n
    from inu_max.i18n_native import localize_material
    settings._STATE['ui_language']='RU'
    before=M.props(dkmat)
    assert localize_material(dkmat)
    assert str(dkmat.params.infodkN.caption)=='Нормали'
    assert int(dkmat.matEffect)==6 and M.props(dkmat)==before
    assert localize_material(colnode.material)
    assert str(colnode.material.params.msur.caption)=='Поверхность: '
    assert surface_of(M.props(colnode.material))==(9,7,125,179)
    settings._STATE['ui_language']='EN'
    assert localize_material(dkmat)
    assert str(dkmat.params.infodkN.caption)=='Normal Map'
    assert int(dkmat.matEffect)==6 and M.props(dkmat)==before
    try:
        result['rollout_probe']=str(dkmat.params)
    except Exception as error:
        result['rollout_probe']=str(error)
    result['success']=True
except Exception:
    result['success']=False
    result['error']=traceback.format_exc()
(ROOT/'dev/tests/e2e/material_runtime_result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
