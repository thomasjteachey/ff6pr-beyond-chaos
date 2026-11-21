"""Beyond Chaos's replaced commands (`w`, and the codes that make more: metronome, suplexwrecks...) in a
seed folder: BC writes each as a 65816 subroutine in the command's slot; here each becomes the PR
command row of that slot (port.SNES_CMD: BC replaces a command for everyone who has it, as the PR's
row is everyone's), with a name in the PR's own words.

  one skill        the row runs that skill's ability directly, as the PR's Pray or Shock run theirs
                   (execution_type 1, list_type 0: no submenu, no MP)
  a random skill   a new ability on the PR's own random-ability function (46, as Bar-Bar-Bar's random
                   esper: ability 214) and a new ability_random_group with BC's odds (BC rolls a list of
                   8, 16 or 32 skills: a skill listed twice is twice as likely)
  N times / chain / combo   the row runs the first (or the random) ability, and the seed's json tells the
                   plugin the rest (BcCommands.cs: more casts, the combo's second skill)

Names (the user: "i don't like R-Ice"): the PR's skill names (Tsunami for BC's CleanSw, Libra for
Scan), "Random Ice", "Double Blizzard", "Chain Valigarmanda", "Arise + Cyclonic". Window widths are
measured in game (BcPlugin harness `bcnames`); the generator only keeps them in words.

bc_seed.py runs apply() on the packed seed folder (full tables), with what bc_run.run captured.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
import prdata as P  # noqa: E402

# BC's random sets (skillrandomizer.get_spellsets) in the PR's words: "Random <word>"
CLASS_WORDS = {
    "Chaos": "Chaos", "Wild": "Skill", "Magic": "Magic", "Black": "Black Magic", "White": "White Magic",
    "Gray": "Gray Magic", "Esper": "Esper", "Sword": "Bushido", "Blitz": "Blitz", "Geo": "Dance",
    "Beast": "Beast", "Lore": "Lore", "Rare": "Rarity", "Fire": "Fire", "Ice": "Ice", "Bolt": "Lightning",
    "Bio": "Poison", "Wind": "Wind", "Pearl": "Holy", "Earth": "Earth", "Water": "Water", "Elem": "Element",
    "Nuke": "Blast", "Heal": "Healing", "Phys": "Strike", "Curse": "Curse", "Bless": "Blessing",
    "Drain": "Drain", "Death": "Death", "Heavy": "Gravity", "All": "Free-for-All", "Party": "Boost",
    "Tek": "Magitek", "Time": "Time Magic", "Limit": "Desperation", "Level": "Level Magic", "Miss": "Gamble",
    "Dance": "Dance",
}
TIMES = {2: "Double", 3: "Triple", 4: "Quadruple"}

# Widths in the battle command list (SE-ALPSTN at size 32, a 256 px box with best fit; measured in game with the
# harness's `textwidth`, 2026-11-20, pr/build/BeyondChaos/textwidth_bcbattle.json): "Random <word>" per class
# word, and what each prefix/suffix adds. A repeated random command takes "Double Random X" where that fits,
# else "Random X x2" (the game would shrink the longer one to 83-91%).
BOX = 256
RANDOM_WIDTH = {"Beast": 157, "Black Magic": 224, "Blast": 149, "Blessing": 185, "Blitz": 141, "Boost": 157,
                "Bushido": 181, "Chaos": 164, "Curse": 159, "Dance": 164, "Death": 159, "Desperation": 223,
                "Drain": 152, "Earth": 153, "Element": 183, "Esper": 158, "Fire": 137, "Free-for-All": 215,
                "Gamble": 179, "Gravity": 172, "Gray Magic": 218, "Healing": 175, "Holy": 143, "Ice": 128,
                "Level Magic": 222, "Lightning": 191, "Lore": 143, "Magic": 159, "Magitek": 179, "Poison": 168,
                "Rarity": 158, "Skill": 139, "Strike": 157, "Time Magic": 219, "Water": 160, "White Magic": 227,
                "Wind": 150}
PREFIX_WIDTH = {"Double": 81, "Triple": 66, "Quadruple": 117}
SUFFIX_WIDTH = 32          # " x2" .. " x9"


def repeated_name(word, n):
    """"Double Random Ice", or "Random White Magic x2" where the word form is wider than the box."""
    base = RANDOM_WIDTH.get(word[len("Random "):]) if word.startswith("Random ") else None
    if n in TIMES and (base is None or base + PREFIX_WIDTH[TIMES[n]] <= BOX):
        return f"{TIMES[n]} {word}"
    return f"{word} x{n}"

# BC's command targeting byte (the SNES's: 01 cursor, 02 one side only, 04 everyone, 08 a whole side,
# 10 auto-confirm, 20 sides switchable, 40 monsters first, 80 random) -> the PR's AbilityRangeType
# (ability renge_id, battle_renge_id: 1 one ally, 2 all allies, 3 one monster, 4 all monsters, 5 self,
# 6 one or a side, 7 one of either side, 9 everyone, 13 a random monster, 16 all monsters by side,
# 20 a side or one). First as the PR has vanilla's spells with that byte (the most common range), then
# by meaning for bytes no vanilla spell has (BC's variants: 0x28 "a random one of a side", 0xC0 "a random
# one of everyone", 0x04 "everyone", 0x02 "only self"; manage_commands_new).
VANILLA_RANGE = {0x01: (7, 7), 0x02: (5, 5), 0x03: (1, 1), 0x04: (9, 9), 0x12: (5, 5), 0x21: (6, 6),
                 0x29: (20, 20), 0x2E: (2, 2), 0x3E: (2, 2), 0x41: (7, 7), 0x43: (3, 3), 0x53: (3, 3),
                 0x61: (6, 6), 0x63: (3, 3), 0x69: (20, 20), 0x6A: (16, 16), 0x6B: (4, 4), 0x6E: (4, 4),
                 0x7A: (16, 16), 0x7E: (4, 4)}
SINGLE = {1, 3, 5, 7, 13, 15}    # ranges that hit one unit


def snes_range(t):
    """BC's command targeting byte -> (renge_id, battle_renge_id), or None (keep the skill's own)."""
    if t is None:
        return None
    t &= 0xEF                                   # BC: commands never auto-confirm
    if t in VANILLA_RANGE:
        return VANILLA_RANGE[t]
    if t & 0x04 or t & 0x80:
        return (9, 9)                           # everyone (random: the plugin picks one of them)
    if t & 0x08 and t & 0x20:
        return (20, 20)                         # a side, switchable (random: one of it)
    if t & 0x08:
        return (16, 16) if t & 0x40 else (2, 2)
    if t & 0x01:
        if t & 0x20:
            return (6, 6)
        return ((3, 3) if t & 0x02 else (7, 7)) if t & 0x40 else (1, 1)
    if t & 0x02:
        return (5, 5)
    return None


def random_target(t, own_range):
    """BC's "random individual" variants: 0xC0 (random, both sides) or a whole side (0x28) on a skill that
    hits one: the SNES hits one unit of those at random (the plugin picks it: BcCommands)."""
    if t is None:
        return False
    t &= 0xEF
    return bool(t & 0x80) or (bool(t & 0x08) and bool(t & 0x20) and not t & 0x01 and own_range in SINGLE)


def odds(counts):
    """A random command's list (BC: 8, 16 or 32 entries, a skill listed twice twice as likely; R-Chaos: any
    of the 256) as ability_random_group invocation rates, which the PR draws by weight
    (CommonUtility.GetRandWeight): out of 100 like the game's own groups where that is exact enough,
    else each entry's count."""
    total = sum(counts.values())
    if len(counts) > 50:
        return dict(counts)
    rates = {k: max(1, round(100 * c / total)) for k, c in counts.items()}
    drift = 100 - sum(rates.values())
    if drift:
        top = max(rates, key=lambda k: (rates[k], -k))
        rates[top] = max(1, rates[top] + drift)
    return rates
DIRECT = {"command_type": "1", "execution_type": "1", "list_type": "0", "number_select": "0",
          "ability_group_id": "0", "consume_type": "0", "auto_execution_ability_id": "0"}
RANDOM_TEMPLATE = 214          # Bar-Bar-Bar's random esper: function 46 (random ability) on a random group


def _tables(out, names):
    import seed_live as L
    t = {}
    for n in names:
        path = os.path.join(out, *L.MASTER_PATH.split("/"), n + ".csv")
        with open(path, encoding="utf-8", newline="") as f:
            t[n] = P.Table(n, f.read())
    return t


def _write(out, tables):
    import seed_live as L
    for n, table in tables.items():
        path = os.path.join(out, *L.MASTER_PATH.split("/"), n + ".csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(table.to_csv(table.rows.keys()))


def _messages(out):
    import seed_live as L
    path = os.path.join(out, *L.MESSAGE_PATH.split("/"), "system_en.txt")
    text = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if "\t" in line:
                k, v = line.split("\t", 1)
                text[k] = v
    return path, text


def plain(name):
    return re.sub(r"<IC_[A-Z]+>", "", name or "").strip()


def apply(out, commands, log=print):
    """BC's commands (bc_run.run's capture["commands"]: SNES command id -> what it does) into the seed
    folder `out`. Returns the plugin's part: {PR command id: {kind, abilities, count, name}}."""
    import idmap as M
    import port
    if not commands:
        return {}
    t = _tables(out, ["command", "ability", "function_group", "ability_random_group", "content"])
    cmd, ab, fg, rg, ct = (t[n] for n in ("command", "ability", "function_group", "ability_random_group", "content"))
    msg_path, msg = _messages(out)
    by_ability = {int(r["type_value"]): r for r in ct.rows.values() if r["type_id"] == "4"}

    def pr_ability(snes):
        k = M.spell(snes)
        return k if k in ab.rows else None

    def skill_name(snes):
        k = pr_ability(snes)
        row = by_ability.get(k)
        return plain(msg.get(row["mes_id_name"], "")) if row else ""

    def ranged(k, rng):
        """ability k with BC's command targeting: a copy (the skill's own row stays as the Magic menu,
        the monsters and the other commands have it), named as the skill"""
        r = ab.rows[k]
        if rng is None or (int(r["renge_id"]), int(r["battle_renge_id"])) == rng:
            return k
        aid = max(ab.rows) + 1
        row = dict(r)
        row.update({"id": str(aid), "sort_id": str(aid), "renge_id": str(rng[0]), "menu_renge_id": "0",
                    "battle_renge_id": str(rng[1])})
        ab.rows[aid] = row
        src = by_ability.get(k)
        if src is not None:
            cid = max(ct.rows) + 1
            ct.rows[cid] = dict(src, id=str(cid), type_value=str(aid))
            by_ability[aid] = ct.rows[cid]
        return aid

    def random_ability(d, label, rng):
        skills = list(range(256)) if d.get("wild") or not d.get("skills") else d["skills"]
        counts = {}
        for s in skills:
            k = pr_ability(s)
            if k is not None and k not in (RANDOM_TEMPLATE,):
                counts[k] = counts.get(k, 0) + 1
        if not counts:
            return None
        group = max(int(r["group_id"]) for r in rg.rows.values()) + 1
        rates = odds(counts)
        rid = max(rg.rows) + 1
        for k, rate in sorted(rates.items()):
            rg.rows[rid] = {"id": str(rid), "group_id": str(group), "ability_id": str(k),
                            "invocation_rate": str(rate), "condition_group_id": "0"}
            rid += 1
        gid = max(fg.rows) + 1
        fg.rows[gid] = {c: "0" for c in fg.columns}
        fg.rows[gid].update({"id": str(gid), "function1_id": "46", "function1_value1": str(group), "function1_value2": "1"})
        aid = max(ab.rows) + 1
        # the template's row with BC's command targeting (only the menu's: the pick then targets as its
        # own skill does, function 46 with value2 1, as BC's random subs retarget), else the targeting
        # of the list's most likely skill
        top = max(counts, key=lambda k: (counts[k], -k))
        row = dict(ab.rows[RANDOM_TEMPLATE])
        for c in ("renge_id", "menu_renge_id", "battle_renge_id"):
            row[c] = ab.rows[top][c]
        if rng is not None:
            row.update({"renge_id": str(rng[0]), "menu_renge_id": "0", "battle_renge_id": str(rng[1])})
        row.update({"id": str(aid), "sort_id": str(aid), "battle_function_group_id": str(gid)})
        ab.rows[aid] = row
        cid = max(ct.rows) + 1
        key = f"MSG_BC_ABILITY_NAME_{aid}"
        ct.rows[cid] = {"id": str(cid), "mes_id_name": key, "mes_id_battle": "None", "mes_id_description": "None",
                        "icon_id": "0", "type_id": "4", "type_value": str(aid)}
        msg[key] = label
        return aid, sorted(counts), group

    plugin = {}
    for snes, d in sorted(commands.items(), key=lambda kv: int(kv[0])):
        snes = int(snes)
        prc = port.SNES_CMD.get(snes)
        if prc is None or prc not in cmd.rows:
            log(f"bc commands: SNES command {snes} ({d.get('name')}) has no PR command")
            continue
        kind = d["kind"]
        inner = d.get("inner") if kind in ("multiple", "chain") else d
        part = {"kind": kind, "inner": inner["kind"], "bc_name": d.get("name", ""), "targeting": d.get("targeting")}
        rng = snes_range(d.get("targeting"))
        if inner["kind"] == "skill":
            first, word = pr_ability(inner["skill"]), skill_name(inner["skill"])
            part["abilities"] = [first]
        elif inner["kind"] == "random":
            # R-Chaos (metronome; endless9 + metronome's 9x too): any skill at all, BC's "wild" sub
            cls = "Chaos" if inner.get("wild") else inner.get("class", "")
            word = "Random " + CLASS_WORDS.get(cls, cls or "Skill")
            made = random_ability(inner, word, rng)
            if not made:
                log(f"bc commands: {d.get('name')}: no PR ability among its skills")
                continue
            first, part["abilities"], part["random_group"] = made
        elif inner["kind"] == "combo":
            names = [skill_name(s) for s in inner["skills"]]
            part["abilities"] = [pr_ability(s) for s in inner["skills"]]
            first, word = part["abilities"][0], " + ".join(n for n in names if n)
        else:
            log(f"bc commands: {d.get('name')}: {inner['kind']} not handled")
            continue
        if first is None:
            log(f"bc commands: {d.get('name')}: no PR ability for its skill")
            continue
        if inner["kind"] in ("skill", "combo"):
            # BC's targeting variants (only self, everyone, a random one; never auto-confirm): the row's
            # ability with the command's targeting; a random one is picked by the plugin
            own = int(ab.rows[first]["renge_id"])
            if random_target(d.get("targeting"), own):
                part["target"] = "random"
            ranged_first = ranged(first, rng)
            if ranged_first != first:
                part["skill_ability"] = first
                first = part["abilities"][0] = ranged_first
        if kind == "multiple":
            n = d.get("count", 2)
            part["count"] = n
            name = repeated_name(word, n)
        elif kind == "chain":
            part["chain"] = True
            name = f"Chain {word}"
        else:
            name = word
        row = cmd.rows[prc]
        row.update(DIRECT)
        row["ability_id"] = str(first)
        for key in {row["mes_id_name"], row["mes_id_name2"]} - {"None", ""}:
            msg[key] = name
        part["name"] = name
        part["ability"] = first
        plugin[str(prc)] = part
        log(f"bc commands: SNES {snes} {d.get('name')!r} -> PR command {prc} {name!r} (ability {first}"
            f"{', ' + str(len(part['abilities'])) + ' in its list' if inner['kind'] == 'random' else ''})")
    _write(out, t)
    with open(msg_path, "w", encoding="utf-8", newline="") as f:
        for k, v in msg.items():
            f.write(f"{k}\t{v}\r\n")
    return plugin
