# Beyond Chaos for FINAL FANTASY VI Pixel Remaster

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
