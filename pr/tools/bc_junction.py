"""Beyond Chaos's junction effects at seed time (bc-junction): which effect BC gave each esper, piece of
equipment, relic, monster, status and character, read back from BC's own output (no draws of ours: a seed
stays BC's exe's seed), into bc_battle.json's "junction" section for plugin/BcPlugin/BcJunction*.cs.

Flags (BC's options.py, "experimental"):
  espffect     espers          BC's randomize_generous over the 27 espers (1-3 effects each)
  effectmas    equipment       randomize_sparing over weapons, shields, helmets, armor (~37% get 1-3)
  effectory    relics          the same over relics
  effectster   monsters        randomize_sparing over monsters (more likely the higher their level; not the
                               early and solo bosses) + randomize_generous over 4 statuses (Morph, Imp,
                               Zombie, Dance: whoever has one has its effects, party members too)
  treaffect    monsters' items a monster has the effects of the items it can still be stolen (in battle) and
                               of its drops; bosses are blacklisted from them
  jejentojori  innate relics   a character's innate relic (mementomori) keeps its effects
  espercutegf  (summoner mode, not one of the six) puts EspMag/EspCntr/EspAtk/EspDef/Caller on the always list

How BC stores them (bcg_junction.py populate_data, tables/bcg_junction_manifest.json): per category a table of
16-bit pointers (one per index, bank 0x61 of the ROM file) to zero-terminated sorted lists of junction
indexes, white and black. Who has an effect (patch_junction_core.txt jun-checker, the rule this mirrors):
  a character: always, its character list, its equipped esper, each of its six equipment slots, each status
               it has, the monster it is Raging as; minus the blacklists of the same (not Rage's)
  a monster:   always, the every-monster list (index 0x180), the items it holds (the two it can still be
               stolen, then its two drops, with treaffect), its own list, each status it has; minus the
               every-monster/items/own/status blacklists
  and then a Junction Jammer roll: a random living combatant; if it has Junction Jammer, the check fails.

  python tools/bc_junction.py ROM_OR_SEED_OUTPUT [--log BC_LOG]    prints the record (and checks it against
                                                                   BC's spoiler-log JUNCTIONS section)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401

FLAGS = ("espffect", "effectmas", "effectory", "effectster", "treaffect", "jejentojori", "espercutegf")

# populate_everything's categories: (name, max index)
CATEGORIES = (("character", 0xF), ("esper", 0x1F), ("equip", 0xFF), ("status", 0x1F), ("monster", 0x1FF))
EVERY_MONSTER = 0x180
# SNES status order (BC's status_names: $3EE4 bits 0-15, then $3EF8 bits 0-15)
STATUS_NAMES = ["Blind", "Zombie", "Poison", "Magitek", "Clear", "Imp", "Petrify", "Wound", "Condemned",
                "Near Fatal", "Image", "Mute", "Berserk", "Muddled", "Seizure", "Sleep", "Dance", "Regen", "Slow",
                "Haste", "Stop", "Shell", "Safe", "Reflect", "Rage", "Freeze", "Life 3", "Morph", "Control",
                "Hide", "Intercept", "Float"]
# BC's vanilla-code parameters its patches re-emit (randomizer.JUNCTION_MANAGER_PARAMETERS), found in the
# patches' code: (where the patch starts, the bytes before the CMP's operand)
MORPHER = (0x621580, bytes.fromhex("b9d83ec9"))     # patch_junction_double_ap main: LDA $3ED8,Y; CMP #<morpher>
BERSERKER = (0x621A40, bytes.fromhex("48dac9"))      # patch_junction_focus_umaro: PHA; PHX; CMP #<berserker>


def manifest():
    import bc_run
    with open(os.path.join(bc_run.SRC, "tables", "bcg_junction_manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def catalog(man=None):
    """{junction index: key} from BC's manifest (173 effects, 0x01-0xAE)."""
    man = man or manifest()
    return {int(v, 16): k for k, v in man["junction_indexes"].items()}


def _list(data, address, index):
    """The zero-terminated junction list for `index` of the table at file offset `address`."""
    p = int.from_bytes(data[address + index * 2:address + index * 2 + 2], "little")
    at = (address & 0xFF0000) | p
    out = []
    while at < len(data) and data[at] != 0:
        out.append(data[at])
        at += 1
    return out


def _table(data, address, max_index):
    """{index: [junction indexes]} for one of BC's tables (empty lists left out); None when there's no table
    (the pointers must all point inside the bank, past the table, at one shared empty list)."""
    end = address + (max_index + 1) * 2
    pointers = [int.from_bytes(data[address + i * 2:address + i * 2 + 2], "little") for i in range(max_index + 1)]
    if not any(pointers) or any((address & 0xFF0000) | p < end for p in pointers):
        return None
    return {i: lst for i in range(max_index + 1) if (lst := _list(data, address, i))}


def read(data, man=None):
    """BC's junction lists from its output ROM bytes: {"always": [...], "<category>": {"white": {i: [..]},
    "black": {i: [..]}}, "steal": bool, "drop": bool, "morpher": n, "berserker": n} by BC's own indexes
    (SNES ids), or None when the seed has no junctions (BC wrote no tables)."""
    man = man or manifest()
    num = lambda k: int(man[k], 16)  # noqa: E731
    always = _table(data, num("always_whitelist_address"), 0)
    if always is None:
        return None
    rec = {"always": always.get(0, [])}
    for cat, max_index in CATEGORIES:
        rec[cat] = {}
        for color in ("white", "black"):
            t = _table(data, num(f"{cat}_{color}list_address"), max_index)
            if t is None:
                return None
            rec[cat][color] = t
    g = {k: int(v, 16) for k, v in man["global_addresses"].items()}
    rec["steal"] = bool(data[g["monster-equip-steal-enabled"]]) if "monster-equip-steal-enabled" in g else False
    rec["drop"] = bool(data[g["monster-equip-drop-enabled"]]) if "monster-equip-drop-enabled" in g else False
    for key, (start, before) in (("morpher", MORPHER), ("berserker", BERSERKER)):
        at = data.find(before, start, start + 0x80)
        rec[key] = data[at + len(before)] if at >= 0 else None
    return rec


# --- the record in the PR's ids ---------------------------------------------------------------------------

def _keys(indexes, cat):
    return [cat[j] for j in indexes if j in cat]


def pr_record(rec, man=None, log=print):
    """read()'s record by the PR's ids and junction keys, for the plugin:
      always: [key]
      characters / espers / equipment / statuses / monsters: {pr id: {"has": [key], "not": [key]}}
        characters by PR character id (SNES actor + 1), espers by the esper's content id, equipment by the
        item's content id (what OwnedCharacterData's slots and a monster's steal/drop rows hold), statuses
        by BC's status index (STATUS_NAMES; BcJunction maps them to the PR's conditions), monsters by PR
        monster id (SNES + 1)
      every_monster: {"has": [key], "not": [key]}
      monster_items: {"steal": bool, "drop": bool}   (treaffect)
      morpher, berserker: BC's Morph and Umaro slots (SNES actor ids)"""
    import idmap
    cat = catalog(man)
    out = {"always": _keys(rec["always"], cat)}

    def side(category, to_id):
        d = {}
        for color, word in (("white", "has"), ("black", "not")):
            for i, lst in rec[category][color].items():
                if category == "monster" and i == EVERY_MONSTER:
                    continue
                pid = to_id(i)
                if pid is None:
                    if lst:
                        log(f"bc junction: {category} {i}: no PR row for {_keys(lst, cat)}")
                    continue
                keys = _keys(lst, cat)
                if keys:
                    d.setdefault(str(pid), {}).setdefault(word, []).extend(keys)
        return d

    out["characters"] = side("character", idmap.character)
    out["espers"] = side("esper", lambda i: idmap.esper_content(i) if i < 27 else None)
    out["equipment"] = side("equip", lambda i: idmap.item_content(i) or None)
    out["statuses"] = side("status", lambda i: i if i < len(STATUS_NAMES) else None)
    out["monsters"] = side("monster", lambda i: idmap.monster(i) if i < EVERY_MONSTER else None)
    every = {}
    for color, word in (("white", "has"), ("black", "not")):
        keys = _keys(rec["monster"][color].get(EVERY_MONSTER, []), cat)
        if keys:
            every[word] = keys
    out["every_monster"] = every
    out["monster_items"] = {"steal": rec["steal"], "drop": rec["drop"]}
    out["morpher"], out["berserker"] = rec["morpher"], rec["berserker"]
    return out


SPELLS = 0x046AC0     # the SNES spell table (C4/6AC0), 14 bytes a spell; an esper's summon = spell 0x36 + esper
ESPER_DATA = 0x186E00  # D8/6E00: 11 bytes an esper: 5 x (learn rate, spell), level-up bonus
# the SNES spells and items BC's junction effects cast or use (bcg patches), by the name BcJunction*.cs knows them
TRIGGER_SPELLS = {"haste": 0x1F, "bserk": 0x21, "float": 0x22, "vanish": 0x26, "warp": 0x2A, "quick": 0x2B,
                  "cure3": 0x2F, "remedy": 0x33, "regen": 0x34, "life3": 0x35, "golem": 0x4C, "fenrir": 0x4E,
                  "phoenix": 0x50, "fire": 0x00, "spiraler": 0x63, "revenge": 0x92, "rippler": 0x9E,
                  "chokesmoke": 0xA6, "escape": 0xC2, "colddust": 0xCF, "hyperdrive": 0xD1, "discard": 0xDB,
                  "lagomorph": 0xFE}
TRIGGER_ITEMS = {"superball": 0xFA, "potion": 0xE9, "fenix": 0xF0, "holywater": 0xF1, "antidote": 0xF2,
                 "eyedrop": 0xF3, "soft": 0xF4, "remedy": 0xF5, "greencherry": 0xF8, "echoscreen": 0xFB}


def spell_foe(data, sid):
    """BC's enemy-type test for a spell (esper_magic): its targeting byte has $40 (aims at foes) or $80/$04."""
    t = data[SPELLS + sid * 14]
    return bool(t & 0x40) or bool(t & 0x84)


def triggers(data):
    """{"spells": {name: PR ability}, "items": {name: content id}} for the effects' casts."""
    import idmap
    # Gaia Assist: the dance steps (SNES spells 101-124) that aim at allies (BC: targeting bit 1 set, bits 6-7 clear)
    ally_steps = [idmap.spell(sid) for sid in range(101, 125)
                  if idmap.spell(sid) and (data[SPELLS + sid * 14] & 0x02) and not (data[SPELLS + sid * 14] & 0xC0)]
    return {"spells": {k: idmap.spell(v) for k, v in TRIGGER_SPELLS.items() if idmap.spell(v)},
            "items": {k: idmap.item_content(v) for k, v in TRIGGER_ITEMS.items()},
            "dance_ally_steps": ally_steps, "salve_items": salve_items(data)}


ITEM_DATA = 0x185000   # D8/5000: 30 bytes an item; byte 0 & 7 = 6 an "Item", byte 0x0E its targeting


def salve_items(data):
    """Salve: the consumables a holder may aim at the whole party (BC: "Item" type, not aimed at foes by default;
    here the single-target ones, as content ids)."""
    import idmap
    out = []
    for i in range(0xE8, 0xFF):
        d = data[ITEM_DATA + i * 30:ITEM_DATA + i * 30 + 30]
        if len(d) == 30 and d[0] & 7 == 6 and not d[0x0E] & 0x40 and d[0x0E] & 0x01:
            cid = idmap.item_content(i)
            if cid:
                out.append(cid)
    return out
ELEMENT_ATTR = [1, 2, 3, 6, 8, 7, 4, 5]   # SNES element bit -> PR attribute id (tools/port_resist.py ELEM_ATTR)


def protect_ids(statuses):
    """BC status indexes -> the PR condition ids a character is made immune to (the porter's tables:
    tools/port_resist.py PROTECT for status bytes 1-2, ENEMY_IMMUNE for byte 3)."""
    import port_resist as R
    ids = []
    for i in statuses:
        for c in R.PROTECT.get(i, []) + R.ENEMY_IMMUNE.get(i, []):
            if c not in ids:
                ids.append(c)
    return ids


def esper_info(data):
    """What Esper Attack / Esper Defense read from each esper's summon in BC's ROM, by the esper's content id:
    elements (PR attribute ids), statuses it sets (BC status indexes), foe (aimed at enemies by default),
    lift (it removes statuses), summon (the PR's summon ability)."""
    import idmap
    out = {}
    for e in range(27):
        s = data[SPELLS + (0x36 + e) * 14:SPELLS + (0x37 + e) * 14]
        if len(s) < 14:
            continue
        status_bits = int.from_bytes(s[0x0A:0x0C], "little") | (int.from_bytes(s[0x0C:0x0E], "little") << 16)
        cid = idmap.esper_content(e)
        if cid is None:
            continue
        ed = data[ESPER_DATA + e * 11:ESPER_DATA + e * 11 + 10]
        spells = [[ed[k * 2], idmap.spell(ed[k * 2 + 1]), spell_foe(data, ed[k * 2 + 1])]
                  for k in range(5) if ed[k * 2 + 1] != 0xFF and ed[k * 2] and idmap.spell(ed[k * 2 + 1])]
        statuses = [i for i in range(32) if status_bits & (1 << i)]
        out[str(cid)] = {"spells": spells, "elements": [ELEMENT_ATTR[b] for b in range(8) if s[1] & (1 << b)],
                         "protect": protect_ids(statuses),
                         "statuses": [i for i in range(32) if status_bits & (1 << i)],
                         "foe": bool(s[0] & 0x40), "lift": bool(s[4] & 0x04),
                         "summon": idmap._ESPERS[e], "esper": e}
    return out


# --- names in the Pixel Remaster's words --------------------------------------------------------------------
# BC's short names (junction_short_names) cut to its 12-character menus, with the SNES's words: Bolt, Bio,
# Pearl, Warp, Cure 3, Remedy (the spell), Life 3, Morph, GP Rain. The PR's: Lightning, Poison, Holy, Teleport,
# Curaga, Esuna, Reraise, Trance, Gil Toss. The SOS command effects take the seed's command in that slot
# (BC: "SOS " + the command's name there).
WORDS = [("Bolt", "Lightning"), ("Bio", "Poison"), ("Pearl", "Holy"), ("Phys ", "Physical "),
         ("SOS Warp", "SOS Teleport"), ("SOS Cure 3", "SOS Curaga"), ("SOS Remedy", "SOS Esuna"),
         ("SOS Life 3", "SOS Reraise"), ("Auto-Life 3", "Auto-Reraise"), ("SOS Morph", "SOS Trance"),
         ("Auto-Vivify", "Auto-Revivify"), ("Rflect", "Reflect"), ("Junction Jam", "Junction Jammer")]
OWN_NAMES = {"esper_magic": "Esper Magic", "esper_defense": "Esper Defense", "esper_counter": "Esper Counter",
             "esper_attack": "Esper Attack", "null_freeze": "Null Freeze", "null_sleep": "Null Sleep"}
# the commands BC's SOS effects use, by PR command id (BC renames these after the seed's command in the slot)
SOS_COMMANDS = {"critical_gprain": 21, "critical_runic": 16, "critical_dance": 22}


def names(man=None, command_names=None):
    """{key: name in the PR's words}; command_names: {PR command id: the seed's name} for the SOS commands."""
    man = man or manifest()
    out = {}
    for key, short in man["junction_short_names"].items():
        name = OWN_NAMES.get(key)
        if name is None:
            name = short
            for a, b in WORDS:
                name = name.replace(a, b)
        if key in SOS_COMMANDS and command_names and command_names.get(SOS_COMMANDS[key]):
            name = "SOS " + command_names[SOS_COMMANDS[key]]
        out[key] = name
    return out


def used(part):
    """Every junction key a record gives someone (its whitelists)."""
    keys = set(part.get("always", []))
    for k in ("characters", "espers", "equipment", "statuses", "monsters"):
        for v in part.get(k, {}).values():
            keys.update(v.get("has", []))
    keys.update(part.get("every_monster", {}).get("has", []))
    return keys


def battle_part(out, rom, spoiler, flags, log=print):
    """bc_battle.json's "junction" (tools/bc_battle.py runs it after the port; `rom` is BC's output, read only)."""
    on = {f.split(":")[0] for f in flags.split()}
    if not on & set(FLAGS):
        return None
    import ff6snes as S
    man = manifest()
    rec = read(S.rom_bytes(rom), man)
    if rec is None:
        log("bc junction: flags on but BC wrote no junction tables")
        return None
    data = S.rom_bytes(rom)
    part = pr_record(rec, man, log)
    part["flags"] = sorted(on & set(FLAGS))
    part["esper_info"] = esper_info(data)
    part.update(triggers(data))
    keys = used(part)
    log(f"bc junction: {len(keys)} effects in use; espers {len(part['espers'])}, equipment {len(part['equipment'])}, "
        f"monsters {len(part['monsters'])}, statuses {len(part['statuses'])}, characters {len(part['characters'])}, "
        f"always {len(part['always'])}")
    if spoiler:
        bad = check_log(rec, spoiler, man)
        if bad:
            log(f"bc junction: {len(bad)} differences from BC's log: {bad[:5]}")
    try:
        part["names"] = {k: v for k, v in describe(out, part, man, log).items() if k in keys}
    except Exception as e:  # noqa: BLE001 - the effects still work without the words
        import traceback
        log(traceback.format_exc())
        log(f"bc junction: descriptions not written: {e}")
    return part


# --- words: each holder's description, and what each effect does ------------------------------------------
MAX_TEXT = 150     # bc_items' limit for a description (about the box's two lines)


def describe(out, part, man=None, log=print):
    """Adds "Junction: <names>." to each esper's and each piece of equipment's description in the seed's
    system_en (after bc_items' "Changed: ..."; the shared summon/esper description for espers), with the effect's
    one-line explanation when there's room. Returns {key: name} for the seed's effects."""
    import bc_commands
    import seed_live as L
    path = os.path.join(out, *L.MESSAGE_PATH.split("/"), "system_en.txt")
    if not os.path.exists(path):
        return names(man)
    _, msg = bc_commands._messages(out)
    t = bc_commands._tables(out, ["content", "command"])
    cmd_names = {}
    for cid, r in t["command"].rows.items():
        cmd_names[int(cid)] = re.sub(r"<[^>]+>", "", msg.get(r["mes_id_name"], "")).strip()
    nm = names(man, cmd_names)
    rows = t["content"].rows
    done = 0
    for side in ("espers", "equipment"):
        for cid, lists in part.get(side, {}).items():
            keys = [k for k in lists.get("has", []) if k not in set(lists.get("not", []))]
            row = rows.get(int(cid))
            if not keys or not row or row.get("mes_id_description") in (None, "None", ""):
                continue
            key = row["mes_id_description"]
            was = msg.get(key, "")
            text = junction_text(keys, nm, was)
            if text != was:
                msg[key] = text
                done += 1
    with open(path, "w", encoding="utf-8", newline="") as f:
        for k, v in msg.items():
            f.write(f"{k}\t{v}\r\n")
    log(f"bc junction: {done} descriptions name their junction effects")
    return nm


def junction_text(keys, nm, was):
    """The description with its junction effects: "<was> Junction: Fire Boost (...)." trimmed to MAX_TEXT
    (the explanation first, then the old description go when there's no room; the names always stay)."""
    names_only = "Junction: " + ", ".join(nm.get(k, k) for k in keys) + "."
    one = BLURBS.get(keys[0]) if len(keys) == 1 else None
    for text in ([f"{was} Junction: {nm.get(keys[0], keys[0])} ({one})."] if one and was else []) + \
                ([f"Junction: {nm.get(keys[0], keys[0])}: {one}."] if one else []) + \
                ([f"{was} {names_only}"] if was else []) + [names_only]:
        if len(text) <= MAX_TEXT:
            return text
    return names_only


# one line each, the player's words: what the effect does for whoever has it (filled from the spec,
# pr/build/bc_junction/spec_*.json; guide pages and short descriptions use them)
BLURBS = {
    "esper_magic": "after an attack, may cast one of the equipped esper's spells (its learning rate in 64)",
    "junction_jammer": "while anyone on the field has it, any junction effect can fail at random",
    "taunt": "draws enemies' single-target attacks (a party member only half the time)",
    "initiative": "starts every battle with a full ATB gauge",
    "instant_run": "escapes at once when the party flees",
    "instant_act": "acts with no wait after choosing a command",
    "salve": "an item it uses can be aimed at the whole party",
    "focus": "keeps control of its commands while Confused, Berserk, dancing or raging",
    "lucid_dead": "keeps control of its commands as a Zombie",
    "blood_mage": "MP is HP / 8; spells cost 8 HP per MP, and its MP-cost heals don't heal itself",
    "gold_mage": "MP is gil / 32; spells cost 32 gil per MP",
    "reflect_boost": "reflected spells hit harder (x1.25 for each extra holder involved)",
    "null_reflect": "its spells are never reflected",
    "poach": "monsters it kills with Attack drop an item at once",
    "imp_harvest": "Imp monsters it kills with Attack drop their rare item",
    "critical_haste": "casts Haste on itself the first time it falls to Near Death in a battle",
    "critical_bserk": "casts Berserk on itself the first time it falls to Near Death",
    "critical_float": "casts Float on itself the first time it falls to Near Death",
    "critical_vanish": "casts Vanish on itself the first time it falls to Near Death",
    "critical_warp": "casts Teleport on itself (leaves the battle) the first time it falls to Near Death",
    "critical_quick": "casts Quick on itself the first time it falls to Near Death",
    "critical_cure3": "casts Curaga on itself the first time it falls to Near Death",
    "critical_remedy": "casts Esuna on itself the first time it falls to Near Death",
    "critical_regen": "casts Regen on itself the first time it falls to Near Death",
    "critical_life3": "casts Reraise on itself the first time it falls to Near Death",
    "critical_golem": "summons Golem the first time it falls to Near Death",
    "critical_fenrir": "summons Fenrir (Blink) on itself the first time it falls to Near Death",
    "critical_rabbit": "casts Mysidian Rabbit on itself the first time it falls to Near Death",
    "critical_freeze": "freezes itself the first time it falls to Near Death",
    "add_steal": "half its attacks also try to steal",
    "critical_escape": "flees the battle the first time it falls to Near Death",
    "critical_morph": "uses Trance the first time it falls to Near Death",
    "critical_runic": "takes up Runic the first time it falls to Near Death",
    "critical_defend": "defends the first time it falls to Near Death",
    "critical_dance": "dances the first time it falls to Near Death",
    "leech": "heals as much as enemies lose to Poison and Sap",
    "sneeze_guard": "can't be removed from battle by enemies (Snort, Sneeze)",
    "critical_gprain": "throws gil the first time it falls to Near Death",
    "critical_esper": "summons its esper the first time it falls to Near Death",
    "critical_jump": "jumps the first time it falls to Near Death",
    "meatbone_cut": "at Near Death, answers a hit with Revenge",
    "boost_crit": "critical hits deal x1.5 more",
    "loner": "deals more the fewer allies stand (x2 alone, x0.5 with four)",
    "crisis_arm": "damage x the last digit of its HP / 4",
    "double_ap": "earns double AP (at most 255)",
    "dog": "an attack aimed at it alone is blocked half the time, as by Interceptor",
    "miasma": "speeds up everyone's Poison",
    "regenerator": "starts battles with Regen, which ticks more often",
    "reverse": "its healing hurts and its damage heals",
    "heal_boost": "its healing x1.5",
    "gilgam_heart": "the party gets 1 gil for each HP it loses",
    "deaths_door": "its instant-death spells that miss deal its missing HP instead",
    "commander": "keeps allies in control of their commands while Confused or Berserk",
    "necromancer": "keeps Zombie allies in control of their commands",
    "potent_venom": "its Poison attacks poison even the immune, half the time",
    "innate_runic": "always soaks up spells as Runic does",
    "null_freeze": "can't be hit while Frozen",
    "precision": "its attacks on everyone spare its own side",
    "faith": "spells between it and others ignore magic evasion",
    "boost_esper": "its summons x1.5",
    "boost_phys": "its physical attacks x1.5",
    "phys_font": "everyone's physical attacks x1.25",
    "phys_sink": "everyone's physical attacks x0.75",
    "boost_nuke": "its non-elemental spells x1.5",
    "nuke_font": "everyone's non-elemental spells x1.25",
    "nuke_sink": "everyone's non-elemental spells x0.75",
    "repel_nuke": "non-elemental spells bounce off it as if it had Reflect",
    "freebie": "a quarter of the items it uses aren't used up",
    "chemist": "its items work twice as well",
    "nihopalaoa": "its healing items hurt instead",
    "heal_font": "everyone's healing x1.25",
    "heal_sink": "everyone's healing x0.75",
    "ravenous": "drains 25% more, past its own max",
    "victory_cry": "fully restored, ailments cured, at the end of a won battle",
    "firestarter": "casts Fire to thaw a frozen ally",
    "auto_reraise": "starts battles with Reraise",
    "camouflage": "enemies aiming at it alone hit an ally instead",
    "catch": "thrown weapons do it no harm (and it sometimes catches one)",
    "esper_defense": "immune to its esper's element; starts with its esper's helpful statuses",
    "prism_wall": "non-elemental spells that ignore defense take a random element for Repel",
    "unlimited": "desperation attacks come more often and again",
    "mp_switch": "half the hits on it take MP instead of HP",
    "mp_regen": "Regen restores MP (and Sap drains MP) instead of HP",
    "astral": "its attacks hit MP instead of HP",
    "vorpal": "its physical attacks ignore defense",
    "brace": "takes half damage while defending",
    "auto_potion": "drinks a Potion when hit",
    "auto_down": "uses a Phoenix Down on a fallen ally",
    "auto_revivify": "uses an item to cure an ally's Zombie",
    "auto_remedy": "uses an item to cure an ally's ailment",
    "counter_all": "counterattacks a quarter of the attacks on it",
    "hamedo": "half the attacks on it miss and are answered at once",
    "return_magic": "casts spells aimed at it back at the caster",
    "esper_counter": "answers attacks with one of its esper's spells",
    "damage_split": "a quarter of each hit on it goes back to the attacker",
    "distribute": "healing past its max goes to its allies",
    "highwind": "jumps with no wait and lands when it chooses",
    "time_font": "status timers run faster for everyone",
    "time_sink": "status timers run slower for everyone",
    "resonate": "trades the statuses it and its foe don't share",
    "sunken_state": "a physical hit makes it vanish",
    "vampire": "drains the HP it deals",
    "immortal": "rises as a Zombie when it falls",
    "final_spiral": "restores its allies as it falls",
    "final_esper": "summons its esper as it falls",
    "final_ripple": "passes its fall to whoever felled it",
    "quickening": "its spells repeat while it can pay 1.5x the MP (and as much HP)",
    "gunblade": "its attacks fire a Super Ball: a critical and a HyperDrive",
    "art_license": "its sketches always work and pierce every element",
    "vip": "if it falls, the battle is lost",
    "final_fenix": "starts with Reraise; when it rises, Phoenix revives its allies",
    "caller": "can summon again and again and change espers in battle",
    "esper_attack": "its attacks take on its esper's elements, never absorbed or blocked",
    "barehanded": "fights barehanded with 5 x its level in attack",
    "decisive": "its attacks can't be countered",
    "maintenance": "monsters can't steal gil from it",
    "true_paladin": "takes attacks aimed at others",
    "popular": "allies (and sometimes enemies) take attacks aimed at it",
    "gaia_boost": "attacks of the battlefield's element x1.5",
    "gaia_assist": "joins attacks with a dance of the battlefield",
    "flinch": "half its attacks cut the target's ATB gauge to a quarter",
    "double_time": "half the damage and healing, but its gauge restarts half full",
    "plague": "every enemy's Doom countdown starts with the battle",
    "discordant": "sets its target's level's last digit to its own HP's",
    "null_sleep": "can't be hit while asleep",
    "luck_font": "no effect in this version of Beyond Chaos",
    "luck_sink": "no effect in this version of Beyond Chaos",
    "juggernaut": "starts battles at half its level, then climbs",
    "burst": "starts battles at 1.5x its level, then sinks",
    "atma_force": "deals more the healthier its side (up to x1.5)",
    "corrosive": "its damage also lowers the target's max HP",
    "overheal": "healing past max raises HP past max (by a quarter of the excess)",
    "juggler": "after each hit, its stronger defense guards against that kind of hit",
}
for _b, (_el, _pr) in enumerate([("fire", "Fire"), ("ice", "Ice"), ("bolt", "Lightning"), ("poison", "Poison"),
                                  ("wind", "Wind"), ("pearl", "Holy"), ("earth", "Earth"), ("water", "Water")]):
    BLURBS[f"boost_{_el}"] = f"its {_pr} attacks x1.5"
    BLURBS[f"{_el}_font"] = f"everyone's {_pr} attacks x1.25"
    BLURBS[f"{_el}_sink"] = f"everyone's {_pr} attacks x0.75"
    BLURBS[f"pierce_{_el}"] = f"its {_pr} attacks can't be absorbed, nullified or halved"
    BLURBS[f"repel_{_el}"] = f"{_pr} spells bounce off it as if it had Reflect"


def guide_pages(part, nm=None):
    """Pages for the seed's guide (tools/bc_guide.py): what junction effects are, then the seed's effects with
    a line each, a few to a page. part: bc_battle.json's "junction"."""
    nm = nm or part.get("names") or names()
    keys = sorted(used(part), key=lambda k: nm.get(k, k))
    fl = set(part.get("flags", []))
    holders = [w for f, w in (("espffect", "espers"), ("effectmas", "equipment"), ("effectory", "relics"))
               if f in fl or (not fl and part.get("espers" if f == "espffect" else "equipment"))]
    if fl & {"effectster", "treaffect"} or (not fl and (part.get("monsters") or part.get("every_monster"))):
        holders.append("monsters")
    pages = [{"title": "Junction effects", "lines": [
        f"In this seed {(', '.join(holders[:-1]) + ' and ' + holders[-1]) if len(holders) > 1 else (holders[0] if holders else 'some things')} "
        "carry hidden extra abilities: junction effects.",
        _sentence("; ".join(([] if holders == ["monsters"] else ["Equip an esper or an item and its holder has its effects in battle"]) +
                            (["a monster with one uses it on you"] if "monsters" in holders else []))),
        "An item's or esper's description lists them (\"Junction: ...\"); the next pages explain each one."]}]
    if part.get("statuses"):
        st = ", ".join(sorted({STATUS_PR.get(int(s), STATUS_NAMES[int(s)]) for s in part["statuses"]}))
        pages[0]["lines"].append(f"Some statuses carry effects too ({st}): whoever has the status has them.")
    if "junction_jammer" in keys:
        pages[0]["lines"].append("Junction Jammer: while someone on the field has it, any effect can fail at random.")
    page = []
    for k in keys:
        page.append(f"{nm.get(k, k)}: {BLURBS.get(k, 'see its description')}.")
        if len(page) == 3:
            pages.append({"title": "Junction effects", "lines": page})
            page = []
    if page:
        pages.append({"title": "Junction effects", "lines": page})
    return pages


STATUS_PR = {1: "Zombie", 5: "Imp", 16: "Dance", 27: "Trance"}


def _sentence(text):
    return text[:1].upper() + text[1:] + "." if text else ""


# --- a check against BC's own report (its spoiler log's JUNCTIONS section, JunctionManager.report) ---------

def log_report(spoiler):
    """{category: {name: [short names]}} from BC's log (ALWAYS / CHARACTERS / ESPERS / EQUIPS / STATUSES /
    MONSTERS sections; a '-' name is a blacklist entry)."""
    m = re.search(r"-\d+- JUNCTIONS\n-+\n(.*?)(?:\n-\d+- |\Z)", spoiler, re.S)
    if not m:
        return {}
    out, section = {}, None
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        if not line.startswith(" ") and line.strip().isupper():
            section = line.strip()
            out[section] = {}
        elif section == "ALWAYS":
            out[section][""] = [s.strip() for s in line.split(",")]
        elif section and " : " in line:
            name, _, js = line.partition(" : ")
            out[section][name.strip()] = [s.strip() for s in js.split(",")]
    return out


def check_log(rec, spoiler, man=None):
    """Differences between read() and BC's report (an empty list: the ROM's lists are what BC logged).
    BC's report renames the SOS command junctions after the seed's commands; those are compared by index."""
    man = man or manifest()
    cat = catalog(man)
    short = {int(man["junction_indexes"][k], 16): v for k, v in man["junction_short_names"].items()}
    report = log_report(spoiler)
    bad = []
    sections = {"character": "CHARACTERS", "esper": "ESPERS", "equip": "EQUIPS", "status": "STATUSES",
                "monster": "MONSTERS"}
    for category, section in sections.items():
        names = man[f"{category}_names"]
        got = report.get(section, {})
        for i in range(len(names)):
            white = set(rec[category]["white"].get(i, []))
            black = set(rec[category]["black"].get(i, []))
            want = sorted({short[j] for j in white - black}) + sorted({"-" + short[j] for j in black})
            have = got.get(names[i].strip(), [])
            if category == "monster":
                # BC's report keys monsters by its (possibly renamed) names: compare where the name matches
                if names[i].strip() not in got:
                    continue
            def norm(lst):
                return sorted(re.sub(r"^(-?)SOS .*", r"\1SOS *", s) for s in lst)
            if norm(have) != norm(want) and (have or want):
                bad.append((category, i, names[i], have, want))
    del cat
    return bad


# --- reading BC's patches: a decoded listing of each (randomtools' patch text, one instruction a line) -------

def _params(man):
    """{{name}} -> text: the manifest's parameters, jun-index-<key> -> 0xNN (key), jun-global-<name> -> address."""
    p = {k: str(v) for k, v in man["patch_parameters"].items()}
    for k, v in man["junction_indexes"].items():
        p[f"jun-index-{k.replace('_', '-')}"] = f"J:{k}"
    for k, v in man["global_addresses"].items():
        p[f"jun-global-{k}"] = v
    return p


def _decode_line(tokens, names):
    """One patch line's tokens (hex bytes, $label[,2], @label,2, label, #param) -> instruction texts."""
    import snes_disasm as D
    out = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if not re.fullmatch(r"[0-9a-fA-F]{2}", t):
            out.append(f".db {' '.join(tokens[i:])}")
            break
        op = int(t, 16)
        mn, mode = D.OPCODES[op]
        rest = tokens[i + 1:]
        # operand tokens: a symbol counts as its width ($x = 3 bytes, $x,2 / @x,2 = 2, bare label = 1 (branch))
        def width(tok):
            if tok.startswith("J:"):
                return 2 if tok.endswith(",2") else 1
            if tok.startswith(("$", "@")):
                return 2 if tok.endswith(",2") else 3
            if re.fullmatch(r"[0-9a-fA-F]{2}", tok):
                return 1
            return 2 if mode in (D.RELL,) else 1
        size = D.SIZE.get(mode)
        if size is None:          # immediate of the M/X width: the rest of a one-instruction line
            size = 2 if sum(width(x) for x in rest) == 2 and len(rest) <= 2 else 1
        operand, used_ = [], 0
        while used_ < size and rest:
            tok = rest.pop(0)
            operand.append(tok)
            used_ += width(tok)
        i += 1 + len(operand)
        txt = " ".join(operand)
        if all(re.fullmatch(r"[0-9a-fA-F]{2}", x) for x in operand) and operand:
            val = int("".join(reversed(operand)), 16)
            num = f"${val:0{len(operand) * 2}X}"
        else:
            num = txt.replace("$", "").replace("@", "").replace(",2", "")
            num = names.get(num, num)
        if mode in (D.IMP,):
            s = mn
        elif mode == D.ACC:
            s = mn
        elif mode in (D.IMM_M, D.IMM_X, D.IMM8, D.IMM16):
            s = f"{mn} #{num}" if mn not in ("PEA",) else f"{mn} {num}"
        elif mode in (D.REL, D.RELL):
            s = f"{mn} {num}"
        else:
            fmt = {D.DP: "{}", D.DPX: "{},X", D.DPY: "{},Y", D.DPI: "({})", D.DPIX: "({},X)", D.DPIY: "({}),Y",
                   D.DPIL: "[{}]", D.DPILY: "[{}],Y", D.ABS: "{}", D.ABSX: "{},X", D.ABSY: "{},Y", D.ABSI: "({})",
                   D.ABSIX: "({},X)", D.ABSIL: "[{}]", D.LONG: "{}", D.LONGX: "{},X", D.SR: "{},S",
                   D.SRIY: "({},S),Y", D.MOVE: "{}"}.get(mode, "{}")
            s = f"{mn} {fmt.format(num)}"
        out.append(s)
    return out


def _bank_addr(offset):
    """A patch's file offset -> its SNES address text (HiROM C0-FF below 4 MB, 40-7D above)."""
    return f"{0xC0 + (offset >> 16):02X}/{offset & 0xFFFF:04X}" if offset < 0x400000 else f"{offset >> 16:02X}/{offset & 0xFFFF:04X}"


_vanilla_code = None


def _vanilla(addr_offset, before=12, after=16):
    """The vanilla US code around a hook (file offset < 4 MB), from a trace of the battle/menu banks."""
    global _vanilla_code
    import snes_disasm as D
    if _vanilla_code is None:
        import prdata as P
        import ted_battle as T
        rom = D.Rom.load(P.VANILLA_ROM)
        _vanilla_code = (rom, D.trace(rom, T.ENTRIES, max_table=128), T.US_NAMES)
    rom, code, names = _vanilla_code
    a = 0xC00000 + addr_offset
    insns = sorted(code.insns) if hasattr(code, "insns") else None
    if insns is None:
        return "  (no trace)"
    import bisect
    k = bisect.bisect_left(insns, a)
    lo, hi = insns[max(0, k - before)], insns[min(len(insns) - 1, k + after)]
    if k >= len(insns) or abs(insns[min(k, len(insns) - 1)] - a) > 0x40:
        return "  (not in traced vanilla code)"
    text = code.listing(lo, hi)
    return "\n".join("    | " + line for line in text.splitlines())


def listing(patch_path, man=None, vanilla=True):
    """A readable listing of one of BC's junction patches: hook sites (with the vanilla code around them),
    blocks with their instructions decoded, junction indexes named, the VALIDATION (original bytes)."""
    man = man or manifest()
    params = _params(man)
    names = {}
    lines = open(patch_path, encoding="utf-8").read().splitlines()
    out = [f"== {os.path.basename(patch_path)}"]
    users = [k for k, v in man["patch_list"].items() if os.path.basename(patch_path) in v]
    if users:
        out.append("   listed for: " + ", ".join(f"{k} ({man['junction_short_names'].get(k, '')})" for k in users))
    section = "code"
    for raw in lines:
        line = raw.rstrip()
        sub = lambda m: params.get(m.group(1), m.group(2) or m.group(1))  # noqa: E731
        line = re.sub(r"\{\{([^:}]+)(?::([^}]*))?\}\}", lambda m: params.get(m.group(1), (m.group(2) or "?")), line)
        if not line.strip():
            continue
        if line.strip() == "VALIDATION":
            section = "validation"
            out.append("\n-- VALIDATION (the bytes the patch expects to replace)")
            continue
        code, _, comment = line.partition("#")
        code = code.strip()
        comment = ("  ; " + comment.strip()) if comment.strip() else ""
        if not code:
            if comment:
                out.append("        " + comment.strip())
            continue
        m = re.match(r"^\.addr\s+(\S+)\s+(\S+)", code)
        if m:
            names[m.group(1)] = m.group(1)
            out.append(f".addr {m.group(1)} = {m.group(2)}" + comment)
            continue
        if code.startswith((".def", ".label")):
            parts = code.split()
            out.append(f"  {parts[1]}:" if parts[0] == ".label" else " ".join(parts) + comment)
            continue
        if code.startswith("$") and ":" not in code:
            out.append(f"\n{code[1:]}:{comment}")
            continue
        m = re.match(r"^([0-9a-fA-F]{6}):\s*(.*)$", code)
        if m:
            off = int(m.group(1), 16)
            toks = m.group(2).split()
            if section == "validation":
                out.append(f"{_bank_addr(off)}: was {' '.join(toks)}")
                continue
            out.append(f"\nHOOK {_bank_addr(off)}: " + "; ".join(_decode_line(toks, names)) + comment)
            if vanilla and off < 0x400000:
                out.append("    vanilla around it:")
                out.append(_vanilla(off))
            continue
        if code.startswith(":"):
            toks = code[1:].split()
            if section == "validation":
                out.append(f"      {' '.join(toks)}")
                continue
            for ins in _decode_line(toks, names):
                out.append(f"    {ins}{comment}")
                comment = ""
            continue
        out.append(f"?? {code}{comment}")
    return "\n".join(out)


def main():
    import argparse
    if len(sys.argv) > 1 and sys.argv[1] == "listing":
        ap = argparse.ArgumentParser(description="decoded listings of BC's junction patches")
        ap.add_argument("cmd")
        ap.add_argument("--out", default=os.path.join(os.path.dirname(HERE), "build", "bc_junction", "listings"))
        ap.add_argument("--no-vanilla", action="store_true")
        ap.add_argument("patches", nargs="*", help="patch file names (default: every patch_junction_*.txt and "
                                                     "the core patches)")
        a = ap.parse_args()
        import bc_run
        man = manifest()
        tables = os.path.join(bc_run.SRC, "tables")
        names = a.patches or sorted({p for v in man["patch_list"].values() for p in v} | set(man["core_patch_list"]) |
                                    {f for f in os.listdir(tables) if f.startswith("patch_junction_")})
        os.makedirs(a.out, exist_ok=True)
        for n in names:
            p = os.path.join(tables, n)
            if not os.path.exists(p):
                print("missing", n)
                continue
            with open(os.path.join(a.out, n), "w", encoding="utf-8") as f:
                f.write(listing(p, man, vanilla=not a.no_vanilla))
        print(f"{len(names)} listings in {a.out}")
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", help="BC's output (bc_run.py OUT, or a plain ROM)")
    ap.add_argument("--log", help="BC's spoiler log, to check the record against its JUNCTIONS section")
    a = ap.parse_args()
    import ff6snes as S
    man = manifest()
    rec = read(S.rom_bytes(a.rom), man)
    if rec is None:
        print("no junction tables in this ROM")
        return
    part = pr_record(rec, man)
    print(json.dumps(part, indent=1))
    print(f"{len(used(part))} effects in use")
    if a.log:
        bad = check_log(rec, open(a.log, encoding="utf-8").read(), man)
        print(f"{len(bad)} differences from BC's log")
        for b in bad[:20]:
            print(" ", b)


if __name__ == "__main__":
    main()
