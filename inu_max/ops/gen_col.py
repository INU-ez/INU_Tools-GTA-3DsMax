# INU Tools (Max) — «Generate COL» окна DFF IO (порт ops/auto_col_ops.py INU).
#
# Выделяешь модели → создаётся редактируемый <имя>_COL: выпуклая оболочка или
# габаритный бокс по вершинам модели (в её системе координат), с её
# трансформом и в её слое; тип COL — дальше идёт в обычный COL-экспорт. Если
# <имя>_COL уже есть — у него заменяется геометрия (перегенерация), а
# сохранённые границы старого COL сбрасываются (новая форма).

import pymxs


def generate(mode):
    """mode: 'CONVEX' | 'BOX'. Возвращает [(имя COL, фактический режим)]."""
    from .auto_col import make
    from .dff_export import groups
    from ..adapter import scene_build, scene_read as sr
    from ..adapter.selection import put_field, set_prop
    rt = pymxs.runtime
    scene_build._ensure()
    made = []
    for base, models in groups().items():
        src = models['DFF'] or models['LOD'] or models['COL']
        if src is None:
            continue
        cname = base + "_COL"
        if str(src.name).lower() == cname.lower():
            continue                            # источник сам является COL
        with sr.full_result():               # вершины модели — целиком
            verts_src = sr.mesh_verts(src)
        res = make(verts_src, mode)
        if res is None:
            continue
        verts, tris, used = res
        flat_v = [float(x) for v in verts for x in v]
        flat_f = [i + 1 for t in tris for i in t]
        old = rt.getNodeByName(cname)            # без учёта регистра
        if old is not None and rt.superClassOf(old) == rt.GeometryClass:
            obj = rt.inuSetMeshData(old, flat_v, flat_f)
            set_prop([obj], 'col_bounds', '""')     # новая форма — границы заново
        else:
            obj = rt.inuMakeMesh(flat_v, flat_f, [1] * len(tris))
            obj.name = cname
            obj.transform = src.transform
            try:
                src.layer.addNode(obj)
            except Exception:                      # noqa: BLE001
                pass
            obj.xray = True
        put_field([obj], 'type', 'COL')
        made.append((cname, used))
    rt.completeRedraw()
    return made
