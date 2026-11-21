"""The public Beyond Chaos repository (ff6pr-beyond-chaos): this project's Beyond Chaos parts, copied into
their own git tree, with the modding kit as its kit/ submodule and Beyond Chaos itself as a submodule.

    .venv/Scripts/python tools/bc_publish.py [OUT]     (default: ../../ff6pr-beyond-chaos)

Copies BC's plugin and its test projects, its tools (tools/bc_*.py: the seed generator around BC's own code,
its ROM-free base, the player bundle, commands, junctions, events, sprites, music), its data (data/bc_*.json;
not data/bc_base.bin, which a developer builds from their own ROM with tools/bc_basedata.py), its checks and
its development log (pr/docs/bc.md) into OUT with the project's layout (pr/...), writes its README,
.gitignore, requirements and manifest, and records two submodules at fixed commits: the kit (ff6pr-kit,
kit/) at the kit repository's current commit (publish and commit the kit first: tools/kit_publish.py), and
Beyond Chaos CE (mods/beyond-chaos/src) at 27de07a, the commit that makes BeyondChaos.exe 6.1.3's seeds.
Nothing of the other mods'; no ROM, no game files, no BC release assets (custom/, remonsterate/: the player
bundle fetches or carries them). OUT's .git is left alone: commit and push from there. The checks are
tools/repo_publish.py's.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401  (the modding kit's tools, when it's this repository's kit/ submodule)
import repo_publish as R  # noqa: E402

DEFAULT_OUT = os.path.join(os.path.dirname(R.PROJECT), "ff6pr-beyond-chaos")
BC_URL = "https://github.com/FF6BeyondChaos/BeyondChaosRandomizer.git"
BC_COMMIT = "27de07a012640ed297b36f94e81bdd8128f3c3b1"   # main, "Update version to 6.1.3": = BeyondChaos.exe 6.1.3
PLUGINS = ("pr/plugin/BcPlugin", "pr/plugin/Bc.Tests", "pr/plugin/BcBattle.Tests", "pr/plugin/BcJunction.Tests")


def parts():
    out = [("pr/tools", ["bc_*.py", "kitpath.py"]),
           ("pr/data", ["bc_*.json"]),          # BC's own data (no PR colours: those are paired with the player's game)
           ("pr/docs", ["bc.md"])]               # its development log (split out of PORTING.md, 2026-11-20)
    for folder in PLUGINS:
        if os.path.isdir(os.path.join(R.PROJECT, *folder.split("/"))):
            out.append((folder, ["**"]))
    tests = sorted(f for f in os.listdir(os.path.join(R.PR, "tests")) if f.startswith("test_bc"))
    if tests:
        out.append(("pr/tests", tests))
    return out


README = """# Beyond Chaos for FINAL FANTASY VI Pixel Remaster

[Beyond Chaos CE](https://github.com/FF6BeyondChaos/BeyondChaosRandomizer) 6.1.3, the Final Fantasy VI
randomizer, ported to the Steam Pixel Remaster as a mod of its own: seeds and flags are chosen in the
game and made in seconds by Beyond Chaos's own code, so a seed number gives the same game as
BeyondChaos.exe 6.1.3 and players can share seeds. Its custom commands, item specials, junction
effects, codes, events, character and monster sprites and music come along. **In development: there
is no release yet.**

## How it works

- `kit/`: the [modding kit](https://github.com/thomasjteachey/ff6pr-kit) (a submodule): the porter that
  turns an FF6 ROM into Pixel Remaster data, the seed system, the SNES battle rules, the SNES music
  player and sprite tools BC uses.
- `mods/beyond-chaos/src`: Beyond Chaos CE at commit 27de07a (a submodule), run as BeyondChaos.exe runs it.
- `pr/tools/bc_seed.py`: makes a seed (Beyond Chaos's randomizer, then the porter and BC's own steps) into a
  seed folder the plugin applies live; `bc_bundle.py` builds the player's generator (bundled Python, no ROM).
- `pr/plugin/BcPlugin`: the BepInEx plugin (the Beyond Chaos screen, live seeds, commands, junctions,
  codes, events, art and music in game).
- `pr/docs/bc.md`: the development log (status, plan, decisions); the project-wide status table is the
  kit's `kit/pr/PORTING.md`.

## Build

Needs Windows, FF6 PR with BepInEx 6 and Magicite installed, .NET 6 SDK, Python 3.12 and the US v1.0 SNES
ROM (`rom/vanilla/`). None of these are in this repository; players need no ROM.

    git clone --recurse-submodules <this repo>
    cd pr && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
    .venv/Scripts/python ../kit/pr/tools/extract.py --game "<your FF6 PR folder>"   # pr/vanilla
    .venv/Scripts/python tools/bc_basedata.py build                                 # data/bc_base.bin from your ROM
    .venv/Scripts/python tools/bc_seed.py --seed 9859608359 --preset "New Player" --out build/seed
    cd plugin/BcPlugin && dotnet build -c Release

## Credits

Beyond Chaos by Abyssonym, and Beyond Chaos CE by its community maintainers and contributors (MIT); its
sprite and music packs by their artists and arrangers. BepInEx, Il2CppInterop, HarmonyX, Magicite by
Silvris. FINAL FANTASY VI is Square Enix's; this is an unofficial fan mod.
"""


def main():
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT)
    entries = list(R.collect(parts()))
    texts = {"README.md": README,
             ".gitignore": R.GITIGNORE_COMMON + "mods/beyond-chaos/CE-6.1.3/\n",
             "pr/requirements.txt": R.REQUIREMENTS, "pr/modkit.json": R.manifest(keep=("bc",))}
    done = R.write(out, entries, texts, submodules=[("kit", R.KIT_URL, R.head(R.KIT_REPO)),
                                                    ("mods/beyond-chaos/src", BC_URL, BC_COMMIT)])
    print(f"Beyond Chaos publish: {done} -> {out}")


if __name__ == "__main__":
    main()
