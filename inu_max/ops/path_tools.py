"""Spline IO for tracks and III/VC IPL paths. Knot metadata stays in .max."""
from dataclasses import asdict
import json
import os
import uuid

from inu_gta_core import paths as P
from ..adapter import selection as S, world as W
from .. import settings


def create_path(points, name, kind, data=None):
    rt = S._rt()
    shape = rt.SplineShape(name=rt.uniqueName(name))
    rt.addNewSpline(shape)
    for point in points:
        rt.addKnot(shape, 1, rt.Name('corner'), rt.Name('line'), rt.Point3(*point))
    rt.updateShape(shape)
    S.put_field([shape], 'path_type', kind)
    S.put_field([shape], 'type', 'NON')
    S.put_field([shape], 'section', 'paths')
    records = []
    for i, point in enumerate(points):
        item = dict(data[i]) if data and i < len(data) else {}
        records.append(dict(id=str(uuid.uuid4()), point=list(point), values=item))
    S.put_data([shape], 'path_knots', records)
    return shape


def knot_records(shape):
    rt = S._rt()
    if int(rt.numSplines(shape)) != 1:
        raise ValueError('Path splines must contain one spline each')
    points = []
    # Base-object access uses local coordinates, independent of the active viewport.
    for i in range(1, int(rt.numKnots(shape, 1)) + 1):
        p = rt.getKnotPoint(shape.baseObject, 1, i) * shape.transform
        points.append([float(p.x), float(p.y), float(p.z)])
    old = S.get_data(shape, 'path_knots', [])
    if len(old) == len(points):
        records = old
    else:
        # On insertion/deletion match retained positions. New knots receive
        # defaults rather than inheriting the next knot's station/flags.
        unused = list(old)
        records = []
        for point in points:
            match = next((r for r in unused if sum((a-b)**2 for a,b in zip(r['point'], point)) < 1e-8), None)
            if match is not None:
                unused.remove(match)
            records.append(match or dict(id=str(uuid.uuid4()), point=point, values={}))
    for record, point in zip(records, points):
        record['point'] = point
    S.put_data([shape], 'path_knots', records)
    return records


def _selected(kind=None):
    return [shape for shape in W.selected_shapes() if kind is None or W.path_type(shape) == kind]


def import_track(path):
    track = P.read_track(path)
    rt = S._rt()
    with S.undo_block('INU: Import Track'):
        shape = create_path([(n.x,n.y,n.z) for n in track.nodes], os.path.splitext(os.path.basename(path))[0],
                            'track', [asdict(n) for n in track.nodes])
        rt.select(shape)
    return 'INFO', 'Imported %d track knots' % len(track.nodes)


def export_track(path):
    shapes = _selected('track')
    if len(shapes) != 1:
        raise ValueError('Select exactly one train track')
    nodes = [P.TrackNode(*r['point'], int(r['values'].get('flag',0))) for r in knot_records(shapes[0])]
    P.write_track(path, P.TrackFile(nodes))
    return 'INFO', 'Exported %d track knots' % len(nodes)


def import_paths_ipl(path):
    data = P.read_paths_ipl(path, game=settings.get('game','VC'))
    rt = S._rt()
    nodes = []
    with S.undo_block('INU: Import Paths IPL'):
        for i, group in enumerate(data.groups):
            # Empty entries preserve their original positions and linkage;
            # removing them would renumber the group's fixed 12-slot indices.
            shape = create_path([(n.x,n.y,n.z) for n in group.nodes], 'Path_%d' % i,
                                'path_ipl', [asdict(n) for n in group.nodes])
            S.put_field([shape], 'group_type', group.group_type)
            S.put_field([shape], 'path_external_index', group.external_index)
            S.put_field([shape], 'path_model_name', group.model_name)
            nodes.append(shape)
        if nodes:
            rt.select(rt.Array(*nodes))
    return 'INFO', 'Imported %d IPL path groups' % len(nodes)


def export_paths_ipl(path):
    shapes = _selected('path_ipl') or [s for s in S._rt().shapes if W.path_type(s)=='path_ipl']
    groups = []
    for shape in shapes:
        records = knot_records(shape)
        if len(records) > 12:
            raise ValueError('%s: IPL path groups allow at most 12 knots' % shape.name)
        nodes = []
        for i,r in enumerate(records):
            values = dict(r['values'])
            values.pop('_raw',None)
            values.pop('_original',None)
            node = P.PathIPLNode(**values) if values else P.PathIPLNode(node_type=2,link_id=i+1 if i+1<len(records) else -1)
            node.x,node.y,node.z = r['point']
            nodes.append(node)
        groups.append(P.PathIPLGroup(S.get_field(shape,'group_type',1),
            S.get_field(shape,'path_external_index',-1), nodes, S.get_field(shape,'path_model_name','')))
    P.write_paths_ipl(path, P.PathIPLFile(groups, settings.get('game','VC')))
    return 'INFO', 'Exported %d IPL path groups' % len(groups)


def add_path(kind='path_ipl'):
    rt = S._rt()
    with S.undo_block('INU: Add Path'):
        shape = create_path([(0,0,0),(10,0,0)], 'Track' if kind=='track' else 'Path', kind)
        S.put_field([shape],'sapath_type',2)
        rt.select(shape)
    return 'INFO', 'Created ' + str(shape.name)


def convert_to_path():
    nodes = W.selected_shapes()
    if not nodes:
        raise ValueError('Select spline shapes to convert')
    with S.undo_block('INU: Convert Paths'):
        for node in nodes:
            S._rt().convertToSplineShape(node)
            S.put_field([node], 'path_type','path_ipl')
            S.put_field([node], 'type','NON')
            S.put_field([node], 'section','paths')
            S.put_field([node], 'sapath_type',2)
            knot_records(node)
    return 'INFO', 'Converted %d splines to paths' % len(nodes)


def edit_flags(bit=None, station=False):
    rt = S._rt()
    count=0
    with S.undo_block('INU: Path Knot Flags'):
        for shape in _selected('track' if station else 'path_ipl'):
            records=knot_records(shape)
            selected=list(rt.getKnotSelection(shape,1))
            indices=[int(i)-1 for i in selected] if selected else range(len(records))
            for i in indices:
                value=records[i]['values']
                key='flag' if station else 'flags'
                value[key]=int(value.get(key,0)) ^ (1 if station else bit)
                count+=1
            S.put_data([shape], 'path_knots', records)
    return 'INFO', 'Updated %d path knots' % count


def refresh_station_markers():
    rt=S._rt()
    count=0
    with S.undo_block('INU: Station Markers'):
        for node in list(rt.helpers):
            if S.get_field(node,'preview_kind','')=='path_station':
                rt.delete(node)
        for shape in rt.shapes:
            if W.path_type(shape)!='track':
                continue
            for r in knot_records(shape):
                if not r['values'].get('flag',0):
                    continue
                marker=rt.Point(name=rt.uniqueName('Station'),pos=rt.Point3(*r['point']),size=2,cross=True)
                S.put_field([marker],'preview_kind','path_station')
                S.put_field([marker],'preview',True)
                S.put_field([marker],'type','NON')
                count+=1
    rt.redrawViews()
    return 'INFO','Created %d station markers' % count


OPERATIONS={name:globals()[name] for name in ('import_track','export_track','import_paths_ipl',
    'export_paths_ipl','convert_to_path','refresh_station_markers')}
OPERATIONS.update(add_path_ipl=add_path,add_track=lambda:add_path('track'),
    mark_station=lambda:edit_flags(station=True),TOGGLE_ROADBLOCK=lambda:edit_flags(bit=2),
    TOGGLE_DISABLED=lambda:edit_flags(bit=1),TOGGLE_BETWEEN_LEVELS=lambda:edit_flags(bit=4))


def refresh_path_colors():
    rt=S._rt()
    count=0
    for shape in rt.shapes:
        if not W.path_type(shape):
            continue
        props=W.sapath(shape)
        vehicle=int(props.get('sapath_type',2))==2
        color=[255,0,0] if vehicle else [0,255,0]
        if vehicle and props.get('sapath_boats'):
            color=[0,0,255]
        if vehicle and props.get('sapath_parking'):
            color=[255,150,0]
        else:
            if int(props.get('sapath_traffic',1))==2:
                color=[max(0,c-75) for c in color]
            if props.get('sapath_highway'):
                color[2]=min(255,color[2]+150)
        shape.wirecolor=rt.Color(*color)
        count+=1
    rt.redrawViews()
    return 'INFO','Colored %d path splines' % count


def add_path_accessory():
    rt=S._rt()
    shape=S.active_node()
    if shape is None or not W.is_shape(shape):
        raise ValueError('Select a path spline')
    records=knot_records(shape)
    index=int(settings.get('acc_knot',0))
    if not 0<=index<len(records):
        raise ValueError('Knot index is outside this spline')
    kind=settings.get('acc_type','TL')
    with S.undo_block('INU: Path Accessory'):
        marker=rt.Point(name=rt.uniqueName('INU_'+kind),size=2,cross=True)
        marker.parent=shape
        S.put_data([marker],'path_accessory',dict(owner=int(rt.getHandleByAnim(shape)),knot=records[index]['id'],kind=kind))
        S.put_field([marker],'type','NON')
        S.put_field([marker],'preview',True)
        records[index]['values']['accessory_'+kind]=True
        S.put_data([shape],'path_knots',records)
        sync_accessories()
        rt.select(marker)
    return 'INFO','Created path accessory '+str(marker.name)


def sync_accessories():
    rt=S._rt()
    cache={}
    for marker in rt.helpers:
        data=S.get_data(marker,'path_accessory',None)
        if not data:
            continue
        owner=rt.maxOps.getNodeByHandle(data['owner'])
        if owner is None:
            marker.isHidden=True
            continue
        if data['owner'] not in cache:
            cache[data['owner']]=knot_records(owner)
        records=cache[data['owner']]
        index=next((i for i,r in enumerate(records) if r['id']==data['knot']),None)
        if index is None:
            marker.isHidden=True
            continue
        marker.isHidden=False
        point=records[index]['point']
        if data['kind']=='TL' and index+1<len(records):
            point=[(a+b)/2 for a,b in zip(point,records[index+1]['point'])]
        marker.pos=rt.Point3(*point)
    rt.redrawViews()


def remove_path_accessory():
    rt=S._rt()
    count=0
    with S.undo_block('INU: Remove Path Accessory'):
        for marker in list(rt.selection):
            data=S.get_data(marker,'path_accessory',None)
            if not data:
                continue
            owner=rt.maxOps.getNodeByHandle(data['owner'])
            if owner is not None:
                records=knot_records(owner)
                for record in records:
                    if record['id']==data['knot']:
                        record['values'].pop('accessory_'+data['kind'],None)
                S.put_data([owner],'path_knots',records)
            rt.delete(marker)
            count+=1
    return 'INFO','Removed %d path accessories' % count


def start_accessory_sync():
    from .. import sessions
    if 'path_accessories' in sessions.timers:
        sessions.stop('path_accessories')
        return 'INFO','Path accessory sync stopped'
    sessions.start('path_accessories',sync_accessories)
    sync_accessories()
    return 'INFO','Path accessory sync started'


def toggle_path_debug(mode='NODE'):
    rt=S._rt()
    with S.undo_block('INU: Path Debug Labels'):
        for node in list(rt.shapes):
            if S.get_field(node,'preview_kind','')=='path_debug':
                rt.delete(node)
        if mode!='OFF':
            from .node_tools import _scene_files
            for _filename,nf,_raw in _scene_files():
                nodes=nf.navi_nodes if mode=='NAVI' else nf.vehicle_nodes+nf.ped_nodes
                for index,node in enumerate(nodes):
                    label=rt.Text(name=rt.uniqueName('INU_NodeID'),text=('%d:%d' % (node.area_id,index)),size=2,
                                  pos=rt.Point3(node.x,node.y,getattr(node,'z',0)+1))
                    S.put_field([label],'preview_kind','path_debug')
                    S.put_field([label],'preview',True)
                    S.put_field([label],'type','NON')
    rt.redrawViews()
    return 'INFO','Path debug '+mode.lower()


OPERATIONS.update({name:globals()[name] for name in ('refresh_path_colors','add_path_accessory',
    'remove_path_accessory','start_accessory_sync','toggle_path_debug')})
