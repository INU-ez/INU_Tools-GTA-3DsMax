"""Blender IK data parity, chain geometry and Max display/floor routing."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import unittest
from inu_max.ops import ik_rig as IK


def node(name,bid,parent=None):
    return NS(name=name,bid=bid,parent=parent)


class FullRigTests(unittest.TestCase):
    def test_scene_references_use_node_handles(self):
        # maxOps.getNodeByHandle cannot resolve an animatable handle.
        with patch.object(IK.S,'_rt',side_effect=AssertionError('Wrong handle API')):
            self.assertEqual(IK._handle(NS(handle=42)),42)

    def skeleton(self):
        pelvis=node('renamed pelvis',1)
        root=node('renamed root',0)
        pelvis.parent=root
        nodes=[root,pelvis]
        for side,arm,leg in [('L',32,41),('R',22,51)]:
            for label,ids in [('arm',(arm,arm+1,arm+2)),('leg',(leg,leg+1,leg+2))]:
                parent=pelvis
                for i,bid in enumerate(ids):
                    parent=node('custom '+side+label+str(i),bid,parent)
                    nodes.append(parent)
        nodes.extend(node('renamed'+str(bid),bid,pelvis) for bid in [3,5,21,31])
        return nodes

    def test_full_ped_has_thirteen_controls(self):
        bones=self.skeleton()
        with patch.object(IK.S,'get_field',side_effect=lambda n,k,d:n.bid):
            chains,rot,root=IK.specification(bones)
        self.assertEqual(len(chains),4)
        self.assertEqual(len(rot),4)
        self.assertEqual(root.bid,1)
        self.assertEqual(len(chains)*2+len(rot)+1,13)

    def test_root_motion_selects_root_instead_of_pelvis(self):
        with patch.object(IK.S,'get_field',side_effect=lambda n,k,d:n.bid):
            self.assertEqual(IK.specification(self.skeleton(),True)[2].bid,0)

    def test_invalid_chain_is_rejected_before_scene_changes(self):
        bones=self.skeleton();bones[3].parent=None
        with patch.object(IK.S,'get_field',side_effect=lambda n,k,d:n.bid):
            with self.assertRaisesRegex(ValueError,'hierarchy'):IK.specification(bones)

    def test_pole_stays_in_bend_plane(self):
        self.assertEqual(IK.pole_position((0,0,0),(1,1,0),(2,0,0)),(1,2,0))
        # Rotate the character into another plane: pole must follow it.
        self.assertEqual(IK.pole_position((0,0,0),(0,1,1),(0,2,0)),(0,1,2))

    def test_straight_chain_uses_safe_perpendicular_fallback(self):
        pole=IK.pole_position((0,0,0),(1,0,0),(2,0,0),(1,0,0))
        self.assertTrue(all(math.isfinite(v) for v in pole))
        self.assertGreater(sum(v*v for v in pole[1:]),0)
        with self.assertRaises(ValueError):IK.pole_position((0,0,0),(1,1,0),(0,0,0))

    def test_display_settings_apply_to_each_control_group(self):
        boxes=[NS(kind=k) for k in IK.SIZES]
        values={'ik_size':2,'ik_color':[1,0,.5,1],'ik_show_pole':False}
        rt=Mock();rt.Color.side_effect=lambda *v:v
        with patch.object(IK.S,'_rt',return_value=rt),patch.object(IK,'controls',return_value=boxes), \
             patch.object(IK.S,'get_field',side_effect=lambda n,k,d:n.kind), \
             patch.object(IK.settings,'get',side_effect=lambda k,d:values.get(k,d)):
            IK.update_display()
        self.assertEqual([b.size for b in boxes],[.4,.32,.36,.6])
        self.assertEqual([b.isHidden for b in boxes],[False,True,False,False])
        self.assertEqual(boxes[0].wirecolor,(255,0,127.5))

    def test_floor_patches_only_foot_controls(self):
        ground=NS(ground=True);foot=NS(foot=True);hand=NS(foot=False)
        rt=Mock();rt.objects=[ground]
        def fields(n,k,d):return getattr(n,'ground' if k=='ik_ground' else 'foot',False)
        with patch.object(IK.S,'_rt',return_value=rt),patch.object(IK.S,'get_field',side_effect=fields), \
             patch.object(IK,'controls',return_value=[foot,hand]),patch.object(IK.settings,'get',return_value=.07):
            IK.patch_floor()
        rt.inuIKFootFloor.assert_called_once_with(foot,ground,.07)

    def test_data_file_retains_blender_categories_and_rest_pose(self):
        self.assertEqual([n for n,_ in IK.DATA['_SA_ROT_BONES']],['spine1','R_shoulder','L_shoulder','head'])
        self.assertIn(' R Calf',IK.DATA['_REST_POSE'])
        self.assertEqual(IK.SIZES,{'chain':.20,'pole':.16,'rot':.18,'root':.30})
