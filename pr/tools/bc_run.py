"""Run Beyond Chaos CE's own randomize() (its Python, untouched) on ROM bytes in memory.

  python tools/bc_run.py OUT --seed 9859608359 [--mode normal] --flags "b c e f ..." [--rom PATH] [--log LOG]

BC is run the way its exe runs it (a PyInstaller build): `sys._MEIPASS` is BC's source folder
(tables, music, data), the working folder holds the release's `custom/` (names, sprites, opera)
and `remonsterate/` (monster images). A seed made here is the exe's seed: BC's commit 27de07a
(main, 2024-09-11, "Update version to 6.1.3"; the git tag CE-6.1.3 sits on an earlier commit
without the release's last fixes) gives a ROM byte-identical to BeyondChaos.exe 6.1.3's. Its
random draws are all Python's random, reseeded (`seed + counter`) before each stage.

OUT gets the ROM bytes zlib'd behind OUT_MAGIC (ff6snes.rom_bytes reads it; never an .sfc), and
LOG BC's spoiler log. Used in process by tools/bc_seed.py (one fresh process per seed: BC keeps
its state in module globals).
"""
import argparse
import contextlib
import io
import os
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # pr/ or the generator bundle
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401  (the modding kit's tools, when it's this repository's kit/ submodule)

VERSION = "CE-6.1.3"          # BC's release this port follows (its exe; source commit 27de07a)
COMMIT = "27de07a"
OUT_MAGIC = b"FF6BCO1\0"      # a BC run's output: zlib'd ROM bytes (ff6snes.rom_bytes)
LOG_SECTIONS = ['characters', 'stats', 'aesthetics', 'commands', 'blitz inputs', 'magitek', 'slots', 'dances',
                'espers', 'item magic', 'item effects', 'command-change relics', 'colosseum', 'monsters', 'music',
                'remonsterate', 'shops', 'treasure chests', 'junctions', 'zozo clock', 'secret items']
MODES = ["normal", "ancientcave", "speedcave", "racecave", "katn", "dragonhunt"]


def _first(*paths):
    return next((p for p in paths if p and os.path.isdir(p)), paths[-1])


# BC's source (its git checkout at VERSION; the bundle's bc/) and the folder BC works in (the
# release's custom/ and remonsterate/; the bundle's bc_home/)
SRC = os.environ.get("FF6_BC_SRC") or _first(os.path.join(ROOT, "bc"),
                                             os.path.join(ROOT, "..", "mods", "beyond-chaos", "src", "BeyondChaos"))
HOME = os.environ.get("FF6_BC_HOME") or _first(os.path.join(ROOT, "bc_home"),
                                               os.path.join(ROOT, "..", "build", "beyond-chaos", "work"))


def seed_string(seed, mode, flags):
    return f"{VERSION}|{mode}|{' '.join(flags.split())}|{seed}"


def describe(sub):
    """One of BC's command subroutines (skillrandomizer: SpellSub, RandomSpellSub, ComboSpellSub,
    MultipleSpellSub, ChainSpellSub) as JSON: SNES skill ids, the random list as BC rolls it (its 8, 16
    or 32 entries: a skill listed twice is twice as likely), counts."""
    kind = type(sub).__name__
    if kind == "SpellBlock":                      # suplexwrecks: a skill itself
        return {"kind": "skill", "skill": sub.spellid}
    if kind == "SpellSub":
        return {"kind": "skill", "skill": sub.spellid}
    if kind == "RandomSpellSub":
        return {"kind": "random", "class": getattr(sub, "name", ""), "about": getattr(sub, "spells_description", ""),
                "wild": bool(getattr(sub, "wild", False)), "skills": [s.spellid for s in getattr(sub, "spells", [])]}
    if kind == "ComboSpellSub":
        return {"kind": "combo", "skills": [s.spellid for s in sub.spells]}
    if kind in ("MultipleSpellSub", "ChainSpellSub"):
        d = {"kind": "multiple" if kind == "MultipleSpellSub" else "chain", "inner": describe(sub.spellsub)}
        if kind == "MultipleSpellSub":
            d["count"] = sub.count
        return d
    return {"kind": "unknown", "type": kind}


def run(rom, seed, mode="normal", flags="", say=print, capture=None, prepare=None, romfree=False):
    """BC on `rom` (vanilla US 1.0 bytes, or the ROM-free base): (output bytes, spoiler log).
    capture: a dict that gets "commands": what each command BC replaced does (its SNES command id ->
    BC's name, targeting byte, and describe() of its subroutine), recorded where BC names it
    (CommandBlock.newname, which draws nothing: the seed stays the exe's).
    romfree: BC's input is tools/bc_basedata.py's data (no ROM): tools/bc_romfree.py's stand-ins go in
    first. prepare: called once BC's modules are loaded (tools/bc_trace.py's recording)."""
    src, home = os.path.abspath(SRC), os.path.abspath(HOME)
    if not os.path.isfile(os.path.join(src, "randomizer.py")):
        raise SystemExit(f"no Beyond Chaos source at {src} (FF6_BC_SRC)")
    if not os.path.isdir(os.path.join(home, "custom")):
        raise SystemExit(f"no custom/ folder in {home} (FF6_BC_HOME: BC's release files)")
    cwd = os.getcwd()
    os.chdir(home)
    sys._MEIPASS = src
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import config
        config.VERSION = VERSION          # before randomizer's `from config import VERSION`
        import randomizer
        randomizer.VERSION = VERSION
        # remonsterate (a child process per attempt) through tools/bc_remon.py: its prepared images cached, and
        # ROM-free its stand-ins
        import bc_remon
        randomizer.remonsterate = bc_remon.child
        os.environ.pop("FF6_BC_ROMFREE_CHILD", None)
        # on (the BC lead, 2026-11-21: 22 seeds identical off/on, and 4 forced music rerolls identical);
        # FF6_BC_MUSIC_FAST=0 turns it off
        if os.environ.get("FF6_BC_MUSIC_FAST", "1") != "0":
            fast_music()
        if romfree:
            import bc_romfree
            bc_romfree.patch()
        if prepare:
            prepare()
        inb, outb = io.BytesIO(bytes(rom)), io.BytesIO(bytes(rom))
        # BC's web mode (buffers, no files) still names the console's paths: the input once
        # (manage_commands_new: get_ranked_spells(infile_rom_path), whose list is cached by then)
        # and the output as its return value
        randomizer.infile_rom_path = inb
        randomizer.outfile_rom_path = None
        import skillrandomizer
        named = {}
        original_newname = skillrandomizer.CommandBlock.newname

        def newname(block, text, fout):
            frame = sys._getframe(1)
            named[block.id] = (text, frame.f_locals.get("spell") or frame.f_locals.get("sb"), getattr(block, "targeting", None))
            return original_newname(block, text, fout)

        if capture is not None:
            skillrandomizer.CommandBlock.newname = newname
        out = io.StringIO()
        t = time.time()
        try:
            with contextlib.redirect_stdout(out):
                randomizer.randomize(application="web", infile_rom_buffer=inb, outfile_rom_buffer=outb,
                                     seed=seed_string(seed, mode, flags), **BINGO)
        finally:
            skillrandomizer.CommandBlock.newname = original_newname
        # bingoboingo's cards (BC writes bingo.<seed>.<n>.txt in its working folder, after the ROM and log are
        # done): taken into capture["bingo"] for the seed folder, and the files removed
        cards = []
        for name in sorted(os.listdir(os.getcwd())):
            path = os.path.join(os.getcwd(), name)
            if name.startswith("bingo.") and name.endswith(".txt") and os.path.getmtime(path) >= t - 1:
                with open(path, encoding="utf-8", errors="replace") as f:
                    cards.append(f.read())
                os.remove(path)
        if capture is not None and cards:
            capture["bingo"] = cards
        if capture is not None:
            capture["commands"] = {cid: {"name": text, "targeting": tgt, **describe(sub)}
                                   for cid, (text, sub, tgt) in sorted(named.items()) if cid is not None}
            capture["flags"] = effective_flags(randomizer)
        text = out.getvalue()
        for line in text.splitlines():
            if line.startswith("{'ord'"):
                break          # web mode prints its result dict (the ROM buffer and the whole log)
            if line.strip():
                say(line.rstrip())
        spoiler = randomizer.get_log_string(LOG_SECTIONS)
        say(f"Beyond Chaos: {time.time() - t:.1f} s")
        # BC's output buffer at the end (remonsterate hands back a new one: the exe writes that one)
        return randomizer.outfile_rom_buffer.getvalue(), spoiler
    finally:
        os.chdir(cwd)


MUSIC_MODULES = ("music.mfvitools.insertmfvi", "mfvitools.insertmfvi", "music.musicrandomizer", "musicrandomizer",
                 "music.johnnydmad", "johnnydmad", "music.jukebox", "jukebox", "musicinterface")


def fast_music():
    """johnnydmad's inserter (music/mfvitools/insertmfvi.py) builds its ROM with byte_insert, which returns
    data[:p] + new + data[p+n:]: a copy of the whole ~4 MB ROM for every few bytes, thousands of times a seed
    (16 s of a profiled 84). Here byte_insert edits a bytearray in place instead: the same bytes (a slice assignment
    past the end extends it as the concatenation does). Safe because every caller reassigns the result to the
    buffer it passed (insertmfvi's outrom is its own bytearray(inrom); put_somewhere raises before inserting), and a
    bytes argument keeps BC's own function (mml2mfvi has its own byte_insert for small buffers: untouched).
    FF6_BC_MUSIC_FAST=0 turns it off (on since 2026-11-21: 22 seeds and 4 forced rerolls identical); tools/bc_parity.py and `bc_remon.py`-style runs check the same seeds."""
    import importlib
    for name in ("music.mfvitools.insertmfvi", "mfvitools.insertmfvi"):
        try:
            mod = importlib.import_module(name)
            break
        except ImportError:
            mod = None
    if mod is None or getattr(mod.byte_insert, "_bc_fast", False):
        return
    original = mod.byte_insert

    def byte_insert(data, position, newdata, maxlength=0, end=0):
        if not isinstance(data, bytearray):
            return original(data, position, newdata, maxlength, end)
        if position > len(data):
            data += b"\x00" * (position - len(data))
        if end:
            maxlength = end - position + 1
        if maxlength and len(newdata) > maxlength:
            newdata = newdata[:maxlength]
        data[position:position + len(newdata)] = newdata
        return data

    byte_insert._bc_fast = True
    for name in MUSIC_MODULES:
        m = sys.modules.get(name)
        if m is not None and getattr(m, "byte_insert", None) is original:
            m.byte_insert = byte_insert


# bingoboingo's card settings: BeyondChaos.exe asks for them (its GUI's BingoPrompts / console.py); web mode takes
# them as randomize()'s keywords and has none of its own (bc_run passed none: `size ** 2` on None, audit gap #2).
# These are the exe's defaults: every square type (the console's blank answer, "aims"), a 5x5 grid, Normal
# difficulty (the GUI's preselected choice), one card. Read only by manage_bingo, after the ROM and log: no draws
# of the seed change.
BINGO = {"bingo_type": "aims", "bingo_size": 5, "bingo_difficulty": "n", "bingo_cards": 1}


def tools_stamp(tools_dir):
    """A stamp of a generator's tool scripts (every *.py directly in tools_dir, by name and content): bc_bundle writes
    it into bundle.json, bc_seed compares at its start, so a bundle whose tools were swapped for newer ones (whose data
    don't match) stops with a clear message instead of a KeyError half-way (QA's laptop, 2026-11-21)."""
    import hashlib
    h = hashlib.sha1()
    for name in sorted(n for n in os.listdir(tools_dir) if n.endswith(".py")):
        h.update(name.encode() + b"\0")
        with open(os.path.join(tools_dir, name), "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def effective_flags(randomizer):
    """BC's flags as its own Options_ holds them after the run (read once BC is done: no draw changes): the typed
    ones minus those the mode prohibits, plus the mode's forced flags (Dragon Hunt: worringtriad) and those BC turns
    on itself (strangejourney -> notawaiter, makeover...), in BC's order and its codes ("name", or "name:value")."""
    out = []
    for f in randomizer.Options_.active_flags:
        out.append(f.name if str(f.value).lower() == "true" else f"{f.name}:{f.value}")
    return " ".join(out)


def write_output(path, data):
    with open(path, "wb") as f:
        f.write(OUT_MAGIC + zlib.compress(data, 6))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--seed", required=True)
    ap.add_argument("--mode", default="normal")
    ap.add_argument("--flags", default="")
    ap.add_argument("--rom", default=None, help="input ROM (default: the vanilla US 1.0 ROM)")
    ap.add_argument("--log", default=None, help="BC's spoiler log")
    ap.add_argument("--sfc", action="store_true", help="write OUT as a plain ROM (testing only)")
    a = ap.parse_args()
    import prdata as P
    import ff6snes as S
    rom = S.rom_bytes(a.rom or P.VANILLA_ROM)
    data, spoiler = run(rom, a.seed, a.mode, a.flags)
    if a.sfc:
        with open(a.out, "wb") as f:
            f.write(data)
    else:
        write_output(a.out, data)
    if a.log:
        with open(a.log, "w", encoding="utf-8") as f:
            f.write(spoiler)


if __name__ == "__main__":
    main()
