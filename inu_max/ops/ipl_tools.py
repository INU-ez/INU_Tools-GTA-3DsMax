"""IPL scene markers and placement of models already loaded in Max."""
from dataclasses import asdict
import math
import os

from inu_gta_core import ipl as I
from ..adapter import selection as S
from .. import settings
from . import map_link as ML

_SECTIONS={'culls':I.IplCull,'garages':I.IplGarage,'enexs':I.IplEnex,
    'pickups':I.IplPickup,'cars':I.IplCar,'auzos':I.IplAuzo,'jumps':I.IplJump,
    'occls':I.IplOccl,'tcycs':I.IplTcyc,'zones':I.IplZone}


def import_ipl_sections(path):
    rt=S._rt()
    data=I.read_ipl(path)
    count=0
    with S.undo_block('INU: Import IPL Sections'):
        for section,cls in _SECTIONS.items():
            layer=rt.LayerManager.getLayerFromName('IPL_'+section) or rt.LayerManager.newLayerFromName('IPL_'+section)
            for index,entry in enumerate(getattr(data,section)):
                values=asdict(entry)
                point=tuple(float(values.get('center_'+a, values.get('pos_'+a, values.get('mid_'+a, values.get('bottom_'+a, values.get('start_lower_'+a, values.get(a,values.get(a+'1',0)))))))) for a in 'xyz')
                node=rt.Point(name=rt.uniqueName('IPL_%s_%d'%(section,index)),pos=rt.Point3(*point),size=3,box=True)
                if section=='culls':
                    from inu_gta_core.ipl_geom import cull_row,cull_box_from_row
                    center,size,angle=cull_box_from_row(cull_row(entry),settings.get('game','SA'))
                    rt.delete(node)
                    node=rt.Box(name=rt.uniqueName('IPL_cull'),width=max(.1,size[0]),length=max(.1,size[1]),height=max(.1,size[2]),
                                pos=rt.Point3(center[0],center[1],center[2]-size[2]/2))
                    node.rotation=rt.EulerAngles(0,0,math.degrees(angle))
                    point=(center[0],center[1],center[2]-size[2]/2)
                    S.put_field([node],'ipl_cull_size',size)
                    S.put_field([node],'ipl_cull_angle',float(angle))
                S.put_field([node],'section','ipl_'+section)
                S.put_field([node],'type','NON')
                S.put_data([node],'ipl_section',dict(section=section,values=values,position=point,
                    source=os.path.abspath(path),index=index))
                for key,value in values.items():
                    if isinstance(value,(int,float,str)):
                        S.put_field([node],'ipl_'+key,value)
                layer.addNode(node)
                count+=1
    rt.redrawViews()
    return 'INFO','Imported %d IPL section markers (fields in user properties)' % count


def export_ipl_sections(path):
    rt=S._rt()
    data=I.read_ipl(path) if os.path.isfile(path) else I.IplFile()
    entries={section:[] for section in _SECTIONS}
    for node in rt.objects:
        record=S.get_data(node,'ipl_section',None)
        if not record:
            continue
        section=record['section']
        values=dict(record['values'])
        for key,value in values.items():
            if isinstance(value,(int,float,str)):
                values[key]=S.get_field(node,'ipl_'+key,value)
        delta=[float(getattr(node.pos,a))-old for a,old in zip('xyz',record['position'])]
        for axis,d in zip('xyz',delta):
            for key in (axis,'center_'+axis,'pos_'+axis,'mid_'+axis,'bottom_'+axis,axis+'1',axis+'2','cube_'+axis,'start_lower_'+axis,'start_upper_'+axis,'target_lower_'+axis,'target_upper_'+axis,'camera_'+axis):
                if key in values:
                    values[key]+=d
        entry=_SECTIONS[section](**values)
        if section=='culls':
            from inu_gta_core.ipl_geom import apply_cull_row,cull_row_from_box
            game=settings.get('game','SA')
            if game=='SA':
                size=(float(node.width)*abs(node.scale.x),float(node.length)*abs(node.scale.y),float(node.height)*abs(node.scale.z))
                center=(node.pos.x,node.pos.y,node.pos.z+size[2]/2)
                angle=math.atan2(node.transform.row1.y,node.transform.row1.x)
                apply_cull_row(entry,cull_row_from_box(center,size,angle))
        entries[section].append(entry)
    for section,records in entries.items():
        if records:
            setattr(data,section,records)
    I.write_ipl(path,data,game=settings.get('game','SA'))
    return 'INFO','Exported %d section records; existing inst entries retained' % sum(map(len,entries.values()))


def import_ide(path):
    from inu_gta_core.ide import read_ide
    data=read_ide(path)
    entries=list(data.objects)+list(data.anims)
    rt=S._rt()
    count=0
    with S.undo_block('INU: Import IDE'):
        scene=ML.Scene()
        for entry in entries:
            for record in scene.recs:
                if scene.model_name(record).lower()!=entry.model_name.lower():
                    continue
                S.put_field([record.node],'model_id',entry.model_id)
                S.put_field([record.node],'txd_name',entry.txd_name)
                S.put_field([record.node],'draw_distance',float(entry.draw_distance))
                S.put_field([record.node],'ide_flags',entry.flags)
                ML.stamp_ide(record,path,entry)
                count+=1
    return 'INFO','Applied IDE definitions to %d scene objects' % count


def _place(inst,source):
    rt=S._rt()
    from ..adapter import map_scene
    rows=ML.inst_rows(inst,settings.get('game','SA')!='SA')
    target=rt.Matrix3(*[rt.Point3(*rows[i:i+3]) for i in range(0,12,3)])
    nodes=[]
    stack=[source]
    while stack:
        node=stack.pop(0)
        nodes.append(node)
        stack[0:0]=list(node.children)
    matrices=[]
    texts=[]
    inverse=rt.inverse(source.transform)
    for original in nodes:
        tm=original.transform*inverse*target
        matrices.extend(float(v) for row in (tm.row1,tm.row2,tm.row3,tm.row4) for v in (row.x,row.y,row.z))
        props=map_scene.read_buffer(original)
        props.update(ML.buffer_props(ML.IPL_CLEAR))
        texts.append(map_scene.buffer_text(props))
    placed=map_scene.place(nodes,True,matrices,[True]*len(nodes),texts,0,'IPL_Models')
    node=placed[0]
    S.put_field([node],'model_id',inst.model_id)
    S.put_field([node],'interior_id',inst.interior)
    S.put_field([node],'real_interior',inst.real_interior)
    return node


def import_ipl(path):
    rt=S._rt()
    data=I.read_ipl(path)
    scene=ML.Scene()
    by_id={record.get('model_id',0):record.node for record in scene.recs if record.get('model_id',0)>0}
    by_name={scene.model_name(record).lower():record.node for record in scene.recs}
    nodes=[]
    with S.undo_block('INU: Import IPL'):
        for inst in data.instances:
            source=by_id.get(inst.model_id) or by_name.get(inst.model_name.lower())
            if source is not None:
                node=_place(inst,source)
                record=ML.Scene().rec(node)
                if record:
                    ML.stamp_ipl(record,path,inst)
            else:
                node=rt.Point(name=rt.uniqueName('IPL_'+inst.model_name),pos=rt.Point3(inst.pos_x,inst.pos_y,inst.pos_z),box=True,size=2)
                S.put_field([node],'type','NON')
                S.put_field([node],'section','ipl_placeholder')
                S.put_data([node],'ipl_placeholder',dict(instance=asdict(inst),source=os.path.abspath(path)))
            nodes.append(node)
        if nodes:
            rt.select(rt.Array(*nodes))
    return 'INFO','Placed %d IPL instances (missing models use markers)' % len(nodes)


def replace_ipl_placeholders():
    rt=S._rt()
    scene=ML.Scene()
    count=0
    with S.undo_block('INU: Replace IPL Markers'):
        for marker in list(rt.helpers):
            record=S.get_data(marker,'ipl_placeholder',None)
            if not record:
                continue
            inst=I.IplInstance(**record['instance'])
            source=next((r.node for r in scene.recs if r.get('model_id',0)==inst.model_id or scene.model_name(r).lower()==inst.model_name.lower()),None)
            if source is None:
                continue
            inst.pos_x,inst.pos_y,inst.pos_z=marker.pos.x,marker.pos.y,marker.pos.z
            node=_place(inst,source)
            new=ML.Scene().rec(node)
            if new:
                ML.stamp_ipl(new,record['source'],inst)
            rt.delete(marker)
            count+=1
    return 'INFO','Replaced %d IPL markers with models' % count


OPERATIONS={name:globals()[name] for name in ('import_ipl_sections','export_ipl_sections',
    'import_ide','import_ipl','replace_ipl_placeholders')}
