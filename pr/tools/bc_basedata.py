"""The data the ROM-free Beyond Chaos generator ships instead of the SNES ROM (as tools/wc_basedata.py is
WC's; PORTING.md "Beyond Chaos port", "ROM-free").

BC decides from the ROM's data tables, and a little more (tools/bc_trace.py records each read with the BC
function that made it and every random draw; BC reseeds before each stage). Everything else BC reads it only
copies or rewrites (sprites, portraits, dialogue, the opening and ending, the sound program, game code), and
tools/bc_romfree.py stands in for those. The generator carries what's left, at its ROM offsets, zeros
elsewhere: data/bc_base.bin. tools/bc_parity.py proves a seed made on it = one made on the ROM.

What's carried, by CATEGORY (each region's category is in tools/bc_basedata_regions.json; `show` sums them):
  data      the data tables: characters, commands, spells, items, espers, monsters and their AI, formations,
            packs, zones, chests, shops, the Colosseum, dances, map properties, names; and the few data tables
            that sit inside the code banks (encounter rates, the characters' battle palette numbers, ...)
  maps      the maps' event triggers, NPCs and entrances (BC's makeover recolours NPCs by their sprite and
            palette numbers; its event changes find their places through them)
  palettes  monster, character, map, battle background, world map, window and animation palettes: BC's
            recolouring draws per colour (hue and brightness classes), so a seed needs them to stay the exe's
  events    a few hundred bytes of event code BC checks or walks before it patches (the auction house,
            the dragons, the recruits, the esper scenes ...)
  code      a few bytes of game code BC reads to patch a bit of it
  shapes    the monster sprites remonsterate keeps, reduced to which 8x8 tiles are blank (its draws depend on
            how many different shapes there are, never on the art): a drawn tile is one marker pixel
  (the colour depth kept: 1 for an 8-colour sprite, 15 for a 16-colour one)

  python tools/bc_basedata.py regions TRACE_DIR... [--port PORT_JSON...]   (dev) the regions to ship, from
                                     bc_trace.py records (real ROM) and porter traces (bc_trace.py port),
                                     less the sites in CONTENT -> tools/bc_basedata_regions.json
  python tools/bc_basedata.py build [OUT] [--without CAT,...]   (dev, with the ROM) data/bc_base.bin
  python tools/bc_basedata.py check           (dev) the file holds the ROM's bytes there (shapes: the stand-in)
  python tools/bc_basedata.py show [FILE]     bytes per category and what they hold

At seed time load() gives BC's input: the ROM's 3 MB with the regions filled, zeros elsewhere.
FF6_BC_BASE_REGIONS=FILE.json (dev experiments): load() makes the input from the ROM with those regions.
"""
import json
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401

PATH = os.path.join(ROOT, "data", "bc_base.bin")
REGIONS_FILE = os.path.join(HERE, "bc_basedata_regions.json")
ROM_SIZE = 3 * 2 ** 20
MAGIC = b"FF6BCB2\0"
CATEGORIES = ["data", "maps", "palettes", "events", "code", "shapes"]

# BC functions whose reads are content BC only copies or rewrites (tools/bc_romfree.py's stand-ins), or
# whole-ROM copies: their regions aren't shipped (unless another function needs the same bytes)
CONTENT = {
    "appearance.py:manage_character_appearance": "character sprites and portraits (makeover copies them)",
    "music/mfvitools/insertmfvi.py:insertmfvi": "the sound program and its tables (johnnydmad replaces them)",
    "decompress.py:decompress_at_location": "the opening's compressed graphics (stand-in: bc_romfree)",
    "randomizer.py:relocate_ending_cinematic_data": "the ending's graphics data (moved)",
    "dialoguemanager.py:read_dialogue": "dialogue (BC rewrites lines by number)",
    "dialoguemanager.py:read_location_names": "location names (BC rewrites them; the PR has its own)",
    "musicinterface.py:randomize_music": "whole-ROM copy",
    "musicinterface.py:manage_opera": "whole-ROM copy",
    "randomizer.py:validate_rom_expansion": "bank 00 mirrored to 40",
    "randomizer.py:rewrite_checksum": "the checksum",
}
# game code BC's (randomtools') and remonsterate's patches check before they replace it (not enforced
# ROM-free: bc_romfree.patch_validation / patch_remonsterate)
VALIDATION = ("patches.py:", "remonsterate/remonsterate.py:begin_remonsterate")
CODE_BANKS = 0x40000

# data tables other BC tools read from BC's output where BC may leave the ROM's (their own traces aren't in
# the BC traces): shipped whatever the traces say
EXTRA = [(0x02BF3B, 0x02BF43), (0x036F00, 0x036F47),
         # our post-steps (tools/bc_trace.py port, 2026-11-20): encounter tables and roll (port_encounter_rates),
         # an equipment table in C2 (bc_items), what bc_codes checks to tell whether BC patched a code
         (0x00C29F, 0x00C2DF), (0x00C48C, 0x00C494), (0x025452, 0x02545C), (0x017D84, 0x017D8A),
         (0x00A183, 0x00A188), (0x2EAF64, 0x2EAF6C),
         # (Advanced preset, 2026-11-20) bc_codes' checks (magicnumbers, mementomori, umaro_risk), bc_data's dance
         # names, the chest table's and AI's ends as the porter walks them, the entrance tables' bounds, the Zozo
         # clock's answer in its event code (bc_events)
         (0x0263A8, 0x0263A9), (0x020E9A, 0x020E9B), (0x021618, 0x021619), (0x04B8E4, 0x04B9D1),
         (0x26FF9D, 0x26FFFD), (0x2D8BCA, 0x2D8CE2), (0x0FFFBE, 0x0FFFFE), (0x1FBE40, 0x1FBE42),
         (0x2DF7C0, 0x2DF7C2), (0x0A96CF, 0x0A970B),
         # bc-sprites (2026-11-20): every monster graphics entry and palette, character palettes 0-8 (its recolours
         # read BC's output of them; BC reads them from its input)
         (0x127000, 0x12A820), (0x268000, 0x268120)]

# allowed inside NEVER: numbers, not the game's content. The sound program's 3-byte pointers to its song, instrument,
# sample, loop, pitch and ADSR tables (and their copies) and its song count: johnnydmad relocates those tables by them,
# and bc_music reads BC's output through them (with zeros they'd all land at offset 0). The program itself isn't
# shipped (bc_romfree.patch_music stands in for its 16-byte check).
ALLOW = [(0x0501E3, 0x0501E6), (0x050222, 0x050225), (0x050228, 0x05022B), (0x05022E, 0x050231),
         (0x05041C, 0x05041F), (0x05049C, 0x05049F), (0x0504DE, 0x0504E1),
         (0x050539, 0x05053C), (0x05053F, 0x050542), (0x050545, 0x050548), (0x053C5E, 0x053C5F)]

# never shipped, whoever reads them (a tool reading these must change: the game's graphics, text and music):
# character sprites, portraits, dialogue (pointers and text), the sound program and its songs, the opening/ending
NEVER = [(0x150000, 0x185000), (0x2D1D00, 0x2D5AC0), (0x0CE600, 0x0EF100), (0x050000, 0x053C5F),
         (0x054A35, 0x0A0000), (0x02686C, 0x02A659)]

# (start, end, category, what it is); first match; unlisted regions are "data"
RULES = [
    (0x00C24B, 0x00C259, "data", "encounter rates (in C0)"),
    (0x00C3E4, 0x00C3F2, "data", "encounter rates, WoR (in C0)"),
    (0x00C29F, 0x00C2DF, "data", "encounter rate tables (in C0; port_encounter_rates)"),
    (0x00C48C, 0x00C494, "code", "the encounter roll (in C0; port_encounter_rates)"),
    (0x00A183, 0x00A188, "code", "the natural magic learner check (in C0; bc_codes)"),
    (0x017D84, 0x017D8A, "code", "code bc_codes checks for BC's patch (in C1)"),
    (0x025452, 0x02545C, "data", "equipment table (in C2; bc_items)"),
    (0x021DD8, 0x021DEE, "data", "AI command table (in C2)"),
    (0x02CE2B, 0x02CE41, "data", "characters' battle palette numbers (in C2)"),
    (0x02BF3B, 0x02BF43, "data", "battle song slots (in C2; bc_music)"),
    (0x02CFD4, 0x02D004, "palettes", "Esper Terra's palette (in C2)"),
    (0x02D01A, 0x02D0F4, "data", "formation moulds (in C2)"),
    (0x036F00, 0x036F47, "data", "portrait pointers (in C3; bc_sprites)"),
    (0x000000, CODE_BANKS, "code", "game code (C0-C3)"),
    (0x040000, 0x046AC0, "maps", "map event triggers, NPCs (C4)"),
    (0x04B8E4, 0x04B9D1, "data", "free space (0xFF) BC's mementomori stubs fill; bc_codes reads them"),
    (0x050000, 0x053C5F, "data", "the sound program's table pointers and song count (ALLOW; bc_music)"),
    (0x046AC0, 0x047AC0, "data", "spells"), (0x047AC0, 0x047F40, "data", "shops"),
    (0x047F40, 0x048000, "data", "metamorph sets"),
    (0x0A0000, 0x0CE600, "events", "event code"),
    (0x0F0000, 0x0F3000, "data", "monster stats"), (0x0F3000, 0x0F3600, "data", "monster items"),
    (0x0F3600, 0x0F4800, "data", "monster specials, sketches, controls, rages"),
    (0x0F4800, 0x0F5900, "data", "packs, zones"), (0x0F5900, 0x0F8400, "data", "formations"),
    (0x0F8400, 0x0FC050, "data", "monster AI"), (0x0FC050, 0x100000, "data", "monster names, misc tables"),
    (0x11F000, 0x120000, "events", "entrance event code"),
    (0x126000, 0x127000, "palettes", "battle animation palettes"),
    (0x127000, 0x127820, "data", "monster graphics info"),
    (0x127820, 0x12A820, "palettes", "monster palettes"),
    (0x12A820, 0x12B300, "data", "monster sprite templates (stencils)"),
    (0x12B300, 0x12C000, "data", "item names"),
    (0x12ED00, 0x12F000, "palettes", "world map palettes"),
    (0x185000, 0x186E00, "data", "items"), (0x186E00, 0x187000, "data", "espers"),
    (0x1FB400, 0x1FB600, "data", "formation AP"), (0x1FB600, 0x1FBB00, "data", "Colosseum"),
    (0x1FBB00, 0x1FDA00, "maps", "short entrances"),
    (0x268000, 0x268400, "palettes", "character palettes"),
    (0x26F000, 0x270000, "data", "names, natural magic"),
    (0x270000, 0x280000, "palettes", "battle background palettes"),
    (0x297000, 0x2CE3C0, "shapes", "monster sprites remonsterate keeps (stand-in: blank or not, per tile)"),
    (0x2CE3C0, 0x2CEC00, "data", "spell and item animation data"),
    (0x2D1C00, 0x2D1D00, "palettes", "window palettes"),
    (0x2D7CA0, 0x2D8634, "data", "characters, chest pointers"),
    (0x2D8634, 0x2D8F00, "data", "chests"),
    (0x2D8F00, 0x2DC480, "data", "map properties"),
    (0x2DC480, 0x2DF480, "palettes", "map palettes"),
    (0x2DF480, 0x2DFCB0, "maps", "long entrances"),
    (0x2EAF64, 0x2EAF6C, "code", "code bc_codes checks for BC's mpparty patch"),
]


def classify(addr):
    for s, e, cat, what in RULES:
        if s <= addr < e:
            return cat, what
    return "data", ""


def label(addr):
    return classify(addr)[1]


def load_regions(path=REGIONS_FILE):
    """[(start, end, category)]"""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    out = []
    for r in doc["regions"]:
        a, b = int(r[0], 16), int(r[1], 16)
        out.append((a, b, r[2] if len(r) > 2 else classify(a)[0]))
    return out


def vanilla_rom():
    import prdata as P
    with open(P.VANILLA_ROM, "rb") as f:
        rom = f.read()
    if len(rom) % 0x8000 == 0x200:
        rom = rom[0x200:]
    return rom


def shapes(rom):
    """The ROM's monster sprite tiles reduced to their shapes: a blank tile stays zeros, a drawn one becomes
    one marker pixel (index 1 in an 8-colour sprite, 15 in a 16-colour one), per monster (its graphics
    info: 0x127000, 5 bytes each; its template: 8 bytes (8x8) or 32 bytes (16x16) at 0x12A824 / 0x12AC24)."""
    out = bytearray(rom[:ROM_SIZE])
    done = set()
    for i in range(416):
        e = rom[0x127000 + 5 * i:0x127000 + 5 * i + 5]
        msp = e[0] | (e[1] << 8)
        eight, big, stencil = bool(msp & 0x8000), bool(e[2] & 0x80), e[4]
        sten = rom[0x12AC24 + 32 * stencil:0x12AC24 + 32 * stencil + 32] if big else \
            rom[0x12A824 + 8 * stencil:0x12A824 + 8 * stencil + 8]
        tiles = sum(bin(v).count("1") for v in sten)
        size = 24 if eight else 32
        at = (msp & 0x7FFF) * 8 + 0x297000
        for t in range(tiles):
            p = at + t * size
            if p in done or p + size > 0x2CE3C0:
                continue
            done.add(p)
            tile = rom[p:p + size]
            new = bytearray(size)
            if any(tile):
                new[0] = 0x80
                if not eight:
                    new[1] = new[16] = new[17] = 0x80
            out[p:p + size] = new
    return bytes(out)


def from_rom(regions, rom=None):
    """BC's ROM-free input made from the ROM: those regions (shapes: the stand-in), zeros elsewhere."""
    rom = rom or vanilla_rom()
    shaped = None
    buf = bytearray(ROM_SIZE)
    for s, e, cat in regions:
        if cat == "shapes":
            shaped = shaped or shapes(rom)
            buf[s:e] = shaped[s:e]
        else:
            buf[s:e] = rom[s:e]
    return bytes(buf)


def build(out=PATH, without=()):
    regions = [r for r in load_regions() if r[2] not in without]
    data = from_rom(regions)
    body = bytearray(struct.pack("<I", len(regions)))
    for s, e, cat in regions:
        body += struct.pack("<IIB", s, e - s, CATEGORIES.index(cat)) + data[s:e]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(MAGIC + zlib.compress(bytes(body), 9))
    print(f"bc_base: {len(regions)} regions, {sum(e - s for s, e, _ in regions)} bytes "
          f"({os.path.getsize(out)} compressed){' without ' + ', '.join(without) if without else ''} -> {out}")


def regions_of(path=PATH):
    """[(start, bytes, category)]"""
    with open(path, "rb") as f:
        raw = f.read()
    if not raw.startswith(MAGIC):
        raise ValueError(f"not a Beyond Chaos base data file: {path}")
    body = zlib.decompress(raw[len(MAGIC):])
    n = struct.unpack_from("<I", body, 0)[0]
    at, out = 4, []
    for _ in range(n):
        s, size, cat = struct.unpack_from("<IIB", body, at)
        at += 9
        out.append((s, body[at:at + size], CATEGORIES[cat]))
        at += size
    return out


def load(path=PATH):
    """BC's input: the ROM's size, the shipped regions in place, zeros elsewhere."""
    dev = os.environ.get("FF6_BC_BASE_REGIONS")
    if dev:
        return from_rom(load_regions(dev))
    buf = bytearray(ROM_SIZE)
    for s, data, _ in regions_of(path):
        buf[s:s + len(data)] = data
    return bytes(buf)


def merge(regs, gap=16):
    out = []
    for s, e in sorted(regs):
        if out and s - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def collect(traces, ports=(), content=CONTENT, validation=VALIDATION, skip_port=()):
    """The regions to ship, by category: BC's reads (bc_trace.py record on the ROM, every preset traced)
    but CONTENT's and the game code its patches only check (VALIDATION), and the porter's (bc_trace.py
    port: both sides, as a byte of BC's output it didn't write is the input's). Regions are cut where the
    category changes."""
    regs = []
    for d in traces:
        reads = json.load(open(os.path.join(d, "reads.json"), encoding="utf-8"))
        for site, v in reads.items():
            if site in content:
                continue
            for s, e in (tuple(r) for k in ("in", "out") for r in v[k]):
                if site.startswith(validation) and s < CODE_BANKS:
                    continue
                regs.append((s, e))
    for p in ports:
        for side in json.load(open(p, encoding="utf-8")).values():
            for who, v in side.items():
                if who not in skip_port:
                    regs += [(int(a, 16), int(b, 16)) for a, b in v["regions"]]
    regs += EXTRA
    mask = bytearray(ROM_SIZE)
    for s, e in regs:
        s, e = max(0, s), min(e, ROM_SIZE)
        if e > s:
            mask[s:e] = b"\1" * (e - s)
    out = []
    for s, e in merge(_runs(mask), gap=16):          # small gaps (table padding) filled
        for a, b in _split(s, e):
            cat = classify(a)[0]
            if out and out[-1][2] == cat and a == out[-1][1]:
                out[-1][1] = b
            else:
                out.append([a, b, cat])
    # never shipped, whoever read them (gaps filled above included)
    cut = []
    for a, b, cat in out:
        pieces = [(a, b)]
        for s, e in NEVER:
            pieces = [q for x, y in pieces for q in ((x, min(y, s)), (max(x, e), y)) if q[1] > q[0]]
        cut += [[x, y, cat] for x, y in pieces]
    for s, e in ALLOW:
        if not any(a <= s and e <= b for a, b, _ in cut):
            cut.append([s, e, classify(s)[0]])
    return sorted(cut)


def _runs(mask):
    out, s = [], None
    for i in range(len(mask) + 1):
        on = i < len(mask) and mask[i]
        if on and s is None:
            s = i
        elif not on and s is not None:
            out.append((s, i))
            s = None
    return out


def _split(s, e):
    """[s, e) cut where its category changes"""
    cuts = sorted({s, e} | {x for r in RULES for x in r[:2] if s < x < e})
    return list(zip(cuts, cuts[1:]))


def check():
    rom = vanilla_rom()
    shaped = shapes(rom)
    bad = [hex(s) for s, data, cat in regions_of() if (shaped if cat == "shapes" else rom)[s:s + len(data)] != data]
    print("bc_base matches the ROM" if not bad else f"bc_base differs from the ROM at {bad}")
    return 1 if bad else 0


def show(path=REGIONS_FILE):
    regs = load_regions(path)
    by = {}
    for s, e, cat in regs:
        by.setdefault(cat, {}).setdefault(label(s) or "?", []).append(e - s)
    for cat in CATEGORIES:
        if cat not in by:
            continue
        total = sum(sum(v) for v in by[cat].values())
        print(f"{cat}: {total} bytes")
        for k, v in sorted(by[cat].items(), key=lambda kv: -sum(kv[1])):
            print(f"  {sum(v):8d} {k} ({len(v)} regions)")
    print(f"{sum(e - s for s, e, _ in regs):8d} in {len(regs)} regions")


def write_regions(regs, path=REGIONS_FILE, note=""):
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"note": %s,\n"regions": [\n' % json.dumps(note or "tools/bc_basedata.py regions: what BC (on the ROM, "
                "every traced preset) and the porter read, less content BC only copies or rewrites"))
        f.write(",\n".join(json.dumps([hex(a), hex(b), c]) for a, b, c in regs))
        f.write("\n]}\n")


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "build":
        rest = [a for a in argv[1:] if not a.startswith("--")]
        without = ()
        if "--without" in argv:
            without = tuple(argv[argv.index("--without") + 1].split(","))
            rest = [a for a in rest if a != argv[argv.index("--without") + 1]]
        build(rest[0] if rest else PATH, without)
    elif cmd == "regions":
        traces, ports, i = [], [], 1
        while i < len(argv):
            if argv[i] == "--port":
                ports.append(argv[i + 1])
                i += 2
            else:
                traces.append(argv[i])
                i += 1
        regs = collect(traces, ports)
        write_regions(regs)
        print(f"{len(regs)} regions, {sum(b - a for a, b, _ in regs)} bytes -> {REGIONS_FILE}")
    elif cmd == "check":
        return check()
    elif cmd == "show":
        show(argv[1] if len(argv) > 1 else REGIONS_FILE)
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
