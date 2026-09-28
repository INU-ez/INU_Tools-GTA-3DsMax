# INU Tools (Max) — авто-генерация коллизии из модели (порт ops/auto_col_ops.py
# INU): габаритный бокс (AABB) или выпуклая оболочка. Чистый Python + numpy,
# без сторонних библиотек (в Max нет scipy); сцену Max трогает
# adapter/col_scene.py.
#
# Треугольники — с внешней нормалью по правилу правой руки (как грани Max):
# нормаль (b − a) × (c − a) смотрит наружу. COL-экспорт сам развернёт обход
# под GTA.


def box(mn, mx):
    """(вершины, треугольники) осевого бокса mn..mx."""
    (x0, y0, z0), (x1, y1, z1) = mn, mx
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    quads = [(0, 3, 2, 1),      # низ (−Z)
             (4, 5, 6, 7),      # верх (+Z)
             (0, 1, 5, 4),      # −Y
             (1, 2, 6, 5),      # +X
             (2, 3, 7, 6),      # +Y
             (3, 0, 4, 7)]      # −X
    tris = []
    for a, b, c, d in quads:
        tris += [(a, b, c), (a, c, d)]
    return verts, tris


def bbox(points):
    xs, ys, zs = zip(*points)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def convex_hull(points, drop_slivers=True):
    """(вершины, треугольники) выпуклой оболочки или None, если точки лежат в
    одной плоскости / на прямой (тогда — бокс, как в INU). drop_slivers —
    убрать треугольники нулевой площади (три точки на одной прямой вдоль
    ребра модели): нормали у них нет, COL-экспорт их всё равно выбросит."""
    import numpy as np
    P = np.unique(np.round(np.asarray(points, dtype=np.float64).reshape(-1, 3), 6), axis=0)
    if len(P) < 4:
        return None
    size = float(np.ptp(P, axis=0).max())
    if size <= 0.0:
        return None
    eps = size * 1e-9

    # начальный тетраэдр из крайних точек
    i0 = int(np.argmin(P[:, 0]))
    i1 = int(np.argmax(np.linalg.norm(P - P[i0], axis=1)))
    d = P[i1] - P[i0]
    cr = np.cross(P - P[i0], d)
    i2 = int(np.argmax(np.linalg.norm(cr, axis=1)))
    if np.linalg.norm(cr[i2]) <= eps * max(np.linalg.norm(d), eps):
        return None                                   # всё на одной прямой
    nrm = np.cross(P[i1] - P[i0], P[i2] - P[i0])
    dist = (P - P[i0]) @ nrm
    i3 = int(np.argmax(np.abs(dist)))
    if abs(dist[i3]) <= eps * np.linalg.norm(nrm):
        return None                                   # всё в одной плоскости

    inside = P[[i0, i1, i2, i3]].mean(axis=0)

    # грани: списки + массивы нормалей/смещений с запасом (растут удвоением);
    # edge_face — направленное ребро → грань (соседи для обхода)
    faces, alive = [], []
    cap = 64
    N = np.zeros((cap, 3))
    D = np.zeros(cap)
    edge_face = {}

    def plane(f):
        a, b, c = P[f[0]], P[f[1]], P[f[2]]
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n)
        n = n / ln if ln > 0 else n
        return n, float(n @ a)

    def add(f):
        nonlocal N, D, cap
        k = len(faces)
        if k >= cap:
            cap *= 2
            N = np.vstack([N, np.zeros((cap - len(N), 3))])
            D = np.concatenate([D, np.zeros(cap - len(D))])
        n, off = plane(f)
        N[k], D[k] = n, off
        faces.append(f)
        alive.append(True)
        a, b, c = f
        for e in ((a, b), (b, c), (c, a)):
            edge_face[e] = k

    for f in ((i0, i1, i2), (i0, i3, i1), (i1, i3, i2), (i2, i3, i0)):
        n, off = plane(f)
        add(f if n @ inside - off < 0 else (f[0], f[2], f[1]))

    # сначала дальние точки: внутренние потом отсеиваются одной проверкой
    order = np.argsort(-np.linalg.norm(P - inside, axis=1))
    for pi in order:
        pi = int(pi)
        if pi in (i0, i1, i2, i3):
            continue
        cnt = len(faces)
        dist = N[:cnt] @ P[pi] - D[:cnt]
        dist[~np.asarray(alive)] = -np.inf
        start = int(np.argmax(dist))
        if dist[start] <= eps:
            continue                                  # точка внутри
        # видимая область — СВЯЗНАЯ, обходом соседей от самой видимой грани
        # (иначе почти компланарные грани рвут её на куски и оболочка
        # теряет выпуклость)
        visible, stack = {start}, [start]
        while stack:
            a, b, c = faces[stack.pop()]
            for u, v in ((a, b), (b, c), (c, a)):
                g = edge_face.get((v, u))
                if g is not None and g not in visible and dist[g] > eps:
                    visible.add(g)
                    stack.append(g)
        horizon = []
        for k in visible:
            a, b, c = faces[k]
            for u, v in ((a, b), (b, c), (c, a)):
                if edge_face.get((v, u)) not in visible:
                    horizon.append((u, v))
        for k in visible:
            alive[k] = False
            a, b, c = faces[k]
            for e in ((a, b), (b, c), (c, a)):
                if edge_face.get(e) == k:
                    del edge_face[e]
        for u, v in horizon:
            add((u, v, pi))

    live = [faces[k] for k in range(len(faces)) if alive[k]]
    if drop_slivers:
        tiny = (size * 1e-6) ** 2
        live = [f for f in live
                if np.linalg.norm(np.cross(P[f[1]] - P[f[0]], P[f[2]] - P[f[0]])) > tiny]
    used = sorted({i for f in live for i in f})
    remap = {old: new for new, old in enumerate(used)}
    verts = [tuple(float(x) for x in P[i]) for i in used]
    tris = [(remap[a], remap[b], remap[c]) for a, b, c in live]
    return verts, tris


def make(points, mode):
    """(вершины, треугольники, фактический режим) для CONVEX | BOX; пустой
    или плоский меш у выпуклой оболочки → бокс (как _make_col_object INU)."""
    if not points:
        return None
    if mode == 'CONVEX':
        hull = convex_hull(points)
        if hull is not None:
            return hull[0], hull[1], 'CONVEX'
    mn, mx = bbox(points)
    v, t = box(mn, mx)
    return v, t, 'BOX'
