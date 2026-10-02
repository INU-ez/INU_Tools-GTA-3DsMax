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

# Engine names from the twelve SA vehicle tables, plus III/VC names.
VEHICLE_ENGINE_NAMES = set('aileron_l aileron_pos aileron_r backrotor bargrip boat_flap_left boat_flap_right boat_moving_hi boat_rearflap_left boat_rearflap_right boat_rudder_hi body_front_dummy body_rear_dummy bogie_front bogie_rear bonnet_dummy boot_dummy bump_front_dummy bump_rear_dummy chainset chassis chassis_dummy door_lf_dummy door_lhs_dummy door_lr_dummy door_rf_dummy door_rhs_dummy door_rr_dummy elevator_l elevator_pos elevator_r elevators engine exhaust exhaust_ok extra1 extra2 extra3 extra4 extra5 extra6 forks_front forks_rear gear_l gear_r handlebars headlights headlights2 hookup light_front light_left light_rear light_right light_tailplane loadbay misc_a misc_b misc_c misc_d misc_e miscpos_a miscpos_b miscpos_c miscpos_d moving_prop moving_prop2 moving_rotor moving_rotor2 mudguard ped_arm ped_backseat ped_frontseat ped_left_entry ped_mid_entry ped_right_entry pedal_l pedal_r petrolcap propeller rear_axle rudder rudder_pos skid_left skid_right static_prop static_prop2 static_rotor static_rotor2 suspension_lf suspension_rf tail taillights taillights2 topknot toprotor transmission_f transmission_r ug_backbullbar ug_bonnet ug_bonnet_dam ug_bonnet_left ug_bonnet_left_dam ug_bonnet_right ug_bonnet_right_dam ug_frontbullbar ug_lights ug_lights_dam ug_nitro ug_roof ug_spoiler ug_spoiler_dam ug_wing_left ug_wing_right wheel_front wheel_front_dummy wheel_lb1_dummy wheel_lb2_dummy wheel_lb3_dummy wheel_lb_dummy wheel_lf1_dummy wheel_lf2_dummy wheel_lf3_dummy wheel_lf_dummy wheel_lm_dummy wheel_rb1_dummy wheel_rb2_dummy wheel_rb3_dummy wheel_rb_dummy wheel_rear wheel_rear_dummy wheel_rf1_dummy wheel_rf2_dummy wheel_rf3_dummy wheel_rf_dummy wheel_rm_dummy windscreen windscreen_dummy windscreen_hi_ok wing_lf_dummy wing_lr_dummy wing_rf_dummy wing_rr_dummy wingtip_pos'.split())
ENGINE_NAMES = (VEHICLE_ENGINE_NAMES | set(VEHICLE_FATAL) | set(VEHICLE_WARN)
                | set(BIKE_REQUIRED) | {n.lower() for n in PED_REQUIRED})
ENGINE_TAILS = ('_dummy', '_ok', '_dam', '_vlo', '_hi', '_lo')
_DOT_DUP = re.compile(r'(?:\.\d+)+$')
_MAX_DUP = re.compile(r'^(.+?)(\d{3})$')


def game_frame_name(name):
    name = _DOT_DUP.sub('', str(name).strip())
    match = _MAX_DUP.match(name)
    if match:
        base = match.group(1)
        if base.lower() in ENGINE_NAMES or base.lower().endswith(ENGINE_TAILS):
            return base
    return name


# Audit also recognizes the Max copy suffix.
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
