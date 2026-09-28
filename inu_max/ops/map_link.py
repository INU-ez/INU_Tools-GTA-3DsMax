# INU Tools (Max) — связь объектов сцены со строками IDE / IPL (порт
# ops/map_link.py Blender-версии INU).
#
# Строка файла ищется по «якорю» — тому, что объект помнит о своей строке
# (id, имя, позиция, поворот), а не по номеру строки: номера сдвигаются от
# любой правки файла. В Blender якорь — obj.inu.*, здесь — user properties
# узла «inu_<ключ>» (как все свойства INU в Max).
#
# Отличия от Blender: владелец строки (ipl_owner) — handle узла, а не имя
# (в Max имена могут повторяться); LOD-партнёр (lod_object) — тоже handle.
# Позиция и поворот якоря пишутся с полной точностью (repr), иначе строку
# далеко от центра карты не найти.

import math
import os
import uuid

PREFIX = 'inu_'


def norm(p):
    """Путь для сравнения (как norm INU): абсолютный, регистр Windows."""
    return os.path.normcase(os.path.abspath(p)) if p else ''


def fmt(v):
    """Значение для буфера user properties (как пишут setUserProp /
    selection.put_field): строки и векторы — в кавычках."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, (tuple, list)):
        return '"%s"' % ",".join(repr(float(x)) for x in v)
    return '"%s"' % str(v).replace('"', "'")


def buffer_props(d):
    """{ключ: значение} → {inu_ключ: текст для буфера}."""
    return {PREFIX + k: fmt(v) for k, v in d.items()}


# ── поля связи (что пишет импорт; Add / Sync — во 2-й части) ─────────

IPL_CLEAR = {
    'ipl_uuid': '', 'ipl_target_file': '', 'ipl_last_model_id': 0,
    'ipl_last_name': '', 'ipl_last_pos': (0.0, 0.0, 0.0),
    'ipl_last_rot': (0.0, 0.0, 0.0, 1.0), 'ipl_owner': 0, 'lod_index': -1,
}

IDE_CLEAR = {
    'ide_linked': False, 'ide_target_file': '', 'ide_last_model_id': 0,
    'ide_last_name': '', 'ide_last_draw_distance': 0.0,
    'ide_last_txd_name': '', 'ide_last_flags': 0,
}


def ipl_stamp(path, inst, lod_index=None):
    """Якорь строки IPL (stamp_ipl INU): новый uuid, файл, id / имя /
    позиция / поворот строки (кватернион — как в файле, x y z w).
    ipl_owner (handle узла) ставит тот, кто знает узел."""
    d = {
        'ipl_uuid': uuid.uuid4().hex, 'ipl_target_file': norm(path),
        'ipl_last_model_id': int(inst.model_id), 'ipl_last_name': inst.model_name,
        'ipl_last_pos': (float(inst.pos_x), float(inst.pos_y), float(inst.pos_z)),
        'ipl_last_rot': (float(inst.rot_x), float(inst.rot_y), float(inst.rot_z),
                         float(inst.rot_w)),
    }
    if lod_index is not None:
        d['lod_index'] = int(lod_index)
    return d


def ide_stamp(path, entry):
    """Связь со строкой IDE (stamp_ide INU): файл и значения строки на момент
    связи — по ним статус показывает «изменено»."""
    return {
        'ide_linked': True, 'ide_target_file': norm(path),
        'ide_last_model_id': int(entry.model_id), 'ide_last_name': entry.model_name,
        'ide_last_draw_distance': float(entry.draw_distance),
        'ide_last_txd_name': entry.txd_name, 'ide_last_flags': int(entry.flags),
    }


# ── строка IPL ↔ матрица узла ────────────────────────────────────────
# Кватернион IPL (x, y, z, w) — это ровно node.transform.rotationpart Max
# (проверено в Max: строки [0,1,0] [-1,0,0] [0,0,1] = +90° по Z → (0, 0,
# −0.7071, 0.7071), как пишет INU). Строки матрицы Max = строки обычной
# матрицы поворота этого кватерниона, без сопряжения.

def quat_rows(x, y, z, w):
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def inst_rows(inst, with_scale=False):
    """12 чисел матрицы Max (3 строки поворота + позиция) строки IPL.
    with_scale — масштаб строки (III / VC; в SA его нет)."""
    rows = quat_rows(inst.rot_x, inst.rot_y, inst.rot_z, inst.rot_w)
    if with_scale:
        for r, s in zip(rows, (inst.scale_x, inst.scale_y, inst.scale_z)):
            for k in range(3):
                r[k] *= float(s)
    return [c for r in rows for c in r] + [float(inst.pos_x), float(inst.pos_y),
                                           float(inst.pos_z)]


def mul_rows(a, b):
    """Произведение матриц Max a·b (12 чисел: строки поворота + позиция)."""
    out = []
    for i in range(3):
        for j in range(3):
            out.append(sum(a[i * 3 + k] * b[k * 3 + j] for k in range(3)))
    for j in range(3):
        out.append(sum(a[9 + k] * b[k * 3 + j] for k in range(3)) + b[9 + j])
    return out
