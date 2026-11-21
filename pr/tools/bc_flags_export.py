"""Beyond Chaos's flags for the in-game options screen: plugin/BcPlugin/bc_flags.json.

  .venv/Scripts/python tools/bc_flags_export.py [OUT]

Read from BC's own definitions (options.py: Flag / Mode dataclasses with description, category,
input type, choices, range, conflicts, requirements, children; the makeover sprite categories
from custom/spritereplacements.txt; presets from config.py), in the schema of WC's wc_flags.json
(tools/wc_flags_export.py) that the kit's flag model reads (plugin/PrKit/Seeds/Flags.cs), plus:
  "style": "colon"   a flag string is BC's: `name` for a switch, `name:value` otherwise
  "modes": [...]     BC's modes (name, label, description, forced and prohibited flags, ported)
  per flag: "code" (BC's own name, shown beside the label), "conflicts", "requires" (any of
  [{flag: value or "*"}] sets), "special" (a value below the range: "random"), "port" (does the
  Pixel Remaster port carry its effect: yes / partly / no).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
import bc_run  # noqa: E402

OUT = os.path.join(ROOT, "plugin", "BcPlugin", "bc_flags.json")

SECTIONS = [("core", "Core"), ("characters", "Characters"), ("battle", "Battle"), ("field", "Field"),
            ("quality_of_life", "Quality of life"), ("sprites", "Sprites"), ("sprite categories", "Sprite categories"),
            ("aesthetic", "Aesthetic"), ("experimental", "Experimental"), ("gamebreaking", "Gamebreaking"),
            ("holiday", "Holiday")]
HIDDEN_CATEGORIES = {"cave"}       # set by the cave modes themselves

# Labels in plain words and the Pixel Remaster's vocabulary (BC's descriptions are all-caps program
# names such as "CHANGE SWDTECH SPEED MODE"); BC's code stays beside them on the screen
LABELS = {
    "b": "Fix exploits", "c": "Random palettes and names", "d": "Random final dungeon", "e": "Random espers",
    "f": "Random formations", "g": "Random dances", "h": "Random final party", "i": "Random equipment",
    "j": "Random Phantom Forest", "k": "Random Zozo clock", "l": "Random Blitz inputs", "m": "Random monster stats",
    "n": "Random window colours", "o": "Shuffle commands", "p": "Random animation palettes",
    "q": "Random character stats and equipment", "r": "Shuffle World of Ruin recruits", "s": "Swap character sprites",
    "t": "Random treasure, shops and drops", "u": "Umaro's berserk for someone", "w": "Replace commands",
    "y": "Shuffle magicite", "z": "Always dash",
    "allcombos": "All combo skills", "canttouchthis": "Invincible party", "desperation": "Desperation attacks",
    "endless9": "Endless nine (9x skills)", "levelcap": "Level cap", "cap_type": "Cap type", "cap_min": "Lowest cap",
    "cap_max": "Highest cap", "mementomori": "Innate relics", "metronome": "Random Chaos for everyone",
    "naturalmagic": "Natural magic only", "naturalstats": "No esper stat bonuses", "nocombos": "No combo skills",
    "penultima": "No Ultima", "replaceeverything": "Replace every skill", "shadowstays": "Shadow stays",
    "supernatural": "Natural magic for every caster", "suplexwrecks": "Suplex mode (everyone is Sabin)",
    "collateraldamage": "Item break mode", "cursepower": "Cursed Shield battles", "dancelessons": "No dance failures",
    "dancingmaduin": "Restricted espers", "darkworld": "Slasher's delight (hard mode)",
    "easymodo": "Easy mode (monsters have 1 HP)", "electricboogaloo": "Wild item breaks", "expboost": "EXP multiplier",
    "gpboost": "Gil multiplier", "lessfanatical": "Easy Fanatics' Tower", "madworld": "Tierless (tiers for fears)",
    "masseffect": "Wild equipment effects", "mpboost": "AP multiplier", "nobreaks": "No item breaks",
    "norng": "No randomness in battle", "playsitself": "Autobattle", "randombosses": "Random boss skills",
    "rushforpower": "Old Vargas fight", "swdtechspeed": "Bushido gauge speed", "unbreakable": "Unbreakable items",
    "bsiab": "Unbalanced monster boxes", "cursedencounters": "Expanded encounters",
    "dearestmolulu": "No random encounters", "fightclub": "Hidden Colosseum rewards", "mimetime": "Hidden Gogo",
    "morefanatical": "Harder Fanatics' Tower", "nomiabs": "No monster boxes", "randomboost": "Randomness boost",
    "thescenarionottaken": "Divergent paths", "worringtriad": "Start in the World of Ruin",
    "alphalores": "Lores in alphabetical order", "informativemiss": "Informative misses",
    "magicnumbers": "Coloured MP numbers", "mpparty": "Party change refills MP",
    "nicerpoison": "Less poison pixelation", "questionablecontent": "Mark changed items with ?",
    "regionofdoom": "Doom Gaze finder", "relicmyhat": "Combined equipment menus", "removeflashing": "Remove flashing",
    "slowerbg": "Slower scrolling backgrounds", "tastetherainbow": "Cycling status auras",
    "bravenudeworld": "Everyone looks like Esper Terra", "kupokupo": "Moogle party", "makeover": "New character sprites",
    "novanilla": "No original sprites", "frenchvanilla": "Original sprites as likely as new",
    "cloneparty": "Clone party", "partyparty": "Guest sprites in the mix", "quikdraw": "Imperial soldier party",
    "animals": "Animal sprites", "anime": "Anime sprites", "boys": "Boy sprites", "generic": "Generic sprites",
    "girls": "Girl sprites", "kids": "Kid sprites", "object": "Object sprites",
    "alasdraco": "Random opera", "bingoboingo": "Bingo cards", "capslockoff": "Mixed-case names",
    "johnnyachaotic": "Chaotic music", "johnnydmad": "New music", "notawaiter": "Cutscene skips",
    "remonsterate": "New monster sprites",
    "effectmas": "Junction effects on equipment", "effectory": "Junction effects on relics",
    "effectster": "Junction effects on monsters", "espercutegf": "Summoner mode",
    "espffect": "Junction effects on espers", "jejentojori": "Innate relic junctions",
    "strangejourney": "Bizarre adventure (entrances)", "treaffect": "Monsters' item junction effects",
    "airship": "Airship from the start", "equipanything": "Equip anything", "sketch": "Sketch glitch",
}

# Does the Pixel Remaster port carry the flag's effect (2026-11-20)? "yes": BC's randomized data,
# which the porter carries; "partly"; "no": assembly, events, sprites or music still to port (the
# flag still changes the seed's data as BC does); "na": no bearing on the Pixel Remaster; "later": planned
# for a later stage of the port (the reasons for na and later: PORT_NOTE, shown first in the flag's help).
PORT = {
    "b": "partly", "c": "partly", "e": "yes", "f": "yes", "g": "partly", "i": "partly", "m": "yes", "o": "partly",
    "q": "yes", "s": "partly", "t": "partly", "z": "yes",
    "canttouchthis": "yes", "easymodo": "yes", "madworld": "yes", "randomboost": "yes", "nomiabs": "yes",
    "cursedencounters": "yes", "randombosses": "yes", "penultima": "yes", "naturalmagic": "partly",
    "darkworld": "partly", "masseffect": "partly", "bsiab": "partly", "questionablecontent": "yes",
    "capslockoff": "yes", "nicerpoison": "na", "slowerbg": "na", "bingoboingo": "yes",
    # BC writes these into the monsters' EXP / gil and the formations' AP: data the porter carries
    "expboost": "yes", "gpboost": "yes", "mpboost": "yes",
    "dancelessons": "yes",          # tools/bc_codes.py
    # carried since (2026-11-20 survey of the code that landed: bc_codes, BcPlugin, PrKit/Ff6, bc_sprites, bc_palettes)
    "alphalores": "yes",            # bc_codes: the Lore list's sort order
    "cursepower": "yes",            # BcCursePower
    "mpparty": "yes",               # BcMpParty
    "swdtechspeed": "yes",          # Bushido's gauge waits
    "naturalstats": "yes",          # esper bonuses off (seed_info.esper_bonus -> SnesEsperBonus)
    "nobreaks": "yes", "unbreakable": "yes",     # bc_items
    "l": "yes",                     # Blitz inputs (PrKit SnesBlitzInputs)
    "n": "yes",                     # window colours (bc_palettes)
    "levelcap": "partly",           # the cap (BcLevelCap); EXP split and the Status screen's next level: not yet
    "supernatural": "partly",       # natural magic lists (bc_codes); starting Lores, teaching at join: not yet
    "u": "partly",                  # Umaro's risk moves; Storm and Umaro's equipment: not yet
    "collateraldamage": "partly",   # breaks, Fight + Item, monsters' items; Tools not yet
    "electricboogaloo": "partly",   # as `i`; skills that aren't magic as item spells: to check
    "dearestmolulu": "partly",      # no encounters; the Moogle Charm's battle every step: not yet
    "dancingmaduin": "partly",      # the Paladin Shield's spell; which characters may equip each esper: not yet
    # bc-sprites (2026-11-20): makeover and its options, s, c's colours (names: porter character/monster names)
    "makeover": "yes", "s": "yes", "c": "yes", "remonsterate": "yes",
    # no bearing / later (the reasons are in PORT_NOTE)
    "p": "na", "sketch": "na", "relicmyhat": "na", "tastetherainbow": "na", "removeflashing": "na",
    "equipanything": "partly", "morefanatical": "later", "thescenarionottaken": "later",
    "fightclub": "partly",          # the Colosseum's rewards hidden (BcData + kit SnesColiseum); running from its fights: not yet
    # bc-seeds (2026-11-20): `t`'s last parts: event gifts (bc_gifts), auction (bc_data + BcData), starting gil, the
    # Colosseum (BcData); bsiab's boxes are in chests only (BC's event gifts never hold monsters)
    "t": "yes", "bsiab": "yes",
    # y (bc_gifts.espers): every esper gift, the lines naming them, the Phoenix Cave, the Ragnarok sword's name, the
    # bosses' names (porter); the esper bosses drawn as their replacements (BC copies the art): not yet
    "y": "partly",
    # bc-events (2026-11-21), passed in game (QA bc-5 / bc-6): the World of Ruin start, the Zozo clock, Shadow
    # stays, the final battle's random parties
    "worringtriad": "yes", "k": "yes", "shadowstays": "yes", "h": "yes",
    "strangejourney": "partly",     # 666/951 entrances rewired (bc_entrances), 55 per-world doors (BcEntrances); ~119 story-version doors keep their own
    "alasdraco": "partly",         # the opera's text and name boxes (bc-events, bc-6), its music (bc-music); the singers' sprites: bc-sprites
}

# why a flag is "na" or "later": the first words of its help on the Beyond Chaos screen
PORT_NOTE = {
    "nicerpoison": "An SNES display fix: the Pixel Remaster draws Poison its own way.",
    "slowerbg": "An SNES display fix: the Pixel Remaster scrolls its backgrounds its own way.",
    "p": "The Pixel Remaster's spell and weapon effects are its own particle art, not palette sprites.",
    "sketch": "The Sketch glitch is SNES memory corruption the Pixel Remaster doesn't have.",
    "relicmyhat": "The Pixel Remaster's equipment and shop screens already work this way.",
    "tastetherainbow": "SNES status-aura palette cycling; the Pixel Remaster draws status effects its own way.",
    "removeflashing": "Edits SNES animation scripts; the Pixel Remaster's effects are its own.",
    "equipanything": "Armor and relics can be held in a hand, as a shield is; items that aren't equipment can't (the game's equip lists hold only weapons and armor).",
    "morefanatical": "Later in this port (with the random final dungeon).",
    "thescenarionottaken": "Later in this port (Divergent paths).",
}


# help text where BC's own doesn't say what the player sees here
HELP = {
    "questionablecontent": "Equipment Beyond Chaos changed gets a ? after its name, and its description says what changed "
                           "(the spell it casts, elements, stats).",
}


def label(f):
    if f.name in LABELS:
        return LABELS[f.name]
    print(f"note: no label for {f.name}: BC's description used")
    text = (f.description or f.name).replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def number(x):
    return float(x) if isinstance(x, float) else int(x)


AUDIT = os.path.join(ROOT, "docs", "bc-audit.md")
AUDIT_PORT = {"tested": "yes", "ported": "yes", "partial": "partly", "missing": "no", "n/a": "na"}


def audit_ports(codes, path=AUDIT):
    """The port status of each flag from the source audit's checklist (pr/docs/bc-audit.md sections (a) and (b): the
    BC lead's, 2026-11-21): tested/ported -> yes, partial -> partly, missing -> no, n/a -> na, left out -> na only
    when the audit says its reason holds (else no: the audit counts it missing). A row may name several codes
    ("animals, anime, boys (7 rows, one each)"). {} without the audit (the public repo: PORT above then)."""
    import re
    if not os.path.exists(path):
        return {}
    text = open(path, encoding="utf-8").read()
    if "### (a) Flags" not in text or "### (c) Modes" not in text:
        return {}
    out = {}
    for line in text[text.index("### (a) Flags"):text.index("### (c) Modes")].splitlines():
        if not line.startswith("| ") or line.startswith(("| Feature", "|---")):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        status = cells[2].split()[0] if cells[2] else ""
        if status == "left":           # "left out"
            note = cells[-1]
            port = "na" if re.search(r"reason holds", note, re.I) and not re.search(r"counted as missing", note, re.I) else "no"
        else:
            port = AUDIT_PORT.get(status)
        if port is None:
            continue
        names = cells[0].split("(")[0]
        keys = [k.strip().strip("`") for k in names.split(",")] if "," in names else [names.split()[0].strip("`")]
        for k in keys:
            if k in codes:
                out[k] = port
    return out


def export(out=OUT):
    src = os.path.abspath(bc_run.SRC)
    cwd = os.getcwd()
    os.chdir(os.path.abspath(bc_run.HOME))
    sys._MEIPASS = src
    sys.path.insert(0, src)
    try:
        import options as O
        import config as C
        O.get_makeover_groups()
        normal = list(O.NORMAL_FLAGS) + list(O.MAKEOVER_MODIFIER_FLAGS)
        everything = {f.name: f for f in list(O.ALL_FLAGS) + list(O.MAKEOVER_MODIFIER_FLAGS)}
        modes = [{"name": m.name, "label": m.display_name, "help": m.description,
                  "forced": list(m.forced_flags), "prohibited": sorted(m.prohibited_flags),
                  "ported": m.name == "normal"} for m in O.ALL_MODES]
        presets = {k: " ".join(v.split()) for k, v in C.SUPPORTED_PRESETS.items()}
    finally:
        os.chdir(cwd)
    flags, sections = {}, []
    by_cat = {}
    port_of = {**PORT, **audit_ports({f.name for f in normal})}      # the audit wins where it has the flag
    for f in normal:
        if f.category in HIDDEN_CATEGORIES:
            continue
        by_cat.setdefault(f.category, []).append(f)
        d = {"label": label(f), "code": f.name, "help": HELP.get(f.name, f.long_description or ""), "port": port_of.get(f.name, "no")}
        if f.name in PORT_NOTE:
            d["help"] = PORT_NOTE[f.name] + "  " + d["help"]
        if f.input_type == "boolean":
            d["type"] = "bool"
        elif f.input_type == "integer":
            d.update(type="int", min=number(f.minimum_value), max=number(f.maximum_value), default=str(f.default_value))
        elif f.input_type == "float2":
            d.update(type="float", min=max(0.0, float(f.minimum_value)), max=float(f.maximum_value), default=str(f.default_value))
        elif f.input_type == "combobox":
            d.update(type="str", choices=[c.lower() for c in f.choices],
                     default=str(f.default_value).lower() if f.default_value != "" else f.choices[max(0, f.default_index)].lower())
        else:
            raise SystemExit(f"{f.name}: unknown input type {f.input_type}")
        if f.special_value_text:
            d["special"] = f.special_value_text.lower()
        if f.conflicts:
            d["conflicts"] = list(f.conflicts)
        if f.requirements:
            d["requires"] = [{k: ("*" if v == "*" else v if isinstance(v, str) else bool(v)) for k, v in r.items()}
                             for r in f.requirements]
        if f.children:
            d["children"] = list(f.children)
        flags[f.name] = d
    child_of = {c: p for p, d in flags.items() for c in d.get("children", [])}
    for cat, title in SECTIONS:
        fs = by_cat.pop(cat, [])
        if not fs:
            continue
        rows = []
        for f in sorted(fs, key=lambda f: (len(f.name) > 1, f.name)):    # the letter codes first, as BC lists them
            if f.name in child_of:
                continue
            rows.append({"kind": "flag", "flag": f.name})
            for c in flags[f.name].get("children", []):
                rows.append({"kind": "flag", "flag": c, "indent": 1})
        ported = {flags[r["flag"]]["port"] for r in rows}
        ported = {"yes" if p == "na" else "no" if p == "later" else p for p in ported}
        sections.append({"title": title, "port": "yes" if ported == {"yes"} else "no" if ported == {"no"} else "partly",
                         "rows": rows})
    if by_cat:
        raise SystemExit(f"categories without a section: {sorted(by_cat)}")
    # (christmas / halloween are BC's by date, not flags: activate_from_string reads NORMAL_FLAGS and the
    # sprite categories only)
    missing = [f.name for f in normal if f.name not in flags and f.category not in HIDDEN_CATEGORIES]
    if missing:
        raise SystemExit(f"flags left out: {missing}")
    doc = {"style": "colon", "version": bc_run.VERSION, "wc_version": bc_run.VERSION, "modes": modes,
           "flags": flags, "sections": sections, "presets": presets}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    print(f"{len(flags)} flags in {len(sections)} sections, {len(modes)} modes, {len(presets)} presets -> {out}")
    return doc


if __name__ == "__main__":
    export(sys.argv[1] if len(sys.argv) > 1 else OUT)
