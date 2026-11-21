"""Do Beyond Chaos's names fit the game's windows? Widths, not character counts (the user: no SNES
abbreviations; the PR's own translations show 11-13 characters in the battle command window).

  .venv/Scripts/python tools/bc_names.py request SEED_DIR REQ.json     # the strings to measure
  (in the game, headless: harness `textwidth REQ.json WIDTHS.json`, BcPlugin/BcHarness.cs)
  .venv/Scripts/python tools/bc_names.py report SEED_DIR WIDTHS.json   # what fits, what doesn't

The game's font bundles are obfuscated, so widths come from the game itself: a UI Text's preferred
width in each font its screens use. A list's limit is the widest name the game itself shows in it, in
any of its Latin-script languages (the PR sized its windows for them): commands (MSG_CMD_NAME), skills
(MSG_MAGIC_NAME), items (MSG_ITEM/WEAPON/ARMOR_NAME), monsters (MSG_MON_NAME), monster attacks
(MSG_MON_ATK). A name no wider than that fits; a wider one is reported with how far over it is.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
import prdata as P  # noqa: E402

LANGS = ["en", "de", "fr", "it", "es", "pt"]
LISTS = {
    "commands": ("MSG_CMD_NAME_",),
    "skills": ("MSG_MAGIC_NAME_",),
    "items": ("MSG_ITEM_NAME_", "MSG_WEAPON_NAME_", "MSG_ARMOR_NAME_"),
    "monsters": ("MSG_MON_NAME_",),
    "monster attacks": ("MSG_MON_ATK_",),
}
LONGEST = 30           # per list and language: the game's longest names by characters (the widest are among them)
# The real boxes, read in game (BcHarness `uitext`, 2026-11-20, in battle): width at font size 32, every one
# with best fit on (Unity shrinks a longer text down to size 3 rather than cutting it). The report scales
# them to the measuring size; a name past its box still shows, smaller.
BOXES = {
    "commands": 256,     # battle_info_window .../command_select_content/root/last_text
    "skills": 215,       # .../ability_scroll_content/ability_content/root/icon_text/last_text
    "items": 352,        # .../item_select_content/root/icon_text/last_text
}
BOX_SIZE = 32


def plain(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


_command_keys = None


def command_keys():
    """The text keys of the battle commands (command.csv rows 1-31; menu-only command names left out)."""
    global _command_keys
    if _command_keys is None:
        c = P.Table("command")
        _command_keys = {r[k] for r in c.rows.values() if int(r["id"]) <= 31 for k in ("mes_id_name", "mes_id_name2")} - {"None", ""}
    return _command_keys


def which(key):
    if key.startswith("MSG_CMD_NAME_") or key.startswith("MSG_SYSTEM_"):
        return "commands" if key in command_keys() else None
    return next((name for name, prefixes in LISTS.items() if key.startswith(prefixes)), None)


def seed_names(seed_dir):
    """The seed's names that differ from the game's (key -> text), by list."""
    import seed_live as L
    van = P.messages("system", "en")
    out = {}
    path = os.path.join(seed_dir, *L.MESSAGE_PATH.split("/"), "system_en.txt")
    for line in open(path, encoding="utf-8"):
        k, _, v = line.rstrip("\r\n").partition("\t")
        lst = which(k)
        if lst and v and v != van.get(k):
            out.setdefault(lst, {})[k] = plain(v)
    return out


def game_names():
    """The game's own names by list and language (the longest few of each)."""
    out = {}
    for lang in LANGS:
        try:
            msgs = P.messages("system", lang)
        except Exception:  # noqa: BLE001 - a language the extract doesn't have
            continue
        for lst in LISTS:
            names = {plain(v) for k, v in msgs.items() if which(k) == lst and plain(v)}
            out.setdefault(lst, {})[lang] = sorted(names, key=len, reverse=True)[:LONGEST]
    return out


def request(seed_dir, path):
    strings = set()
    for lst, by_lang in game_names().items():
        for names in by_lang.values():
            strings.update(names)
    for names in seed_names(seed_dir).values():
        strings.update(names.values())
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"strings": sorted(strings), "size": 40}, f, ensure_ascii=False, indent=0)
    print(f"{len(strings)} strings -> {path}")


def report(seed_dir, widths_path):
    w = json.load(open(widths_path, encoding="utf-8"))
    game = game_names()
    mine = seed_names(seed_dir)
    for font, widths in w["fonts"].items():
        print(f"== font {font} (size {w['size']})")
        for lst, by_lang in game.items():
            measured = [(widths[n], lang, n) for lang, names in by_lang.items() for n in names if n in widths]
            if not measured:
                continue
            widest_game, lang, widest = max(measured)
            box = BOXES.get(lst)
            limit = box * w["size"] / BOX_SIZE if box else widest_game
            print(f"  {lst}: box {limit:.0f} px" + (f" ({box} at size {BOX_SIZE})" if box else " (no box read: the widest name)") +
                  f"; the game's widest {widest_game:.0f} px ({lang} {widest!r})")
            for key, name in sorted(set(mine.get(lst, {}).items())):
                width = widths.get(name)
                if width is None:
                    continue
                verdict = "fits" if width <= limit else f"shown at {100 * limit / width:.0f}% size (best fit)"
                print(f"    {name!r:34} {width:6.0f}  {verdict}")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "request":
        request(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 4 and sys.argv[1] == "report":
        report(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
