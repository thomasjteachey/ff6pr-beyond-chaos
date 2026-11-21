"""Beyond Chaos seeds in a running game: what a seed may change, and the BeyondChaos Magicite
folder's baseline (the kit's tools/seed_live.py: master tables and text set live, chest maps, AI
slots and battle_extra_data swapped through Magicite). Used by bc_seed.py and the deploy/bundle.

  .venv/Scripts/python tools/bc_live.py baseline OUT_DIR   # the BeyondChaos Magicite folder
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401  (the modding kit's tools, when it's this repository's kit/ submodule)
import seed_live  # noqa: E402
from seed_live import (MESSAGE_FILES, AI_SLOTS, MASTER_PATH, MESSAGE_PATH,  # noqa: E402,F401
                       full_table, full_messages)

# the shared porter's tables, and the command table: BC's replaced commands are their PR command
# rows (tools/bc_commands.py), so every seed carries the whole table and undoes the last one's
# + BC's starting gil (bc_data: initialize_data) and bc-events' new scripts' rows (script: ids 9200-9299, mimetime)
MANAGED_TABLES = sorted(set(seed_live.MANAGED_TABLES) | {"command", "initialize_data", "script"})

MOD = "BeyondChaos"          # the Magicite folder (StreamingAssets/Magicite/BeyondChaos)
BASELINE = "bc_baseline.json"


def own_files():
    """Whole data files only Beyond Chaos's seeds change: the Veldt's table (its formations' monsters
    change with the seed's: port_veldt, the misc asset), the seed's guide (tools/bc_guide.py: its
    script in the opening's last map; the game has no such file, the baseline's shows nothing) and the
    scripts and map files BC's light events change (tools/bc_events.py)."""
    import port_veldt as V
    import bc_guide as G
    import bc_events
    import bc_gifts           # BC's event gifts (`t`): the scripts that give them
    events = bc_events.files()
    shared = set(events) | set(seed_live.managed_files())
    return [f"{V.GROUP}/{V.ASSET}.json", G.GUIDE_REL] + events + [f for f in bc_gifts.files() if f not in shared]


def managed_files():
    return seed_live.managed_files() + own_files()


def write_baseline(out):
    """The BeyondChaos Magicite folder: every file a seed may change, vanilla content."""
    def extra(out, add):
        import json
        import shutil
        import port_veldt as V
        import bc_guide as G
        import pr_script
        import bc_events
        events = set(bc_events.files())
        for rel in own_files():
            if rel in events:
                continue          # bc_events.write_baseline below
            dest = os.path.join(out, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if rel == G.GUIDE_REL:
                G.write_script(dest, 0)   # no seed: a guide with nothing to say
                add(rel)
            else:
                shutil.copyfile(os.path.join(seed_live.P.VANILLA, *rel.split("/")), dest)
        os.makedirs(os.path.join(out, V.GROUP, "keys"), exist_ok=True)
        with open(os.path.join(out, V.GROUP, "keys", "mod_misc.json"), "w", encoding="utf-8") as f:
            json.dump({"keys": [V.KEY], "values": [V.ASSET]}, f, indent=2)
        # the guide in its map's script list (a map runs only the scripts its package lists)
        pr_script.list_in_map(out, G.GUIDE_GROUP, G.GUIDE_FOLDER, G.GUIDE_SUB, [G.GUIDE_SCRIPT])
        add(f"{G.GUIDE_GROUP}/Assets/GameAssets/Serial/Res/Map/{G.GUIDE_FOLDER}/package.json")
        bc_events.write_baseline(out, add)    # its files as vanilla's (its own scripts: Exit only), listed in their maps
    files = seed_live.write_baseline(out, extra=extra, baseline_name=BASELINE, files=managed_files())
    import json
    with open(os.path.join(out, BASELINE), "w", encoding="utf-8") as f:
        json.dump({"tables": MANAGED_TABLES, "messages": MESSAGE_FILES, "files": files}, f, indent=1)
    return files


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "baseline":
        write_baseline(os.path.abspath(sys.argv[2]))
    else:
        sys.exit(__doc__)
