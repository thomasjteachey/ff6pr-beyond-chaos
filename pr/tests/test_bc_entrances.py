"""Offline tests for Beyond Chaos's entrance shuffle index (tools/bc_entrances.py, data/bc_entrance_index.json).

  pr/.venv/Scripts/python -m unittest discover -s pr/tests -p "test_bc_entrances.py" -v

  * the shipped index: its shape, the coverage it was built with (minimums measured 2026-11-21: 1029 of
    1123 short entrances on a PR door, 932 of BC's 1015-entrance pool; 921 of 976 destinations), a known
    door (Narshe's inn, shared by the World of Balance and Ruin Narshes)
  * against the PR extract: every door and arrival the index names is that object in that file
  * against the US ROM: BC's reading of the tables, the pool, the index is up to date, a seed's
    changes and rewiring (a ROM with two entrances' destinations swapped by hand: no BC run)
  * the seed step (apply) on the hand-swapped ROM: the plain door set in the seed's copy of its map file, the
    shared Narshe door left for the plugin with a per-world redirect, another step's copy respected, no
    strangejourney = nothing written
  * FF6_BC_ENTRANCES_SEED=1: BC's own strangejourney seed 1234567890 (New Player + strangejourney,
    ~30 s, + ~20 s ROM-free in a second process): at least 650 of its 951 new destinations rewirable;
    apply's seed folder (every file it wrote, every object it changed = bc_doors.json, none set twice,
    the new PointIns); BC's entrance tables ROM-free = on the ROM
    (BC works in FF6_BC_HOME: point it at a copy of build/beyond-chaos/work when the build folder is shared)
Tests needing the US ROM or the PR extract skip without them.
"""
import collections
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import kitpath  # noqa: E402,F401
import prdata as P  # noqa: E402
import bc_entrances as B  # noqa: E402

MIN = {"entrances": 1123, "pool": 1015, "doors_matched": 1020, "pool_matched": 925, "doors_agreeing": 1000,
       "destinations_matched": 915, "pool_destinations_matched": 855}


def index_or_skip():
    if not os.path.exists(B.INDEX_FILE):
        raise unittest.SkipTest("no data/bc_entrance_index.json")
    return B.load_index()


def rom_or_skip():
    if not P.VANILLA_ROM or not os.path.exists(P.VANILLA_ROM):
        raise unittest.SkipTest("no US ROM")
    import ff6snes as S
    return S.rom_bytes(P.VANILLA_ROM)


def extract_or_skip():
    if not os.path.isdir(os.path.join(P.VANILLA, "map_20010")):
        raise unittest.SkipTest("no PR extract")


def swapped(rom, ix):
    """The US ROM with Narshe's inn door (SNES 20 #0, a PR door the World of Ruin's Narshe shares) and a plain
    entrance's destinations swapped by hand, as the vortex does: (ROM bytes, the plain entrance)."""
    by = {(e["map"], e["index"]): e for e in ix["entrances"]}
    narshe = by[(20, 0)]
    plain = next(e for e in ix["entrances"] if e["bc_shuffles"] and e["doors"] and not e.get("shared_with")
                 and e["dest"] != narshe["dest"] and e["map"] != narshe["dest"]
                 and ix["destinations"][B.dest_key(e["dest"], e["dest_x"], e["dest_y"])]["arrivals"])
    out = bytearray(rom)

    def at(e):
        ptr = out[B.SHORT + 2 * e["map"]] | out[B.SHORT + 2 * e["map"] + 1] << 8
        return B.SHORT + ptr + 6 * e["index"]
    a, b = at(narshe), at(plain)
    out[a + 2:a + 6], out[b + 2:b + 6] = rom[b + 2:b + 6], rom[a + 2:a + 6]
    return bytes(out), plain


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _props(o):
    return {p["name"]: p["value"] for p in o.get("properties", [])}


def check_seed(tc, out, doc, before=None):
    """apply's seed folder against its bc_doors.json: it wrote exactly doc["files"]; in each, the objects that
    differ from the file it started from (vanilla's, or `before`: {rel: doc} another step's copy) are the doors
    bc_doors.json lists as set (map_id/point_id only, each object once, to an existing PointIn) and the PointIns
    it lists as new; the shared doors stay as they were."""
    before = before or {}
    set_to = {}
    for r in doc["rewired"]:
        for d in r["doors"]:
            k = (d["file"], d["id"])
            tc.assertEqual(set_to.setdefault(k, d["to"]), d["to"], f"{k} set two ways")
    added = collections.defaultdict(dict)
    for p in doc["new_points"]:
        added[p["file"]][p["object"]] = p
    shared = {(s["file"], s["id"]): s for s in doc["shared"]}
    tc.assertFalse(set(shared) & set(set_to), "a shared door was set")
    tc.assertEqual(doc["files"], sorted(set(f for f, _ in set_to) | set(added)))
    written = sorted(os.path.relpath(os.path.join(r, f), os.path.join(out, "files")).replace("\\", "/")
                     for r, _, fs in os.walk(os.path.join(out, "files")) for f in fs)
    tc.assertEqual(sorted(set(written) - set(before)), sorted(set(doc["files"]) - set(before)))
    for rel in doc["files"]:
        mine = {o["id"]: o for _, o in B._objects(_load(os.path.join(out, "files", *rel.split("/"))))}
        was = {o["id"]: o for _, o in B._objects(before.get(rel) or _load(os.path.join(P.VANILLA, *rel.split("/"))))}
        tc.assertEqual(set(mine) - set(was), set(added[rel]), rel)
        tc.assertFalse(set(was) - set(mine), rel)
        for oid, o in mine.items():
            if oid in added[rel]:
                p, pp = added[rel][oid], _props(o)
                tc.assertEqual((o["name"], pp["object_id"], pp["object_type"], int(o["x"] // 16), int(o["y"] // 16) - 1),
                               ("PointIn", p["point_id"], 0, p["x"], p["y"]), (rel, oid))
                tc.assertGreaterEqual(pp["object_id"], B.NEW_POINT_FIRST)
            elif (rel, oid) in set_to:
                pp, vp = _props(o), _props(was[oid])
                tc.assertEqual([pp["map_id"], pp["point_id"]], set_to[(rel, oid)], (rel, oid))
                tc.assertEqual({k: v for k, v in pp.items() if k not in ("map_id", "point_id")},
                               {k: v for k, v in vp.items() if k not in ("map_id", "point_id")}, (rel, oid))
                tc.assertEqual({k: v for k, v in o.items() if k != "properties"},
                               {k: v for k, v in was[oid].items() if k != "properties"}, (rel, oid))
            else:
                tc.assertEqual(o, was[oid], (rel, oid))
    # every target is a PointIn there: vanilla's or one the seed added
    pr = B.Pr()
    names = {v: k for k, v in pr.ids.items()}
    new = {(p["map_id"], p["point_id"]) for p in doc["new_points"]}
    for (rel, oid), to in set_to.items():
        tc.assertTrue(tuple(to) in new or to[1] in pr.points.get(names.get(to[0]), {}), (rel, oid, to))
    for s in doc["shared"]:
        tc.assertGreaterEqual(len(s["versions"]), 2, s)
        tc.assertGreater(len({tuple(v["target"]) if v["target"] else None for v in s["versions"]}), 1, s)
        tc.assertEqual("redirect" in s, s["split"] == "world", s)
        for v in s["versions"]:
            if v["how"] == "vanilla":       # the door's own destination (a few lead to maps without entity_default.json)
                tc.assertEqual(v["target"], s["vanilla"], v)
            elif v["target"]:
                tc.assertTrue(tuple(v["target"]) in new or v["target"][1] in pr.points.get(names.get(v["target"][0]), {}), v)
            else:
                tc.assertTrue(v["reason"], v)
    return set_to


class Shipped(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ix = index_or_skip()

    def test_shape(self):
        ix = self.ix
        for k in ("entrances", "destinations", "rooms_found", "worlds", "coverage"):
            self.assertIn(k, ix)
        for e in ix["entrances"]:
            for k in ("map", "index", "x", "y", "dest_word", "dest", "flags", "dest_x", "dest_y", "bc_shuffles",
                      "doors", "reason"):
                self.assertIn(k, e)
            self.assertEqual(e["dest"], e["dest_word"] & 0x1FF)
            self.assertEqual(bool(e["doors"]), e["reason"] is None, e)
            self.assertIn(B.dest_key(e["dest"], e["dest_x"], e["dest_y"]), ix["destinations"])
            for d in e["doors"]:
                for k in ("pr", "file", "id", "x", "y", "map_id", "point_id", "how", "dest_agrees"):
                    self.assertIn(k, d)
                self.assertIn(d["how"], ("spot", "near", "twin"))
                self.assertTrue(d["file"].endswith(".json") and "/" in d["file"] and "\\" not in d["file"])
        for d in ix["destinations"].values():
            self.assertEqual(bool(d["arrivals"]), d["reason"] is None, d)
            for a in d["arrivals"]:
                self.assertIn(a["how"], ("door", "point", "new_point"))
                self.assertEqual(a["point_id"] is None, a["how"] == "new_point")

    def test_coverage(self):
        c = self.ix["coverage"]
        self.assertEqual(c, B.coverage(self.ix), "coverage in the file doesn't match its records")
        self.assertEqual(c["entrances"], MIN["entrances"])
        self.assertEqual(c["pool"], MIN["pool"])
        for k, v in MIN.items():
            self.assertGreaterEqual(c[k], v, k)

    def test_narshe_inn(self):
        e = next(e for e in self.ix["entrances"] if (e["map"], e["index"]) == (20, 0))
        self.assertEqual((e["x"], e["y"], e["dest"], e["dest_x"], e["dest_y"]), (41, 36, 28, 8, 45))
        self.assertTrue(e["bc_shuffles"])
        self.assertEqual([(d["pr"], d["x"], d["y"], d["dest_agrees"]) for d in e["doors"]], [("Map_20010", 41, 36, True)])
        self.assertIn([32, 0], e["shared_with"])     # the World of Ruin Narshe's inn door is the same PR door

    def test_kept(self):
        by = {(e["map"], e["index"]): e for e in self.ix["entrances"]}
        self.assertFalse(by[(0x14, 10)]["bc_shuffles"])      # Narshe -> Arvis's house
        self.assertFalse(any(e["bc_shuffles"] for e in self.ix["entrances"] if e["map"] in (0, 1)))
        self.assertFalse(any(e["bc_shuffles"] for e in self.ix["entrances"] if e.get("dup")))


class Extract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ix = index_or_skip()
        extract_or_skip()
        cls.files = {}

    def objects(self, rel):
        if rel not in self.files:
            with open(os.path.join(P.VANILLA, *rel.split("/")), encoding="utf-8") as f:
                doc = json.load(f)
            self.files[rel] = {o["id"]: (lay, o) for lay, o in B._objects(doc)}
        return self.files[rel]

    def test_doors_are_there(self):
        n = 0
        for e in self.ix["entrances"]:
            for d in e["doors"]:
                lay, o = self.objects(d["file"])[d["id"]]
                p = {x["name"]: x["value"] for x in o.get("properties", [])}
                self.assertEqual((p.get("map_id"), p.get("point_id", 0)), (d["map_id"], d["point_id"]), d)
                self.assertEqual((int(o["x"] // 16), int(o["y"] // 16) - (1 if "gid" in o else 0)), (d["x"], d["y"]))
                self.assertEqual(lay, d["layer"])
                n += 1
        self.assertGreater(n, 1000)

    def test_arrivals_are_there(self):
        pr = B.Pr()
        for d in self.ix["destinations"].values():
            for a in d["arrivals"]:
                self.assertEqual(pr.ids[a["pr"]], a["map_id"])
                if a["point_id"] is not None:
                    self.assertIn(a["point_id"], pr.points[a["pr"]], a)
                else:
                    import snes_maps as SM
                    self.assertIn((a["pr_x"], a["pr_y"]), SM.pr_walkable(a["pr"]), a)


class Rom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = rom_or_skip()
        cls.ix = index_or_skip()

    def test_reader(self):
        ents = B.short_entrances(self.rom)
        self.assertEqual(len(ents), B.LOCATIONS)
        allents = [e for es in ents.values() for e in es]
        self.assertEqual(sum(1 for e in allents if not e.get("dup")), MIN["entrances"])
        self.assertEqual(sum(1 for e in allents if not e.get("dup") and not B.bc_kept(e)), MIN["pool"])
        # within a map, BC's uniqify leaves no two entrances on one tile
        for m, es in ents.items():
            xy = [(e["x"], e["y"]) for e in es if not e.get("dup")]
            self.assertEqual(len(xy), len(set(xy)), m)

    def test_up_to_date(self):
        doc = B.build_index(self.rom, say=lambda *_: None)
        self.assertEqual(doc["coverage"], self.ix["coverage"], "rebuild: python tools/bc_entrances.py index")

    def test_no_changes(self):
        self.assertEqual(B.changes(self.rom, self.rom), [])

    def test_swap(self):
        """Two entrances' destinations swapped by hand, as the vortex does: the plan rewires the plain
        one's PR door to the other's arrival and holds the shared Narshe door (the World of Ruin's
        version still goes to the inn)."""
        ix = self.ix
        rom, plain = swapped(self.rom, ix)
        chg = B.changes(self.rom, rom)
        self.assertEqual(sorted(((e["map"], e["index"]), k) for e, _, k in chg),
                         sorted([((20, 0), "dest"), ((plain["map"], plain["index"]), "dest")]))
        plan = {(p["entrance"]["map"], p["entrance"]["index"]): p for p in B.rewire_plan(ix, chg)}
        p = plan[(plain["map"], plain["index"])]
        self.assertTrue(p["ok"], p["reason"])
        inn = ix["destinations"][B.dest_key(28, 8, 45)]["arrivals"]
        self.assertTrue(p["doors"])
        for door, arr in p["doors"]:
            self.assertIn((arr["map_id"], arr["point_id"]), [(x["map_id"], x["point_id"]) for x in inn])
        q = plan[(20, 0)]
        self.assertFalse(q["ok"])
        self.assertTrue(q["reason"].startswith("shared PR door: the other world's version"), q["reason"])

    def test_pick_arrival(self):
        """An interior both worlds share: the World of Ruin room's door lands in the World of Ruin copy."""
        arrs = [{"pr": "A_wob", "how": "door"}, {"pr": "A_wor", "how": "door"}]
        graph = {"B_wor": {"A_wor", "W"}, "A_wor": {"B_wor"}, "W": {"B_wor", "A_wob"}, "A_wob": {"W"}}
        self.assertEqual(B.pick_arrival(arrs, "B_wor", graph)["pr"], "A_wor")
        self.assertEqual(B.pick_arrival(arrs, "nowhere", graph)["pr"], "A_wob")


class Apply(unittest.TestCase):
    """The seed step on the hand-swapped ROM (no BC run)."""

    @classmethod
    def setUpClass(cls):
        cls.rom = rom_or_skip()
        cls.ix = index_or_skip()
        extract_or_skip()
        cls.seed, cls.plain = swapped(cls.rom, cls.ix)

    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="bc_doors_")
        self.addCleanup(shutil.rmtree, self.out, True)

    def run_apply(self, flags="b c strangejourney", mode="normal"):
        return B.apply(self.out, flags, self.seed, self.rom, mode=mode, log=lambda m: None, index=self.ix)

    def test_graph(self):
        self.assertEqual(B.graph_of(self.ix), B.Pr().graph(), "rebuild: python tools/bc_entrances.py index")

    def test_no_vortex(self):
        self.assertEqual(self.run_apply("b c j"), ([], None))
        self.assertEqual(self.run_apply("b c strangejourney", mode="ancientcave"), ([], None))
        self.assertEqual(os.listdir(self.out), [])

    def test_swap(self):
        files, summary = self.run_apply()
        doc = _load(os.path.join(self.out, B.DOORS_JSON))
        self.assertEqual(files, doc["files"])
        self.assertEqual(summary, doc["summary"])
        set_to = check_seed(self, self.out, doc)
        plain = self.plain
        r = next(r for r in doc["rewired"] if r["entrance"] == [plain["map"], plain["index"]])
        self.assertFalse(r["partial"])
        inn = {(a["map_id"], a["point_id"]) for a in self.ix["destinations"][B.dest_key(28, 8, 45)]["arrivals"]}
        self.assertEqual({(d["file"], d["id"]) for d in r["doors"]}, {(d["file"], d["id"]) for d in plain["doors"]})
        for d in r["doors"]:
            self.assertIn(tuple(d["to"]), inn)
        self.assertEqual(set(set_to), {(d["file"], d["id"]) for d in plain["doors"]})
        # Narshe's inn door: the World of Balance's goes where the plain door went, the World of Ruin's to the inn
        s = next(s for s in doc["shared"] if s["pr"] == "Map_20010" and [s["x"], s["y"]] == [41, 36])
        self.assertEqual(s["split"], "world")
        self.assertTrue(s["key_unique"])
        vs = {tuple(v["entrance"]): v for v in s["versions"]}
        self.assertTrue(vs[(20, 0)]["changed"])
        self.assertFalse(vs[(32, 0)]["changed"])
        self.assertEqual(s["redirect"]["on"], s["vanilla"])
        self.assertEqual(s["redirect"]["off"], vs[(20, 0)]["target"])
        self.assertEqual(s["redirect"]["flag"], list(B.WOR_FLAG))
        self.assertIn([20, 0], [r["entrance"] for r in doc["not_rewired"]])
        self.assertEqual(doc["conflicts"], [])

    def test_other_step_first(self):
        """A door another step already changed in the seed's copy of its file stays as that step left it."""
        d = self.plain["doors"][0]
        path = os.path.join(self.out, "files", *d["file"].split("/"))
        os.makedirs(os.path.dirname(path))
        doc = _load(os.path.join(P.VANILLA, *d["file"].split("/")))
        o = next(o for _, o in B._objects(doc) if o["id"] == d["id"])
        for p in o["properties"]:
            if p["name"] == "map_id":
                p["value"] = 9999
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        before = {d["file"]: json.loads(json.dumps(doc))}
        self.run_apply()
        res = _load(os.path.join(self.out, B.DOORS_JSON))
        check_seed(self, self.out, res, before=before)
        c = [c for c in res["conflicts"] if (c["file"], c["id"]) == (d["file"], d["id"])]
        self.assertEqual(len(c), 1, res["conflicts"])
        self.assertIn("another step", c[0]["reason"])
        after = _load(path)
        self.assertEqual(_props(next(o for _, o in B._objects(after) if o["id"] == d["id"]))["map_id"], 9999)

    def test_files(self):
        """files(): every door and new-point file a seed may write, none the baseline has already (chest maps)."""
        import seed_live
        fs = set(B.files(self.ix))
        managed = set(seed_live.managed_files())
        self.assertFalse(fs & managed)
        for e in self.ix["entrances"]:
            if e["bc_shuffles"]:
                for d in e["doors"]:
                    self.assertIn(d["file"], fs | managed)
        for rel in fs:
            self.assertTrue(os.path.exists(os.path.join(P.VANILLA, *rel.split("/"))), rel)


@unittest.skipUnless(os.environ.get("FF6_BC_ENTRANCES_SEED") == "1", "BC seed run (~50 s): FF6_BC_ENTRANCES_SEED=1")
class Seed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = rom_or_skip()
        cls.ix = index_or_skip()
        extract_or_skip()
        cls.vanilla, cls.data, cls.flags = B.make_seed(B.SEED, None, cls.rom)   # one BC run per process

    def test_seed(self):
        r = B.diff_report(self.ix, self.vanilla, self.data, B.Pr().graph())
        B.print_diff(r)        # the measurement (as `bc_entrances.py diff`)
        self.assertEqual(collections.Counter(r["changed"])["removed"], 0)
        self.assertGreaterEqual(r["dest_changed"], 900)
        self.assertGreaterEqual(r["rewirable"], 650)
        self.assertEqual(r["pr_object_conflicts"], 0)

    def test_apply(self):
        out = tempfile.mkdtemp(prefix="bc_doors_")
        self.addCleanup(shutil.rmtree, out, True)
        lines = []
        files, summary = B.apply(out, self.flags, self.data, self.vanilla, log=lines.append, index=self.ix)
        print("\n" + "\n".join(lines))
        doc = _load(os.path.join(out, B.DOORS_JSON))
        self.assertEqual(files, doc["files"])
        set_to = check_seed(self, out, doc)
        self.assertGreaterEqual(summary["rewired"], 650)
        self.assertEqual(summary["rewired"] + summary["not_rewired"], summary["dest_changed"])
        self.assertEqual(len(set_to), summary["objects_set"])
        self.assertGreaterEqual(summary["objects_set"], 790)
        self.assertGreaterEqual(summary["new_points"], 3)
        self.assertEqual(summary["conflicts"], 0)
        self.assertGreaterEqual(summary["shared_world"], 40)
        # every file it wrote is one the baseline holds (bc_live.own_files: files(); chest maps: seed_live's)
        import seed_live
        self.assertFalse(set(files) - set(B.files(self.ix)) - set(seed_live.managed_files()))

    def test_romfree(self):
        """BC on the generator's data/bc_base.bin (a player's machine) deals the same entrances as on the ROM."""
        import bc_basedata
        if not os.path.exists(bc_basedata.PATH):
            self.skipTest("no data/bc_base.bin")
        tmp = tempfile.mkdtemp(prefix="bc_tables_")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "tables.json")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env.pop("FF6_BC_ROMFREE", None)
        p = subprocess.run([sys.executable, "-B", os.path.join(HERE, "..", "tools", "bc_entrances.py"), "tables", path,
                            "--romfree"], env=env, capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        got = _load(path)
        want = json.loads(json.dumps({"short": {str(m): es for m, es in B.short_entrances(self.data).items()},
                                      "changes": [[e, s, k] for e, s, k in B.changes(self.vanilla, self.data)]}))
        self.assertEqual(got["short"], want["short"])
        self.assertEqual(got["changes"], want["changes"])


if __name__ == "__main__":
    unittest.main()
