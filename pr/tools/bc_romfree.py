"""Beyond Chaos without the SNES ROM's content: stand-ins for what BC only copies or rewrites.

The ROM-free generator (PORTING.md "Beyond Chaos port", "ROM-free"). BC reads its input ROM for two kinds of
things (tools/bc_trace.py records each read with the BC function that made it, and each random draw):
  - data it randomizes with its draws: characters, commands, spells, items, espers, monsters and their AI,
    formations, packs, zones, chests, shops, the Colosseum, dances, map properties ... shipped as
    data/bc_base.bin (tools/bc_basedata.py)
  - content it only copies or rewrites: sprites and portraits (makeover), dialogue, the opening and the
    ending, the sound program (johnnydmad), game code it patches
These patches stand in for the second kind where BC would stop on zeros or would draw differently, keeping
every draw of every stage (BC reseeds before each one) and every table the porter reads: a seed made
ROM-free is BC's exe's seed (tools/bc_parity.py checks it on the ROM). What BC writes over the content is
SNES content the port never reads.

Each stand-in names what it replaces and why it keeps the draws. Used by tools/bc_run.py (romfree=True)
once BC's modules are loaded.
"""

# The opening's Magitek palette (in the opening's compressed graphics, which aren't shipped) decides how
# many draws BC's luma recolouring makes. BC hands it the palette's 32 bytes, each taken as a colour: only
# their number, how many different brightnesses (r+g+b) they have and whether the middle one is neither the
# darkest nor the brightest count. These are those brightnesses, each a byte that has it (our bytes, not
# the palette), so BC draws as it does on the ROM.
MAGITEK_BRIGHTNESS = [0, 0, 22, 3, 16, 18, 9, 14, 7, 6, 14, 28, 12, 24, 15, 3, 12, 26, 6, 14, 11, 5, 14, 30,
                      7, 18, 8, 1, 8, 1, 8, 1]


def patch_validation():
    """BC's assembly patches (randomtools write_patch) check the game code they replace (their VALIDATION
    blocks) and stop if it isn't the ROM's; the code isn't shipped. A failed check only prints (as BC's own
    noverify patches do): the patch is written the same, nothing drawn."""
    from randomtools import tablereader
    d = list(tablereader.write_patch.__defaults__)
    # (parameters, mapping, noverify, validate, force)
    d[3] = False
    tablereader.write_patch.__defaults__ = tuple(d)


def patch_opening():
    """The opening (manage_opening: its compressed graphics, palettes and credits, rewritten and
    recompressed; the port doesn't read it): the same palette transformers, so the same draws; nothing
    written."""
    import randomizer
    get = randomizer.get_palette_transformer

    def manage_opening():
        get(always=True)                     # clouds, lightning, fire
        get(always=True)                     # the end of the world
        get(use_luma=True, basepalette=bytes(MAGITEK_BRIGHTNESS))     # Magitek

    randomizer.manage_opening = manage_opening


def patch_music():
    """johnnydmad's insertmfvi looks for FF6's sound program before it replaces it (16 bytes of it, which
    BC's own source carries as the check's constant): the constant goes in BC's working copy, so the check
    passes; the program isn't needed otherwise (BC's songs and samples replace the game's)."""
    from music.mfvitools import insertmfvi as M
    sig = next(c for c in M.insertmfvi.__code__.co_consts if isinstance(c, bytes) and len(c) == 16)
    original = M.insertmfvi

    def insertmfvi(inrom, *a, **kw):
        at = 0x50710
        if inrom[at:at + 16] != sig:
            inrom = inrom[:at] + sig + inrom[at + 16:]
        return original(inrom, *a, **kw)

    M.insertmfvi = insertmfvi
    import music.musicrandomizer as R
    if getattr(R, "insertmfvi", None) is original:
        R.insertmfvi = insertmfvi


def patch_remonsterate():
    """remonsterate's own patch (its monster_expansion_patch) checks the ROM's header and code it replaces:
    not enforced either (in its child process: tools/bc_remon.py child)."""
    from remonsterate.tools import tablereader as T
    T.write_patch.__defaults__ = (True, False)      # (noverify, force)


def patch():
    patch_validation()
    patch_opening()
    patch_music()
    # remonsterate runs in a child process (tools/bc_remon.py child, which bc_run always uses): it applies
    # patch_remonsterate there when this is set (a child inherits the environment)
    import os
    os.environ["FF6_BC_ROMFREE_CHILD"] = "1"
