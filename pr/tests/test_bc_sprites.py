"""Offline tests for Beyond Chaos's art (tools/bc_sprites.py, bc_monsters.py, bc_palettes.py) and the kit's
SNES character sprite conversion (tools/snes_charsprites.py, data/ff6_charsprites.json).

  pr/.venv/Scripts/python -m unittest discover -s pr/tests -p "test_bc_sprites.py" -v

Without the game or the vanilla ROM (the player's machine, CI) the checks that need them are skipped.
  * the pose map: every frame name of every PR group has an SNES pose; the SNES Terra converted through it
    sits where the PR's own Terra frame is (masks agree on most pixels, frame for frame)
  * BC's custom sheets: every one converts to all 57 frames + its portrait; none comes out empty but the
    poses BC's sheets lack (filled in by bc_sprites)
  * recolouring the PR's art: an unchanged palette leaves it byte for byte; a changed one moves its slot
  * remonsterate: its log lines go on monster ids as BC's list has them; a mismatch is an error
  * art.json: what bc_sprites/bc_monsters/bc_palettes write is the schema ArtSwap reads
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PR, "tools"))
import kitpath  # noqa: E402,F401
import snes_charsprites as C  # noqa: E402
import bc_monsters as BM  # noqa: E402


def rom_or_skip():
    import prdata as P
    if not os.path.exists(P.VANILLA_ROM):
        raise unittest.SkipTest("no vanilla ROM (dev PC only)")
    return C._rom()


def game_or_skip():
    try:
        from prkit import games
        g = games.get("ff6").install
    except Exception:  # noqa: BLE001
        g = None
    if not g or not os.path.isdir(os.path.join(g, "FINAL FANTASY VI_Data")):
        raise unittest.SkipTest("FINAL FANTASY VI PR not installed")
    return g


def custom_dir():
    import bc_run
    d = os.path.join(bc_run.HOME, "custom", "sprites")
    if not os.path.isdir(d):
        raise unittest.SkipTest(f"no Beyond Chaos custom/sprites at {d}")
    return d


class PoseMap(unittest.TestCase):
    def test_every_frame_has_a_pose(self):
        d = C.data()
        for g, names in d["groups"].items():
            for n in names:
                spec = C.spec_for(n)
                self.assertIn(str(spec["pose"]), d["poses"], f"{g} {n}")

    def test_snes_terra_sits_on_the_pr_terra(self):
        rom = rom_or_skip()
        game = game_or_skip()
        import pr_images
        tex = pr_images.textures(pr_images.bundle_for(game, "bc_ff6_p001"))
        tl = C.tiles(C.rom_sheet(rom, 0))
        bad = []
        for n in C.frame_names("bc_ff6_p001"):
            if n not in tex:
                continue
            idx = C.frame(tl, C.spec_for(n))
            px = tex[n][2]
            both = sum(1 for y in range(32) for x in range(32) if idx[y][x] and px[(y * 32 + x) * 4 + 3])
            either = sum(1 for y in range(32) for x in range(32) if idx[y][x] or px[(y * 32 + x) * 4 + 3])
            if either and both / either < 0.6:
                bad.append(f"{n} {both / either:.2f}")
        self.assertEqual(bad, [], "SNES pose and PR frame disagree")


class CustomSheets(unittest.TestCase):
    def test_all_custom_sheets_convert(self):
        d = custom_dir()
        names = C.frame_names("bc_ff6_p001")
        lacking = {}
        n = 0
        listed = [line.split(",")[0].strip() for line in open(os.path.join(os.path.dirname(d), "spritereplacements.txt"),
                                                               encoding="utf-8") if line.strip()]
        for fn in listed:
            with open(os.path.join(d, fn), "rb") as f:
                sheet = f.read()
            self.assertGreaterEqual(len(sheet), 0x1560, fn)
            frames = C.group_frames(sheet, [(8 * k, 8 * k, 8 * k) for k in range(16)], names)
            self.assertEqual(set(frames), set(names))
            empty = [k for k, px in frames.items() if sum(1 for a in px[3::4] if a) < 8]
            if empty:
                lacking[fn] = empty
            n += 1
            p = os.path.join(d, fn[:-4] + "-p.bin")
            if os.path.exists(p):
                face = C.portrait(open(p, "rb").read(), open(p[:-4] + ".pal", "rb").read())
                self.assertEqual(len(face), 40 * 40 * 4)
        self.assertGreater(n, 600)
        # what BC's sheets lack (bc_sprites fills it in): mostly the tent; never the walking or battle stances
        core = {"Default_00", "Default_01", "Default_02", "WalkB_00", "WalkL_01", "Idle_00", "Ready_00", "Win_00"}
        self.assertEqual({fn: v for fn, v in lacking.items() if core & set(v)}, {})


class Recolor(unittest.TestCase):
    def test_slot_lists_match_this_game(self):
        """The data's slot lists pair with this PC's game: every group's color count agrees (else recolor
        falls back to the nearest vanilla color)."""
        game = game_or_skip()
        import bc_sprites
        art = bc_sprites.GameArt(game)
        for g in C.data()["color_slots"]:
            self.assertTrue(art.maps(g).matched, g)

    def test_data_holds_no_colors(self):
        import re
        with open(C.DATA, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("snes_palettes", text)
        self.assertEqual(re.findall(r'"[0-9a-f]{6}"', text), [], "a color value in the kit data")
        with open(BM.COLORS, encoding="utf-8") as f:
            self.assertEqual(re.findall(r'"[0-9a-f]{6}"', f.read()), [])

    def test_unchanged_palette_is_lossless(self):
        game = game_or_skip()
        rom = rom_or_skip()
        import bc_sprites
        art = bc_sprites.GameArt(game)
        pal = C.vanilla_palettes(rom)[1]
        for n, px in list(art.frames("bc_ff6_p002").items())[:10]:
            self.assertEqual(C.recolor(px, art.maps("bc_ff6_p002"), pal, pal), px, n)

    def test_changed_slot_moves(self):
        game = game_or_skip()
        rom = rom_or_skip()
        import bc_sprites
        art = bc_sprites.GameArt(game)
        px = art.frames("bc_ff6_p001")["Default_01"]
        old = C.vanilla_palettes(rom)[2]
        new = list(old)
        new[4] = (255, 0, 0)          # Terra's hair slot to red
        out = C.recolor(px, art.maps("bc_ff6_p001"), old, new)
        self.assertNotEqual(out, px)
        self.assertEqual(out[3::4], px[3::4], "the shape (alpha) stays")

    def test_shift_keeps_lightness_order(self):
        centre = C.lab((100, 100, 100))
        dark, light = C.shift((60, 60, 60), centre, (200, 0, 0)), C.shift((160, 160, 160), centre, (200, 0, 0))
        self.assertLess(sum(dark), sum(light))


class Remonsterate(unittest.TestCase):
    SPOILER = ("-01- Characters\n-17- Remonsterate\n\n-17- REMONSTERATE\n------\n"
               "Guard      (Guard     ) -> FF3\\FF3-Titan.png.\n"
               "Leafer     (Leafer    ) -> original sprite.\n"
               "Dark Wind  (Dark Wind ) -> Saga\\Demon - Werebat.png.\n\n-18- SHOPS\nx (y) -> z.png.\n")

    def test_lines_go_on_ids(self):
        lines = BM.picks(self.SPOILER)
        self.assertEqual(len(lines), 3)
        mons = [(0, "Guard", "Guard"), (1, "", ""), (2, "Leafer", "Leafer"), (3, "Dark Wind", "Dark Wind")]
        self.assertEqual(BM.assign(lines, mons), {0: "FF3\\FF3-Titan.png", 3: "Saga\\Demon - Werebat.png"})

    def test_sorted_spoiler_by_name(self):
        lines = sorted(BM.picks(self.SPOILER))      # BC's spoiler log sorts the section
        mons = [(0, "Guard", "Guard"), (1, "", ""), (2, "Leafer", "Leafer"), (3, "Dark Wind", "Dark Wind")]
        self.assertEqual(BM.assign_by_name(lines, mons), {0: "FF3\\FF3-Titan.png", 3: "Saga\\Demon - Werebat.png"})

    def test_mismatch_is_an_error(self):
        lines = BM.picks(self.SPOILER)
        with self.assertRaises(ValueError):
            BM.assign(lines, [(0, "Guard", "Guard"), (1, "Rhodox", "Rhodox")])

    def test_pivot_puts_it_where_the_snes_draws_it(self):
        # a 16x16 picture at the grid's top left; the old monster's box (8, 8)-(24, 32): its bottom-centre
        # (16, 32) is the anchor, so the picture's pivot is 1.0 across (x 16) and -1.0 up (y 32 is 16 below it)
        self.assertEqual(BM.pivot([8, 8, 24, 32], 16, 16, 0, 0), [1.0, -1.0])

    def test_pack_rects_fit(self):
        imgs = {f"K{i}": (20 + i, 30, bytes(4 * (20 + i) * 30)) for i in range(60)}
        pages = BM.pack(imgs)
        seen = {}
        for png, rects in pages:
            self.assertTrue(png.startswith(b"\x89PNG"))
            seen.update(rects)
        self.assertEqual(set(seen), set(imgs))
        for k, (x, y, w, h) in seen.items():
            self.assertLessEqual(x + w, BM.SHEET)


class ArtJson(unittest.TestCase):
    """A seed's sprites/ as bc_sprites + bc_palettes + bc_monsters write it (BC_SPRITES_SEED=DIR: a seed folder
    made by tools/bc_seed.py): every entry names an existing PNG and a rect inside it; keys' addresses are served."""

    def test_seed_art(self):
        d = os.environ.get("BC_SPRITES_SEED")
        if not d:
            raise unittest.SkipTest("BC_SPRITES_SEED not set")
        from PIL import Image
        art = json.load(open(os.path.join(d, "sprites", "art.json"), encoding="utf-8"))
        sizes = {}
        for addr, e in list(art["sprites"].items()) + [(f"{a}/{f}", e) for a, m in art["atlases"].items() for f, e in m.items()]:
            p = os.path.join(d, "sprites", e["png"])
            self.assertTrue(os.path.exists(p), addr)
            if p not in sizes:
                sizes[p] = Image.open(p).size
            x, y, w, h = e["rect"]
            self.assertLessEqual(x + w, sizes[p][0], addr)
            self.assertLessEqual(y + h, sizes[p][1], addr)
        for g, keys in art.get("keys", {}).items():
            for k, addr in keys.items():
                self.assertIn(addr, art["sprites"], f"{g}/{k}")


class ThemedModes(unittest.TestCase):
    """suplexwrecks / bravenudeworld / quikdraw / halloween are BC's change_to with every slot on one character
    (appearance.manage_character_appearance): plan() draws each slot with that character's PR art."""

    def test_suplexwrecks_plan(self):
        import bc_sprites as B
        ids = list(range(21))
        cap = {"sprites": {"change_to": {c: 5 for c in ids}, "char_ids": ids}}
        p = B.plan(cap, bytes(0x300000))
        self.assertEqual({("vanilla", 5)}, {v["art"] for s, v in p.items() if s in ids})


class Opera(unittest.TestCase):
    """alasdraco's singers (bc_sprites.opera): BC's sheet offsets and the NPC poses as BC lays them out."""

    def test_offsets_are_bcs(self):
        import re
        import bc_sprites as B
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "mods", "beyond-chaos",
                           "src", "BeyondChaos", "musicinterface.py")
        if not os.path.exists(src):
            raise unittest.SkipTest("no BC source")
        text = open(src, encoding="utf-8").read()
        found = {int(m.group(2), 16): m.group(1) for m in re.finditer(r'"(\w+)": \((0x[0-9A-Fa-f]+), pose\[', text)}
        self.assertEqual({o: r for o, (r, _, _, _) in B.OPERA_SHEETS.items()}, found)

    def test_extra_poses(self):
        import bc_sprites as B
        sheet = bytes(range(256)) * (0x38 * 32 // 256)      # 0x38 distinct-ish tiles, as create_sprite writes them
        tl = C.tiles(sheet)
        for k, p in B.NPC_POSES.items():
            self.assertEqual(6, len(p["tiles"]), k)
            self.assertLess(max(p["tiles"]), len(tl), k)
            px = C.frame(tl, {"pose": k}, B.NPC_POSES)
            self.assertEqual(C.FRAME, len(px))

    def test_no_pr_art_writes_nothing(self):
        import bc_sprites as B

        class NoArt:
            def bundle(self, g):
                return None
        out = tempfile.mkdtemp()
        try:
            import pr_art
            w = pr_art.ArtWriter(out)
            self.assertEqual({}, B.opera(w, {"opera": {0x1705C0: bytes(0x700)}}, None, NoArt(), log=lambda m: None))
            self.assertEqual({}, w.art["atlases"])
        finally:
            shutil.rmtree(out)


if __name__ == "__main__":
    unittest.main()
