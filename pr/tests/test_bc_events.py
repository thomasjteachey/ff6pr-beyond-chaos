"""Beyond Chaos's light events (tools/bc_events.py): each flag's PR scripts, map files, lines and tables from BC's own
output, checked offline (the scripts run in test_wc's script machine).

  .venv/Scripts/python -m unittest tests.test_bc_events -v

BC's output for each flag set is made once (tools/bc_run.py in its own process, ~10 s; needs the vanilla ROM) and kept
in build/bc-events-test (zlib'd as bc_run writes it: never an .sfc). Seed 9859608359, flags "o w t m" (the requirements
of rushforpower / mimetime / lessfanatical) plus the flag under test; BC reseeds per stage, so "base" is the same game
without it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PR, "tools"))
sys.path.insert(0, HERE)
import prdata as P  # noqa: E402
import pr_script as S  # noqa: E402
import bc_events as B  # noqa: E402
B.SPEAKERS_LIVE = True     # the name boxes' file (tools/bc_events.py: written once PrKit's LiveData routes it)

SEED, BASE = "9859608359", "o w t m"
CACHE = os.path.join(PR, "build", "bc-events-test")
HAVE_ROM = os.path.exists(P.VANILLA_ROM)


RUN = """
import json, sys
sys.path.insert(0, "tools")
import ff6snes as F, prdata as P, bc_run, bc_events
capture = {}
data, _ = bc_run.run(F.rom_bytes(P.VANILLA_ROM), sys.argv[1], "normal", sys.argv[2], say=lambda _: None, capture=capture,
                     prepare=lambda: bc_events.prepare(capture))
bc_run.write_output(sys.argv[3], data)
json.dump({k: v for k, v in capture.items() if k in ("clock", "wor_recruits", "wor_free", "opera")}, open(sys.argv[3] + ".capture.json", "w"))
"""


def bc_output(name, flags):
    """BC's output ROM bytes for BASE + flags (made once, cached, with bc_events.prepare's capture beside it)."""
    import ff6snes as F
    path = os.path.join(CACHE, f"{name}.bin")
    if not os.path.exists(path + ".capture.json"):
        os.makedirs(CACHE, exist_ok=True)
        subprocess.run([sys.executable, "-c", RUN, SEED, f"{BASE} {flags}".strip(), path], check=True,
                       capture_output=True, cwd=PR)
    return F.rom_bytes(path)


def capture_of(name):
    with open(os.path.join(CACHE, f"{name}.bin.capture.json"), encoding="utf-8") as f:
        return json.load(f)


class Seed:
    """A scratch seed folder with the vanilla tables/messages bc_events edits, and apply()'s result."""

    def __init__(self, flags, rom, tables=(), capture=None):
        import seed_live as L
        self.out = tempfile.mkdtemp(prefix="bc_events_")
        for t in tables:
            dest = os.path.join(self.out, *L.MASTER_PATH.split("/"), t + ".csv")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(os.path.join(P.MASTER, t + ".csv"), dest)
        msg = os.path.join(self.out, *L.MESSAGE_PATH.split("/"), "system_en.txt")
        os.makedirs(os.path.dirname(msg), exist_ok=True)
        open(msg, "w").close()
        self.files, self.data = B.apply(self.out, flags, rom=rom, capture=capture, log=lambda m: None)

    def script(self, name):
        return json.load(open(os.path.join(self.out, "files", *B.script_rel(name).split("/")), encoding="utf-8"))

    def file(self, rel):
        return json.load(open(os.path.join(self.out, "files", *rel.split("/")), encoding="utf-8"))

    def messages(self, name):
        import seed_live as L
        out = {}
        path = os.path.join(self.out, *L.MESSAGE_PATH.split("/"), name + ".txt")
        with open(path, encoding="utf-8") as f:
            for line in f.read().splitlines():
                if "	" in line:
                    k, v = line.split("	", 1)
                    out[k] = v
        return out

    def lines(self):
        import seed_live as L
        out = {}
        for line in open(os.path.join(self.out, *L.MESSAGE_PATH.split("/"), "system_en.txt"), encoding="utf-8"):
            if "\t" in line:
                k, v = line.rstrip("\r\n").split("\t", 1)
                out[k] = v
        return out

    def close(self):
        shutil.rmtree(self.out, ignore_errors=True)


class Files(unittest.TestCase):
    def test_every_file_is_a_vanilla_file(self):
        for rel in B.files():
            name = os.path.splitext(os.path.basename(rel))[0]
            if name not in B.NEW_SCRIPTS and rel not in B.NEW_LAYERS:
                self.assertTrue(os.path.exists(os.path.join(P.VANILLA, *rel.split("/"))), rel)

    def test_baseline_is_vanilla(self):
        out = tempfile.mkdtemp(prefix="bc_events_base_")
        try:
            added = []
            B.write_baseline(out, added.append)
            self.assertEqual(sorted(set(added) - {r for r in added if r.endswith("package.json")}), B.files())
            for rel in B.files():
                name = os.path.splitext(os.path.basename(rel))[0]
                with open(os.path.join(out, *rel.split("/")), "rb") as a:
                    got = a.read()
                if name in B.NEW_SCRIPTS:                       # our own scripts: Exit only
                    self.assertEqual([o["mnemonic"] for o in json.loads(got)["Mnemonics"]], ["Nop", "Exit"], rel)
                elif rel in B.NEW_LAYERS:                       # our own entity layers: no objects
                    self.assertEqual(json.loads(got)["layers"][0]["objects"], [], rel)
                else:
                    with open(os.path.join(P.VANILLA, *rel.split("/")), "rb") as b:
                        self.assertEqual(got, b.read(), rel)
            # each listed in its map
            for rel, (group, folder, sub, layer) in B.NEW_LAYERS.items():
                pkg = json.load(open(os.path.join(out, group, "Assets/GameAssets/Serial/Res/Map", folder, "package.json"),
                                     encoding="utf-8"))
                entry = next(m for m in pkg["map"] if m["name"] == sub)
                self.assertIn(f"{sub}/{layer}", [e["asset"] for e in entry["entity"]], rel)
                self.assertTrue([e for e in entry["script"] if e["name"].startswith("sc_bc_gogo_")], rel)
        finally:
            shutil.rmtree(out, ignore_errors=True)


class Notawaiter(unittest.TestCase):
    STATE = {"SetFlag", "ResetFlag", "Calc", "GetItem", "RemoveItem", "RemoveGil", "SetEntities", "Encount", "EncountBoss",
             "ChangeMap", "ChangeScript", "SetVehicle", "SysCall", "OrganizePartySlot", "ChangePartySlot", "AutoSave"}

    def test_condensed_scenes_keep_their_state(self):
        """Every condensed scene: no show left, and the same state steps as the original on the same menu answers
        (test_wc's script machine; menus answered 0, as the condenser does)."""
        import copy
        import test_wc as W
        checked = 0
        for name in B.NAW_CUT:
            try:
                vanilla = S.load(name)
            except KeyError:
                continue
            cut = copy.deepcopy(vanilla)
            B.condense(cut)
            self.assertFalse([o["mnemonic"] for o in cut["Mnemonics"] if o["mnemonic"] in B.SHOW or o["mnemonic"] == "Select"], name)
            self.assertEqual(len(cut["Mnemonics"]), len(vanilla["Mnemonics"]), name)
            runs = []
            for sc in (vanilla, cut):
                r = W.Run(sc, W.State(), answers=[0] * 50, max_steps=200000)
                runs.append(([(t[1], tuple(t[2][:3]), tuple(t[3][:2])) for t in r.trace if t[1] in self.STATE], r.end))
            self.assertEqual(runs[0], runs[1], name)
            checked += 1
        self.assertGreater(checked, 150)


@unittest.skipUnless(HAVE_ROM, "needs the vanilla ROM (BC's input)")
class Flags(unittest.TestCase):
    def doors(self, rom):
        seed = Seed("j", rom)
        try:
            return {(d[0], tuple(d[1])): (d[2] if isinstance(d[2], str) else tuple(d[2])) for d in seed.data["j"]["doors"]}, seed
        except Exception:
            seed.close()
            raise

    def test_forest_without_j_reads_as_the_prs_own_doors(self):
        doors, seed = self.doors(bc_output("base", ""))
        seed.close()
        self.assertEqual(doors, {("Map_30421_1", (28, 8)): (352, 1), ("Map_30421_2", (5, 15)): (351, 2),
                                 ("Map_30421_2", (22, 15)): (353, 1), ("Map_30421_3", (10, 8)): (352, 2),
                                 ("Map_30421_3", (16, 8)): "train", ("Map_30421_3", (17, 13)): (351, 2)})

    def test_forest_j_rewires_and_moves_the_train(self):
        doors, seed = self.doors(bc_output("j", "j"))
        try:
            self.assertEqual(sum(1 for v in doors.values() if v == "train"), 1)
            self.assertEqual(doors[("Map_30421_2", (22, 15))], "train")
            self.assertEqual(doors[("Map_30421_1", (28, 8))], (353, 3))          # a new arrival point BC needs
            room = seed.file(B.MAP_REL.format(group="map_30421", folder="Map_30421", sub="Map_30421_3", file="entity_default.json"))
            points = {pr["object_id"]: B._tile(o) for _, o, pr in B._objects(room) if pr.get("object_type") == 0}
            self.assertEqual(points[3], (17, 12))
            walk = seed.script(B.SPRING_WALK)
            self.assertFalse(any(m["mnemonic"] == "SetEntities" for m in walk["Mnemonics"]))
        finally:
            seed.close()

    def test_clock_answer_and_hints(self):
        self.assertEqual(B.clock_answer(bc_output("base", "")), [2, 0, 4])        # vanilla 6:10:50
        seed = Seed("k", bc_output("k", "k"), capture=capture_of("k"))
        try:
            k = seed.data["k"]
            self.assertEqual(k["time"], "6:50:30")
            self.assertEqual(len(k["hints"]), 8)
            import test_wc as W
            sc = seed.script(B.CLOCK_SCRIPT)
            for answers, solved in (([2, 4, 2], True), ([2, 0, 4], False), ([2, 4, 1], False)):
                st = W.State()
                r = W.Run(sc, st, answers=answers)
                self.assertEqual(any(t[1] == "Call" and t[2][0] == 53 for t in r.trace), solved, answers)
            lines = seed.lines()
            self.assertIn("The seconds? They're a square times 10.", lines.values())
            zozo = seed.file(B._zozo_rel("Map_30511_7"))
            keys = {p["value"] for _, o, _ in B._objects(zozo) for p in o.get("properties", []) if str(p.get("value")).startswith("BC_EV_k_")}
            self.assertTrue(keys and keys <= set(lines))
        finally:
            seed.close()

    def test_lessfanatical_drops_the_towers_magic_only_script(self):
        seed = Seed("lessfanatical", bc_output("base", ""), tables=["monster_party"])
        try:
            self.assertEqual(len(seed.data["lessfanatical"]["parties"]), 18)
            import seed_live as L
            with open(os.path.join(seed.out, *L.MASTER_PATH.split("/"), "monster_party.csv"), encoding="utf-8") as f:
                t = P.Table("monster_party", f.read())
            self.assertFalse([i for i, r in t.rows.items() if r["script_name"] == B.TOWER_SCRIPT])
        finally:
            seed.close()

    def test_doom_gaze_from_the_wheel(self):
        import test_wc as W
        seed = Seed("regionofdoom", bc_output("base", ""))
        try:
            wheel, arrive = seed.script("sc_e_FAoutboard"), seed.script("sc_e_FAoutboard_1")
            st = W.State()
            r = W.Run(wheel, st, answers=[1])                              # (Find Doom Gaze.)
            self.assertEqual(len(r.offered[0]), 3)
            self.assertEqual(r.end[:2], ("ChangeMap", 2))
            self.assertEqual(st.get(B.BC_FLAGS, B.DOOM_SEARCH), 1)
            # (the script machine ends at ChangeScript; the game calls sc_map_10020 there and goes on: start after it)
            a = W.Run(arrive, st, start=4)
            self.assertTrue(a.did("EncountBoss"))
            self.assertEqual(st.get(B.BC_FLAGS, B.DOOM_SEARCH), 0)
            self.assertFalse(W.Run(arrive, st, start=4).did("EncountBoss"))   # the next flight is a flight
            st2 = W.State()
            st2.set(*B.DOOM_GAZE_BEATEN, 1)
            r2 = W.Run(wheel, st2, answers=[0])
            self.assertEqual(len(r2.offered[0]), 2)                        # beaten: the PR's own two choices
        finally:
            seed.close()

    def test_r_recasts_the_recruit_sites(self):
        rom = bc_output("r", "r")
        cap = capture_of("r")
        sites = {label: int(c) for c, label in cap["wor_recruits"].items() if label in B.SITES}
        self.assertGreaterEqual(len(sites), 9)
        seed = Seed("r", rom, capture=cap)
        try:
            done = seed.data["r"]["sites"]
            for site, new in sites.items():
                old = B.SITES[site][0]
                if new == old:
                    continue
                self.assertIn(site, done)
                joins = [o["operands"]["sValues"][0] for n in B.SITES[site][1] if os.path.exists(os.path.join(
                         seed.out, "files", *B.script_rel(n).split("/")))
                         for o in seed.script(n)["Mnemonics"] if o["mnemonic"] == "SysCall"]
                self.assertFalse([j for j in joins if j.endswith("：" + B.PR_NAMES[old]) and j.startswith("メンバー加入")], site)
                if site != "Mt. Zozo":                                          # the only site with no NPC object
                    self.assertGreater(done[site]["sprites"] + done[site]["calls"], 0, site)
        finally:
            seed.close()

    def test_r_name_boxes_follow_the_recast(self):
        """r: a recast site's lines name the newcomer (the PR's placeholder: (UMARO) -> (GAU) in the Sasquatch cave),
        the other speakers stay, and every changed key is one the baseline restores."""
        seed = Seed(f"{BASE} r mimetime notawaiter", bc_output("rmime", "r mimetime notawaiter"), capture=capture_of("rmime"))
        try:
            cha = seed.messages("story_cha_en")
            self.assertEqual(cha["E0790_02_496_a_01"], "(GAU)")
            self.assertNotIn("E0790_02_496_a_02", cha)                                 # Mog's line stays Mog's
            self.assertTrue(set(cha) <= set(B.speaker_keys()))
            self.assertGreater(seed.data["speakers"], 10)
        finally:
            seed.close()

    def test_banon_gives_bcs_two_items(self):
        """notawaiter: Banon's question gives both of BC's items (its skip's `80 item` pair, rerolled with t), not the
        PR's Gauntlet alone, on every path that gave it."""
        import idmap
        rom = bc_output("rmime", "r mimetime notawaiter")
        want = [idmap.item_content(rom[a + 1]) for a in B.BANON_ITEMS]
        seed = Seed(f"{BASE} notawaiter", rom)
        try:
            self.assertEqual(seed.data["notawaiter"]["banon"], want)
            gets = [o["operands"]["iValues"][0] for o in seed.script(B.BANON)["Mnemonics"] if o["mnemonic"] == "GetItem"]
            self.assertNotIn(B.GAUNTLET, gets)
            vanilla = sum(1 for o in S.load(B.BANON)["Mnemonics"] if o["mnemonic"] == "GetItem" and
                          o["operands"]["iValues"][0] == B.GAUNTLET)
            self.assertEqual(sorted(gets), sorted(want * vanilla))
        finally:
            seed.close()

    def test_mobliz_letters_at_once(self):
        import test_wc as W
        seed = Seed("notawaiter", bc_output("base", ""))
        try:
            sc = seed.script(B.LETTERS)
            calls = {"BC:pay 2500": lambda st: st.set("MapLocalVariable", 0, 1)}
            st = W.State()
            st.set("ScenarioFlag2", 247, 1)                                  # the first letter in hand
            r = W.Run(sc, st, answers=[0], syscalls=calls)
            self.assertTrue(r.did("SysCall", "BC:pay 2500"))
            self.assertTrue(all(st.get(c, i) == 1 for c, i in B.LETTER_FLAGS))
            st2 = W.State()                                                  # no letter yet: the PR's own line
            self.assertFalse(W.Run(sc, st2, answers=[0], syscalls=calls).did("SysCall", "BC:pay 2500"))
        finally:
            seed.close()

    def test_mimetime_spot_and_recruits_captured(self):
        rom = bc_output("mimetime", "mimetime")
        self.assertEqual(B.gogo_spot(rom), {"map": 0x80, "x": 76, "y": 31, "sprite": 5, "direction": 1})   # Duncan's, as Sabin
        self.assertIsNone(B.gogo_spot(bc_output("base", "")))
        cap = capture_of("mimetime")
        self.assertTrue(cap.get("wor_recruits"))            # BC's character per recruit site (prepare)

    def test_mimetime_places_gogo_in_bcs_disguise(self):
        """BC's Gogo (Duncan's cabin, as Sabin): his NPC in the WoR room's own layer, the script table row for his talk
        script, the talk (Zone Eater's recruit with Sabin along, else the PR's brush-off), the room showing him only in
        the World of Ruin until he's found, and the Zone Eater holding Gau instead."""
        import seed_live as L
        import test_wc as W
        seed = Seed(f"{BASE} mimetime", bc_output("mimetime", "mimetime"), capture=capture_of("mimetime"))
        try:
            part = seed.data["mimetime"]
            self.assertEqual((part["room"], part["tile"], part["disguise"]), ("Map_20401_1", [75, 31], 6))
            sid, name = B.GOGO_IDS[0x80], "sc_bc_gogo_80"
            layer = seed.file(B.MAP_REL.format(group="map_20401", folder="Map_20401", sub="Map_20401_1",
                                               file=B.GOGO_LAYER + ".json"))
            (npc,) = layer["layers"][0]["objects"]
            props = {p["name"]: p["value"] for p in npc["properties"]}
            self.assertEqual((props["asset_id"], props["script_id"]), (119 + 6, sid))
            with open(os.path.join(seed.out, *L.MASTER_PATH.split("/"), "script.csv"), encoding="utf-8", newline="") as f:
                self.assertEqual(P.Table("script", f.read()).rows[sid]["script_name"], name)
            talk = seed.file(B.new_rel(name))
            st = W.State()
            st.party = [6, 1]
            r = W.Run(talk, st)
            self.assertTrue(r.did("SysCall", "メンバー加入：ゴゴ"))
            self.assertEqual(st.get(B.BC_FLAGS, B.GOGO_FOUND), 1)
            self.assertTrue([t for t in r.did("SetPuppet") if t[2][1] == props["entity_id"]], "he goes once he's joined")
            st = W.State()
            st.party = [1, 2]
            r = W.Run(talk, st)
            self.assertFalse(r.did("SysCall", "メンバー加入：ゴゴ"))
            self.assertTrue(r.did("Msg", B.GOGO_WRONG))
            room = seed.script("sc_map_20401_1")
            for wor, found, shown in ((0, 0, False), (1, 0, True), (1, 1, False)):
                st = W.State()
                st.set("ScenarioFlag2", 41, wor)
                st.set(B.BC_FLAGS, B.GOGO_FOUND, found)
                self.assertEqual(bool(W.Run(room, st).did("SetEntities", B.GOGO_LAYER)), shown, (wor, found))
            joins = [o["operands"]["sValues"][0] for o in seed.script(B.GOGO_ZONE)["Mnemonics"] if o["mnemonic"] == "SysCall"]
            self.assertFalse([j for j in joins if j.endswith("ゴゴ")], joins)
            self.assertTrue([j for j in joins if j.endswith("ガウ") or j.startswith("BC:join 12")], joins)
            said = [o["operands"]["sValues"][0] for o in seed.script(B.GOGO_ZONE)["Mnemonics"] if o["mnemonic"] == "Msg"]
            self.assertEqual(said, ["E0241_00_001_b_01", "E0241_00_001_b_02", "E0241_00_001_b_03"])   # Gau's own words
        finally:
            seed.close()

    def test_alasdraco_casts_the_opera_in_the_prs_words(self):
        """alasdraco: BC's cast (captured as BC sets its dialogue variables) in the PR's own opera lines: names,
        factions, pronouns, the thrown item; every line keeps its codes (the sung lines' timing), none is left with a
        vanilla role name, and a cast name that is another role's ("Draco" as Ralse) isn't swapped twice."""
        import re
        import seed_live as L
        rom = bc_output("opera", "alasdraco")
        cap = capture_of("opera")
        v = cap["opera"]["vars"]
        seed = Seed(f"{BASE} alasdraco", rom, capture=cap)
        try:
            self.assertEqual(seed.data["alasdraco"]["cast"]["Maria"], v["maria"])
            story = {}
            with open(os.path.join(seed.out, *L.MESSAGE_PATH.split("/"), "story_mes_en.txt"), encoding="utf-8") as f:
                for line in f.read().splitlines():
                    k, t = line.split("\t", 1)
                    story[k] = t
            vanilla = P.messages("story_mes", "en")
            codes = lambda t: re.findall(r"<[^>]+>|\\n|\(FULL_SPACE\)", t)   # noqa: E731
            self.assertGreater(len(story), 40)
            for k, t in story.items():
                self.assertEqual(codes(t), codes(vanilla[k]), k)
            line = story["E0315_02_114_a_01"]
            for want in (v["maria"], v["draco"], v["operawest"]):
                self.assertIn(want, line)
            self.assertIn(f"of {v['dracoeir']} love", line)
            ralse = story["E0318_02_118_c_02"]
            self.assertIn(f"{v['ralsetitle']} {v['ralse']}", ralse)                     # e.g. "Sir Draco", not re-swapped
            self.assertIn(v["operaitem"], story["E0137_00_113_a_02"])
            cha = seed.messages("story_cha_en")                                         # the name boxes
            self.assertEqual(cha["E0315_00_112_a_01"], v["impresario"][0].upper() + v["impresario"][1:])
            self.assertTrue(set(cha) <= set(B.speaker_keys()))
            for k in B.OPERA_LINES:
                if k.startswith("SPEAKER_") or k not in story:
                    continue
                for role in ("Maria", "Ralse", "Impresario", "impresario"):
                    if role.lower() not in {x.lower() for x in (v["maria"], v["draco"], v["ralse"], v["impresario"])}:
                        self.assertNotRegex(story[k], rf"\b{role}\b", k)
        finally:
            seed.close()

    def test_airship_from_the_stables_and_the_wheel(self):
        import test_wc as W
        seed = Seed("airship", bc_output("base", ""))
        try:
            st = W.State()
            st.set("ScenarioFlag3", 36, 1)                                 # past the chocobo tutorial
            r = W.Run(seed.script("sc_chocobo_20071_1"), st, answers=[0])
            self.assertEqual(r.end, ("ChangeMap", 1, 1, "sc_e_BJoutboard_1"))
            self.assertEqual([t[2][:4] for t in r.did("SetVehicle")], [[B.BLACKJACK, 1, 85, 111]])
            self.assertFalse(r.did("RemoveGil"))
            r = W.Run(seed.script("sc_chocobo_20481_1"), st, answers=[0])
            self.assertEqual(r.end, ("ChangeMap", 2, 1, "sc_e_FAoutboard_1"))
            self.assertEqual(r.did("SetVehicle")[0][2][:4], [B.FALCON, 2, 62, 38])
            no = W.Run(seed.script("sc_chocobo_20071_1"), W.State(), answers=[1])
            self.assertEqual(no.end, ("Exit",))
            wheel = W.State()
            wheel.set("TreasureFlag4", 135, 1)                            # the Blackjack placed: the wheel's menu
            r = W.Run(seed.script("sc_e_BJoutboard"), wheel, answers=[1])
            self.assertEqual(len(r.offered[0]), 3)                          # the Floating Continent before it rose
            self.assertTrue(any(t[1] == "SetVehicle" and t[2][0] == B.FALCON for t in W.Run(seed.script("sc_e_0607_13"), W.State()).trace))
        finally:
            seed.close()

    def test_worringtriad_starts_in_the_world_of_ruin(self):
        import test_wc as W
        seed = Seed("worringtriad", bc_output("worringtriad", "worringtriad"))
        try:
            part = seed.data["worringtriad"]
            self.assertEqual(part["party"], [7])                       # Celes
            self.assertEqual(part["levels"]["7"], 24)                  # BC's see-saw: Strago 24 / Mog 25 averaged, +0
            self.assertEqual(part["free"], 12)                         # Gau (commands randomized: BC's free character)
            self.assertEqual(part["gil"], 50000)
            self.assertEqual(part["espers"], 12)
            sc = seed.script(B.OPENING)
            demo = W.State()
            demo.set("MapLocalVariable", 7, 1)                         # the title's attract demo
            r = W.Run(sc, demo, start=2)
            self.assertFalse(r.did("SysCall", "BC:join 7 24"))
            self.assertEqual(r.end[0], "ChangeMap")
            self.assertNotEqual(r.end[1], 2)
            st = W.State()
            r = W.Run(sc, st, start=2)
            self.assertEqual(r.end[:3], ("ChangeMap", 2, 2))            # the WoR's map, Albrook's arrival
            self.assertTrue(r.did("SysCall", "BC:join 7 24"))
            self.assertTrue(r.did("SysCall", "BC:join 12 26"))
            self.assertTrue(r.did("SysCall", "BC:gil 50000"))
            self.assertEqual(st.get("ScenarioFlag2", 41), 1)           # after the collapse
            self.assertEqual(st.get("ScenarioFlag2", 97), 0)           # no Falcon yet
            self.assertGreater(sum(t[2][1] for t in r.did("GetItem")), 600)
        finally:
            seed.close()


if __name__ == "__main__":
    unittest.main()
