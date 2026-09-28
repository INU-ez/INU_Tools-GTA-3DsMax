# INU Tools — диагностика v2: зависает ли Max ПОСЛЕ подключения НОВЫХ
# (ни разу не открытых) PNG и зависит ли это от папки / вьюпорта.
# Запуск: Scripting → Run Script… → этот файл. Идёт ~1–3 минуты сам, результат —
# строки [probe2] в MAXScript Listener. Max можно не трогать.
#
# Варианты (каждый — свежие копии PNG с новыми именами):
#   A — новые PNG рядом с моделями (F:\AllDFF\...), показаны во вьюпорте
#   B — новые PNG во временной папке Windows, показаны во вьюпорте
#   C — новые PNG рядом с моделями, только Bitmaptexture (без материала)
import glob
import os
import shutil
import tempfile
import time

import pymxs
from PySide6 import QtCore

rt = pymxs.runtime
SRC = sorted(glob.glob(r"F:\AllDFF\lae2_ground10_textures\*.png"))[:5]
STAMP = time.strftime('%H%M%S')
DIRS = {'A': r"F:\AllDFF\_inu_probe_A_" + STAMP,
        'B': os.path.join(tempfile.gettempdir(), "_inu_probe_B_" + STAMP),
        'C': r"F:\AllDFF\_inu_probe_C_" + STAMP}


def log(msg):
    print("[probe2] " + msg)


class Probe(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.order = ['A', 'B', 'C']
        self.nodes = []
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.tick)
        self.cur = None
        self.start_next()

    def fresh(self, key):
        d = DIRS[key]
        os.makedirs(d, exist_ok=True)
        out = []
        for i, p in enumerate(SRC):
            q = os.path.join(d, "probe%s_%s_%d.png" % (key, STAMP, i))
            shutil.copyfile(p, q)
            out.append(q)
        return out

    def start_next(self):
        if not self.order:
            self.finish()
            return
        key = self.order.pop(0)
        files = self.fresh(key)
        t = time.perf_counter()
        bmps = [rt.Bitmaptexture(fileName=f) for f in files]
        if key in ('A', 'B'):
            mm = rt.MultiMaterial(numsubs=len(bmps))
            for i, b in enumerate(bmps):
                s = rt.StandardMaterial(name="probe2_%s_%d" % (key, i))
                s.diffuseMap = b
                s.showInViewport = True
                rt.setSubMtl(mm, i + 1, s)
            box = rt.Box(pos=rt.Point3(len(self.nodes) * 60.0, 0, 0))
            box.material = mm
            self.nodes.append(box)
            rt.completeRedraw()
        log("%s: set up in %.2fs (%s)" % (key, time.perf_counter() - t, DIRS[key]))
        self.cur = dict(key=key, t0=time.perf_counter(), last=time.perf_counter(),
                        worst=0.0, total=0.0, calm=time.perf_counter())
        self.timer.start()

    def tick(self):
        c = self.cur
        now = time.perf_counter()
        gap = now - c['last'] - 0.25
        c['last'] = now
        if gap > 0.5:
            c['worst'] = max(c['worst'], gap)
            c['total'] += gap
            c['calm'] = now
        # вариант закончен: 8 с без зависаний подряд (или 90 с всего)
        if now - c['calm'] > 8 or now - c['t0'] > 90:
            self.timer.stop()
            log("%s: Max froze %.1fs in total (longest %.1fs)"
                % (c['key'], c['total'], c['worst']))
            QtCore.QTimer.singleShot(500, self.start_next)

    def finish(self):
        for n in self.nodes:
            try:
                rt.delete(n)
            except Exception:                          # noqa: BLE001
                pass
        rt.completeRedraw()
        log("done — folders left for inspection: %s" % ", ".join(DIRS.values()))


# держим ссылку в builtins: глобалы скрипта Run Script может выбросить,
# а с ними и таймеры
import builtins  # noqa: E402
builtins._inu_probe2 = Probe()
