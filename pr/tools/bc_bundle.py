"""Build what the Beyond Chaos plugin needs besides its DLL: the seed generator a player runs in game (Python,
Beyond Chaos's own code, our porter, the data tables BC reads), the baselines and the Magicite folder.

  .venv/Scripts/python tools/bc_bundle.py [OUT_DIR] [--dev] [--check]   (default pr/build/BeyondChaos)

OUT_DIR/plugin/    -> BepInEx/BeyondChaos/ (the plugin's data folder, beside BepInEx/plugins)
  generator/python/      CPython (+ Pillow, which remonsterate uses), copied from this PC's install
  generator/tools/       the porter: the tool scripts bc_seed.py and bc_gamedata.py need (gen_bundle)
  generator/bc/          Beyond Chaos's source at commit 27de07a (= BeyondChaos.exe 6.1.3's seeds; MIT):
                         its randomizer, tables, johnnydmad (music) and remonsterate code; no GUI, no tests
  generator/bc_home/     the folder BC works in: the release's custom/ (names, sprites, opera) and
                         remonsterate/ (monster images) -- see ASSETS
  generator/data/bc_base.bin   the ROM's data tables BC reads (ROM-free: tools/bc_basedata.py, bc_romfree.py)
  generator/gamedata.json, gamedata_recipe.json, gamedata/   the game's files a player's install makes from
                         their own game (tools/bc_gamedata.py setup): the zip leaves vanilla/, cache/,
                         baseline/files, baseline/vanilla_data and the Magicite folder out
  generator/bundle.json  written last: {"mod", "version", "built"} (the Deck tooling counts a BC install as
                         installable when it's there)
  baseline/files/, baseline/vanilla_data/   the vanilla copies a seed can change (bc_live)
OUT_DIR/magicite/BeyondChaos/ -> StreamingAssets/Magicite/BeyondChaos (bc_live.write_baseline)

--dev: only the baselines and the Magicite folder (the generator stays the project's on a development PC: the
plugin's config [Generator] ProjectDir). --check: a seed made with the bundled Python alone, ROM-free, compared
with the project's (tools/bc_parity.compare).

ASSETS: where BC's art and samples from other games come from (its custom/ sprites, remonsterate/ images,
music/samples): "bundle" (in the player's zip, as BC ships them) or "release" (left out; the player's
machine fetches BC's release, tools/bc_assets.py). "bundle" is the default: the user has every mod owner's
permission to bundle their art, sprites and music (2026-11-20), and FF6's SNES sound driver and 8 built-in
instrument waveforms may ship too (2026-11-20 ~20:55: data/ff6_resident.json, written by bc_music.bundle_data).
Never shipped: the SNES ROM, any other SNES data, the PR's own files.
"""
import datetime
import glob
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.dirname(HERE)
PROJECT = os.path.dirname(PR)
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
import bc_live as L  # noqa: E402
import gen_bundle as GB  # noqa: E402

OUT = os.path.join(PR, "build", "BeyondChaos")
ASSETS = os.environ.get("FF6_BC_ASSETS", "bundle")     # "bundle" | "release"
# the scripts the plugin runs (BcSeeds' generator: bc_seed.py; the game-data setup: bc_gamedata.py) and those
# build() runs in the bundle; gen_bundle adds what they import or start
ENTRY_TOOLS = ["bc_seed", "bc_gamedata", "pr_script", "port_chests", "bc_live", "bc_assets", "bc_remon", "bc_romfree"]
# other mods' modules, reachable only through their own profiles
OTHER_MODS = {"bnw_plugin_data", "port_bnw", "profile_bnw", "wc_seed", "wc_live", "wc_run", "wc_romfree",
              "wc_basedata", "wc_gamedata", "wc_bundle", "wc_events"}
# BC's source: what its randomizer runs (randomize(), johnnydmad, remonsterate); not its GUI, console or tests
BC_SKIP_FILES = ["beyondchaos.py", "console.py", "tests.py", "update.py", "*.bat", "*.sln", "*.pyproj*", "*.pyperf",
                 "test*.py", "*.sfc", "*.smc"]
BC_SKIP_DIRS = {"__pycache__", ".git", ".github", "gui_themes", "test", "tests"}
# the PR files the generator reads (traced on BC seeds with an audit hook: master tables, text, monster AI,
# battle scripts and data; the maps' entities), whole folders so other flags reading other files there work
VANILLA_DIRS = ["master", "message", "monster_ai", "battle_script", "battleextradata", "assetspath"]
VANILLA_GLOBS = ["map_*/**/entity_default.json",
                 # the world maps' encounter grids and ground types (port_encounter_rates: BC's encounter rules)
                 "map_10010/**/encount_grid.json", "map_10010/**/attribute.json",
                 "map_10020/**/encount_grid.json", "map_10020/**/attribute.json"]


def version():
    import re
    cs = open(os.path.join(PR, "plugin", "BcPlugin", "Plugin.cs"), encoding="utf-8").read()
    m = re.search(r'Version\s*=\s*"([^"]+)"', cs) or re.search(r'BepInPlugin\([^)]*"(\d+\.\d+\.\d+)"', cs)
    return m.group(1) if m else "0.0.0"


def write_baseline_data(plugin, magicite):
    import bc_gamedata
    bc_gamedata.write_baseline_data(plugin, magicite)


# BC's art and samples from other games (generator-relative): left out of a "release" bundle, fetched on the
# player's machine (tools/bc_assets.py, checked file by file against this build's)
ART = ["bc_home/custom/sprites", "bc_home/custom/spritereplacements.txt", "bc_home/custom/spritecredits.txt",
       "bc_home/custom/opera", "bc_home/remonsterate", "bc/music/samples"]


def bc_source(dst, assets):
    import bc_run
    src = os.path.abspath(bc_run.SRC)
    GB.copytree(src, dst, skip_dirs=BC_SKIP_DIRS, skip_files=list(BC_SKIP_FILES))
    lic = os.path.join(os.path.dirname(src), "LICENSE")
    for cand in (lic, os.path.join(src, "LICENSE"), os.path.join(os.path.dirname(src), "LICENSE.txt")):
        if os.path.exists(cand):
            shutil.copy2(cand, os.path.join(dst, "LICENSE.txt"))
            break


def bc_home(dst, assets):
    """The folder BC works in (bc_run.HOME): the release's custom/ and remonsterate/, BC's config.ini."""
    import bc_run
    home = os.path.abspath(bc_run.HOME)
    os.makedirs(dst, exist_ok=True)
    for f in ("config.ini",):
        if os.path.exists(os.path.join(home, f)):
            shutil.copy2(os.path.join(home, f), os.path.join(dst, f))
    for d in ("custom", "remonsterate"):      # (not our caches there: bc_remon's, made on each machine)
        GB.copytree(os.path.join(home, d), os.path.join(dst, d), skip_dirs={"__pycache__"},
                    skip_files=[".image_sizes.json*", ".prepared_images.pickle*"])


def art(gen, assets):
    """generator/bc_assets.json; a "release" bundle leaves the art out (its sha1 list stays)."""
    import bc_assets
    cfg = {"source": assets}
    if assets == "release":
        cfg["files"] = bc_assets.manifest(gen, ART)
        for rel in ART:
            p = os.path.join(gen, *rel.split("/"))
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.exists(p):
                os.remove(p)
    with open(os.path.join(gen, bc_assets.CONFIG), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=0)
    if assets == "bundle":
        return "art in the bundle"
    return f"art fetched on the player's machine ({len(cfg['files'])} files)"


# pr/data files of other mods (their tools aren't in the bundle, but a shared tool may name them)
OTHER_DATA = ("ted_", "tedition", "_bnw", "snes_event_ted_", "wc_base")


def data_files(gen):
    """pr/data's files the bundled tools name (our correspondence tables: sprite frames, monster boxes and
    colour slots, SNES -> PR maps, chest areas, BC's event data; facts about the game's data, never its
    content), into generator/data."""
    import re
    tools = os.path.join(gen, "tools")
    text = "\n".join(open(os.path.join(tools, f), encoding="utf-8").read() for f in os.listdir(tools) if f.endswith(".py"))
    src = os.path.join(PR, "data")
    taken = []
    for f in sorted(os.listdir(src)):
        if not f.endswith(".json") or any(x in f for x in OTHER_DATA):
            continue
        quoted = r"""["'/\\]""" + re.escape(f) + r"""["']|["']""" + re.escape(f[:-5]) + r"""["']"""
        if re.search(quoted, text):
            shutil.copy2(os.path.join(src, f), os.path.join(gen, "data", f))
            taken.append(f)
    return f"data: {', '.join(taken)}"


def build(out=OUT, dev=False, assets=ASSETS):
    t0 = time.time()
    plugin, magicite = os.path.join(out, "plugin"), os.path.join(out, "magicite", L.MOD)
    if dev:
        os.makedirs(plugin, exist_ok=True)
        write_baseline_data(plugin, magicite)
        GB.no_roms(out)
        print(f"bundle (dev): baseline {GB.size(os.path.join(plugin, 'baseline')) // 1024} KB; Magicite folder "
              f"{GB.size(magicite) // 1024} KB; {time.time() - t0:.0f} s -> {out}")
        return
    import prdata as P
    shutil.rmtree(out, ignore_errors=True)
    gen = os.path.join(plugin, "generator")
    notes = [GB.python_runtime(os.path.join(gen, "python"), packages=["PIL"])]
    needed, total = GB.copy_tools(os.path.join(gen, "tools"), ENTRY_TOOLS, OTHER_MODS)
    notes.append(f"{len(needed)} of {total} tool scripts")
    bc_source(os.path.join(gen, "bc"), assets)
    bc_home(os.path.join(gen, "bc_home"), assets)
    notes.append(art(gen, assets))
    # the flags' labels, modes and port status (bc_seed's guide step reads them; the plugin has its own copy)
    shutil.copy2(os.path.join(PR, "plugin", "BcPlugin", "bc_flags.json"), os.path.join(gen, "bc_flags.json"))
    for d in VANILLA_DIRS:
        GB.copytree(os.path.join(P.VANILLA, d), os.path.join(gen, "vanilla", d), skip_dirs={"__pycache__"})
    for pattern in VANILLA_GLOBS:
        for f in glob.glob(os.path.join(P.VANILLA, pattern), recursive=True):
            rel = os.path.relpath(f, P.VANILLA)
            os.makedirs(os.path.dirname(os.path.join(gen, "vanilla", rel)), exist_ok=True)
            shutil.copy2(f, os.path.join(gen, "vanilla", rel))
    # every map file a seed can change (the generator edits its own copies), the monster boxes' scripts
    import seed_live
    for rel in seed_live.chest_files() + seed_live.empty_chest_files() + seed_live.miab_files() + L.own_files():
        srcf = os.path.join(P.VANILLA, *rel.split("/"))
        if os.path.exists(srcf):
            dst = os.path.join(gen, "vanilla", *rel.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(srcf, dst)
    import port_chests   # the chest folders' sizes (its matcher's tie-break; the bundle has no tilemaps)
    import idmap         # the SNES formation -> PR party map (idmap.party reads every event script: precomputed)
    tools = os.path.join(gen, "tools")
    with open(os.path.join(tools, port_chests.SIZES_FILE), "w", encoding="utf-8") as fh:
        json.dump(port_chests.chest_folder_sizes(), fh)
    with open(os.path.join(tools, idmap.PARTY_FILE), "w", encoding="utf-8") as fh:
        json.dump({str(f): idmap.party(f) for f in range(576)}, fh)
    import bc_music  # bc-music: the SNES -> PR map pairs, compact (BC's area songs: forests, tombs, villages ...)
    bc_music.bundle_data(tools)
    import bnw_text  # the menu font's text table (item/spell text decoding)
    os.makedirs(os.path.join(gen, "data"), exist_ok=True)
    shutil.copy2(bnw_text.VWF_TBL, os.path.join(gen, "data", "vwf.tbl"))
    notes.append(data_files(gen))
    # no SNES ROM in the bundle: the generator is ROM-free, BC's input the ROM's data tables only, made here
    # from the ROM on this machine
    import bc_basedata
    bc_basedata.build(os.path.join(gen, "data", "bc_base.bin"))
    notes.append("ROM-free (data/bc_base.bin)")
    GB.precompile(gen, ["python/Lib", "bc", "tools"])
    notes.append("bytecode precompiled")
    p = subprocess.run([os.path.join(gen, "python", "python.exe"), "-c",
                        "import pr_script, port_chests, bc_live; pr_script.index(); port_chests._scan_chests(); "
                        "print(len(bc_live.managed_files()))"],
                       cwd=tools, check=False, capture_output=True, text=True)
    notes.append(f"vanilla cache: {p.stdout.strip() or p.stderr.strip()[-300:]} managed files")
    # the copies of the game's own files (the Magicite folder, baseline/; generator/vanilla and cache above): made
    # here for a development install, and on a player's machine from their own game (bc_gamedata.py setup, from
    # gamedata.json): the player zip leaves them out. .complete marks this build's copies as made.
    import bc_gamedata
    write_baseline_data(plugin, magicite)
    manifest = bc_gamedata.make_recipe(gen, plugin, magicite)
    with open(os.path.join(gen, "vanilla", bc_gamedata.MARK), "w", encoding="utf-8") as f:
        f.write(manifest["id"])
    notes.append(f"gamedata.json: {len(manifest['files'])} game files for a player's setup")
    GB.no_roms(out)
    parts = {name: GB.size(os.path.join(gen, name)) // (1 << 20) for name in os.listdir(gen) if os.path.isdir(os.path.join(gen, name))}
    # last: the marker that this is a whole player bundle (the Deck tooling looks for it)
    with open(os.path.join(gen, "bundle.json"), "w", encoding="utf-8") as f:
        json.dump({"mod": "BeyondChaos", "version": version(),
                   "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "assets": assets}, f)
    print(f"bundle: {notes[0]}; {'; '.join(notes[1:])}; generator {GB.size(gen) // (1 << 20)} MB {parts}; "
          f"Magicite folder {GB.size(magicite) // 1024} KB; {time.time() - t0:.0f} s -> {out}")


def check(out, seed="1234567890", preset="New Player"):
    """A seed made with the bundled Python alone (fresh environment, ROM-free), = the project's ROM-free seed."""
    gen = os.path.join(out, "plugin", "generator")
    py = os.path.join(gen, "python", "python.exe")
    dest = os.path.join(out, "check_seed")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "VIRTUAL_ENV", "FF6_"))}
    env["PYTHONIOENCODING"] = "utf-8"
    t = time.time()
    p = subprocess.run([py, "-u", os.path.join(gen, "tools", "bc_seed.py"), "--seed", seed, "--preset", preset,
                        "--out", dest], cwd=os.path.join(gen, "tools"), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(p.stdout.strip().splitlines()[-1] if p.stdout.strip() else p.stderr[-1500:])
    ok = p.returncode == 0 and os.path.exists(os.path.join(dest, "bc_seed.json"))
    if ok:
        import prdata as P
        if os.path.exists(P.VANILLA_ROM):
            import bc_parity
            mine = os.path.join(out, "check_seed_project")
            # the bundle's own copy of the tools, run in the project (its Python, pr/vanilla, BC's source there):
            # only the packaging differs (the bundled Python, the game files its setup made, its BC copy), not
            # the code, which other sessions keep editing
            import bc_run
            q = subprocess.run([sys.executable, os.path.join(gen, "tools", "bc_seed.py"), "--seed", seed, "--preset", preset,
                                "--out", mine], cwd=PR,
                               env=dict(os.environ, FF6_BC_ROMFREE="1", PYTHONIOENCODING="utf-8", PYTHONWARNINGS="ignore",
                                        FF6PR_ROOT=PR, FF6_BC_SRC=os.path.abspath(bc_run.SRC),
                                        FF6_BC_HOME=os.path.abspath(bc_run.HOME)),
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            diffs = bc_parity.compare(mine, dest) if q.returncode == 0 else [f"the project's generator failed: {q.stderr[-300:]}"]
            print("bundle parity: " + ("the project's seed folder" if not diffs else "; ".join(diffs[:8])))
            ok = not diffs
            if ok:
                shutil.rmtree(mine, ignore_errors=True)
    print(f"bundle check: {'ok' if ok else 'FAILED (kept: check_seed, check_seed_project)'} ({time.time() - t:.1f} s)")
    if ok:
        shutil.rmtree(dest, ignore_errors=True)
    shutil.rmtree(os.path.join(gen, "mods"), ignore_errors=True)
    GB.clean_bytecode(os.path.join(gen, "tools"))
    return ok


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = os.path.abspath(args[0]) if args else OUT
    build(out, dev="--dev" in sys.argv)
    if "--check" in sys.argv and not check(out):
        sys.exit(1)
