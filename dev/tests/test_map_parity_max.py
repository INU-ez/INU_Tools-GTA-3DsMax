"""Max bridges for multi-mesh placements, IDE matching, LOD names and ID presets."""
import contextlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from inu_max.ops import map_link as ML, id_manager_ops as IM
from inu_max import id_presets as IP


class Rec:
    def __init__(self, handle, name, kind='DFF', base=None, pos=(0,0,0), quat=(0,0,0,1), **props):
        self.handle, self.name, self.top, self.depth = handle, name, 1, 1
        self.node = SimpleNamespace(pos=pos, quat=quat, inode=SimpleNamespace(handle=handle))
        self.props, self.kind, self.base = props, kind, base or name
    def get(self, key, default): return self.props.get(key, default)
    def put(self, props): self.props.update(props)


def scene(recs):
    sc = ML.Scene(recs)
    sc._types = {r.handle: (r.kind, r.base) for r in recs}
    sc.LS = SimpleNamespace(world=lambda n: (n.pos, n.quat, (1,1,1)))
    return sc


@contextlib.contextmanager
def options(game='SA', **values):
    values['game'] = game
    with patch.object(IM.settings, 'get', side_effect=lambda k,d=None: values.get(k,d)):
        yield


class PlacementTests(unittest.TestCase):
    def test_parts_group_by_spot_not_parent_and_q_sign(self):
        a = Rec(1,'bar_L0',model_id=500,atomic_order=0)
        b = Rec(2,'bar_dam',model_id=500,quat=(0,0,0,-1))
        c = Rec(3,'bar_L0',model_id=500,pos=(1,0,0))
        sc = scene([a,b,c])
        self.assertIs(sc.main_of(b), a)
        self.assertIs(sc.main_of(c), c)
        self.assertEqual(sc.model_name(b),'bar')

    def test_restore_moves_every_part_of_the_placement(self):
        from inu_gta_core.ipl import IplInstance
        a=Rec(1,'house_L0',model_id=500)
        b=Rec(2,'house_dam',model_id=500)
        sc=scene([a,b])
        with patch('inu_max.adapter.link_scene.set_world') as move:
            ML.apply_inst(a,IplInstance(model_id=500,model_name='house',pos_x=5),sc=sc)
        self.assertEqual([call.args[0] for call in move.call_args_list],[a.node,b.node])
        self.assertTrue(all(call.args[1][9:]==[5,0,0] for call in move.call_args_list))

    def test_two_original_rows_at_same_spot_remain_separate(self):
        a = Rec(1,'bar_L0',model_id=500,ipl_uuid='a',ipl_owner=1)
        b = Rec(2,'bar_L0',model_id=500,ipl_uuid='b',ipl_owner=2)
        sc = scene([a,b])
        self.assertIs(sc.main_of(a),a)
        self.assertIs(sc.main_of(b),b)

    def test_valid_stamp_survives_removal_of_other_parts(self):
        a=Rec(1,'bar_dam',model_id=500,ide_last_name='original',ide_last_model_id=500)
        sc=scene([a])
        self.assertEqual(sc.model_name(a),'original')
        a.props['model_id']=501
        sc.reset_copies()
        self.assertEqual(sc.model_name(a),'bar')


class IdeTests(unittest.TestCase):
    def test_current_id_resolves_same_name_in_two_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            files=[]
            for mid in (500,501):
                p=Path(tmp)/('%s.ide'%mid)
                p.write_text('objs\n%d, house, walls, 100, 0\nend\n'%mid)
                files.append(str(p))
            r=Rec(1,'house',model_id=501)
            linked,skipped,_=ML.ide_sync_from_file(scene([r]),[r],files)
            self.assertEqual((linked,skipped),(1,0))
            self.assertEqual(r.get('model_id',0),501)
            self.assertEqual(ML.norm(r.get('ide_target_file','')),ML.norm(files[1]))

    def test_missing_own_file_does_not_change_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            other=Path(tmp)/'other.ide'
            other.write_text('objs\n501, house, walls, 100, 0\nend\n')
            r=Rec(1,'house',model_id=500,ide_linked=True,ide_target_file=str(Path(tmp)/'missing.ide'))
            linked,skipped,rep=ML.ide_sync_from_file(scene([r]),[r],[str(other)])
            self.assertEqual((linked,skipped),(0,1))
            self.assertEqual(r.get('model_id',0),500)
            self.assertIn('links of 1 models kept',rep.messages[0][1])

    def test_own_file_wins_and_stale_link_does_not_undo_new_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            own=Path(tmp)/'own.ide'; other=Path(tmp)/'other.ide'
            own.write_text('objs\n500, house, first, 100, 0\nend\n')
            other.write_text('objs\n501, house, second, 200, 0\nend\n')
            r=Rec(1,'house',model_id=500,ide_linked=True,ide_target_file=str(own),
                  ide_last_model_id=500,ide_last_name='house')
            sc=scene([r])
            ML.ide_sync_from_file(sc,[r],[str(other),str(own)])
            self.assertEqual(r.get('txd_name',''),'first')
            r.props['model_id']=501
            ML.ide_sync_from_file(sc,[r],[str(other),str(own)])
            self.assertEqual(r.get('txd_name',''),'second')

    def test_add_warns_about_other_ide_and_keeps_original_bytes(self):
        with tempfile.TemporaryDirectory() as tmp, options():
            own=Path(tmp)/'own.ide'; new=Path(tmp)/'new.ide'
            own.write_text('objs\n500, house, walls, 100, 0\nend\n')
            new.write_text('objs\nend\n')
            before=own.read_bytes()
            r=Rec(1,'house',model_id=500,ide_linked=True,ide_target_file=str(own),
                  ide_last_model_id=500,ide_last_name='house')
            rep=ML.ide_write(scene([r]),[r],picked=str(new))
            self.assertEqual(own.read_bytes(),before)
            self.assertIn('house',new.read_text())
            self.assertTrue(any('another IDE' in t for _,t in rep.messages))


class LodTests(unittest.TestCase):
    def test_new_names_and_preserved_import_names(self):
        for game in ('III','VC'):
            with options(game):
                hd=Rec(1,'house',model_id=500)
                lod=Rec(2,'house_LOD',kind='LOD',base='house',model_id=501)
                sc=scene([hd,lod])
                self.assertEqual(ML.lod_model_name(lod,'house',hd='house',sc=sc),'LODse')
                lod.props['ide_last_name']='LODhouse'
                self.assertEqual(ML.lod_model_name(lod,'house',hd='house',sc=sc),'LODhouse')
                self.assertIn('will not pair',ML.lod_name_note(lod,'LODhouse','house',sc=sc))
        with options():
            lod=Rec(1,'melody_hall_LOD',kind='LOD',base='melody_hall')
            self.assertEqual(ML.lod_model_name(lod,'melody_hall'),'LODmelody_hall')

    def test_tail_pair_requires_correct_owner_and_placement(self):
        with options('III'):
            first=Rec(1,'lhsbackbit',model_id=1410)
            second=Rec(2,'havbackbit',model_id=1451)
            lod=Rec(3,'lodbackbit',kind='LOD',base='backbit',model_id=1411)
            sc=scene([first,second,lod]); idx=ML.LodIndex(sc)
            self.assertIs(idx.partner(first),lod)
            self.assertIsNone(idx.partner(second))
            lod.node.pos=(10,0,0)
            self.assertIsNone(idx.partner(first))

    def test_taken_game_name_falls_back_and_warns(self):
        with options('VC'):
            hd=Rec(1,'dt_house1',model_id=600)
            foreign=Rec(2,'ne_house1',model_id=500)
            lod=Rec(3,'dt_house1_LOD',kind='LOD',base='dt_house1')
            sc=scene([hd,foreign,lod])
            name=ML.lod_model_name(lod,'dt_house1',hd='dt_house1',sc=sc)
            self.assertEqual(name,'LODdt_house1')
            self.assertIn('taken',ML.lod_name_note(lod,name,'dt_house1',sc=sc))

    def test_vc_ide_tail_pair_is_limited_to_own_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'own.ide'; p.write_text('objs\n500, ap_tower, walls, 100, 0\n501, LODtower, walls, 500, 0\nend\n')
            hd=Rec(1,'ap_tower',model_id=500,ide_linked=True,ide_target_file=str(p))
            with options('VC'):
                self.assertEqual(ML.IdeLods().find(hd,'ap_tower')[:2],(501,'LODtower'))


class IdTests(unittest.TestCase):
    def test_selected_lod_is_ordered_after_model(self):
        a=Rec(1,'house',model_id=500,lod_object=2)
        b=Rec(2,'house_LOD',kind='LOD',base='house')
        sc=scene([a,b])
        with options():
            self.assertEqual(IM._ordered_keys(sc,[b,a],ML.LodIndex(sc),True), [('DFF','house'),('LOD','LODhouse'.lower())])

    def test_assign_reuses_own_ide_lod_id_even_outside_preset(self):
        with tempfile.TemporaryDirectory() as tmp, options(), patch.object(IM,'active',return_value='test'), \
             patch.object(IP,'presets_dir',return_value=tmp):
            p=Path(tmp)/'own.ide';p.write_text('objs\n501, LODhouse, walls, 500, 0\nend\n')
            IP.save('test',[(502,None)])
            hd=Rec(1,'house',model_id=500,lod_object=2)
            lod=Rec(2,'house_LOD001',kind='LOD',base='house',ide_linked=True,
                    ide_target_file=str(p),ide_last_model_id=501,ide_last_name='LODhouse')
            IM.assign_models(scene([hd,lod]),[hd])
            self.assertEqual(lod.get('model_id',0),501)

    def test_lod_copy_with_hd_id_does_not_give_that_id_to_original(self):
        with tempfile.TemporaryDirectory() as tmp, options(), patch.object(IM,'active',return_value='test'), \
             patch.object(IP,'presets_dir',return_value=tmp):
            IP.save('test',[(501,None),(502,None)])
            hd=Rec(1,'house',model_id=500,lod_object=2)
            lod=Rec(2,'house_LOD',kind='LOD',base='house')
            clone=Rec(3,'house_LOD001',kind='LOD',base='house',model_id=500)
            IM.assign_models(scene([hd,lod,clone]),[hd])
            self.assertEqual(lod.get('model_id',0),501)
            self.assertEqual(clone.get('model_id',0),501)
            self.assertEqual(hd.get('model_id',0),500)

    def test_from_id_is_repeatable_and_updates_parts_and_own_col(self):
        with tempfile.TemporaryDirectory() as tmp, options(), patch.object(IM,'active',return_value='test'), \
             patch.object(IP,'presets_dir',return_value=tmp):
            p=Path(tmp)/'own.ide'; p.write_text('objs\n500, house, walls, 100, 0\nend\n')
            IP.save('test',[(500,'house'),(501,None)])
            a=Rec(1,'house_L0',base='house_L0',model_id=500,ide_linked=True,ide_target_file=str(p),ide_last_model_id=500)
            b=Rec(2,'house_dam',model_id=500)
            col=Rec(3,'house_COL',kind='COL',base='house',model_id=500,type='COL')
            sc=scene([a,b,col])
            with patch.object(IM.ML,'Scene',return_value=sc), patch.object(IM,'_selected',return_value=[a.node]), \
                 patch.object(IM,'_undo',side_effect=lambda _:contextlib.nullcontext()):
                IM.id_manager_assign_from(500)
                IM.id_manager_assign_from(500)
            self.assertEqual([r.get('model_id',0) for r in sc.recs],[500,500,500])

    def test_foreign_ide_row_keeps_same_id_occupied(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(IP,'presets_dir',return_value=tmp), \
             patch.object(IM,'active',return_value='test'):
            own=Path(tmp)/'own.ide'; foreign=Path(tmp)/'foreign.ide'
            own.write_text('objs\n500, house, walls, 100, 0\nend\n')
            foreign.write_text('objs\n500, foreign, other, 100, 0\nend\n')
            IP.save('test',[(500,'house'),(501,None)])
            r=Rec(1,'house',model_id=500,ide_linked=True,ide_target_file=str(own),ide_last_model_id=500)
            sc=scene([r])
            with options(ide_sync_list=[str(foreign)]), patch.object(IM.ML,'Scene',return_value=sc), \
                 patch.object(IM,'_selected',return_value=[r.node]), \
                 patch.object(IM,'_undo',side_effect=lambda _:contextlib.nullcontext()):
                IM.id_manager_assign_from(500)
            self.assertEqual(r.get('model_id',0),501)

    def test_own_collision_does_not_block_assign_but_foreign_collision_does(self):
        for foreign, expected in ((False,500),(True,501)):
            with self.subTest(foreign=foreign), tempfile.TemporaryDirectory() as tmp, options(), \
                 patch.object(IP,'presets_dir',return_value=tmp), patch.object(IM,'active',return_value='test'):
                IP.save('test',[(500,None),(501,None)])
                model=Rec(1,'house')
                own=Rec(2,'house_COL',kind='COL',base='house',model_id=500,type='COL')
                recs=[model,own]
                if foreign:
                    recs.append(Rec(3,'foreign_COL',kind='COL',base='foreign',model_id=500,type='COL'))
                IM.assign_models(scene(recs),[model])
                self.assertEqual(model.get('model_id',0),expected)

    def test_game_ids_stay_protected_until_explicit_release(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(IP,'presets_dir',return_value=tmp), \
             patch.object(IM,'active',return_value='test'):
            IP.save('test',[(500,'vanilla'),(501,None)])
            IP.save_game_ids('test',{500})
            preset=IP.Preset('test'); preset.release(500)
            self.assertEqual(preset.allocate('own',set()),501)
            before=Path(IP.game_path('test')).read_bytes()
            self.assertIsNone(IM.id_manager_release(500,confirm=lambda *a:False))
            self.assertEqual(Path(IP.game_path('test')).read_bytes(),before)
            with patch.object(IM.ML,'Scene',return_value=scene([])), \
                 patch.object(IM,'_undo',side_effect=lambda _:contextlib.nullcontext()):
                IM.id_manager_release(500,confirm=lambda *a:True)
            self.assertNotIn(500,IP.game_ids('test'))
            self.assertTrue(IP.Preset('test').is_free(500))

    def test_visible_names_and_orphan_game_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(IP,'presets_dir',return_value=tmp):
            IP.save_game_ids('x',{500})
            self.assertTrue(IP.create('_x'))
            self.assertIn('x',IP.list_presets())
            self.assertEqual(IP.game_ids('x'),set())
            self.assertFalse(IP.create('...'))
            IP.save_game_ids('y',{501})
            self.assertTrue(IP.rename('x','y'))
            self.assertEqual(IP.game_ids('y'),set())

    def test_mark_game_counts_previously_free_rows(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(IP,'presets_dir',return_value=tmp):
            IP.save('test',[(500,None),(501,'old')])
            preset=IP.Preset('test')
            clashes,added=preset.mark_game({500:'vanilla',501:'old',502:'extra'})
            self.assertEqual(added,2)
            self.assertFalse(clashes)


class MapExportTests(unittest.TestCase):
    def test_layer_split_uses_top_ipl_layer(self):
        from inu_max.ops import map_export as ME
        class Layer:
            def __init__(self,name,parent=None): self.name,self.parent=name,parent
            def getParent(self): return self.parent
        node=SimpleNamespace(layer=Layer('LAn2_DFF',Layer('LAn2',Layer('0'))))
        self.assertEqual(ME._top_layer(node),'LAn2')
        node.layer=Layer('0')
        self.assertEqual(ME._top_layer(node),'unsorted')

    def test_copy_rows_use_first_lod_and_lowest_model_id(self):
        from inu_max.ops import map_export as ME
        a=Rec(1,'house',model_id=500,lod_object=3)
        b=Rec(2,'house',model_id=502,lod_object=4,pos=(10,0,0))
        first=Rec(3,'house_LOD',kind='LOD',base='house',model_id=501)
        copy=Rec(4,'house_LOD001',kind='LOD',base='house',model_id=503,pos=(10,0,0))
        sc=scene([a,b,first,copy])
        with options():
            rows,other,dup=ME._ipl_rows(sc,ML.LodIndex(sc),[a,b],False)
        self.assertEqual([r.model_id for r in rows],[500,500,501,501])
        self.assertEqual([r.lod_index for r in rows[:2]],[2,3])

    def test_shared_lod_at_same_spot_has_one_row(self):
        from inu_max.ops import map_export as ME
        a=Rec(1,'first',model_id=500,lod_object=3)
        b=Rec(2,'second',model_id=502,lod_object=3)
        lod=Rec(3,'shared_LOD',kind='LOD',base='shared',model_id=501)
        sc=scene([a,b,lod])
        with options():
            rows,_,_=ME._ipl_rows(sc,ML.LodIndex(sc),[a,b],False)
        self.assertEqual([r.model_id for r in rows],[500,502,501])
        self.assertEqual([r.lod_index for r in rows[:2]],[2,2])

    def test_lod_with_model_id_is_omitted(self):
        from inu_max.ops import map_export as ME
        a=Rec(1,'house',model_id=500,lod_object=2)
        lod=Rec(2,'house_LOD',kind='LOD',base='house',model_id=500)
        sc=scene([a,lod])
        with options():
            rows,_,_=ME._ipl_rows(sc,ML.LodIndex(sc),[a],False)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].lod_index,-1)


if __name__=='__main__': unittest.main()
