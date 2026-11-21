"""Offline tests for Beyond Chaos's battle side (bc-battle: tools/bc_commands.py, bc_items.py, bc_codes.py,
bc_junction.py; plugin/BcPlugin's BcCommands/BcItems/BcCodes/BcJunction read what these write).

  pr/.venv/Scripts/python -m unittest discover -s pr/tests -p "test_bc_battle.py" -v

Each test runs a tool on a temporary folder holding the PR's vanilla tables (no ROM, no BC run), with
what BC's code would have captured, and checks the rows and the plugin's part. In-game checks: the
BcSelfTests registry (harness `bcselftest`) in one headless battle through the PC test runner.
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PR, "tools"))
import kitpath  # noqa: E402,F401
import prdata as P  # noqa: E402
import seed_live as L  # noqa: E402


def seed_folder(tables, messages=("system",)):
    """A temporary seed folder with the PR's vanilla `tables` and English `messages` files."""
    out = tempfile.mkdtemp(prefix="bc_battle_")
    mdir = os.path.join(out, *L.MASTER_PATH.split("/"))
    os.makedirs(mdir)
    for t in tables:
        shutil.copy(os.path.join(P.MASTER, t + ".csv"), mdir)
    gdir = os.path.join(out, *L.MESSAGE_PATH.split("/"))
    os.makedirs(gdir)
    for m in messages:
        shutil.copy(os.path.join(P.MESSAGE, m + "_en.txt"), gdir)
    return out


def table(out, name):
    with open(os.path.join(out, *L.MASTER_PATH.split("/"), name + ".csv"), encoding="utf-8") as f:
        return P.Table(name, f.read())


class Commands(unittest.TestCase):
    TABLES = ["command", "ability", "function_group", "ability_random_group", "content"]

    def setUp(self):
        self.out = seed_folder(self.TABLES)

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def run_apply(self, commands):
        import bc_commands
        log = []
        part = bc_commands.apply(self.out, commands, log.append)
        return part, log

    def test_ranges(self):
        import bc_commands as C
        self.assertEqual(C.snes_range(0x6E), (4, 4))        # all monsters
        self.assertEqual(C.snes_range(0x02), (5, 5))        # only self
        self.assertEqual(C.snes_range(0x04), (9, 9))        # everyone
        self.assertEqual(C.snes_range(0xC0), (9, 9))        # a random one of everyone
        self.assertEqual(C.snes_range(0x53), (3, 3))        # BC clears auto-confirm: one monster, picked
        self.assertEqual(C.snes_range(0x68), (20, 20))      # BC's 0x28 variant: a side
        self.assertTrue(C.random_target(0xC0, 3))
        self.assertTrue(C.random_target(0x68, 3))           # a side, on a skill that hits one
        self.assertFalse(C.random_target(0x6E, 4))
        self.assertFalse(C.random_target(0x29, 6))

    def test_skill_keeps_own_targeting(self):
        # Scan (SNES 0x18 -> Libra) with its own targeting: the row runs the skill's own ability
        part, _ = self.run_apply({28: {"name": "Scan", "targeting": 0x41, "kind": "skill", "skill": 0x18}})
        c = part[str(__import__("port").SNES_CMD[28])]
        self.assertEqual(c["ability"], c["abilities"][0])
        self.assertNotIn("skill_ability", c)
        self.assertNotIn("target", c)

    def test_variants(self):
        import idmap as M
        import port
        fire = M.spell(0x00)     # Fire: one monster or a side (0x61)
        part, log = self.run_apply({
            21: {"name": "Fire", "targeting": 0x02, "kind": "skill", "skill": 0x00},             # only self
            22: {"name": "Fire", "targeting": 0x04, "kind": "skill", "skill": 0x00},             # everyone
            24: {"name": "Scan", "targeting": 0x68, "kind": "skill", "skill": 0x18},             # random of a side
        })
        ab, ct = table(self.out, "ability"), table(self.out, "content")
        c = part[str(port.SNES_CMD[21])]
        self.assertEqual(c["skill_ability"], fire)
        self.assertNotEqual(c["ability"], fire)
        self.assertEqual((ab[c["ability"]]["renge_id"], ab[c["ability"]]["battle_renge_id"]), ("5", "5"))
        # the copy keeps the skill's function and name; the skill's own row is untouched
        self.assertEqual(ab[c["ability"]]["battle_function_group_id"], ab[fire]["battle_function_group_id"])
        self.assertEqual(ab[fire]["renge_id"], P.Table("ability")[fire]["renge_id"])
        names = {int(r["type_value"]): r["mes_id_name"] for r in ct.rows.values() if r["type_id"] == "4"}
        self.assertEqual(names[c["ability"]], names[fire])
        self.assertEqual(c["name"], "Fire")
        c = part[str(port.SNES_CMD[22])]
        self.assertEqual(ab[c["ability"]]["renge_id"], "9")
        self.assertNotIn("target", c)
        c = part[str(port.SNES_CMD[24])]
        self.assertEqual(c.get("target"), "random")
        self.assertEqual(ab[c["ability"]]["renge_id"], "20")
        cmd = table(self.out, "command")
        self.assertEqual(int(cmd[port.SNES_CMD[24]]["ability_id"]), c["ability"])

    def test_combo_repeated(self):
        import port
        # BC's MultipleSpellSub of a ComboSpellSub: each round A then B
        part, _ = self.run_apply({11: {"name": "3xLifCycl", "targeting": 0x41, "kind": "multiple", "count": 3,
                                       "inner": {"kind": "combo", "skills": [0x25, 0x87]}}})
        c = part[str(port.SNES_CMD[11])]
        self.assertEqual((c["kind"], c["inner"], c["count"], len(c["abilities"])), ("multiple", "combo", 3, 2))
        self.assertTrue(c["name"].startswith("Triple "))

    def test_random_chaos(self):
        import port
        # metronome: MagiTek -> R-Chaos (BC's wild sub: any of the 256 skills)
        part, _ = self.run_apply({29: {"name": "R-Chaos", "targeting": 0x04, "kind": "random", "class": "Chaos",
                                       "wild": True, "skills": []},
                                  27: {"name": "9xChaos", "targeting": 0x04, "kind": "multiple", "count": 9,
                                       "inner": {"kind": "random", "class": "Fire", "wild": True, "skills": []}}})
        c = part[str(port.SNES_CMD[29])]
        self.assertEqual(c["name"], "Random Chaos")
        self.assertGreater(len(c["abilities"]), 200)
        rg = table(self.out, "ability_random_group")
        rates = [int(r["invocation_rate"]) for r in rg.rows.values() if r["group_id"] == str(c["random_group"])]
        self.assertEqual(set(rates), {1})            # GetRandWeight draws by weight: each skill alike
        self.assertEqual(part[str(port.SNES_CMD[27])]["name"], "Random Chaos x9")
        ab = table(self.out, "ability")
        self.assertEqual(ab[c["ability"]]["renge_id"], "9")     # BC's 0x04 (the pick retargets)

    def test_repeated_names_fit(self):
        import bc_commands as C
        self.assertEqual(C.repeated_name("Random Ice", 2), "Double Random Ice")
        self.assertEqual(C.repeated_name("Random White Magic", 2), "Random White Magic x2")   # 308 px > the 256 box
        self.assertEqual(C.repeated_name("Random Fire", 3), "Triple Random Fire")
        self.assertEqual(C.repeated_name("Random Desperation", 4), "Random Desperation x4")
        self.assertEqual(C.repeated_name("Tsunami", 2), "Double Tsunami")          # a skill's name: no width known
        self.assertEqual(C.repeated_name("Random Ice", 9), "Random Ice x9")
        for word, w in C.RANDOM_WIDTH.items():                                    # every chosen form fits the box
            for n in (2, 3, 4):
                name = C.repeated_name("Random " + word, n)
                width = w + (C.PREFIX_WIDTH[C.TIMES[n]] if not name.endswith(f"x{n}") else C.SUFFIX_WIDTH)
                self.assertLessEqual(width, C.BOX + 3, name)                      # +3: the measured x9 form is 259

    def test_random_odds(self):
        import port
        # R-Ice: BC's 8-entry list, one skill listed twice (twice as likely)
        skills = [0x01, 0x01, 0x04, 0x07, 0x3A, 0x46, 0x47, 0x4B]
        part, _ = self.run_apply({19: {"name": "R-Ice", "targeting": 0x6E, "kind": "random", "class": "Ice",
                                       "wild": False, "skills": skills}})
        c = part[str(port.SNES_CMD[19])]
        rg = table(self.out, "ability_random_group")
        rates = {int(r["ability_id"]): int(r["invocation_rate"]) for r in rg.rows.values()
                 if r["group_id"] == str(c["random_group"])}
        self.assertEqual(sum(rates.values()), 100)
        import idmap as M
        self.assertEqual(rates[M.spell(0x01)], max(rates.values()))


EXE_ROM = os.path.join(os.path.dirname(PR), "build", "beyond-chaos", "Beyond Chaos CE 6.1.3 (New Player) 9859608359.sfc")


@unittest.skipUnless(os.path.exists(EXE_ROM) and os.path.exists(P.VANILLA_ROM), "needs BC's test seed ROM and the vanilla ROM")
class Items(unittest.TestCase):
    """bc_items.battle_part on the PR's vanilla tables with the New Player seed's ROM (BC's exe made it)."""

    @classmethod
    def setUpClass(cls):
        import json
        import bc_items
        import port_procs as PP
        cls.out = seed_folder(["weapon", "armor", "ability", "content", "function_group", "condition_group"])
        extra = os.path.join(cls.out, "files", PP.GROUP, *PP.ASSET.split("/")) + ".json"
        os.makedirs(os.path.dirname(extra))
        with open(extra, "w", encoding="utf-8") as f:
            json.dump(PP.vanilla_extra(), f)
        cls.part = bc_items.battle_part(cls.out, EXE_ROM, "", "", lambda m: None)
        with open(extra, encoding="utf-8") as f:
            cls.extra = json.load(f)
        cls.t = {n: table(cls.out, n) for n in ("weapon", "armor", "ability", "function_group", "condition_group")}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_breaks(self):
        w, a, ab = self.t["weapon"], self.t["armor"], self.t["ability"]
        life = 34                                       # Thunder Rod?: Life when used, used up, no proc
        rod = w[57]
        self.assertEqual(rod["destroy_rate"], "100")
        copy = ab[int(rod["trigger_ability_id"])]
        self.assertEqual(copy["battle_function_group_id"], ab[life]["battle_function_group_id"])
        self.assertEqual((copy["invalid_reflection"], copy["ability_wait"], copy["condition_group_id"]), ("1", "0", "0"))
        self.assertNotIn(57, [e["weapon_id"] for e in self.extra["add_ability_weapon"]])
        self.assertEqual(rod["process_prog"], "None")
        self.assertNotEqual(a[77]["trigger_ability_id"], "0")      # Behemoth Suit?: Doom
        self.assertEqual(a[43]["destroy_rate"], "0")                # Cat Hood?: Life 3, never used up
        self.assertEqual(a[11]["trigger_ability_id"], "283")        # Flame Shield: vanilla's copy kept

    def test_procs(self):
        procs = {e["weapon_id"]: e for e in self.extra["add_ability_weapon"]}
        for weapon in (40, 76, 82):                                 # Kodachi?, Bone Club?, Trump?
            self.assertIn(weapon, procs)
            self.assertEqual(procs[weapon]["ability_per"], 25)
            self.assertEqual(self.t["weapon"][weapon]["process_prog"], "ADD_MAGIC")
        self.assertEqual(self.t["ability"][procs[40]["ability_id"]]["type_id"], "629")

    def test_throw_and_left_to_the_porter(self):
        w, vw = self.t["weapon"], P.Table("weapon")
        self.assertEqual(w[38]["throw_flag"], "1")                  # every weapon throwable
        # Evade, MBlock and worn statuses are the shared porter's (2026-11-20): left as the tables had them
        for k in (9, 59, 62, 66, 79):
            for col in ("evasion_rate", "wear_function_group_id", "wear_condition_group_id"):
                self.assertEqual(w[k][col], vw[k][col], (k, col))

    def test_changers(self):
        pairs = {(r["function1_value1"], r["function1_value2"]) for r in self.t["function_group"].rows.values()
                 if r["function1_id"] == "61"}
        self.assertIn(("18", "23"), pairs)                          # Sketch -> Rage (was Fight -> Jump)
        self.assertNotIn(("1", "30"), pairs)

    def test_plugin_part(self):
        self.assertEqual(self.part["vigor"], [325])                 # Gale Hairpin
        self.assertEqual(self.part["immune"], {"158": [33]})        # Rainbow Brush: no Vanish
        self.assertEqual(self.part["auto"], {"161": [26], "300": [26]})   # auto Stop: Pinwheel, Hero's Ring
        self.assertEqual(self.part["rerise"], [371])


@unittest.skipUnless(os.path.exists(EXE_ROM) and os.path.exists(P.VANILLA_ROM), "needs BC's test seed ROM and the vanilla ROM")
class Codes(unittest.TestCase):
    """bc_codes' data that needs BC's ROM (the New Player seed: `s`, swdtechspeed:faster)."""

    def setUp(self):
        self.out = seed_folder(["ability", "learning", "content"])

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def test_rom_data(self):
        import bc_codes
        done = bc_codes.rom_data(self.out, EXE_ROM, "", lambda m: None)
        self.assertEqual(done["swdtechspeed"], {"speed": "faster", "factor": 8})
        ab = table(self.out, "ability")
        self.assertEqual([ab[a]["ability_wait"] for a in range(124, 132)], ["1", "1", "1", "1", "1", "2", "2", "2"])
        # natural magic is the shared porter's (port_spells follows BC's JSL): rom_data leaves the learning table,
        # Cyan's Bushido and Sabin's Blitz level rows (type 1, jobs 3 and 6) included
        self.assertNotIn("natural_magic", done)
        le, vle = table(self.out, "learning"), P.Table("learning")
        self.assertEqual({k: r for k, r in le.rows.items()}, {k: r for k, r in vle.rows.items()})
        # the reader still reads BC's table right: Celes's 16 spells as BC's log lists them
        part = bc_codes.natural_magic(self.out, EXE_ROM, lambda m: None)
        self.assertEqual(part["7"][0], [36, 4])                           # Antdot at 4

    def test_blitz_readback(self):
        import bc_codes
        part = bc_codes.blitz_inputs({}, self.out, P.VANILLA_ROM, "", lambda m: None)
        self.assertEqual(part["134"], [3, 4, 8, 12])                     # Suplex: X Y down up
        self.assertEqual(len(part), 7)                                   # Pummel is never BC's


@unittest.skipUnless(os.path.exists(EXE_ROM), "needs BC's test seed ROM")
class CodeReaders(unittest.TestCase):
    """bc_codes' seed-time readers on BC's ROM with one code's bytes written in (as BC's patch writes them): what each
    reads back for the plugin, and nothing when the code's bytes aren't there. No BC run, no seed folder."""

    @classmethod
    def setUpClass(cls):
        import ff6snes as S
        cls.S = S
        cls.base = bytes(S.rom_bytes(EXE_ROM))
        cls.n = 0

    def rom(self, patch):
        """BC's ROM with {file offset: bytes} written in, registered in memory under a fake path."""
        d = bytearray(self.base)
        for at, b in patch.items():
            d[at:at + len(b)] = bytes(b)
        CodeReaders.n += 1
        path = os.path.abspath(f"bc_battle_test_{CodeReaders.n}.sfc")
        self.S.MEMORY[path] = bytes(d)
        self.addCleanup(self.S.MEMORY.pop, path, None)
        return path

    def read(self, fn, rom):
        return fn({}, "", rom, "", lambda m: None)

    def test_levelcap(self):
        import bc_codes as C
        caps = [99] * 14
        caps[0], caps[5], caps[13] = 38, 21, 40
        part = self.read(C.levelcap, self.rom({C.LEVEL_CAPS: caps}))
        self.assertEqual(part, {"caps": {"1": 38, "6": 21, "14": 40}})        # 99 = no cap

    def test_cursepower(self):
        import bc_codes as C
        at = C.CURSE_GOAL
        self.assertEqual(self.read(C.cursepower, self.rom({at - 4: [0xAD, 0xC0, 0x3E, 0xC9, 10]})), {"battles": 10})
        self.assertIsNone(self.read(C.cursepower, EXE_ROM))                    # vanilla's INC/BNE: not BC's patch

    def test_norng(self):
        import bc_codes as C
        self.assertEqual(self.read(C.norng, self.rom({C.RNG_TABLE: [0] * 256})), {"zero": True})
        self.assertIsNone(self.read(C.norng, EXE_ROM))                          # b's shuffled table

    def test_playsitself(self):
        import bc_codes as C
        # Fight (0), Magic (2), Steal (5) allowed in both tables; Item (1) only in the first
        auto = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 5)
        both = (1 << 0) | (1 << 2) | (1 << 5)
        part = self.read(C.playsitself, self.rom({C.NO_MENU: [0x80], 0x204D0: auto.to_bytes(4, "little"),
                                                   0x204D4: both.to_bytes(4, "little")}))
        self.assertEqual(part["commands"], [1, 7, 10])                         # PR Attack, Magic, Steal
        self.assertIsNone(self.read(C.playsitself, EXE_ROM))

    def test_markers(self):
        import bc_codes as C
        exe = EXE_ROM                                                           # New Player has all three
        self.assertEqual(self.read(C.mpparty, exe), {"on": True})
        self.assertEqual(self.read(C.magicnumbers, exe), {"on": True})
        self.assertEqual(self.read(C.informativemiss, exe), {"on": True})
        bare = self.rom({C.MP_REFILLS: [0xFF] * 8, C.MP_DIGITS: [0xEB], C.INFORM_MISS: [0xB9, 0xA1, 0x3A]})
        for fn in (C.mpparty, C.magicnumbers, C.informativemiss):
            self.assertIsNone(self.read(fn, bare), fn.__name__)

    def test_mementomori(self):
        import bc_codes as C
        import idmap as M
        patch = {C.MEMENTO_HOOK: [0x48]}
        for c in range(14):                                                     # BC's 14 stubs, relic FF = none
            at = C.MEMENTO_RELIC + 0x11 * c
            patch[at - 15] = [0xC9, c]
            patch[at - 1] = [0xA9, 0xFF]
        relic = 0xD0                                                            # a relic item for Locke (1)
        patch[C.MEMENTO_RELIC + 0x11 - 1] = [0xA9, relic]
        part = self.read(C.mementomori, self.rom(patch))
        kind, pid = M.item(relic)
        self.assertEqual(part, {"relics": {"2": {"armor": pid, "content": M.content_id(kind, pid), "snes": relic}}})
        self.assertIsNone(self.read(C.mementomori, EXE_ROM))

    def test_swdtechspeed_variants(self):
        import bc_codes as C
        for code, (name, factor) in C.SWDTECH_SPEEDS.items():
            out = seed_folder(["ability"])
            self.addCleanup(shutil.rmtree, out, True)
            got = C.swdtechspeed(out, self.rom({C.SWDTECH_GAUGE: code}), lambda m: None)
            self.assertEqual(got, {"speed": name, "factor": factor})
            waits = [int(table(out, "ability")[a]["ability_wait"]) for a in C.BUSHIDO]
            self.assertEqual(waits, [max(1, round(w / factor)) for w in (3, 5, 7, 9, 11, 13, 15, 17)])
        out = seed_folder(["ability"])
        self.addCleanup(shutil.rmtree, out, True)
        self.assertIsNone(C.swdtechspeed(out, self.rom({C.SWDTECH_GAUGE: [0xA5, 0x0E, 0x29, 0x03]}), lambda m: None))

    def test_umaro_risk(self):
        import bc_codes as C
        out = seed_folder(["character_status"])
        self.addCleanup(shutil.rmtree, out, True)
        got = C.umaro_risk(out, self.rom({C.BERSERKER: [3]}), "b u", lambda m: None)   # SNES character 3: Shadow
        self.assertEqual(got, {"berserker": 4})
        cs = table(out, "character_status")
        self.assertEqual((cs[4]["initial_condition_group"], cs[14]["initial_condition_group"]), (C.UMARO_GROUP, "0"))
        self.assertIsNone(C.umaro_risk(out, self.rom({C.BERSERKER: [3]}), "b", lambda m: None))   # no `u`


if __name__ == "__main__":
    unittest.main()
