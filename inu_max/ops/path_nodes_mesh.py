"""Live Editable Poly graph and persistent vertex identity for Compiled NODES.

Two user VData channels hold exactly representable 24-bit integer tokens.
Their pair is checked, so interpolated subdivision data is not an old ID.
"""
import copy
import re
from dataclasses import replace
from inu_gta_core import paths as P
from inu_gta_core.paths_graph import graph_edges, rebuild_graph
from ..adapter import selection as S, world as W


def identity_token(slot):
    mask = (1 << 24) - 1
    if not 0 <= slot < 65536:
        raise ValueError('NODES identity capacity exceeded')
    value = ((slot + 1) * 104729) & mask
    value ^= value >> 11
    value = (value * 0x45D9F3B) & mask
    value ^= value >> 16
    witness = ((value * 2654435761) & mask) ^ (value >> 7)
    return value, witness


def initialize_identity(node, count, source):
    rt = S._rt()
    obj = node.baseObject
    if rt.classOf(obj) != rt.Editable_Poly:
        raise ValueError('Compiled NODES requires Editable Poly')
    channels = []
    for channel in range(11, 101):
        if channel > int(rt.polyop.getNumVDataChannels(obj)) or not rt.polyop.getVDataChannelSupport(obj, channel):
            channels.append(channel)
            if len(channels) == 2:
                break
    if len(channels) != 2:
        raise ValueError('No free user vertex-data channels for NODES identities')
    rt.polyop.setNumVDataChannels(obj, max(channels[-1], int(rt.polyop.getNumVDataChannels(obj))), keep=True)
    for channel in channels:
        rt.polyop.setVDataChannelSupport(obj, channel, True)
    for i in range(count):
        for channel, token in zip(channels, identity_token(i)):
            rt.polyop.setVDataValue(obj, channel, i + 1, float(token))
    S.put_data([node], 'nodes_identity', dict(version=1, channels=channels, source=source))


def read_mesh(node, source):
    """Read live base data in subobject mode; never snapshot away loose edges."""
    rt = S._rt()
    if list(node.modifiers):
        raise ValueError(str(node.name) + ': edit the imported Editable Poly directly; modifiers obscure persistent NODES identities')
    obj = node.baseObject
    metadata = S.get_data(node, 'nodes_identity', None)
    if rt.classOf(obj) != rt.Editable_Poly or not metadata or metadata.get('version') != 1:
        raise ValueError(str(node.name) + ': reimport NODES to initialize stable vertex identities')
    if metadata.get('source') != source:
        raise ValueError('NODES mesh belongs to a different import; do not mix region copies')
    channels = metadata.get('channels', [])
    if len(channels) != 2 or any(not rt.polyop.getVDataChannelSupport(obj, c) for c in channels):
        raise ValueError('NODES identity channels are missing; reimport the source file')
    dead = {int(i) for i in rt.polyop.getDeadVerts(obj)}
    selected = {int(i) for i in rt.polyop.getVertSelection(obj)}
    indices = [i for i in range(1, int(rt.polyop.getNumVerts(obj)) + 1) if i not in dead]
    compact = {index: i for i, index in enumerate(indices)}
    local, world, identities, selection = [], [], [], []
    for index in indices:
        point = rt.polyop.getVert(obj, index)
        local.append((float(point.x), float(point.y), float(point.z)))
        point = point * node.objectTransform
        world.append((float(point.x), float(point.y), float(point.z)))
        identities.append(tuple(float(rt.polyop.getVDataValue(obj, c, index)) for c in channels))
        selection.append(index in selected)
    dead_edges = {int(i) for i in rt.polyop.getDeadEdges(obj)}
    edges = set()
    for index in range(1, int(obj.GetNumEdges()) + 1):
        if index in dead_edges:
            continue
        a, b = int(obj.GetEdgeVertex(index, 1)), int(obj.GetEdgeVertex(index, 2))
        if a not in compact or b not in compact:
            raise ValueError('Live NODES edge references a deleted vertex')
        edges.add(tuple(sorted((compact[a], compact[b]))))
    return dict(local=local, world=world, identities=identities, selected=selection, edges=edges)


def mesh_origins(mesh, original):
    if any(len(mesh[key]) != len(mesh['world']) for key in ('local', 'identities', 'selected')):
        raise ValueError('Incomplete live NODES identity data')
    by_token = {identity_token(i): i for i in range(len(original))}
    candidates = {}
    origins = [None] * len(mesh['world'])
    for i, pair in enumerate(mesh['identities']):
        slot = by_token.get(tuple(pair))
        if slot is not None:
            candidates.setdefault(slot, []).append(i)
    for slot, choices in candidates.items():
        old = original[slot]
        def rank(i):
            return (sum((v - o) ** 2 for v, o in zip(mesh['local'][i], (old.x, old.y, getattr(old, 'z', 0)))),
                    bool(mesh['selected'][i]))
        choices.sort(key=lambda i: (*rank(i), i))
        if len(choices) > 1 and rank(choices[0]) == rank(choices[1]):
            raise ValueError('Coincident duplicated NODES identity: move the new point before exporting')
        origins[choices[0]] = slot
    return origins


def collect_graph(original, meshes, area):
    """Pure collector; meshes contains the complete categories of one import."""
    baseline = copy.deepcopy(original)
    pools = ('vehicle_nodes', 'ped_nodes', 'navi_nodes')
    for category, pool in zip(('nodes_vehicle', 'nodes_ped', 'nodes_navi'), pools):
        if category not in meshes and getattr(baseline, pool):
            raise ValueError('Include every vehicle, pedestrian and navigation mesh from this NODES region')
    nav_mesh = meshes.get('nodes_navi')
    if nav_mesh is not None:
        if len(nav_mesh['world']) != len(baseline.navi_nodes):
            raise ValueError('Edit vehicle edges to create navigation; do not add/delete navigation vertices')
        slots = mesh_origins(nav_mesh, baseline.navi_nodes)
        if set(slots) != set(range(len(baseline.navi_nodes))):
            raise ValueError('Navigation vertex identities changed; reimport NODES')
        for i, slot in enumerate(slots):
            baseline.navi_nodes[slot].x, baseline.navi_nodes[slot].y = nav_mesh['world'][i][:2]
    nodes, origins, edges = [], [], set()
    old_offset = 0
    vehicle_count = 0
    for category, old_nodes in (('nodes_vehicle', baseline.vehicle_nodes), ('nodes_ped', baseline.ped_nodes)):
        mesh = meshes.get(category)
        if mesh is None:
            old_offset += len(old_nodes)
            continue
        slots = mesh_origins(mesh, old_nodes)
        order = sorted(range(len(slots)), key=lambda i: (slots[i] is None, slots[i] if slots[i] is not None else i))
        local_to_output = {local: len(nodes) + i for i, local in enumerate(order)}
        adjacency = [[] for _ in slots]
        for a, b in mesh['edges']:
            if not 0 <= a < len(slots) or not 0 <= b < len(slots) or a == b:
                raise ValueError('Invalid live NODES edge')
            adjacency[a].append(b)
            adjacency[b].append(a)
            edges.add(tuple(sorted((local_to_output[a], local_to_output[b]))))
        templates = list(slots)
        queue = [i for i, slot in enumerate(slots) if slot is not None]
        for local in queue:
            for neighbor in adjacency[local]:
                if templates[neighbor] is None:
                    templates[neighbor] = templates[local]
                    queue.append(neighbor)
        for local in order:
            slot, template = slots[local], templates[local]
            if template is None and old_nodes:
                template = 0
            node = replace(old_nodes[template]) if template is not None else P.PathNode(
                flags=0x000F0000, node_type=1, path_width=8, is_vehicle=category == 'nodes_vehicle')
            point = mesh['world'][local]
            if slot is None:
                if P.get_area_id(int(point[0] * 8) / 8, int(point[1] * 8) / 8) != area:
                    raise ValueError('New NODES point lies outside its region; add it to the correct region mesh')
                node.area_id = area
                node.flags &= ~(15 | (1 << 4) | (1 << 6) | 0x00F00000)
                node.is_vehicle = category == 'nodes_vehicle'
            node.x, node.y, node.z = point
            if original.fla4:
                node.spawn_probability, node.speed_limit_kmh, node.lane_count_override = [int(v * 8) for v in point]
            nodes.append(node)
            origins.append(None if slot is None else old_offset + slot)
        if category == 'nodes_vehicle':
            vehicle_count = len(mesh['world'])
        old_offset += len(old_nodes)
    result, remap, changed = rebuild_graph(baseline, nodes, origins, edges, area=area, vehicle_count=vehicle_count)
    result.node_remap, result.topology_changed, result.original_node_indices = remap, changed, origins
    return result


def collect_owner(owner, original, record):
    meshes = {}
    source = record.get('source')
    if not source or record.get('identity_version') != 1:
        raise ValueError('Reimport this NODES region: the older scene has no stable vertex identities')
    for node in owner.children:
        category = W.path_type(node)
        if category in ('nodes_vehicle', 'nodes_ped', 'nodes_navi'):
            if category in meshes:
                raise ValueError('Select one imported mesh per NODES category and region')
            meshes[category] = read_mesh(node, source)
    match = re.fullmatch(r'nodes(\d+)\.dat', record['filename'], re.I)
    if not match:
        raise ValueError('Cannot identify a NODES region')
    return collect_graph(original, meshes, int(match[1]))
