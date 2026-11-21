"""Offline tests for Beyond Chaos's area songs (tools/bc_music.py map_overrides, map_pairs, bundle_data).

  pr/.venv/Scripts/python -m unittest discover -s pr/tests -p "test_bc_music.py" -v

  * a PR map two SNES maps share takes the song of the surer pair (hand-confirmed, chests/exits, doors,
    lookalike tiles, then coverage), not whichever SNES map comes first; a pair across worlds (snes_maps'
    "cross") is left out when a same-world pair found at least as surely exists (World of Ruin Mobliz), kept
    when the same-world pairs are only lookalikes (Figaro Castle's basement); same-slot SNES maps merge
  * the bundle's compact copy keeps what the choice needs (cross, how, coverage) and reads back; older
    copies (bare ids, a manual flag) still read
  * a PR room that names its track again where the SNES keeps the playing song (song 0: Mobliz's houses) takes
    its area's song from the rooms its doors join (inherit_kept); not with a track of its own, a song of its own,
    or neighbours that disagree
  * the table's lookalike pairs (another place's room by tiles alone) never reach map_pairs
Synthetic ROM bytes and pairs: no ROM, no BC run (the lookalike check reads data/snes_pr_maps.json when present).
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import kitpath  # noqa: E402,F401
import bc_music as M  # noqa: E402

SONG_A, SONG_B, VAN = 0x05, 0x07, 0x09     # FF6 slots with PR tracks (snes_songs.FF6_SONG_PR_BGM)


def roms(changes):
    """(vanilla, BC's) bytes: every map plays VAN; `changes` {SNES map: BC's slot}."""
    size = M.MAP_SONGS + 0x200 * M.MAP_SIZE
    van = bytearray(size)
    for m in range(0x200):
        van[M.MAP_SONGS + m * M.MAP_SIZE] = VAN
    bc = bytearray(van)
    for m, s in changes.items():
        bc[M.MAP_SONGS + m * M.MAP_SIZE] = s
    return bytes(van), bytes(bc)


def pair(pid, how="tiles", coverage=0.5, cross=False):
    return {"pr_id": pid, "how": how, "coverage": coverage, "cross": cross}


class SharedMaps(unittest.TestCase):
    def overrides(self, pairs, changes):
        van, bc = roms(changes)
        log = []
        with mock.patch.object(M, "map_pairs", return_value=pairs):
            return M.map_overrides(van, bc, log.append), log

    def test_surer_pair_wins_whatever_the_order(self):
        # SNES 0x10 is the weaker pair of PR map 500; 0x20 the surer one: 0x20's song, though 0x10 comes first
        pairs = {"16": [pair(500, coverage=0.4)], "32": [pair(500, coverage=0.9)]}
        out, log = self.overrides(pairs, {0x10: SONG_A, 0x20: SONG_B})
        self.assertEqual(out[500]["slot"], SONG_B)
        self.assertEqual(out[500]["snes_map"], 0x20)
        self.assertTrue(any("0x20's kept" in m for m in log), log)

    def test_hand_confirmed_pair_first(self):
        pairs = {"16": [pair(500, how="manual", coverage=0.1)], "32": [pair(500, coverage=0.99)]}
        out, _ = self.overrides(pairs, {0x10: SONG_A, 0x20: SONG_B})
        self.assertEqual(out[500]["slot"], SONG_A)

    def test_exits_outrank_lookalike_tiles(self):
        pairs = {"16": [pair(500, how="tiles", coverage=1.0)], "32": [pair(500, how="exits", coverage=0.6)]}
        out, _ = self.overrides(pairs, {0x10: SONG_A, 0x20: SONG_B})
        self.assertEqual(out[500]["slot"], SONG_B)

    def test_cross_world_pair_left_out_beside_its_own_world(self):
        # PR map 500 is World of Ruin Mobliz: the World of Balance town (cross, by exits) doesn't give it its song
        # when the World of Ruin town pairs by exits too, even when only the WoB town's song changed
        pairs = {"16": [pair(500, how="exits", coverage=0.4)], "32": [pair(500, how="exits", coverage=0.99, cross=True)]}
        out, _ = self.overrides(pairs, {0x20: SONG_B})
        self.assertNotIn(500, out)
        out, _ = self.overrides(pairs, {0x10: SONG_A, 0x20: SONG_B})
        self.assertEqual(out[500]["slot"], SONG_A)

    def test_cross_pair_by_exits_beats_same_world_lookalikes(self):
        # Figaro Castle's basement: its SNES rooms read as World of Ruin (nearest by the cave), both worlds use them;
        # the PR's World of Balance basement pairs with them by exits and with other places' lookalike rooms by tiles
        pairs = {"61": [pair(500, how="exits", coverage=1.0, cross=True)], "62": [pair(500, coverage=1.0, cross=True)],
                 "89": [pair(500, how="tiles", coverage=1.0)], "232": [pair(500, how="layout", coverage=1.0)]}
        out, _ = self.overrides(pairs, {62: SONG_A})     # BC changed a basement room the PR map pairs by tiles
        self.assertEqual(out[500]["slot"], SONG_A)

    def test_cross_pair_counts_when_alone(self):
        pairs = {"32": [pair(500, cross=True)]}
        out, _ = self.overrides(pairs, {0x20: SONG_B})
        self.assertEqual(out[500]["slot"], SONG_B)

    def test_unchanged_surer_map_doesnt_block(self):
        pairs = {"16": [pair(500, coverage=0.4)], "32": [pair(500, coverage=0.9)]}
        out, _ = self.overrides(pairs, {0x10: SONG_A})
        self.assertEqual(out[500]["slot"], SONG_A)

    def test_same_slot_merges(self):
        pairs = {"16": [pair(500, coverage=0.4)], "32": [pair(500, coverage=0.9)]}
        out, log = self.overrides(pairs, {0x10: SONG_A, 0x20: SONG_A})
        self.assertEqual(out[500]["slot"], SONG_A)
        self.assertEqual(log, [])


class Kept(unittest.TestCase):
    """inherit_kept: Town (500, track 21) has BC's slot 0x5C; House (600) is SNES map 0x30, song 0 (keep)."""
    names = {500: "Town", 600: "House", 700: "Back"}
    graph = {"Town": {"House"}, "House": {"Town", "Back"}, "Back": {"House"}}

    def run_(self, house_song=0, bgm=None, out=None, graph=None):
        van, bc = roms({})
        van, bc = bytearray(van), bytearray(bc)
        for m, sng in ((0x30, house_song), (0x31, 0)):
            van[M.MAP_SONGS + m * M.MAP_SIZE] = bc[M.MAP_SONGS + m * M.MAP_SIZE] = sng
        by_pr = {600: [((3, -1.0), 0x30, pair(600, how="exits"))], 700: [((3, -1.0), 0x31, pair(700, how="exits"))]}
        out = out if out is not None else {500: {"from": [21], "slot": 0x5C, "snes_map": 0x9D}}
        return M.inherit_kept(dict(out), by_pr, bytes(van), bytes(bc), bgm or {500: 21, 600: 21, 700: 21}, self.names,
                              self.graph if graph is None else graph)

    def test_house_and_back_room_keep_the_town_song(self):
        out = self.run_()
        self.assertEqual(out[600]["slot"], 0x5C)
        self.assertEqual(out[700]["slot"], 0x5C)          # through the house
        self.assertEqual(out[600]["kept_from"], 500)

    def test_not_when_the_snes_room_has_a_song_of_its_own(self):
        self.assertNotIn(600, self.run_(house_song=0x2A))

    def test_not_with_another_track_or_none(self):
        self.assertNotIn(600, self.run_(bgm={500: 21, 600: 47, 700: 47}))
        self.assertNotIn(600, self.run_(bgm={500: 21, 600: 0, 700: 0}))    # track 0: the PR keeps the song itself

    def test_not_when_neighbours_disagree(self):
        graph = {"Town": {"House"}, "Other": {"House"}, "House": {"Town", "Other"}}
        names = {**self.names, 800: "Other"}
        out = {500: {"from": [21], "slot": 0x5C}, 800: {"from": [21], "slot": 0x5D}}
        van, bc = roms({})
        by_pr = {600: [((3, -1.0), 0x30, pair(600))]}
        van, bc = bytearray(van), bytearray(bc)
        van[M.MAP_SONGS + 0x30 * M.MAP_SIZE] = bc[M.MAP_SONGS + 0x30 * M.MAP_SIZE] = 0
        got = M.inherit_kept(dict(out), by_pr, bytes(van), bytes(bc), {500: 21, 600: 21, 800: 21}, names, graph)
        self.assertNotIn(600, got)

    def test_no_graph_no_change(self):
        self.assertNotIn(600, self.run_(graph={}))


class Lookalikes(unittest.TestCase):
    def test_lookalikes_left_out(self):
        if not os.path.exists(os.path.join(M.ROOT, "data", "snes_pr_maps.json")):
            self.skipTest("no data/snes_pr_maps.json")
        import snes_maps as SM
        rows = [(m, mt.pr_id, bool(getattr(mt, "lookalike", False))) for m, ms in SM.table().items() for mt in ms]
        real = {(m, p) for m, p, look in rows if not look}
        looks = {(m, p) for m, p, look in rows if look} - real      # a pair that is only ever a lookalike
        if not looks:
            self.skipTest("this table marks no lookalikes")
        with mock.patch.object(M, "HERE", os.path.join(M.ROOT, "no-compact-copy")):
            got = {(int(k), e["pr_id"]) for k, v in M.map_pairs().items() for e in v}
        self.assertEqual(got & looks, set(), "a lookalike pair reached map_pairs")
        self.assertTrue(got)


class Compact(unittest.TestCase):
    def test_round_trip(self):
        pairs = {"16": [pair(500, coverage=0.4), pair(500, coverage=0.8), pair(501, how="manual")],
                 "32": [pair(500, how="exits", cross=True, coverage=0.91234)]}
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(M, "map_pairs", return_value=pairs), \
                    mock.patch.object(M, "resident_source", return_value=None):
                path = M.bundle_data(d)
            got = json.load(open(path, encoding="utf-8"))
            self.assertEqual(got["16"], [[500, 0, "tiles", 0.8], [501, 0, "manual", 0.5]])   # one per PR map: its best
            self.assertEqual(got["32"], [[500, 1, "exits", 0.912]])
            with mock.patch.object(M, "HERE", d):
                back = M.map_pairs()
        self.assertEqual(back["16"][1], {"pr_id": 501, "cross": False, "how": "manual", "coverage": 0.5})
        self.assertTrue(back["32"][0]["cross"])

    def test_old_compact_reads(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, M.MAP_PAIRS_FILE), "w") as f:
                json.dump({"16": [500, 501], "32": [[502, 0, 1, 0.5]]}, f)
            with mock.patch.object(M, "HERE", d):
                got = M.map_pairs()
        self.assertEqual(got["16"], [{"pr_id": 500}, {"pr_id": 501}])
        self.assertEqual(got["32"][0]["how"], "manual")


if __name__ == "__main__":
    unittest.main()
