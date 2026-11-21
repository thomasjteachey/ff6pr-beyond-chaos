"""Beyond Chaos's copies of the game's own files, made on the player's machine from their own copy of the game
(the kit's tools/gamedata.py; PORTING.md "Beyond Chaos port", "WC without the game's files"). The mod is
distributed: its zip carries none of the Pixel Remaster's files, as it carries no SNES ROM.

    python tools/bc_gamedata.py setup [--game DIR] [--magicite DIR]    the player's machine (BcPlugin runs it)
    python tools/bc_gamedata.py status                                  exit 0: set up for this manifest
    python tools/bc_gamedata.py recipe <build dir>                      bc_bundle.py, on this PC
    python tools/bc_gamedata.py selftest [<build dir>]                  this PC: setup = the build?

Made: BepInEx/BeyondChaos/generator/vanilla (the PR files the generator's porter reads), generator/cache,
baseline/files and baseline/vanilla_data (bc_live), and the BeyondChaos Magicite folder.
Layout: this file is generator/tools/ (in the bundle) or pr/tools/ (in the project).
"""
import kitpath  # noqa: E402,F401  (the modding kit's tools, when it's this repository's kit/ submodule)
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gamedata as G  # noqa: E402

FOLDER = "BeyondChaos"
LEFT_OUT = ["generator/vanilla", "generator/cache", "baseline/files", "baseline/vanilla_data"]   # = modkit.json
SPEC = G.Spec(FOLDER, LEFT_OUT, script="bc_gamedata.py", title="Beyond Chaos")
MARK = G.MARK


def write_baseline_data(plugin, magicite):
    """The Magicite folder, baseline/files and baseline/vanilla_data, from prdata.VANILLA (bc_live)."""
    import bc_live as L
    L.write_baseline(magicite)
    base = os.path.join(plugin, "baseline")
    for d in ("files", "vanilla_data"):
        shutil.rmtree(os.path.join(base, d), ignore_errors=True)
    for rel in L.managed_files():
        dst = os.path.join(base, "files", *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(magicite, *rel.split("/")), dst)
    for t in L.MANAGED_TABLES:
        table, _ = L.full_table(t)
        dst = os.path.join(base, "vanilla_data", *L.MASTER_PATH.split("/"), t + ".csv")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8", newline="") as f:
            f.write(table.to_csv(table.rows.keys()))
    for m in L.MESSAGE_FILES:
        text, _ = L.full_messages(None, m)
        dst = os.path.join(base, "vanilla_data", *L.MESSAGE_PATH.split("/"), m + ".txt")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8", newline="") as f:
            for k, v in text.items():
                f.write(f"{k}\t{v}\r\n")
    # the story lines a seed changes (bc_data: the Coral's lines at Ebot's Rock), as the game has them
    import bc_data
    import bc_gifts           # + the lines naming each esper gift (`y`)
    import bc_events          # + the opera lines alasdraco rewrites
    dst = os.path.join(base, "vanilla_data", *L.MESSAGE_PATH.split("/"), bc_data.STORY + ".txt")
    with open(dst, "w", encoding="utf-8", newline="") as f:
        for k, v in bc_data.story_lines(sorted(set(bc_data.STORY_KEYS) | set(bc_gifts.story_keys())
                                               | set(bc_events.story_keys()))).items():   # + alasdraco's opera lines
            f.write(f"{k}\t{v}\r\n")


def make_recipe(gen, plugin, magicite):
    return G.make_recipe(SPEC, gen, plugin, magicite)


def status(gen=None):
    return G.status(gen or os.path.dirname(HERE))


if __name__ == "__main__":
    sys.exit(G.main(SPEC, HERE, write_baseline_data,
                    default_build=os.path.join(os.path.dirname(HERE), "build", "BeyondChaos")))
