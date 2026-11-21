"""Beyond Chaos's randomized data that the shared porter doesn't carry by itself, from BC's output into the seed
folder (tools/bc_seed.py runs apply() after packing). Reads only what BC writes, or data tables the ROM-free
generator ships (tools/bc_basedata.py), so a ROM-free seed is the same (tools/bc_parity.py).

  dances (g)        the eight dances' names BC gave them (0x26FF9D, 8 x 12): the PR's Dance list
                    (MSG_MAGIC_NAME_146..153), when BC renamed them
  starting gil (t)  BC's starting money (its event command 84 lo hi at CC/9A93): the PR's INIT_GIL
                    (initialize_data, a table the seed library sets live)
  Coral             BC's name for the Coral (every seed): the key item's name and description, its lines at
                    Ebot's Rock (story_mes_en; the baseline keeps their vanilla lines: bc_gamedata)
  auction (t)       the auction house's four sales' items (bc_seed.json auction_items, as WC's: the plugin's
                    auction hook gives them)
Returns {"dance_names": [...], "gil": n} for bc_seed.json.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
import ff6snes as S  # noqa: E402
import prdata as P  # noqa: E402
import seed_live  # noqa: E402

DANCE_NAMES = 0x26FF9D, 12, 8
DANCE_KEYS = [f"MSG_MAGIC_NAME_{146 + i}" for i in range(8)]
START_GIL = 0x0C9A93          # BC: 84 lo hi (give gil); vanilla's own 84 B8 0B is 3000, the PR's INIT_GIL too
TABLES = ["initialize_data"]  # beyond seed_live.MANAGED_TABLES (bc_live adds it)
# the auction house's four sales (BC's manage_auction_house with `t`: `6D item 45 45 45` written at each sale's
# give): vanilla item -> the address BC writes. As WC's info["auction_items"] (vanilla content -> the seed's),
# for the plugin's auction hook (WC's WcItems; for BC: the kit, when it moves)
AUCTION = {0xBC: 0x0B5012, 0xBD: 0x0B55A4, 0xC9: 0x0B56FF, 0xC0: 0x0B5C9F}
# the Coral (BC's manage_coral, every seed: a name from custom/coralnames.txt written at EF/C08, 12 bytes; its
# dialogue patch data/script/coral.txt puts it in the five lines about coral): the PR's key item name and
# description and its lines at Ebot's Rock
CORAL_NAME = 0x0EFC08
CORAL_KEYS = ("MSG_KEY_NAME_06", "MSG_KEY_INF_09")
CORAL_LINES = ["E0943_00_540_a_02", "E0943_00_540_a_11", "E0948_00_541_a_01", "E0948_00_541_a_02",
               "E0948_00_541_a_03", "E0948_00_541_a_04"]
STORY = "story_mes_en"
# the auctioneer's announcement of each sale (story_mes_en), by the sale's vanilla PR content
AUCTION_LINES = {287: "E0424_00_111_a_01", 288: "E1055_00_111_a_01", 291: "E0751_00_111_a_01", 300: "E0752_00_111_a_01"}
STORY_KEYS = CORAL_LINES + sorted(AUCTION_LINES.values())   # every story line a seed may change (the baseline's)


def dance_names(rom):
    at, size, n = DANCE_NAMES
    return [S.decode_name(rom[at + i * size:at + (i + 1) * size]).strip() for i in range(n)]


def _messages(out):
    path = os.path.join(out, *seed_live.MESSAGE_PATH.split("/"), "system_en.txt")
    lines, keys = [], {}
    with open(path, encoding="utf-8", newline="") as f:
        for i, line in enumerate(f.read().split("\r\n")):
            lines.append(line)
            if "\t" in line:
                keys[line.split("\t", 1)[0]] = i
    return path, lines, keys


def coral_name(rom):
    name = S.decode_name(rom[CORAL_NAME:CORAL_NAME + 12]).strip()
    if not name or "<" in name:
        return ""
    return name.title() if name.isupper() else name      # BC's capslockoff off: all capitals -> the PR's case


def story_lines(keys):
    """The game's own story_mes_en lines for these keys."""
    text = P.messages("story_mes", "en")
    return {k: text[k] for k in keys if k in text}


def coral(out, name):
    """BC's Coral name in the PR's words: the key item's name and description, the lines at Ebot's Rock (as BC's
    coral.txt: "coral" -> the name). Story lines go into the seed's story_mes_en (merged with any other step's)."""
    path, lines, keys = _messages(out)
    vals = {"MSG_KEY_NAME_06": "<IC_IOBJ>" + name,
            "MSG_KEY_INF_09": f"A piece of {name.lower()} found in the cave at Ebot's Rock."}
    for k, v in vals.items():
        if k in keys:
            lines[keys[k]] = f"{k}\t{v}"
        else:
            lines.append(f"{k}\t{v}")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(lines))
    story = os.path.join(out, *seed_live.MESSAGE_PATH.split("/"), STORY + ".txt")
    have = {}
    if os.path.exists(story):
        with open(story, encoding="utf-8") as f:
            for line in f.read().splitlines():
                if "\t" in line:
                    k, v = line.split("\t", 1)
                    have[k] = v
    for k, v in story_lines(CORAL_LINES).items():
        have[k] = v.replace("coral", name)
    os.makedirs(os.path.dirname(story), exist_ok=True)
    with open(story, "w", encoding="utf-8", newline="") as f:
        f.write("".join(f"{k}\t{v}\r\n" for k, v in have.items()))


def _story(out, lines):
    """Merges {key: text} into the seed's story_mes_en (other steps may write it too)."""
    story = os.path.join(out, *seed_live.MESSAGE_PATH.split("/"), STORY + ".txt")
    have = {}
    if os.path.exists(story):
        with open(story, encoding="utf-8") as f:
            for line in f.read().splitlines():
                if "\t" in line:
                    k, v = line.split("\t", 1)
                    have[k] = v
    have.update(lines)
    os.makedirs(os.path.dirname(story), exist_ok=True)
    with open(story, "w", encoding="utf-8", newline="") as f:
        f.write("".join(f"{k}\t{v}\r\n" for k, v in have.items()))


def content_name(content_id):
    """A PR content's name as the game shows it (system_en, its icon tag left out)."""
    import re
    row = P.Table("content").rows.get(int(content_id))
    text = P.messages("system", "en").get(row["mes_id_name"], "") if row else ""
    return re.sub(r"<[^>]*>", "", text).strip()


def auction_lines(out, sales):
    """The auctioneer names each sale's item (the PR's announcement lines; as WC's -ari: "...a fine <item>!")."""
    lines = {AUCTION_LINES[int(a)]: f"...a fine {content_name(b)}!" for a, b in sales.items() if int(a) in AUCTION_LINES}
    if lines:
        _story(out, lines)
    return lines


def prepare(capture):
    """In BC's run (bc_run.run's prepare): records each event gift as BC rerolls it (chestrandomizer.EventItem
    .mutate_contents: `t`, bsiab, nomiabs; ~40 gifts in events: items, gil, monster boxes). Records only: BC's draws
    are its own. capture["event_items"]: [{location, pointer, before, after}] with (type, contents, monster)."""
    import chestrandomizer as C
    rec = capture.setdefault("event_items", [])
    original = C.EventItem.mutate_contents
    if getattr(original, "_bc_data", False):
        return

    def state(e):
        return {"type": e.content_type, "contents": e.contents, "monster": bool(e.monster)}

    def mutate_contents(self, *a, **kw):
        before = state(self)
        out = original(self, *a, **kw)
        loc = next((k for k, v in C.get_event_items().items() if self in v), None)
        rec.append({"location": loc, "pointer": self.pointer, "before": before, "after": state(self)})
        return out

    mutate_contents._bc_data = True
    C.EventItem.mutate_contents = mutate_contents


def apply(out, rom, vanilla, flags, log=print):
    """rom, vanilla: BC's output and its input (bytes)."""
    info = {}
    names, van = dance_names(rom), dance_names(vanilla)
    if names != van and all(names):
        path, lines, keys = _messages(out)
        for k, name in zip(DANCE_KEYS, names):
            if k in keys:
                lines[keys[k]] = f"{k}\t{name}"
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("\r\n".join(lines))
        info["dance_names"] = names
        log(f"bc_data: dances named {', '.join(names)}")
    if rom[START_GIL] == 0x84 and rom[START_GIL:START_GIL + 3] != vanilla[START_GIL:START_GIL + 3]:
        gil = rom[START_GIL + 1] | rom[START_GIL + 2] << 8
        path = os.path.join(out, *seed_live.MASTER_PATH.split("/"), "initialize_data.csv")
        if os.path.exists(path):
            with open(path, encoding="utf-8", newline="") as f:
                table = P.Table("initialize_data", f.read())
        else:
            table = P.Table("initialize_data")
        for r in table.rows.values():
            if r["key_name"] == "INIT_GIL":
                r["value1"] = str(gil)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(table.to_csv(table.rows.keys()))
        info["gil"] = gil
        log(f"bc_data: starting gil {gil}")
    name = coral_name(rom)
    if name and name.lower() != "coral":
        coral(out, name)
        info["coral"] = name
        log(f"bc_data: the Coral is {name}")
    if "t" in flags.split():
        import idmap as M
        sales = {}
        for van_item, at in AUCTION.items():
            if rom[at] == 0x6D and rom[at + 2:at + 5] == bytes([0x45] * 3):
                a, b = M.item_content(van_item), M.item_content(rom[at + 1])
                if a and b and a != b:
                    sales[str(a)] = b
        if sales:
            info["auction_items"] = sales
            auction_lines(out, sales)
            log(f"bc_data: auction sales {sales}")
    return info
