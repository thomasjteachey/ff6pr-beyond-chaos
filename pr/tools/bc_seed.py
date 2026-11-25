"""Beyond Chaos seed -> PR data, for the in-game generator (no restart).

  python tools/bc_seed.py --seed 9859608359 [--mode normal] --flags "b c e f ..." [--preset "New Player"] --out DIR

Runs Beyond Chaos CE (its own code, tools/bc_run.py: a seed is BC's exe's seed) on the vanilla
US v1.0 ROM's bytes, or ROM-free on the data the generator ships (data/bc_base.bin, tools/bc_basedata.py,
with tools/bc_romfree.py's stand-ins: the same seed, tools/bc_parity.py), then our porter on the result,
and writes a seed folder the plugin applies live (plugin/BcPlugin on the kit's seed library,
tools/bc_live.py):
  DIR/master/.../Master/<table>.csv   full tables (seed_live.MANAGED_TABLES + anything else changed)
  DIR/message/.../Message/system_en.txt  full text
  DIR/files/<mod path>                 changed chest maps / AI scripts / battle_extra_data
  DIR/bc_seed.json                     {seed, mode, flags, preset, version, tables, files, snes_ai, ...}
  DIR/bc_log.txt, DIR/generate.log     BC's own game guide (its spoiler log); our log
Prints "[bc] ..." progress lines for the plugin's screen. An empty --seed is a random one (BC's
own rule: the time). Never writes a ROM: BC's output stays in memory.
"""
import argparse
import io
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # pr/ or the bundle
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401  (the modding kit's tools, when it's this repository's kit/ submodule)
import prdata as P  # noqa: E402
import ff6snes as S  # noqa: E402
import bc_live as L  # noqa: E402
import bc_run  # noqa: E402

# ROM-free: BC's input is the data the generator ships (the ROM's data tables, no graphics, text, maps or
# code) with stand-ins for what BC only rewrites; no SNES ROM is read or written. The default where there's
# no ROM (the player's bundle); FF6_BC_ROMFREE=1 / 0 forces it.
BASE = os.path.join(ROOT, "data", "bc_base.bin")
_mode = os.environ.get("FF6_BC_ROMFREE", "")
ROMFREE = _mode == "1" or (_mode != "0" and not os.path.exists(P.VANILLA_ROM) and os.path.exists(BASE))
if ROMFREE:
    import bc_basedata  # noqa: E402
    P.VANILLA_ROM = BASE                       # the porter's vanilla side: the same input BC had
    S.MEMORY[os.path.abspath(BASE)] = bc_basedata.load(BASE)


# the plugin's flag list (labels, modes, port status): the project's plugin folder, or the bundle's copy
FLAGS_JSON = next((p for p in (os.path.join(ROOT, "plugin", "BcPlugin", "bc_flags.json"), os.path.join(ROOT, "bc_flags.json"))
                   if os.path.exists(p)), os.path.join(ROOT, "bc_flags.json"))


class _Presets(dict):
    """BC's presets: its own config.SUPPORTED_PRESETS (the plugin's screen has them too, bc_flags.json)."""

    def _load(self):
        if not dict.__len__(self):
            cwd = os.getcwd()
            try:
                if os.path.abspath(bc_run.SRC) not in sys.path:
                    sys.path.insert(0, os.path.abspath(bc_run.SRC))
                os.chdir(bc_run.HOME)
                import config
                self.update({k: " ".join(v.split()) for k, v in config.SUPPORTED_PRESETS.items()})
            finally:
                os.chdir(cwd)

    def __getitem__(self, k):
        self._load()
        return dict.__getitem__(self, k)

    def get(self, k, d=None):
        self._load()
        return dict.get(self, k, d)

    def __contains__(self, k):
        self._load()
        return dict.__contains__(self, k)


PRESETS = _Presets()


def say(text):
    print(f"[bc] {text}", flush=True)


class port_lock:
    """One port at a time in a folder: the porter writes mods/BCSeed (on a development PC several generators
    can run at once: other sessions, tools/bc_parity.py, bc_trace.py), and clears it first."""

    def __init__(self, port_dir):
        self.path = port_dir + ".lock"

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.f = open(self.path, "a+b")
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_LOCK, 1)   # waits ~10 s, then raises: again
                    return self
                except OSError:
                    say("waiting for another seed's port to finish")
        else:
            import fcntl
            fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f, fcntl.LOCK_UN)
        finally:
            self.f.close()
        return False


def port_in_process(rom, name, log):
    """port.py's main in this process, BC's output in memory (ff6snes.MEMORY)."""
    import contextlib
    cwd = os.getcwd()
    try:
        os.chdir(ROOT)
        import port
        import profiles
        prof = profiles.Profile()
        prof.rom, prof.mod_name = rom, name
        prof.snes_ai = True          # monsters run BC's own SNES scripts in the plugin (the kit's SnesAiHost)
        prof.sprite_identity = "pointer"   # a monster's sprite by its graphics pointer (ROM-free: no graphics)
        prof.monster_names = True    # BC's monster and boss names (c with m, y) onto the PR's (port_names)
        prof.character_names = True  # BC's names for the 14 characters (c, makeover) onto MSG_CHAR_NAME_* (port_names)
        prof.guest_commands = True   # BC's `o` gives the guests (Ghosts, Moogles ...) commands too
        prof.metamorph_monsters = True   # BC re-rolls each monster's metamorph set and odds (port_procs)
        # the menus' help (audit gap #10): each Dance lists its steps and each Rage its two attacks (port_dances; no
        # words of BC's own: {} = every Rage described from its abilities), as BC's menus show them
        prof.dance_descriptions = True
        prof.rage_descriptions = lambda: {}
        with contextlib.redirect_stdout(log):
            port.main(prof)
    except SystemExit as e:
        log.write(f"port: exit {e.code}\n")
        say(f"error: the port stopped ({e.code})")
        raise SystemExit(1)
    except Exception as e:  # noqa: BLE001
        import traceback
        log.write(traceback.format_exc())
        say(f"error: the port failed: {e}")
        raise SystemExit(1)
    finally:
        os.chdir(cwd)


def pack(port_dir, out, log, keep=False):
    """The port's folder -> the seed folder: full managed tables and text, the managed files
    (moved, or copied with `keep`: the port's Magicite folder stays whole for tests/test_mod.py)."""
    port_master = os.path.join(port_dir, *L.MASTER_PATH.split("/"))
    port_tables = sorted(f[:-4] for f in os.listdir(port_master) if f.endswith(".csv")) if os.path.isdir(port_master) else []
    extra = [t for t in port_tables if t not in L.MANAGED_TABLES]
    if extra:
        log.write(f"WARNING: tables outside seed_live.MANAGED_TABLES: {extra} (a later seed won't undo them)\n")
    tables = {}
    for t in sorted(set(L.MANAGED_TABLES) | set(port_tables)):
        table, changed = L.full_table(t, os.path.join(port_master, t + ".csv"))
        dest = os.path.join(out, *L.MASTER_PATH.split("/"), t + ".csv")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="") as f:
            f.write(table.to_csv(table.rows.keys()))
        tables[t] = len(changed)
    texts = {}
    for m in L.MESSAGE_FILES:
        text, changed = L.full_messages(os.path.join(port_dir, *L.MESSAGE_PATH.split("/"), m + ".txt"), m)
        dest = os.path.join(out, *L.MESSAGE_PATH.split("/"), m + ".txt")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="") as f:
            for k, v in text.items():
                f.write(f"{k}\t{v}\r\n")
        texts[m] = len(changed)
    managed = set(L.managed_files())
    files, unmanaged = [], []
    for r, _, fs in os.walk(port_dir):
        for fn in fs:
            rel = os.path.relpath(os.path.join(r, fn), port_dir).replace("\\", "/")
            if rel.startswith(("master/", "message/")) or "/keys/" in rel or "/" not in rel:
                continue
            if rel in managed:
                dest = os.path.join(out, "files", *rel.split("/"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                try:
                    if keep:
                        raise OSError("keep the port's folder")
                    os.replace(os.path.join(r, fn), dest)   # port.py clears its folder every run
                except OSError:
                    shutil.copyfile(os.path.join(r, fn), dest)   # another drive (a move can't cross one)
                files.append(rel)
            else:
                unmanaged.append(rel)
    if unmanaged:
        log.write(f"WARNING: {len(unmanaged)} port files no seed can change live (left out): {unmanaged[:20]}\n")
    return tables, texts, files, unmanaged


def check_bundle():
    """Run from a player bundle (generator/bundle.json beside tools/): its tools must be the ones it was built with,
    or its data may not match them (a newer tool expecting a file the bundle lacks)."""
    import json
    path = os.path.join(ROOT, "bundle.json")
    if not os.path.exists(path):
        return
    try:
        want = json.load(open(path, encoding="utf-8")).get("tools")
    except (OSError, ValueError):
        return
    if want and bc_run.tools_stamp(HERE) != want:
        raise SystemExit("error: this generator's tool scripts aren't the ones its bundle was built with (bundle.json "
                         "'tools'): its data may not match them. Rebuild the bundle (tools/bc_bundle.py), or reinstall "
                         "the mod's zip.")


def main():
    check_bundle()
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="")
    ap.add_argument("--mode", default="normal")
    ap.add_argument("--flags", default="")
    ap.add_argument("--preset", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep-port", action="store_true",
                    help="keep the port's Magicite folder (pr/mods/BCSeed) for PR_MOD=BCSeed tests/test_mod.py")
    a = ap.parse_args()
    flags = " ".join(a.flags.split())
    if a.preset:
        flags = " ".join((PRESETS[a.preset] + " " + flags).split())
    seed = a.seed.strip() or str(int(time.time()) % 10 ** 10)
    out = os.path.abspath(a.out)
    work = out + ".work"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    log = open(os.path.join(work, "generate.log"), "w", encoding="utf-8")
    log.write(f"Beyond Chaos {bc_run.VERSION} ({bc_run.SRC}, home {bc_run.HOME})\n"
              f"ROM {'none: the shipped data (ROM-free) ' + BASE if ROMFREE else P.VANILLA_ROM}\n"
              f"Python {sys.version}\nseed {bc_run.seed_string(seed, a.mode, flags)}\n")
    if not os.path.exists(P.VANILLA_ROM):
        say(f"error: vanilla ROM not found ({P.VANILLA_ROM})")
        raise SystemExit(1)
    t0 = time.time()
    import bc_assets    # a player's install that fetches BC's art from its releases does it once, here
    try:
        bc_assets.ensure(say=say)
    except (OSError, SystemExit, ValueError) as e:
        say(f"error: Beyond Chaos's sprites and samples couldn't be fetched: {e}")
        raise SystemExit(1)

    say("randomizing (Beyond Chaos)")
    vanilla = S.rom_bytes(P.VANILLA_ROM)
    bc_out = io.StringIO()
    capture = {}
    try:
        import bc_sprites      # bc-sprites: records BC's sprite choices as BC makes them (no draws of ours)
        import bc_events       # bc-events: records BC's Zozo clock shuffles as BC makes them (no draws of ours)
        import bc_data         # bc-seeds: records BC's event gifts as BC rerolls them (no draws of ours)
        data, spoiler = bc_run.run(vanilla, seed, a.mode, flags, say=lambda line: bc_out.write(line + "\n"), capture=capture,
                                   prepare=lambda: (bc_sprites.prepare(capture), bc_events.prepare(capture),
                                                    bc_data.prepare(capture)),
                                   romfree=ROMFREE)
    except Exception as e:  # noqa: BLE001
        import traceback
        log.write(bc_out.getvalue() + traceback.format_exc())
        say(f"error: Beyond Chaos stopped: {e}")
        raise SystemExit(1)
    log.write(bc_out.getvalue())
    # BC's effective flags (bc_run.effective_flags: the mode's forced ones, those BC turns on itself, minus the
    # prohibited): what the steps check. BC itself and the seed string keep the typed ones (the seed's identity).
    eff = capture.get("flags") or flags
    rom = os.path.join(work, "bc_out.bin")      # never a file: the port reads it from memory
    S.MEMORY[os.path.abspath(rom)] = data
    info = {"seed": seed, "mode": a.mode, "flags": flags, "preset": a.preset, "version": bc_run.VERSION,
            "seed_string": bc_run.seed_string(seed, a.mode, flags), "effective_flags": eff}
    say(f"randomized in {time.time() - t0:.1f} s")

    say("porting to the Pixel Remaster")
    name = "BCSeed"
    os.environ.pop("WC_FLAGS", None)   # the porter's WC-only paths stay off
    os.environ["PR_SEED_LIVE"] = "1"   # applied in game: no new files (port_chests.live_seed)
    port_dir = os.path.join(P.ROOT, "mods", name)   # where the porter writes (profiles.Profile.out)
    with port_lock(port_dir):
        port_in_process(rom, name, log)
        import port_ai
        snes_ai = getattr(port_ai.port, "snes_ai", None)

        say("packing the seed")
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        tables, texts, files, unmanaged = pack(port_dir, out, log, keep=a.keep_port)
        if not a.keep_port:
            shutil.rmtree(port_dir, ignore_errors=True)   # inside the lock: the next seed's port may start
    with open(os.path.join(out, "bc_log.txt"), "w", encoding="utf-8") as f:
        f.write(spoiler)
    # BC's replaced commands: their PR command rows, random abilities and names (tools/bc_commands.py)
    import bc_commands
    try:
        info["commands"] = bc_commands.apply(out, capture.get("commands", {}), lambda m: log.write(m + "\n"))
        if info["commands"]:
            tables["command"] = len(info["commands"])
    except Exception as e:  # noqa: BLE001 - the seed still plays with the PR's commands in those slots
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: BC's commands weren't ported: {e}")
    # what BC's "?" on an item means, in the item's description (tools/bc_items.py)
    import bc_items
    try:
        info["changed_items"] = len(bc_items.apply(out, P.VANILLA_ROM, rom, spoiler, lambda m: log.write(m + "\n")))
    except Exception as e:  # noqa: BLE001
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: BC's changed items weren't described: {e}")
    # BC's small codes that are data here (tools/bc_codes.py)
    import bc_codes
    try:
        info["codes"] = bc_codes.apply(out, eff, lambda m: log.write(m + "\n"))
    except Exception as e:  # noqa: BLE001
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: BC's codes weren't applied: {e}")
    # BC's data the shared porter doesn't carry by itself: dance names, starting gil (tools/bc_data.py)
    import bc_data
    try:
        info.update(bc_data.apply(out, data, S.rom_bytes(P.VANILLA_ROM), eff, lambda m: log.write(m + "\n")))
        if capture.get("event_items"):
            info["event_items"] = capture["event_items"]   # BC's event gifts, before/after (bc_data.prepare; for bc_events)
        # bingoboingo's cards (bc_run takes them from BC's run): beside the seed, shown by the guide (bc_guide)
        for n, card in enumerate(capture.get("bingo") or [], 1):
            with open(os.path.join(out, f"bingo_{n}.txt"), "w", encoding="utf-8", newline="") as f:
                f.write(card.replace("\r\n", "\n").replace("\n", "\r\n"))
            info.setdefault("bingo", []).append(f"bingo_{n}.txt")
    except Exception as e:  # noqa: BLE001
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: BC's dance names / starting gil weren't ported: {e}")
    # bc-battle: what the plugin's battle code reads (encounter rules, codes, item specials, junction
    # effects) into bc_battle.json (tools/bc_battle.py)
    import bc_battle
    try:
        info["battle"] = bc_battle.apply(out, rom, spoiler, eff, lambda m: log.write(m + "\n"))
    except Exception as e:  # noqa: BLE001 - the seed still plays without the battle side's extras
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: BC's battle data wasn't made: {e}")
    # bc-events: BC's light events (worringtriad, r, j, k, notawaiter...): the seed's PR scripts, map files, lines
    # and tables, read from BC's output, and bc_events.json for the plugin (tools/bc_events.py)
    import bc_events
    try:
        ev_files, ev = bc_events.apply(out, eff, rom=data, vanilla_rom=P.VANILLA_ROM, spoiler=spoiler,
                                       capture=capture, log=lambda m: log.write(m + "\n"), mode=a.mode)
        files.extend(f for f in ev_files if f not in files)
        info["events"] = {k: v for k, v in ev.items() if k in ("flags", "lines")}
    except Exception as e:  # noqa: BLE001 - the seed still plays, with vanilla's events
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: BC's events weren't made: {e}")
    # bc-strange: `strangejourney`'s shuffled short entrances on the PR's doors, after bc_events (its map files are the
    # seed's copies): the doors' map files and new arrival points in files/, bc_doors.json (what wasn't rewired, the
    # doors several story versions or both worlds share, for the plugin) (tools/bc_entrances.py)
    try:
        import bc_entrances
        door_files, doors = bc_entrances.apply(out, eff, data, vanilla, mode=a.mode, log=lambda m: log.write(m + "\n"))
        files.extend(f for f in door_files if f not in files)
        if doors:
            info["entrances"] = doors
    except Exception as e:  # noqa: BLE001 - the seed still plays, with the PR's doors
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: BC's entrance shuffle wasn't ported: {e}")
    # bc-seeds: BC's event gifts (`t` rerolls 28: Owzer's, the Sealed Gate's, Vector's...) in the PR's scripts
    # that give them, after bc_events (its cut scenes carry their own) (tools/bc_gifts.py)
    # and `y`'s esper shuffle: the espers those scripts give, the lines naming them, the Phoenix Cave, the sword
    import bc_gifts
    try:
        if capture.get("event_items"):
            gift_files, info["event_gifts"] = bc_gifts.apply(out, capture["event_items"], eff,
                                                             lambda m: log.write(m + "\n"))
            files.extend(f for f in gift_files if f not in files)
        esper_files, espers = bc_gifts.espers(out, data, S.rom_bytes(P.VANILLA_ROM), eff,
                                              lambda m: log.write(m + "\n"))
        files.extend(f for f in esper_files if f not in files)
        if espers:
            info["espers"] = espers
    except Exception as e:  # noqa: BLE001 - the seed still plays, with the PR's gifts
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: BC's event gifts weren't ported: {e}")
    # bc-sprites: BC's character art (makeover and its options, `s`, `c`'s palettes) into sprites/ (PNG sheets +
    # art.json), served in game by the kit's ArtSwap (tools/bc_sprites.py, BcSprites.cs)
    try:
        info["sprites"] = bc_sprites.build(out, capture, data, vanilla_rom=vanilla, log=lambda m: log.write(m + "\n"))
    except Exception as e:  # noqa: BLE001 - the seed still plays with the game's own art
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: BC's sprites weren't made: {e}")
    # bc-sprites: `n`'s window colors on the PR's window sprites (tools/bc_palettes.py)
    try:
        import bc_palettes
        pal = bc_palettes.build(out, data, eff, vanilla=vanilla, log=lambda m: log.write(m + "\n"))
        if pal:
            info["palettes"] = pal
    except Exception as e:  # noqa: BLE001 - the seed still plays with the game's windows
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: BC's window colors weren't made: {e}")
    # bc-sprites: remonsterate's pictures and `c`'s monster palettes, each changed monster on an image key of its
    # own (tools/bc_monsters.py)
    try:
        import bc_monsters
        mon = bc_monsters.build(out, spoiler, rom=data, vanilla=vanilla, log=lambda m: log.write(m + "\n"))
        if mon:
            info["remonsterate"] = mon["monsters"]
            info["monster_recolors"] = mon["recolors"]
            for t, n in mon["tables"].items():
                tables[t] = tables.get(t, 0) + n
    except Exception as e:  # noqa: BLE001 - the seed still plays with the game's monster art
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: BC's monster pictures weren't made: {e}")
    # bc-music: johnnydmad's songs (BC's output, its own tracklist) into music/ (a song pack + bc_music.json),
    # played in game by the kit's SNES player (tools/bc_music.py, BcMusic.cs)
    try:
        import bc_music
        info["music"] = bc_music.apply(out, data, P.VANILLA_ROM, eff, lambda m: log.write(m + "\n"))
    except Exception as e:  # noqa: BLE001 - the seed still plays with the game's own music
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: BC's music wasn't made: {e}")
    import seed_info
    for key, make in (("magitek", lambda: seed_info.magitek(rom)),
                      ("esper_bonus", lambda: seed_info.esper_bonus(P.VANILLA_ROM, rom)),
                      ("command_weapons", lambda: seed_info.command_weapons(P.VANILLA_ROM, rom)),
                      # BC shows every reward (its show_coliseum_rewards patch) unless fightclub: then the SNES rule
                      ("coliseum", lambda: seed_info.coliseum(P.VANILLA_ROM, rom, hidden=(lambda b: b != 0)
                                                              if "fightclub" in eff.split() else (lambda b: False))),
                      (None, lambda: seed_info.monster_chests(P.VANILLA_ROM, rom, out,
                                                                     lambda m: log.write(m + "\n"), make_missing=True))):
        try:
            if key:
                info[key] = make()
            else:
                info.update(make())   # boxes, monster_chests
        except Exception as e:  # noqa: BLE001 - the seed still plays without it
            log.write(f"{key or 'monster chests'}: {e}\n")
    # a guide to this seed for someone new to Beyond Chaos (tools/bc_guide.py): the plugin shows it after
    # the opening's controls tutorial and on its screen. Last of the steps: it reads what they made (bc_battle's
    # junction effects, bc-sprites' "sprites" for Who's who, the character names in the text, bc_events)
    import bc_guide
    try:
        flags_json = FLAGS_JSON
        modes = json.load(open(flags_json, encoding="utf-8")).get("modes", []) if os.path.exists(flags_json) else []
        info["mode_label"] = next((m["label"] for m in modes if m["name"] == a.mode), a.mode)
        info["guide"] = bc_guide.for_seed(out, eff, info, FLAGS_JSON,
                                          lambda m: log.write(m + "\n"))
        rel, info["guide_messages"] = bc_guide.write_in_game(out, info["guide"], info, info.get("mode_label", "Normal"),
                                                             lambda m: log.write(m + "\n"))
        files.append(rel)
    except Exception as e:  # noqa: BLE001
        import traceback
        log.write(traceback.format_exc())
        say(f"warning: the guide wasn't made: {e}")
    if snes_ai:
        info["snes_ai"] = snes_ai   # the plugin runs these scripts (the kit's SnesAiHost)
    info.update(tables=tables, messages=texts, files=sorted(files), unmanaged=len(unmanaged),
                created=time.strftime("%Y-%m-%d %H:%M:%S"), seconds=round(time.time() - t0, 1))
    with open(os.path.join(out, "bc_seed.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1)
    log.close()
    shutil.copyfile(os.path.join(work, "generate.log"), os.path.join(out, "generate.log"))
    shutil.rmtree(work, ignore_errors=True)
    changed_rows = sum(tables.values())
    say(f"done: seed {seed}: {changed_rows} rows in {sum(1 for v in tables.values() if v)} tables, "
        f"{sum(texts.values())} texts, {len(files)} files, {info['seconds']} s")


if __name__ == "__main__":
    main()
