"""Paint on a welded proxy; original topology and UV seams stay untouched."""
import math

from ..adapter import selection as S,scene_read as R


def weld_weights(points,weights,tolerance=1e-5):
    if len(points) != len(weights) or tolerance <= 0:
        raise ValueError("Matching vertex and weight counts and a positive tolerance are required")
    buckets={}
    positions=[]
    sums=[]
    counts=[]
    mapping=[]
    for point,vertex_weights in zip(points,weights):
        key=tuple(math.floor(c/tolerance) for c in point)
        match=None
        for x in (-1,0,1):
            for y in (-1,0,1):
                for z in (-1,0,1):
                    for index in buckets.get((key[0]+x,key[1]+y,key[2]+z),()):
                        if math.dist(point,positions[index])<=tolerance:
                            match=index
                            break
        if match is None:
            match=len(positions)
            positions.append(tuple(point))
            sums.append({})
            counts.append(0)
            buckets.setdefault(key,[]).append(match)
        mapping.append(match)
        counts[match]+=1
        for bone,weight in vertex_weights:
            sums[match][bone]=sums[match].get(bone,0)+weight
    averaged=[]
    for values in sums:
        values={b:w for b,w in values.items() if w>0}
        total=sum(values.values())
        averaged.append([(bone,value/total) for bone,value in sorted(values.items())] if total else [])
    return positions,averaged,mapping


def _skin(node):
    rt=S._rt()
    return next((m for m in node.modifiers if rt.classOf(m)==rt.Skin),None)


def _write_weights(node,weights):
    rt=S._rt()
    skin=_skin(node)
    if skin is None:
        raise ValueError('%s has no Skin modifier'%node.name)
    if any(not any(weight > 0 for _, weight in vertex) for vertex in weights):
        raise ValueError("Every Skin vertex must have a positive bone weight")
    old=list(rt.selection)
    mode=rt.getCommandPanelTaskMode()
    try:
        rt.setCommandPanelTaskMode(rt.Name('modify'))
        rt.select(node)
        rt.modPanel.setCurrentObject(skin)
        bones={str(rt.skinOps.GetBoneName(skin,i,0)):i for i in range(1,int(rt.skinOps.GetNumberBones(skin))+1)}
        if int(rt.skinOps.GetNumberVertices(skin))!=len(weights):
            raise ValueError('Skin vertex count changed: '+str(node.name))
        missing={name for vertex in weights for name,weight in vertex if weight>0 and name not in bones}
        if missing:
            raise ValueError('Missing Skin bones: '+', '.join(sorted(missing)))
        for i,vertex in enumerate(weights,1):
            entries=[(bones[name],weight) for name,weight in vertex if weight>0]
            rt.skinOps.ReplaceVertexWeights(skin,i,rt.Array(*[b for b,_ in entries]),rt.Array(*[w for _,w in entries]))
    finally:
        rt.select(rt.Array(*old))
        rt.setCommandPanelTaskMode(mode)


def _proxy():
    rt=S._rt()
    selected=S.active_node()
    if selected is not None and S.get_data(selected,'weight_merge',None):
        return selected
    return next((node for node in rt.geometry if S.get_data(node,'weight_merge',None)),None)


def weight_merge_start():
    import pymxs
    with pymxs.attime(0):
        return _weight_merge_start_at_rest()


def _weight_merge_start_at_rest():
    rt=S._rt()
    if _proxy() is not None:
        raise ValueError('Apply or roll back the existing weight proxy first')
    nodes=S.selected_meshes()
    if not nodes or any(_skin(n) is None for n in nodes):
        raise ValueError('Select meshes with Skin modifiers')
    points=[]
    weights=[]
    faces=[]
    originals=[]
    for node in nodes:
        vertex_weights=R.skin_data(node)
        mesh=rt.snapshotAsMesh(node)
        try:
            count=int(rt.getNumVerts(mesh))
            if count!=len(vertex_weights):
                raise ValueError('Modifiers above Skin changed the vertex count: '+str(node.name))
            offset=len(points)
            for i in range(1,count+1):
                p=rt.getVert(mesh,i)*node.transform
                points.append((float(p.x),float(p.y),float(p.z)))
            weights.extend(vertex_weights)
            for i in range(1,int(rt.getNumFaces(mesh))+1):
                f=rt.getFace(mesh,i)
                faces.append(tuple(int(v)-1+offset for v in (f.x,f.y,f.z)))
            originals.append(dict(handle=int(rt.getHandleByAnim(node)),offset=offset,count=count,hidden=bool(node.isHidden)))
        finally:
            rt.delete(mesh)
    positions,averaged,mapping=weld_weights(points,weights)
    bone_names={name for vertex in averaged for name,_weight in vertex}
    bone_nodes={name:rt.getNodeByName(name) for name in bone_names}
    if any(node is None for node in bone_nodes.values()):
        raise ValueError('Some Skin bone nodes cannot be found')
    merged_faces=[tuple(mapping[i]+1 for i in face) for face in faces]
    merged_faces=[face for face in merged_faces if len(set(face))==3]
    with S.undo_block('INU: Merge Weight Seams'):
        proxy=rt.mesh(name=rt.uniqueName('INU_WeightProxy'),vertices=rt.Array(*[rt.Point3(*p) for p in positions]),
                      faces=rt.Array(*[rt.Point3(*face) for face in merged_faces]))
        proxy.material=nodes[0].material
        skin=rt.Skin()
        rt.addModifier(proxy,skin)
        rt.setCommandPanelTaskMode(rt.Name('modify'))
        rt.select(proxy)
        rt.modPanel.setCurrentObject(skin)
        for i,name in enumerate(sorted(bone_names)):
            rt.skinOps.AddBone(skin,bone_nodes[name],1 if i==len(bone_names)-1 else 0)
        _write_weights(proxy,averaged)
        S.put_data([proxy],'weight_merge',dict(originals=originals,mapping=mapping,count=len(positions)))
        S.put_field([proxy],'weight_edit_backup','proxy')
        S.put_field([proxy],'type','NON')
        S.put_field([proxy],'preview',True)
        for node in nodes:
            node.isHidden=True
        rt.select(proxy)
    return 'INFO','Weight proxy: %d vertices → %d welded vertices'%(len(points),len(positions))


def _restore(apply):
    rt=S._rt()
    proxy=_proxy()
    if proxy is None:
        return 'WARNING','No active weight proxy'
    data=S.get_data(proxy,'weight_merge')
    originals=[]
    for record in data['originals']:
        node=rt.maxOps.getNodeByHandle(record['handle'])
        if node is None:
            raise ValueError('Original mesh was deleted; proxy retained')
        originals.append((node,record))
    weights=R.skin_data(proxy) if apply else None
    if apply and (weights is None or len(weights)!=data['count']):
        raise ValueError('Proxy topology changed; original meshes retained')
    with S.undo_block('INU: Restore Weight Seams'):
        for node,record in originals:
            if apply:
                indices=data['mapping'][record['offset']:record['offset']+record['count']]
                _write_weights(node,[weights[i] for i in indices])
            node.isHidden=record['hidden']
        rt.delete(proxy)
        rt.select(rt.Array(*[node for node,_ in originals]))
    rt.redrawViews()
    return 'INFO',('Applied weights and restored seams' if apply else 'Rolled back weight editing')


OPERATIONS={'weight_merge_start':weight_merge_start,'weight_merge_apply':lambda:_restore(True),
            'weight_merge_cancel':lambda:_restore(False)}
