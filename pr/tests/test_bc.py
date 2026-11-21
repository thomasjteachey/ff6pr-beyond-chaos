"""Offline tests for the Beyond Chaos port (tools/bc_*.py, plugin/BcPlugin's flags).

  pr/.venv/Scripts/python -m unittest discover -s pr/tests -p "test_bc.py" -v

  * the flags: bc_flags.json covers every flag BC's own options.py has, and every flag string the
    in-game screen makes (plugin/Bc.Tests writes them: bc_flags_cases.tsv) is read by BC's own parser
    as the screen meant it
  * the generator: BC's source (tools/bc_run.py) makes BC's exe's ROM for the same seed (needs the
    vanilla ROM and the exe's ROM in build/beyond-chaos; ~29 s, skipped while everything it reads is as it was
    when it last passed: pr/cache/test_bc_parity.json, BC_PARITY_FULL=1 runs it), and a seed folder (tools/bc_seed.py)
    holds full tables, its files in the managed list and its json (BC_SEED_TEST=1: ~25 s)
The porter's own checks run on a BC seed with tools/bc_seed.py --keep-port, then
PR_MOD=BCSeed tests/test_mod.py.
"""
import glob
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.dirname(HERE)
PROJECT = os.path.dirname(PR)
sys.path.insert(0, os.path.join(PR, "tools"))
import kitpath  # noqa: E402,F401
import bc_run  # noqa: E402

FLAGS_JSON = os.path.join(PR, "plugin", "BcPlugin", "bc_flags.json")
CASES = os.path.join(PR, "plugin", "Bc.Tests", "bc_flags_cases.tsv")
EXE_ROMS = glob.glob(os.path.join(PROJECT, "build", "beyond-chaos", "Beyond Chaos CE 6.1.3 (*) *.sfc"))


def bc_options():
    """BC's options module, loaded as bc_run runs BC."""
    src, home = os.path.abspath(bc_run.SRC), os.path.abspath(bc_run.HOME)
    if not os.path.isfile(os.path.join(src, "options.py")):
        raise unittest.SkipTest(f"no Beyond Chaos source at {src}")
    cwd = os.getcwd()
    os.chdir(home)
    sys._MEIPASS = src
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import options
        options.get_makeover_groups()
        return options
    finally:
        os.chdir(cwd)


class BcFlags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.O = bc_options()
        cls.doc = json.load(open(FLAGS_JSON, encoding="utf-8"))

    def test_every_bc_flag_is_on_the_screen(self):
        names = {f.name for f in list(self.O.NORMAL_FLAGS) + list(self.O.MAKEOVER_MODIFIER_FLAGS)
                 if f.category != "cave"}
        self.assertEqual(names - set(self.doc["flags"]), set())
        on_rows = {r["flag"] for s in self.doc["sections"] for r in s["rows"]}
        self.assertEqual(set(self.doc["flags"]) - on_rows, set(), "flags without a row")

    def test_labels_are_words_not_bc_program_names(self):
        for name, d in self.doc["flags"].items():
            self.assertFalse(d["label"].isupper() and len(d["label"]) > 3, f"{name}: {d['label']}")
            self.assertNotIn("_", d["label"], name)

    def test_presets_are_bcs(self):
        import config
        self.assertEqual(set(self.doc["presets"]), set(config.SUPPORTED_PRESETS))

    def test_screen_strings_read_by_bcs_parser(self):
        if not os.path.exists(CASES):
            self.skipTest("run plugin/Bc.Tests first (dotnet run -c Release)")
        O = self.O
        O.Options_.mode = O.get_mode("normal")
        flags_by_name = {f.name: f for f in list(O.NORMAL_FLAGS) + list(O.MAKEOVER_MODIFIER_FLAGS)}
        n = 0
        for line in open(CASES, encoding="utf-8"):
            name, text = line.rstrip("\n").split("\t", 1)
            want = {}
            for tok in text.split():
                k, _, v = tok.partition(":")
                self.assertIn(k, flags_by_name, f"{name}: {tok} isn't a BC flag")
                want[k] = v or "True"
            out = io.StringIO()
            import contextlib
            with contextlib.redirect_stdout(out):
                O.activate_from_string(text)
            have = {f.name: str(f.value) for f in flags_by_name.values() if f.value != ""}
            for k, v in want.items():
                if k in have:
                    self.assertEqual(have[k].lower(), v.lower(), f"{name}: {k}")
                else:
                    # BC itself drops a few combinations (sketch with remonsterate): it says so
                    self.assertIn(k, out.getvalue(), f"{name}: {k} not active and not reported")
            n += 1
        self.assertGreater(n, 300)


@unittest.skipUnless(EXE_ROMS and os.path.exists(os.path.join(PROJECT, "rom", "vanilla", "Final Fantasy III (USA).sfc")),
                     "needs the vanilla ROM and a ROM made by BC's exe")
class BcParity(unittest.TestCase):
    # ~29 s, and its inputs rarely change (the pre-flight reruns test_bc on any tools/ or data/ edit): a pass is
    # remembered with a fingerprint of everything the run reads, and the same inputs again skip it.
    # BC_PARITY_FULL=1 always runs it.
    CACHE = os.path.join(PR, "cache", "test_bc_parity.json")

    @staticmethod
    def inputs_fp():
        """What the run reads: bc_run and the porter modules it calls (by content), BC's source and its release
        files (custom/, remonsterate/, tables/, Config.ini; by size and time), both ROMs and the spoiler log."""
        import hashlib
        import prdata as P
        import ff6snes as S
        h = hashlib.sha1(sys.version.encode())
        tools = os.path.dirname(os.path.abspath(bc_run.__file__))
        for f in (bc_run.__file__, os.path.join(tools, "bc_remon.py"), S.__file__, P.__file__):
            if os.path.isfile(f):
                h.update(f.encode() + open(f, "rb").read())
        rom = EXE_ROMS[0]
        for p in (P.VANILLA_ROM, rom, os.path.splitext(rom)[0] + ".txt", os.path.join(bc_run.HOME, "Config.ini")):
            st = os.stat(p) if os.path.exists(p) else None
            h.update(f"{os.path.basename(p)}|{st and st.st_size}|{st and st.st_mtime_ns}\n".encode())

        def tree(d, rel):   # scandir: Windows hands back each file's size and time with the listing (~17,000 files)
            try:
                entries = sorted(os.scandir(d), key=lambda e: e.name)
            except OSError:
                h.update(f"{rel}|missing\n".encode())
                return
            for e in entries:
                if e.name.startswith(".") or e.name == "__pycache__" or e.name.endswith(".pyc"):
                    continue
                if e.is_dir():
                    tree(e.path, f"{rel}/{e.name}")
                else:
                    st = e.stat(follow_symlinks=False)
                    h.update(f"{rel}/{e.name}|{st.st_size}|{st.st_mtime_ns}\n".encode())

        tree(bc_run.SRC, "src")
        for d in ("custom", "remonsterate", "tables"):
            tree(os.path.join(bc_run.HOME, d), d)
        return h.hexdigest()

    def test_source_makes_the_exes_rom(self):
        full = os.environ.get("BC_PARITY_FULL") == "1"
        try:
            with open(self.CACHE, encoding="utf-8") as f:
                last = json.load(f)
        except (OSError, ValueError):
            last = {}
        if not full and last.get("fp") == self.inputs_fp():
            self.skipTest(f"same inputs as the run that passed at {last.get('when')} (BC_PARITY_FULL=1 runs it)")
        # the exe's spoiler log names its seed string on the first line
        rom_path = EXE_ROMS[0]
        first = open(os.path.splitext(rom_path)[0] + ".txt", encoding="utf-8", errors="replace").readline()
        version, mode, flags, seed = first.split(":", 1)[1].strip().split("|")
        import prdata as P
        import ff6snes as S
        data, spoiler = bc_run.run(S.rom_bytes(P.VANILLA_ROM), seed, mode, flags, say=lambda _: None)
        exe = open(rom_path, "rb").read()
        self.assertEqual(len(data), len(exe))
        diff = sum(1 for a, b in zip(data, exe) if a != b)
        self.assertEqual(diff, 0, f"{diff} bytes differ from the exe's ROM")
        # passed: remember the inputs as they are now (after the run: anything it wrote is in the fingerprint)
        import time
        os.makedirs(os.path.dirname(self.CACHE), exist_ok=True)
        tmp = f"{self.CACHE}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"fp": self.inputs_fp(), "when": time.strftime("%Y-%m-%d %H:%M")}, f)
        os.replace(tmp, self.CACHE)


class BcGuideInGame(unittest.TestCase):
    """The seed's guide in the game's message window (tools/bc_guide.py; BcPlugin/BcGuide.cs starts it)."""

    PAGES = [{"title": "Beyond Chaos", "lines": ["intro"]},
             {"title": "Random Ice", "lines": ["Each use picks one at random: Blizzard (38%), Blizzara (13%), Blizzaga (12%), "
                                               "Absolute Zero (10%), Snowball (9%), Ice Rabbit (9%) and 3 more.",
                                               "(It replaced Steal.)"]},
             {"title": "Equipment", "lines": ["Weapons, armor and relics are rerolled: their stats, elements, the spells",
                                              "they cast or teach. Read an item's description before you rely on it."]}]

    def test_windows_fit_and_read_like_the_games_lessons(self):
        import re
        import bc_guide as G
        texts = G.in_game(self.PAGES, {"seed": "1234567890"}, "Normal")
        self.assertEqual(len(texts), len(self.PAGES) + 1)   # the question, a message per page after the first, the end
        self.assertIn("seed 1234567890, Normal mode", texts[0])
        self.assertTrue(texts[0].endswith("Shall I explain what's different in this game?"))
        self.assertTrue(texts[1].startswith("-Random Ice-" + G.NL))
        for t in texts:
            for window in t.split(G.PAGE):
                shown = re.sub(r"<[^>]+>", "", window).replace(G.NL, " ")
                self.assertLessEqual(len(shown), G.ROOM, window)
                self.assertNotIn("\n", window)        # a real line break would end the text file's line
        self.assertIn("(It replaced Steal.)", texts[1])

    def test_script_asks_then_shows_each_message(self):
        import bc_guide as G
        import pr_script as S
        sc = G.guide_script(4)
        ms = sc["Mnemonics"]
        self.assertEqual([m["operands"]["sValues"][0] for m in ms if m["mnemonic"] == "Msg"],
                         [G.GUIDE_KEY.format(n) for n in range(4)])
        branch = next(m for m in ms if m["mnemonic"] == "Branch")
        # a No goes on after the jump's target: the end
        self.assertEqual(ms[branch["operands"]["iValues"][2] + 1]["mnemonic"], "Exit")
        # the school's lesson question is written the same way (its Branch's operands)
        school = S.load("sc_e_0023")["Mnemonics"]
        want = next(m for m in school if m["mnemonic"] == "Branch")["operands"]
        self.assertEqual(branch["operands"]["sValues"], want["sValues"])
        self.assertEqual(branch["operands"]["iValues"][:2], want["iValues"][:2])
        self.assertEqual(sc["Segments"][0]["Count"], len(ms))
        empty = G.guide_script(0)["Mnemonics"]
        self.assertEqual([m["mnemonic"] for m in empty if m["mnemonic"] != "Nop"], ["Exit"])

    def test_baseline_lists_the_guide_in_its_map(self):
        import bc_guide as G
        import bc_live as L
        self.assertIn(G.GUIDE_REL, L.managed_files())
        out = tempfile.mkdtemp()
        try:
            L.write_baseline(out)
            pkg = json.load(open(os.path.join(out, G.GUIDE_GROUP, "Assets", "GameAssets", "Serial", "Res", "Map",
                                              G.GUIDE_FOLDER, "package.json"), encoding="utf-8"))
            entry = next(m for m in pkg["map"] if m["name"] == G.GUIDE_SUB)
            self.assertIn({"name": G.GUIDE_SCRIPT, "asset": f"{G.GUIDE_SUB}/{G.GUIDE_SCRIPT}"}, entry["script"])
            self.assertTrue(any(s["name"] == "sc_e_0001_5" for s in entry["script"]))   # the map's own scripts kept
            keys = {}
            for f in glob.glob(os.path.join(out, G.GUIDE_GROUP, "keys", "*.json")):
                d = json.load(open(f, encoding="utf-8"))
                keys.update(zip(d["keys"], d["values"]))
            self.assertEqual(keys.get("package"), f"Assets/GameAssets/Serial/Res/Map/{G.GUIDE_FOLDER}/package")
            self.assertEqual(keys.get(f"{G.GUIDE_SUB}/{G.GUIDE_SCRIPT}"),
                             f"Assets/GameAssets/Serial/Res/Map/{G.GUIDE_FOLDER}/{G.GUIDE_SUB}/{G.GUIDE_SCRIPT}")
            base = json.load(open(os.path.join(out, *G.GUIDE_REL.split("/")), encoding="utf-8"))
            self.assertFalse(any(m["mnemonic"] == "Msg" for m in base["Mnemonics"]))
        finally:
            shutil.rmtree(out, ignore_errors=True)


@unittest.skipUnless(os.environ.get("BC_SEED_TEST") == "1", "BC_SEED_TEST=1 makes a seed (~25 s)")
class BcSeedFolder(unittest.TestCase):
    def test_seed_folder(self):
        import subprocess
        import bc_live as L
        out = os.path.join(tempfile.mkdtemp(), "seed")
        try:
            p = subprocess.run([sys.executable, os.path.join(PR, "tools", "bc_seed.py"), "--seed", "1234567890",
                                "--preset", "New Player", "--out", out], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(p.returncode, 0, p.stdout[-2000:] + p.stderr[-2000:])
            info = json.load(open(os.path.join(out, "bc_seed.json"), encoding="utf-8"))
            self.assertEqual(info["seed"], "1234567890")
            self.assertEqual(info["mode"], "normal")
            self.assertEqual(info["unmanaged"], 0)
            managed = set(L.managed_files())
            self.assertEqual(set(info["files"]) - managed, set())
            for t in L.MANAGED_TABLES:
                self.assertTrue(os.path.exists(os.path.join(out, *L.MASTER_PATH.split("/"), t + ".csv")), t)
            self.assertTrue(os.path.exists(os.path.join(out, "bc_log.txt")))
            self.assertIn("snes_ai", info)
            # the in-game guide: its script among the seed's files, its messages in the seed's text
            import bc_guide as G
            self.assertIn(G.GUIDE_REL, info["files"])
            sc = json.load(open(os.path.join(out, "files", *G.GUIDE_REL.split("/")), encoding="utf-8"))
            self.assertEqual(sum(m["mnemonic"] == "Msg" for m in sc["Mnemonics"]), info["guide_messages"])
            self.assertEqual(info["guide_messages"], len(info["guide"]) + 1)
            text = open(os.path.join(out, *L.MESSAGE_PATH.split("/"), "system_en.txt"), encoding="utf-8").read()
            for n in range(info["guide_messages"]):
                self.assertIn(G.GUIDE_KEY.format(n) + "\t", text)
        finally:
            shutil.rmtree(os.path.dirname(out), ignore_errors=True)


class BcDataSteps(unittest.TestCase):
    """tools/bc_data.py's text steps on a seed folder's text: the Coral and the auctioneer's lines."""

    def setUp(self):
        import bc_data
        import seed_live
        self.D, self.L = bc_data, seed_live
        self.out = tempfile.mkdtemp()
        self.msg = os.path.join(self.out, *seed_live.MESSAGE_PATH.split("/"))
        os.makedirs(self.msg)
        with open(os.path.join(self.msg, "system_en.txt"), "w", encoding="utf-8", newline="") as f:
            f.write("MSG_KEY_NAME_06\t<IC_IOBJ>Coral\r\nMSG_KEY_INF_09\tA piece of coral found in the cave at Ebot's Rock.")
        with open(os.path.join(self.msg, "story_mes_en.txt"), "w", encoding="utf-8", newline="") as f:
            f.write("OTHER_STEP_KEY\tkept\r\n")

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def read(self, name):
        with open(os.path.join(self.msg, name), encoding="utf-8") as f:
            return dict(line.split("\t", 1) for line in f.read().splitlines() if "\t" in line)

    def test_coral_names_the_item_its_description_and_lines(self):
        self.D.coral(self.out, "Crystal")
        text = self.read("system_en.txt")
        self.assertEqual(text["MSG_KEY_NAME_06"], "<IC_IOBJ>Crystal")
        self.assertIn("piece of crystal", text["MSG_KEY_INF_09"])
        story = self.read("story_mes_en.txt")
        self.assertEqual(story["OTHER_STEP_KEY"], "kept")
        self.assertEqual(len([k for k in self.D.CORAL_LINES if "Crystal" in story.get(k, "")]), len(self.D.CORAL_LINES))

    def test_auctioneer_names_the_seeds_items(self):
        self.D.auction_lines(self.out, {"287": 288})
        self.assertEqual(self.read("story_mes_en.txt")[self.D.AUCTION_LINES[287]], "...a fine Angel Ring!")

    def test_natural_moved_names_the_changed_characters(self):
        import prdata as P
        t = P.Table("learning")
        terra = next(r for r in t.rows.values() if r["type_id"] == "1" and r["job_id"] == "1")
        terra["job_id"] = "7"                                       # one of Terra's spells moved to Celes
        path = os.path.join(self.out, *self.L.MASTER_PATH.split("/"), "learning.csv")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(t.to_csv(t.rows.keys()))
        self.assertEqual(self.D.natural_moved(self.out), [1, 7])
        self.assertEqual(self.D.natural_moved(tempfile.mkdtemp()), [])   # no learning table: nothing moved

    def test_coral_name_title_cases_capitals(self):
        import ff6snes as S
        rom = bytearray(0x0F0000)
        inv = {v: k for k, v in S._NAME.items()}
        for i, ch in enumerate("CRYSTAL"):
            rom[self.D.CORAL_NAME + i] = inv[ch]
        for i in range(7, 12):
            rom[self.D.CORAL_NAME + i] = 0xFF
        self.assertEqual(self.D.coral_name(bytes(rom)), "Crystal")


class BcGifts(unittest.TestCase):
    """tools/bc_gifts.py: BC's rerolled event gifts given by the PR's scripts, their lines naming them."""

    def setUp(self):
        import bc_gifts
        import seed_live
        self.G, self.L = bc_gifts, seed_live
        self.out = tempfile.mkdtemp()
        self.msg = os.path.join(self.out, *seed_live.MESSAGE_PATH.split("/"))
        os.makedirs(self.msg)
        with open(os.path.join(self.msg, "system_en.txt"), "w", encoding="utf-8", newline="") as f:
            f.write("OTHER\tkept\r\n")

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def script(self, name):
        import pr_script as S
        with open(os.path.join(self.out, "files", *S.rel(name).split("/")), encoding="utf-8") as f:
            return json.load(f)

    def lines(self):
        with open(os.path.join(self.msg, "system_en.txt"), encoding="utf-8") as f:
            return dict(line.split("\t", 1) for line in f.read().splitlines() if "\t" in line)

    def test_table_matches_vanilla_scripts(self):
        self.assertTrue(self.G.check())

    def test_item_gil_and_tag_gifts(self):
        import idmap as M
        flame = next(b for b in range(256) if M.item_content(b) == 207)          # the Flame Shield's SNES id
        items = [{"pointer": 0xC9257, "after": {"type": 0x40, "contents": flame}},    # Vector: Tintinnabulum
                 {"pointer": 0xB313F, "after": {"type": 0x80, "contents": 25}},       # the Sealed Gate's gil
                 {"pointer": 0xB4B03, "after": {"type": 0x40, "contents": flame}},    # Owzer's: a Tag line
                 {"pointer": 0xC926C, "after": {"type": 0x40, "contents": 0xDF}}]     # Ward Bangle: the PR's own
        written, done = self.G.apply(self.out, items, "t", log=lambda m: None)
        self.assertEqual(len(written), 3)
        ops = self.script("sc_e_0506")["Mnemonics"]
        gives = [m["operands"]["iValues"][:2] for m in ops if m["mnemonic"] == "GetItem"]
        self.assertEqual(gives, [[207, 1], [322, 1]])               # the Ward Bangle stays the PR's
        self.assertEqual(self.lines()["BC_GIFT_C9257_0"], "<CT>Obtained Flame Shield!")
        self.assertEqual(self.lines()["OTHER"], "kept")
        gil = [m["operands"]["iValues"][:2] for m in self.script("sc_e_0453")["Mnemonics"] if m["mnemonic"] == "GetItem"]
        self.assertEqual(gil, [[1, 2500]])
        self.assertEqual(self.lines()["BC_GIFT_B313F_0"], "<CT>Obtained 2500 gil!")
        tag = [m["operands"]["sValues"][:2] for m in self.script("sc_e_0769_1")["Mnemonics"] if m["mnemonic"] == "Tag"]
        self.assertEqual(tag, [["ITEM_N", self.G.name_key(207)]])

    def test_another_steps_script_without_the_give_is_passed_by(self):
        import pr_script as S
        sc = S.load("sc_e_0238")
        for m in sc["Mnemonics"]:
            if m["mnemonic"] == "GetItem":
                m["operands"]["iValues"][0] = 2                         # another step gave something else
        dest = os.path.join(self.out, "files", *S.rel("sc_e_0238").split("/"))
        os.makedirs(os.path.dirname(dest))
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(sc, f)
        written, done = self.G.apply(self.out, [{"pointer": 0xC6883, "after": {"type": 0x40, "contents": 0xDF}}],
                                     "t", log=lambda m: None)
        self.assertEqual((written, done), ([], {}))

    def test_espers_trade_places_and_names(self):
        import idmap as M
        G = self.G
        rom, van = bytearray(0x400000), bytearray(0x400000)
        swap = {1: 2, 2: 1, 11: 0, 16: 12}         # Ifrit <-> Shiva, Odin -> Ramuh, Ragnarok -> Raiden
        for a, _ in G.magicite_table():
            van[a] = rom[a] = 0x86
        van[0xC79D9 + 1], van[0xC79E9 + 1] = 0x36 + 1, 0x36 + 2
        for a in (0xC1ED1, 0xC1F81):
            van[a + 1] = 0x36 + 11
        van[0xC0B53 + 1] = 0x36 + 16
        for a, _ in G.magicite_table():
            o = van[a + 1] - 0x36
            rom[a + 1] = 0x36 + swap.get(o, o) if van[a + 1] else 0
        written, names = G.espers(self.out, bytes(rom), bytes(van), "y", log=lambda m: None)
        self.assertEqual(names, {"Ifrit": "Shiva", "Shiva": "Ifrit", "Odin": "Ramuh", "Ragnarok": "Raiden"})
        gives = lambda n: [m["operands"]["iValues"][0] for m in self.script(n)["Mnemonics"]
                           if m["mnemonic"] in ("GetItem", "RemoveItem")]
        self.assertEqual(gives("sc_e_0399"), [M.esper_content(2)])
        self.assertEqual(gives("sc_e_0400"), [M.esper_content(1)])
        self.assertEqual(gives("sc_e_0890"), [M.esper_content(0), M.esper_content(12)])   # Odin's taken: Ramuh
        with open(os.path.join(self.msg, "story_mes_en.txt"), encoding="utf-8") as f:
            story = dict(line.split("\t", 1) for line in f.read().splitlines())
        self.assertEqual(story["E0399_00_398_a_01"], "<CT>Obtained Shiva magicite!")
        self.assertEqual(story["E0400_00_398_a_02"], "<CT>Obtained Ifrit magicite!")
        self.assertTrue(self.lines()[self.G.name_key(self.G.SWORD)].endswith("Raiden"))
        self.assertEqual(G.espers(self.out, bytes(rom), bytes(van), "t", log=lambda m: None), ([], {}))   # no y


class BcBingo(unittest.TestCase):
    """bingoboingo (audit gap #2): BC's run with the exe's bingo defaults (bc_run.BINGO) makes its card instead of
    crashing on `size ** 2` with None, and bc_run hands the card over (capture["bingo"]), leaving no file behind."""

    def test_bingoboingo_makes_a_card(self):
        import ff6snes as S
        import prdata as P
        import bc_trace
        if not os.path.exists(P.VANILLA_ROM):
            self.skipTest("no ROM on this PC")
        capture = {}
        data, log = bc_run.run(S.rom_bytes(P.VANILLA_ROM), "9859608359", "normal",
                               bc_trace.preset_flags("New Player") + " bingoboingo", say=lambda m: None, capture=capture)
        self.assertTrue(data)
        cards = capture.get("bingo") or []
        self.assertEqual(len(cards), 1)
        self.assertIn("Beyond Chaos Bingo Card", cards[0])
        self.assertEqual([n for n in os.listdir(os.path.abspath(bc_run.HOME)) if n.startswith("bingo.")], [])


class BcPlayerTestInBatch(unittest.TestCase):
    """tools/bc_playertest.py inside a test batch: the batch's own BC test install (bc_testinstall) is restored before
    the player install and put back after it, on a fake game folder (the real game is the test runner's)."""

    def setUp(self):
        import types
        import zipfile
        import bc_testinstall as T
        import bc_playertest as PT
        self.T, self.PT = T, PT
        self.tmp = tempfile.mkdtemp()
        root = self.tmp
        game = types.SimpleNamespace(install=os.path.join(root, "game"), running=lambda: False)
        game.bepinex = os.path.join(game.install, "BepInEx")
        game.plugins_dir = os.path.join(game.bepinex, "plugins")
        game.shelf_dir = os.path.join(game.bepinex, "mod-shelf")
        game.magicite_dir = os.path.join(game.install, "Magicite")
        os.makedirs(os.path.join(game.bepinex, "config"))
        os.makedirs(os.path.join(game.plugins_dir, "WorldsCollide"))          # the mod the batch had active
        build = os.path.join(root, "build")
        for d in (os.path.join(build, "plugin", "baseline"), os.path.join(build, "magicite", T.MOD)):
            os.makedirs(d)
            open(os.path.join(d, "x.txt"), "w").close()
        for f in ("dll", "flags"):
            open(os.path.join(root, f), "w").close()
        self.zip = os.path.join(root, "BeyondChaos-PR-test.zip")
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr("BepInEx/plugins/BeyondChaos/BeyondChaos.PR.dll", b"player dll")
            z.writestr("BepInEx/BeyondChaos/generator/bundle.json", "{}")
        self.saved = (T.game, T.DLL, T.FLAGS, T.BUILD)
        T.game = lambda: game
        T.DLL, T.FLAGS, T.BUILD = os.path.join(root, "dll"), os.path.join(root, "flags"), build
        self.g = game

    def tearDown(self):
        self.T.game, self.T.DLL, self.T.FLAGS, self.T.BUILD = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dev_install_restored_then_put_back(self):
        T, PT, g = self.T, self.PT, self.g
        state = os.path.join(g.bepinex, T.STATE)
        T.install()                                            # the batch's earlier BC steps
        self.assertTrue(os.path.exists(state))
        PT.install(self.zip)                                    # used to stop here: "restore first"
        self.assertTrue(os.path.exists(os.path.join(g.bepinex, T.MOD, "generator", "bundle.json")))
        self.assertFalse(os.path.isdir(os.path.join(g.magicite_dir, T.MOD)))          # a player's: no Magicite folder
        PT.restore()
        self.assertTrue(os.path.exists(state))                  # the batch's install is back for its later steps
        self.assertTrue(os.path.isdir(os.path.join(g.magicite_dir, T.MOD)))
        self.assertFalse(os.path.exists(os.path.join(g.bepinex, T.MOD, "generator")))
        T.restore()
        self.assertTrue(os.path.isdir(os.path.join(g.plugins_dir, "WorldsCollide")))   # as the batch found it

    def test_without_a_dev_install_restore_leaves_none(self):
        T, PT, g = self.T, self.PT, self.g
        PT.install(self.zip)
        PT.restore()
        self.assertFalse(os.path.exists(os.path.join(g.bepinex, T.STATE)))
        self.assertTrue(os.path.isdir(os.path.join(g.plugins_dir, "WorldsCollide")))


class BcRomFree(unittest.TestCase):
    """The ROM-free generator's shipped data (data/bc_base.bin, tools/bc_basedata.py): only what BC's draws and
    our porter need, never the game's graphics, text, music or code (PORTING.md "Beyond Chaos port")."""

    # US 1.0 ranges that must never ship (whole or in part): character sprites, dialogue, the sound program and
    # songs, the opening/ending graphics, battle and map graphics (shapes: the monster tiles' stand-in instead)
    CONTENT = [(0x150000, 0x185000, "character sprites"), (0x0D0000, 0x0EF100, "dialogue"),
               (0x050000, 0x053C5F, "the sound program"), (0x054A35, 0x0A0000, "samples and songs"),
               (0x02686C, 0x02A659, "the opening and ending"), (0x2D1D00, 0x2D5AC0, "portraits")]

    @classmethod
    def setUpClass(cls):
        import bc_basedata
        cls.B = bc_basedata
        if not os.path.exists(bc_basedata.PATH):
            raise unittest.SkipTest("no data/bc_base.bin (tools/bc_basedata.py build)")
        cls.regions = bc_basedata.regions_of()

    def test_no_content_ships(self):
        allowed = set()
        for a, b in self.B.ALLOW:          # the sound program's table pointers: numbers (bc_basedata.ALLOW)
            self.assertLessEqual(b - a, 3, "ALLOW is for pointers and counts, a few bytes each")
            allowed.update(range(a, b))
        for s, data, cat in self.regions:
            for a, b, what in self.CONTENT:
                bad = [x for x in range(max(s, a), min(s + len(data), b)) if x not in allowed]
                self.assertFalse(bad, f"{s:06X}+{len(data)} ({cat}) overlaps {what}")
            self.assertIn(cat, self.B.CATEGORIES)

    def test_code_is_bytes_not_banks(self):
        code = sum(len(d) for _, d, c in self.regions if c == "code")
        self.assertLess(code, 64, "game code beyond the few bytes BC reads to patch")

    def test_shapes_are_marker_pixels_only(self):
        for s, data, cat in self.regions:
            if cat == "shapes":
                self.assertLessEqual(set(data), {0, 0x80}, f"{s:06X}: a monster tile that isn't a stand-in")

    def test_file_matches_the_rom(self):
        import prdata as P
        if not os.path.exists(P.VANILLA_ROM):
            self.skipTest("no vanilla ROM")
        self.assertEqual(self.B.check(), 0)

    def test_load_is_the_roms_size(self):
        self.assertEqual(len(self.B.load()), self.B.ROM_SIZE)


@unittest.skipUnless(os.environ.get("BC_PARITY_TEST") == "1",
                     "BC_PARITY_TEST=1 makes a seed on the ROM and ROM-free and compares them (~3 min)")
class BcRomFreeParity(unittest.TestCase):
    def test_new_player_seed_is_the_same(self):
        import subprocess
        p = subprocess.run([sys.executable, os.path.join(PR, "tools", "bc_parity.py"), "9859608359", "New Player"],
                           cwd=PR, capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0, p.stdout[-3000:] + p.stderr[-1500:])


if __name__ == "__main__":
    unittest.main()
