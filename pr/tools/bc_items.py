"""Beyond Chaos's changed equipment, said in words (the user, 2026-11-20, on "Behemoth Suit?": "what does the
question mark mean though? ... BC is unparseable").

BC's `questionablecontent` puts a "?" after (or over the last letter of) the name of any equipment its
item randomizer changed, and only its spoiler log says how ("BehemothSui?:  Doom" under BREAKABLE ITEMS:
it casts Doom when used). Here the name is the game's own with BC's "?" (the user: "? is fine if that's
what it means"), and the item's description says what the "?" stands for, in the Pixel Remaster's words:
"Changed: Casts Doom when used in battle (and breaks); Defense 62 (was 50)."

From BC's log (its own account of each item: breaks, procs, spells taught, elements, special features)
and the seed's PR tables next to the game's (the numbers the menus show: Attack, Defense, Accuracy...). Run by bc_seed.py on
the packed seed folder.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
import prdata as P  # noqa: E402

ELEMENTS = {"fire": "Fire", "ice": "Ice", "lightning": "Lightning", "bolt": "Lightning", "poison": "Poison",
            "wind": "Wind", "pearl": "Holy", "holy": "Holy", "earth": "Earth", "water": "Water"}
STATUS = {"dark": "Blind", "zombie": "Zombie", "poison": "Poison", "magitek": "Magitek", "clear": "Vanish",
          "imp": "Imp", "petrify": "Petrify", "condemned": "Doom", "image": "Image", "mute": "Silence",
          "berserk": "Berserk", "muddle": "Confuse", "seizure": "Sap", "sleep": "Sleep", "float": "Float",
          "regen": "Regen", "slow": "Slow", "haste": "Haste", "stop": "Stop", "shell": "Shell", "safe": "Protect",
          "reflect": "Reflect", "near fatal": "Near Death"}
# BC's feature names (itemrandomizer.get_feature) in plain words
FEATURES = {
    "bat. pwr +1/4": "Attack +25%", "mag. pwr +1/4": "Magic +25%", "+1/4 hp": "Max HP +25%",
    "+1/2 hp": "Max HP +50%", "+1/8 hp": "Max HP +12.5%", "+1/4 mp": "Max MP +25%", "+1/2 mp": "Max MP +50%",
    "+1/8 mp": "Max MP +12.5%", "better steal": "Steals more often", "better sketch": "Sketch works more often",
    "better control": "Control works more often", "100% hit rate": "Attacks never miss", "1/2 mp cost": "Half MP cost",
    "mp cost = 1": "Every spell costs 1 MP", "vigor +50%": "Strength +50%", "initiative": "More first strikes",
    "vigilance": "No back attacks", "command changer": "Changes a command", "super jump": "Jump strikes repeatedly",
    "fight -> x-fight": "Attack strikes four times", "can counter": "Counterattacks", "random evade": "Evades at random",
    "use weapon 2-handed": "Two-handed grip", "can equip 2 weapons": "Dual wield", "can equip anything": "Equip anything",
    "cover": "Protects weak allies", "step regen": "Restores HP while walking", "low hp shell": "Shell when HP is low",
    "low hp safe": "Protect when HP is low", "low hp reflect": "Reflect when HP is low", "double exp": "Double EXP",
    "double gp": "Double gil", "reverses cures": "Healing hurts the wearer", "death protection": "Prevents Death",
    "near fatal always": "Always near death", "1/2 enc.": "Halves random battles", "no enc.": "No random battles",
    "sprint": "Dash",
}


def feature_words(text):
    t = text.strip().lower()
    if t in FEATURES:
        return FEATURES[t]
    m = re.match(r"no (.+)$", t)
    if m and m.group(1) in STATUS:
        return f"Prevents {STATUS[m.group(1)]}"
    m = re.match(r"auto (.+)$", t)
    if m and m.group(1) in STATUS:
        return f"Auto-{STATUS[m.group(1)]}"
    if t in STATUS:
        return f"Afflicts the wearer with {STATUS[t]}"
    return text.strip()


def _norm(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


def spell_names(van):
    """SNES skill name (normalized) -> the PR's name for it."""
    import ff6snes as S
    import idmap as M
    ct = P.Table("content")
    msg = P.messages("system", "en")
    by_ability = {int(r["type_value"]): r for r in ct.rows.values() if r["type_id"] == "4"}
    out = {}
    for s in S.spells(van):
        k = M.spell(s.id)
        row = by_ability.get(k) if k is not None else None
        name = re.sub(r"<[^>]+>", "", msg.get(row["mes_id_name"], "")).strip() if row else ""
        if s.name and name:
            out.setdefault(_norm(s.name), name)
    return out


def parse_log(text):
    """BC's ITEM MAGIC and ITEM EFFECTS sections: {SNES item name: [(kind, value)]}."""
    out = {}
    section = None
    current = None
    for line in text.splitlines():
        head = line.strip().upper()
        if head in ("BREAKABLE ITEMS", "ITEM PROCS", "SPELL-TEACHING ITEMS", "ELEMENTAL PROPERTIES",
                    "SPECIAL ACTIONS", "SPECIAL FEATURES", "COMMAND CHANGERS"):
            section, current = head, None
            continue
        if section is not None and line.startswith("-1") and "COLOSSEUM" in head:
            break
        if section is None or not line.strip() or set(line.strip()) == {"-"}:
            continue
        if section == "ELEMENTAL PROPERTIES":
            if not line.startswith((" ", "\t")) and line.rstrip().endswith(":"):
                current = line.strip()[:-1]
                continue
            if current:
                out.setdefault(current, []).append(("element", line.strip()))
            continue
        m = re.match(r"^(\S.*?):\s+(.*)$", line)
        if m:
            out.setdefault(m.group(1).strip(), []).append((section, m.group(2).strip()))
    return out


def element_words(line):
    m = re.match(r"(Gained|Lost) Elemental (Half-Damage|Absorption|Nullification|Weakness|Damage): (\w+)", line)
    if not m:
        return line
    gained, kind, element = m.group(1) == "Gained", m.group(2), ELEMENTS.get(m.group(3).lower(), m.group(3))
    words = {"Half-Damage": ("Halves {} damage", "No longer halves {} damage"),
             "Absorption": ("Absorbs {}", "No longer absorbs {}"),
             "Nullification": ("Immune to {}", "No longer immune to {}"),
             "Weakness": ("Weak to {}", "No longer weak to {}"),
             "Damage": ("{} damage", "No longer {} damage")}[kind]
    return (words[0] if gained else words[1]).format(element)


def describe(entries, spells, stats):
    """Phrases for one item: what it does differently."""
    def spell(name):
        n = re.sub(r"\(.*?\)", "", name).strip()
        return spells.get(_norm(n), n)
    out = []
    for kind, value in entries:
        if kind == "BREAKABLE ITEMS":
            keeps = "indestructible" in value
            out.append(f"Casts {spell(value)} when used in battle" + ("" if keeps else " (and breaks)"))
        elif kind == "ITEM PROCS":
            out.append(f"Sometimes casts {spell(value)} on a hit")
        elif kind == "SPELL-TEACHING ITEMS":
            m = re.match(r"(.+?)\s+x\d+$", value)
            out.append(f"Teaches {spell(m.group(1) if m else value)}")
        elif kind == "element":
            out.append(element_words(value))
        elif kind in ("SPECIAL FEATURES", "SPECIAL ACTIONS"):
            out.extend(feature_words(v) for v in value.split(",") if v.strip())
    return group_elements(out) + stats


def group_elements(phrases):
    """"Halves Poison damage; Halves Lightning damage" -> "Halves Poison and Lightning damage"."""
    forms = [("Halves {} damage", r"Halves (\w+) damage"), ("No longer halves {} damage", r"No longer halves (\w+) damage"),
             ("Absorbs {}", r"Absorbs (\w+)$"), ("No longer absorbs {}", r"No longer absorbs (\w+)$"),
             ("Immune to {}", r"Immune to (\w+)$"), ("No longer immune to {}", r"No longer immune to (\w+)$"),
             ("Weak to {}", r"Weak to (\w+)$"), ("No longer weak to {}", r"No longer weak to (\w+)$")]
    out, groups = [], {}
    for p in phrases:
        for i, (_, rx) in enumerate(forms):
            m = re.fullmatch(rx, p)
            if m:
                if i not in groups:
                    groups[i] = []
                    out.append(i)
                groups[i].append(m.group(1))
                break
        else:
            out.append(p)

    def join(names):
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return [forms[x][0].format(join(groups[x])) if isinstance(x, int) else x for x in out]


MAX_TEXT = 150      # about the description box's two lines (to be measured with the game's font)

# the numbers the Pixel Remaster's menus show, by table: (column, label, signed bonus)
STATS = {
    "weapon": [("attack", "Attack", False), ("evasion_rate", "Evasion", True),
               ("critical_rate", "Critical rate", True), ("strength", "Strength", True), ("agility", "Agility", True),
               ("vitality", "Stamina", True), ("magic", "Magic", True), ("max_hp_up", "Max HP %", True),
               ("max_mp_up", "Max MP %", True)],
    "armor": [("defense", "Defense", False), ("ability_defense", "Magic Defense", False), ("evasion_rate", "Evasion", True),
              ("ability_evasion_rate", "Magic Evasion", True), ("strength", "Strength", True), ("agility", "Agility", True),
              ("vitality", "Stamina", True), ("magic", "Magic", True), ("max_hp_up", "Max HP %", True),
              ("max_mp_up", "Max MP %", True)],
}


def stat_changes(kind, van_row, seed_row):
    """The menu's numbers that changed between the game's item and the seed's (PR weapon/armor rows)."""
    out = []
    for col, label, signed in STATS.get(kind, []):
        if col not in van_row or col not in seed_row:
            continue
        try:
            was, now = int(van_row[col]), int(seed_row[col])
        except ValueError:
            continue
        if was == now:
            continue
        if not signed:
            out.append(f"{label} {now} (was {was})")
        else:
            out.append(f"{label} {now:+d}" + (f" (was {was:+d})" if was else ""))
    return out


def apply(out, van_rom_path, seed_rom_path, spoiler, log=print):
    """Descriptions that say what BC changed in each "?" item. Returns {PR name key: description}."""
    import bc_commands
    import ff6snes as S
    import idmap as M
    van, bc = S.Rom(van_rom_path), S.Rom(seed_rom_path)
    vitems, bitems = S.items(van), S.items(bc)
    entries = parse_log(spoiler)
    spells = spell_names(van)
    t = bc_commands._tables(out, ["content", "weapon", "armor"])
    ct = t["content"]
    vtables = {k: P.Table(k) for k in ("weapon", "armor")}
    msg_path, msg = bc_commands._messages(out)
    vmsg = P.messages("system", "en")
    done = {}
    for vi, bi in zip(vitems, bitems):
        if "?" not in bi.name:
            continue
        m = M.item(bi.id)
        cid = M.content_id(*m) if m else None
        row = ct.rows.get(cid) if cid else None
        if not row or row["mes_id_name"] in ("None", ""):
            continue
        kind, pid = m
        stats = (stat_changes(kind, vtables[kind].rows.get(pid, {}), t[kind].rows.get(pid, {}))
                 if kind in vtables else [])
        # a weapon's hit rate: the porter writes the SNES's own (0-255) where the PR's is 100, so say
        # which way BC moved it rather than two numbers on different scales
        if bi.type == "weapon" and abs(bi.hit_or_mdef - vi.hit_or_mdef) >= 8:
            stats.insert(1 if stats else 0, "More accurate" if bi.hit_or_mdef > vi.hit_or_mdef else "Less accurate")
        phrases = describe(entries.get(bi.name, []), spells, stats)
        key = row["mes_id_name"]   # the name: the game's own + BC's "?" (pr_names), which the description explains
        if phrases and row["mes_id_description"] not in ("None", ""):
            text = "Changed: " + "; ".join(phrases) + "."
            while len(text) > MAX_TEXT and len(phrases) > 1:
                phrases = phrases[:-1]                      # the stat changes go first (the menus show those)
                text = "Changed: " + "; ".join(phrases) + "; ..."
            msg[row["mes_id_description"]] = text
            done[key] = text
    bc_commands._write(out, t)
    with open(msg_path, "w", encoding="utf-8", newline="") as f:
        for k, v in msg.items():
            f.write(f"{k}\t{v}\r\n")
    log(f"bc items: {len(done)} changed items described")
    return done


# --- the battle side of BC's equipment (bc-battle; bc_battle.py runs battle_part) -------------------------
# BC's item layout (itemrandomizer.extend_item_breaks, always on): byte 18 = the spell (all 8 bits), byte 19
# bit 2 = cast on a hit (weapons, 25%), bit 3 = used up when used; byte 0 bit 5 = usable from the battle Item
# list, bit 4 = throwable. The porter reads byte 18 in vanilla's layout (bit 6 proc, bit 7 destroyed), so
# here the seed's weapon/armor rows, proc and break copies and battle_extra_data are rewritten from BC's ROM
# in BC's layout (the ROM is only read: BC's draws are BC's). Spec: bc-battle-spec-items.md (notes).
BREAK_OWN = {"condition_group_id": "0", "content_flag_group_id": "14", "invalid_reflection": "1", "ability_wait": "0"}
CHANGERS_BEFORE, CHANGERS_AFTER = 0x25452, 0x25457     # C2/5452: 5 commands, C2/5457: what each becomes
# Evade, MBlock and worn statuses (bytes 8 and 25, weapons too) are the shared porter's (port_effects,
# port_resist, 2026-11-20). Left here: what the PR's tables can't hold, for the plugin: auto Stop (byte 8 bit 4,
# set once at battle start) and a weapon's status immunities (bytes 6-7: the PR's weapons have no such column)
AUTO_8 = {0: 17, 1: 20, 2: 25, 3: 21, 4: 26, 5: 22, 6: 23, 7: 92}
# byte 27's special actions the PR decides by weapon id in code (CalcExecuteFF6 / CalcExecuteCorrection /
# BattleActExectionSerial): the plugin adds BC's weapons to those (BcWeaponSpecials)
WEAPON_SPECIALS_IN_CODE = {0x2: "atma", 0x7: "mp_critical", 0xA: "valiant", 0xC: "heal", 0xE: "fragile"}


def _status_conds(byte, table):
    return sorted({table[b] for b in range(8) if byte >> b & 1 and b in table})


def equipment(out, rom, log=print):
    """Rewrite the seed folder's equipment rows from BC's ROM (breaks, procs, command changers, throwing); returns
    the plugin's part (auto Stop, weapon immunities, Vigor +50%, monsters' item use)."""
    import json
    import bc_commands
    import ff6snes as S
    import idmap as M
    import port
    import port_procs as PP
    import port_resist as PRs
    van, bc = S.Rom(P.VANILLA_ROM), S.Rom(rom)
    t = bc_commands._tables(out, ["weapon", "armor", "ability", "content", "function_group"])
    ab, ct, fg = t["ability"], t["content"], t["function_group"]
    vab = P.Table("ability")
    extra_path = os.path.join(out, "files", PP.GROUP, *PP.ASSET.split("/")) + ".json"
    if os.path.exists(extra_path):
        with open(extra_path, encoding="utf-8") as f:
            extra = json.load(f)
    else:
        extra = PP.vanilla_extra()
    vextra = PP.vanilla_extra()
    vitems, bitems = S.items(van), S.items(bc)

    # vanilla's copies: PR spell -> its break copy (rods, shields) / its proc copy
    breaks, procs = {}, {}
    vprocs = {e["weapon_id"]: e["ability_id"] for e in vextra["add_ability_weapon"]}
    for vi in vitems:
        m = M.item(vi.id)
        if not m or m[0] not in ("weapon", "armor"):
            continue
        spell = M.spell(vi.raw[18] & 0x3F)
        if vi.raw[18] & 0x80:
            trig = {"weapon": van_weapon_trigger, "armor": van_armor_trigger}[m[0]](m[1])
            if trig:
                breaks.setdefault(spell, trig)
        if m[0] == "weapon" and vi.raw[18] & 0x40 and m[1] in vprocs:
            procs.setdefault(spell, vprocs[m[1]])

    def copy(spell, own):
        k = max(ab.rows) + 1
        ab.rows[k] = dict(ab[spell], id=str(k), sort_id=str(k), **own)
        cid = max(ct.rows) + 1
        ct.rows[cid] = {"id": str(cid), "mes_id_name": "None", "mes_id_battle": "None", "mes_id_description": "None",
                        "icon_id": "0", "type_id": "4", "type_value": str(k)}
        return k

    def break_copy(spell):
        if spell not in breaks:
            own = dict(BREAK_OWN)
            if ab[spell]["renge_id"] in ("4", "9", "16"):
                own["content_flag_group_id"] = "16"         # as vanilla's Quartr break (a group target)
            breaks[spell] = copy(spell, own)
        return breaks[spell]

    def proc_copy(spell):
        if spell not in procs:
            procs[spell] = copy(spell, PP.PROC_OWN)
        return procs[spell]

    entries = [e for e in extra["add_ability_weapon"]]
    by_weapon = {e["weapon_id"]: e for e in entries}
    plugin = {"auto": {}, "immune": {}, "vigor": [], "monster_item_use": {}, "special": {}}
    n = {"break": 0, "proc": 0, "throw": 0}
    for vi, bi in zip(vitems, bitems):
        m = M.item(bi.id)
        if bi.id >= 0xE8 or not m or m[0] not in ("weapon", "armor") or m[1] not in t[m[0]].rows:
            continue
        kind, pid = m
        row, raw = t[kind][pid], bi.raw
        spell = M.spell(raw[18])
        spell = spell if spell in ab.rows else None
        # item use: casts byte 18's spell; used up unless byte 19 bit 3 is clear (unbreakable, 1-in-20)
        trig, rate = ("0", "0")
        if raw[0] & 0x20 and spell is not None:
            trig, rate = str(break_copy(spell)), "100" if raw[19] & 0x08 else "0"
        if (row["trigger_ability_id"], row["destroy_rate"]) != (trig, rate):
            row["trigger_ability_id"], row["destroy_rate"] = trig, rate
            n["break"] += 1
        if trig != "0":
            # a monster "using" it (collateraldamage turns monsters' spells into F6 00 item uses; the AI's
            # item map, port_ai.item_abilities, holds consumables only) casts the same spell
            plugin["monster_item_use"][str(bi.id)] = int(trig)
        if kind == "weapon":
            # a hit casts byte 18's spell 25% of the time (C2/3649), weapons only
            proc = bool(raw[19] & 0x04) and spell is not None
            had = by_weapon.get(pid)
            if proc:
                e = {"weapon_id": pid, "ability_id": proc_copy(spell), "ability_per": PP.PROC_RATE}
                if had != e:
                    by_weapon[pid] = e
                    n["proc"] += 1
            elif had is not None:
                del by_weapon[pid]
                n["proc"] += 1
            if proc:
                row["process_prog"] = "ADD_MAGIC"
            elif row["process_prog"] == "ADD_MAGIC":
                row["process_prog"] = "None"
            # every weapon throwable (BC's unrestrict)
            thr = str(raw[0] >> 4 & 1)
            if row["throw_flag"] != thr:
                row["throw_flag"] = thr
                n["throw"] += 1
        # Evade, MBlock and the statuses equipment wears are the shared porter's since 2026-11-20 (port_effects,
        # port_resist: weapons' bytes 8/25, byte 25, auto Slow as a wear condition). Auto Stop (byte 8 bit 4, which
        # no vanilla item has) the SNES sets once at battle start: the plugin's (only what BC added)
        cid = M.content_id(kind, pid)
        vraw = vi.raw
        auto = _status_conds(raw[8] & ~vraw[8] & 0x10, AUTO_8)
        if auto:
            plugin["auto"][str(cid)] = auto
        if kind == "weapon":
            bits = (raw[6] | raw[7] << 8) & ~(vraw[6] | vraw[7] << 8)
            imm = sorted({c for b in range(16) if bits >> b & 1 for c in PRs.PROTECT.get(b, [])})
            if imm:
                plugin["immune"][str(cid)] = imm
        if raw[11] & 0x80 and not vraw[11] & 0x80:
            plugin["vigor"].append(cid)
        # weapon special actions the PR keys on weapon ids in code (byte 27 high nibble; BC's mutate_special_action
        # gives one to weapons that had none): Atma, MP criticals, Valiant, healing hits, fragile. The others (steal,
        # X-kill, man eater, drains, throw, dice, wind, slice) are data the porter carries.
        if kind == "weapon" and raw[27] >> 4 != vraw[27] >> 4 and raw[27] >> 4 in WEAPON_SPECIALS_IN_CODE:
            plugin["special"].setdefault(WEAPON_SPECIALS_IN_CODE[raw[27] >> 4], []).append({"weapon": pid, "content": cid})
    extra["add_ability_weapon"] = sorted(by_weapon.values(), key=lambda e: e["weapon_id"])
    os.makedirs(os.path.dirname(extra_path), exist_ok=True)
    with open(extra_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(extra, f, ensure_ascii=False, indent=2)

    # command changers (byte 10 bits 2-6): BC's pairs into the PR's function 61 rows that hold vanilla's
    vb, va = van.data[CHANGERS_BEFORE:CHANGERS_BEFORE + 5], van.data[CHANGERS_AFTER:CHANGERS_AFTER + 5]
    bb, ba = bc.data[CHANGERS_BEFORE:CHANGERS_BEFORE + 5], bc.data[CHANGERS_AFTER:CHANGERS_AFTER + 5]
    pairs = {}
    for i in range(5):
        old = (port.SNES_CMD.get(vb[i]), port.SNES_CMD.get(va[i]))
        new = (port.SNES_CMD.get(bb[i]), port.SNES_CMD.get(ba[i]))
        if None not in old and None not in new and old != new:
            pairs[tuple(map(str, old))] = tuple(map(str, new))
    changed_fg = 0
    for r in fg.rows.values():
        for i in (1, 2, 3):
            if r.get(f"function{i}_id") == "61":
                key = (r[f"function{i}_value1"], r[f"function{i}_value2"])
                if key in pairs:
                    r[f"function{i}_value1"], r[f"function{i}_value2"] = pairs[key]
                    changed_fg += 1
    bc_commands._write(out, t)
    log(f"bc items: equipment in BC's layout: {n['break']} item-use rows, {n['proc']} procs, {n['throw']} throw flags; "
        f"{len(pairs)} command changer pairs ({changed_fg} function rows); for the plugin: {len(plugin['auto'])} with Stop at battle start, {len(plugin['immune'])} weapons with "
        f"immunities, {len(plugin['vigor'])} with Vigor +50%")
    return plugin


_vtrig = {}


def _van_trigger(kind, pid):
    if kind not in _vtrig:
        _vtrig[kind] = {k: int(r["trigger_ability_id"]) for k, r in P.Table(kind).rows.items() if r["trigger_ability_id"] != "0"}
    return _vtrig[kind].get(pid, 0)


def van_weapon_trigger(pid):
    return _van_trigger("weapon", pid)


def van_armor_trigger(pid):
    return _van_trigger("armor", pid)


RERISE = 31   # the PR's Reraise (Life 3's function 9 condition)


def rerise(rom, log=print):
    """PR monster ids BC starts with Rerise (SNES monster byte 30 bit 2, status byte 4 at battle start): its
    HP boost gives it to a monster pushed past 65535 HP (far likelier under darkworld); port_resist reads the
    starting statuses of bytes 27-29 only. The plugin gives Rerise at battle start (BcItems)."""
    import ff6snes as S
    import idmap as M
    van, bc = S.enemies(S.Rom(P.VANILLA_ROM)), S.enemies(S.Rom(rom))
    out = [M.monster(b.id) for v, b in zip(van, bc) if b.raw[30] & 0x04 and not v.raw[30] & 0x04]
    if out:
        log(f"bc items: {len(out)} monsters start with Rerise (BC's HP cap)")
    return out


def battle_part(out, rom, spoiler, flags, log=print):
    """bc_battle.json's "items": the equipment fix above, and what the plugin applies (BcItems.cs)."""
    part = equipment(out, rom, log)
    part["rerise"] = rerise(rom, log)
    return part
