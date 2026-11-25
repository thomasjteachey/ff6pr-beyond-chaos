"""A guide to a Beyond Chaos seed for someone who has never played Beyond Chaos (the user, 2026-11-20:
"explain what Random and Chain means. basically explain everything a new player might not know about
beyond chaos"; shown in the game right after its opening controls tutorial, and on the Beyond Chaos
screen).

Built per seed from its flags and its data, and only for what this port carries (a flag whose effect isn't
in the Pixel Remaster yet isn't explained as if it were): the seed's own new commands one by one (what
Random, Chain, Double, a combo do, with the skills and odds), the "?" on equipment, rerolled equipment,
espers, monsters, treasure, shuffled commands, the boosts. Each page is a title and a few short lines (the
game's message window shows three or four).

bc_seed.py writes the pages into bc_seed.json ("guide") and the in-game guide into the seed (write_in_game):
a question, then each page in the game's own message window, the way the Narshe school's lessons are written
(E0023_00_007_a_02: "-Title-" on its own line, pages split by <P>, the window wrapping the text). Its script,
sc_bc_guide, sits in the map of the opening's last scene (Map_20010, Narshe's outskirts, game map 3); BcGuide.cs
starts it when that scene's controls tutorial (sc_e_0001_5's ShowHelpAndExit: the field help) closes.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401

# --- the in-game guide ---------------------------------------------------------------------------------
GUIDE_SCRIPT = "sc_bc_guide"
GUIDE_GROUP, GUIDE_FOLDER, GUIDE_SUB = "map_20010", "Map_20010", "Map_20010"   # sc_e_0001_5's map (game map 3)
GUIDE_REL = f"{GUIDE_GROUP}/Assets/GameAssets/Serial/Res/Map/{GUIDE_FOLDER}/{GUIDE_SUB}/{GUIDE_SCRIPT}.json"
# the same script in another map's list (bc_events: worringtriad starts in the World of Ruin, game map 2)
GUIDE_COPIES = [f"map_10020/Assets/GameAssets/Serial/Res/Map/Map_10020/Map_10020/{GUIDE_SCRIPT}.json"]
GUIDE_KEY = "BC_GUIDE_{:02d}"     # its lines, in the seed's system_en (the game looks every message key up in one table)
WINDOW = 200                      # characters a message page holds (the game's own lessons run to 250, wrapped)
ROOM, SHORT = 250, 60             # ... at most, and a last page short enough to join the one before
NL = "\\n"                        # a line break as the game's text files write it
PAGE = "<P>" + NL                 # a new page, as the game's lessons write it


def _windows(text, limit=WINDOW):
    """Text -> message pages of at most `limit` characters, split between sentences (a sentence longer
    than a page is split between words)."""
    pieces = []
    for sentence in re.split(r"(?<=[.!?:])\s+(?=[A-Z(\"])", text.strip()):
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            pieces.append(sentence[:cut])
            sentence = sentence[cut:].lstrip()
        if sentence:
            pieces.append(sentence)
    pages, cur = [], ""
    for p in pieces:
        if cur and len(cur) + 1 + len(p) > limit:
            pages.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}" if cur else p
    if cur:
        pages.append(cur)
    # a short last page joins the one before when both fit the window's real room (no lone "Here is each one.")
    room = ROOM - (WINDOW - limit)   # a title over the first page takes its share of the room too
    if len(pages) > 1 and len(pages[-1]) < SHORT and len(pages[-2]) + 1 + len(pages[-1]) <= room:
        pages[-2:] = [pages[-2] + " " + pages[-1]]
    return pages


def _message(title, lines, limit=WINDOW):
    """One guide page as one message: "-Title-" over its first page, the rest on following pages."""
    pages = _windows(" ".join(lines), limit - len(title) - 2)
    first, rest = pages[0] if pages else "", " ".join(pages[1:])
    out = [f"-{title}-{NL}{first}"] + (_windows(rest, limit) if rest else [])
    return PAGE.join(out)


def in_game(pages, info, mode_label="Normal"):
    """The guide's messages, in order: the question (Yes: the rest; No: nothing), a message per page after the
    BC screen's first, the last word."""
    seed = info.get("seed", "")
    ask = (f"-Beyond Chaos-{NL}This is a Beyond Chaos game (seed {seed}, {mode_label} mode): much of Final Fantasy VI "
           f"has been shuffled or rerolled.{PAGE}Shall I explain what's different in this game?")
    out = [ask] + [_message(p["title"], p["lines"]) for p in pages[1:] if not p.get("screen")]
    out.append("That's all. These pages are also on the Beyond Chaos screen, on the title screen, with the seed's flags.")
    return out


def guide_script(count):
    """sc_bc_guide for `count` messages (0: the baseline's, which shows nothing): message 0 asks, Select
    (Yes/No), a No goes to the end (Branch MessageSelection = 1, as the school's lessons), then 1..count-1."""
    import pr_script as S
    ops = [S.label("Main")]
    if count:
        ops += [S.op("Msg", s=[GUIDE_KEY.format(0)]), S.op("Select"),
                S.op("Branch", i=[0, 1, "@no"], s=["MessageSelection", "＝", "imm"])]
        ops += [S.op("Msg", s=[GUIDE_KEY.format(n)]) for n in range(1, count)]
    # A branch directly to Exit leaves the question window visible over a
    # player-controlled field. Close it on both the Yes and No paths.
    ops += [S.label("no")] + ([S.op("MsgClose")] if count else []) + [S.op("Exit")]
    S._resolve(ops, 0)
    return {"SystemFlag": {"SkipInitialize": 0, "KeepPlayerPuppet": 0, "KeepBadStatusVisual": 0, "RidingVehicle": 0},
            "Segments": [{"Label": "Main", "EntryPoint": 0, "Count": len(ops)}],
            "ScriptLocal": [], "ScriptLocalValue": [], "Mnemonics": ops, "Animations": [],
            "Name": GUIDE_SCRIPT, "Title": {"main": "Beyond Chaos: the seed's guide (after the opening's controls tutorial)", "sub": ""}}


def write_script(path, count):
    import json
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(guide_script(count), ensure_ascii=False, separators=(",", ":")))


def write_in_game(out, pages, info, mode_label="Normal", log=print):
    """Into a packed seed folder: the messages (its system_en) and sc_bc_guide (files/). Returns the script's
    path (a managed file: bc_live.own_files) and the message count."""
    import seed_live as L
    texts = in_game(pages, info, mode_label)
    path = os.path.join(out, *L.MESSAGE_PATH.split("/"), "system_en.txt")
    with open(path, "a", encoding="utf-8", newline="") as f:
        for n, t in enumerate(texts):
            f.write(f"{GUIDE_KEY.format(n)}\t{t}\r\n")
    write_script(os.path.join(out, "files", *GUIDE_REL.split("/")), len(texts))
    for rel in GUIDE_COPIES:          # copies an earlier step placed in other maps (bc-events: worringtriad's WoR copy)
        if os.path.exists(os.path.join(out, "files", *rel.split("/"))):
            write_script(os.path.join(out, "files", *rel.split("/")), len(texts))
    log(f"bc guide in game: {len(texts)} messages, {sum(t.count('<P>') + 1 for t in texts)} windows")
    return GUIDE_REL, len(texts)


def _odds(abilities_rates):
    """[(name, rate %)] -> "Blizzard (38%), Blizzara (13%) ..." the likeliest first, at most 6."""
    items = sorted(abilities_rates, key=lambda x: (-x[1], x[0]))
    shown = [f"{n} ({r}%)" for n, r in items[:6]]
    more = len(items) - len(shown)
    return ", ".join(shown) + (f" and {more} more" if more > 0 else "")


TIMES = {2: "twice", 3: "three times", 4: "four times"}


def command_pages(commands, names, rates, replaced):
    """commands: bc_seed.json "commands" (PR command id -> its part); names: PR ability id -> name;
    rates: random group id -> [(ability id, rate %)]; replaced: PR command id -> the command it took the
    place of. Returns pages."""
    pages = []
    if not commands:
        return pages
    pages.append(("New commands", [
        "Some commands are new: Beyond Chaos made them for this game.",
        "They take the place of a usual command (whoever had it has the new one),",
        "cost no MP, and their names say what they do. Here is each one."]))
    for cid, c in sorted(commands.items(), key=lambda kv: int(kv[0])):
        name = c.get("name", "")
        was = replaced.get(int(cid), "")
        took = f"(It replaced {was}.)" if was else ""
        kind = c.get("kind")
        abilities = [names.get(a, f"skill {a}") for a in c.get("abilities", [])]
        lines = []
        if c.get("random_group") is not None:
            pool = [(names.get(a, f"skill {a}"), r) for a, r in rates.get(c["random_group"], [])]
            lines.append(f"Each use picks one at random: {_odds(pool)}.")
        if kind == "skill":
            lines.insert(0, f"Uses {abilities[0] if abilities else name}.")
        elif kind == "combo":
            lines.insert(0, f"Uses {' and then '.join(abilities)}, one after the other.")
        elif kind == "multiple":
            n = c.get("count", 2)
            what = (abilities[0] if abilities else "the skill") if c.get("random_group") is None                 else "a random pick (rolled each time)"
            lines.insert(0, f"Uses {what} {TIMES.get(n, f'{n} times')} in a row.")
        elif kind == "chain":
            lines.insert(0, "Uses the skill, then flips a coin: heads, it goes again (and again).")
        if took:
            lines.append(took)
        pages.append((name, lines))
    pages.append(("Command words", [
        "Random: each use picks a skill from its list at random.",
        "Double, Triple, ...: the same skill that many times in a row.",
        "Chain: again and again while a coin keeps landing heads. A + B: both, in order."]))
    return pages


# what each flag means to a newcomer, when this port carries it (the flag's "port" in bc_flags.json)
FLAG_PAGES = {
    "o": ("Shuffled commands", ["Characters' commands are shuffled: anyone may have Steal, Blitz, Runic,",
                                 "Lore, Throw... Check each character's commands in the menu."]),
    "q": ("Characters", ["Who can equip what has changed, and so have everyone's stats."]),
    "i": ("Equipment", ["Weapons, armor and relics are rerolled: their stats, elements, the spells",
                        "they cast or teach. Read an item's description before you rely on it."]),
    "questionablecontent": ("A ? after a name", ["A ? after an equipment's name means Beyond Chaos changed it a lot.",
                                                 "Its description starts with \"Changed:\" and says how."]),
    "e": ("Espers", ["Espers teach different spells, and their level-up bonuses changed.",
                     "Check each esper's spells and bonus before you equip it."]),
    "m": ("Monsters", ["Monsters' stats and skills are rerolled: an early monster may hit hard,",
                       "and what they steal or drop is different."]),
    "f": ("Battles", ["You meet different groups of monsters than usual, anywhere."]),
    "t": ("Treasure", ["Chests, shops, the Colosseum and monster drops are rerolled.",
                       "Some chests hold monsters: \"Monster-in-a-box!\" starts a battle."]),
    "g": ("Dances", ["Each Dance has different moves."]),
    "dancelessons": ("Dancing anywhere", ["A Dance never stumbles on the wrong terrain."]),
    "c": ("Names and colors", ["The characters have new names and new colors."]),
    "makeover": ("New looks", ["Some characters, and guests like Leo, Banon and Kefka, look like people from other games",
                               "(Beyond Chaos's sprite pack). Only the look changes: their abilities, stats and story stay",
                               "their own, and their menu portrait changes with them."]),
    "s": ("Swapped looks", ["The original cast's looks are shuffled: someone may look like Celes or Sabin.",
                            "Who they are doesn't change."]),
    "remonsterate": ("New monsters", ["Monsters show pictures from other games, in battle and in the bestiary.",
                                      "Only the picture changes: names, stats, attacks and drops are the seed's."]),
    "n": ("Windows", ["The menus' windows have new colors."]),
    "z": ("Dash", ["You always dash, as if wearing Sprint Shoes."]),
    "shadowstays": ("Shadow", ["Shadow never leaves the party after a battle."]),
    "easymodo": ("Easy mode", ["Every monster has 1 HP."]),
    "canttouchthis": ("Invincible", ["Your party has 255 Defense and Magic Defense and very high evasion."]),
    "madworld": ("No tiers", ["Monsters and shops ignore the usual early/late order: anything goes anywhere."]),
    "nomiabs": ("No monster boxes", ["No chest holds a monster."]),
    "naturalmagic": ("Natural magic", ["Espers and equipment teach no spells: characters learn them by level."]),
    "penultima": ("No Ultima", ["Ultima can't be learned."]),
    "randombosses": ("Bosses", ["Bosses' skills are rerolled too."]),
    # bc-events (light events): shown once each flag's port status isn't "no" (bc_flags_export)
    "j": ("The Phantom Forest", ["The Phantom Forest's paths are shuffled: a path may lead somewhere else, even back",
                                 "where you came from. Keep trying the exits to find the way to the train."]),
    "k": ("The Zozo clock", ["The clock in Zozo shows a different time, and the townsfolk's hints changed to match.",
                             "Most of them lie, as always: trust what the honest ones agree on."]),
    "lessfanatical": ("The Cultists' Tower", ["In the Cultists' Tower you can use every command, not only Magic."]),
    "regionofdoom": ("Doom Gaze", ["On the Falcon's deck the wheel offers \"(Find Doom Gaze.)\": it flies you straight into",
                                   "the fight instead of waiting for Doom Gaze to find you in the sky."]),
    "worringtriad": ("World of Ruin", ["The game starts in the World of Ruin with Celes and one more character, the World of",
                                       "Balance's treasure, many items and espers, and 50,000 gil. Find your friends again."]),
    "h": ("The final battle", ["Your parties for the final battle are chosen at random: there's no party menu before it."]),
    "airship": ("The airship", ["Once you leave Narshe, the Blackjack waits outside; in the World of Ruin an airship waits",
                                "too. Any chocobo stable calls the airship for free. Going places early can leave you stuck."]),
    "notawaiter": ("Fewer cutscenes", ["Most story scenes up to Kefka at Narshe (and a few later) are cut: their battles and",
                                       "rewards stay. The Mobliz letters can all be sent at once for 2500 gil."]),
    "r": ("Who's where", ["In the World of Ruin, your friends wait in different places than usual: someone else may be",
                          "in Mt. Zozo, the Phoenix Cave or Mobliz. One of them joins when you get the Falcon."]),
    "mimetime": ("A familiar face", ["Gogo hides in the World of Ruin looking like one of your friends. Bring that friend",
                                     "along and talk to him."]),
    "alasdraco": ("A new opera", ["The opera house stages a different show: new singers in Maria's, Draco's and Ralse's",
                                  "roles, a new Impresario, other armies at war and something else to throw from the",
                                  "balcony. The story and the music's timing stay the same."]),
    "rushforpower": ("Vargas", ["Vargas on Mt. Kolts fights as in the original game: hurt him once and the next part",
                                "of the fight begins."]),
}


def looks_page(sprites, names):
    """Who's who: each character this seed renamed ({usual name: new name}, from its MSG_CHAR_NAME keys)
    and/or gave another look ({usual name: look}, bc_seed.json "sprites" from the sprite step). A new name
    hides who someone is (their abilities and story are still Terra's), so it comes first."""
    pairs = []
    for slot in list(names) + [s for s in sprites if s not in names]:
        new, look = names.get(slot), sprites.get(slot)
        if new and new != slot:
            pairs.append(f"{new} is {slot}" + (f" (looks like {look})" if look and look not in (new, slot) else ""))
        elif look and look != slot:
            pairs.append(f"{slot} looks like {look}")
    if not pairs:
        return None
    return ("Who's who", [", ".join(pairs) + "."])


def boosts(flags):
    out = []
    for code, what in (("expboost", "EXP"), ("gpboost", "gil"), ("mpboost", "AP")):
        v = flags.get(code)
        if v and v != "True":
            out.append(f"{what} x{v[:-2] if v.endswith('.0') else v}")
    return [("Rewards", [f"Battles give {', '.join(out)}."])] if out else []


def build(flag_string, info, flags_json, names, rates, replaced, mode_label="Normal"):
    """The guide's pages for one seed: [{"title", "lines"}]."""
    flags = {}
    for tok in flag_string.split():
        k, _, v = tok.partition(":")
        flags[k] = v or "True"
    port = {k: d.get("port", "no") for k, d in flags_json.get("flags", {}).items()}
    pages = [("Beyond Chaos", [
        f"This is a Beyond Chaos game (seed {info.get('seed')}, {mode_label}): much of Final Fantasy VI",
        "has been shuffled or rerolled. The next pages explain what's different in this one.",
        "They're on the Beyond Chaos screen too (title screen), with the seed's flags."])]
    pages += command_pages(info.get("commands") or {}, names, rates, replaced)
    for code, page in FLAG_PAGES.items():
        if code in flags and port.get(code, "no") not in ("no", "na", "later"):   # only what the port carries
            if code == "c" and "m" in flags:
                page = (page[0], page[1] + ["Monsters wear new colors too, and some have another monster's shape."])
            pages.append(page)
    looks = looks_page(info.get("sprites") or {}, info.get("character_names") or {})
    if looks:
        pages.append(looks)
    pages += boosts(flags)
    return [{"title": t, "lines": lines} for t, lines in pages]


def for_seed(out, flag_string, info, flags_json_path, log=print):
    """From a packed seed folder (its tables: ability names, random groups, the replaced commands)."""
    import json
    import re
    import bc_commands
    import port
    import prdata as P
    t = bc_commands._tables(out, ["content", "ability_random_group"])
    _, msg = bc_commands._messages(out)
    names = {}
    for r in t["content"].rows.values():
        if r["type_id"] == "4":
            names[int(r["type_value"])] = re.sub(r"<[^>]+>", "", msg.get(r["mes_id_name"], "")).strip()
    rates = {}
    for r in t["ability_random_group"].rows.values():
        rates.setdefault(int(r["group_id"]), []).append((int(r["ability_id"]), int(r["invocation_rate"])))
    vmsg = P.messages("system", "en")
    vcmd = P.Table("command")
    replaced = {cid: re.sub(r"<[^>]+>", "", vmsg.get(vcmd.rows[cid]["mes_id_name"], "")).strip()
                for cid in vcmd.rows if str(cid) in (info.get("commands") or {})}
    flags_json = json.load(open(flags_json_path, encoding="utf-8")) if os.path.exists(flags_json_path) else {}
    # the characters' names in this seed (MSG_CHAR_NAME_01..14, set by the porter's character_names)
    info = dict(info)
    info["character_names"] = {vmsg[k]: re.sub(r"<[^>]+>", "", msg[k]).strip()
                               for k in (f"MSG_CHAR_NAME_{i:02d}" for i in range(1, 15))
                               if k in vmsg and k in msg and msg[k].strip() != vmsg[k].strip()}
    pages = build(flag_string, info, flags_json, names, rates, replaced, info.get("mode_label", "Normal"))
    pages += junction_pages(out)
    pages += bingo_pages(out)
    log(f"bc guide: {len(pages)} pages")
    return pages


def bingo_pages(out):
    """bingoboingo's cards (bc_seed writes them as bingo_<n>.txt in the seed folder, from BC's run): a page in the
    game saying where they are, and each card itself on the Beyond Chaos screen (a 5x5 grid is too wide for the
    game's text box)."""
    import glob
    cards = sorted(glob.glob(os.path.join(out, "bingo_*.txt")))
    if not cards:
        return []
    names = [os.path.basename(c) for c in cards]
    pages = [{"title": "Beyond Chaos Bingo",
              "lines": [f"This seed comes with {len(cards)} bingo card{'s' if len(cards) > 1 else ''}: abilities, items,",
                        "monsters and spells to use, find or beat, each worth points.",
                        "The card is on the Beyond Chaos screen (title screen) and in",
                        f"the seed's folder: {', '.join(names)}."]}]
    for c in cards:
        with open(c, encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip() for ln in f.read().splitlines()]
        pages.append({"title": f"Bingo card ({os.path.basename(c)})", "lines": lines, "screen": True})
    return pages


def junction_pages(out):
    """The seed's junction effects (tools/bc_junction.guide_pages, from bc_battle.json's "junction", which
    bc_battle.apply writes: the guide step runs after it). The intro page in the game too; the effects one by
    one (~40 pages on a full seed) only on the Beyond Chaos screen ("screen": True)."""
    import json
    path = os.path.join(out, "bc_battle.json")
    if not os.path.exists(path):
        return []
    part = (json.load(open(path, encoding="utf-8")) or {}).get("junction")
    if not part:
        return []
    import bc_junction
    pages = bc_junction.guide_pages(part)
    if not pages:
        return []
    # the intro shows in the game too, where the effect pages don't follow it
    intro = dict(pages[0], lines=[ln.replace("the next pages explain each one.",
                                             "each one is explained on the Beyond Chaos screen (title screen).")
                                  for ln in pages[0]["lines"]])
    return [intro] + [dict(p, screen=True) for p in pages[1:]]
