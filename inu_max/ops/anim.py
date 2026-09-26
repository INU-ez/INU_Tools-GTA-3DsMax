# INU Tools (Max) — операции окна «IFP IO» на общем ядре: импорт IFP в
# библиотеку анимаций сцены и проверка round-trip (как import_ifp и
# ifp_roundtrip Blender-версии INU).


def import_ifp(path):
    """Как import_ifp INU: анимации файла — в библиотеку сцены (имя + путь
    .ifp), ключи читаются из файла при применении. Возвращает число
    анимаций файла."""
    from inu_gta_core.ifp import read_ifp
    from ..adapter import anim
    ifp = read_ifp(path)
    names = [a.name for a in ifp.animations]
    anim.library_add(path, ifp.name, ifp.source_format, names)
    return len(names)


def roundtrip(path):
    """(ok, отчёт) — как gtatools.ifp_roundtrip INU: read → write во
    временный файл → read и сравнение; исходный файл не меняется. ok=None —
    файл не прочитался (отчёт — текст ошибки)."""
    from inu_gta_core.ifp import roundtrip_test
    r = roundtrip_test(path)
    if r['error']:
        return None, "IFP round-trip: %s" % r['error']
    lines = [
        "Animations: %d → %d" % (r['anims_in'], r['anims_out']),
        "Bones: %d → %d" % (r['bones_in'], r['bones_out']),
        "Keys: %d → %d" % (r['keyframes_in'], r['keyframes_out']),
        "Max rotation delta: %.6f" % r['max_rot_delta'],
        "Max translation delta: %.6f" % r['max_trans_delta'],
        "Max time delta: %.6f" % r['max_time_delta'],
    ]
    lost = r['missing_anims']
    if lost:
        more = " (+%d)" % (len(lost) - 5) if len(lost) > 5 else ""
        lines.append("Lost animations: %s%s" % (", ".join(lost[:5]), more))
    if r['missing_bones']:
        lines.append("Animations with lost bones: %d" % len(r['missing_bones']))
    if r['kf_mismatches']:
        lines.append("Keyframe count mismatches: %d" % len(r['kf_mismatches']))
    ok = (r['anims_in'] == r['anims_out'] and r['bones_in'] == r['bones_out']
          and r['keyframes_in'] == r['keyframes_out'] and not lost
          and not r['missing_bones'] and not r['kf_mismatches'])
    text = ("Round-trip: OK ✓" if ok else "Round-trip: mismatches ⚠") \
        + "\n" + "\n".join(lines)
    print("\n[IFP Round-trip] %s\n%s" % (path, text))
    return ok, text
