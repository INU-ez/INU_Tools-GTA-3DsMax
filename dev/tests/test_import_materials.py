import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from inu_max.adapter import material as M
from inu_max import settings

class ImportMaterialTests(unittest.TestCase):
    def runtime(self):
        return SimpleNamespace(classOf=lambda mat:'INU_GTA_Mtl',getAppData=lambda *args:json.dumps({'uv_anim_write':True,'reflection_scale_x':2}),setAppData=lambda *args:None,Bitmaptexture=lambda **kw:SimpleNamespace(**kw))

    def material(self):
        values={field:False if key.startswith('export_') else 1 for key,field in M._KAM_FIELDS.items()}
        values.update({field:None for field in M._KAM_MAPS.values()})
        return SimpleNamespace(**values,matEffect=1,colhprIdx=1,colormap=None)

    def test_native_edits_override_saved_values_and_keep_other_metadata(self):
        mat=self.material(); mat.amb=.4
        with patch.object(M,'_rt',return_value=self.runtime()):
            props=M.props(mat)
        self.assertEqual(props['ambient'],.4)
        self.assertTrue(props['uv_anim_write'])
        self.assertEqual(props['reflection_scale_x'],2)

    def test_surface_and_effect_units(self):
        mat=self.material()
        with patch.object(M,'_rt',return_value=self.runtime()):
            M.set_props(mat,dict(env_map_coef=.2,specular_level=.8,dual_tex_src_blend='5',export_env_map=True,export_bump_map=True))
            props=M.props(mat)
        self.assertEqual(mat.Reflection,20)
        self.assertEqual(mat.spec_power,80)
        self.assertEqual(mat.matEffect,4)
        self.assertEqual(props['dual_tex_src_blend'],'5')
        self.assertAlmostEqual(props['env_map_coef'],.2)

    def test_vehicle_slot_roundtrip(self):
        mat=self.material()
        with patch.object(M,'_rt',return_value=self.runtime()):
            M.set_props(mat,{'vehicle_color_slot':'FOURTH'})
            self.assertEqual(M.props(mat)['vehicle_color_slot'],'FOURTH')
        self.assertEqual(mat.colhprIdx,5)

    def test_effect_image_path_is_resolved(self):
        mat=self.material(); mat.reflectionmap=SimpleNamespace(fileName='env.png')
        with patch.object(M,'_rt',return_value=self.runtime()):
            M.resolve_effect_maps(mat,{'env':'C:/textures/env.dds'})
        self.assertEqual(mat.reflectionmap.fileName,'C:/textures/env.dds')

    def test_diffuse_uses_scripted_field(self):
        mat=self.material(); texture=object()
        with patch.object(M,'_rt',return_value=self.runtime()):
            M.set_diffuse(mat,texture)
            self.assertIs(M.base_diffuse(mat),texture)
        self.assertTrue(mat.use_colormap)

    def test_default_import_is_standard(self):
        rt=SimpleNamespace(StandardMaterial=lambda **kw:('standard',kw['name']))
        with patch.object(settings,'get',return_value='STANDARD'),patch.object(M,'_rt',return_value=rt):
            self.assertEqual(M.create_import_material('test'),('standard','test'))

class CollisionMaterialTests(unittest.TestCase):
    def runtime(self,shadow=False):
        cls='INU_GTA_COLShadow' if shadow else 'INU_GTA_COLSurface'
        return SimpleNamespace(classOf=lambda mat:cls,getAppData=lambda *args:json.dumps({'col_source_game':'SA','col_mat_index':99}),setAppData=lambda *args:None)

    def material(self):
        return SimpleNamespace(surface=9,flags=7,brightness=125,dayLight=3,nightLight=11)

    def test_native_collision_fields_override_metadata(self):
        from inu_max.ops.col_build import surface_of
        with patch.object(M,'_rt',return_value=self.runtime()):
            values=M.props(self.material())
        self.assertEqual(surface_of(values),(9,7,125,179))
        self.assertEqual(values['col_source_game'],'SA')

    def test_panel_updates_native_collision_fields(self):
        mat=self.material()
        with patch.object(M,'_rt',return_value=self.runtime()):
            M.set_props(mat,{'col_mat_index':178,'col_flags':42,'col_brightness':200,'col_night_light':8})
        self.assertEqual((mat.surface,mat.flags,mat.brightness,mat.nightLight),(178,42,200,8))

    def test_collision_fields_are_clamped(self):
        mat=self.material()
        with patch.object(M,'_rt',return_value=self.runtime()):
            M.set_props(mat,dict(col_mat_index=300,col_flags=-1,col_day_light=20,col_night_light=-2))
        self.assertEqual((mat.surface,mat.flags,mat.dayLight,mat.nightLight),(255,0,15,0))

    def test_shadow_keeps_bytes_for_export(self):
        from inu_max.ops.col_build import surface_of
        mat=self.material()
        with patch.object(M,'_rt',return_value=self.runtime(shadow=True)):
            self.assertTrue(M.is_col(mat))
            self.assertFalse(M.is_gta(mat))
            self.assertEqual(surface_of(M.props(mat)),(9,7,125,179))

    def test_collision_color(self):
        mat=self.material();mat.previewColor=SimpleNamespace(r=60,g=60,b=60)
        with patch.object(M,'_rt',return_value=self.runtime()):
            self.assertEqual(M.color(mat)[3],1)
        with patch.object(M,'_rt',return_value=self.runtime(shadow=True)):
            self.assertAlmostEqual(M.color(mat)[3],125/255)

    def test_standard_is_not_collision_material(self):
        with patch.object(M,'_rt',return_value=SimpleNamespace(classOf=lambda mat:'Standardmaterial')):
            self.assertFalse(M.is_col(object()))

class OriginalKamTests(unittest.TestCase):
    def runtime(self,cls):
        return SimpleNamespace(classOf=lambda mat:cls,getAppData=lambda *args:'{}',setAppData=lambda *args:None)

    def test_original_col_surface_bytes(self):
        mat=SimpleNamespace(surface=9,u2=7,part=125,u1=179)
        with patch.object(M,'_rt',return_value=self.runtime('GTA_COLSurface')):
            from inu_max.ops.col_build import surface_of
            self.assertEqual(surface_of(M.props(mat)),(9,7,125,179))
            M.set_props(mat,{'col_day_light':4,'col_flags':17})
        self.assertEqual((mat.u1,mat.u2),(180,17))

    def test_original_shadow_bytes(self):
        mat=SimpleNamespace(u1=9,u2=125)
        with patch.object(M,'_rt',return_value=self.runtime('GTA_COLShadow')):
            self.assertEqual(M.props(mat)['col_brightness'],125)
            M.set_props(mat,{'col_brightness':200})
        self.assertEqual(mat.u2,200)

    def test_original_surface_part_minus_one_is_byte_255(self):
        mat=SimpleNamespace(surface=9,u2=7,part=-1,u1=187)
        with patch.object(M,'_rt',return_value=self.runtime('GTA_COLSurface')):
            self.assertEqual(M.props(mat)['col_brightness'],255)

    def test_original_parameter_set_is_bundled(self):
        from pathlib import Path
        import re
        source=(Path(M.__file__).parents[1]/'GTA_Material.ms').read_text(encoding='utf-8')
        fields=set(re.findall(r'^\s*(\w+)\s+type:',source,re.M))
        self.assertTrue({'specular','spec_alpha','dkpNmap','dkpRmap','dkpRAmount','use_reflectionmap','use_specularmap'}<=fields)
        self.assertIn('classID:#(0x48238272, 0x48206285)',source)
