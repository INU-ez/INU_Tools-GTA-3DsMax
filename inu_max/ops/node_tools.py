"""SA node files retain their full binary payload while scene points move."""
import base64
import copy
import math
import os
import re
import tempfile

from inu_gta_core import paths as P
from ..adapter import selection as S, world as W
from .. import settings
from .path_tools import create_path, knot_records


def _read_bytes(data):
    fd,tmp=tempfile.mkstemp(suffix='.dat')
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data)
        return P.read_nodes(tmp)
    finally:
        os.unlink(tmp)


def import_nodes(paths):
    import uuid
    from .path_nodes_mesh import initialize_identity
    from inu_gta_core.paths_graph import graph_edges
    rt = S._rt()
    prepared = []
    for path in paths:
        match = re.fullmatch(r'nodes(\d+)\.dat', os.path.basename(path), re.I)
        if not match:
            raise ValueError('Expected NODES<area>.DAT: ' + path)
        with open(path, 'rb') as stream:
            raw = stream.read()
        data = _read_bytes(raw)
        edges = graph_edges(data, int(match[1]))
        prepared.append((path, raw, data, edges))
    count = 0
    created = []
    with S.undo_block('INU: Import Compiled Nodes'):
        try:
            for path, raw, data, edges in prepared:
                source = str(uuid.uuid4())
                owner = rt.Point(name=rt.uniqueName('INU_' + os.path.basename(path)), size=2)
                created.append(owner)
                S.put_field([owner], 'section', 'nodes_file')
                S.put_field([owner], 'type', 'NON')
                S.put_data([owner], 'nodes_file', dict(filename=os.path.basename(path),
                    raw=base64.b64encode(raw).decode('ascii'), source=source, identity_version=1))
                offset = 0
                for kind, field in (('nodes_vehicle', 'vehicle_nodes'), ('nodes_ped', 'ped_nodes'), ('nodes_navi', 'navi_nodes')):
                    nodes = getattr(data, field)
                    shape = rt.Editable_Poly(name=rt.uniqueName(os.path.splitext(os.path.basename(path))[0] + '_' + kind))
                    created.append(shape)
                    shape.parent = owner
                    for node in nodes:
                        rt.polyop.createVert(shape.baseObject, rt.Point3(node.x, node.y, getattr(node, 'z', 0)))
                    if kind != 'nodes_navi':
                        for a, b in sorted(edges):
                            if offset <= a < b < offset + len(nodes):
                                shape.baseObject.createEdge(a - offset + 1, b - offset + 1)
                        offset += len(nodes)
                    initialize_identity(shape, len(nodes), source)
                    S.put_field([shape], 'path_type', kind)
                    S.put_field([shape], 'section', 'nodes')
                    S.put_field([shape], 'type', 'NON')
                    S.put_field([shape], 'nodes_owner', int(rt.getHandleByAnim(owner)))
                    rt.update(shape)
                    count += len(nodes)
            if created:
                rt.select(rt.Array(*[node for node in created if S.get_data(node, 'nodes_file', None)]))
        except Exception:
            for node in reversed(created):
                if rt.isValidNode(node):
                    rt.delete(node)
            raise
    rt.redrawViews()
    return 'INFO', 'Imported %d compiled nodes with editable graph edges and persistent identities' % count


def _scene_files(owners=None):
    from .path_nodes_mesh import collect_owner
    rt = S._rt()
    output = []
    for owner in (rt.helpers if owners is None else owners):
        record = S.get_data(owner, 'nodes_file', None)
        if not record:
            continue
        raw = base64.b64decode(record['raw'])
        data = collect_owner(owner, _read_bytes(raw), record)
        output.append((record['filename'], data, raw))
    return output


def _write_checked(path,data):
    fd,tmp=tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)),suffix='.dat')
    os.close(fd)
    try:
        P.write_nodes(tmp,data)
        read=P.read_nodes(tmp)
        if (len(read.vehicle_nodes),len(read.ped_nodes),len(read.navi_nodes),len(read.links)) != (
            len(data.vehicle_nodes),len(data.ped_nodes),len(data.navi_nodes),len(data.links)):
            raise ValueError('Node file verification failed')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _selected_node_sources():
    """Selecting an imported child exports its complete preserved region."""
    rt = S._rt()
    owners = {}
    bare = []
    for node in rt.selection:
        parent = node
        owner = None
        while parent is not None:
            if S.get_data(parent, 'nodes_file', None):
                owner = parent
                break
            parent = parent.parent
        if owner is None:
            handle = int(S.get_field(node, 'nodes_owner', 0))
            if handle:
                owner = rt.maxOps.getNodeByHandle(handle)
                if owner is None or not rt.isValidNode(owner) or not S.get_data(owner, 'nodes_file', None):
                    raise ValueError('Imported node owner is missing: ' + str(node.name))
        if owner is not None:
            owners[int(rt.getHandleByAnim(owner))] = owner
        elif W.path_type(node) in ('nodes_vehicle', 'nodes_ped') and S.node_kind(node) == 'MESH':
            bare.append(node)
    points = []
    for node in bare:
        mesh = rt.snapshotAsMesh(node)
        try:
            for index in range(1, int(rt.getNumVerts(mesh)) + 1):
                point = rt.getVert(mesh, index) * node.objectTransform
                points.append((W.path_type(node), float(point.x), float(point.y), float(point.z)))
        finally:
            rt.delete(mesh)
    return list(owners.values()), P.split_nodes_by_area(points, fla4=bool(settings.get('nodes_fla4', False)))


def prepare_node_merge(files, zones, fla4=False):
    """Compose edited graph IDs and bare-node shifts before any disk writes."""
    from inu_gta_core.paths_graph import remap_foreign_references, validate_graph_batch
    prepared = {}
    for filename, data, _raw in files:
        match = re.fullmatch(r'nodes(\d+)\.dat', filename, re.I)
        if not match or not 0 <= int(match[1]) < 65536:
            raise ValueError('Invalid NODES<area>.DAT region filename: ' + filename)
        area = int(match[1])
        if area in prepared:
            raise ValueError('Conflicting imported copies of NODES%d.DAT; select one source region' % area)
        prepared[area] = (filename, copy.deepcopy(data))
    extras = copy.deepcopy(zones)
    remap = {address: target for _, data in prepared.values() for address, target in data.node_remap.items()}
    shifting = any(area in prepared and extra.vehicle_nodes and prepared[area][1].ped_nodes for area, extra in extras.items())
    if shifting or remap:
        if set(prepared) != set(range(64)):
            raise ValueError('Changing node IDs requires all 64 imported regions; no files written')
        for area, (filename, data) in prepared.items():
            if data.extra_data or (data.links and not data.parsed_extras):
                raise ValueError(filename + ': navigation sections are unparsed; no files written')
            if any(node.area_id == area and node.node_id != index
                   for index, node in enumerate(data.vehicle_nodes + data.ped_nodes)):
                raise ValueError(filename + ': node IDs do not match physical indices; no files written')
    merged = []
    for area, extra in sorted(extras.items()):
        if not 0 <= area < 64:
            raise ValueError('Bare nodes must belong to the vanilla 64-region map')
        if extra.links or extra.navi_nodes or any(node.flags & 15 for node in extra.vehicle_nodes + extra.ped_nodes):
            raise ValueError('Bare-node merge cannot accept a connected curve graph')
        if extra.fla4 or fla4:
            for node in extra.vehicle_nodes + extra.ped_nodes:
                node.spawn_probability, node.speed_limit_kmh, node.lane_count_override = [int(v * 8) for v in (node.x, node.y, node.z)]
        if area not in prepared:
            prepared[area] = ('NODES%d.DAT' % area, extra)
            continue
        filename, data = prepared[area]
        original_format = data.fla4
        if data.fla4 or fla4 or extra.fla4:
            for node in extra.vehicle_nodes + extra.ped_nodes:
                node.spawn_probability, node.speed_limit_kmh, node.lane_count_override = [int(v * 8) for v in (node.x, node.y, node.z)]
        merge_remap = P.merge_bare_nodes(data, extra, area_id=area, allow_reindex=bool(shifting))
        data.fla4 = original_format
        P.remap_node_references(data, merge_remap, area_id=area)
        # Local graph references already address rebuilt indices; incoming
        # references still address original indices, so compose both steps.
        for address, target in list(remap.items()):
            if target is not None and address[0] == area:
                remap[address] = merge_remap.get((area, target), target)
        if data.topology_changed:
            for current, original in enumerate(data.original_node_indices):
                if original is not None and (area, current) in merge_remap:
                    remap[(area, original)] = merge_remap[(area, current)]
        else:
            remap.update(merge_remap)
        merged.append(filename)
    changed = any(data.topology_changed for _, data in prepared.values())
    if remap or changed:
        for area, (_filename, data) in prepared.items():
            remap_foreign_references(data, remap, area=area)
        validate_graph_batch({area: data for area, (_filename, data) in prepared.items()})
    for _filename, data in prepared.values():
        if fla4 and not data.fla4:
            for node in data.vehicle_nodes + data.ped_nodes:
                node.spawn_probability, node.speed_limit_kmh, node.lane_count_override = [int(v * 8) for v in (node.x, node.y, node.z)]
            # Packed addresses have a different bit split in FLA4.
            from inu_gta_core.paths_graph import navi_address, unpack_navi_address
            data.navi_links = [navi_address(*unpack_navi_address(value), fla4=True) for value in data.navi_links]
        data.fla4 = data.fla4 or fla4
    return {filename: data for filename, data in prepared.values()}, merged


def write_node_batch(folder, files):
    """Serialize and verify every region before the batch replaces files."""
    from .file_write import write_batch
    os.makedirs(folder, exist_ok=True)
    existing = {}
    for filename in os.listdir(folder):
        key = filename.casefold()
        if key in existing and re.fullmatch(r'nodes\d+\.dat', filename, re.I):
            raise ValueError('Ambiguous node filenames differing only by case: ' + filename)
        existing[key] = filename
    payloads = {}
    with tempfile.TemporaryDirectory(dir=folder, prefix='.inu_nodes_') as staging:
        for filename, data in files.items():
            if os.path.basename(filename) != filename:
                raise ValueError('Node filename must not contain a directory')
            temporary = os.path.join(staging, filename)
            _write_checked(temporary, data)
            destination = os.path.join(folder, existing.get(filename.casefold(), filename))
            with open(temporary, 'rb') as stream:
                payloads[destination] = stream.read()
        write_batch(payloads)


def export_nodes(folder):
    owners, zones = _selected_node_sources()
    sources = _scene_files(owners)
    if not sources and not zones:
        return 'WARNING', 'Select imported node regions and/or bare vehicle/pedestrian node meshes'
    files, merged = prepare_node_merge(sources, zones, bool(settings.get('nodes_fla4', False)))
    # A standalone bare area must not erase a file whose source was not selected.
    selected_names = {filename.casefold() for filename, _data, _raw in sources}
    existing = {filename.casefold() for filename in os.listdir(folder)} if os.path.isdir(folder) else set()
    conflicts = sorted(name for name in files if name.casefold() in existing and name.casefold() not in selected_names)
    if conflicts:
        raise ValueError('Select the imported source region before merging into existing files: ' + ', '.join(conflicts))
    write_node_batch(folder, files)
    text = 'Exported %d node files' % len(files)
    if merged:
        text += '\nNew bare nodes merged with imported regions: ' + ', '.join(merged)
    if zones:
        text += '\nNew bare nodes remain disconnected; edit imported Editable Poly edges to create road connections.'
    return ('WARNING' if merged else 'INFO'), text


def build_graph(curves,path_set=64,fla4=False):
    """Pure graph builder: node IDs index vehicles first, then pedestrians."""
    zones={}
    unique={}
    adjacency={}
    for points,props,closed in curves:
        chain=[]
        vehicle=int(props.get('sapath_type',2))==2
        for point in points:
            point=tuple(int(float(v)*8)/8 for v in point)
            area=P.get_area_id(point[0],point[1],path_set)
            key=(area,vehicle,point)
            if key not in unique:
                node=P.PathNode(*point,area_id=area,is_vehicle=vehicle,
                    path_width=max(0,min(255,int(float(props.get('sapath_width',1))*8))))
                node.flags=P.encode_path_node_flags(switched_off=int(props.get('sapath_traffic',1))==2,
                    roadblock=bool(props.get('sapath_roadblock',False)),boats=bool(props.get('sapath_boats',False)),
                    highway=bool(props.get('sapath_highway',False)),emergency=bool(props.get('sapath_emergency',False)),
                    parking=bool(props.get('sapath_parking',False)),spawn=int(float(props.get('sapath_spawn',1))*15))
                unique[key]=node
                zones.setdefault(area,P.NodesFile(fla4=fla4,parsed_extras=True))
                pool=zones[area].vehicle_nodes if vehicle else zones[area].ped_nodes
                pool.append(node)
            chain.append(key)
        pairs=list(zip(chain,chain[1:]))
        if closed and len(chain)>2:
            pairs.append((chain[-1],chain[0]))
        for a,b in pairs:
            if a!=b:
                adjacency.setdefault(a,set()).add(b)
                adjacency.setdefault(b,set()).add(a)
    for nf in zones.values():
        for i,node in enumerate(nf.vehicle_nodes+nf.ped_nodes):
            node.node_id=i
    key_of={id(node):key for key,node in unique.items()}
    for area,nf in zones.items():
        for node in nf.vehicle_nodes+nf.ped_nodes:
            links=sorted(adjacency.get(key_of[id(node)],set()))
            if len(links)>15:
                raise ValueError('A node cannot have more than 15 outgoing links')
            node.link_id=len(nf.links)
            node.flags=(node.flags & ~15)|len(links)
            for key in links:
                dest=unique[key]
                nf.links.append(P.PathLink(dest.area_id,dest.node_id))
                nf.link_lengths.append(min(255,int(math.dist((node.x,node.y,node.z),(dest.x,dest.y,dest.z)))))
                if node.is_vehicle:
                    navi_id=len(nf.navi_nodes)
                    if navi_id >= (65536 if fla4 else 1024):
                        raise ValueError('Region exceeds the navigation node index limit')
                    dx,dy=dest.x-node.x,dest.y-node.y
                    length=max(1e-8,math.hypot(dx,dy))
                    nf.navi_nodes.append(P.NaviNode((node.x+dest.x)/2,(node.y+dest.y)/2,
                        node.area_id,node.node_id,int(dx/length*100),int(dy/length*100),
                        P.encode_navi_flags(left_lanes=1,right_lanes=1)))
                    nf.navi_links.append(navi_id|(area << (16 if fla4 else 10)))
                else:
                    nf.navi_links.append(0)
        nf.path_intersections=[0]*(len(nf.links)+192)
    return zones


def curves_to_dat(path):
    rt=S._rt()
    curves=[]
    for shape in W.selected_shapes():
        curves.append(([r['point'] for r in knot_records(shape)],W.sapath(shape),bool(rt.isClosed(shape,1))))
    if not curves:
        raise ValueError('Select path splines')
    path_set=int(settings.get('curves_path_set',64))
    fla4=bool(settings.get('curves_fla4',False))
    if path_set!=64 and not fla4:
        raise ValueError('Larger path sets require FLA4')
    zones=build_graph(curves,path_set,fla4)
    folder=os.path.dirname(os.path.abspath(path))
    entire=bool(settings.get('curves_entire_map',False))
    if entire:
        for area in range(path_set):
            zones.setdefault(area,P.NodesFile(fla4=fla4,parsed_extras=True))
    existing={name.lower():name for name in os.listdir(folder)}
    for area,nf in zones.items():
        filename=existing.get(('nodes%d.dat'%area).lower(),'NODES%d.DAT'%area)
        target=os.path.join(folder,filename)
        if os.path.isfile(target):
            raise ValueError('Curve graph would overwrite %s. Export into a new folder to retain existing references.' % filename)
    for area,nf in zones.items():
        _write_checked(os.path.join(folder,'NODES%d.DAT'%area),nf)
    return 'INFO','Exported %d connected path regions' % len(zones)


def nodes_to_curves():
    rt=S._rt()
    created=[]
    files = [(name, data, b'') for name, data in prepare_node_merge(_scene_files(), {})[0].items()]
    index = {(n.area_id, n.node_id): n for _, nf, _ in files for n in nf.vehicle_nodes + nf.ped_nodes}
    seen = set()
    with S.undo_block('INU: Nodes to Curves'):
        for filename,nf,_raw in files:
            nodes=nf.vehicle_nodes+nf.ped_nodes
            for node in nodes:
                for link in nf.links[node.link_id:node.link_id+(node.flags & 15)]:
                    dest=index.get((link.area_id,link.node_id))
                    if dest is None:
                        continue
                    key=tuple(sorted(((node.area_id,node.node_id),(dest.area_id,dest.node_id))))
                    if key in seen:
                        continue
                    seen.add(key)
                    shape=create_path([(node.x,node.y,node.z),(dest.x,dest.y,dest.z)],
                        'Path_'+filename,'nodes_vehicle' if node.is_vehicle else 'nodes_ped')
                    S.put_field([shape],'sapath_type',2 if node.is_vehicle else 1)
                    S.put_field([shape],'sapath_width',node.path_width/8)
                    created.append(shape)
        if created:
            rt.select(rt.Array(*created))
    return 'INFO','Created %d editable path segments' % len(created)


OPERATIONS={name:globals()[name] for name in ('import_nodes','export_nodes','curves_to_dat','nodes_to_curves')}


def toggle_nodes_viz():
    rt=S._rt()
    old=[n for n in rt.shapes if S.get_field(n,'preview_kind','')=='nodes_viz']
    with S.undo_block('INU: Node Visualization'):
        if old:
            for node in old:
                rt.delete(node)
            return 'INFO','Node visualization hidden'
        files=[(name, data, b'') for name, data in prepare_node_merge(_scene_files(), {})[0].items()]
        index={(node.area_id,node.node_id):node for _,nf,_ in files for node in nf.vehicle_nodes+nf.ped_nodes}
        lines=[]
        seen=set()
        for _,nf,_ in files:
            for node in nf.vehicle_nodes+nf.ped_nodes:
                for link in nf.links[node.link_id:node.link_id+(node.flags & 15)]:
                    target=index.get((link.area_id,link.node_id))
                    pair=tuple(sorted(((node.area_id,node.node_id),(link.area_id,link.node_id))))
                    if target is None or pair in seen:
                        continue
                    seen.add(pair)
                    lines.append(((node.x,node.y,node.z),(target.x,target.y,target.z)))
        if not lines:
            return 'WARNING','No connected path nodes to display'
        shape=rt.SplineShape(name=rt.uniqueName('INU_NodeLinks'))
        for i,(a,b) in enumerate(lines,1):
            rt.addNewSpline(shape)
            for point in (a,b):
                rt.addKnot(shape,i,rt.Name('corner'),rt.Name('line'),rt.Point3(*point))
        rt.updateShape(shape)
        S.put_field([shape],'preview_kind','nodes_viz')
        S.put_field([shape],'preview',True)
        S.put_field([shape],'type','NON')
    rt.redrawViews()
    return 'INFO','Displayed %d node links'%len(lines)


OPERATIONS['toggle_nodes_viz']=toggle_nodes_viz
