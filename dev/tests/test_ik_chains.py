import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from inu_max.ops import anim_tools as T

class IKChainTests(unittest.TestCase):
    def nodes(self, ids=True):
        arm=NS(name='  L   UpperArm',parent=None,bid=32 if ids else -1)
        elbow=NS(name='elbow',parent=arm,bid=33 if ids else -1)
        hand=NS(name=' L Hand ',parent=elbow,bid=34 if ids else -1)
        return [arm,elbow,hand]

    def test_whitespace_names_find_chain(self):
        nodes=self.nodes(False)
        with patch.object(T.S,'get_field',side_effect=lambda n,k,d:n.bid):
            self.assertEqual(T._ik_pairs(nodes),[('L_Arm',nodes[0],nodes[2])])

    def test_ids_find_renamed_bones(self):
        nodes=self.nodes()
        for i,n in enumerate(nodes):n.name='custom'+str(i)
        with patch.object(T.S,'get_field',side_effect=lambda n,k,d:n.bid):
            self.assertEqual(len(T._ik_pairs(nodes)),1)

    def test_wrong_hierarchy_is_rejected(self):
        nodes=self.nodes();nodes[2].parent=None
        with patch.object(T.S,'get_field',side_effect=lambda n,k,d:n.bid):
            self.assertEqual(T._ik_pairs(nodes),[])

    def test_no_chains_does_not_create_backups(self):
        from unittest.mock import Mock
        runtime=Mock()
        with patch.object(T.S,'_rt',return_value=runtime),patch.object(T,'_rig'),patch.object(T,'_bones',return_value=[]):
            with self.assertRaisesRegex(ValueError,'No standard SA'):T.add_ik_rig()
        runtime.Point.assert_not_called()
