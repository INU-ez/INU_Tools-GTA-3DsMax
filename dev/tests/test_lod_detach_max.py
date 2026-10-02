"""Pure Python regression checks for the Max placement bridge."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from inu_max.ops import map_link as ml


class Rec:
    def __init__(self, handle, kind, base, pos, **props):
        self.handle, self.kind, self.base = handle, kind, base
        self.name, self.node, self.props = base, pos, props

    def get(self, key, default):
        return self.props.get(key, default)


def scene(recs):
    return SimpleNamespace(
        recs=recs, by_handle={r.handle: r for r in recs},
        LS=SimpleNamespace(world=lambda node: (node, None, None)),
        model_type=lambda r: (r.kind, r.base), is_col=lambda r: False,
        is_copy=lambda r: False, reset_copies=lambda: None,
        linked_models=lambda: [r for r in recs if r.get('ipl_uuid', '')])


class LodDetachTests(unittest.TestCase):
    def test_nearest_tail_pair_and_anchor(self):
        lod = Rec(3, 'LOD', 'LODtower', (10, 0, 0))
        first = Rec(1, 'DFF', 'ap_tower', (0, 0, 0))
        second = Rec(2, 'DFF', 'ap_tower', (20, 0, 0),
                     ipl_uuid='b', ipl_last_pos=(10, 0, 0))
        sc = scene([first, second, lod])
        self.assertIs(ml._lod_owner_at(sc, lod, [first, second], 2), second)
        second.props.clear()
        self.assertIsNone(ml._lod_owner_at(sc, lod, [first, second], 2))
        first.props['lod_object'] = 3
        self.assertIs(ml._lod_owner_at(sc, lod, [first, second], 2), first)

    def test_one_detach_for_two_placements(self):
        for game in ('III', 'VC', 'SA'):
            with self.subTest(game=game), tempfile.TemporaryDirectory() as tmp:
                path = str(Path(tmp) / 'map.ipl')
                Path(path).write_text('inst\nend\n')
                first = Rec(1, 'DFF', 'house', (0, 0, 0),
                            ipl_uuid='a', ipl_target_file=path)
                second = Rec(2, 'DFF', 'house', (10, 0, 0),
                             ipl_uuid='b', ipl_target_file=path)
                lod = Rec(3, 'LOD', 'house', (10, 0, 0))
                lod.name = 'LODhouse'
                calls = []
                def detach(obj, anchor):
                    calls.append(obj.handle)
                    return SimpleNamespace(lod_removed=True, _row=None)
                ed = SimpleNamespace(detach_lod=detach)
                doc = SimpleNamespace(rows=[], editor=lambda **kw: ed)
                with patch.object(ml, '_load_ipl', return_value=doc), \
                     patch.object(ml, '_reserve_others'), \
                     patch.object(ml, '_commit', return_value=True):
                    ml.ipl_remove(scene([first, second, lod]), [lod], game=game,
                                  dry_run=True)
                self.assertEqual(calls, [1, 2] if game == 'SA' else [2])

    def test_unowned_lod_warns(self):
        lod = Rec(3, 'LOD', 'house', (10, 0, 0))
        rep = ml.ipl_remove(scene([lod]), [lod], game='VC', dry_run=True)
        self.assertTrue(any('LOD without' in text for _, text in rep.messages))


if __name__ == '__main__':
    unittest.main()
