"""Beyond Chaos's remonsterate for a seed: each monster BC gave a picture from its release's remonsterate/
folder (13,418 PNGs from other games) shows it in battle and in the bestiary, as the SNES draws it.
Run by tools/bc_seed.py on the player's machine after tools/bc_sprites.py; served by the kit's ArtSwap
(plugin/BcPlugin/BcSprites.cs).

BC's choice is BC's (a seed = the exe's): remonsterate runs in a process of its own and hands back, for each
monster in id order, "Display (Original) -> Game/file.png." (or "-> original sprite."), which BC logs; its
log dict keeps that order (the spoiler log sorts the section), and BC's own monster list
(monsterrandomizer.get_monsters, the same objects remonsterate was given) puts the lines on monster ids. Each picture is converted by remonsterate's own prepare_image (crop, 15 colors), with its
transparency rule and the SNES's 15-bit colors, as remonsterate writes it into the ROM.

In the PR a monster is a pre-drawn image (monster.monster_asset_id -> monster_asset -> key
{GROUP}_{ASSET}, cropped to its opaque box, pivot bottom-centre). Each remonsterated monster gets its
own image key, as BNW's new art does (tools/port_sprites.py): monster_asset row 2000+m in its own
group (the group's shadow and bestiary place), key {GROUP}_B{m:03}; ArtSwap registers the key and
serves the picture. The pivot puts the picture where the SNES draws it: the SNES draws a sprite's
tiles from the formation position's top-left, the PR draws the old image's bottom-centre at the
bottom-centre of that monster's SNES box (data/bc_monster_boxes.json: coordinates only).

    python tools/bc_monsters.py boxes      # dev PC: remake data/bc_monster_boxes.json from the ROM
    python tools/bc_monsters.py colors     # dev PC: remake data/bc_monster_colors.json (ROM + game)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pr_art  # noqa: E402  (the kit's: GameArt, ArtWriter, monster image keys)
BOXES = os.path.join(os.path.dirname(HERE), "data", "bc_monster_boxes.json")
MASTER = "master/Assets/GameAssets/Serial/Data/Master"


def boxes():
    with open(BOXES, encoding="utf-8") as f:
        return {int(k): v for k, v in json.load(f)["boxes"].items()}


def build_boxes():
    """Each vanilla SNES monster's opaque box in its sprite's tile grid (x0, y0, x1, y1), dev PC."""
    import prdata as P
    import ff6snes as S
    from snes_sprites import Sprites
    sp = Sprites(S.Rom(P.VANILLA_ROM))
    out = {}
    for i in range(384):
        b = sp.sprite(i).bbox()
        if b:
            out[str(i)] = list(b)
    with open(BOXES, "w", encoding="utf-8") as f:
        json.dump({"_doc": "FF6 SNES monsters 0-383: the opaque box (x0, y0, x1, y1, exclusive) of each sprite in its "
                           "tile grid (tools/bc_monsters.py boxes; tools/snes_sprites.py). The PR's image of a monster is "
                           "this box; a new picture's pivot puts it where the SNES draws it.", "boxes": out}, f, indent=0)
    print(f"{len(out)} boxes -> {BOXES}")


# --- BC's choices -------------------------------------------------------------------------------------

LINE = re.compile(r"^(.*?) \((.*?)\) -> (.*)\.$")


def picks(spoiler):
    """remonsterate's log lines in order: (display, original, path or None)."""
    out, inside = [], False
    for line in spoiler.splitlines():
        if re.match(r"^-\d+- ", line.strip()):      # a section header (the contents list has them too)
            inside = re.match(r"^-\d+- REMONSTERATE", line.strip(), re.I) is not None
            continue
        m = LINE.match(line.rstrip())
        if inside and m:
            path = m.group(3).strip()
            out.append((m.group(1).strip(), m.group(2).strip(), None if path == "original sprite" else path))
    return out


def log_lines():
    """remonsterate's lines as BC logged them, in monster order (its log dict before get_log_string sorts each
    section); None outside BC's process."""
    r = sys.modules.get("randomizer")
    got = getattr(r, "randomizer_log", {}).get("remonsterate") if r else None
    if not got:
        return None
    out = []
    for text in got:
        for line in str(text).splitlines():
            m = LINE.match(line.rstrip())
            if m:
                path = m.group(3).strip()
                out.append((m.group(1).strip(), m.group(2).strip(), None if path == "original sprite" else path))
    return out


def assign_by_name(lines, monsters):
    """The spoiler's lines (sorted by BC's log) on monster ids by name: each (display, original) pair takes the
    next monster with those names in id order (monsters sharing both names may get each other's picture)."""
    ids = {}
    for i, d, o in monsters:
        if d and o:
            ids.setdefault((d.strip(), o.strip()), []).append(i)
    out = {}
    for d, o, path in lines:
        q = ids.get((d, o))
        if not q:
            continue
        i = q.pop(0)
        if path:
            out[i] = path
    return out


def assign(lines, monsters):
    """The log's lines on monster ids: remonsterate logs every monster of its list (id order) whose name
    and display name aren't blank. monsters: [(id, display, original)] in id order. Returns {id: path}."""
    named = [(i, d, o) for i, d, o in monsters if d and o]
    out, k = {}, 0
    for i, d, o in named:
        if k >= len(lines):
            break
        ld, lo, path = lines[k]
        if ld != d.strip() or lo != o.strip():
            raise ValueError(f"remonsterate's line {k} is {ld} ({lo}), monster {i} is {d} ({o})")
        if path:
            out[i] = path
        k += 1
    return out


def bc_monsters():
    """BC's own monster list after its run (the objects remonsterate was given): [(id, display, name)]."""
    import monsterrandomizer
    return [(m.id, m.display_name.strip("_").strip(), m.name.strip("_").strip()) for m in monsterrandomizer.get_monsters()]


# --- the pictures -------------------------------------------------------------------------------------

def picture(path):
    """A remonsterate PNG as the SNES draws it: (w, h, rgba, x0, y0) cropped to its opaque box, x0/y0 its
    place in the sprite's tile grid. remonsterate's prepare_image (BC's code: no random draws), its
    transparency (the commonest border index), the top 8-row strips load_image drops, 15-bit colors."""
    from PIL import Image
    from remonsterate.remonsterate import prepare_image
    from remonsterate.tools.utils import get_transparency
    im = prepare_image(Image.open(path))
    if im.mode != "P":
        im = im.convert("P")
    t = get_transparency(im)
    w, h = im.size
    px = im.tobytes()
    pal = im.getpalette()
    # load_image: blank 8-row strips at the top go (the sprite's grid starts at the first with a pixel)
    top = 0
    while top + 8 < h and all(px[y * w + x] == t for y in range(top, top + 8) for x in range(w)):
        top += 8
    opaque = [(x, y) for y in range(top, h) for x in range(w) if px[y * w + x] != t]
    if not opaque:
        return None
    x0, x1 = min(x for x, _ in opaque), max(x for x, _ in opaque) + 1
    y0, y1 = min(y for _, y in opaque), max(y for _, y in opaque) + 1

    def snes(c):
        c >>= 3
        return (c << 3) | (c >> 2)
    out = bytearray()
    for y in range(y0, y1):
        for x in range(x0, x1):
            v = px[y * w + x]
            out += bytes([snes(pal[3 * v]), snes(pal[3 * v + 1]), snes(pal[3 * v + 2]), 255]) if v != t else b"\0\0\0\0"
    return x1 - x0, y1 - y0, bytes(out), x0, y0 - top


# the kit's (tools/pr_art.py)
pivot, apply_table, game_dir = pr_art.pivot, pr_art.apply_table, pr_art.game_dir
SHEET = pr_art.SHEET
_art = None


def art():
    global _art
    if _art is None:
        _art = pr_art.GameArt()
    return _art


def textures(group):
    return art().textures(group)


def pack(images):
    return pr_art.pack_shelves(images)


# --- the seed ---------------------------------------------------------------------------------------

def build(out_dir, spoiler, rom=None, vanilla=None, home=None, monsters=None, log=print):
    """The seed's monster art into sprites/ (monster sheets, thumbnails, art.json entries and keys) and its
    monster/monster_asset tables: remonsterate's pictures, and (rom + vanilla given) BC's palette and shape
    changes on the PR's own images for the rest. Returns {"monsters": n, "recolors": n, "tables": ...} or
    None when no monster looks different."""
    import bc_run
    import prdata as P
    import port_sprites as PS
    import pr_images
    lines, ordered = log_lines(), True
    if lines is None:
        lines, ordered = picks(spoiler), False       # BC's spoiler log sorts the section: by names
    home = home or bc_run.HOME
    src = os.path.join(home, "remonsterate", "sprites")
    mons = monsters if monsters is not None else (bc_monsters() if lines else [])
    chosen = (assign(lines, mons) if ordered else assign_by_name(lines, mons)) if lines else {}
    bx = boxes()
    vmon, vasset = P.Table("monster"), P.Table("monster_asset")
    found = []                 # (monster, its image's group, its monster_asset row, w, h, rgba, pivot, thumbnail)
    missing = []
    for m, rel in sorted(chosen.items()):
        group, a = pr_art.monster_asset(m, vmon, vasset)
        if a is None:
            continue
        path = os.path.join(src, *rel.replace("\\", "/").split("/"))
        if not os.path.exists(path):
            missing.append(rel)
            continue
        pic = picture(path)
        if pic is None:
            continue
        w, h, rgba, x0, y0 = pic
        found.append((m, group, a, w, h, rgba, pivot(bx.get(m), w, h, x0, y0), None))
    n_pictures, n_recolors = len(found), 0
    if rom is not None and vanilla is not None and os.path.exists(COLORS) and not lines:
        # with remonsterate BC rewrote every graphics entry (its own layout): shapes can't be read, so only
        # its pictures are carried
        rec = recolors(rom, vanilla, skip=set(chosen), log=log)
        found += rec
        n_recolors = len(rec)
    if not found:
        return None
    out = pr_art.ArtWriter(os.path.join(out_dir, "sprites"), standalone_battle=True)
    for m, group, a, w, h, rgba, pv, thumb in found:
        out.monster(m, group, a, w, h, rgba, pivot=pv, thumb=thumb)
    out.save()
    # the tables: each changed monster on its own image (the seed's full monster table, as packed)
    pr_art.write_monster_tables(os.path.join(out_dir, *MASTER.split("/")), out.monster_rows)
    if missing:
        log(f"bc_monsters: {len(missing)} pictures not in {src}: {missing[:5]}")
    groups = len(out.art.get("keys", {}))
    log(f"bc_monsters: {n_pictures} monsters remonsterated ({len(lines)} logged, {len(chosen)} with a picture), "
        f"{n_recolors} recoloured, {groups} groups")
    rows = len(out.monster_rows)
    return {"monsters": n_pictures, "recolors": n_recolors, "tables": {"monster": rows, "monster_asset": rows}}


# --- `c` (with `m`): BC's monster palettes on the PR's own images ------------------------------------
# BC's manage_monster_appearance gives every monster a mutated palette (and non-bosses another monster's
# shape). The PR's monster images are the SNES sprites' boxes redrawn in the same 16 colors, so a palette
# change is a color table: each PR color sits on one SNES palette slot (data/bc_monster_colors.json, learned
# once from the game and the ROM: tools/port_sprites.py's alignment; it holds only the slot of each of an
# image's distinct colors, sorted, paired at run time with the player's own image), and moves by its slot's
# change in Lab
# (port_sprites.color_table's rule). Per seed only BC's data tables are read (graphics entries D2/7000,
# palettes D2/7820): no graphics, so it works ROM-free.
COLORS = os.path.join(os.path.dirname(HERE), "data", "bc_monster_colors.json")
INFO, PAL = 0x127000, 0x127820


def build_colors():
    """Dev PC: for each vanilla SNES monster with PR art, its PR image key and {PR color: SNES palette slot}."""
    import collections
    import math
    import prdata as P
    import ff6snes as S
    import port_sprites as PS
    from snes_sprites import Sprites
    vs = Sprites(S.Rom(P.VANILLA_ROM))
    vmon, vasset = P.Table("monster"), P.Table("monster_asset")
    crops = {i: PS.Crop(vs.sprite(i)) for i in range(384)}
    out, done = {}, {}
    for i in range(384):
        r = vmon.rows.get(i + 1)
        a = vasset.rows.get(int(r["monster_asset_id"])) if r else None
        if a is None or crops[i].empty:
            continue
        key = f"{a['group_name'].upper()}_{a['asset_name'].upper()}"
        if key in done:                       # several monsters on one image: the first one's slots
            out[str(i)] = {"key": key, "group": a["group_name"], "same_as": done[key]}
            continue
        tex = PS.pr_textures(a["group_name"]).get(key)
        if tex is None:
            continue
        w, h, rgba = tex
        van = crops[i]
        dx, dy = PS.align(w, h, rgba, van)
        used = sorted(set(van.idx) - {0})
        per = collections.defaultdict(collections.Counter)
        for y in range(h):
            for x in range(w):
                k = 4 * (y * w + x)
                if rgba[k + 3] == 0:
                    continue
                c = tuple(rgba[k:k + 3])
                best = None
                for rr in (1, 2, 3):
                    for yy in range(y + dy - rr, y + dy + rr + 1):
                        for xx in range(x + dx - rr, x + dx + rr + 1):
                            v = van.at(xx, yy)
                            if v:
                                cost = PS.dE(c, van.pal[v]) + 6 * math.hypot(xx - x - dx, yy - y - dy)
                                if best is None or cost < best[0]:
                                    best = (cost, v)
                    if best:
                        break
                per[c][best[1] if best else min(used, key=lambda u: PS.dE(c, van.pal[u]))] += 1
        out[str(i)] = {"key": key, "group": a["group_name"], "n": len(per),
                       "slots": [per[c].most_common(1)[0][0] for c in sorted(per)]}
        done[key] = str(i)
    with open(COLORS, "w", encoding="utf-8") as f:
        json.dump({"_doc": "FF6 SNES monsters 0-383 with PR art: the PR image key (group mn_ff6_NNN) and the SNES "
                           "palette slot of each of that image's distinct colors, sorted (n: how many), learned with "
                           "port_sprites' alignment (tools/bc_monsters.py colors). No colors: they're paired with the "
                           "player's own image at run time. same_as: a monster on another one's image.", "monsters": out},
                  f, indent=0)
    print(f"{len(out)} monsters -> {COLORS}")


def entry(rom, i):
    """A monster's SNES graphics entry: (shape: pointer/3bpp/big/stencil, palette index, 3bpp)."""
    e = rom[INFO + 5 * i:INFO + 5 * i + 5]
    ptr = e[0] | e[1] << 8
    return (ptr, e[2] & 0x80, e[4]), (e[2] & 3) << 8 | e[3], bool(ptr & 0x8000)


def snes_palette(rom, index, bpp3):
    import snes_charsprites as C
    return C.palette(rom[PAL + 16 * index:PAL + 16 * index + (16 if bpp3 else 32)])


def recolors(rom, vanilla, skip=(), log=print):
    """Monsters whose palette or shape BC changed (not remonsterated ones, `skip`): their PR image recoloured,
    for an image key of their own: [(monster, group, monster_asset row, w, h, rgba, pivot, thumbnail or False)].
    vanilla: the ROM's (or the ROM-free base's) bytes for the same tables."""
    import prdata as P
    import port_sprites as PS
    with open(COLORS, encoding="utf-8") as f:
        mc = json.load(f)["monsters"]
    shapes = {}
    for i in range(384):
        shp, _, _ = entry(vanilla, i)
        shapes.setdefault(shp, i)
    vmon, vasset = P.Table("monster"), P.Table("monster_asset")
    found = []
    for m in range(384):
        if m in skip or m + 1 not in vmon.rows:
            continue
        shp, pal_i, bpp3 = entry(rom, m)
        vshp, vpal_i, vbpp3 = entry(vanilla, m)
        k = m if shp == vshp else shapes.get(shp)
        if k is None:
            continue                      # a shape no vanilla monster has (remonsterate's): not ours
        src = mc.get(str(k))
        if src is None:
            continue
        known = mc[src["same_as"]] if "same_as" in src else src
        _, kpal_i, kbpp3 = entry(vanilla, k)
        old, new = snes_palette(vanilla, kpal_i, kbpp3), snes_palette(rom, pal_i, bpp3)
        if k == m and old == new:
            continue
        tex = textures(src["group"]).get(src["key"])
        if tex is None:
            continue
        w, h, rgba = tex
        colors = sorted({tuple(rgba[q:q + 3]) for q in range(0, len(rgba), 4) if rgba[q + 3]})
        if len(colors) != known["n"]:
            log(f"bc_monsters: {src['key']} has {len(colors)} colors, not {known['n']}: monster {m} not recoloured")
            continue
        table = {}
        for rgb, v in zip(colors, known["slots"]):
            if v >= len(old) or v >= len(new) or old[v] == new[v]:
                continue
            A, B, X = PS.lab(old[v]), PS.lab(new[v]), PS.lab(rgb)
            table[rgb] = PS.from_lab(tuple(X[q] + B[q] - A[q] for q in range(3)))
        if not table and k == m:
            continue
        group, a = pr_art.monster_asset(m, vmon, vasset)
        th = textures(PS.thumb_group(src["key"])).get("Thumbnail")   # none for some (scene bosses)
        found.append((m, group, a, w, h, apply_table(rgba, table), [0.5, 0.0], apply_table(th[2], table) if th else False))
    return found


if __name__ == "__main__":
    if sys.argv[1:] == ["boxes"]:
        build_boxes()
    elif sys.argv[1:] == ["colors"]:
        build_colors()
    else:
        print(__doc__)
