"""Beyond Chaos's small codes that are data in the Pixel Remaster, applied to a seed folder's full tables
(bc_seed.py, after the port). BC writes them as 65816 patches the porter can't read; the PR keeps the
same rules in its tables.

  dancelessons   no stumbling: the SNES's Dance fails half the time off its own terrain (C2/17B7 BC
                 patches); the PR's dance step groups for "elsewhere" (ability_random_group 37-44) hold
                 the stumble (ability 262) at 50, which goes, the steps keeping their odds between them
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
import bc_commands  # noqa: E402  (its seed-folder table helpers)

STUMBLE = 262
ELSEWHERE_GROUPS = range(37, 45)


def dancelessons(t, log):
    rg = t["ability_random_group"]
    n = 0
    for g in ELSEWHERE_GROUPS:
        rows = [r for r in rg.rows.values() if int(r["group_id"]) == g]
        stumble = [r for r in rows if int(r["ability_id"]) == STUMBLE]
        steps = [r for r in rows if int(r["ability_id"]) != STUMBLE]
        if not stumble or not steps:
            continue
        total = sum(int(r["invocation_rate"]) for r in steps)
        if total <= 0:
            continue
        for r in stumble:
            r["invocation_rate"] = "0"
        left = 100
        for i, r in enumerate(steps):
            rate = left if i == len(steps) - 1 else round(100 * int(r["invocation_rate"]) / total)
            r["invocation_rate"] = str(rate)
            left -= rate
        n += 1
    log(f"bc codes: dancelessons: no stumble in {n} dance step groups")


LORES = range(140, 164)        # the PR's 24 Lores (SNES 8B-A2), sort_id = id: SNES order


def alphalores(t, log, out=None):
    """`alphalores` (BC: a fixed order table read by the battle and field Lore lists, C2/5564, C3/520F): the
    Lores' sort_ids (the same 24 values) handed out in the alphabetical order of their names as the seed
    shows them in English."""
    import re
    import bc_commands
    ab, ct = t["ability"], t["content"]
    _, msg = bc_commands._messages(out)
    names = {}
    for r in ct.rows.values():
        if r["type_id"] == "4" and int(r["type_value"]) in LORES:
            names[int(r["type_value"])] = re.sub(r"<[^>]+>", "", msg.get(r["mes_id_name"], "")).strip()
    ids = [a for a in LORES if a in ab.rows]
    slots = sorted(int(ab[a]["sort_id"]) for a in ids)
    order = sorted(ids, key=lambda a: (names.get(a, "").lower(), a))
    for a, sid in zip(order, slots):
        ab[a]["sort_id"] = str(sid)
    log(f"bc codes: alphalores: {', '.join(names.get(a, str(a)) for a in order[:4])} ... ({len(order)} Lores)")


RAGE_ABILITY_TYPE = 625        # the PR's Rage abilities (800 + monster: port_dances.RAGE_ABILITY_TYPE)


def rage_order(t, log, out=None):
    """BC's Rage list in alphabetical order (every seed: manage_reorder_rages writes its order table, sorted by the
    seed's monster names, read by the Rage menus; audit gap #10): the Rages' sort_ids (the same values) handed out
    in the alphabetical order of their names as the seed shows them in English, as alphalores does for Lores."""
    import re
    import bc_commands
    ab, ct = t["ability"], t["content"]
    _, msg = bc_commands._messages(out)
    ids = [a for a, r in ab.rows.items() if r["type_id"] == str(RAGE_ABILITY_TYPE)]
    want = set(ids)
    names = {}
    for r in ct.rows.values():
        if r["type_id"] == "4" and int(r["type_value"]) in want:
            names[int(r["type_value"])] = re.sub(r"<[^>]+>", "", msg.get(r["mes_id_name"], "")).strip()
    slots = sorted(int(ab[a]["sort_id"]) for a in ids)
    order = sorted(ids, key=lambda a: (names.get(a, "").lower(), a))
    for a, sid in zip(order, slots):
        ab[a]["sort_id"] = str(sid)
    log(f"bc codes: rage order: {', '.join(names.get(a, str(a)) for a in order[:4])} ... ({len(order)} Rages)")


ALWAYS = {"rage_order": (["ability", "content"], rage_order)}    # BC does these on every seed

CODES = {"dancelessons": (["ability_random_group"], dancelessons),
         "alphalores": (["ability", "content"], alphalores)}


def apply(out, flags, log=print):
    """The codes in `flags` (BC's flag string) that are data here."""
    on = {f.split(":")[0] for f in flags.split()}
    done = []
    for code, (tables, run) in CODES.items():
        if code not in on:
            continue
        t = bc_commands._tables(out, tables)
        if code == "alphalores":
            run(t, log, out)
        else:
            run(t, log)
        bc_commands._write(out, t)
        done.append(code)
    for code, (tables, run) in ALWAYS.items():
        t = bc_commands._tables(out, tables)
        run(t, log, out)
        bc_commands._write(out, t)
        done.append(code)
    return done


def flag_values(flags):
    """BC's flag string -> {code: value} ("swdtechspeed:fast" -> "fast"; a bare code -> True)."""
    out = {}
    for f in flags.split():
        k, _, v = f.partition(":")
        out[k] = v if v else True
    return out


BLITZ_TABLE = 0x47A40               # C4/7A40: 8 Blitzes x 12 bytes, codes then $01 (BC's manage_blitz writes 2-8)
BLITZ_ABILITIES = [132, 133, 134, 135, 136, 137, 138, 139]   # the PR's Pummel .. Bum Rush


def blitz_inputs(on, out, rom, spoiler, log):
    """`l`: BC's Blitz inputs, {PR ability id: SNES button codes} (PrKit/Ff6/SnesBlitzInputs maps them to the
    PR's inputs). Pummel stays left-right-left (BC never rewrites it, so a ROM-free output may not hold it)."""
    import ff6snes as S
    d = S.rom_bytes(rom)
    part = {}
    for i in range(1, 8):
        row = d[BLITZ_TABLE + 12 * i: BLITZ_TABLE + 12 * i + 11]
        codes = []
        for b in row:
            if b == 0x01 or b == 0:
                break
            codes.append(b)
        if codes and all(3 <= c <= 0xE for c in codes):
            part[str(BLITZ_ABILITIES[i])] = codes
    log(f"bc codes: l: {len(part)} Blitz inputs")
    return part


LEVEL_CAPS = 0x303173         # F0/3173 (Myself's LEVEL_CAP): 14 bytes, one per character (99: none)
CURSE_GOAL = 0x26005          # C2/6001 `CMP #N`: the battles a Cursed Shield needs (patches.change_cursed_shield_battles)
RNG_TABLE = 0xFD00            # C0/FD00: the SNES's random table (norng: all zeros)
NO_MENU = 0x20928             # C2/091F's branch: $80 = nobody gets a command menu (playsitself)


def levelcap(on, out, rom, spoiler, log):
    """`levelcap` (its caps drawn by BC's own `rng`: read back, F0/3173): {PR character status id: cap}."""
    import ff6snes as S
    d = S.rom_bytes(rom)
    if len(d) < LEVEL_CAPS + 14:
        log("bc codes: levelcap: no F0 bank in this ROM (not BC's 6 MB layout)")
        return None
    caps = {str(c + 1): d[LEVEL_CAPS + c] for c in range(14) if 1 <= d[LEVEL_CAPS + c] < 99}
    log(f"bc codes: levelcap: {caps or 'none below 99'}")
    return {"caps": caps}


def cursepower(on, out, rom, spoiler, log):
    """`cursepower` (Random already rolled by BC): the battles a Cursed Shield takes to uncurse (vanilla 256)."""
    import ff6snes as S
    d = S.rom_bytes(rom)
    if bytes(d[CURSE_GOAL - 4:CURSE_GOAL - 1]) != bytes([0xAD, 0xC0, 0x3E]) or d[CURSE_GOAL - 1] != 0xC9:
        log("bc codes: cursepower: BC's patch not found")
        return None
    log(f"bc codes: cursepower: {d[CURSE_GOAL]} battles")
    return {"battles": max(1, d[CURSE_GOAL])}


def norng(on, out, rom, spoiler, log):
    """`norng`: BC zeroes the SNES's random table, so every battle roll is 0 (always the minimum damage
    variance, every eligible hit critical, stamina always blocks, always the rare steal/drop, the AI's first
    choice)."""
    import ff6snes as S
    d = S.rom_bytes(rom)
    zero = not any(d[RNG_TABLE:RNG_TABLE + 256])
    log(f"bc codes: norng: random table {'all zeros' if zero else 'not zeroed (BC left it)'}")
    return {"zero": zero} if zero else None


def playsitself(on, out, rom, spoiler, log):
    """`playsitself`: nobody gets a command menu (C2/091F branch at file 0x20928 = $80): each ready character
    uses a random command of his own that BC allows automatically (C2/04D0 and C2/04D4 bit tables)."""
    import ff6snes as S
    d = S.rom_bytes(rom)
    if d[NO_MENU] != 0x80:
        return None
    auto = int.from_bytes(bytes(d[0x204D0:0x204D4]), "little")
    berserk = int.from_bytes(bytes(d[0x204D4:0x204D8]), "little")
    log(f"bc codes: playsitself: auto commands {auto:08X}, while berserk {berserk:08X}")
    import port
    # C2/0420 offers a command if it is in both tables (nobody is Muddled or in the Colosseum for this path)
    both = [c for c in range(32) if auto >> c & 1 and berserk >> c & 1]
    return {"auto": [c for c in range(32) if auto >> c & 1], "berserk": [c for c in range(32) if berserk >> c & 1],
            "commands": sorted({port.SNES_CMD[c] for c in both if c in port.SNES_CMD} | ({1} if 0 in both else set()))}


MP_REFILLS = 0x2EAF64         # patches.mp_refills: 8 bytes a character, `88 id 08 40 8C id 7F FE`


def mpparty(on, out, rom, spoiler, log):
    """`mpparty`: BC's party-rebuild event subroutine (CA/CBAF, run after every party select) restores MP to max
    beside the HP it restores (event command $8C id $7F after $8B id $7F)."""
    import ff6snes as S
    d = S.rom_bytes(rom)
    if bytes(d[MP_REFILLS:MP_REFILLS + 8]) != bytes([0x88, 0x00, 0x08, 0x40, 0x8C, 0x00, 0x7F, 0xFE]):
        log("bc codes: mpparty: BC's MP refills not found")
        return None
    log("bc codes: mpparty: MP refilled with HP after a party select")
    return {"on": True}


MEMENTO_HOOK = 0x20E9A        # C2/0E9A: BC's JSL into C4/B8CF (vanilla EB): the stat loader adds a hidden relic
MEMENTO_RELIC = 0x4B8F3       # C4/B8E4 + $11 x id: `C9 id D0 0D AD xx 1E 29 bit D0 03 4C D2 B9 A9 RELIC 6B`


def mementomori(on, out, rom, spoiler, log):
    """`mementomori` (BC's draws: how many characters, who, which relics; read back from the stubs it writes): each
    chosen character's invisible 7th relic, {PR character status id: {"armor", "content", "snes"}}."""
    import ff6snes as S
    import idmap as M
    d = S.rom_bytes(rom)
    if d[MEMENTO_HOOK] != 0x48:
        log("bc codes: mementomori: BC's hidden-relic hook not found")
        return None
    relics = {}
    for c in range(14):
        at = MEMENTO_RELIC + 0x11 * c
        if d[at - 15] != 0xC9 or d[at - 14] != c or d[at - 1] != 0xA9:
            continue
        r = d[at]
        m = M.item(r) if r != 0xFF else None
        if m and m[0] == "armor":
            relics[str(c + 1)] = {"armor": m[1], "content": M.content_id(*m), "snes": r}
    log(f"bc codes: mementomori: {len(relics)} hidden relics ({', '.join(f'{k}: armor {v['armor']}' for k, v in relics.items())})")
    return {"relics": relics}


MP_DIGITS = 0x263A8           # C2/63A8: BC's JSL into SilentEnigma's colour-coded MP digits (vanilla EB 09 0B 00)


def magicnumbers(on, out, rom, spoiler, log):
    """`magicnumbers`: MP damage and MP healing numbers in colours of their own (patch_mp_color_digits)."""
    import ff6snes as S
    d = S.rom_bytes(rom)
    if d[MP_DIGITS] != 0x22:
        log("bc codes: magicnumbers: BC's MP digit hook not found")
        return None
    return {"on": True}


INFORM_MISS = 0x22252         # C2/2252: BC's JSR into Bropedio's informative miss (vanilla B9 A1 3A)


def informativemiss(on, out, rom, spoiler, log):
    """`informativemiss`: "Null" (immune) and "Fail" (evaded) in place of Miss (the kit's SnesInformativeMiss)."""
    import ff6snes as S
    d = S.rom_bytes(rom)
    if bytes(d[INFORM_MISS:INFORM_MISS + 3]) != bytes([0x20, 0x38, 0x67]):
        log("bc codes: informativemiss: BC's hook not found")
        return None
    return {"on": True}


EQUIP_ANYTHING = 0x39B8B      # C3/9B8B: BC's `80 04` (vanilla F0 04): the hand slots' "weapon or shield" test skipped


def equipanything(on, out, rom, spoiler, log):
    """`equipanything` (patches C3/9B8B and C3/9B99): any item can go in either hand."""
    import ff6snes as S
    d = S.rom_bytes(rom)
    if d[EQUIP_ANYTHING] != 0x80:
        log("bc codes: equipanything: BC's patch not found")
        return None
    return {"on": True}


# the codes that are plugin code (plugin/BcPlugin/BcCodes.cs), each: (flags, out, rom, spoiler, log) -> its part
PLUGIN_CODES = {"equipanything": equipanything, "mementomori": mementomori, "magicnumbers": magicnumbers, "informativemiss": informativemiss, "l": blitz_inputs, "levelcap": levelcap, "cursepower": cursepower, "norng": norng,
                "playsitself": playsitself, "mpparty": mpparty}


def plugin_part(out, rom, spoiler, flags, log=print):
    """bc_battle.json's "codes": what BcCodes.cs needs for the seed's codes that are plugin code."""
    on = flag_values(flags)
    part = {}
    for code, make in PLUGIN_CODES.items():
        if code in on:
            v = make(on, out, rom, spoiler, log)
            if v is not None:
                part[code] = v
    return part


# --- data that needs BC's ROM (bc_battle.py runs rom_data before the battle parts) ---------------------------
NATURAL_TABLE = 0x300C6C      # F0/0C6C (Myself's NATURAL_MAGIC_TABLE): 12 characters x 16 (spell, level), FF = none
NATURAL_HOOK = 0xA182         # C0/A182: BC's `JSL $F00C00` (vanilla: the CMP/BEQs to Terra's and Celes's lists)
CELES_LIST = 0x2CE3E0
TERRA_JOB2 = 19              # port_spells.NATURAL: Terra's list is on PR jobs 1 and 19


def natural_magic(out, rom, log=print):   # not run in a seed (see rom_data): parked Bushido/Blitz rows
    """Natural magic as BC teaches it (BC's manage_natural_magic, run with `o` (shuffle commands) or `supernatural`):
    each character's 16-spell list from BC's table, learned by level in battle and on the field (F0/0BD9,
    F0/0C00); Terra's vanilla list is gone in every BC seed, Celes's stays only where BC left C0/A186's branch.
    Since 2026-11-20 the shared porter reads this itself (port_spells.natural_learners follows BC's JSL), so
    rom_data no longer runs this: it is kept as a reader for tests (it also parked the Bushido/Blitz rows)."""
    import ff6snes as S
    import idmap as M
    import prdata as P   # P.VANILLA_ROM: Celes's vanilla list below (TODO ROM-free: read it from bc_base.bin)
    import bc_commands
    d = S.rom_bytes(rom)
    if bytes(d[NATURAL_HOOK:NATURAL_HOOK + 4]) != bytes([0x22, 0x00, 0x0C, 0xF0]):
        log("bc codes: natural magic: not BC's (left as ported)")
        return None
    lists = {}
    for c in range(12):
        row = d[NATURAL_TABLE + 32 * c: NATURAL_TABLE + 32 * c + 32]
        seen, pairs = set(), []
        for i in range(0, 32, 2):
            if row[i] != 0xFF and row[i] not in seen:
                seen.add(row[i])
                pairs.append((row[i], row[i + 1]))
        if pairs:
            lists[c] = pairs
    if bytes(d[NATURAL_HOOK + 4:NATURAL_HOOK + 6]) == bytes([0xC9, 0x06]):
        celes = S.rom_bytes(P.VANILLA_ROM)[CELES_LIST:CELES_LIST + 32]
        have = {sp for sp, _ in lists.get(6, [])}
        lists.setdefault(6, []).extend((celes[i], celes[i + 1]) for i in range(0, 32, 2)
                                       if celes[i] != 0xFF and celes[i] not in have)
    t = bc_commands._tables(out, ["learning", "content"])
    le, ct = t["learning"], t["content"]
    spell_content = {int(r["type_value"]): int(r["id"]) for r in ct.rows.values() if r["type_id"] == "4"}
    jobs = {c: [c + 1] + ([TERRA_JOB2] if c == 0 else []) for c in range(12)}   # Terra has a second PR job
    ids = sorted(k for k, r in le.rows.items() if r["type_id"] == "1" and (1 <= int(r["job_id"]) <= 12 or int(r["job_id"]) == TERRA_JOB2))
    template = ids[0] if ids else None
    want = []
    for c, pairs in sorted(lists.items()):
        for spell, lv in pairs:
            k = M.spell(spell)
            if k in spell_content:
                want.extend((job, lv, spell_content[k]) for job in jobs[c])
    if template is None and want:
        log("bc codes: natural magic: no level-learning row to copy")
        return None
    for i, (job, lv, content) in enumerate(want):
        if i < len(ids):
            rid = ids[i]
        else:
            rid = max(le.rows) + 1
            le.rows[rid] = dict(le[template], id=str(rid))
        le.rows[rid].update({"type_id": "1", "value1": str(lv), "value2": "0", "job_id": str(job), "content_id": str(content)})
    for rid in ids[len(want):]:
        le.rows[rid].update({"type_id": "0", "job_id": "0", "value1": "0", "value2": "0"})   # parked (port_spells.neutralize)
    bc_commands._write(out, t)
    who = ", ".join(f"character {c} ({len(p)})" for c, p in sorted(lists.items())) or "nobody"
    log(f"bc codes: natural magic as BC teaches it: {who}; {len(want)} rows")
    return {str(c + 1): [[M.spell(s), lv] for s, lv in p] for c, p in lists.items()}


SWDTECH_GAUGE = 0x17D84       # C1/7D84: the SwdTech gauge step (patches.change_swdtech_speed)
SWDTECH_SPEEDS = {bytes([0xA5, 0x0E, 0x29, 0x00]): ("fast", 4), bytes([0xAD, 0x82, 0x7B, 0x18, 0x69, 0x02]): ("faster", 8),
                  bytes([0xAD, 0x82, 0x7B, 0x18, 0x69, 0x04]): ("fastest", 16)}
BUSHIDO = range(124, 132)     # the PR's eight techniques (Fang .. Oblivion)


def swdtechspeed(out, rom, log=print):
    """`swdtechspeed` (its Random already rolled by BC: read back from C1/7D84): the SNES's gauge climbs a
    level every 128 frames, x4 / x8 / x16 faster; the PR charges a chosen technique for its ability_wait
    (Fang 3 .. Oblivion 17) in the background, so the waits go down by the same factor (as WC's -fst / 4)."""
    import ff6snes as S
    import bc_commands
    d = S.rom_bytes(rom)
    speed = next(((name, f) for code, (name, f) in SWDTECH_SPEEDS.items()
                  if bytes(d[SWDTECH_GAUGE:SWDTECH_GAUGE + len(code)]) == code), None)
    if speed is None:
        return None
    name, factor = speed
    t = bc_commands._tables(out, ["ability"])
    ab = t["ability"]
    waits = {}
    for aid in BUSHIDO:
        row = ab.rows[aid]
        want = str(max(1, round(int(row["ability_wait"]) / factor)))
        waits[aid] = (row["ability_wait"], want)
        row["ability_wait"] = want
    bc_commands._write(out, t)
    log(f"bc codes: swdtechspeed {name}: Bushido charge times / {factor} ({', '.join(f'{a}->{b}' for a, b in waits.values())})")
    return {"speed": name, "factor": factor}


BERSERKER = 0x21618           # C2/1617 `CMP #id`: who acts as Umaro (vanilla $0D; `u` writes BC's pick)
UMARO_GROUP = "4"             # character_status.initial_condition_group 4: condition 59 (ConditionType Umalo)
UMARO_STATUS = 14


def umaro_risk(out, rom, flags, log=print):
    """`u` (Umaro risk: BC's random berserker, read back from C2/1617): the PR makes Umaro act on his own through
    his starting condition (character_status 14's initial_condition_group 4: condition 59, the PR's Umalo
    behaviour and attack pick, ActSelectUmalo); the berserker gets it and Umaro loses it. His commands and the
    orbs' equip masks are data the porter carries. Not carried: Umaro's Equip menu lock and the Blizzard Orb's
    Storm swap (C2/1711)."""
    if "u" not in flag_values(flags):
        return None
    import ff6snes as S
    import bc_commands
    d = S.rom_bytes(rom)
    who = d[BERSERKER]
    if who > 13 or who == 13:
        log(f"bc codes: u: berserker {who} (Umaro stays himself)")
        return None
    t = bc_commands._tables(out, ["character_status"])
    cs = t["character_status"]
    if who + 1 not in cs.rows:
        return None
    cs[UMARO_STATUS]["initial_condition_group"] = "0"
    cs[who + 1]["initial_condition_group"] = UMARO_GROUP
    bc_commands._write(out, t)
    log(f"bc codes: u: character {who + 1} is the berserker (Umaro's starting condition), Umaro acts normally")
    return {"berserker": who + 1}


def rom_data(out, rom, flags, log=print):
    """The data codes that need BC's ROM; returns what they did for bc_battle.json."""
    done = {}
    u = umaro_risk(out, rom, flags, log)
    if u is not None:
        done["u"] = u
    sw = swdtechspeed(out, rom, log)
    if sw is not None:
        done["swdtechspeed"] = sw
    # natural magic as BC teaches it: the shared porter's since 2026-11-20 (port_spells.natural_learners follows
    # BC's JSL at C0/A182 into its F0/0C6C table); natural_magic() below stays only as a reader for tests
    return done
