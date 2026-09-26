# INU Tools (Max) — проверки имён фреймов машины / педа и пар _ok/_dam
# (как ops/frame_hierarchy.py и tools/vehicle_scale.py в Blender-версии).
# Чистый Python: на входе — имена фреймов.

import re

# Имена из gta_sa.exe 1.0 US (RwObjectNameIdAssocation, CClumpModelInfo::
# SetFrameIds; движок сравнивает _stricmp). Без колёсных dummy игра падает:
# CVehicleModelInfo::GetWheelPosn не проверяет null.
VEHICLE_FATAL = {
    'wheel_lf_dummy': "front-left wheel axle",
    'wheel_rf_dummy': "front-right wheel axle",
    'wheel_lb_dummy': "rear-left wheel axle",
    'wheel_rb_dummy': "rear-right wheel axle",
}
VEHICLE_WARN = {'chassis_dummy': "top-level dummy of the whole vehicle"}
BIKE_REQUIRED = {
    'chassis_dummy': "top-level dummy of the bike",
    'wheel_front': "front wheel",
    'wheel_rear': "rear wheel",
}
# Скелет педа — 25 имён, ped.ifp ищет их дословно.
PED_REQUIRED = (
    'Root', 'Pelvis', 'Spine', 'Spine1', 'Neck', 'Head',
    'Bip01 L Clavicle', 'L UpperArm', 'L Forearm', 'L Hand', 'L Finger',
    'Bip01 R Clavicle', 'R UpperArm', 'R Forearm', 'R Hand', 'R Finger',
    'L Thigh', 'L Calf', 'L Foot', 'L Toe0',
    'R Thigh', 'R Calf', 'R Foot', 'R Toe0',
    'Bip01',
)

# Суффикс копии: Blender «.001», Max «001». Имя фрейма пишется в DFF как
# есть — «wheel_lf_dummy001» движок не узнает.
_DUP_SUFFIX = re.compile(r"\.?\d{3}$")


def check_vehicle_names(names):
    """(fatal, warnings) — готовые строки «имя — пояснение»."""
    lower = {str(n).lower() for n in names}
    if 'wheel_front' in lower or 'wheel_rear' in lower:
        return [], ["%s — %s" % (n, d) for n, d in BIKE_REQUIRED.items()
                    if n not in lower]
    fatal, warnings = [], []
    for name, desc in VEHICLE_FATAL.items():
        if name in lower:
            continue
        near = next((k for k in lower if _DUP_SUFFIX.sub("", k) == name), None)
        if near:
            fatal.append("%s — present as \"%s\" — the suffix will go into "
                         "the DFF" % (name, near))
        else:
            fatal.append("%s — %s" % (name, desc))
    for name, desc in VEHICLE_WARN.items():
        if name not in lower:
            warnings.append("%s — %s" % (name, desc))
    for name in sorted(lower):
        if name == 'wheel':          # ванильный меш колеса, клонируется игрой
            continue
        if 'wheel' in name and not any(s in name for s in
                                       ('_lf', '_rf', '_lb', '_rb', '_lm', '_rm')):
            warnings.append("%s — wheel without _lf/_rf/_lb/_rb" % name)
    return fatal, warnings


def check_ped_names(names):
    """Имена скелета педа, которых нет (сравнение с учётом регистра)."""
    have = set(str(n) for n in names)
    return [n for n in PED_REQUIRED if n not in have]


def pair_report(names):
    """Пары _ok / _dam по базовому имени: (пары, одиночные _ok, одиночные
    _dam) — как vehicle_pair_report INU."""
    oks = {n[:-3]: n for n in names if n.endswith('_ok')}
    dams = {n[:-4]: n for n in names if n.endswith('_dam')}
    pairs = sorted((b, oks[b], dams[b]) for b in oks if b in dams)
    lonely_ok = sorted(oks[b] for b in oks if b not in dams)
    lonely_dam = sorted(dams[b] for b in dams if b not in oks)
    return pairs, lonely_ok, lonely_dam
