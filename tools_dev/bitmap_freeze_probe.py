# INU Tools — диагностика: какой шаг подключения текстуры вешает Max.
# Запуск в 3ds Max: Scripting → Run Script… → этот файл. Результат — в
# MAXScript Listener (строки [probe]). Создаёт один Box, в конце удаляет.
import glob
import time

import pymxs

rt = pymxs.runtime
PNG_DIR = r"F:\AllDFF\lae2_ground10_textures"


def step(label, fn):
    t = time.perf_counter()
    r = fn()
    print("[probe] %-38s %6.2fs" % (label, time.perf_counter() - t))
    return r


pngs = sorted(glob.glob(PNG_DIR + r"\*.png"))[:5]
print("[probe] PNG:", len(pngs), "from", PNG_DIR)

# настройки путей Max, которые трогают поиск файлов
try:
    n = rt.mapPaths.count()
    print("[probe] map paths (%d):" % n,
          [str(rt.mapPaths.get(i + 1)) for i in range(n)][:20])
except Exception as e:                                 # noqa: BLE001
    print("[probe] map paths: %r" % e)

box = step("create box", lambda: rt.Box())
step("redraw (empty material)", rt.completeRedraw)

bmps = [step("Bitmaptexture #%d" % i, lambda p=p: rt.Bitmaptexture(fileName=p))
        for i, p in enumerate(pngs)]
mat = rt.StandardMaterial(name="probe")
step("assign diffuseMap", lambda: setattr(mat, 'diffuseMap', bmps[0]))
step("assign material to box", lambda: setattr(box, 'material', mat))
step("redraw (map, not shown)", rt.completeRedraw)
step("showInViewport = True", lambda: setattr(mat, 'showInViewport', True))
step("redraw (map shown)", rt.completeRedraw)

mm = rt.MultiMaterial(numsubs=len(bmps))
for i, b in enumerate(bmps):
    s = rt.StandardMaterial(name="probe_%d" % i)
    s.diffuseMap = b
    s.showInViewport = True
    rt.setSubMtl(mm, i + 1, s)
step("assign Multi (%d shown maps)" % len(bmps), lambda: setattr(box, 'material', mm))
step("redraw (multi)", rt.completeRedraw)

step("delete box", lambda: rt.delete(box))
step("redraw (after delete)", rt.completeRedraw)
print("[probe] done")
