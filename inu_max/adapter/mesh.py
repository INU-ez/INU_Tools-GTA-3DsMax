# INU Tools (Max) — адаптер меша: структуры ядра → объект 3ds Max (pymxs).
#
# Фаза 1: геометрия (вершины + грани) + выравнивание намотки по авторским
# нормалям (чтобы не было чёрных «вывернутых» граней от triangle-strip
# намотки GTA) + трансформ фрейма. UV, материалы, гладкие нормали, скелет и
# иерархия фреймов — следующими итерациями.
#
# Системы координат: GTA и Max оба Z-up → вершины напрямую. Индексы граней
# в ядре 0-based → в Max 1-based (+1). frame.rotation — 3 строки-оси
# (RW row-major) = формат Max Matrix3.

import pymxs

try:
    import numpy as _np
except Exception:                                      # noqa: BLE001
    _np = None


def _prepare_tris(geom):
    """Вернуть (tris, mat_ids): список (a,b,c) 0-based + индекс материала на
    каждую грань. Подготовка как в Blender-импорте:

      • есть авторские нормали → выровнять НАМОТКУ по ним;
      • нет нормалей (карты) → выбросить ТОЛЬКО вырожденные грани, дубликаты
        сохранить (двусторонние стены), намотку не трогать (в Blender так же).

    Без numpy — намотка как в файле, все грани."""
    tris = geom.triangles
    n_verts = len(geom.vertices)
    has_normals = (bool(getattr(geom, 'normals', None))
                   and len(geom.normals) == n_verts)

    if _np is None:
        return ([(int(t.a), int(t.b), int(t.c)) for t in tris],
                [int(t.material) for t in tris])

    tri = _np.array([(t.a, t.b, t.c) for t in tris], dtype=_np.int64)
    mat = _np.array([int(t.material) for t in tris], dtype=_np.int64)
    V = _np.asarray(geom.vertices, dtype=_np.float64).reshape(-1, 3)

    if has_normals:
        a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
        N = _np.asarray(geom.normals, dtype=_np.float64).reshape(-1, 3)
        face_n = _np.cross(V[b] - V[a], V[c] - V[a])
        vert_n = N[a] + N[b] + N[c]
        flip = _np.einsum('ij,ij->i', face_n, vert_n) < 0.0
        tri[flip, 1], tri[flip, 2] = tri[flip, 2].copy(), tri[flip, 1].copy()
        return ([tuple(int(x) for x in row) for row in tri], mat.tolist())

    if len(tri) == 0:
        return [], []
    vkey = _np.round(V, 4)
    _, vclass = _np.unique(vkey, axis=0, return_inverse=True)
    tcls = vclass[tri]
    pa, pb, pc = tcls[:, 0], tcls[:, 1], tcls[:, 2]
    valid = (pa != pb) & (pb != pc) & (pa != pc)
    tri = tri[valid]
    mat = mat[valid]
    return ([tuple(int(x) for x in row) for row in tri], mat.tolist())


def _mat_name(dm, i):
    tex = getattr(dm, 'texture', None)
    nm = getattr(tex, 'name', '') if tex is not None else ''
    return nm or ("mat_%d" % i)


def _apply_materials(rt, node, geom, mat_ids, tex_map=None):
    """Multi-material из geom.materials (цвет + имя + двусторонность),
    назначение material-id на каждую грань и — если найдена текстура в
    tex_map {имя.lower(): путь_png} — diffuse-bitmap."""
    tex_map = tex_map or {}
    mats = geom.materials or []
    if not mats:
        mtl = rt.StandardMaterial(name="dff_mtl")
        mtl.twoSided = True
        mtl.diffuse = rt.color(180, 180, 180)
        node.material = mtl
        return

    _unmatched = []
    mm = rt.MultiMaterial(numsubs=len(mats))
    for i, dm in enumerate(mats):
        std = rt.StandardMaterial(name=_mat_name(dm, i))
        std.twoSided = True
        c = getattr(dm, 'color', None)
        if c is not None:
            std.diffuse = rt.color(float(c.r), float(c.g), float(c.b))
        # diffuse-текстура по имени текстуры материала
        tex = getattr(dm, 'texture', None)
        tname = (getattr(tex, 'name', '') or '').lower() if tex is not None else ''
        png = tex_map.get(tname)
        if tname and not png:
            _unmatched.append(tname)
        if png:
            try:
                bt = rt.Bitmaptexture(fileName=png)
                std.diffuseMap = bt
                std.showInViewport = True
            except Exception as e:                     # noqa: BLE001
                print("[INU mesh] bitmap '%s' failed: %r" % (tname, e))
        # setSubMtl — 1-based, задаёт и позицию, и Material ID слота
        # (надёжнее прямого присваивания materialList из pymxs).
        try:
            rt.setSubMtl(mm, i + 1, std)
        except Exception as e:                         # noqa: BLE001
            print("[INU mesh] submat %d failed: %r" % (i, e))
    node.material = mm

    if _unmatched:
        print("[INU tex] БЕЗ текстуры (%d): %s | доступно в TXD: %s"
              % (len(set(_unmatched)), sorted(set(_unmatched)),
                 sorted(tex_map.keys())))

    # material-id на грань (1-based). Клампим на всякий в диапазон.
    nsub = len(mats)
    for fi, mid in enumerate(mat_ids):
        _id = int(mid) + 1
        if _id < 1:
            _id = 1
        elif _id > nsub:
            _id = nsub
        rt.setFaceMatID(node, fi + 1, _id)
    rt.update(node)


def _frame_matrix(rt, frame):
    """Matrix3 из DffFrame. rotation — ПЛОСКИЙ кортеж 9 float (row-major
    3×3, RW), position — xyz. Строки-оси идут r[0:3], r[3:6], r[6:9]."""
    if frame is None or not getattr(frame, 'rotation', None):
        return None
    r = frame.rotation
    if len(r) < 9:
        return None
    p = frame.position or (0.0, 0.0, 0.0)
    P3 = rt.Point3
    return rt.Matrix3(P3(float(r[0]), float(r[1]), float(r[2])),
                      P3(float(r[3]), float(r[4]), float(r[5])),
                      P3(float(r[6]), float(r[7]), float(r[8])),
                      P3(float(p[0]), float(p[1]), float(p[2])))


def build_object_from_geometry(geom, frame, name, tex_map=None):
    """Создать Editable Mesh в сцене Max из DffGeometry. Возвращает узел
    (или None, если даже базовое построение не удалось). tex_map — карта
    {имя_текстуры.lower(): путь_png} для diffuse-bitmap."""
    rt = pymxs.runtime
    P3 = rt.Point3

    verts = [P3(float(v[0]), float(v[1]), float(v[2])) for v in geom.vertices]
    tris, mat_ids = _prepare_tris(geom)
    faces = [P3(a + 1, b + 1, c + 1) for (a, b, c) in tris]

    # Базовое построение — если упадёт тут, объекта нет (пробрасываем).
    node = rt.mesh(vertices=rt.Array(*verts), faces=rt.Array(*faces))

    # Дальше — best-effort: объект уже в сцене, отдельные шаги не должны
    # «терять» его при сбое.
    try:
        node.name = name or "dff_mesh"
    except Exception:                                  # noqa: BLE001
        pass
    try:
        mat = _frame_matrix(rt, frame)
        if mat is not None:
            node.transform = mat
    except Exception as e:                             # noqa: BLE001
        print("[INU mesh] transform '%s' failed: %r" % (name, e))
    # UV (первый слой): GTA V сверху → в Max флипаем (1 − v).
    try:
        _apply_uv(rt, node, geom, tris)
    except Exception as e:                             # noqa: BLE001
        print("[INU mesh] UV '%s' failed: %r" % (name, e))

    # Multi-material из geom.materials (цвет/имя/двусторонность) + per-face id
    # + diffuse-текстуры из tex_map.
    try:
        _apply_materials(rt, node, geom, mat_ids, tex_map)
    except Exception as e:                             # noqa: BLE001
        print("[INU mesh] materials '%s' failed: %r" % (name, e))

    try:
        rt.update(node)
    except Exception:                                  # noqa: BLE001
        pass
    return node


def _apply_uv(rt, node, geom, tris):
    """Первый UV-слой (map channel 1). GTA хранит UV per-vertex → tv-грани
    совпадают с гранями. V флипаем (1 − v): GTA top-origin → Max."""
    if not geom.uv_layers or not geom.uv_layers[0]:
        return
    uv = geom.uv_layers[0]
    n = len(uv)
    rt.setNumTVerts(node, n)
    for i in range(n):
        t = uv[i]
        rt.setTVert(node, i + 1, float(t.u), 1.0 - float(t.v), 0.0)
    rt.buildTVFaces(node)
    for i, (a, b, c) in enumerate(tris):
        rt.setTVFace(node, i + 1, a + 1, b + 1, c + 1)
    rt.update(node)
