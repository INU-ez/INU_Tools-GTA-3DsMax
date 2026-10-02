"""Run inside a fresh empty 3ds Max scene; writes only beneath output_dir.

This file is not an automatic unit test. It exercises native poly/VData,
subobject-mode reads, saved .max identities and export roundtrip.
"""
import os
from pathlib import Path


def run(output_dir):
    from pymxs import runtime as rt
    from inu_gta_core import paths as P
    from inu_gta_core.paths_graph import graph_edges, navi_address
    from inu_max.ops import node_tools as N
    from inu_max.ops.path_nodes_mesh import identity_token
    from inu_max.adapter import selection as S, world as W
    if list(rt.objects):
        raise ValueError('Open a fresh empty scene before running native NODES checks')
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = root/'source'
    source.mkdir(exist_ok=True)
    nf = P.NodesFile(vehicle_nodes=[
        P.PathNode(x=800, y=100, area_id=37, node_id=0, flags=1, path_width=8),
        P.PathNode(x=820, y=100, area_id=37, node_id=1, flags=1, link_id=1, path_width=8)],
        navi_nodes=[P.NaviNode(x=810, y=100, area_id=37, node_id=0, dir_x=-100,
            flags=P.encode_navi_flags(left_lanes=0, right_lanes=2))],
        links=[P.PathLink(37, 1), P.PathLink(37, 0)],
        navi_links=[navi_address(37, 0)]*2, link_lengths=[20, 20],
        path_intersections=[0]*194, parsed_extras=True)
    P.write_nodes(str(source/'nodes37.dat'), nf)
    P.write_nodes(str(source/'nodes36.dat'), P.NodesFile(parsed_extras=True))
    N.import_nodes([str(source/'nodes37.dat'), str(source/'nodes36.dat')])
    owners = [o for o in rt.helpers if S.get_data(o, 'nodes_file', None)]
    owner = next(o for o in owners if S.get_data(o, 'nodes_file', {})['filename'] == 'nodes37.dat')
    vehicle = next(o for o in owner.children if W.path_type(o) == 'nodes_vehicle')
    metadata = S.get_data(vehicle, 'nodes_identity', {})
    assert len(metadata['channels']) == 2
    assert int(vehicle.baseObject.GetNumEdges()) == 1
    rt.select(vehicle)
    rt.setCommandPanelTaskMode(rt.Name('modify'))
    rt.modPanel.setCurrentObject(vehicle.baseObject)
    rt.subObjectLevel = 1
    vertex = int(rt.polyop.createVert(vehicle.baseObject, rt.Point3(840, 100, 0)))
    for channel, value in zip(metadata['channels'], identity_token(1)):
        rt.polyop.setVDataValue(vehicle.baseObject, channel, vertex, float(value))
    vehicle.baseObject.createEdge(2, vertex)
    rt.update(vehicle)
    # Read while the Editable Poly vertex level is still active.
    files = N._scene_files([owner])
    edited = files[0][1]
    assert graph_edges(edited, 37) == {(0, 1), (1, 2)}
    assert len(edited.navi_nodes) == 2
    N.export_nodes(str(root/'export'))
    back = P.read_nodes(str(root/'export'/'nodes37.dat'))
    assert graph_edges(back, 37) == {(0, 1), (1, 2)}
    rt.subObjectLevel = 0
    save = root/'nodes_identity.max'
    if not rt.saveMaxFile(str(save), quiet=True):
        raise RuntimeError('Native .max save failed')
    if not rt.loadMaxFile(str(save), quiet=True):
        raise RuntimeError('Native .max reload failed')
    owner = next(o for o in rt.helpers if S.get_data(o, 'nodes_file', {}).get('filename') == 'nodes37.dat')
    edited = N._scene_files([owner])[0][1]
    assert graph_edges(edited, 37) == {(0, 1), (1, 2)}
    print('[INU] Native Compiled NODES smoke checks passed: live poly, VData, empty region, save/reload, DAT')
    return str(root)
