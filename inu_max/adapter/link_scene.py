# INU Tools (Max) — сцена Max для связи со строками IDE / IPL (Map IO,
# вкладка Export): индекс узлов с их user properties, чтение / запись
# свойств, мировые матрицы.
#
# Индекс — одним вызовом MAXScript на всю геометрию (поэлементные вызовы
# pymxs медленные, а у карты тысячи узлов): узел, handle, имя, буфер user
# properties, верхний предок и глубина (под-меши одной модели).
# Значения свойств — как их пишут импорт и map_link.fmt: строки и векторы в
# кавычках, числа и true / false как есть.

from .selection import _rt

PREFIX = 'inu_'

_MXS = r'''
global inuLinkIndex
fn inuLinkIndex = (
    local lnkNodes = #(), lnkHandles = #(), lnkNames = #(), lnkBufs = #()
    local lnkTops = #(), lnkDepths = #()
    for o in geometry do (
        append lnkNodes o
        append lnkHandles o.inode.handle
        append lnkNames o.name
        append lnkBufs (getUserPropBuffer o)
        local t = o
        local d = 0
        while t.parent != undefined do (t = t.parent; d += 1)
        append lnkTops t.inode.handle
        append lnkDepths d
    )
    #(lnkNodes, lnkHandles, lnkNames, lnkBufs, lnkTops, lnkDepths)
)
global inuLinkBufs
fn inuLinkBufs = (
    -- буферы узлов со связью (для слежения за IDE / IPL). Путь читает
    -- Python из буфера: getUserProp разбирает значение как литерал MAXScript
    -- и портит обратные слэши пути
    local lnkOut = #()
    for o in geometry do (
        local b = getUserPropBuffer o
        if (findString b "_target_file") != undefined do append lnkOut b
    )
    lnkOut
)
'''
_READY = []


def ensure():
    if not _READY:
        _rt().execute(_MXS)
        _READY.append(True)


def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        return v[1:-1]
    return v


def typed(raw, default):
    """Текст значения из буфера → тип default (как selection.get_field)."""
    if raw is None:
        return default
    v = _unquote(str(raw))
    try:
        if isinstance(default, bool):
            return v.lower() in ('true', '1', 'yes', 'on')
        if isinstance(default, int):
            return int(float(v))
        if isinstance(default, float):
            return float(v)
        if isinstance(default, tuple):
            vals = tuple(float(x) for x in v.split(',')) if v else ()
            return vals if len(vals) == len(default) else default
    except (TypeError, ValueError):
        return default
    return v


def fmt(v):
    """Значение → текст user property (строки и векторы — в кавычках)."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, (tuple, list)):
        return '"%s"' % ",".join(repr(float(x)) for x in v)
    return '"%s"' % str(v).replace('"', "'")


class Rec:
    """Узел сцены и его свойства INU (на момент индекса + то, что записано
    за операцию)."""

    __slots__ = ('node', 'handle', 'name', 'props', 'top', 'depth')

    def __init__(self, node, handle, name, props, top, depth):
        self.node = node
        self.handle = int(handle)
        self.name = str(name)
        self.props = props
        self.top = int(top)
        self.depth = int(depth)

    def get(self, key, default):
        return typed(self.props.get(PREFIX + key), default)

    def put(self, d):
        """Записать свойства на узел (и в индекс)."""
        rt = _rt()
        for k, v in d.items():
            text = fmt(v)
            rt.setUserProp(self.node, PREFIX + k, text)
            self.props[PREFIX + k] = text

    def __repr__(self):
        return "Rec(%s #%d)" % (self.name, self.handle)


def _parse_buffer(text):
    out = {}
    for line in (text or '').splitlines():
        if '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip().lower()
        if k:
            out[k] = v.strip()
    return out


def index():
    """[Rec] всей геометрии сцены."""
    ensure()
    nodes, handles, names, bufs, tops, depths = _rt().inuLinkIndex()
    return [Rec(n, h, nm, _parse_buffer(str(b or '')), t, d)
            for n, h, nm, b, t, d in zip(nodes, handles, names, bufs, tops, depths)]


def rec_of(node):
    """Rec одного узла (без индекса сцены: top / depth не считаются)."""
    rt = _rt()
    return Rec(node, int(node.inode.handle), str(node.name),
               _parse_buffer(str(rt.getUserPropBuffer(node) or '')), 0, 0)


def linked_files():
    """Файлы IDE / IPL, с которыми связаны узлы сцены (без нормализации)."""
    ensure()
    out = set()
    for b in _rt().inuLinkBufs():
        p = _parse_buffer(str(b or ''))
        if typed(p.get(PREFIX + 'ipl_uuid'), '') and typed(p.get(PREFIX + 'ipl_target_file'), ''):
            out.add(typed(p.get(PREFIX + 'ipl_target_file'), ''))
        if typed(p.get(PREFIX + 'ide_linked'), False) and typed(p.get(PREFIX + 'ide_target_file'), ''):
            out.add(typed(p.get(PREFIX + 'ide_target_file'), ''))
    return sorted(out)


def world(node):
    """((x, y, z), (qx, qy, qz, qw), (sx, sy, sz)) мировой матрицы узла.
    Кватернион — rotationpart, это и есть кватернион IPL (ops/map_link)."""
    tm = node.transform
    p, q, s = tm.translationpart, tm.rotationpart, tm.scalepart
    return ((float(p.x), float(p.y), float(p.z)),
            (float(q.x), float(q.y), float(q.z), float(q.w)),
            (float(s.x), float(s.y), float(s.z)))


def set_world(node, rows):
    """Мировая матрица узла из 12 чисел (строки поворота·масштаба + позиция)."""
    rt = _rt()
    r = [float(x) for x in rows]
    node.transform = rt.Matrix3(rt.Point3(r[0], r[1], r[2]), rt.Point3(r[3], r[4], r[5]),
                                rt.Point3(r[6], r[7], r[8]), rt.Point3(r[9], r[10], r[11]))


def has_texture(node):
    from .selection import _has_texture
    return _has_texture(node)
