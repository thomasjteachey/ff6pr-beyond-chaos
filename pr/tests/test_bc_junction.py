"""Offline tests for Beyond Chaos's junction effects at seed time (tools/bc_junction.py; the plugin's
BcJunction*.cs reads what it writes).

  pr/.venv/Scripts/python -m unittest discover -s pr/tests -p "test_bc_junction.py" -v

- BC's own writer (bcg_junction.populate_data) fills a ROM-sized buffer; bc_junction.read must read back
  exactly what it was given, and pr_record must name the PR's rows.
- BC_SEED_TEST=1: a real BC run with the six junction flags (~40 s): the record equals BC's own report (its
  spoiler log's JUNCTIONS section), and the seed is still BC's (the run is bc_run's: no draws of ours).
"""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PR, "tools"))
import kitpath  # noqa: E402,F401
import bc_junction as J  # noqa: E402
import bc_run  # noqa: E402


def bc_modules():
    """BC's bcg_junction with its randomtools, as bc_run loads them (its source on the path, _MEIPASS set)."""
    src = os.path.abspath(bc_run.SRC)
    sys._MEIPASS = src
    if src not in sys.path:
        sys.path.insert(0, src)
    cwd = os.getcwd()
    try:
        os.chdir(os.path.abspath(bc_run.HOME))
        import bcg_junction
        return bcg_junction
    finally:
        os.chdir(cwd)


class Read(unittest.TestCase):
    def setUp(self):
        self.man = J.manifest()
        self.cat = J.catalog(self.man)
        self.index = {k: i for i, k in self.cat.items()}

    def write(self, lists):
        """lists: {(category, color): {index: [keys]}} and "always": [keys] -> a 7 MB buffer BC's way."""
        bj = bc_modules()
        buf = io.BytesIO(bytes(0x700000))
        num = lambda k: int(self.man[k], 16)  # noqa: E731
        bj.populate_data({0: sorted(self.index[k] for k in lists.get("always", []))}, buf, num("always_whitelist_address"))
        for cat, max_index in J.CATEGORIES:
            for color in ("white", "black"):
                d = {i: [self.index[k] for k in ks] for i, ks in lists.get((cat, color), {}).items()}
                d.setdefault(max_index, [])
                bj.populate_data(d, buf, num(f"{cat}_{color}list_address"))
        return buf.getvalue()

    def test_reads_back_what_bc_wrote(self):
        lists = {
            "always": ["junction_jammer"],
            ("character", "white"): {1: ["resonate", "dog"]},
            ("esper", "white"): {0: ["boost_fire", "repel_water"], 26: ["vip"]},
            ("equip", "white"): {0x5A: ["mp_switch", "critical_golem"], 0xEE: ["salve"]},
            ("equip", "black"): {0x10: ["leech"]},
            ("status", "white"): {27: ["burst"], 5: ["imp_harvest"]},
            ("monster", "white"): {0x100: ["vampire"], J.EVERY_MONSTER: ["flinch"]},
            ("monster", "black"): {J.EVERY_MONSTER: ["reverse", "quickening"], 0x11A: ["astral"]},
        }
        rec = J.read(self.write(lists), self.man)
        self.assertIsNotNone(rec)
        self.assertEqual([self.cat[j] for j in rec["always"]], ["junction_jammer"])
        for (cat, color), d in ((k, v) for k, v in lists.items() if k != "always"):
            got = {i: sorted(self.cat[j] for j in js) for i, js in rec[cat][color].items()}
            self.assertEqual(got, {i: sorted(ks) for i, ks in d.items()}, (cat, color))
        part = J.pr_record(rec, self.man, log=lambda m: None)
        self.assertEqual(part["characters"]["2"]["has"], sorted(["resonate", "dog"], key=lambda k: self.index[k]))
        import idmap
        self.assertIn(str(idmap.esper_content(0)), part["espers"])
        self.assertIn(str(idmap.item_content(0x5A)), part["equipment"])
        self.assertEqual(part["equipment"][str(idmap.item_content(0x10))], {"not": ["leech"]})
        self.assertEqual(part["statuses"]["27"]["has"], ["burst"])
        self.assertEqual(part["monsters"][str(0x100 + 1)]["has"], ["vampire"])
        self.assertEqual(part["every_monster"], {"has": ["flinch"], "not": sorted(["reverse", "quickening"], key=lambda k: self.index[k])})
        self.assertEqual(J.used(part) >= {"junction_jammer", "vampire", "flinch", "salve"}, True)

    def test_no_tables_no_record(self):
        self.assertIsNone(J.read(bytes(0x700000), self.man))

    def test_names_are_the_prs_words(self):
        nm = J.names(self.man, {21: "Gil Toss"})
        self.assertEqual(nm["boost_bolt"], "Lightning Boost")
        self.assertEqual(nm["critical_warp"], "SOS Teleport")
        self.assertEqual(nm["critical_gprain"], "SOS Gil Toss")
        self.assertEqual(nm["esper_magic"], "Esper Magic")
        self.assertFalse(any(w in n for n in nm.values() for w in ("Bio", "Pearl", "Bolt", "Rflect", "-J")))

    def test_description_fits(self):
        nm = J.names(self.man)
        t = J.junction_text(["boost_fire", "dog", "vip"], nm, "A sword forged in flame.")
        self.assertLessEqual(len(t), J.MAX_TEXT)
        self.assertIn("Fire Boost", t)

    def test_spec_covers_every_junction(self):
        import json
        spec = json.load(open(os.path.join(PR, "data", "bc_junction_spec.json"), encoding="utf-8"))
        missing = set(self.man["junction_indexes"]) - set(spec["junctions"])
        self.assertEqual(missing, set())

    def test_every_junction_has_a_key(self):
        self.assertEqual(len(self.cat), len(self.man["junction_indexes"]))
        self.assertTrue(all(1 <= i <= 0xFF for i in self.cat))


@unittest.skipUnless(os.environ.get("BC_SEED_TEST") == "1", "BC_SEED_TEST=1 runs BC (~40 s)")
class RealSeed(unittest.TestCase):
    def test_record_is_bcs_report(self):
        import bc_seed
        import ff6snes as S
        import prdata as P
        flags = bc_seed.PRESETS["New Player"] + " espffect effectmas effectory effectster treaffect mementomori:6 jejentojori"
        data, spoiler = bc_run.run(S.rom_bytes(P.VANILLA_ROM), "9859608359", "normal", flags, say=lambda m: None)
        rec = J.read(data)
        self.assertIsNotNone(rec)
        self.assertEqual(J.check_log(rec, spoiler), [])
        part = J.pr_record(rec, log=lambda m: None)
        self.assertGreater(len(J.used(part)), 60)
        self.assertTrue(part["monster_items"]["steal"] and part["monster_items"]["drop"])
        info = J.esper_info(data)
        self.assertEqual(len(info), 27)
        self.assertTrue(all(v["summon"] for v in info.values()))
        trig = J.triggers(data)
        self.assertEqual(trig["spells"]["haste"], 71)
        self.assertEqual(trig["spells"]["lagomorph"], 210)
        self.assertTrue(trig["items"]["superball"] > 0)


if __name__ == "__main__":
    unittest.main()
