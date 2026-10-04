"""Run in an isolated 3ds Max Batch process; no existing scene is touched."""
import json
import os
import sys
sys.dont_write_bytecode = True
import traceback
from pathlib import Path
import pymxs
from pymxs import runtime as rt
ROOT=Path(__file__).resolve().parents[3]
GAME_ROOT=Path(os.environ.get('INU_TEST_GAME_ROOT',r'D:\Grand Theft Auto San Andreas'))
PED=os.environ.get('INU_TEST_PED','bmycr')
sys.path.insert(0,str(ROOT))
import inu_boot
inu_boot._ensure_paths()
from inu_max.adapter import selection as S, scene_build as B
from inu_max.ops import ik_rig as IK, anim_tools as T
from inu_max import settings
# Test preferences remain in this process and never alter the user's Max.
settings._save=lambda:None
settings._STATE.update({'ik_root_motion':False,'ik_size':1.,'ik_show_pole':True})
from inu_gta_core.img import extract_file
from inu_gta_core.dff import read_dff
from inu_max.ops.dff_read import plan
REPORT=ROOT/'dev/tests/e2e/ik_runtime_result.json'
result={'checks':[]}
def checkpoint(text):
    result['checks'].append(text)
    REPORT.write_text(json.dumps(result,indent=2),encoding='utf-8')

def matrix_drift(before,after):
    return max(rt.distance(getattr(old[h],'row'+str(row)),getattr(new[h],'row'+str(row)))
               for (_,old),(_,new) in zip(before,after) for h in old for row in range(1,5))
try:
    rt.resetMaxFile(rt.Name('noPrompt'))
    checkpoint('Max initialized')
    data=extract_file(str(GAME_ROOT/'models/gta3.img'),PED+'.dff')
    p=plan(read_dff(data),PED)
    made=B.build(p)
    root=made[0]
    mesh_nodes=[n for n in made if S.node_kind(n)=='MESH']
    assert mesh_nodes
    def mesh_positions():
        result=[]
        for obj in mesh_nodes:
            mesh=rt.snapshotAsMesh(obj)
            result.extend(rt.getVert(mesh,i)*obj.transform for i in range(1,int(rt.getNumVerts(mesh))+1))
        return result
    checkpoint('Actual DFF import creates mesh and Skin')
    rt.select(root)
    rt.animationRange=rt.Interval(0,3)
    bones=T._bones(root)
    checkpoint('Imported vanilla '+PED+' skeleton: '+str(len(bones)))
    output=T.add_ik_rig()
    checkpoint(str(output))
    boxes=IK.controls(root)
    assert len(boxes)==13,len(boxes)
    groups={kind:sum(S.get_field(n,'ik_ctrl_type','')==kind for n in boxes) for kind in IK.SIZES}
    assert groups=={'chain':4,'pole':4,'rot':4,'root':1},groups
    for n in boxes:
        kind=S.get_field(n,'ik_ctrl_type','')
        assert abs(n.size-IK.SIZES[kind])<1e-5
        assert n.box and not n.cross
        if rt.isProperty(n,rt.Name('drawOnTop')):
            assert n.drawOnTop
    checkpoint('13 enlarged box controls with correct groups; drawOnTop enabled')
    by_id={S.get_field(n,'bone_id',-1):n for n in bones}
    assert (by_id[5].transform.row4-by_id[1].transform.row4).z>.5
    front=(by_id[44].transform.row4-by_id[43].transform.row4)+(by_id[54].transform.row4-by_id[53].transform.row4)
    front.z=0
    front=rt.normalize(front)
    for label,ids,sign in [('R_arm',(22,23,24),-1),('L_arm',(32,33,34),-1),('R_leg',(51,52,53),1),('L_leg',(41,42,43),1)]:
        box=next(n for n in boxes if S.get_field(n,'ik_ctrl_type','')=='chain' and str(n.name).startswith('INU_IK_'+label))
        original=rt.copy(box.transform)
        upper,middle,tip=[by_id[i] for i in ids]
        previous_reach=rt.distance(upper.transform.row4,tip.transform.row4)
        mesh_before=mesh_positions() if label=='R_arm' else None
        box.pos=box.pos+(upper.transform.row4-box.pos)*.12
        sv=next(n for n in rt.helpers if S.get_field(n,"ik_root",0) and S.get_field(n,"ik_goal_node",0)==IK._handle(box))
        rt.sliderTime=1
        rt.sliderTime=0
        start=upper.transform.row4;axis=rt.normalize(tip.transform.row4-start)
        bend=middle.transform.row4-start
        bend=bend-axis*rt.dot(bend,axis)
        measured=rt.dot(bend,front)*sign
        checkpoint(label+' reach change: '+str(previous_reach-rt.distance(upper.transform.row4,tip.transform.row4)))
        assert previous_reach-rt.distance(upper.transform.row4,tip.transform.row4)>.03,label
        checkpoint(label+' anatomical bend: '+str(measured))
        assert measured>.03,(label,measured)
        assert rt.distance(tip.transform.row4,sv.transform.row4)<1e-5,label
        checkpoint(label+" goal error: "+str(rt.distance(sv.transform.row4,box.transform.row4-box.transform.row2*.05)))
        assert rt.distance(sv.transform.row4,(box.transform.row4-box.transform.row2*.05))<1e-5,label
        pole=next(n for n in boxes if S.get_field(n,'ik_ctrl_type','')=='pole' and str(n.name).startswith('INU_IK_'+label))
        original_pole=rt.copy(pole.transform)
        before_joint=rt.copy(middle.transform.row4)
        pole.pos=pole.pos+rt.Point3(.2,.1,-.1)
        assert rt.distance(before_joint,middle.transform.row4)>.01,label
        pole.transform=original_pole
        checkpoint(label+' pole box drives bend direction')
        if mesh_before is not None:
            assert max(rt.distance(a,b) for a,b in zip(mesh_before,mesh_positions()))>.01
            checkpoint('IK movement deforms the imported Skin mesh')
        box.transform=original
    checkpoint('Fresh ped is upright; knees bend forward and elbows backward')
    assert T._rig()==root
    checkpoint('Selected box resolves its skeleton')
    for solver in rt.helpers:
        if S.get_field(solver,'ik_root',0):
            assert solver.isHidden
            assert S.node_by_handle(S.get_field(solver,"ik_vh_node",0)) is not None
    checkpoint('Solver helpers hidden; poles connected')
    goal=next(n for n in boxes if S.get_field(n,'ik_ctrl_type','')=='chain')
    solver=next(n for n in rt.helpers if S.get_field(n,'ik_root',0) and S.get_field(n,"ik_goal_node",0)==IK._handle(goal))
    before=rt.copy(solver.transform.row4)
    goal.pos=goal.pos+rt.Point3(.03,.02,.01)
    rt.sliderTime=1
    rt.sliderTime=0
    assert rt.distance(before,solver.transform.row4)>.001
    checkpoint('Moving a box drives limb IK')
    original_goal=rt.copy(goal.transform)
    start=S.node_by_handle(S.get_field(solver,'ik_start_node',0)).transform.row4
    for target in [start,start+rt.Point3(100,0,0)]:
        tm=rt.copy(original_goal)
        tm.row4=target+tm.row2*.05
        goal.transform=tm
        for n in bones:
            matrix=n.transform
            assert all(__import__('math').isfinite(float(getattr(getattr(matrix,'row'+str(row)),axis)))
                       for row in range(1,5) for axis in ('x','y','z')),str(n.name)
    goal.transform=original_goal
    checkpoint('Coincident and unreachable goals keep finite bone transforms')
    pole=next(n for n in boxes if S.get_field(n,'ik_ctrl_type','')=='pole')
    goal.pos=goal.pos+(S.node_by_handle(S.get_field(solver,"ik_start_node",0)).transform.row4-goal.pos)*.2
    joint=next(n for n in bones if S.get_field(n,'bone_id',-1)==23)
    old_pole=rt.copy(pole.transform)
    before=rt.copy(joint.transform.row4)
    pole.pos=pole.pos+rt.Point3(.2,.1,-.1)
    assert rt.distance(before,joint.transform.row4)>.0001
    pole.transform=old_pole
    checkpoint('Elbow box changes the limb bend')
    settings.set('ik_size',2.)
    settings.set('ik_show_pole',False)
    IK.update_display()
    assert all(n.isHidden for n in boxes if S.get_field(n,'ik_ctrl_type','')=='pole')
    checkpoint('Display settings work')
    T.add_ground_plane()
    foot=next(n for n in boxes if S.get_field(n,'ik_foot',False))
    ground=next(n for n in rt.objects if S.get_field(n,'ik_ground',False))
    ground.pos=rt.Point3(0,0,2)
    foot.pos=rt.Point3(0,0,-5)
    assert foot.pos.z>=2+settings.get('floor_offset',.05)-1e-4,foot.pos.z
    checkpoint('Floor follows plane and clamps foot')
    positions={IK._handle(n):rt.copy(n.transform) for n in bones}
    checkpoint('Current time: '+str(rt.sliderTime)+'; root: '+str(root.transform))
    sampled=IK._samples(bones,[float(rt.sliderTime.frame)])[0][1]
    checkpoint('Sampling current frame drift: '+str(max(rt.distance(positions[h].row4,sampled[h].row4) for h in positions)))
    rt.select(root)
    output=T.bake_ik_rig()
    checkpoint(str(output))
    assert not IK.controls(root)
    assert not S.get_field(root,'ik_rigged',False)
    assert not any(S.get_field(n,'ik_backup_root',0)==IK._handle(root) for n in rt.helpers)
    checkpoint('Post-bake sampled pose error: '+str(max(rt.distance(tm.row4,IK._samples(bones,[0])[0][1][h].row4) for h,tm in positions.items())))
    for n in bones:
        error=rt.distance(n.transform.row4,positions[IK._handle(n)].row4)
        assert error<1e-4,(str(n.name),error, str(n.pos),str(positions[IK._handle(n)].row4))
    checkpoint('Bake preserves evaluated pose and removes rig nodes')
    rt.delete(ground)
    settings.set('ik_root_motion',True)
    pelvis=next(n for n in bones if S.get_field(n,'bone_id',-1)==1)
    with pymxs.animate(True),pymxs.attime(3):
        pelvis.pos=pelvis.pos+rt.Point3(.1,.03,.02)
    frames=list(range(4))
    before=IK._samples(bones,frames)
    rt.select(root)
    checkpoint(str(T.add_ik_rig()))
    after=IK._samples(bones,frames)
    drift=matrix_drift(before,after)
    errors=sorted([(max(rt.distance(getattr(old[IK._handle(n)],'row'+str(r)),getattr(new[IK._handle(n)],'row'+str(r))) for r in range(1,5)),str(n.name),f) for (f,old),(_,new) in zip(before,after) for n in bones],reverse=True)
    checkpoint('FK errors: '+str(errors[:12]))
    checkpoint('FK position error: '+str(max(rt.distance(old[h].row4,new[h].row4) for (_,old),(_,new) in zip(before,after) for h in old)))
    checkpoint('FK position details: '+str(sorted([(rt.distance(old[IK._handle(n)].row4,new[IK._handle(n)].row4),str(n.name),str(old[IK._handle(n)].row4),str(new[IK._handle(n)].row4)) for (_,old),(_,new) in zip(before,after) for n in bones],reverse=True)[:8]))
    checkpoint('FK transfer maximum position error: '+str(drift))
    assert drift<.001,drift
    scene=ROOT/'dev/tests/e2e/ik_roundtrip.max'
    rt.saveMaxFile(str(scene),quiet=True)
    rt.loadMaxFile(str(scene),quiet=True)
    rt.execute('inuIKQuatTM=undefined; inuIKSetWorld=undefined; inuIKFootFloor=undefined; inuIKCopyRotation=undefined; inuIKCopyPosition=undefined; inuIKFollowPosition=undefined')
    root=next(n for n in rt.objects if S.get_field(n,'ik_rigged',False))
    bones=T._bones(root)
    assert len(IK.controls(root))==13
    checkpoint('Rig references survive save/reload without Python/global MAXScript evaluation callbacks')
    before=IK._samples(bones,frames)
    rt.select(root)
    checkpoint(str(T.bake_ik_rig()))
    after=IK._samples(bones,frames)
    drift=matrix_drift(before,after)
    assert drift<.001,drift
    checkpoint('Animated bake preserves every sampled frame')
    from inu_gta_core.ifp import read_ifp
    package=read_ifp(str(GAME_ROOT/'anim/ped.ifp'))
    clip=next(a for a in package.animations if a.name=='WALK_civi')
    count,missing=T.apply_clip(clip,root)
    assert count==32 and not missing,(count,missing)
    frames=list(range(int(rt.animationRange.end.frame)+1))
    before=IK._samples(bones,frames)
    rt.select(root)
    checkpoint(str(T.add_ik_rig()))
    after=IK._samples(bones,frames)
    drift=matrix_drift(before,after)
    checkpoint('WALK_civi FK transfer error: '+str(drift))
    checkpoint('WALK errors: '+str(sorted([(max(rt.distance(getattr(old[IK._handle(n)],'row'+str(r)),getattr(new[IK._handle(n)],'row'+str(r))) for r in range(1,5)),str(n.name),f) for (f,old),(_,new) in zip(before,after) for n in bones],reverse=True)[:8]))
    checkpoint('WALK positions: '+str(max(rt.distance(old[h].row4,new[h].row4) for (_,old),(_,new) in zip(before,after) for h in old)))
    assert drift<.001,drift
    rt.select(root)
    checkpoint(str(T.bake_ik_rig()))
    after_bake=IK._samples(bones,frames)
    assert matrix_drift(after,after_bake)<.001
    checkpoint('Vanilla WALK_civi transfer and bake preserve the animation')
    result['success']=True
except Exception:
    result['success']=False
    result['error']=traceback.format_exc()
finally:
    REPORT.write_text(json.dumps(result,indent=2),encoding='utf-8')
