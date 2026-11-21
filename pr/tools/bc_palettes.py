"""Beyond Chaos's palette flags for a seed, on the PR's own art. Run by tools/bc_seed.py (after
tools/bc_sprites.py, which does `c`'s character palettes); served by the kit's ArtSwap (BcSprites.cs).

- `n` (random_window): BC recolours the SNES's 8 window palettes (D1/C00 + 0x20 each: black, five border
  shades, two background blues). The PR has one window style, drawn from sprites in its `common` group: the
  silver frame (UI_Common_WindowFrame01, 9-sliced), the blue gradient backgrounds (UI_Common_WindowFrame02,
  04) and the small rounded box (05). Each PR color is given the SNES window-1 slot it is nearest to (Lab),
  then moved to BC's new color for that slot with its shade kept (snes_charsprites.shift, centred on the
  PR's own average shade of the slot). Window 1 is the SNES's default; the PR has no window choice.
- `p` (random_animation_palettes): not ported. BC recolours the SNES's battle animation palettes; the
  PR's spell and weapon effects are its own art (particle effects and textured meshes, not palette
  sprites), so there is nothing they map onto.
- `c` monsters (with `m`): BC's monster palette mutation is not ported yet (the PR's monster images
  would be recoloured as BNW's recolors are, tools/port_sprites.py images mode).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import snes_charsprites as C  # noqa: E402

WINDOW = 0x2D1C00                       # SNES window palettes, 0x20 bytes each (8 colors used)
# the PR's window sprites: name -> (w, h, 9-slice border l, b, r, t); pivot (0.5, 0.5), 100 px per unit
WINDOW_SPRITES = {
    "UI_Common_WindowFrame01": (100, 100, [45, 45, 45, 45]),
    "UI_Common_WindowFrame02": (100, 100, [0, 0, 0, 0]),
    "UI_Common_WindowFrame04": (100, 100, [0, 0, 0, 0]),
    "UI_Common_WindowFrame05": (100, 42, [49, 20, 49, 20]),
}


def window_palette(rom, w=0):
    return C.palette(rom[WINDOW + w * 0x20:WINDOW + w * 0x20 + 16])


def windows(out_dir, rom, vanilla, art=None, log=print):
    """`n`: the PR's window sprites in BC's window-1 colors, into sprites/ (art.json entries). None when the
    seed keeps the vanilla window. vanilla: BC's input (the ROM or the generator's base data: the window
    palettes are a data table there)."""
    import pr_art
    bc_new = new = window_palette(rom)
    old = window_palette(vanilla)
    if new == old:
        return None
    tex = (art or pr_art.GameArt()).textures_named("common", set(WINDOW_SPRITES))
    old_lab = [C.lab(c) for c in old]

    def slot(c):
        L = C.lab(c)
        s = min(range(1, 8), key=lambda s: sum((L[k] - old_lab[s][k]) ** 2 for k in range(3)))
        return 6 if s == 7 else s      # the two background blues are one gradient in the PR: one shade group
    new = list(new)
    new[6] = tuple((a + b) // 2 for a, b in zip(new[6], new[7]))
    slots, acc = {}, {}
    for _, (w, h, px) in tex.items():
        for i in range(0, len(px), 4):
            if px[i + 3]:
                c = tuple(px[i:i + 3])
                if c not in slots:
                    slots[c] = slot(c)
                a = acc.setdefault(slots[c], [0.0, 0.0, 0.0, 0])
                L = C.lab(c)
                a[0] += L[0]; a[1] += L[1]; a[2] += L[2]; a[3] += 1
    centre = {s: (a[0] / a[3], a[1] / a[3], a[2] / a[3]) for s, a in acc.items()}
    moved = {c: C.shift(c, centre[s], new[s]) for c, s in slots.items()}
    writer = pr_art.ArtWriter(os.path.join(out_dir, "sprites"))
    done = []
    for name, (w, h, border) in WINDOW_SPRITES.items():
        if name not in tex:
            continue
        tw, th, px = tex[name]
        out = bytearray(px)
        for i in range(0, len(out), 4):
            if out[i + 3]:
                out[i:i + 3] = bytes(moved[tuple(px[i:i + 3])])
        writer.ui(name, tw, th, bytes(out), border)
        done.append(name)
    writer.save()
    log(f"bc_palettes: windows in BC's colors ({' '.join('%02x%02x%02x' % c for c in bc_new[1:])}): {', '.join(done)}")
    return {"window": ["%02x%02x%02x" % c for c in bc_new], "sprites": done}


def build(out_dir, rom, flags, vanilla=None, log=print):
    """bc_seed.py's step: what `n` changes (and the reasons `p` isn't carried, for the log)."""
    info = {}
    if vanilla is None:
        vanilla = C._rom()
    w = windows(out_dir, rom, vanilla, log=log)
    if w:
        info["windows"] = w
    if "p" in flags.split():
        log("bc_palettes: p (animation palettes) not carried: the PR's effects are its own art, not palette sprites")
    return info
