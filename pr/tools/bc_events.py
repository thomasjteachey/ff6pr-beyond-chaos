"""Beyond Chaos's light events on the Pixel Remaster: BC's story/field flags as PR scripts, data and plugin calls.

  .venv/Scripts/python tools/bc_events.py files                 # the PR files any flag may change (the baseline's)
  .venv/Scripts/python tools/bc_events.py show OUT_DIR          # what a seed folder's bc_events.json holds

BC changes these flags in SNES event code, data and assembly; a seed here gets the same play from:
  * PR scripts (map_*/.../sc_*.json) rewritten per seed: a seed with the flag carries its copy in files/<rel>
    (the BeyondChaos Magicite folder's baseline has every such script as vanilla's, so a seed without it plays
    vanilla's: bc_live.own_files + write_baseline take FILES / write_baseline from here);
  * the seed's master tables (lessfanatical: the Cultists' Tower's battle script);
  * lines in the seed's system_en (BC_EV_* keys: the game looks every message key up in one table);
  * bc_events.json in the seed folder for plugin/BcPlugin/BcEvents.cs (SysCall "BC:<name>" in our scripts,
    the plugin's hooks: shadowstays, the final battle's order).
BC's own choices (a seed number must stay BC's exe's game) are read from BC's output ROM or captured where BC
makes them, never drawn here. bc_seed.py runs apply() after packing the port (its chest maps are in files/).
The plan per flag and what is tested how: bc-events.md in the BC lead's notes folder; PORTING.md "Beyond Chaos".
"""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401  (the modding kit's tools, when it's this repository's kit/ submodule)
import prdata as P  # noqa: E402
import pr_script as S  # noqa: E402
from pr_scene_cut import cut as condense, SHOW  # noqa: E402,F401  (the kit's scene cut: notawaiter)

EQ = "＝"
EVENTS_JSON = "bc_events.json"     # in the seed folder, for BcEvents.cs
KEY = "BC_EV_{}_{:02d}"            # the seed's lines (system_en): BC_EV_<flag>_<n>

# the flags this module ports (BC option names), in the order apply() runs them
# (thescenarionottaken: its own work, bc-13 "Divergent paths"; morefanatical: with `d`, bc-12)
FLAGS = ["lessfanatical", "shadowstays", "rushforpower", "h", "j", "k", "regionofdoom", "airship",
         "worringtriad", "r", "mimetime", "notawaiter", "alasdraco", "christmas", "halloween"]

# ---------------------------------------------------------------------------------------------------------
# the PR files any flag may change: every one is in the baseline as vanilla's (same list for every seed)

SCRIPTS = {}   # flag -> [script names] (each flag's section adds its own)
# map files (entity layers) a flag may rewrite: (map group folder, map, file)
MAP_FILES = {}
# scripts of our own, listed in their map's package.json by the baseline (an Exit-only script there):
# name -> (map group, map folder, map)
NEW_SCRIPTS = {}
# entity layers of our own (ev_*.json), listed in their map's package.json "entity" by the baseline (empty there):
# rel -> (map group, map folder, map, layer name)
NEW_LAYERS = {}

MAP_REL = "{group}/Assets/GameAssets/Serial/Res/Map/{folder}/{sub}/{file}"


def script_rel(name):
    return S.rel(name)


def new_rel(name):
    group, folder, sub = NEW_SCRIPTS[name]
    return MAP_REL.format(group=group, folder=folder, sub=sub, file=name + ".json")


def files():
    """Every Magicite file a BC seed's events may change (bc_live.own_files)."""
    out = []
    for names in SCRIPTS.values():
        out += [script_rel(n) for n in names]
    for entries in MAP_FILES.values():
        out += [MAP_REL.format(group=g, folder=f, sub=s, file=x) for g, f, s, x in entries]
    out += [new_rel(n) for n in NEW_SCRIPTS]
    out += list(NEW_LAYERS)
    import seed_live
    shared = set(seed_live.managed_files())     # chest maps the porter may write: in the baseline already (ours edit its copy)
    return sorted(set(out) - shared)


def empty_script(name, title):
    ops = [S.label("Main"), S.op("Exit")]
    return {"SystemFlag": {"SkipInitialize": 0, "KeepPlayerPuppet": 0, "KeepBadStatusVisual": 0, "RidingVehicle": 0},
            "ScriptLocal": ["なし"], "ScriptLocalValue": [0],
            "Segments": [{"Label": "Main", "EntryPoint": 0, "Count": len(ops)}], "Mnemonics": ops,
            "Name": name, "Title": {"main": title, "sub": ""}}


def write_baseline(out, add):
    """Into the BeyondChaos Magicite folder (bc_live.write_baseline's extra): every file in files() as vanilla's
    (our own scripts: Exit only) and our scripts in their maps' package.json. add(rel) for each file written."""
    import shutil
    for rel in files():
        dest = os.path.join(out, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        name = os.path.splitext(os.path.basename(rel))[0]
        if name in NEW_SCRIPTS:
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(empty_script(name, "Beyond Chaos (no seed: nothing)"), f, ensure_ascii=False, separators=(",", ":"))
        elif rel in NEW_LAYERS:
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(empty_layer(NEW_LAYERS[rel][3]), f, ensure_ascii=False, separators=(",", ":"))
        else:
            shutil.copyfile(os.path.join(P.VANILLA, *rel.split("/")), dest)
        add(rel)
    by_map = {}
    for name, (group, folder, sub) in NEW_SCRIPTS.items():
        by_map.setdefault((group, folder, sub), []).append(name)
    for (group, folder, sub), names in sorted(by_map.items()):
        S.list_in_map(out, group, folder, sub, sorted(names))
        add(f"{group}/Assets/GameAssets/Serial/Res/Map/{folder}/package.json")
    for rel, (group, folder, sub, layer) in sorted(NEW_LAYERS.items()):
        list_layer(out, group, folder, sub, layer)
        add(f"{group}/Assets/GameAssets/Serial/Res/Map/{folder}/package.json")


def empty_layer(name, objects=()):
    """An entity layer file (a Tiled group with one object group), as the game's ev_*.json are."""
    return {"id": 20, "name": name, "opacity": 1, "type": "group", "visible": True, "x": 0, "y": 0, "width": 0, "height": 0,
            "layers": [{"draworder": "topdown", "id": 21, "name": "GroundObject", "objects": list(objects), "opacity": 1,
                        "type": "objectgroup", "visible": True, "x": 0, "y": 0}]}


def list_layer(out_root, group, folder, sub, name):
    """An entity layer in its map's package.json "entity" list (the port's copy if there, else vanilla's)."""
    tail = (group, "Assets", "GameAssets", "Serial", "Res", "Map", folder, "package.json")
    path = os.path.join(out_root, *tail)
    src = path if os.path.exists(path) else os.path.join(P.VANILLA, *tail)
    with open(src, encoding="utf-8") as f:
        doc = json.load(f)
    entry = next(m for m in doc["map"] if m["name"] == sub)
    asset = f"{sub}/{name}"
    if not any(x["asset"] == asset for x in entry["entity"]):
        entry["entity"].append({"name": name, "asset": asset})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------------------------------------
# a seed: BC's output, the packed seed folder, what each flag writes

def bc_rom(data):
    """BC's output ROM bytes as a kit SNES event reader (tools/snes_events.py) on the US dialect."""
    import snes_events as E
    r = object.__new__(E.Rom)
    r.path, r.name, r.data, r.dialect, r.tables, r.size = "bc", "bc", bytes(data), E.US_DIALECT, E.Tables(), len(data)
    r.dialog_choices = None   # no dialogue read (ROM-free: BC's output has the dialogue bank only where BC wrote it);
    return r                  # the routines read here show no menus


def _merge_messages(out, name, lines):
    """{key: text} merged into the seed's message file `name` (other steps may write it too)."""
    import seed_live as L
    path = os.path.join(out, *L.MESSAGE_PATH.split("/"), name + ".txt")
    have = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f.read().splitlines():
                if "\t" in line:
                    k, v = line.split("\t", 1)
                    have[k] = v
    have.update(lines)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("".join(f"{k}\t{v}\r\n" for k, v in have.items()))


class Ctx:
    """One seed's events: scripts/tables/lines changed in the packed seed folder `out` (files/<rel>, master/,
    message/), bc_events.json's parts. Several flags may change one script: each sees the others' changes."""

    def __init__(self, out, flags, rom=None, vanilla_rom=None, spoiler="", capture=None, log=print):
        self.out, self.rom, self.vanilla_rom, self.spoiler, self.log = out, rom, vanilla_rom, spoiler, log
        self.flags = {f.split(":")[0]: (f.split(":", 1)[1] if ":" in f else True) for f in flags.split()}
        # BC CE 27de07a options.py (Options.activate_flags), after the mode's forced flags:
        #     if self.is_flag_active('strangejourney'):
        #         self.activate_flag('notawaiter', True)
        # so a strangejourney seed is BC's notawaiter game too, though the flags string doesn't say so
        if "strangejourney" in self.flags:
            self.flags.setdefault("notawaiter", True)
        self.capture = capture or {}
        self.scripts, self.files, self.tables, self.lines = {}, {}, {}, []
        self.story = {}            # the PR's own story_mes_en lines this seed rewords (key -> text)
        self.speakers = {}         # their name boxes (story_cha_en: key -> name; PrKit LiveData sets them live)
        self.data = {"flags": [f for f in FLAGS if f in self.flags]}
        self._events = None

    def on(self, flag):
        return flag in self.flags

    # PR scripts: a copy from the seed folder if a flag (or the port) wrote one, else vanilla's
    def script(self, name):
        if name not in self.scripts:
            rel = new_rel(name) if name in NEW_SCRIPTS else script_rel(name)
            mine = os.path.join(self.out, "files", *rel.split("/"))
            if os.path.exists(mine):
                self.scripts[name] = (rel, json.load(open(mine, encoding="utf-8")))
            elif name in NEW_SCRIPTS:
                self.scripts[name] = (rel, empty_script(name, "Beyond Chaos"))
            else:
                self.scripts[name] = (rel, S.load(name))
        return self.scripts[name][1]

    def set_script(self, name, sc):
        self.script(name)
        self.scripts[name] = (self.scripts[name][0], sc)

    def map_file(self, rel):
        """A map's JSON (entity_default.json...): the seed's copy (a chest map the port wrote) or vanilla's."""
        if rel not in self.files:
            mine = os.path.join(self.out, "files", *rel.split("/"))
            src = mine if os.path.exists(mine) else os.path.join(P.VANILLA, *rel.split("/"))
            self.files[rel] = json.load(open(src, encoding="utf-8"))
        return self.files[rel]

    def table(self, name):
        if name not in self.tables:
            import seed_live as L
            path = os.path.join(self.out, *L.MASTER_PATH.split("/"), name + ".csv")
            if os.path.exists(path):
                with open(path, encoding="utf-8", newline="") as f:
                    self.tables[name] = P.Table(name, f.read())
            else:              # a table the port doesn't write (script: Gogo's talk rows): vanilla's, set live whole
                self.tables[name] = P.Table(name)
        return self.tables[name]

    def line(self, flag, text):
        """A new line for our scripts (system_en): its key."""
        key = KEY.format(flag, sum(1 for k, _ in self.lines if k.startswith(f"BC_EV_{flag}_")))
        self.lines.append((key, text))
        return key

    def events(self):
        """BC's output decoded (tools/snes_events.py on its ROM)."""
        if self._events is None:
            self._events = bc_rom(self.rom)
        return self._events

    def finish(self):
        """Write everything; returns (seed-folder files (rels), bc_events.json's dict)."""
        import seed_live as L
        written = []
        for name, (rel, sc) in sorted(self.scripts.items()):
            dest = os.path.join(self.out, "files", *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(json.dumps(sc, ensure_ascii=False, separators=(",", ":")))
            written.append(rel)
        for rel, doc in sorted(self.files.items()):
            dest = os.path.join(self.out, "files", *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
            written.append(rel)
        for name, table in self.tables.items():
            path = os.path.join(self.out, *L.MASTER_PATH.split("/"), name + ".csv")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(table.to_csv(table.rows.keys()))
        if self.lines:
            path = os.path.join(self.out, *L.MESSAGE_PATH.split("/"), "system_en.txt")
            with open(path, "a", encoding="utf-8", newline="") as f:
                for k, t in self.lines:
                    f.write(f"{k}\t{t}\r\n")
        for name, lines in ((STORY, self.story), (SPEAKERS, self.speakers if SPEAKERS_LIVE else {})):
            if lines:
                _merge_messages(self.out, name, lines)
        self.data["lines"] = len(self.lines)
        self.data["story"] = sorted(self.story)
        self.data["speakers"] = len(self.speakers)
        self.data["files"] = sorted(written)
        with open(os.path.join(self.out, EVENTS_JSON), "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1, ensure_ascii=False)
        return sorted(written), self.data


# ---------------------------------------------------------------------------------------------------------
# the flags

TOWER_SCRIPT = "9024"   # sc_b_2024: SysCall 狂信者の塔状態異常付与 (the TowerOfZealots status: magic only), then the loop


def lessfanatical(ctx):
    """BC: no forced Magic in the Cultists' Tower (C2/5352 -> BRA: the SNES's Fight-into-Magic swap, gated by the
    tower's battle event bit, is skipped). The PR's magic-only is the tower parties' battle script 9024 (its
    first line gives every player unit the TowerOfZealots status); those parties get the default loop (0)."""
    t = ctx.table("monster_party")
    changed = [i for i, r in t.rows.items() if r["script_name"] == TOWER_SCRIPT]
    for i in changed:
        t.rows[i]["script_name"] = "0"
    ctx.log(f"lessfanatical: {len(changed)} tower parties without the magic-only script")
    return {"parties": changed}


def shadowstays(ctx):
    """BC: Shadow never leaves after a random battle (C2/4885). The PR's draw is the SysCall シャドウ離脱抽選
    (Current.LotSecedeShadow) in the battle scripts: BcEvents.cs takes its "stays" path in such a seed."""
    return True


# --- j: the Phantom Forest --------------------------------------------------------------------------------
# BC (locationrandomizer.randomize_forest): the forest's middle rooms (SNES 133, 134) get their exits rewired at
# random, the way out to the train (SNES 134's exit to the world map + its event tile, CB/A3C4) moves to one of
# them, and the forced walk to the spring on entering SNES 133 (event tile (3,12), CB/A3D1) is cut. Read here
# from BC's output (its exits and event tiles), onto the PR's rooms Map_30421_1..3: each SNES room is one PR map,
# the same layout shifted by (dx, dy) (snes_maps: exits/arrivals pair one to one).
FOREST = {132: ("Map_30421_1", 351, (0, 1)), 133: ("Map_30421_2", 352, (2, 1)), 134: ("Map_30421_3", 353, (5, 1)),
          135: ("Map_30421_4", 354, (0, -2))}
FOREST_GROUP = "map_30421"
TRAIN_EVENT = 0xCBA3C4        # SNES 134 (11,7): to the forest's last room, or out once the train is done
TRAIN_SCRIPT_ID = 1181        # PR: sc_e_0214_0 (the same choice), a touch object on Map_30421_3
SPRING_WALK = "sc_map_30421_2"   # places ev_e_0158 (sc_e_0158: the walk to the spring) until ScenarioFlag1 106
MAP_FILES["j"] = [(FOREST_GROUP, "Map_30421", FOREST[m][0], "entity_default.json") for m in (132, 133, 134)]
SCRIPTS["j"] = [SPRING_WALK]


def _objects(doc):
    """Every object of a map's entity file with its layer: [(layer, object, {property: value})]."""
    out = []

    def walk(layers):
        for layer in layers:
            if layer.get("type") == "group":
                walk(layer.get("layers", []))
            else:
                for o in layer.get("objects", []):
                    out.append((layer, o, {p["name"]: p["value"] for p in o.get("properties", [])}))
    walk(doc["layers"])
    return out


def _tile(o):
    return (int(o["x"]) // 16, int(o["y"]) // 16)


def _set_prop(o, name, value, kind="int"):
    for p in o.setdefault("properties", []):
        if p["name"] == name:
            p["value"] = value
            return
    o["properties"].append({"name": name, "type": kind, "value": value})


def _drop_prop(o, name):
    o["properties"] = [p for p in o.get("properties", []) if p["name"] != name]


def forest_links(rom):
    """BC's forest: {SNES map: [(exit tile, ("train",) | (dest map, dest x, dest y))]} for 132-134 (132's west edge,
    the way back to the world map, left out: BC keeps it)."""
    import snes_maps as M
    out = {}
    for m in (132, 133, 134):
        train = {(e["x"], e["y"]) for e in M.event_tiles(rom, m) if e["event"] == TRAIN_EVENT}
        links = []
        for e in M.exits(rom, m):
            if e["kind"] != "short":
                continue
            tile = e["tiles"][0]
            links.append((tile, ("train",) if tile in train else (e["dest"], e["dest_x"], e["dest_y"])))
        out[m] = links
    return out


def j(ctx):
    links = forest_links(ctx.rom)
    docs = {m: ctx.map_file(MAP_REL.format(group=FOREST_GROUP, folder="Map_30421", sub=FOREST[m][0],
                                           file="entity_default.json")) for m in FOREST if m != 135}
    vanilla_train = None
    with open(os.path.join(P.VANILLA, *MAP_REL.format(group=FOREST_GROUP, folder="Map_30421", sub="Map_30421_3",
                                                      file="entity_default.json").split("/")), encoding="utf-8") as f:
        v3 = json.load(f)
    for _, o, pr in _objects(v3):
        if pr.get("object_type") == 2 and pr.get("script_id") == TRAIN_SCRIPT_ID:
            vanilla_train = o
    assert vanilla_train is not None, "Phantom Forest's train object changed"

    def point(m, x, y):
        """The PR arrival point (PointIn object_id) at SNES (m, x, y), added if the PR room has none there."""
        if m not in docs and m in FOREST:      # the forest's last room: not rewired, its points as they are
            docs[m] = ctx.map_file(MAP_REL.format(group=FOREST_GROUP, folder="Map_30421", sub=FOREST[m][0],
                                                  file="entity_default.json"))
        dx, dy = FOREST[m][2]
        want = (x + dx, y + dy)
        objs = _objects(docs[m])
        ins = [(o, pr) for _, o, pr in objs if pr.get("object_type") == 0]
        for o, pr in ins:
            if _tile(o) == want:
                return FOREST[m][1], pr["object_id"]
        # a new arrival point (BC sends a door to a spot the PR room has no arrival for)
        layer, tpl, _ = next((l, o, pr) for l, o, pr in objs if pr.get("object_type") == 0)
        new = copy.deepcopy(tpl)
        new["id"] = max(o["id"] for _, o, _ in objs) + 1
        new["x"], new["y"] = want[0] * 16, want[1] * 16
        pid = max(pr["object_id"] for _, pr in ins) + 1
        _set_prop(new, "object_id", pid)
        _set_prop(new, "entity_id", max(pr.get("entity_id", 0) for _, _, pr in objs) + 1)
        layer["objects"].append(new)
        return FOREST[m][1], pid

    changed = []
    for m, ls in links.items():
        doc = docs[m]
        dx, dy = FOREST[m][2]
        objs = _objects(doc)
        for (x, y), dest in ls:
            at = (x + dx, y + dy)
            found = [(o, pr) for _, o, pr in objs if _tile(o) == at and
                     (pr.get("object_type") == 3 or (pr.get("object_type") == 2 and pr.get("script_id") == TRAIN_SCRIPT_ID))]
            assert found, f"Phantom Forest: no PR door at {FOREST[m][0]} {at} (SNES {m} {(x, y)})"
            o, pr = found[0]
            if dest == ("train",):
                o["name"] = vanilla_train["name"]
                for k in ("object_type", "script_id"):
                    _set_prop(o, k, {"object_type": 2, "script_id": TRAIN_SCRIPT_ID}[k])
                for k in ("map_id", "point_id"):
                    _drop_prop(o, k)
                changed.append((FOREST[m][0], at, "train"))
            else:
                pm, pid = point(*dest)
                o["name"] = "GotoMap"
                _set_prop(o, "object_type", 3)
                _set_prop(o, "map_id", pm)
                _set_prop(o, "point_id", pid)
                _set_prop(o, "script_id", 0)
                changed.append((FOREST[m][0], at, (pm, pid)))
    # BC cuts the forced walk to the spring (the spring itself stays)
    sc = ctx.script(SPRING_WALK)
    ms = sc["Mnemonics"]
    assert ms[2]["mnemonic"] == "SetEntities" and ms[2]["operands"]["sValues"][0] == "ev_e_0158", "Phantom Forest's map script changed"
    ms[2] = S.op("Nop")
    ctx.log(f"j: {len(changed)} forest doors: " + "; ".join(f"{a} {b} -> {c}" for a, b, c in changed))
    return {"doors": [[a, list(b), c if isinstance(c, str) else list(c)] for a, b, c in changed]}


# --- BC's dialogue in its output (pointers CE/600, the first word = the first index in the second bank; text D0/0000) --
_TEXT_TABLE = None


def _text_table():
    """BC's own dialogue table (its tables/dialoguetext.txt, read as its utils does): byte(s) hex -> text."""
    global _TEXT_TABLE
    if _TEXT_TABLE is None:
        import bc_run
        by_text = {}
        with open(os.path.join(bc_run.SRC, "tables", "dialoguetext.txt"), encoding="utf-8") as f:
            for line in f:
                line = line.strip("\n")
                if line:
                    value, text = line.split("=", 1)
                    by_text.setdefault(text, value)
        _TEXT_TABLE = {v: k for k, v in by_text.items()}
        _TEXT_TABLE["1104"] = "<wait 60 frames>"
    return _TEXT_TABLE


def bc_dialogue(rom, idx):
    """Dialogue `idx` of BC's output ROM as BC writes text ("<line>", "<TERRA>"...)."""
    t = _text_table()
    bank_idx = rom[0xCE600] | rom[0xCE601] << 8
    ptr = rom[0xCE602 + 2 * idx] | rom[0xCE603 + 2 * idx] << 8
    at = 0xD0000 + ptr + (0x10000 if idx >= bank_idx else 0)
    out = []
    while rom[at] != 0:
        two = f"{rom[at]:02X}{rom[at + 1]:02X}"
        if two in t:
            out.append(t[two])
            at += 2
        else:
            out.append(t.get(f"{rom[at]:02X}", f"${rom[at]:02X}"))
            at += 1
    return "".join(out)


def _pr_text(key):
    if not hasattr(_pr_text, "d"):
        _pr_text.d = {}
        for f in ("story_mes_en", "system_en"):
            _pr_text.d.update(_load_messages(f))
    return _pr_text.d[key]


def _load_messages(name):
    out = {}
    with open(os.path.join(P.VANILLA, "message", "Assets", "GameAssets", "Serial", "Data", "Message", name + ".txt"),
              encoding="utf-8") as f:
        for line in f:
            if "\t" in line:
                k, v = line.rstrip("\r\n").split("\t", 1)
                out[k] = v
    return out


# --- k: the Zozo clock --------------------------------------------------------------------------------------------
# BC (manage_clock): which option of each hand's menu is right (CA/96CF: 6 hours, E2 = right; CA/96E8: 5 minutes, F8;
# CA/96FE: 5 seconds, 0E), and the townsfolk's hints rewritten to fit (dialogues 0x416-0x41A the wrong hours, 0x421 a
# wrong second, 0x423 two wrong seconds in one clue, 0x425 the last wrong second as a clock-face number, 0x42A the
# minute as one). PR: the clock (sc_e_0299: each hand's Select, Branches past the counter for the wrong options) and the
# hints as the townsfolk's own lines (their talk keys in Zozo's entity_default; the pairs are Worlds Collide's,
# wc_events.ZOZO_CLUES), each line the PR's with BC's numbers.
CLOCK_SCRIPT = "sc_e_0299"
CLOCK_HANDS = [(0xA96CF, 6, 0xE2, 4), (0xA96E8, 5, 0xF8, 13), (0xA96FE, 5, 0x0E, 21)]   # (slots, options, right, first Branch)
CLOCK_HINTS = {   # BC dialogue -> (the PR's map file, its talk key)
    0x416: ("Map_30511_7", "N008_C00_390_06_01"), 0x417: ("Map_30511_7", "N008_C00_390_02_01"),
    0x418: ("Map_30511_7", "N008_C00_390_03_01"), 0x419: ("Map_30511_7", "N008_C00_390_04_01"),
    0x41A: ("Map_30511_7", "N008_C00_390_05_01"), 0x421: ("Map_30511_1", "N008_C00_384_01_01"),
    0x423: ("Map_30510", "N008_C00_383_05_01"), 0x425: ("Map_30511_8", "N008_C00_391_01_01"),
    0x42A: ("Map_30511_4", "N002_C00_387_02_01"),
}
CLOCK_WORDS = {"two": 2, "four": 4, "six": 6, "eight": 8, "ten": 10}


def _zozo_rel(sub):
    group, folder = ("map_30510", "Map_30510") if sub == "Map_30510" else ("map_30511", "Map_30511")
    return MAP_REL.format(group=group, folder=folder, sub=sub, file="entity_default.json")


SCRIPTS["k"] = [CLOCK_SCRIPT]
MAP_FILES["k"] = [(("map_30510", "Map_30510") if s == "Map_30510" else ("map_30511", "Map_30511")) + (s, "entity_default.json")
                  for s in sorted({s for s, _ in CLOCK_HINTS.values()})]


def clock_answer(rom):
    """BC's clock: the right option of each hand (0-based: hour 2..12, minutes and seconds 10..50)."""
    out = []
    for at, n, right, _ in CLOCK_HANDS:
        rights = [i for i in range(n) if rom[at + 3 * i] == right]
        assert len(rights) == 1, f"Zozo clock: {len(rights)} right options at {at:X}"
        out.append(rights[0])
    return out


# manage_clock's clue for two wrong seconds (dialogue 0x423), by the pair (BC's own lines; [20, 40] keeps the game's)
DOUBLE_CLUE = {(10, 20): "The seconds? They're less than 30!", (10, 30): "The seconds? They're a factor of 30!",
               (10, 40): "The seconds? They're a square times 10.", (10, 50): "The second hand's in the clock's top half.",
               (20, 30): "The seconds? They're around 25!", (20, 50): "The seconds have four proper factors.",
               (30, 40): "The seconds? They're around 35!", (30, 50): "The seconds are an odd prime times 10!",
               (40, 50): "The seconds? They're greater than 30!"}
FACE = {10: "two", 20: "four", 30: "six", 40: "eight", 50: "ten"}


def prepare(capture):
    """Before BC runs (bc_run.run's prepare): record BC's own clock choices as BC makes them, its draws unchanged.
    manage_clock shuffles the wrong hours, then the wrong seconds (utils.utilrandom, BC's one Random): the wrapper
    lets the instance's shuffle record each list after the real shuffle, for that call only."""
    import randomizer
    import utils
    global _CAPTURE
    _CAPTURE = capture
    if getattr(randomizer.manage_clock, "_bc_events", False):
        return                     # wrapped by an earlier run in this process: they write to _CAPTURE
    original = randomizer.manage_clock

    def manage_clock():
        rng = utils.utilrandom
        seen = []
        real = rng.shuffle

        def shuffle(x, *a, **kw):
            real(x, *a, **kw)
            seen.append(list(x))
        rng.shuffle = shuffle
        try:
            return original()
        finally:
            del rng.shuffle
            _CAPTURE["clock"] = {"wrong_hours": seen[0] if seen else [], "wrong_seconds": seen[1] if len(seen) > 1 else []}
    manage_clock._bc_events = True
    randomizer.manage_clock = manage_clock

    # r / mimetime: BC's character at each World of Ruin recruit site (wor.py writes character.wor_location as it
    # picks; mimetime's Gogo: "<place> as <name>"), read once BC's recruit shuffle returns
    recruit = randomizer.manage_wor_recruitment

    def manage_wor_recruitment(*a, **kw):
        free = recruit(*a, **kw)
        import character
        _CAPTURE["wor_recruits"] = {c.id: c.wor_location for c in character.get_characters() if getattr(c, "wor_location", None)}
        _CAPTURE["wor_free"] = free
        return free
    randomizer.manage_wor_recruitment = manage_wor_recruitment

    # alasdraco: the opera's dialogue variables and flags BC set (names, titles, pronouns, factions, the thrown item)
    opera = randomizer.manage_opera

    def manage_opera(*a, **kw):
        import dialoguemanager as D
        before, flags = dict(D.dialogue_vars), set(D.dialogue_flags)
        out = opera(*a, **kw)
        import musicinterface
        rafters = re.search(r"Opera Rafters:\s*(.+)", getattr(musicinterface, "opera_log", "") or "")
        _CAPTURE["opera"] = {"vars": {k: v for k, v in D.dialogue_vars.items() if before.get(k) != v},
                             "flags": sorted(set(D.dialogue_flags) - flags | {f for f in D.dialogue_flags if f.endswith("plu")}),
                             "rafters": rafters.group(1).strip().lower() if rafters else None}
        return out
    randomizer.manage_opera = manage_opera

    # BC's always-on texts (randomizer.randomize: hints, poem, passwords): each recorded from BC's own call. ROM-free
    # BC has no dialogue to read back, so the choices are taken as BC makes them (its random.choice results)
    def recording(name, record):
        real = getattr(randomizer, name)

        def call(*a, **kw):
            rng = utils.utilrandom
            picks = []
            choice = rng.choice

            def chosen(seq):
                x = choice(seq)
                picks.append(x)
                return x
            rng.choice = chosen
            try:
                out = real(*a, **kw)
            finally:
                rng.choice = choice
            record(out, picks)
            return out
        setattr(randomizer, name, call)

    def texts():
        return _CAPTURE.setdefault("texts", {})

    def sprint(out, picks):
        texts()["sprint_spell"] = randomizer.get_item(0xE6).features.get("learnspell")

    def sabin(out, picks):
        c = randomizer.get_character(0x05).battle_commands
        texts()["sabin_command"] = c[1] if c[1] and c[1] != 0xFF else c[0]

    def house_skill(out, picks):
        word = str(out)
        spell = None
        if word.endswith("-"):
            for i in range(256):
                try:
                    if randomizer.get_spell(i).name == word[:-1]:
                        spell = i
                        break
                except Exception:  # noqa: BLE001
                    continue
        texts()["house"] = {"word": word, "spell": spell}

    def poem(out, picks):
        if picks:
            texts()["poem"] = picks[-1][0]

    def passwords(out, picks):
        if len(picks) >= 3:
            texts()["passwords"] = [str(x) for x in picks[-3:]]

    recording("sprint_shoes_hint", sprint)
    recording("sabin_hint", sabin)
    import monsterrandomizer
    real_house = monsterrandomizer.get_collapsing_house_help_skill

    def house_help():
        picks = []
        out = real_house()
        house_skill(out, picks)
        return out
    randomizer.get_collapsing_house_help_skill = house_help
    monsterrandomizer.get_collapsing_house_help_skill = house_help
    recording("randomize_poem", poem)
    recording("randomize_passwords", passwords)


_CAPTURE = {}

def clock_lines(clock, answer):
    """BC's clock hints (dialogue -> its words) from the captured choices, as manage_clock writes them; None if not captured."""
    if not clock or len(clock.get("wrong_hours", [])) != 5 or len(clock.get("wrong_seconds", [])) != 4:
        return None
    minute = (answer[1] + 1) * 10
    hours, seconds = clock["wrong_hours"], clock["wrong_seconds"]
    out = {0x416 + i: f"It's {h}:00." for i, h in enumerate(hours)}
    pair = tuple(sorted(seconds[:2]))
    if pair != (20, 40):
        out[0x423] = DOUBLE_CLUE[pair]
    out[0x421] = f"Clock's second hand's pointin' at {seconds[2]}."
    out[0x425] = f"The second hand of my watch is pointing at {FACE[seconds[3]]}."
    if minute != 10:
        out[0x42A] = f"Hand's pointin' at the {FACE[minute]}."
    return out


def clock_hint(idx, bc, pr):
    """The PR's hint line `pr` saying what BC's line `bc` says (BC changed only its numbers, or 0x423's whole clue)."""
    import re
    bc = bc.replace("’", "'").replace("<line>", " ").replace("<end>", "").strip()
    if 0x416 <= idx <= 0x41A:
        hour = re.search(r"(\d+):00", bc).group(1)
        return re.sub(r"\d+(?=:00)", hour, pr)
    if idx == 0x421:
        return re.sub(r"\d+", re.search(r"(\d+)", bc).group(1), pr, count=1)
    if idx in (0x425, 0x42A):
        word = re.search(r"\b(two|four|six|eight|ten)\b", bc)
        n = CLOCK_WORDS[word.group(1)] if word else int(re.search(r"(\d+)", bc).group(1))
        return re.sub(r"\d+", str(n), pr, count=1)
    if idx == 0x423:
        return bc if "divisible by 20" not in bc else pr
    return pr


def k(ctx):
    answer = clock_answer(ctx.rom)
    sc = ctx.script(CLOCK_SCRIPT)
    ms = sc["Mnemonics"]
    for (_, n, _, first), right in zip(CLOCK_HANDS, answer):
        wrong = [i for i in range(n) if i != right]
        for b, value in zip(range(first, first + n - 1), wrong):
            o = ms[b]
            assert o["mnemonic"] == "Branch" and o["operands"]["sValues"][0] == "MessageSelection", "Zozo clock changed"
            o["operands"]["iValues"][1] = value
    # the solved path (30: the label 正解, 31 its first step): a line in the plugin's log (tests see the clock solved)
    assert ms[30]["label"] and ms[31]["mnemonic"] == "Call", "Zozo clock changed"
    S.hook(sc, 31, "bc_clock_solved", [S.op("SysCall", s=["BC:log zozo clock solved"])])
    time = f"{(answer[0] + 1) * 2}:{(answer[1] + 1) * 10:02}:{(answer[2] + 1) * 10:02}"
    hints = {}
    lines = clock_lines(ctx.capture.get("clock"), answer)
    if lines is None:
        ctx.log("k: BC's hint choices weren't captured (bc_events.prepare): the townsfolk keep the PR's hints")
        lines = {}
    for idx, (sub, key) in sorted(CLOCK_HINTS.items()):
        if idx not in lines:
            continue
        text = clock_hint(idx, lines[idx], _pr_text(key))
        if text == _pr_text(key):
            continue
        new = ctx.line("k", text)
        doc = ctx.map_file(_zozo_rel(sub))
        hit = [p for _, o, _ in _objects(doc) for p in o.get("properties", []) if p.get("value") == key]
        assert hit, f"Zozo: {key} not in {sub}"
        for p in hit:
            p["value"] = new
        hints[key] = text
    ctx.log(f"k: the Zozo clock at {time}; {len(hints)} hints changed")
    return {"time": time, "answer": answer, "hints": hints}


# --- regionofdoom: Doom Gaze from the Falcon's wheel ---------------------------------------------------------------
# BC (patches.patch_doom_gaze, dialogue 0x60): the Falcon's wheel offers (Lift-off) (Find Doom Gaze) (Not just yet) in
# the World of Ruin until Doom Gaze is beaten; Find Doom Gaze fades out, puts the party on the airship and fights it
# (formation 0x5D), then its usual aftermath (Bahamut) or, if it fled, back to flying. PR: the wheel (sc_e_FAoutboard)
# gets the middle choice while ScenarioFlag2 216 (Doom Gaze beaten) is clear; it lifts off as the first choice does with
# our flag DOOM_SEARCH set, and the flying arrival (sc_e_FAoutboard_1) then starts the PR's own sky encounter
# (EncountBoss 464 with its after-script sc_e_0964_1: the Bahamut scene on the deck, or Doom Gaze back in the sky).
# Our flags: ScenarioFlag4 0-31 (no vanilla script touches 0-131; Worlds Collide uses them in its own games only).
BC_FLAGS = "ScenarioFlag4"
DOOM_SEARCH = 1                  # set by the wheel's (Find Doom Gaze.), cleared by the arrival that starts the fight
DOOM_GAZE_PARTY, DOOM_GAZE_AFTER, DOOM_GAZE_BEATEN = 464, "sc_e_0964_1", ("ScenarioFlag2", 216)
SCRIPTS["regionofdoom"] = ["sc_e_FAoutboard", "sc_e_FAoutboard_1"]


def _flag(cat, i):
    return S.op("SetFlag", i=[i], s=[cat])


def _reset(cat, i):
    return S.op("ResetFlag", i=[i], s=[cat])


def _if(cat, i, value, target):
    return S.op("Branch", i=[i, value, target], s=[cat, EQ, "imm"])


def _choice(n, target):
    return S.op("Branch", i=[0, n, target], s=["MessageSelection", EQ, "imm"])


def regionofdoom(ctx):
    sc = ctx.script("sc_e_FAoutboard")
    ms = sc["Mnemonics"]
    assert [ms[i]["label"] for i in (4, 7, 12)] == ["通常時", "発進する", "何もしない"] and ms[5]["mnemonic"] == "Select", \
        "the Falcon's wheel changed"
    take, never = ms[5]["operands"]["sValues"][:2]
    find = ctx.line("regionofdoom", "(Find Doom Gaze.)")
    S.hook(sc, 5, "bc_doom_gaze", [
        _if(*DOOM_GAZE_BEATEN, 1, "@vanilla"),
        S.op("Select", s=[take, find, never]),
        _choice(0, 7),                                   # (Take the wheel.): lift off
        _choice(1, "@find"),
        S.op("Jump", i=[12]),                            # (Never mind.)
        S.label("find"),
        _flag(BC_FLAGS, DOOM_SEARCH),
        S.op("Jump", i=[7]),                             # lift off; the arrival starts the fight
    ])
    arrive = ctx.script("sc_e_FAoutboard_1")
    ams = arrive["Mnemonics"]
    assert ams[8]["mnemonic"] == "FadeIn" and ams[9]["mnemonic"] == "Exit", "the Falcon's flying arrival changed"
    S.hook(arrive, 9, "bc_doom_gaze", [
        _if(BC_FLAGS, DOOM_SEARCH, 0, "@vanilla"),
        _reset(BC_FLAGS, DOOM_SEARCH),
        S.op("EncountBoss", i=[DOOM_GAZE_PARTY], s=[DOOM_GAZE_AFTER]),
        S.op("Exit"),
    ])
    ctx.log("regionofdoom: (Find Doom Gaze.) on the Falcon's wheel")
    return {"line": find}


# --- worringtriad: a New Game starts in the World of Ruin ------------------------------------------------------------
# BC (wor.manage_wor_skip): the new game's start routine (CC/9A4F) calls its own: the opening's party out, a level
# "see-saw" (Strago and Mog recruited and re-propertied six times over, so the party average climbs), Celes in with
# that average, every other character's properties, 50,000 GP, 12 espers, battle bits, ~250 items (every chest of the
# World of Balance's own places, their event items, a set of supplies), then the World of Balance's event bits
# (tables/wobeventbits.txt; the free character's "available" bit: Gau when commands/treasure are randomized, else
# BC's WoR recruit choice) and the World of Ruin's map at (145, 211), the airship parked there with `airship`.
# PR: the opening (sc_e_0001) goes straight to the same: the opening's party leaves, the PR's own World of Balance end
# state (every story flag its scenes set up to the collapse, sc_e_0607_13: data/bc_events_wor.json, `build-wor`),
# Celes (and the free character) joins at BC's level (BC:join), the items/espers as GetItem, BC:gil, the WoR map at
# Albrook's arrival (point 2, tile 139,210: BC's spot is 6 tiles east). The title's attract demo (map-local 7 = 1)
# keeps the vanilla opening.
OPENING = "sc_e_0001"
WOR_DATA = os.path.join(os.path.dirname(HERE), "data", "bc_events_wor.json")
WOR_LAST_SCENE = 607                     # sc_e_0607_13: the PR's collapse ("after the world's collapse", SF2 41)
WOR_EXTRA = [("ScenarioFlag3", 36)]      # BC's bit $134: no chocobo tutorial (Worlds Collide's research: SF3 36)
WOR_ARRIVAL = (2, 2)                     # Map_10020 point 2: Albrook's entrance on the World of Ruin's map
WOR_START = (145, 211)                   # BC's tile (the airship's spot with `airship`)
FALCON = 5
LEAVE = "メンバー離脱："
OPENING_PARTY = ["ティナ", "ビックス", "ウェッジ"]
LEVEL_MOD = [0, 2, 5, -3]                # C0/A228: the char_props level modifier by the init table's type (ED/7CB5 bits 2-3)
# each character props' level modifier type (ED/7CA0 + 22 * props + 0x15, bits 2-3): vanilla's, which BC keeps with
# worringtriad (characterstats randomizes them only without it), so a ROM-free seed needs no ROM byte for it
LEVEL_TYPES = [0, 1, 1, 0, 1, 1, 0, 1, 0, 0, 2, 1, 1, 0, 3, 2, 1, 3, 1, 0, 0, 3, 0, 1, 1, 0, 0, 1, 2]
START_LORES, LORE_BASE = 0x26F564, 140   # ED/F564: the Lores known at the start (24 bits); PR Lore abilities 140 + n
SCRIPTS["worringtriad"] = [OPENING]


def build_wor_flags():
    """The PR's story flags at the World of Ruin's start: every ScenarioFlag set/reset in its sc_e scenes in scene
    order up to the collapse (WOR_LAST_SCENE), the ones left on. Static: written to data/bc_events_wor.json."""
    import glob
    import re
    num = re.compile(r"^sc_e_(\d{4})")
    ops = []
    for f in glob.glob(os.path.join(P.VANILLA, "map_*", "**", "sc_e_*.json"), recursive=True):
        m = num.match(os.path.basename(f)[:-5])
        if not m or int(m.group(1)) > WOR_LAST_SCENE:
            continue
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        for k, o in enumerate(d.get("Mnemonics", [])):
            sv = o["operands"]["sValues"]
            if o["mnemonic"] in ("SetFlag", "ResetFlag") and sv[0].startswith("ScenarioFlag"):
                ops.append((int(m.group(1)), os.path.basename(f), k, o["mnemonic"] == "SetFlag", sv[0], o["operands"]["iValues"][0]))
    state = {}
    for _, _, _, on, cat, i in sorted(ops):
        state[(cat, i)] = on
    flags = sorted({k for k, v in state.items() if v} | set(WOR_EXTRA))
    doc = {"_doc": "The PR's story flags at the World of Ruin's start (tools/bc_events.py build-wor: its sc_e scenes in "
                   f"order up to sc_e_{WOR_LAST_SCENE:04d}, the collapse) + BC's extras", "set": [list(f) for f in flags]}
    with open(WOR_DATA, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=0)
    return flags


def wor_flags():
    if not os.path.exists(WOR_DATA):
        build_wor_flags()
    with open(WOR_DATA, encoding="utf-8") as fh:
        return [tuple(f) for f in json.load(fh)["set"]]


def _bit(ins):
    b = ins.args.get("bit")
    return b[0] if isinstance(b, tuple) else b


def wor_start(rom):
    """BC's World of Ruin start from its output: gil, espers (SNES), items (SNES ids, in order), Celes's level and
    the free character (SNES id or None) with theirs, by the SNES's char_props rule (C0/A07C: the average level of
    the recruited characters ($1EDE bits, characters 0-13; 3 when none) + the props' level modifier, 1-99)."""
    import snes_events as E
    ev = bc_rom(rom)
    assert rom[0xC9A4F] == 0xB2, "worringtriad: the new game's start routine isn't BC's call"
    first = rom[0xC9A50] | rom[0xC9A51] << 8 | rom[0xC9A52] << 16
    ins = E.script(ev, first, limit=2000)
    tail = [i for i in ins if i.name == "call"]
    assert tail, "worringtriad: BC's start routine doesn't call its event bits"
    bits_at = tail[-1].args.get("event")
    ins += E.script(ev, bits_at, limit=2000)
    level = [0] * 16
    recruited, available = set(), set()
    out = {"gil": 0, "espers": [], "items": [], "party": [], "free": None, "levels": {}, "airship": False}
    for i in ins:
        n = i.name
        if n == "gil_add":
            out["gil"] += i.args["gil"]
        elif n == "esper_add":
            out["espers"].append(i.args["esper"])
        elif n == "item_add":
            out["items"].append(i.args["item"])
        elif n == "party_char" and i.args["party"]:
            out["party"].append(i.args["char"])
        elif n in ("bit_set", "bit_clear"):
            b = _bit(i)
            on = n == "bit_set"
            for base, s in ((0x2E0, recruited), (0x2F0, available)):
                if base <= b < base + 16:
                    (s.add if on else s.discard)(b - base)
        elif n == "char_props":
            c, p = i.args["char"], i.args["props"]
            members = [level[k] for k in recruited if k < 14]
            avg = sum(members) // len(members) if members else 3
            kind = LEVEL_TYPES[p] if p < len(LEVEL_TYPES) else 0
            level[c] = max(1, min(99, avg + LEVEL_MOD[kind]))
    free = sorted(c for c in available if c not in out["party"] and c < 14)
    out["free"] = free[0] if free else None
    for c in out["party"] + ([out["free"]] if out["free"] is not None else []):
        out["levels"][c] = level[c]
    out["airship"] = out["airship"] or any(i.name == "bit_set" and _bit(i) == 0x1B9 for i in ins)
    # the Lores known from the start (ED/F564, 24 bits: BC adds some at random with worringtriad), as PR abilities
    # (Lore 140 + n, Worlds Collide's mapping, wc_seed start_skills)
    out["lores"] = [LORE_BASE + n for n in range(24) if rom[START_LORES + n // 8] >> (n % 8) & 1]
    return out


# worringtriad skips the opening, whose last scene shows the seed's guide (plugin BcGuide.cs): a copy of the guide's
# script (same name, sc_bc_guide) is listed in the World of Ruin's map (game map 2), and BcGuide runs it there the first
# time the player has control, once per game. This step places the copy (the baseline's is Exit-only); the guide step
# (tools/bc_guide.py write_in_game, which runs after this one) writes its content into every copy it finds in the seed.
WOR_GUIDE = ("map_10020", "Map_10020", "Map_10020")
WOR_GUIDE_REL = MAP_REL.format(group=WOR_GUIDE[0], folder=WOR_GUIDE[1], sub=WOR_GUIDE[2], file="sc_bc_guide.json")
NEW_SCRIPTS["sc_bc_guide"] = WOR_GUIDE


def place_wor_guide(ctx):
    ctx.set_script("sc_bc_guide", empty_script("sc_bc_guide", "Beyond Chaos: the seed's guide (World of Ruin copy)"))


def worringtriad(ctx):
    place_wor_guide(ctx)
    import idmap
    start = wor_start(ctx.rom)
    sc = ctx.script(OPENING)
    ms = sc["Mnemonics"]
    assert ms[1]["mnemonic"] == "SysCall" and ms[2]["mnemonic"] == "Branch" and ms[2]["operands"]["iValues"][:2] == [7, 1], \
        "the opening changed"
    ops = [S.op("Branch", i=[7, 1, "@vanilla"], s=["MapLocalVariable", EQ, "imm"])]      # the title's demo
    ops += [S.op("SysCall", s=[LEAVE + n]) for n in OPENING_PARTY]
    ops += [_flag(cat, i) for cat, i in wor_flags()]
    for c in start["party"] + ([start["free"]] if start["free"] is not None else []):
        ops.append(S.op("SysCall", s=[f"BC:join {c + 1} {start['levels'][c]}"]))           # status id = SNES id + 1
    counts = {}
    missing = []
    for it in start["items"]:
        try:
            cid = idmap.item_content(it)
        except KeyError:
            cid = 0
        if cid:
            counts[cid] = counts.get(cid, 0) + 1
        else:
            missing.append(it)
    ops += [S.op("GetItem", i=[cid, n]) for cid, n in sorted(counts.items())]
    espers = [idmap.esper_content(e - 0x36) for e in start["espers"] if e >= 0x36 and idmap.esper_content(e - 0x36)]
    ops += [S.op("GetItem", i=[cid, 1]) for cid in espers]
    if start["gil"]:
        ops.append(S.op("SysCall", s=[f"BC:gil {start['gil']}"]))
    ops.append(S.op("ChangeGpsData", i=[2]))
    if ctx.on("airship") or start["airship"]:
        ops.append(S.op("SetVehicle", i=[FALCON, WOR_ARRIVAL[0], WOR_START[0], WOR_START[1], 0, 0]))
    ops += [S.op("ChangeMap", i=[WOR_ARRIVAL[0], WOR_ARRIVAL[1], 0, 0, 1, 0]), S.op("Exit")]
    S.hook(sc, 2, "bc_worringtriad", ops)
    ctx.log(f"worringtriad: party {start['party']} free {start['free']} levels {start['levels']}, {len(start['items'])} items "
            f"({len(missing)} without a PR item), {len(espers)} espers, {start['gil']} GP, {len(wor_flags())} story flags")
    return {"party": [c + 1 for c in start["party"]], "free": None if start["free"] is None else start["free"] + 1,
            "levels": {str(c + 1): lv for c, lv in start["levels"].items()}, "items": sum(counts.values()),
            "espers": len(espers), "gil": start["gil"], "flags": len(wor_flags()), "lores": start["lores"]}


# --- airship: the airship from the start ------------------------------------------------------------------------------
# BC (activate_airship_mode): leaving Narshe after the moogle defense, the party is on the World of Balance's map with
# the airship parked south of Narshe (84,35); after the collapse the airship waits in the World of Ruin (78,240); the
# Blackjack's wheel always offers the Floating Continent in the World of Balance; every chocobo stable's "ride?" takes
# you up in the airship where the stable is (the SNES lift-off back to the parent map) and costs nothing; the deck can
# always be left; two party menus stop forcing Locke and Celes. ("Doing events out of order can cause softlocks.")
# PR: the moogle defense's way back to Narshe's north (sc_e_0018_4's second path, before its autosave) parks the
# Blackjack at 84,35; the collapse (sc_e_0607_13, where the PR sets "after the collapse") parks the Falcon at 78,240;
# the Blackjack's wheel (sc_e_BJoutboard) goes to its three-choice menu whatever ScenarioFlag2 28; each stable's talk
# script, past its Yes, puts the world's airship (Blackjack in the WoB, Falcon in the WoR) where its chocobo would
# stand (the stable's own arrival script's SetVehicle) and lifts off with the game's own flying arrival. Not carried:
# BC's party menus without Locke/Celes forced and the deck's exit checks (the PR has neither as event code).
BLACKJACK = 4
AIRSHIP_NARSHE = (84, 35)
AIRSHIP_WOR = (78, 240)
AIRSHIP_ARRIVE = {1: (BLACKJACK, "sc_e_BJoutboard_1"), 2: (FALCON, "sc_e_FAoutboard_1")}
STABLES = ["sc_chocobo_20071_1", "sc_chocobo_20121_2", "sc_chocobo_20151_1", "sc_chocobo_20281_1", "sc_chocobo_20281_2",
           "sc_chocobo_20281_3", "sc_chocobo_20281_4", "sc_chocobo_20351_2", "sc_chocobo_20361_1", "sc_chocobo_20431_1",
           "sc_chocobo_20481_1", "sc_chocobo_20481_2", "sc_chocobo_20481_3"]
GPS_TO_PLAYER = "GPSの対象をプレイヤーに"
SCRIPTS["airship"] = ["sc_e_0018_4", "sc_e_0607_13", "sc_e_BJoutboard"] + STABLES


def stable_spot(name):
    """A stable's world spot: (world map, x, y) of the chocobo its arrival script (<name>_2) places."""
    sc = S.load(name + "_2")
    v = next(o for o in sc["Mnemonics"] if o["mnemonic"] == "SetVehicle")["operands"]["iValues"]
    return v[1], v[2], v[3]


def _label_at(ms, label):
    return next(n for n, o in enumerate(ms) if o["mnemonic"] == "Nop" and o["label"] == label)


def airship(ctx):
    # the Blackjack south of Narshe once the moogles' fight is over
    sc = ctx.script("sc_e_0018_4")
    ms = sc["Mnemonics"]
    assert ms[12]["label"] == "sc_e_0018_6" and ms[25]["mnemonic"] == "AutoSave", "Narshe's north (after the moogles) changed"
    S.hook(sc, 25, "bc_airship", [S.op("SetVehicle", i=[BLACKJACK, 1, AIRSHIP_NARSHE[0], AIRSHIP_NARSHE[1], 0, 0])])
    # the Falcon in the World of Ruin from the collapse on
    sc = ctx.script("sc_e_0607_13")
    ms = sc["Mnemonics"]
    assert ms[10]["mnemonic"] == "ChangeGpsData" and ms[7]["operands"]["iValues"][0] == 41, "the collapse changed"
    S.hook(sc, 10, "bc_airship", [S.op("SetVehicle", i=[FALCON, 2, AIRSHIP_WOR[0], AIRSHIP_WOR[1], 0, 0])])
    # the Floating Continent on the Blackjack's wheel whenever (the PR: once the continent has risen, ScenarioFlag2 28)
    sc = ctx.script("sc_e_BJoutboard")
    ms = sc["Mnemonics"]
    assert ms[7]["mnemonic"] == "Branch" and ms[7]["operands"]["iValues"][:3] == [28, 1, 11] and ms[11]["label"] == "魔大陸追加",         "the Blackjack's wheel changed"
    ms[7] = S.op("Jump", i=[11])
    # the stables: the airship instead of a chocobo
    call = ctx.line("airship", "Shall I signal your airship to land here? It won't cost you a thing.")
    for name in STABLES:
        world, x, y = stable_spot(name)
        vehicle, arrive = AIRSHIP_ARRIVE[world]
        sc = ctx.script(name)
        ms = sc["Mnemonics"]
        ride = _label_at(ms, "乗る")
        ask = max(n for n in range(ride) if ms[n]["mnemonic"] == "Select")          # "ride?" (the price line before it)
        price = max(n for n in range(ask) if ms[n]["mnemonic"] == "Msg")
        assert ms[ride + 1]["mnemonic"] == "RemoveGil", f"{name} changed"
        ms[price]["operands"]["sValues"][0] = call
        S.hook(sc, ride + 1, "bc_airship", [
            S.op("SetVehicle", i=[vehicle, world, x, y, 0, 0]),
            S.op("FadeOut", i=[0, 0, 0, 255], r=[0.7]),
            S.op("SysCall", s=[GPS_TO_PLAYER]),
            S.op("ChangeMap", i=[world, 1, 0, 0, 1, 0], s=[arrive]),
            S.op("Exit"),
        ])
    ctx.log(f"airship: the Blackjack at Narshe {AIRSHIP_NARSHE}, the Falcon in the WoR {AIRSHIP_WOR}, the Floating Continent "
            f"on the wheel, {len(STABLES)} stables call the airship")
    return {"stables": len(STABLES)}


# --- r: the World of Ruin's recruits shuffled ---------------------------------------------------------------------------
# BC (wor._shuffle_recruit_locations): each World of Ruin recruit site gets another character (its event's character
# ids, recruited bits, NPC sprite/palette, the lines' name placeholders, naming screens, specials). BC's choice per site
# is captured as it runs (bc_events.prepare: character.wor_location), so a seed made without the ROM has it too.
# PR: in each site's scripts the calls naming the site's character (join, reserve, naming, best equipment, leave) and
# the character checks name BC's; the site's NPCs show BC's character (asset 119 + status). The lines' speakers stay the
# site character's until a seed can set speaker names (story_cha_en: the kit's seed messages, after the WC freeze).
SITES = {   # BC's label: (SNES character, PR scripts, NPC layer files (rel))
    "Phoenix Cave": (1, ["sc_e_0828", "sc_e_0828_2", "sc_e_0828_3", "sc_e_0828_4"],
                     ["map_30781/Assets/GameAssets/Serial/Res/Map/Map_30781/Map_30781_2/ev_e_0828.json"]),
    "Mt. Zozo": (2, ["sc_e_0735", "sc_e_0735_2", "sc_e_0737"], []),
    "Collapsing House": (5, ["sc_e_0636", "sc_e_0638_1", "sc_e_0639"],
                         ["map_20330/Assets/GameAssets/Serial/Res/Map/Map_20330/Map_20330/ev_e_0636_1.json"]),
    "Fanatics' Tower": (7, ["sc_e_0776"], ["map_30700/Assets/GameAssets/Serial/Res/Map/Map_30700/Map_30700/ev_e_0001.json"]),
    "Owzer's House": (8, ["sc_e_0773", "sc_e_0773_1", "sc_e_0773_2", "sc_e_0774", "sc_e_0775"],
                      ["map_30631/Assets/GameAssets/Serial/Res/Map/Map_30631/Map_30631_5/ev_e_0773.json"]),
    "Mobliz": (0, ["sc_e_0648", "sc_e_0649", "sc_e_0650", "sc_e_0650_1", "sc_e_0650_2", "sc_e_0650_3", "sc_e_0707",
                   "sc_e_0709", "sc_e_0709_1", "sc_e_0709_2", "sc_e_0709_3"],
               ["map_20341/Assets/GameAssets/Serial/Res/Map/Map_20341/Map_20341_8/ev_e_0649.json",
                "map_20341/Assets/GameAssets/Serial/Res/Map/Map_20341/Map_20341_8/ev_e_0650_1.json",
                "map_20340/Assets/GameAssets/Serial/Res/Map/Map_20340/Map_20340/ev_e_0650.json",
                "map_20341/Assets/GameAssets/Serial/Res/Map/Map_20341/Map_20341_9/ev_e_0707.json"]),
    "Moogle Cave": (0xA, ["sc_e_0778"], ["map_30011/Assets/GameAssets/Serial/Res/Map/Map_30011/Map_30011_3/ev_e_0778.json"]),
    "Sasquatch Cave": (0xD, ["sc_e_0790"], ["map_30771/Assets/GameAssets/Serial/Res/Map/Map_30771/Map_30771_4/ev_e_0790.json"]),
    "ZoneEater": (0xC, ["sc_e_0865"], ["map_30791/Assets/GameAssets/Serial/Res/Map/Map_30791/Map_30791_8/ev_e_0865.json"]),
}
PR_NAMES = ["ティナ", "ロック", "カイエン", "シャドウ", "エドガー", "マッシュ", "セリス", "ストラゴス", "リルム", "セッツァー",
            "モグ", "ガウ", "ゴゴ", "ウーマロ"]                       # by SNES character id (PR status id - 1)
NAMED_CALLS = ("メンバー加入：", "控えに移動：", "名前入力：", "最強装備：", "メンバー離脱：")
CHAR_BRANCHES = ("BranchByCharacter", "BranchByLeader")
SCRIPTS["r"] = sorted({n for _, names, _ in SITES.values() for n in names})
MAP_FILES["r"] = [tuple(rel.split("/Assets/GameAssets/Serial/Res/Map/")[0:1]) + tuple(
    rel.split("/Assets/GameAssets/Serial/Res/Map/")[1].split("/")) for _, _, rels in SITES.values() for rel in rels]


# the named calls vanilla's scripts use (the game's table may have more; where not, the plugin's generic call)
KNOWN_CALLS = {"控えに移動：": set(PR_NAMES) - {"ガウ", "ゴゴ"}, "メンバー離脱：": set(PR_NAMES) - {"ゴゴ", "ウーマロ"},
               "最強装備：": {"ティナ", "エドガー"}, "メンバー加入：": set(PR_NAMES), "名前入力：": set(PR_NAMES)}
PLUGIN_CALLS = {"控えに移動：": "BC:reserve", "メンバー離脱：": "BC:leave"}
UNNAMED = (0xA, 0xC, 0xD)     # Mog, Gogo, Umaro: BC names them at any site; the others keep their names (no rename)


def recast(ctx, site, new):
    """One recruit site recast for BC's character `new` (SNES id): its scripts' named calls and character checks, its
    NPCs' sprite, BC's naming rule. Returns what changed."""
    old, names, layers = SITES[site]
    if new == old:
        return None
    o_name, n_name = PR_NAMES[old], PR_NAMES[new]
    calls = checks = sprites = 0
    named = False
    for name in names:
        sc = ctx.script(name)
        ms = sc["Mnemonics"]
        for k, o in enumerate(ms):
            sv, iv = o["operands"]["sValues"], o["operands"]["iValues"]
            if o["mnemonic"] == "SysCall" and sv[0].startswith(NAMED_CALLS) and sv[0].endswith("：" + o_name):
                kind = sv[0][:-len(o_name)]
                calls += 1
                if kind == "名前入力：":
                    named = True
                    if new not in UNNAMED:                     # BC skips the rename for a named character
                        ms[k] = S.op("Nop", label=o.get("label", ""), kind=o.get("type", 1))
                        continue
                if n_name in KNOWN_CALLS[kind]:
                    sv[0] = kind + n_name
                elif kind in PLUGIN_CALLS:
                    sv[0] = f"{PLUGIN_CALLS[kind]} {new + 1}"
                else:                                          # best equipment: Terra's and Edgar's only
                    ms[k] = S.op("Nop", label=o.get("label", ""), kind=o.get("type", 1))
            elif o["mnemonic"] in CHAR_BRANCHES and iv[0] == old + 1:
                iv[0] = new + 1
                checks += 1
    if not named and new in UNNAMED:                           # BC's recruit_*_insert: a naming screen before the join
        for name in names:
            sc = ctx.script(name)
            ms = sc["Mnemonics"]
            at = next((k for k, o in enumerate(ms) if o["mnemonic"] == "SysCall" and
                       o["operands"]["sValues"][0] == "メンバー加入：" + n_name), None)
            if at is not None:
                S.hook(sc, at, "bc_r_name", [S.op("SysCall", s=["名前入力：" + n_name])])
                calls += 1
                break
    for rel in layers:
        doc = ctx.map_file(rel)
        for _, obj, pr in _objects(doc):
            if pr.get("asset_id") == 119 + old + 1:
                _set_prop(obj, "asset_id", 119 + new + 1)
                sprites += 1
    speakers = P.messages("story_cha", "en")                    # the name boxes: the old one's placeholder -> the new one's
    for name in names:
        for o in ctx.script(name)["Mnemonics"]:
            if o["mnemonic"] == "Msg" and speakers.get(o["operands"]["sValues"][0]) == SPEAKER_NAMES[old]:
                ctx.speakers[o["operands"]["sValues"][0]] = SPEAKER_NAMES[new]
    lines = 0
    for name in names:                                         # the newcomer's own lines where the PR has them
        ms = ctx.script(name)["Mnemonics"]
        for k, o in enumerate(ms):
            if o["mnemonic"] == "Msg" and o["operands"]["sValues"][0] in RECAST_LINES.get((site, new), {}):
                key = RECAST_LINES[(site, new)][o["operands"]["sValues"][0]]
                if key:
                    o["operands"]["sValues"][0] = key
                else:
                    ms[k] = S.op("Nop", label=o.get("label", ""), kind=o.get("type", 1))
                lines += 1
    return {"was": old + 1, "now": new + 1, "calls": calls, "checks": checks, "sprites": sprites, "lines": lines}


# the PR's name-box placeholders (story_cha_en) by SNES character: the game shows the character's current name
SPEAKER_NAMES = ["(TINA)", "(ROCK)", "(KAIEN)", "(SHADOW)", "(EDGAR)", "(MASH)", "(CELES)", "(STRAGUS)", "(RELM)",
                 "(SETZER)", "(MOG)", "(GAU)", "(GOGO)", "(UMARO)"]
SPEAKERS = "story_cha_en"
# PrKit's LiveData sets a seed's story_cha_<lang>.txt as name boxes (2026-11-21); a plugin older than that would set
# them as the lines' texts. Off: the seed doesn't write the file.
SPEAKERS_LIVE = True


# (site, BC's character) -> {the site's line: the PR's line for the newcomer, or None: gone}. The Zone Eater's Gau
# (mimetime; BC's text 0x286 "Uwao, aooh! I'm GAU! I'm your friend! Let's travel together!"): his rejoining lines at
# the Veldt (sc_e_0241), where Gogo's narration and words were.
RECAST_LINES = {
    ("ZoneEater", 0xB): {"E0865_00_999_a_01": None, "E0865_01_507_a_01": "E0241_00_001_b_01",
                         "E0865_01_507_a_02": "E0241_00_001_b_02", "E0865_01_507_a_03": "E0241_00_001_b_03"},
}


# BC's "Falcon" site (falcon_recruit): the shuffled character it gets becomes available once the Falcon is (BC's free
# World of Ruin character). PR: the Falcon's rise (sc_e_0703_11, where "after obtaining the Falcon" is set) joins them.
FALCON_SCENE = "sc_e_0703_11"
SCRIPTS["r"] = sorted(set(SCRIPTS["r"]) | {FALCON_SCENE})


def falcon_recruit(ctx, new):
    sc = ctx.script(FALCON_SCENE)
    ms = sc["Mnemonics"]
    at = next(k for k, o in enumerate(ms) if o["mnemonic"] == "SetFlag" and o["operands"]["iValues"][0] == 97 and
              o["operands"]["sValues"][0] == "ScenarioFlag2")
    S.hook(sc, at + 1, "bc_r_falcon", [S.op("SysCall", s=["メンバー加入：" + PR_NAMES[new]])])
    return {"now": new + 1}


def bc_recruits(ctx):
    """{BC site label: SNES character} from the capture (prepare), the recruit sites only."""
    got = ctx.capture.get("wor_recruits") or {}
    return {label: int(c) for c, label in got.items() if label in SITES}


def r(ctx):
    sites = bc_recruits(ctx)
    if not sites:
        ctx.log("r: BC's recruit choices weren't captured (bc_events.prepare): the World of Ruin's recruits stay the PR's")
        return {"sites": {}}
    done = {}
    for site, new in sorted(sites.items()):
        part = recast(ctx, site, new)
        if part:
            done[site] = part
    falcon = {int(c) for c, label in (ctx.capture.get("wor_recruits") or {}).items() if label == "Falcon"}
    if falcon:
        done["Falcon"] = falcon_recruit(ctx, falcon.pop())
    ctx.log("r: " + "; ".join(f"{k}: -> {PR_NAMES[v['now'] - 1]}" + (f" (was {PR_NAMES[v['was'] - 1]}: {v['calls']} calls, "
                                 f"{v['checks']} checks, {v['sprites']} sprites)" if "was" in v else " (joins with the Falcon)")
                                 for k, v in done.items()))
    return {"sites": done}


# --- mimetime: Gogo hidden in the World of Ruin ----------------------------------------------------------------------
# BC (wor._manage_gogo_recruitment): a new NPC on one of a few maps looks like one of the recruitable characters (its
# sprite), and with that character in the party, talking to him recruits Gogo (event CC/E5EF; else dialogue 0xE5).
# Read from BC's output (it writes every NPC table): the NPC whose event is CC/E5EF.
GOGO_EVENT = 0xCCE5EF
GOGO_MAPS = [0xE2, 0x120, 0x80, 0x158, 0x161, 0x83, 0x14A, 0x4E, 0x3C, 0x1C, 0xCA, 0xEE]   # BC's candidate spots


def gogo_spot(rom):
    """BC's hidden Gogo: {map, x, y, sprite (the disguise's SNES character id), direction} or None."""
    import snes_maps as M
    for m in GOGO_MAPS:
        for n in M.npcs(rom, m):
            if n.get("event") == GOGO_EVENT:
                return {"map": m, "x": n["x"], "y": n["y"], "sprite": n["sprite"], "direction": n["direction"]}
    return None


# PR: Gogo's NPC in a layer of our own (ev_bc_gogo) in the room of BC's spot, placed by the room's map script while the
# world has collapsed (ScenarioFlag2 41) and he isn't found (our ScenarioFlag4 2); his talk script (sc_bc_gogo_<map>,
# script table row GOGO_IDS[map]) checks the disguise's character in the party: Zone Eater's own Gogo lines, naming and
# join (not its flag: the Zone Eater then holds Gau), else the PR's line for SNES 0xE5. Every candidate room has the
# layer and script listed (empty in the baseline); a seed fills the chosen one.
GOGO_FOUND = 2                     # ScenarioFlag4: Gogo found (mimetime)
GUIDE_WOR_SHOWN = 3                # ScenarioFlag4: the seed's guide shown in the World of Ruin (worringtriad; BcGuide.cs)
GOGO_LAYER = "ev_bc_gogo"
GOGO_ENTITY = 900                  # his NPC's entity_id (its layer is ours alone)
GOGO_WRONG = "E0044_00_061_a_01"   # the PR's line for SNES 0xE5 ("My work here is done! You're in my way. Move it!")
GOGO_ZONE = "sc_e_0865"            # the Zone Eater's Gogo: its narration, naming, lines and join are his
GOGO_TEMPLATE = "map_30791/Assets/GameAssets/Serial/Res/Map/Map_30791/Map_30791_8/ev_e_0865.json"   # Gogo: asset 132
# BC's spot (SNES map) -> (PR group, folder, room, PR tile, the room's map script or None): the World of Ruin's room,
# matched from the SNES and PR NPC/exit positions (snes_maps.to_pr gives the WoB twin for 0x4E and a Figaro room for
# 0xEE); where BC's exact tile is furniture in the PR room, the walkable tile beside it. (*) a room without a map
# script file: the game's map_script table names one for every room, so ours (NEW_SCRIPTS) runs there
GOGO_ROOMS = {
    0xE2: ("map_30511", "Map_30511", "Map_30511_12", (84, 17), "sc_map_30511_12"),   # Zozo, the tower top (merged map)
    0x120: ("map_20411", "Map_20411", "Map_20411_1", (56, 39), "sc_map_20411_1"),    # Maranda's inn (56,40 furniture)
    0x80: ("map_20401", "Map_20401", "Map_20401_1", (75, 31), "sc_map_20401_1"),     # Duncan's cabin (76,31 the table)
    0x158: ("map_20460", "Map_20460", "Map_20460", (54, 18), "sc_map_20460"),         # Thamasa, by Leo's grave
    0x161: ("map_30761", "Map_30761", "Map_30761_2", (27, 27), "sc_map_30761_2"),    # the cave on the Veldt, the camp
    0x83: ("map_20470", "Map_20470", "Map_20470", (10, 12), "sc_map_20470"),          # Gau's father's house (10,11 the well)
    0x14A: ("map_20321", "Map_20321", "Map_20321_3", (11, 27), "sc_map_20321_3"),    # Albrook's pub (12,27 the edge)
    0x4E: ("map_20361", "Map_20361", "Map_20361_5", (72, 38), "sc_map_20361_5"),     # South Figaro's pub, back room (*)
    0x3C: ("map_20371", "Map_20371", "Map_20371_7", (100, 16), "sc_map_20371_7"),    # Figaro Castle's library
    0x1C: ("map_20011", "Map_20011", "Map_20011_5", (13, 21), "sc_map_20011_5"),     # Narshe's inn (merged map)
    0xCA: ("map_20431", "Map_20431", "Map_20431_7", (51, 19), "sc_map_20431_7"),     # Jidoor's relic shop
    0xEE: ("map_20441", "Map_20441", "Map_20441_1", (99, 19), "sc_map_20441_1"),     # the opera's dressing room (99,18)
}
GOGO_IDS = {}                      # SNES map -> script table id (9200..)


def _register_gogo_rooms():
    for n, (m, (group, folder, sub, _, _)) in enumerate(sorted(GOGO_ROOMS.items())):
        name = f"sc_bc_gogo_{m:x}"
        NEW_SCRIPTS[name] = (group, folder, sub)
        NEW_LAYERS[MAP_REL.format(group=group, folder=folder, sub=sub, file=GOGO_LAYER + ".json")] = (group, folder, sub, GOGO_LAYER)
        GOGO_IDS[m] = 9200 + n
        if not os.path.exists(os.path.join(P.VANILLA, *MAP_REL.format(group=group, folder=folder, sub=sub,
                                                                    file=GOGO_ROOMS[m][4] + ".json").split("/"))):
            NEW_SCRIPTS[GOGO_ROOMS[m][4]] = (group, folder, sub)
    SCRIPTS["mimetime"] = sorted({room[4] for room in GOGO_ROOMS.values()} - set(NEW_SCRIPTS) | {GOGO_ZONE})



def gogo_script(name, disguise):
    """The hidden Gogo's talk script: `disguise` (PR status id) in the party -> Zone Eater's Gogo recruit, else a brush-off."""
    zone = S.load(GOGO_ZONE)["Mnemonics"]
    keep = [copy.deepcopy(o) for o in zone if o["mnemonic"] in ("Msg", "SysCall")]
    for o in keep:
        o["label"] = ""
    ops = [S.label("Main"),
           _if(BC_FLAGS, GOGO_FOUND, 1, "@end"),                   # found already (where the NPC can't go away)
           S.op("BranchByCharacter", i=[disguise, 0, 0, "@join"]),
           S.op("Msg", i=[0, 2], s=[GOGO_WRONG]), S.op("Exit"),
           S.label("join")] + keep + [_flag(BC_FLAGS, GOGO_FOUND), S.op("Call", i=[0]), S.op("Exit"),
                                      S.label("end"), S.op("Exit")]
    S._resolve(ops, 0)
    sc = empty_script(name, "Beyond Chaos: the hidden Gogo (mimetime)")
    sc["Mnemonics"] = ops
    sc["Segments"] = [{"Label": "Main", "EntryPoint": 0, "Count": len(ops)}]
    # he goes once he's joined, as the Zone Eater's Gogo does (its Puppet_0005: the NPC hidden)
    hide = S.append(sc, "gogo_hide", [S.op("SetPuppet", i=[0, GOGO_ENTITY, "@gogo_hide_00"], kind=2),
                                      S.op("ExecPuppet", kind=2), S.op("Return", kind=2),
                                      S.label("gogo_hide_00", kind=2), S.op("Hide", kind=2), S.op("Exit", kind=2)])
    sc["Mnemonics"][hide]["type"] = 2
    next(o for o in ops if o["mnemonic"] == "Call")["operands"]["iValues"][0] = hide
    return sc


def mimetime(ctx):
    # the Zone Eater holds Gau instead (BC's _setup_alternate_zone_eater, when it auto-recruits Gau: o, w or t); with r
    # the site is BC's shuffled one ("ZoneEater" in r's capture: recast there)
    zone = None
    if "ZoneEater" not in bc_recruits(ctx) and any(ctx.on(f) for f in ("o", "w", "t")):
        zone = recast(ctx, "ZoneEater", 0xB)
    spot = gogo_spot(ctx.rom)
    if spot is None or spot["map"] not in GOGO_ROOMS:
        ctx.log(f"mimetime: BC's Gogo at {spot}: no PR room for it")
        return {"spot": spot, "zone_eater": zone}
    group, folder, sub, (x, y), map_script = GOGO_ROOMS[spot["map"]]
    disguise = spot["sprite"] + 1                               # SNES character id -> PR status id
    name = f"sc_bc_gogo_{spot['map']:x}"
    ctx.set_script(name, gogo_script(name, disguise))
    with open(os.path.join(P.VANILLA, *GOGO_TEMPLATE.split("/")), encoding="utf-8") as f:
        tpl = next(o for _, o, pr in _objects(json.load(f)) if pr.get("asset_id") == 132)
    npc = copy.deepcopy(tpl)
    npc["id"] = GOGO_ENTITY
    npc["x"] = x * 16
    npc["y"] = (y + 1) * 16 if "gid" in npc else y * 16          # a tile object's y is its bottom edge
    for k, v in (("asset_id", 119 + disguise), ("script_id", GOGO_IDS[spot["map"]]), ("entity_id", GOGO_ENTITY),
                 ("direction", {0: 1, 1: 2, 2: 4, 3: 8}.get(spot["direction"], 4))):
        _set_prop(npc, k, v)
    _set_prop(npc, "message_key", "", "string")
    rel = MAP_REL.format(group=group, folder=folder, sub=sub, file=GOGO_LAYER + ".json")
    ctx.files[rel] = empty_layer(GOGO_LAYER, [npc])
    room = ctx.script(map_script)
    S.hook(room, 1, "bc_gogo", [
        _if("ScenarioFlag2", 41, 0, "@vanilla"),
        _if(BC_FLAGS, GOGO_FOUND, 1, "@vanilla"),
        S.op("SetEntities", s=[GOGO_LAYER]),
    ])
    t = ctx.table("script")
    t.rows[GOGO_IDS[spot["map"]]] = {"id": str(GOGO_IDS[spot["map"]]), "script_name": name}
    ctx.log(f"mimetime: Gogo in {sub} ({x},{y}) as status {disguise} (BC: SNES map {spot['map']:#x} {spot['x']},{spot['y']})"
            f"{'; the Zone Eater holds Gau' if zone else ''}")
    return {"room": sub, "tile": [x, y], "disguise": disguise, "zone_eater": zone}


_register_gogo_rooms()


# --- alasdraco: BC's opera cast in the PR's opera words
# BC (musicinterface.manage_opera): a random cast for Maria, Draco, Ralse and the Impresario (custom/opera.txt:
# name, title, gender), two random factions for the East and the West, the item thrown from the balcony; its
# data/script/opera.txt swaps words in the SNES lines for dialogue variables ({Maria}, {mariaEm}, {OperaWest}...).
# PR: the same variables (captured as BC sets them: prepare) swapped into the PR's own opera lines, word for word
# where the PR says it (its wording differs from the SNES's, so the swaps are per PR line, below). Only words change:
# the lines keep their <WAIT..>/<AUTO_P> codes, so the sung lines keep the scene's timing (it follows the music).
# BC's templates: {Var} the variable, capitalized when the name is ({Maria}); {flag?yes:no} by BC's dialogue flags
# (mariaplu: Maria is "they"). The speakers' name boxes (story_cha_en per line) wait for the kit's per-seed speakers.
STORY = "story_mes_en"
_IMP = "{ImpresarioTitle} {Impresario}"
OPERA_LINES = {
    "N002_C00_290_01_01": [(r"the impresario", "{impresarioTitle} {impresario}")],
    "N002_C00_105_05_02": [(r"\bMaria\b", "{Maria}")],
    "E1054_00_442_a_02": [(r"\bMaria\b", "{Maria}"), (r"\bof her\b", "of {mariaEm}"), (r"\bShe's\b", "{MariaEyIs}")],
    "E0313_00_442_a_01": [(r"\bMaria\b", "{Maria}")],
    "E0313_00_442_a_03": [(r"\bMaria\b", "{Maria}")],
    "E0313_00_442_a_04": [(r"\bMaria\b", "{Maria}")],
    "E0314_00_442_a_02": [(r"That man is", "{ImpresarioEyIs}"), (r"calls him", "calls {impresarioEm}"),
                          (r"\"Impresario\.\"", "\"{Impresario}.\""), (r"\bHe's been\b", "{ImpresarioEyIs} been")],
    "E0314_00_442_a_93": [(r"\bMaria\b", "{Maria}"), (r"my wife", "my {mariaWife}")],
    "E0315_00_112_a_02": [(r"\bMaria\b", "{Maria}")],
    "E0315_00_112_a_07": [(r"\bMaria\b", "{Maria}")],
    "E0315_00_112_a_10": [(r"\bMaria\b", "{Maria}")],
    "E0315_00_112_a_11": [(r"\bMaria\b", "{Maria}")],
    "E0315_00_112_a_13": [(r"\bMaria\b", "{Maria}")],
    "E0315_00_112_a_15": [(r"\bMaria\b", "{Maria}")],
    "E0315_02_114_a_01": [(r"between the East and the West", "between {operaEast} and {operaWest}"),
                          (r"from the West", "from {operaWest}"), (r"\bDraco\b", "{Draco}"),
                          (r"of his love", "of {dracoEir} love"), (r"\bMaria\b", "{Maria}")],
    "E0315_02_114_a_02": [(r"\bMaria\b", "{Maria}")],
    "E0316_00_113_a_06": [(r"\bMaria\b", "{Maria}"), (r"\bDraco\b", "{Draco}"), (r"pours her", "pours {mariaEir}")],
    "E0137_00_113_a_02": [(r"pick up the flowers", "pick up the {operaItem}"), (r"toss the bouquet", "toss the {operaItem}"),
                          (r"(?<=\))Impresario(?=<P>)", _IMP)],
    "E0318_00_118_a_01": [(r"The Western armies", "{OperaWest}'s armies"), (r"\bMaria's\b", "{Maria}'s"),
                          (r"the hands of the East", "the hands of {operaEast}"),
                          (r"wed the Eastern Prince Ralse", "wed {RalseTitle} {Ralse} of {operaEast}"),
                          (r"\bMaria\b", "{Maria}"), (r"\bDraco\b", "{Draco}"),
                          (r"as she gazes", "as {mariaEy} {mariaPlu?gaze:gazes}")],
    "E0318_00_118_c_02": [(r"\bDraco\b", "{Draco}")],
    "E0318_03_118_a_02": [(r"\bDraco\b", "{Draco}")],
    "E0318_02_118_a_02": [(r"Prince Ralse", "{RalseTitle} {Ralse}")],
    "E0318_02_118_c_02": [(r"Prince Ralse", "{RalseTitle} {Ralse}")],
    "E1039_00_118_a_01": [(r"\bMaria\b", "{Maria}")],
    "E0320_00_118_a_03": [(r"Prince Ralse is looking for his", "{RalseTitle} {Ralse} is looking for {ralseEir}"),
                          (r"part of the East", "part of {operaEast}")],
    "E0329_00_113_a_02": [(r"the impresario", "{impresarioTitle} {impresario}")],
    "E0330_00_114_a_02": [(r"The Western survivors", "{OperaWest}'s survivors")],
    "E0330_00_114_a_06": [(r"\bMaria\b", "{Maria}")],
    "E0330_00_114_a_07": [(r"\bDraco\b", "{Draco}")],
    "E0330_00_114_a_08": [(r"the Western horde", "{operaWest}'s horde"), (r"my queen to be", "my {mariaQueen} to be"),
                          (r"\bMaria\b", "{Maria}")],
    "E0330_00_114_a_09": [(r"\bMaria's\b", "{Maria}'s")],
    "E0330_00_114_a_12": [(r"\bMaria\b", "{Maria}")],
    "E0344_00_114_a_01": [(r"win the girl", "win {mariaTheGirl}")],
    "E0344_00_114_a_02": [(r"\bDraco\b", "{Draco}"), (r"\bRalse\b", "{Ralse}")],
    "E0344_02_114_a_04": [(r"\bImpresario\b", "{Impresario}"), (r"\bMaria\b", "{Maria}")],
    "E0344_02_114_a_06": [(r"\bMaria\b", "{Maria}"), (r"new bride", "new {mariaWife}"), (r"\bshe's\b", "{mariaEyIs}"),
                          (r"for her now", "for {mariaEm} now")],
    "E0331_00_115_a_01": [(r"The impresario", "{ImpresarioTitle} {impresario}")],
    "E0344_03_123_a_07": [(r"\bMaria\b", "{Maria}")],
    "E0344_03_123_a_09": [(r"\bMaria\b", "{Maria}")],
    "E0347_00_120_a_09": [(r"\bMaria\b", "{Maria}")],
    "E1021_00_542_a_01": [(r"\bMaria\b", "{Maria}")],
    # the speakers' names as the story file lists them (the name boxes themselves: story_cha_en, later)
    "SPEAKER_37": [(r"^Impresario$", "{Impresario}")],
    "SPEAKER_39": [(r"^Draco$", "{Draco}")],
    "SPEAKER_40": [(r"^Ralse$", "{Ralse}")],
}
# BC's dialogue table codes in its custom names ($73The Man$62 -> “The Man”)
_BC_CODES = {"73": "“", "62": "”", "63": "'", "65": ".", "66": ",", "61": ":", "64": "-", "67": "…"}


def _bc_text(v):
    return re.sub(r"\$([0-9A-Fa-f]{2})", lambda m: _BC_CODES.get(m[1].upper(), ""), str(v)).strip()


def opera_fill(template, vars_, flags):
    """BC's dialoguemanager.patch for one template: {var} (capitalized when the name is), {flag?yes:no}."""
    def one(m):
        body = m[1]
        if "?" in body:
            flag, opts = body.split("?", 1)
            yes, _, no = opts.partition(":")
            return yes if flag.lower() in flags else no
        v = _bc_text(vars_.get(body.lower(), body))
        if body.isupper():
            return v.upper()
        if body[0].isupper() and v:
            return v[0].upper() + v[1:]
        return v
    out = re.sub(r"\{([^{}]+)\}", one, template)
    return re.sub(r" {2,}", " ", out).strip() if template.startswith("{") else re.sub(r" {2,}", " ", out)


def opera_lines(story, vars_, flags):
    """{PR key: the line with BC's cast} for the opera lines the game has."""
    out = {}
    for key, subs in OPERA_LINES.items():
        text = story.get(key)
        if text is None:
            continue
        new = text.replace("\\n", "\n")      # the PR's line breaks are "\\n" codes: a word at a line's start
        fills = [opera_fill(tpl, vars_, flags) for _, tpl in subs]
        for i, (pat, _) in enumerate(subs):            # one pass: a cast name ("Draco" as Ralse) isn't swapped again
            new = re.sub(pat, f"\x00{i}\x00", new)
        new = re.sub("\x00(\\d+)\x00", lambda m: fills[int(m[1])], new)
        new = re.sub(r'"(\u201c[^"\u201d]*\u201d)(\.?)"', r"\1\2", new)   # a name with its own quotes: no second pair
        new = new.replace("\n", "\\n")
        if new != text:
            out[key] = new
    return out


# alasdraco's prop: BC's object on the rafters in Ultros's place of the 4-ton weight (its opera log "Opera Rafters"),
# the weight's object in the opera's three event layers (Map_20161_5: asset 157) given the PR asset the kit learned
# for BC's SNES sprite (event_translate.sprite_assets). BC's book and rat have no PR asset learned: the weight stays.
# The balcony's bouquet has no object in the PR's maps to re-skin (its words carry BC's item: {operaItem}).
RAFTER_ASSETS = {"letter": 94, "mini statue": 103, "baby": 9, "4 ton weight": 157, "fire": 24}
RAFTER_LAYERS = [("map_20161", "Map_20161", "Map_20161_5", f) for f in ("ev_e_0330.json", "ev_e_0341.json", "ev_e_0344.json")]
MAP_FILES["alasdraco"] = list(RAFTER_LAYERS)


def opera_rafters(ctx, item):
    asset = RAFTER_ASSETS.get(item or "")
    if not asset or asset == 157:
        return None
    n = 0
    for g, f, sub, name in RAFTER_LAYERS:
        doc = ctx.map_file(MAP_REL.format(group=g, folder=f, sub=sub, file=name))
        for _, o, pr in _objects(doc):
            if pr.get("asset_id") == 157:
                _set_prop(o, "asset_id", asset)
                n += 1
    return {"item": item, "asset": asset, "objects": n}


# the opera roles' name boxes (story_cha_en): the role -> BC's cast (Maria's lines are (CELES)'s: Celes sings her)
OPERA_SPEAKERS = {"Impresario": "{Impresario}", "Draco": "{Draco}", "Ralse": "{Ralse}"}


def speaker_keys():
    """Every story_cha_en line a seed's events may change (the baseline keeps them as the game has them): the
    opera roles' and the World of Ruin recruit sites' lines."""
    cha = P.messages("story_cha", "en")
    h = _holiday()
    keys = ({k for k, v in cha.items() if v in OPERA_SPEAKERS} | set(h["santa_cha"]) | set(santa_battle_keys(h)[1]) |
            {k for b in h["spooky"] for k in b["keys"] if k in cha})
    for _, names, _ in SITES.values():
        for name in names:
            keys |= {o["operands"]["sValues"][0] for o in S.load(name)["Mnemonics"] if o["mnemonic"] == "Msg"} & set(cha)
    return sorted(keys)


# BC's always-on texts (every seed, by BC's own rules: the hints by its flags, the poem and passwords always), in the
# PR's lines: (key, how). BC's words where it changed the SNES line; the rest of the PR's line kept.
SPRINT_KEY = "E0135_00_040_a_01"       # SNES 0xB8: the Sprint Shoes' owner (BC: which spell they teach)
SABIN_KEY = "N005_C02_063_01_01"       # SNES 0xB9: Duncan's wife (BC: Sabin's command)
HOUSE_KEY = "N002_C00_201_04_01"       # SNES 0x8A4: the collapsing house (BC: what its monsters do)
POEM_KEY = "E0735_00_475_a_01"         # SNES 0x9FC: Cyan's poem at Mt. Zozo... the stone tablet's (BC: a random poem)
PASSWORD_KEYS = ["E0075_00_060_c_01", "E0075_00_060_c_02", "E0075_00_060_c_03"]   # SNES 0xE0's three choices
TEXT_KEYS = [SPRINT_KEY, SABIN_KEY, HOUSE_KEY, POEM_KEY] + PASSWORD_KEYS
POEM_PAGE = "<WAIT1c><AUTO_P>"         # the PR poem's own page end (BC: 390 frames a page)


def _plain(text):
    return re.sub(r"<[^>]*>", "", text or "").strip()


def _ability_name(snes_spell):
    import idmap
    pr = idmap.spell(snes_spell) if snes_spell is not None else None
    if pr is None:
        return None
    names = {(r["type_id"], r["type_value"]): r["mes_id_name"] for r in P.Table("content")}
    return _plain(P.messages("system", "en").get(names.get(("4", str(pr))), "")) or None


def _command_name(ctx, snes_cmd):
    import port
    pr = port.SNES_CMD.get(snes_cmd)
    if pr is None:
        return None
    row = ctx.table("command").rows.get(pr)
    key = row["mes_id_name"] if row else f"MSG_CMD_NAME_{pr:02d}"
    import seed_live as L
    seed_text = {}
    path = os.path.join(ctx.out, *L.MESSAGE_PATH.split("/"), "system_en.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f.read().splitlines():
                if "\t" in line:
                    k, v = line.split("\t", 1)
                    seed_text[k] = v
    return _plain(seed_text.get(key) or P.messages("system", "en").get(key, "")) or None


def _bc_poem(text):
    """BC's poem (its <line>, page waits and <page>) as the PR writes a poem: centred lines, the PR's page end."""
    pages = [p for p in re.split(r"<wait \d+ frames?>(?:<wait \d+ frames?>)*(?:<page>)?", text) if p.strip()]
    out = []
    for page in pages:
        out.append("\\n".join("<CT>" + ln.strip() for ln in page.split("<line>") if ln.strip()) + POEM_PAGE)
    return "\\n".join(out)


def always_texts(ctx):
    got = ctx.capture.get("texts") or {}
    story = P.messages("story_mes", "en")
    done = {}
    spell = _ability_name(got.get("sprint_spell")) if "sprint_spell" in got else None
    if spell and SPRINT_KEY in story:
        first = story[SPRINT_KEY].split("<P>")[0]
        done[SPRINT_KEY] = f"{first}<P>\\nThese teach me {spell}!"
    command = _command_name(ctx, got["sabin_command"]) if "sabin_command" in got else None
    if command and SABIN_KEY in story:
        pages = story[SABIN_KEY].split("<P>\\n")
        done[SABIN_KEY] = "<P>\\n".join(pages[:1] + [f"He is a master of the art of {command}."] + pages[1:])
    house = got.get("house")
    if house and HOUSE_KEY in story:
        word = house["word"]
        if word.endswith("-"):
            name = _ability_name(house.get("spell")) or word[:-1]
            word = name + "-"
        done[HOUSE_KEY] = story[HOUSE_KEY].replace("petrifying", word + "ing", 1)
    if got.get("poem") and POEM_KEY in story:
        done[POEM_KEY] = _bc_poem(got["poem"])
    if got.get("passwords") and all(k in story for k in PASSWORD_KEYS):
        for k, pw in zip(PASSWORD_KEYS, got["passwords"]):
            done[k] = f'"{pw}"'
    ctx.story.update(done)
    ctx.log(f"texts: {sorted(done)}")
    return {"keys": sorted(done), "passwords": got.get("passwords"), "sprint": spell, "sabin": command,
            "house": house["word"] if house else None}


# --- katn (BC's mode "Race - Kefka @ Narshe": randomizer.randomize, Options_.mode.name == 'katn')
# BC: start_with_random_espers (a call at CC/9AB6 to its code at 0x305000: `78 0E 78 0F`, then `86 <0x36 + esper>` per
# esper, FE) and set_lete_river_encounters (the raft's random rolls always fight); the end at Kefka (the_end_comes_
# beyond_katn) waits for the lead's choice. PR: the espers as GetItem in the opening's first script (not the title's
# demo), the raft script's "no battle this time" branches (SetRandomValue MapLocalVariable 3, then 3 == 3 skips the
# Encount) made Nops.
KATN_ESPERS = 0x305000
LETE_RIVER = "sc_e_0063_3"            # the raft ride (map 30380): CB/0486.. in BC's patch
NARSHE_WON = "sc_e_0259_1"            # after Kefka at Narshe: [2] the battle's result, [3] lost -> 30, [4] won on
SCRIPTS["mode:katn"] = [OPENING, LETE_RIVER, NARSHE_WON]

# The race modes' end (katn: Kefka at Narshe; dragonhunt: the 8th dragon). BC rolls its credits (event command BB);
# the PR's staff roll is built on the real ending's scenes, so ours is an end screen (the lead's choice, 2026-11-21;
# the real ending is an audit gap item): the race-over line (its text set live by the plugin's BC:raceover: the time
# played, the seed and its flags), then the title (BC:totitle: the game's own GotoTitle; a save loads from there, so
# nothing traps the player).
DRAGONS = {"sc_e_0734_1": 108, "sc_e_0779_1": 138, "sc_e_0809_1": 148, "sc_e_0879_1": 166, "sc_e_0889_1": 175,
           "sc_e_0893_3": 178, "sc_e_0974_1": 220, "sc_e_0981_1": 225}      # each dragon's win sets its ScenarioFlag2
SCRIPTS["mode:dragonhunt"] = sorted(DRAGONS)


def race_end(ctx, mode):
    keys = ctx.data.setdefault("race_end", {})
    key = keys.get(mode) or keys.setdefault(mode, ctx.line(mode, "The race is over!"))
    return [S.op("SysCall", s=[f"BC:raceover {key} {mode}"]), S.op("Msg", i=[0, 2], s=[key]),
            S.op("SysCall", s=["BC:totitle"]), S.op("Exit")]


def dragonhunt(ctx):
    for name, flag in sorted(DRAGONS.items()):
        sc = ctx.script(name)
        ms = sc["Mnemonics"]
        at = next(k for k, o in enumerate(ms) if o["mnemonic"] == "SetFlag" and o["operands"]["iValues"][0] == flag
                  and o["operands"]["sValues"][0] == "ScenarioFlag2")
        S.hook(sc, at + 1, "bc_dragonhunt_end", [_if("ScenarioFlag2", f, 0, "@vanilla") for f in sorted(DRAGONS.values())]
               + race_end(ctx, "dragonhunt"))
    ctx.log("dragonhunt: the 8th dragon ends the race (our end screen, then the title)")
    return {"dragons": len(DRAGONS)}


def katn_espers(rom):
    """BC's starting espers (SNES esper ids) from its code at 0x305000, or [] when it isn't there."""
    if rom is None or bytes(rom[KATN_ESPERS:KATN_ESPERS + 4]) != bytes([0x78, 0x0E, 0x78, 0x0F]):
        return []
    out, at = [], KATN_ESPERS + 4
    while rom[at] == 0x86:
        out.append(rom[at + 1] - 0x36)
        at += 2
    return out


def katn(ctx):
    import idmap
    espers = katn_espers(ctx.rom)
    contents = [idmap.esper_content(e) for e in espers if idmap.esper_content(e)]
    if contents:
        sc = ctx.script(OPENING)
        ms = sc["Mnemonics"]
        assert ms[2]["mnemonic"] == "Branch" and ms[2]["operands"]["iValues"][:2] == [7, 1], "the opening changed"
        S.hook(sc, 2, "bc_katn_espers", [S.op("Branch", i=[7, 1, "@vanilla"], s=["MapLocalVariable", EQ, "imm"])] +
               [S.op("GetItem", i=[cid, 1]) for cid in contents])
    sc = ctx.script(LETE_RIVER)
    ms = sc["Mnemonics"]
    forced = 0
    for k in range(1, len(ms)):
        o, prev = ms[k], ms[k - 1]
        if (o["mnemonic"] == "Branch" and o["operands"]["sValues"][0] == "MapLocalVariable" and
                o["operands"]["iValues"][0] == 3 and prev["mnemonic"] == "SetRandomValue"):
            ms[k] = S.op("Nop", label=o.get("label", ""), kind=o.get("type", 1))
            forced += 1
    sc = ctx.script(NARSHE_WON)
    ms = sc["Mnemonics"]
    assert ms[2]["operands"]["sValues"][0] == "戦闘結果取得" and ms[3]["mnemonic"] == "Branch", "Kefka at Narshe changed"
    S.hook(sc, 4, "bc_katn_end", race_end(ctx, "katn"))
    ctx.log(f"katn: {len(contents)} starting espers {espers}, {forced} Lete River rolls always fight, the end at Narshe")
    return {"espers": espers, "lete_river": forced}


# --- christmas (BC turns it on by the seed's date: randomizer.py:5532; it's in BC's effective flags)
# BC's manage_santa: Kefka -> Santa in its first dialogue list, KEFKA -> SANTA (the SNES's speaker prefixes) in its
# second, and Kefka's battle names. PR: the same lines (data/bc_events_holiday.json: the PR keys of BC's ids), the
# name boxes of the second list, Kefka's monster name; his battle speech (santa_battle: BC's battle-event boxes, by wording). Its sprites, windows and music are bc-sprites' / bc-music's.
HOLIDAY_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bc_events_holiday.json")


def _holiday():
    with open(HOLIDAY_DATA, encoding="utf-8") as f:
        return json.load(f)


def santa_battle_keys(h=None):
    """christmas's battle lines (data/bc_events_holiday.json santa_battle, BC's two battle-text lists matched to the
    PR's battle-scene lines): (story_mes keys whose words say Kefka, story_cha keys whose name box says Kefka)."""
    b = (h or _holiday())["santa_battle"]
    text = sorted({k for ks in b["text"].values() for k in ks})
    cha = sorted({k for part in ("cha", "named") for ks in b[part].values() for k in ks})
    return text, cha


def christmas(ctx):
    h = _holiday()
    story = P.messages("story_mes", "en")
    cha = P.messages("story_cha", "en")
    system = P.messages("system", "en")
    battle_text, battle_cha = santa_battle_keys(h)
    lines = {k: re.sub(r"\bKefka\b", "Santa", story[k]) for k in h["santa_text"] + battle_text if k in story}
    ctx.story.update({k: v for k, v in lines.items() if v != story[k]})
    speakers = {k: "Santa" for k in h["santa_cha"] + battle_cha if cha.get(k) == "Kefka"}
    ctx.speakers.update(speakers)
    for k in h["santa_monsters"]:
        if system.get(k) == "Kefka":
            ctx.lines.append((k, "Santa"))
    ctx.log(f"christmas: Santa in {len(lines)} lines and {len(speakers)} name boxes "
            f"({len(battle_text)} and {len(battle_cha)} of them in battle)")
    return {"lines": len(lines), "speakers": len(speakers), "battle": len(battle_text) + len(battle_cha)}


# --- halloween (by the seed's date as christmas). BC's manage_spookiness points 13 event text boxes (5 of them only
# without notawaiter, whose cuts take those scenes) at the Phantom Train's ghost lines ("...No...escape..." and
# "Nowhere...to...run..."). PR: the lines of each box it replaced (data/bc_events_holiday.json "spooky": the PR keys of
# the SNES dialogue there) say the ghost line, with no name box. The demon chocobo is bc-sprites'.
def halloween(ctx):
    h = _holiday()
    story = P.messages("story_mes", "en")
    ghost = {kind: story.get(key, "") for kind, key in h["spooky_text"].items()}
    done = 0
    for box in h["spooky"]:
        if box["unless_notawaiter"] and ctx.on("notawaiter"):
            continue
        for k in box["keys"]:
            if k in story and ghost.get(box["kind"]):
                ctx.story[k] = ghost[box["kind"]]
                ctx.speakers[k] = ""
                done += 1
    ctx.log(f"halloween: {done} lines say the ghosts' words")
    return {"lines": done}


# --- Namingway (every seed but the cave modes: BC's namingway(), randomizer.py:4423-4456). BC adds an NPC to both
# airships (SNES map 7 at 39,12 and map 0x0C at 14,45, sprite 0x24) asking "Rename lead character?" -> the naming
# screen. PR: the NPC in each airship room's entity_default (snes_maps.to_pr of BC's spot; the PR asset the kit
# learned for SNES sprite 0x24: event_translate.sprite_assets), its talk script (ours: script table rows 9212-9213)
# asks the same, then BranchByLeader -> the leader's own naming call (名前入力：<name>).
NAMERS = {"sc_bc_namer_bj": ("map_20171", "Map_20171", "Map_20171_1", (39, 16), 9212),    # the Blackjack (SNES 7)
          "sc_bc_namer_fa": ("map_20391", "Map_20391", "Map_20391_1", (14, 45), 9213)}    # the Falcon (SNES 0x0C)
NAMER_ASSET = 12                      # SNES NPC sprite 0x24 in the PR (sprite_assets: 12, then 29)
for _n, (_g, _f, _sub, _, _) in NAMERS.items():
    NEW_SCRIPTS[_n] = (_g, _f, _sub)
MAP_FILES["namingway"] = [(g, f, sub, "entity_default.json") for g, f, sub, _, _ in NAMERS.values()]


def namer_script(name, ask, yes, no):
    ops = [S.label("Main"), S.op("Msg", i=[0, 2], s=[ask]), S.op("Select", s=[yes, no]), _choice(1, "@end")]
    ops += [S.op("BranchByLeader", i=[c + 1, f"@name_{c + 1}"]) for c in range(14)]
    ops += [S.op("Exit")]
    for c in range(14):
        ops += [S.label(f"name_{c + 1}"), S.op("SysCall", s=["名前入力：" + PR_NAMES[c]]), S.op("Exit")]
    ops += [S.label("end"), S.op("Exit")]
    S._resolve(ops, 0)
    sc = empty_script(name, "Beyond Chaos: Namingway (rename the lead character)")
    sc["Mnemonics"] = ops
    sc["Segments"] = [{"Label": "Main", "EntryPoint": 0, "Count": len(ops)}]
    return sc


def namingway(ctx):
    ask = ctx.line("namingway", "Rename lead character?")
    yes, no = ctx.line("namingway", "Yes"), ctx.line("namingway", "No")
    with open(os.path.join(P.VANILLA, *GOGO_TEMPLATE.split("/")), encoding="utf-8") as f:
        tpl = next(o for _, o, pr in _objects(json.load(f)) if pr.get("asset_id") == 132)
    t = ctx.table("script")
    for name, (group, folder, sub, (x, y), sid) in sorted(NAMERS.items()):
        ctx.set_script(name, namer_script(name, ask, yes, no))
        doc = ctx.map_file(MAP_REL.format(group=group, folder=folder, sub=sub, file="entity_default.json"))
        layer = next(l for l in doc["layers"] if l.get("type") == "objectgroup") if any(
            l.get("type") == "objectgroup" for l in doc["layers"]) else next(
            sl for l in doc["layers"] for sl in l.get("layers", []) if sl.get("type") == "objectgroup")
        objs = list(_objects(doc))
        npc = copy.deepcopy(tpl)
        npc["id"] = max([o["id"] for _, o, _ in objs] or [0]) + 1
        npc["x"] = x * 16
        npc["y"] = (y + 1) * 16 if "gid" in npc else y * 16
        for k, v in (("asset_id", NAMER_ASSET), ("script_id", sid), ("direction", 4),
                     ("entity_id", max([pr.get("entity_id", 0) for _, _, pr in objs] or [0]) + 1)):
            _set_prop(npc, k, v)
        _set_prop(npc, "message_key", "", "string")
        layer["objects"].append(npc)
        t.rows[sid] = {"id": str(sid), "script_name": name}
    ctx.log("namingway: the renaming NPC on both airships")
    return {"rooms": [v[2] for v in NAMERS.values()]}


# --- Gau's auto-recruit (o, w or t: every preset; BC randomizer.py:5564-5568 auto_recruit_gau(stays_in_wor=not r
# and not mimetime), AutoRecruitGauSub at :377-398). BC's three patches, as the US ROM has them:
#   CB/C19C (Gau's first scene, SNES map 156: CB/C188 `3F 0B 00` party_char Gau party 0, the naming, then the run-off):
#     a call to BC's CF/E1A `50 BC 59 10` (the tint/fade it displaced) `3F 0B 01` (Gau into party 1) `D4 FB`
#     `B8 49` FE: Gau stays with the party, his recruit done.
#   C2/4856 `89 FF`: the Veldt battles' "Gau joins after a battle" check (the dried-meat recruit) never fires.
#   CA/5324 `D4 FB` (with stays_in_wor): his bit kept through the collapse: BC's free World of Ruin character
#     (randomizer.py:5985-5988: wor_free_char = 0xB with o/w/t), at the Falcon.
# PR: his first scene sc_e_0218_2 ([35] メンバー加入：ガウ, [39] メンバー離脱：ガウ: he runs off) keeps him ([39] a Nop)
# and marks the dried-meat recruit done (ScenarioFlag1 126, set by sc_e_0239_b [105] before its join), so the Veldt's
# recruit scene never comes; in the World of Ruin he rejoins as the Falcon rises (as r's Falcon site: falcon_recruit),
# unless r (its own Falcon character) or mimetime (the Zone Eater holds him).
GAU_FIRST = "sc_e_0218_2"
GAU_RECRUITED = ("ScenarioFlag1", 126)
SCRIPTS["gau"] = [GAU_FIRST, FALCON_SCENE]


def gau(ctx):
    sc = ctx.script(GAU_FIRST)
    ms = sc["Mnemonics"]
    at = next(k for k, o in enumerate(ms) if o["mnemonic"] == "SysCall" and o["operands"]["sValues"][0] == "メンバー離脱：ガウ")
    assert any(o["mnemonic"] == "SysCall" and o["operands"]["sValues"][0] == "メンバー加入：ガウ" for o in ms[:at]), \
        "Gau's first scene changed"
    ms[at] = S.op("Nop", label=ms[at].get("label", ""), kind=ms[at].get("type", 1))
    S.hook(sc, at, "bc_gau_stays", [_flag(*GAU_RECRUITED)])
    wor = not ctx.on("r") and not ctx.on("mimetime")
    if wor:
        falcon_recruit(ctx, 0x0B)
    ctx.log(f"gau: auto-recruited at his first scene{'; rejoins with the Falcon' if wor else ''}")
    return {"wor": wor}


# --- The auction house (every seed but the cave modes: BC's manage_auction_house, randomizer.py:4163-4195, called
# at :5792). Vanilla's sale is a chain of blocks (CB/4EA4 the entry calls the first), each "if <sold or world> go to
# X" and/or a 50% random_jump to the next block, else its own sale; BC rewrites both pointers of each block (its "two
# ways": the condition's and the random jump's) into a new order, the espers first:
#   entry -> Zoneseek (CB/5312: if bought, or 50% -> Golem) -> Golem (5197: if bought, or 50% -> Golem WoR) ->
#   Golem WoR (58FA: same check -> Zoneseek WoR) -> Zoneseek WoR (5A39: if bought, or 50% -> Cherub Down) ->
#   Cherub Down (4ECC: World of Ruin -> Hero Ring; 50% -> Chocobo) -> Chocobo (501D: 50% -> Cure Ring) -> Cure Ring;
#   Hero Ring (55B0: 50%, or bought -> Zephyr Cape) -> Zephyr Cape (5B85: bought, or 50% -> 1/1200 Airship) ->
#   1/1200 Airship (570C: 50% -> Imp Robot) -> Imp Robot.
# PR: the dispatcher sc_e_0422 draws one sale at random among the world's (SetRandomValue; a bought esper or ring
# draws again: its [5]); ours runs BC's chain at [6] instead, with the PR's sold flags (Golem ScenarioFlag1 204,
# Zoneseek 205, Hero Ring ScenarioFlag2 121, Zephyr Cape 120) and world flag (ScenarioFlag2 41), each node's 50% as
# SetRandomValue 1..2, then the PR's own sale (its label in sc_e_0422: the sale or its ChangeScript).
AUCTION = "sc_e_0422"
AUCTION_SALES = {"golem": 22, "zoneseek": 108, "cherub": 111, "chocobo": 113, "cure": 115, "zephyr": 117, "hero": 120,
                 "airship": 123, "imp": 125}                   # the sales' labels in sc_e_0422 (asserted below)
AUCTION_CHAIN = [   # (node, sold flag or None, its sale, the next node; "world": Cherub Down's World of Ruin test)
    ("zoneseek", ("ScenarioFlag1", 205), "zoneseek", "golem"),
    ("golem", ("ScenarioFlag1", 204), "golem", "golem_wor"),
    ("golem_wor", ("ScenarioFlag1", 204), "golem", "zoneseek_wor"),
    ("zoneseek_wor", ("ScenarioFlag1", 205), "zoneseek", "cherub"),
    ("cherub", "world", "cherub", "chocobo"),
    ("chocobo", None, "chocobo", "cure"),
    ("cure", None, "cure", None),
    ("hero", ("ScenarioFlag2", 121), "hero", "zephyr"),
    ("zephyr", ("ScenarioFlag2", 120), "zephyr", "airship"),
    ("airship", None, "airship", "imp"),
    ("imp", None, "imp", None),
]
SCRIPTS["auction"] = [AUCTION]


def auction(ctx):
    sc = ctx.script(AUCTION)
    ms = sc["Mnemonics"]
    labels = {k: ms[i]["label"] for k, i in AUCTION_SALES.items()}
    assert all(labels.values()) and ms[5]["label"] == "崩壊前判定" and ms[6]["mnemonic"] == "Branch" and \
        ms[8]["mnemonic"] == "SetRandomValue", "the auction's dispatcher changed"
    ops = []
    for node, sold, sale, nxt in AUCTION_CHAIN:
        skip = f"@bc_auction_{nxt}" if nxt else None
        ops.append(S.label(f"bc_auction_{node}"))
        if sold == "world":
            ops.append(_if("ScenarioFlag2", 41, 1, "@bc_auction_hero"))
        elif sold:
            ops.append(_if(sold[0], sold[1], 1, skip))
        if nxt:
            ops += [S.op("SetRandomValue", i=[3, 2], s=["MapLocalVariable"]),
                    S.op("Branch", i=[3, 1, skip], s=["MapLocalVariable", EQ, "imm"])]
        ops.append(S.op("Jump", i=[AUCTION_SALES[sale]]))
    S.hook(sc, 6, "bc_auction", ops)              # [5] (a labelled Nop: a bought sale's draw-again) runs on into it
    ctx.log("auction: BC's sale order (the espers first, each a 50% chance)")
    return {"nodes": len(AUCTION_CHAIN)}


# --- The opening's seed display (every seed: BC's manage_opening, randomizer.py:4113-4145): BC rewrites the opening
# credits to "BEYOND CHAOS CE by DarkSlash88", the based-on lines, the flags (its one-letter flags, upper case, and
# FLAGS ON/OFF), the seed as a code (each digit a consonant: 0 b .. 9 m, upper case) and "ver. V"
# (config.VERSION_ROMAN). PR shows that text alongside the first visible field dialogue in the opening's last
# scene. Its former Msg at sc_e_0001_4 [5] could strand the credits flight on a black fade: the field scene
# already has a working message window at [23]. BC:seedinfo fills the line from the active seed and flags.
OPENING_SEED_SCENE = "sc_e_0001_5"
SCRIPTS["seedinfo"] = [OPENING_SEED_SCENE]


def seedinfo(ctx):
    sc = ctx.script(OPENING_SEED_SCENE)
    ms = sc["Mnemonics"]
    assert ms[23]["mnemonic"] == "Msg" and ms[23]["operands"]["sValues"][0] == "E0001_04_003_a_01", \
        "the opening's first field dialogue changed"
    key = ctx.line("seedinfo", "Beyond Chaos CE")
    S.hook(sc, 23, "bc_seedinfo", [S.op("SysCall", s=[f"BC:seedinfo {key}"]), S.op("Msg", i=[0, 0], s=[key])])
    return {"key": key}


def story_keys():
    """Every story_mes_en line a seed's events may reword (the baseline keeps them as the game has them)."""
    h = _holiday()
    return sorted(set(OPERA_LINES) | set(TEXT_KEYS) | set(h["santa_text"]) | set(santa_battle_keys(h)[0]) |
                  {k for b in h["spooky"] for k in b["keys"]})


def alasdraco(ctx):
    opera = ctx.capture.get("opera") or {}
    vars_ = opera.get("vars") or {}
    if not vars_.get("maria"):
        ctx.log("alasdraco: BC's opera cast wasn't captured (bc_events.prepare): the opera's words stay the PR's")
        return {"cast": {}}
    flags = set(opera.get("flags") or [])
    story = P.messages("story_mes", "en")
    ctx.story.update(opera_lines(story, vars_, flags))
    for key, who in P.messages("story_cha", "en").items():
        if who in OPERA_SPEAKERS:
            ctx.speakers[key] = opera_fill(OPERA_SPEAKERS[who], vars_, flags)
    cast = {r: _bc_text(vars_.get(r.lower(), "")) for r in ("Maria", "Draco", "Ralse", "Impresario")}
    rafters = opera_rafters(ctx, opera.get("rafters"))
    part = {"rafters": rafters, "cast": cast, "factions": [_bc_text(vars_.get("operaeast", "")), _bc_text(vars_.get("operawest", ""))],
            "item": vars_.get("operaitem", ""), "lines": len(ctx.story)}
    ctx.log(f"alasdraco: {cast}, {part['factions'][0]} vs {part['factions'][1]}, the {part['item']}: "
            f"{part['lines']} lines")
    return part

# --- notawaiter: cutscene skips ---------------------------------------------------------------------------------------
# BC (manage_skips, tables/skipevents.txt + 4 hardcoded): "Up to Kefka at Narshe, the vast majority of mandatory
# cutscenes are completely removed" (and later ones: Ramuh, Zozo, the Maduin flashback, the boat to Thamasa, Thamasa,
# Nikeah...), the battles kept, their event items given silently. PR: each scene script that shows a line BC cuts
# (data/bc_events_notawaiter.json, measured from BC's output: 113 SNES scenes, 573 lines -> 159 PR scripts) is
# condensed: the same instructions at the same indices (jumps stay valid), its show (lines, menus, puppets, moves,
# animations, waits, fades out, shakes, flashes, sounds) turned into plain Nops, its state (flags, variables, party,
# items, gil, entity layers, battles, map changes, vehicles, music, recovery, autosaves, every SysCall) kept; a menu
# takes its first answer (BC's skips answer it, e.g. Banon's questions). The cut is the kit's (tools/pr_scene_cut.py).
NAW_DATA = os.path.join(os.path.dirname(HERE), "data", "bc_events_notawaiter.json")
def naw_scripts():
    """The scene scripts to cut: the measured list less the ones kept as the PR's ("keep": why each)."""
    with open(NAW_DATA, encoding="utf-8") as fh:
        d = json.load(fh)
    return [n for n in d["scripts"] if n not in d.get("keep", {})]


NAW_CUT = naw_scripts() if os.path.exists(NAW_DATA) else []          # the scripts cut
SCRIPTS["notawaiter"] = NAW_CUT + ["sc_e_0225"]                         # + the Mobliz letters (hooked, not cut)


# Banon's question (sc_e_0062): the PR gives the Gauntlet on "Yes" or the Genji Glove after three "No"s (ScenarioFlag3
# 34 gates the second, sc_e_0062_1); BC's skip answers for the player and gives both, the items at its skip pointers
# (chestrandomizer.mutate_event_items with cutscene_skip: `80 item` at CA/FAC9 and CA/FDE7, rerolled with `t`)
BANON, GAUNTLET = "sc_e_0062", 307
BANON_ITEMS = (0xAFAC9, 0xAFDE7)


def banon(ctx):
    import idmap
    import bc_gifts
    items = []
    for at in BANON_ITEMS:
        if ctx.rom is not None and ctx.rom[at] == 0x80:
            try:
                items.append(idmap.item_content(ctx.rom[at + 1]))
            except KeyError:
                pass
    if len(items) != 2 or not all(items):
        return None
    sc = ctx.script(BANON)
    ms = sc["Mnemonics"]
    gets = [k for k, o in enumerate(ms) if o["mnemonic"] == "GetItem" and o["operands"]["iValues"][0] == GAUNTLET]
    assert gets, "Banon's question changed"
    for k in gets:
        ms[k]["operands"]["iValues"][0] = items[0]
        S.hook(sc, k, "bc_banon", [S.op("GetItem", i=[items[1], 1])])      # then the (BC's) first, as hooked
    names = [bc_gifts.content_name(item) for item in items]
    assert all(names), f"Banon's gifts have no item names: {items}"
    ctx.story["E0062_00_066_a_14"] = f"<CT>Obtained {names[0]}!<P>\\n<CT>Obtained {names[1]}!"
    return items


# The Mobliz letters (sc_e_0225, the post office): the PR's quest is five sends of 500 gil, each once the soldier has
# handed over the next item (received/sent flag pairs below). BC's notawaiter (hardcoded at 0xC67CF, dialogue 0x2FF):
# once the first letter is in hand and until everything is sent, one offer sends it all for 2500 GP.
LETTERS = "sc_e_0225"
LETTER_FLAGS = [("ScenarioFlag2", 247), ("ScenarioFlag2", 248), ("ScenarioFlag2", 250), ("ScenarioFlag2", 251),
                ("ScenarioFlag2", 253), ("ScenarioFlag2", 254), ("ScenarioFlag3", 0), ("ScenarioFlag3", 1),
                ("ScenarioFlag3", 3), ("ScenarioFlag3", 4)]
LETTERS_PRICE = 2500


def mobliz_letters(ctx):
    sc = ctx.script(LETTERS)
    ms = sc["Mnemonics"]
    assert ms[3]["mnemonic"] == "Branch" and ms[3]["operands"]["iValues"][:3] == [247, 0, 57] and         ms[6]["mnemonic"] == "Select" and ms[61]["label"] and ms[63]["label"], "the Mobliz letters changed"
    send, forget = [k for k in ms[6]["operands"]["sValues"] if k][:2]
    offer = ctx.line("notawaiter", f"For {LETTERS_PRICE} gil, I can send two letters, a record, a potion and a book "
                                   "all at once. How about it?")
    S.hook(sc, 3, "bc_letters", [
        _if("ScenarioFlag2", 247, 0, "@vanilla"),             # no letter from the soldier yet: as the PR
        _if("ScenarioFlag3", 4, 1, "@vanilla"),               # all sent already
        S.op("Msg", s=[offer]),
        S.op("Select", s=[send, forget]),
        _choice(1, 63),                                       # (Forget it.)
        S.op("SysCall", s=[f"BC:pay {LETTERS_PRICE}"]),
        S.op("Branch", i=[0, 0, 61], s=["MapLocalVariable", EQ, "imm"]),   # not enough gil: the PR's line
    ] + [_flag(c, i) for c, i in LETTER_FLAGS] + [S.op("Exit")])
    return LETTERS_PRICE


def notawaiter(ctx):
    names, cut = [], 0
    for name in NAW_CUT:
        try:
            sc = ctx.script(name)
        except (KeyError, FileNotFoundError):
            continue
        cut += condense(sc)
        names.append(name)
    gifts = banon(ctx)
    mobliz_letters(ctx)
    ctx.log(f"notawaiter: {len(names)} scene scripts condensed ({cut} instructions of show cut); Banon gives {gifts}; "
            f"the Mobliz letters for {LETTERS_PRICE} gil at once")
    return {"scripts": len(names), "cut": cut, "banon": gifts, "letters": LETTERS_PRICE}


HANDLERS = {"lessfanatical": lessfanatical, "shadowstays": shadowstays, "j": j, "k": k, "regionofdoom": regionofdoom,
            "airship": airship, "worringtriad": worringtriad, "notawaiter": notawaiter, "r": r, "mimetime": mimetime,
            "alasdraco": alasdraco, "texts": always_texts, "mode:katn": katn, "mode:dragonhunt": dragonhunt,
            "christmas": christmas, "halloween": halloween, "namingway": namingway, "gau": gau, "auction": auction,
            "seedinfo": seedinfo}


def apply(out, flags, rom=None, vanilla_rom=None, spoiler="", capture=None, log=print, mode="normal"):
    """The seed's events into the packed seed folder `out`. Returns (files written (rels), bc_events.json).
    mode: BC's mode (normal, katn, dragonhunt...): its own changes run after the flags'."""
    ctx = Ctx(out, flags, rom, vanilla_rom, spoiler, capture, log)
    ctx.mode = mode or "normal"
    ctx.data["mode"] = ctx.mode
    steps = ["texts"] + ([] if ctx.on("ancientcave") else ["namingway", "auction"]) + [f for f in FLAGS if ctx.on(f)]
    if any(ctx.on(f) for f in ("o", "w", "t")) and not ctx.on("ancientcave"):
        steps.append("gau")
    steps += [f"mode:{ctx.mode}"] if f"mode:{ctx.mode}" in HANDLERS else []
    steps.append("seedinfo")
    for flag in steps:
        if flag in HANDLERS:
            keep = (copy.deepcopy(ctx.scripts), copy.deepcopy(ctx.files), len(ctx.lines), copy.deepcopy(ctx.tables),
                    dict(ctx.story), dict(ctx.speakers))
            try:
                part = HANDLERS[flag](ctx)
            except Exception as e:  # noqa: BLE001 - the seed still plays that flag's part as the PR's own
                import traceback
                log(f"{flag}: failed, left as the game's own ({e})")
                log(traceback.format_exc())
                ctx.data.setdefault("failed", []).append(flag)
                # its half-done edits go: the scripts, files and tables as they were before it
                ctx.scripts, ctx.files, ctx.tables, ctx.story, ctx.speakers = keep[0], keep[1], keep[3], keep[4], keep[5]
                del ctx.lines[keep[2]:]
                continue
            if part is not None:
                ctx.data[flag] = part
    return ctx.finish()


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["files"]:
        print("\n".join(files()))
    elif a[:1] == ["show"] and len(a) == 2:
        print(json.dumps(json.load(open(os.path.join(a[1], EVENTS_JSON), encoding="utf-8")), indent=1))
    else:
        sys.exit(__doc__)
