import struct
import unittest
from inu_gta_core import dff as D
from inu_gta_core.rwbinary import BinaryReader
from inu_max.ops.dff_build import MatData,build_material

class DKMaterialTests(unittest.TestCase):
    def parse(self,mat):
        data=mat.to_bytes(0x1803ffff,D.GTA_SA_VERSION)
        _,size,_=struct.unpack_from('<III',data)
        return D._read_material_chunk(BinaryReader(data,12),size,D.GTA_SA_VERSION)

    def test_type49_matches_kams_layout(self):
        normal=D.DffTexture(name='normal')
        reflection=D.DffTexture(name='env')
        effect=D.DKNormalMapEffect(normal,.7,reflection)
        expected=struct.pack('<I',49)+normal.to_bytes(0x1803ffff)+struct.pack('<f',.7)+reflection.to_bytes(0x1803ffff)
        data=effect.to_bytes(0x1803ffff)
        self.assertEqual(struct.unpack_from('<III',data),(0x133,len(expected),0x1803ffff))
        self.assertEqual(data[12:],expected)

    def test_type49_material_roundtrip(self):
        mat=D.DffMaterial(dk_normal_map=D.DKNormalMapEffect(D.DffTexture(name='normal'),.7,D.DffTexture(name='env')))
        parsed=self.parse(mat).dk_normal_map
        self.assertEqual(parsed.normal_texture.name,'normal')
        self.assertEqual(parsed.reflection_texture.name,'env')
        self.assertAlmostEqual(parsed.reflection_amount,.7,places=6)

    def test_older_type1_roundtrip(self):
        effect=D.DKNormalMapEffect(D.DffTexture(name='normal'),effect_type=1)
        parsed=self.parse(D.DffMaterial(dk_normal_map=effect)).dk_normal_map
        self.assertEqual(parsed.effect_type,1)
        self.assertEqual(parsed.normal_texture.name,'normal')
        self.assertIsNone(parsed.reflection_texture)

    def test_no_reflection_texture(self):
        parsed=self.parse(D.DffMaterial(dk_normal_map=D.DKNormalMapEffect(D.DffTexture(name='normal'))))
        self.assertEqual(parsed.dk_normal_map.reflection_texture.name,'')

    def test_export_adapter_creates_dk_effect(self):
        mat=build_material(MatData(props=dict(export_dk_normal_map=True,dk_normal_texture='body_normal.dds',dk_reflection_texture='env.tga',dk_reflection_amount=.6)))
        parsed=self.parse(mat).dk_normal_map
        self.assertEqual(parsed.normal_texture.name,'body_normal')
        self.assertEqual(parsed.reflection_texture.name,'env')
        self.assertAlmostEqual(parsed.reflection_amount,.6,places=6)

    def test_missing_normal_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'normal texture'):
            build_material(MatData(props={'export_dk_normal_map':True}))

    def test_truncated_dk_plugin_is_rejected(self):
        with self.assertRaises(ValueError):
            D._read_dk_plugin(BinaryReader(struct.pack('<I',49)),4)

    def test_explicit_reflection_is_serialized(self):
        mat=D.DffMaterial(reflection=D.ReflectionMaterial(.1,.2,.3,.4,.5))
        parsed=self.parse(mat)
        self.assertIsNotNone(parsed.reflection)
        self.assertAlmostEqual(parsed.reflection.intensity,.5)

    def test_dk_atomic_uses_kams_right_to_render(self):
        mat=D.DffMaterial(dk_normal_map=D.DKNormalMapEffect(D.DffTexture(name='normal')))
        geom=D.DffGeometry(materials=[mat])
        clump=D.DffClump(frames=[D.DffFrame()],geometries=[geom],atomics=[D.DffAtomic(frame_index=0,geometry_index=0)])
        data=clump.to_bytes()
        self.assertIn(struct.pack('<III',0x1f,8,0x1803ffff)+struct.pack('<II',0x133,1),data)
        self.assertEqual(D.read_dff(data).geometries[0].materials[0].dk_normal_map.normal_texture.name,'normal')
