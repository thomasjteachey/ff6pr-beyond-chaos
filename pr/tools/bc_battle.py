"""Beyond Chaos's battle side at seed time (bc-battle): what the plugin's battle code reads from a seed, into
its own file bc_battle.json beside bc_seed.json (plugin/BcPlugin/BcBattleData.cs reads it). bc_seed.py runs
apply() after the port, with BC's output ROM (read, never written: BC's draws are BC's) and its spoiler log.

Sections (each a tool's):
  data         seed-time data that needs BC's ROM, written into the seed's tables (tools/bc_codes.py rom_data:
               natural magic as BC teaches it); the section records what it did
  encounters   BC's random-battle rules from its ROM (tools/port_encounter_rates.py: rate tables, codes, roll,
               party odds), for the kit's SNES encounter counter (BcCodes.cs: PrKit/Ff6/SnesEncounters);
               dearestmolulu is these tables
  codes        the small codes that are plugin code (tools/bc_codes.py plugin_part)
  items        item specials the PR's tables can't hold (tools/bc_items.py battle_part)
  junction     junction effects (tools/bc_junction.py)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
import prdata as P  # noqa: E402

FILE = "bc_battle.json"


def encounters(rom, log):
    import ff6snes as S
    import port_encounter_rates as R
    return R.rules(S.Rom(P.VANILLA_ROM), S.Rom(rom), "bc", log)


def apply(out, rom, spoiler, flags, log=print):
    """Write bc_battle.json in the seed folder `out`; returns {section: size} for bc_seed.json."""
    import bc_codes
    import bc_items
    data, done = {}, {}
    parts = [("data", lambda: bc_codes.rom_data(out, rom, flags, log)),
             ("encounters", lambda: encounters(rom, log)),
             ("codes", lambda: bc_codes.plugin_part(out, rom, spoiler, flags, log)),
             ("items", lambda: bc_items.battle_part(out, rom, spoiler, flags, log))]
    try:
        import bc_junction
        parts.append(("junction", lambda: bc_junction.battle_part(out, rom, spoiler, flags, log)))
    except ImportError:
        pass
    for name, make in parts:
        try:
            part = make()
        except Exception as e:  # noqa: BLE001 - the seed still plays without this part
            import traceback
            log(traceback.format_exc())
            log(f"bc battle: {name} not made: {e}")
            continue
        if part:
            data[name] = part
            done[name] = len(part) if hasattr(part, "__len__") else 1
    with open(os.path.join(out, FILE), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, separators=(",", ":"))
    log(f"bc battle: {FILE}: {', '.join(f'{k} {v}' for k, v in done.items()) or 'nothing'}")
    return done
