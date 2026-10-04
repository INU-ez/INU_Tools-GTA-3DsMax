import unittest
from inu_gta_core.dff import DffClump, DffFrame, DffGeometry, DffAtomic, HAnimData, HAnimBone, SkinData
from inu_max.ops.dff_read import plan
from inu_max.ops.dff_build import world_matrices, _inv, _mul, build_skin, ExportNode, MeshData


def tm(x, y=0):
    return [[1,0,0,0],[0,1,0,0],[0,0,1,0],[x,y,0,1]]


class PedBindPoseTests(unittest.TestCase):
    def fixture(self):
        frames = [DffFrame(name='root', position=(10,0,0)),
                  DffFrame(name='pelvis', parent=0, position=(99,0,0),
                           hanim=HAnimData(bone_id=0, bones=[HAnimBone(bone_id=1,index=1),HAnimBone(bone_id=0,index=0)])),
                  DffFrame(name='child',parent=1,position=(99,0,0),hanim=HAnimData(bone_id=1))]
        skin=SkinData(num_bones=2,bone_matrices=[tm(-2),tm(-2,-3)],
                      bone_indices=[(1,0,0,0)],bone_weights=[(1,0,0,0)])
        return DffClump(frames=frames,geometries=[DffGeometry(vertices=[(0,0,0)],skin=skin)],
                        atomics=[DffAtomic(frame_index=0,geometry_index=0)])

    def test_bind_pose_overrides_bad_frame_positions_and_uses_palette_indices(self):
        p=plan(self.fixture(),'ped',vanilla=False)
        worlds=world_matrices(p.nodes)
        self.assertEqual(worlds[1][3][:3],[12,0,0])
        self.assertEqual(worlds[2][3][:3],[12,3,0])
        self.assertEqual(worlds[-1][3][:3],[10,0,0])
        self.assertEqual(p.nodes[-1].mesh.skin,[[(2,1.0)]])

    def test_export_reconstructs_inverse_bind_matrices(self):
        c=self.fixture();p=plan(c,'ped',vanilla=False)
        nodes=[ExportNode(name=n.name,parent=n.parent,transform=n.transform,
                          bone_id=n.props.get('bone_id')) for n in p.nodes]
        nodes[-1].mesh=MeshData(skin=[[('child',1)]])
        skin=build_skin(len(nodes)-1,nodes,[0],[1,2],world_matrices(nodes))
        self.assertEqual(skin.bone_matrices,c.geometries[0].skin.bone_matrices)

    def test_unskinned_frame_transforms_are_unchanged(self):
        c=self.fixture();c.geometries[0].skin=None
        p=plan(c,'object',vanilla=False)
        self.assertEqual(world_matrices(p.nodes)[2][3][:3],[208,0,0])


class KamsBoneDisplayTests(unittest.TestCase):
    def test_skeleton_uses_kams_dummy_links_not_bone_geometry(self):
        from inu_max.adapter.scene_build import _MXS
        constructor = _MXS.split('fn inuMakeBone boneName = (',1)[1].split('global inuSetChannel',1)[0]
        self.assertIn('dummy name:boneName boxsize:[0,0,0] wirecolor:yellow showlinks:true', constructor)
        self.assertIn('bn.showLinksOnly = true',constructor)
        self.assertNotIn('BoneSys.createBone',constructor)
        self.assertNotIn('objectOffsetRot',constructor)

    def test_bone_factory_returns_dummy_link_node(self):
        from unittest.mock import Mock, patch
        from inu_max.adapter import scene_build
        runtime=Mock()
        with patch.object(scene_build,'_rt',return_value=runtime):
            self.assertIs(scene_build._bone('pelvis'),runtime.inuMakeBone.return_value)
        runtime.inuMakeBone.assert_called_once_with('pelvis')
