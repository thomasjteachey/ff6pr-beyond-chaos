"""Beyond Chaos's character art for a seed: makeover (its categories, novanilla, frenchvanilla, cloneparty,
partyparty, quikdraw, kupokupo, bravenudeworld, ...), `s` (sprites swapped between characters) and `c`'s
character palettes. Run by tools/bc_seed.py on the player's machine; served in game by plugin/BcPlugin
(BcSprites.cs on the kit's PrKit/Ff6/ArtSwap.cs).

BC works in SNES sprite slots (0-21: the 14 characters, Soldier, Imp, Leo, Banon, Esper Terra, Merchant,
Ghost, Kefka): each slot gets a sheet (a vanilla slot's, `s`, or one of BC's custom sheets, makeover) and
a palette index (0-7), and the palettes themselves get recoloured (`c`). Whatever shows a slot's sheet on
the SNES (the party member, the same character as an NPC in scenes) shows the new art; here, the PR's art
groups of that slot (data/ff6_charsprites.json "slots": battle bc_, field mo_, portrait fa_).

BC's choices are BC's (a seed = the exe's seed): prepare() wraps appearance.get_sprite_swaps (its custom
sheet per slot) and manage_palettes (the slot shuffle `change_to`) and records what they return; nothing
is drawn by us; BC's portrait loop (no draws) is replayed from get_free_portrait_ids' inputs and result.
Palette indexes and palettes are read from BC's output (data, ROM-free too); graphics never are.

Per changed slot the seed folder gets one PNG per PR group (all its frames, tools/snes_charsprites.py
pack) and art.json entries the plugin serves (ArtSwap's format):
  sprites/<group>.png, sprites/art.json {"sprites": {address: {png, rect, pivot}}, "atlases": {name: {frame: ...}}}
A custom sheet is converted 1:1 (the PR's art is SNES-sized); a vanilla slot's art is the PR's own
(read from the player's game, recoloured to BC's palette). BC's custom sheets come from BC's release
(custom/sprites, the folder bc_run.HOME holds: one setting, wherever it lives).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import snes_charsprites as C  # noqa: E402
import pr_art  # noqa: E402

OG = {"ogterra": 0, "oglocke": 1, "ogcyan": 2, "ogshadow": 3, "ogedgar": 4, "ogsabin": 5, "ogceles": 6,
      "ogstrago": 7, "ogrelm": 8, "ogsetzer": 9, "ogmog": 10, "oggau": 11, "oggogo": 12, "ogumaro": 13,
      "ogtrooper": 14, "ogimp": 15, "ogleo": 16, "ogbanon": 17, "ogesperterra": 18, "ogmerchant": 19,
      "ogghost": 20, "ogkefka": 21}


# --- capturing BC's choices (in BC's process, before randomize) ---------------------------------

def prepare(capture):
    """Wrap BC's appearance choosers (no draws of ours) so `capture["sprites"]` records them."""
    import appearance
    rec = capture.setdefault("sprites", {})
    swaps, palettes = appearance.get_sprite_swaps, appearance.manage_palettes

    def get_sprite_swaps(*a, **k):
        swap_to = swaps(*a, **k)
        rec["swap_to"] = {int(c): {"file": s.file, "name": s.name, "portrait": s.portrait_filename,
                                   "portrait_pal": getattr(s, "portrait_palette_filename", None),
                                   "fallback_portrait": s.fallback_portrait_id}
                          for c, s in (swap_to or {}).items()}
        return swap_to

    def manage_palettes(outfile, change_to, char_ids):
        rec["change_to"] = {int(c): int(v) for c, v in change_to.items()}
        rec["char_ids"] = [int(c) for c in char_ids]
        import options      # BC's new palette mode re-indexes Cyan's, Mog's and Umaro's sheets (RC*.bin)
        rec["reindexed"] = not options.Options_.is_flag_active("sometimeszombies")
        return palettes(outfile, change_to, char_ids)

    free_ids = appearance.get_free_portrait_ids

    def get_free_portrait_ids(swap_to, change_to, char_ids, char_portraits):
        got = free_ids(swap_to, change_to, char_ids, char_portraits)
        import options
        o = options.Options_
        rec["portraits"] = {
            "char": {int(c): int(v) for c, v in char_portraits.items()},     # portrait offsets as BC read them
            "free": [int(x) for x in got[0]], "merchant": bool(got[1]), "char_ids": [int(c) for c in char_ids],
            "makeover": o.is_flag_active("makeover") and not any(o.is_flag_active(f) for f in (
                "suplexwrecks", "bravenudeworld", "quikdraw", "kupokupo", "halloween")),
            "wild": o.is_flag_active("partyparty")}
        return got

    appearance.get_sprite_swaps = get_sprite_swaps
    appearance.manage_palettes = manage_palettes
    appearance.get_free_portrait_ids = get_free_portrait_ids

    # alasdraco (musicinterface.manage_opera): the singers' sheets BC writes over the opera NPCs' (its own art from
    # custom/opera or custom/sprites: create_sprite's 0x28 tiles + the role's extra pose tiles), as written
    import musicinterface
    insert = musicinterface.byte_insert

    def byte_insert(data, offset, new, *a, **k):
        if offset in OPERA_SHEETS:
            rec.setdefault("opera", {})[offset] = bytes(new)
        return insert(data, offset, new, *a, **k)

    musicinterface.byte_insert = byte_insert


# alasdraco's opera NPCs: BC's sheet offset -> (role, the NPC's SNES palette on the opera maps (vanilla map data),
# the PR's map objects drawn from it (map 20161: 46/388 Draco and his ghost, 47 Maria, 45 the Impresario), and the
# role's extra pose: tiles 0x28-0x2D (Maria's ready, Draco's and Ralse's lying (3x2), the Impresario's angry),
# singing in 0x2E-0x37 (SNES poses 54/55 = the singer's character poses 30/29))
OPERA_SHEETS = {
    0x1705C0: ("Maria", 0, ["mo_ff6_n039_c00"], "ready"),
    0x1713C0: ("Draco", 4, ["mo_ff6_n038_c00", "mo_ff6_n038_c01"], "prone"),
    0x170CC0: ("Ralse", 1, [], "prone"),            # the PR's Ralse (n048_c00) is also every scholar: left as is
    0x176B40: ("Impresario", 4, ["mo_ff6_n037_c00"], "angry"),
}
NPC_POSES = {"ready": {"tiles": list(range(0x28, 0x2E)), "w": 2}, "angry": {"tiles": list(range(0x28, 0x2E)), "w": 2},
             "prone": {"tiles": list(range(0x28, 0x2E)), "w": 3},
             "sing0": {"tiles": [0x2E, 0x2F, 0x30, 0x31, 0x32, 0x33], "w": 2},   # SNES pose 54
             "sing1": {"tiles": [0x34, 0x35, 0x36, 0x37, 0x32, 0x33], "w": 2}}   # SNES pose 55
# PR frame -> the NPC sheet's pose: singing frames on the singing poses, the role's extra pose where the PR has it,
# the walk cycle as the characters' (kit pose map), anything else the PR drew for the opera on the standing pose
OPERA_FRAMES = {"Sing_00": "sing0", "Sing_01": "sing1", "CloseEyesSing_00": "sing0", "CloseEyesSing_01": "sing1",
                "SingWalkL_00": "sing0", "SingWalkL_01": "sing1", "SingWalkL_02": "sing0", "HandUp_00": "extra",
                "HandUp_01": "extra", "Fall_00": "extra"}


def opera(out, rec, vanilla_rom, art, log=print):
    """alasdraco's singers on the PR's opera NPCs (atlas frames of their map objects), drawn from BC's sheets in the
    NPC's own SNES colors. Returns {role: groups}."""
    import pr_atlas
    sheets = rec.get("opera") or {}
    vp = C.vanilla_palettes(vanilla_rom) if vanilla_rom is not None else None
    done = {}
    for off, sheet in sorted(sheets.items()):
        role, pal_i, groups, extra = OPERA_SHEETS[off]
        if not groups:
            continue
        pal = vp[pal_i] if vp else C.palette(C._rom()[0x268000 + 0x20 * pal_i:][:0x20])
        tl = C.tiles(sheet)
        poses = dict(NPC_POSES, extra=NPC_POSES[extra])
        kit = C.data()["poses"]
        for grp in groups:
            path = art.bundle(grp)
            names = sorted(pr_atlas.sprites(path)) if path else []
            frames = {}
            for n in names:
                key = OPERA_FRAMES.get(n)
                if key is None:
                    spec = C.spec_for(n)
                    if max(kit[str(spec["pose"])]["tiles"]) >= 0x28:    # a character-only pose: stand
                        spec = C.spec_for("Default_00")
                    px = C.frame(tl, spec, kit)
                else:
                    px = C.frame(tl, {"pose": key}, poses)
                frames[n] = C.rgba(px, pal)
            if frames:
                png, rects = C.pack(frames)
                fn = grp + ".png"
                out.png(fn, png)
                out.art["atlases"][grp.upper()] = {n: {"png": fn, "rect": r, "pivot": [0.5, 0]} for n, r in rects.items()}
                done.setdefault(role, []).append(grp)
    if sheets:
        log(f"bc_sprites: alasdraco's opera: {done or 'no PR art found'}")
    return done


# --- reading BC's output ------------------------------------------------------------------------

def out_palette(rom, index):
    """The 16 colors of SNES character palette `index` in BC's output (6: Esper Terra's, which BC keeps
    at palette 8 of the field set and copies to the battle set's 6)."""
    at = 0x268000 + (8 if index == 6 else index) * 0x20
    return C.palette(rom[at:at + 0x20])


def slot_palette_index(rom, slot):
    return rom[0x2CE2B + slot]


def portraits(rec, swap_to, change_to, sprites_dir):
    """What portrait each slot ends with, from BC's own choices (manage_character_appearance's portrait loop
    replayed: no draws in it): {slot: ("custom", portrait file, palette file) | ("vanilla", SNES portrait id)}.
    Never BC's output's graphics: ROM-free, only what BC wrote from custom/ would be there."""
    pr = rec.get("portraits")
    if not pr:
        return {}
    cp = {int(c): int(v) for c, v in pr["char"].items()}
    free = list(pr["free"])
    makeover, wild, merchant = pr["makeover"], pr["wild"], pr["merchant"]
    written, final = {}, {}
    for c in pr["char_ids"]:
        new = change_to.get(c, c)
        portrait = cp[new] // C.PORTRAIT_SIZE
        sw = swap_to.get(c)
        if c == 0x13 and makeover and not merchant:
            portrait = cp[change_to.get(0xE, 0xE)] // C.PORTRAIT_SIZE
        elif cp[c] == 0 and c != 0:
            portrait = cp[0xE] // C.PORTRAIT_SIZE
        elif makeover and sw:
            fb = int(sw.get("fallback_portrait", 0xE))
            if fb < 0 or fb > 18:
                fb = 0xE
            portrait, content, fallback = fb, ("vanilla", fb), True
            if sw.get("portrait") and sw.get("portrait_pal"):
                pf, pp = os.path.join(sprites_dir, sw["portrait"]), os.path.join(sprites_dir, sw["portrait_pal"])
                if os.path.exists(pf) and os.path.exists(pp):
                    fallback, content = False, ("custom", pf, pp)
            if not fallback or fb in free:
                pid = free.pop(0)
                written[pid] = content
                portrait = pid
        elif cp[new] == 0 and wild and new != 0:
            portrait = cp[0xE] // C.PORTRAIT_SIZE
        final[c] = portrait
    return {c: written.get(p, ("vanilla", p)) for c, p in final.items()}


# --- the game's own art: the kit's (tools/pr_art.py) ---------------------------------------------------
GameArt = pr_art.GameArt
game_dir = pr_art.game_dir


# --- the seed's art ---------------------------------------------------------------------------------

def plan(capture, rom):
    """Per SNES slot BC changed: {"art": ("custom", file) | ("vanilla", slot), "palette": index,
    "face": ("custom", file, pal file) | ("vanilla", portrait id) | None}."""
    rec = capture.get("sprites") or {}
    change_to = {int(k): v for k, v in (rec.get("change_to") or {}).items()}
    swap_to = {int(k): v for k, v in (rec.get("swap_to") or {}).items()}
    slots = C.data()["slots"]
    out = {}
    for s in range(22):
        if str(s) not in slots:
            continue
        art = ("vanilla", change_to.get(s, s))
        sw = swap_to.get(s)
        if sw:
            stem = os.path.splitext(sw["file"])[0].lower()
            art = ("vanilla", OG[stem]) if stem in OG else ("custom", sw["file"])
        out[s] = {"art": art, "palette": slot_palette_index(rom, s), "swap": sw}
    return out


def build(out_dir, capture, rom, vanilla_rom=None, home=None, art=None, log=print):
    """Write sprites/*.png + sprites/art.json into the seed folder for every slot whose look changed.
    Returns a summary {slot name: what it looks like} (for bc_seed.json / the guide)."""
    import bc_run
    home = home or bc_run.HOME
    sprites_dir = os.path.join(home, "custom", "sprites")
    d = C.data()
    vpal = C.vanilla_palettes(vanilla_rom if vanilla_rom is not None else C._rom())
    art = art or GameArt()
    out = pr_art.ArtWriter(os.path.join(out_dir, "sprites"))
    summary = {}
    rec = capture.get("sprites") or {}
    rc = bool(rec.get("reindexed"))
    faces = portraits(rec, {int(k): v for k, v in (rec.get("swap_to") or {}).items()},
                      {int(k): v for k, v in (rec.get("change_to") or {}).items()}, sprites_dir)
    for s, p in plan(capture, rom).items():
        slot = d["slots"][str(s)]
        kind, what = p["art"]
        pal = out_palette(rom, p["palette"])
        groups = [slot["battle"]] + slot.get("also", [])
        changed = False
        for grp in groups:
            names = d["groups"].get(grp)
            if not names:
                continue
            gpal = pal
            if grp != slot["battle"]:          # a palette variant (green soldiers): its own palette, recoloured
                gpal = out_palette(rom, d["palettes"][grp])
            if kind == "custom":
                sheet = open(os.path.join(sprites_dir, what), "rb").read()
                frames = C.group_frames(sheet, gpal, names)
                empty = _fill_empty(frames, grp, art, vpal[d["palettes"].get(grp, slot["palette"])], gpal, rc,
                                    art.maps(grp))
                if empty:
                    log(f"bc_sprites: {what} has no {', '.join(empty)} (empty on the SNES too): filled in")
            else:
                src = d["slots"].get(str(what))
                if src is None:
                    continue
                src_grp = grp if what == s else src["battle"]
                old = vpal[d["palettes"].get(src_grp, src["palette"])]   # the art's own SNES colors
                if what == s and old == gpal:
                    continue                   # this group looks as it always did
                have = art.frames(src_grp)
                frames = {}
                for n in names:
                    px = have.get(n) or have.get(_closest(n, have))
                    frames[n] = C.recolor(px, art.maps(src_grp), old, gpal, reindexed=rc)
            out.character(grp, frames, field=slot.get("field") if grp == slot["battle"] else None)
            changed = True
        # the portrait: BC's pointer for the slot; its bytes tell a custom portrait from a vanilla one
        face = slot.get("face")
        content = faces.get(s)
        if face and content:
            img = None
            if content[0] == "custom":                  # BC's portrait from custom/: the file itself
                with open(content[1], "rb") as f1, open(content[2], "rb") as f2:
                    img = C.portrait(f1.read(C.PORTRAIT_SIZE), f2.read(0x20))
            else:
                pid = content[1]
                # a slot still on its own SNES portrait keeps the PR's (Esper Terra uses Terra's on the SNES);
                # a slot with no SNES portrait of its own (BC points it at the Soldier's) keeps the PR's too
                own = d["portraits"].get(str(slot.get("portrait"))) == face
                if own and pid != slot.get("portrait") and d["portraits"].get(str(pid)) not in (None, face):
                    img = art.face(d["portraits"][str(pid)])     # another character's portrait: the PR's own
            if img is not None:
                out.face(face, img)
                changed = True
        if changed:
            summary[slot["name"]] = (p["swap"]["name"] if p.get("swap") else d["slots"][str(what)]["name"]
                                     if kind == "vanilla" and str(what) in d["slots"] else str(what))
    for role in opera(out, rec, vanilla_rom, art, log):
        summary["opera " + role] = "alasdraco"
    out.save()
    log(f"bc_sprites: {len(summary)} slots changed, {len(out.art['sprites'])} sprites, "
        f"{sum(len(v) for v in out.art['atlases'].values())} atlas frames: {summary}")
    return summary


def _fill_empty(frames, grp, art, old, new, rc, maps):
    """A custom sheet's pose with (almost) nothing in it (Aerith's sheet has no tent) gets a frame anyway:
    the tent the slot's own PR art has, in the slot's colors; any other pose the sheet's standing frame
    facing the same way. Returns the names filled."""
    filled = []
    for n, px in frames.items():
        if sum(1 for a in px[3::4] if a) >= 8:
            continue
        if n.startswith("Tent"):
            own = art.frames(grp).get(n)
            if own:
                frames[n] = C.recolor(own, maps, old, new, reindexed=rc)
                filled.append(n)
                continue
        base = frames.get("Idle_00") or frames.get("Default_01")
        if base is None or base is px:
            continue
        frames[n] = C.mirror(base) if C.spec_for(n).get("mirror") else base
        filled.append(n)
    return filled


def _closest(name, have):
    """A frame the source group lacks (Imp has no Float_00): the pose-map's nearest one it has."""
    spec = C.spec_for(name)
    for n in have:
        if C.spec_for(n).get("pose") == spec.get("pose") and C.spec_for(n).get("mirror") == spec.get("mirror"):
            return n
    return "Idle_00" if "Idle_00" in have else next(iter(have))
