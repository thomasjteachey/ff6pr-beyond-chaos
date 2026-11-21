"""Beyond Chaos's `strangejourney` (the entrance shuffle) on the Pixel Remaster: SNES short entrances -> PR doors.

  python tools/bc_entrances.py index      (writes data/bc_entrance_index.json from the US ROM and the PR extract)
  python tools/bc_entrances.py show       (the index's coverage)
  python tools/bc_entrances.py diff [--seed 1234567890] [--flags "..."]
                                          (a strangejourney seed through BC: how many changed doors the index rewires)
  python tools/bc_entrances.py apply OUT [--seed ...] [--flags ...] [--romfree]
                                          (the seed step, apply(), into OUT: files/<map files>, bc_doors.json)
  python tools/bc_entrances.py tables OUT.json [--romfree]   (BC's short entrances and changes, as JSON)

BC (randomizer.create_dimensional_vortex) reads every map's short entrances (6 bytes at DF/BB00 + the
map's 2-byte offset: x, y, dest word (map in bits 0-8, flags above), dest x, dest y; maps 0-414, as
its locationrandomizer.EntranceSet), drops duplicates (Location.uniqify_entrances), leaves a fixed list
vanilla (`bc_kept`: the world maps both ways, the Esper world, the collapsing house, the opening's
mines...), permutes (dest, dest x, dest y) between the rest (a destination is dealt only when its map
has an entrance within 3 tiles of the landing spot, never back into the door's own map), keeps twin
doors (adjacent, same destination) together, and clears the dest word's flag bits off the world maps.
Long entrances (7-byte rows/columns at ED/F480) are untouched. Its write_all_entrances rewrites the
tables at the end (offsets for maps 0-415, the records after them), each map's records in vanilla's
order less the duplicates: a seed's entrance is vanilla's at the same (map, x, y).

On the PR a door is an object with a map_id (a GotoMap: map_id = PR map id, point_id = the object_id
of a PointIn on that map, where the party lands) in a map's entity_default.json; story layers
(ev_*.json, shown by the map's scripts) can carry doors too. The index pairs:
  * each SNES short entrance with the PR door object(s) the party walks into there: an object with a
    map_id within a tile of the SNES spot on a PR room of the SNES map (PR = SNES + (dx, dy)),
    preferring one whose own destination agrees with the SNES entrance's (its PR map is a room of the
    SNES destination map and its PointIn sits within 2 tiles of the landing spot). Every object at that
    spot (the default door and its story-layer copies) and an unclaimed neighbour with the same
    destination (the PR widened the door: "twin") are the entrance's doors. A door several SNES
    entrances agree on is shared (`shared_with`: the PR keeps one Narshe for the World of Balance and
    Ruin; SNES maps 20 and 32 both enter it).
  * each SNES destination (map, x, y) with PR arrivals: (map_id, point_id) of the PointIn vanilla's
    own matched doors use, else the PointIn within a tile of the spot on each PR room of the map that
    holds it, else a PointIn to add there (`new_point`).
The PR rooms of a SNES map are tools/snes_maps.py's pairs plus the ones its doors reach (`Rooms`:
the snes_maps build's exit-following, again over this index's doors, so pairs its table lacks or
overrides added since its build are followed too), each checked by the SNES tile properties under
the PR's walkable cells (snes_maps.walk_agreement >= 0.8) and by the room's doors sitting on the
map's exits. Several SNES maps of one layout (a town's World of Balance and Ruin versions, a scene's
copy) agree with the same PR doors: where the PR keeps separate versions, the one nearest the same
world map by vanilla's doors keeps the door (`world_labels`); where it keeps one map (Narshe), the
door is shared and a seed that sends the versions apart needs a per-world or per-story door.

data/bc_entrance_index.json is dev-PC data (it needs the US ROM): the seed step on a player's machine
reads it, BC's output tables (in memory) and the player's own PR map files; no ROM at seed time.

The seed step (apply(), run by tools/bc_seed.py after bc_events): each door of an entrance BC dealt a new
destination gets the destination's PR arrival in the seed's copy of its map file (files/<rel>; PointIns added
where the index says, object ids from 100); a door several SNES entrances share is left vanilla's unless every
version lands on one PR arrival, and seed/bc_doors.json lists each version's target for the plugin's redirect.
files() is every map file a seed may change (the BeyondChaos baseline's and the bundle's, bc_live.own_files).
"""
import argparse
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
import prdata as P  # noqa: E402

INDEX_FILE = os.path.join(ROOT, "data", "bc_entrance_index.json")

SHORT = 0x1FBB00          # DF/BB00: 2-byte offsets per map from the table's own start, 6-byte records
LOCATIONS = 415           # BC's locations (0-414): offsets 0-415
PARENT = 0x1FF            # dest map 0x1FF: back to the parent (world) map where the party entered
WORLD_MAPS = (0, 1)       # BC keeps the world maps' entrances (and every entrance into them) vanilla

SEED = "1234567890"
NEW_PLAYER = "New Player"


# --- SNES side ------------------------------------------------------------------------------------
def short_entrances(rom, maps=LOCATIONS):
    """Every map's short entrances as BC reads them (EntranceSet.read_data): {map: [entrance]} with
    the raw table index (BC's entid), x, y, the dest word, its map (bits 0-8), flags (word >> 9), dest
    x and y. A duplicate (same spot and destination as an earlier one: Location.uniqify_entrances) is
    marked `dup` (BC drops it from its output)."""
    ptr = [rom[SHORT + 2 * i] | rom[SHORT + 2 * i + 1] << 8 for i in range(maps + 1)]
    out = {}
    for m in range(maps):
        a, b = ptr[m], ptr[m + 1]
        ents, seen = [], set()
        for i, o in enumerate(range(a, b - 5, 6)):
            r = rom[SHORT + o:SHORT + o + 6]
            word = r[2] | r[3] << 8
            e = {"map": m, "index": i, "x": r[0], "y": r[1], "dest_word": word, "dest": word & PARENT,
                 "flags": word >> 9, "dest_x": r[4], "dest_y": r[5]}
            key = (e["x"], e["y"], e["dest"], e["dest_x"], e["dest_y"])
            if key in seen:
                e["dup"] = True
            seen.add(key)
            ents.append(e)
        out[m] = ents
    return out


def bc_kept(e):
    """Whether BC's create_dimensional_vortex leaves the entrance vanilla (its should_be_vanilla)."""
    loc, i, dest = e["map"], e["index"], e["dest"]
    return bool(
        (loc == 0x1E and i == 1)                       # leave Arvis's house
        or (loc == 0x14 and i in (10, 14))             # Arvis's house / the mines from Narshe
        or (loc == 0x32 and i == 3)                    # back out of the mines
        or loc == 0x2A                                 # the room with Terrato (Vicks and Wedge)
        or 0xD7 < loc < 0xDC                           # the Esper world
        or loc == 0x137 or dest == 0x137               # the collapsing house
        or (loc == 0x180 and i == 0)                   # the Sealed Gate cave's out-of-bounds entrance
        or (loc == 0x3B and dest == 0x3A) or (loc == 0x19A and dest == 0x19A)   # Figaro's throne room
        or loc in WORLD_MAPS or dest in WORLD_MAPS)    # the world maps (towns) both ways


def dest_key(m, x, y):
    return f"{m}:{x}:{y}"


# --- PR side --------------------------------------------------------------------------------------
class Pr:
    """The vanilla PR maps' doors and arrival points (entity_default.json and story layers ev_*.json):
    snes_maps.PrDoors (this tool's reader, lifted into the kit 2026-11-21): `doors`, `points`, `spots`, `into`,
    `ids`, `names`, `dirs`, `target(door)`, `graph()`; plus `entity_file(name)`. snes_maps is imported here, not
    at the top, so the player's generator loads it only on a strangejourney seed's index work."""

    def __init__(self):
        import snes_maps as SM
        self.SM = SM
        self._kit = SM.PrDoors()
        self.ids, self.names, self.dirs = self._kit.ids, self._kit.names, self._kit.dirs
        self.doors, self.points, self.spots, self.into = self._kit.doors, self._kit.points, self._kit.spots, self._kit.into

    def target(self, door):
        """(PR map name, PointIn or None) a door leads to."""
        return self._kit.target(door)

    def entity_file(self, name):
        d = self.dirs.get(name)
        return os.path.relpath(os.path.join(d, "entity_default.json"), P.VANILLA).replace("\\", "/") if d else None

    def graph(self):
        """{PR map: {PR maps its doors lead to or come from}} (vanilla's doors, both ways)."""
        return self._kit.graph()


def _objects(doc):
    out = []

    def walk(ls):
        for lay in ls:
            for o in lay.get("objects") or []:
                out.append((lay.get("name"), o))
            walk(lay.get("layers", []))
    walk(doc.get("layers", []))
    return out


def is_world(pr_name):
    return pr_name.startswith("Map_1")     # the PR's world maps (group 1xxxx: chunked, no tilemap.json)


# --- the PR rooms of each SNES map ---------------------------------------------------------------------
class Rooms:
    """{SNES map: {PR map: (dx, dy, how)}}: snes_maps' pairs (best first: its build now follows vanilla's doors too,
    "door" / "door-in", the pass this tool had, lifted into the kit 2026-11-21), then any room that pass still finds
    from them (snes_maps.grow_doors: a door of a known room on an SNES exit's tile leads into the PR map, or a door
    into a known room's landing spot comes from it; the room walks where the SNES walks, its doors on the exits)."""

    def __init__(self, rom, pr, exits):
        import snes_maps as SM
        self.SM, self.rom, self.pr, self.exits = SM, rom, pr, exits
        self.of = collections.defaultdict(dict)
        for m, ms in SM.table().items():
            for mt in ms:      # not a lookalike (a tiles/layout pair whose PR room is another place's: its doors aren't m's)
                if mt.pr in pr.dirs and not getattr(mt, "lookalike", False):
                    self.of[m].setdefault(mt.pr, (mt.dx, mt.dy, mt.how))
        self.found = []

    def grow(self, rounds=6):
        """Follow vanilla's doors both ways until no new room is found (snes_maps.grow_doors)."""
        pairs = {m: {name: (dx, dy) for name, (dx, dy, _) in prs.items()} for m, prs in self.of.items()}
        for f in self.SM.grow_doors(self.rom, pairs, doors=self.pr._kit, rounds=rounds):
            m = f["snes"]
            if m in WORLD_MAPS or m >= LOCATIONS or f["pr"] in self.of[m]:
                continue
            self.of[m][f["pr"]] = (f["dx"], f["dy"], f["how"])
            self.found.append(f)
        return self


def snes_graph(exits):
    """{SNES map: {maps its exits lead to or come from}} (both ways; parent exits left out)."""
    g = collections.defaultdict(set)
    for m, es in exits.items():
        for e in es:
            if e["dest"] < LOCATIONS and e["dest"] != m:
                g[m].add(e["dest"])
                g[e["dest"]].add(m)
    return g


# --- matching -------------------------------------------------------------------------------------
def dest_agrees(pr, rooms, door, dest, x, y):
    """(agrees, distance): whether a PR door's destination is the SNES destination (map dest at
    (x, y)): its PR map is a room of dest and its PointIn within 2 tiles of the landing spot. A
    SNES "back to the parent map" (0x1FF) agrees with a door onto a world map."""
    name, pt = pr.target(door)
    if dest == PARENT:
        return bool(name and is_world(name)), 0
    if not name:
        return False, None
    off = rooms.of.get(dest, {}).get(name)
    if off is None:
        return False, None
    if pt is None:
        return False, 99
    d = max(abs(pt["x"] - (x + off[0])), abs(pt["y"] - (y + off[1])))
    return d <= 2, d


def candidates(pr, rooms, e):
    """The PR door objects within a tile of SNES entrance e on its map's PR rooms, best first:
    [(sort key, door, how the room was found, distance, agrees)]."""
    out = []
    for rank, (name, (dx, dy, how)) in enumerate(rooms.of.get(e["map"], {}).items()):
        px, py = e["x"] + dx, e["y"] + dy
        for door in pr.doors.get(name, []):
            d = max(abs(door["x"] - px), abs(door["y"] - py))
            if d > 1:
                continue
            ok, adist = dest_agrees(pr, rooms, door, e["dest"], e["dest_x"], e["dest_y"])
            key = (not ok, d, how == "tiles", rank, adist if adist is not None else 99)
            out.append((key, door, how, d, ok))
    out.sort(key=lambda c: c[0])
    return out


def build_index(rom, say=print):
    import snes_maps as SM
    pr = Pr()
    ents = short_entrances(rom)
    allents = [e for m in sorted(ents) for e in ents[m]]
    exits = {m: SM.exits(rom, m) for m in range(LOCATIONS)}
    rooms = Rooms(rom, pr, exits).grow()
    say(f"PR rooms: {sum(len(v) for v in rooms.of.values())} pairs on {sum(1 for v in rooms.of.values() if v)} SNES maps "
        f"({sum(1 for v in rooms.of.values() for (_, _, how) in v.values() if how in ('door', 'door-in'))} found by doors, "
        f"{len(rooms.found)} of them beyond snes_maps' table)")

    # 1. each entrance's candidate spots: its agreeing doors (one spot per PR room), else its best one
    cands, claims = {}, collections.defaultdict(list)
    for e in allents:
        k = (e["map"], e["index"])
        cs = candidates(pr, rooms, e) if not e.get("dup") else []
        cands[k] = cs
        agreeing = [c for c in cs if c[4]]
        per_room = {}
        for c in (agreeing or cs[:1]):
            per_room.setdefault(c[1]["pr"], c)
        for c in per_room.values():
            claims[(c[1]["pr"], c[1]["x"], c[1]["y"])].append((c[0], k))
    # 2. a spot goes to every entrance that agrees with its door (shared), else to the best claimant;
    # SNES maps of one layout (a town's World of Balance and Ruin versions) agree with both PR versions'
    # doors: of several SNES maps, the ones of the PR map's world keep it
    sworld = SM.world_labels(snes_graph(exits), {0: 0, 1: 1})        # each side's nearest world map by doors (a hint)
    pworld = SM.world_labels(pr.graph(), {"Map_10010": 0, "Map_10020": 1})
    held = collections.defaultdict(list)
    holders = {}
    for spot, cl in claims.items():
        ok = [c for c in cl if not c[0][0]]
        if len({k[0] for _, k in ok}) > 1 and pworld.get(spot[0]):
            fit = [c for c in ok if not sworld.get(c[1][0]) or sworld[c[1][0]] & pworld[spot[0]]]
            ok = fit or ok
        keep = ok or [min(cl)]
        holders[spot] = [k for _, k in keep]
        for key, k in keep:
            held[k].append((key, spot))
    at = collections.defaultdict(list)
    for name, ds in pr.doors.items():
        for door in ds:
            at[(name, door["x"], door["y"])].append(door)
    entries, by = [], {}
    for e in allents:
        k = (e["map"], e["index"])
        rec = dict(e)
        rec["bc_shuffles"] = not bc_kept(e) and not e.get("dup")
        rec["doors"] = []
        shared = set()
        for key, spot in sorted(held.get(k, [])):
            first = at[spot][0]
            others = sorted([list(h) for h in holders[spot] if h != k])
            extra = {"shared_with": others} if others else {}
            for door in at[spot]:
                ok, _ = dest_agrees(pr, rooms, door, e["dest"], e["dest_x"], e["dest_y"])
                rec["doors"].append(dict(door, how="spot" if key[1] == 0 else "near", dest_agrees=ok, **extra))
            # twins: an unclaimed neighbour with the same destination (the PR widened the door)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nb = (spot[0], spot[1] + dx, spot[2] + dy)
                    if (dx or dy) and nb in at and nb not in claims:
                        for door in at[nb]:
                            if (door["map_id"], door["point_id"]) == (first["map_id"], first["point_id"]):
                                rec["doors"].append(dict(door, how="twin", dest_agrees=not key[0], **extra))
            shared |= {h for h in holders[spot] if h != k}
        if shared:
            rec["shared_with"] = sorted([list(h) for h in shared])
        if e.get("dup"):
            rec["reason"] = "duplicate of an earlier entrance (BC drops it)"
        elif not rec["doors"]:
            rec["reason"] = door_reason(pr, rooms, e, cands[k], claims, holders)
        else:
            rec["reason"] = None
        by[k] = rec
        entries.append(rec)

    # 3. destinations: every (map, x, y) a short entrance lands on
    seen = collections.defaultdict(collections.Counter)
    for rec in entries:
        if rec["dest"] == PARENT:
            continue
        for d in rec["doors"]:
            if d["dest_agrees"] and d["how"] != "twin":
                seen[dest_key(rec["dest"], rec["dest_x"], rec["dest_y"])][(d["map_id"], d["point_id"])] += 1
    dests = {}
    for e in allents:
        dk = dest_key(e["dest"], e["dest_x"], e["dest_y"])
        if dk not in dests:
            dests[dk] = dict({"map": e["dest"], "x": e["dest_x"], "y": e["dest_y"]},
                             **arrival(pr, rooms, e["dest"], e["dest_x"], e["dest_y"], seen.get(dk)))

    doc = {"_about": "Beyond Chaos strangejourney: SNES short entrances (US v1.0, maps 0-414, as BC reads them) -> PR doors, "
                     "and SNES destinations -> PR arrivals (tools/bc_entrances.py index). entrances[]: map, index (BC's "
                     "entid: the raw table index), x, y, dest_word, dest (map), flags, dest_x, dest_y, bc_shuffles (BC's "
                     "vortex may deal it a new destination), doors (PR objects with a map_id: file under the game's "
                     "assets, Tiled object id, layer, PR tile, current map_id/point_id; how: spot / near (a tile off) / "
                     "twin (an unclaimed neighbour with the same destination); dest_agrees: the object's own destination "
                     "is the SNES one; shared_with: other SNES entrances holding the same PR door), shared_with (all "
                     "of them), reason when none. "
                     "destinations{'map:x:y'}: arrivals [{pr, map_id, point_id (an existing PointIn) or null + new_point "
                     "(a PointIn to add at pr_x, pr_y in file), how: door (vanilla's matched doors land there) / point "
                     "(a PointIn within a tile of the spot on a PR room of the map) / new_point}], first = vanilla's "
                     "choice; reason when none. rooms_found: PR rooms of SNES maps this index found by following doors "
                     "(beyond data/snes_pr_maps.json).",
           "entrances": entries, "destinations": dests, "rooms_found": rooms.found,
           "pr_graph": {"_about": "vanilla's PR door graph (each PR map: the PR maps its doors lead to or come "
                                  "from, both ways): pick_arrival's distances at seed time without reading every map",
                        **{n: sorted(v) for n, v in sorted(pr.graph().items())}},
           "worlds": {"_about": "the world map(s) nearest each map by vanilla's doors (0: World of Balance, 1: World of "
                                "Ruin; SNES exits / PR doors, both ways; event warps aren't followed): which version of "
                                "a door several SNES maps share is which",
                      "snes": {str(m): sorted(v) for m, v in sorted(sworld.items()) if m not in WORLD_MAPS},
                      "pr": {n: sorted(v) for n, v in sorted(pworld.items()) if not is_world(n)}}}
    doc["coverage"] = coverage(doc)
    return doc


def door_reason(pr, rooms, e, cs, claims, holders):
    if e["map"] in WORLD_MAPS:
        return "world map (BC keeps its entrances)"
    if not rooms.of.get(e["map"]):
        return "SNES map has no PR room (snes_maps: unused slot, scene map, or no confirmed pair)"
    if cs:
        return "the PR door there belongs to another SNES entrance (its destination agrees)"
    near = []
    for name, (dx, dy, _) in rooms.of[e["map"]].items():
        px, py = e["x"] + dx, e["y"] + dy
        near += [d for d in pr.doors.get(name, []) if max(abs(d["x"] - px), abs(d["y"] - py)) <= 3]
    if near:
        return "no PR door within a tile (one 2-3 tiles off)"
    import snes_maps as SM
    inside = any((e["x"] + dx + a, e["y"] + dy + b) in SM.pr_walkable(name)
                 for name, (dx, dy, _) in rooms.of[e["map"]].items() for a in (-1, 0, 1) for b in (-1, 0, 1))
    if not inside:
        return "spot is in no known PR room of the map"
    return "no PR door at the spot (the PR does it by event, or dropped the door)"


def arrival(pr, rooms, m, x, y, seen):
    """A SNES destination's PR arrivals (see the module doc): {"arrivals": [...]} best first, or a reason."""
    import snes_maps as SM
    if m == PARENT:
        return {"arrivals": [], "reason": "parent map (0x1FF): back to the world map where the party entered; "
                                          "BC never deals it as a new destination"}
    out, have = [], set()
    for (mid, pid), n in (seen.most_common() if seen else []):
        name, pt = pr.target({"map_id": mid, "point_id": pid})
        out.append({"how": "door", "pr": name, "map_id": mid, "point_id": pid, "pr_x": pt["x"] if pt else None,
                    "pr_y": pt["y"] if pt else None, "doors": n})
        have.add(name)
    if not rooms.of.get(m):
        return {"arrivals": out, "reason": None if out else "SNES map has no PR room"}
    news = []
    for name, (dx, dy, _) in rooms.of[m].items():
        if name in have or name not in pr.ids:
            continue
        px, py = x + dx, y + dy
        pts = sorted(pr.points.get(name, {}).items(), key=lambda kv: (max(abs(kv[1]["x"] - px), abs(kv[1]["y"] - py)), kv[0]))
        if pts and max(abs(pts[0][1]["x"] - px), abs(pts[0][1]["y"] - py)) <= 1:
            oid, pt = pts[0]
            out.append({"how": "point", "pr": name, "map_id": pr.ids[name], "point_id": oid, "pr_x": pt["x"], "pr_y": pt["y"]})
            continue
        if is_world(name):
            continue     # a world map: its arrivals are its own PointIns (no tilemap to place one by)
        # a PointIn to add: on the spot, else on the walkable cell beside it (the PR's door tiles are often walls)
        wk = SM.pr_walkable(name)
        spot = next(((px + a, py + b) for a, b in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1))
                     if (px + a, py + b) in wk), None)
        if spot:
            news.append({"how": "new_point", "pr": name, "map_id": pr.ids[name], "point_id": None, "pr_x": spot[0],
                         "pr_y": spot[1], "file": pr.entity_file(name)})
    out += news
    if not out and m in WORLD_MAPS:
        return {"arrivals": [], "reason": "world map: no vanilla door matched lands there (BC never deals one as a new destination)"}
    return {"arrivals": out, "reason": None if out else "landing spot is in no known PR room of the map"}


def coverage(doc):
    ents = [e for e in doc["entrances"] if not e.get("dup")]
    pool = [e for e in ents if e["bc_shuffles"]]
    dests = doc["destinations"]
    pool_dests = {dest_key(e["dest"], e["dest_x"], e["dest_y"]) for e in pool}

    def reasons(es):
        return dict(collections.Counter(e["reason"] for e in es if e["reason"]).most_common())

    def first_how(d):
        return d["arrivals"][0]["how"] if d["arrivals"] else "none"
    return {
        "entrances": len(ents), "doors_matched": sum(1 for e in ents if e["doors"]),
        "doors_agreeing": sum(1 for e in ents if any(d["dest_agrees"] for d in e["doors"])),
        "doors_shared": sum(1 for e in ents if e.get("shared_with")),
        "pool": len(pool), "pool_matched": sum(1 for e in pool if e["doors"]),
        "pool_agreeing": sum(1 for e in pool if any(d["dest_agrees"] for d in e["doors"])),
        "pool_shared": sum(1 for e in pool if e.get("shared_with")),
        "destinations": len(dests), "destinations_matched": sum(1 for d in dests.values() if d["arrivals"]),
        "destinations_by_how": dict(collections.Counter(first_how(d) for d in dests.values())),
        "pool_destinations": len(pool_dests), "pool_destinations_matched": sum(1 for k in pool_dests if dests[k]["arrivals"]),
        "rooms_found": len(doc.get("rooms_found", [])),
        "door_reasons": reasons(ents), "pool_door_reasons": reasons(pool),
        "destination_reasons": dict(collections.Counter(d["reason"] for d in dests.values() if d.get("reason")).most_common()),
    }


def write_index(doc, path=INDEX_FILE):
    """The index as JSON with one entrance / destination / room per line (diffs stay readable)."""
    def one(v):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    parts = []
    for k, v in doc.items():
        if isinstance(v, list):
            body = "[\n" + ",\n".join("  " + one(x) for x in v) + "\n ]"
        elif isinstance(v, dict) and k in ("destinations", "worlds", "pr_graph"):
            body = "{\n" + ",\n".join(f"  {one(kk)}:{one(vv)}" for kk, vv in v.items()) + "\n }"
        else:
            body = one(v)
        parts.append(f" {one(k)}:{body}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("{\n" + ",\n".join(parts) + "\n}\n")


def load_index(path=INDEX_FILE):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --- a seed -------------------------------------------------------------------------------------------
def changes(vanilla, seed_rom):
    """The short entrances BC's output moved: [(vanilla entrance, seed entrance or None, kind)], kind
    "dest" (a new map/x/y), "flags" (only the dest word's flag bits), "removed" (not in the output),
    "added" (only in the output). Entrances are keyed by (map, x, y): BC keeps each map's order but
    drops duplicates."""
    v, s = short_entrances(vanilla), short_entrances(seed_rom)
    out = []
    for m in range(LOCATIONS):
        sv = {(e["x"], e["y"]): e for e in v[m] if not e.get("dup")}
        ss = {(e["x"], e["y"]): e for e in s[m]}
        for xy, e in sv.items():
            f = ss.get(xy)
            if f is None:
                out.append((e, None, "removed"))
            elif (f["dest"], f["dest_x"], f["dest_y"]) != (e["dest"], e["dest_x"], e["dest_y"]):
                out.append((e, f, "dest"))
            elif f["dest_word"] != e["dest_word"]:
                out.append((e, f, "flags"))
        for xy, f in ss.items():
            if xy not in sv:
                out.append((None, f, "added"))
    return out


def pick_arrival(arrivals, door_pr, graph):
    """The arrival for a door in PR map door_pr: the one nearest it in vanilla's door graph (a World
    of Ruin room's door lands in the World of Ruin version of a place), vanilla's choice on a tie."""
    if len(arrivals) < 2:
        return arrivals[0] if arrivals else None
    dist, frontier = {door_pr: 0}, [door_pr]
    while frontier:
        nxt = []
        for n in frontier:
            for t in graph.get(n, ()):
                if t not in dist:
                    dist[t] = dist[n] + 1
                    nxt.append(t)
        frontier = nxt
    return min(enumerate(arrivals), key=lambda ia: (dist.get(ia[1]["pr"], 999), ia[0]))[1]


def rewire_plan(index, chg, graph=None):
    """The seed's rewiring: for each entrance BC dealt a new destination, its PR doors' new (map_id,
    point_id). [{"entrance", "seed", "ok", "reason", "doors": [(door, arrival)], "held": [door]}]; ok
    when the index has the door and an arrival of the new destination and no other SNES entrance on
    a shared door went elsewhere ("held": the shared doors that did: a per-world door when the other
    entrance is the other world's version of the map, else another story version's)."""
    by = {(e["map"], e["index"]): e for e in index["entrances"]}
    dests = index["destinations"]
    sworld = {int(m): set(v) for m, v in index.get("worlds", {}).get("snes", {}).items()}
    new = {(e["map"], e["index"]): (f["dest"], f["dest_x"], f["dest_y"]) for e, f, k in chg if k == "dest"}
    out = []
    for e, f, kind in chg:
        if kind != "dest":
            continue
        rec = by[(e["map"], e["index"])]
        mine = (f["dest"], f["dest_x"], f["dest_y"])
        arr = dests.get(dest_key(*mine))
        reasons = []
        if not rec["doors"]:
            reasons.append("door: " + (rec["reason"] or "?"))
        if not (arr and arr["arrivals"]):
            reasons.append("destination: " + ((arr or {}).get("reason") or "not in the index"))
        doors, held, splits = [], [], set()
        for d in rec["doors"]:
            clash = []
            for h in d.get("shared_with", []):
                other = by[tuple(h)]
                if new.get(tuple(h), (other["dest"], other["dest_x"], other["dest_y"])) != mine:
                    clash.append(h[0])
            if clash:
                held.append(d)
                w = sworld.get(rec["map"], set())
                splits.add("world" if w and all(sworld.get(m) and not (sworld[m] & w) for m in clash) else "story")
            elif not reasons:
                doors.append((d, pick_arrival(arr["arrivals"], d["pr"], graph or {})))
        if held and not doors:
            reasons.append("shared PR door: " + ("the other world's version of the map goes elsewhere (a per-world door)"
                                                 if splits == {"world"} else
                                                 "another story version of the map goes elsewhere"))
        out.append({"entrance": rec, "seed": f, "ok": not reasons, "reason": "; ".join(reasons) or None,
                    "doors": doors if not reasons else [], "held": held, "partial": bool(held and doors and not reasons)})
    return out


def make_seed(seed=SEED, flags=None, rom=None, romfree=False):
    """(vanilla bytes, BC's output bytes, flags) for a strangejourney seed (tools/bc_run.py in this
    process; BC keeps state in its modules: one seed per process). romfree: BC's input is the
    generator's data/bc_base.bin (tools/bc_basedata.py), as a player's machine runs it."""
    import ff6snes as S
    import bc_run
    sys.dont_write_bytecode = True      # BC's source folder stays as it is
    if flags is None:
        import bc_seed
        flags = bc_seed.PRESETS[NEW_PLAYER] + " strangejourney"
    flags = " ".join(f for f in flags.split() if f not in ("j", "thescenarionottaken"))
    if romfree:
        import bc_basedata
        rom = bc_basedata.load()
    rom = rom if rom is not None else S.rom_bytes(P.VANILLA_ROM)
    if "randomizer" in sys.modules:
        # BC ran in this process already (a test suite: test_bc's parity check); its modules keep state, and a
        # second run fails inside BC (screw_tutorial_bosses: "is not in list"), so this one runs in a child process
        return rom, _seed_in_child(seed, flags, rom, romfree), flags
    data, _ = bc_run.run(rom, seed, "normal", flags, say=lambda line: None, romfree=romfree)
    return rom, data, flags


def _seed_in_child(seed, flags, rom, romfree):
    """BC's output bytes for (seed, flags) on `rom`, made by make_seed in a fresh Python process."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory(prefix="bc_entrances_") as d:
        rin, rout = os.path.join(d, "in.bin"), os.path.join(d, "out.bin")
        with open(rin, "wb") as f:
            f.write(bytes(rom))
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import bc_entrances as B\n"
                "rom = open(sys.argv[2], 'rb').read()\n"
                "_, data, _ = B.make_seed(sys.argv[3], sys.argv[4], rom, sys.argv[5] == '1')\n"
                "open(sys.argv[6], 'wb').write(bytes(data))\n")
        subprocess.run([sys.executable, "-c", code, HERE, rin, seed, flags, "1" if romfree else "0", rout],
                       check=True, capture_output=True, cwd=ROOT)
        with open(rout, "rb") as f:
            return f.read()


def diff_report(index, vanilla, seed_rom, graph=None):
    chg = changes(vanilla, seed_rom)
    kinds = collections.Counter(k for _, _, k in chg)
    plan = rewire_plan(index, chg, graph)
    ok = [p for p in plan if p["ok"]]
    # a PR object two rewired entrances would set differently (twins of two doors)
    sets = collections.defaultdict(set)
    for p in ok:
        for d, a in p["doors"]:
            sets[(d["file"], d["id"])].add((a["map_id"], a["point_id"], a["pr_x"], a["pr_y"]))
    shared_only = [p for p in plan if not p["ok"] and p["reason"].startswith("shared PR door")]
    return {"changed": dict(kinds), "dest_changed": len(plan), "rewirable": len(ok),
            "rewirable_partial": sum(1 for p in ok if p["partial"]),
            "rewirable_door_agrees": sum(1 for p in ok if any(d["dest_agrees"] for d in p["entrance"]["doors"])),
            "rewirable_arrival_how": dict(collections.Counter(a["how"] for p in ok for _, a in p["doors"][:1])),
            "new_points": len({(a["pr"], a["pr_x"], a["pr_y"]) for p in ok for _, a in p["doors"] if a["how"] == "new_point"}),
            "pr_objects_rewired": len(sets), "pr_object_conflicts": sum(1 for v in sets.values() if len(v) > 1),
            "shared_only": len(shared_only),
            "shared_only_world": sum(1 for p in shared_only if "other world" in p["reason"]),
            "not_rewirable": dict(collections.Counter(p["reason"] for p in plan if not p["ok"]).most_common()),
            "flags_only": sum(1 for e, f, k in chg if k == "flags"), "added": [f for _, f, k in chg if k == "added"],
            "plan": plan}


# --- the seed step (tools/bc_seed.py) ---------------------------------------------------------------------------
# A strangejourney seed's doors: every PR door object of an entrance BC dealt a new destination gets the new
# destination's arrival (map_id, point_id) in the seed's copy of its map file (files/<rel>, as tools/bc_events.py
# writes map files: the seed library swaps them in live, the BeyondChaos baseline holds vanilla's for a seed
# without them); a destination with no PointIn on the spot gets one (object ids from 100). A door several SNES
# entrances share (one PR Narshe for the World of Balance and Ruin, one map for a place's story versions) is set
# only when every version goes to the same PR arrival; otherwise it stays vanilla's and bc_doors.json lists each
# version's target for the plugin to redirect (EventGotoMap). Inputs at seed time: BC's output and vanilla's
# bytes (the ROM, or ROM-free data/bc_base.bin: the short-entrance tables are in both), this index, the PR's
# map files (the player's own copies in the bundle: files() below); no ROM is read here.
FLAG = "strangejourney"
CAVE_MODES = ("ancientcave", "speedcave", "racecave")   # strangejourney is prohibited there (no vortex)
DOORS_JSON = "bc_doors.json"       # in the seed folder
NEW_POINT_FIRST = 100              # our PointIns' object ids (vanilla's end at 41; ted_maps.vanilla_point's rule)
POINT_GID = 997                    # the PR's PointIn tile (ted_maps.POINT_GID)
DIRECTION = {0: 1, 1: 2, 2: 4, 3: 8}   # SNES facing (dest word bits 12-13: up, right, down, left) -> PointIn direction
WOR_FLAG = ("kScenarioFlag2", 41)  # the World of Ruin (WcEvents.CollapseFlag): the per-world redirect's switch


def files(index=None):
    """Every Magicite file a strangejourney seed may change (for bc_live.own_files: the baseline holds them as
    vanilla's, the bundle carries the game's copies): the PR door objects' files of the entrances BC's vortex may
    deal a new destination, and the files a new PointIn goes into for a destination it may deal. Chest maps the
    porter writes are in the baseline already (seed_live.managed_files) and left out."""
    ix = index or load_index()
    out = set()
    pool = set()
    for e in ix["entrances"]:
        if e["bc_shuffles"]:
            out |= {d["file"] for d in e["doors"]}
            pool.add(dest_key(e["dest"], e["dest_x"], e["dest_y"]))
    for k in pool:
        out |= {a["file"] for a in ix["destinations"][k]["arrivals"] if a["how"] == "new_point"}
    import seed_live
    return sorted(out - set(seed_live.managed_files()))


def graph_of(index):
    """The PR door graph pick_arrival measures by: the index's copy, else read from the maps."""
    g = index.get("pr_graph")
    if g:
        return {k: set(v) for k, v in g.items() if not k.startswith("_")}
    return Pr().graph()


def _props(o):
    return {p["name"]: p["value"] for p in o.get("properties", [])}


def _set_prop(o, name, value, kind="int"):
    for p in o.setdefault("properties", []):
        if p["name"] == name:
            p["value"] = value
            return
    o["properties"].append({"name": name, "type": kind, "value": value})


def _groups(doc):
    """Every object group of an entity file: [layer dict]."""
    out = []

    def walk(ls):
        for lay in ls:
            if "objects" in lay:
                out.append(lay)
            walk(lay.get("layers", []))
    walk(doc.get("layers", []))
    return out


class SeedDoors:
    """One seed's door edits on the packed seed folder `out`: each map file is the seed's copy (another step's:
    a chest map, bc_events' Phantom Forest) or vanilla's; written back at the end (finish)."""

    def __init__(self, out):
        self.out = out
        self.docs, self.changed = {}, set()
        self.points, self.new_points = {}, []
        self.set = {}                  # (file, object id) -> (map_id, point_id): every object set, once

    def doc(self, rel):
        if rel not in self.docs:
            mine = os.path.join(self.out, "files", *rel.split("/"))
            src = mine if os.path.exists(mine) else os.path.join(P.VANILLA, *rel.split("/"))
            with open(src, encoding="utf-8") as f:
                self.docs[rel] = json.load(f)
        return self.docs[rel]

    def find(self, d):
        """The door object `d` (an index door) in its file, or (None, why) when the file no longer has it as
        vanilla's (another step changed or replaced it)."""
        for lay in _groups(self.doc(d["file"])):
            for o in lay["objects"]:
                if o.get("id") == d["id"]:
                    p = _props(o)
                    if (p.get("map_id"), p.get("point_id", 0)) != (d["map_id"], d["point_id"]):
                        return None, (f"the seed's copy of the door goes elsewhere already (map {p.get('map_id')} "
                                      f"point {p.get('point_id', 0)}: another step's)")
                    return o, None
        return None, "the door object isn't in the seed's copy of its file"

    def point(self, a, facing):
        """(map_id, point_id) of arrival `a`: its PointIn, or one added on its spot (once per spot)."""
        if a["point_id"] is not None:
            return a["map_id"], a["point_id"]
        key = (a["file"], a["pr_x"], a["pr_y"])
        if key not in self.points:
            doc = self.doc(a["file"])
            groups = _groups(doc)
            objs = [(lay, o) for lay in groups for o in lay["objects"]]
            ins = [(lay, o) for lay, o in objs if o.get("name") == "PointIn"]
            here = [o for _, o in ins if (int(o["x"] // 16), int(o["y"] // 16) - (1 if "gid" in o else 0)) == key[1:]
                    and isinstance(_props(o).get("object_id"), int)]
            if here:                   # a PointIn another step put there
                self.points[key] = _props(here[0])["object_id"]
            else:
                taken = {_props(o).get("object_id") for _, o in ins}
                pid = NEW_POINT_FIRST
                while pid in taken:
                    pid += 1
                layer = ins[0][0] if ins else next((lay for lay in groups if lay.get("type") == "objectgroup"), groups[0])
                ents = [_props(o).get("entity_id") for _, o in objs]
                new = {"gid": POINT_GID, "height": 16, "id": max([o["id"] for _, o in objs] or [0]) + 1, "name": "PointIn",
                       "properties": [{"name": "direction", "type": "int", "value": DIRECTION.get(facing, 4)},
                                      {"name": "entity_id", "type": "int",
                                       "value": max([v for v in ents if isinstance(v, int)] or [0]) + 1},
                                      {"name": "link_object_id", "type": "int", "value": 0},
                                      {"name": "object_id", "type": "int", "value": pid},
                                      {"name": "object_type", "type": "int", "value": 0},
                                      {"name": "title_id", "type": "string", "value": ""},
                                      {"name": "title_type", "type": "int", "value": 0}],
                       "rotation": 0, "type": "", "visible": True, "width": 16,
                       "x": a["pr_x"] * 16, "y": (a["pr_y"] + 1) * 16}     # a tile object's y is its bottom edge
                layer["objects"].append(new)
                self.changed.add(a["file"])
                self.points[key] = pid
                self.new_points.append({"file": a["file"], "pr": a["pr"], "map_id": a["map_id"], "point_id": pid,
                                        "object": new["id"], "x": a["pr_x"], "y": a["pr_y"],
                                        "direction": DIRECTION.get(facing, 4)})
        return a["map_id"], self.points[key]

    def set_door(self, d, target):
        """Set door `d` to target (map_id, point_id); never an object twice (the first setting stands)."""
        k = (d["file"], d["id"])
        if k in self.set:
            return None if self.set[k] == tuple(target) else f"set already, to map {self.set[k][0]} point {self.set[k][1]}"
        o, why = self.find(d)
        if o is None:
            return why
        _set_prop(o, "map_id", target[0])
        _set_prop(o, "point_id", target[1])
        self.set[k] = tuple(target)
        self.changed.add(d["file"])
        return None

    def finish(self):
        written = []
        for rel in sorted(self.changed):
            dest = os.path.join(self.out, "files", *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(json.dumps(self.docs[rel], ensure_ascii=False, separators=(",", ":")))
            written.append(rel)
        return written


def _ref(d):
    """A door's identity in bc_doors.json: its file, Tiled object id (the game's PropertyEntity.TmeId), layer,
    PR map and tile, entity id, vanilla destination."""
    return {"file": d["file"], "id": d["id"], "layer": d.get("layer"), "pr": d["pr"], "x": d["x"], "y": d["y"],
            "vanilla": [d["map_id"], d["point_id"]]}


def apply(out, flags, rom, vanilla, mode="normal", log=print, index=None):
    """bc_seed's step for `strangejourney`: BC's short-entrance tables in its output `rom` against `vanilla`'s
    (bytes, or a path ff6snes.rom_bytes reads: ROM-free, data/bc_base.bin's), the PR doors rewired in the seed
    folder `out` (files/<rel>) and out/bc_doors.json. Returns (files written (rels), summary for bc_seed.json),
    or ([], None) when the seed has no vortex."""
    if FLAG not in flags.split() or mode in CAVE_MODES:
        return [], None
    import ff6snes as S
    if isinstance(vanilla, str):
        vanilla = S.rom_bytes(vanilla)
    if isinstance(rom, str):
        rom = S.rom_bytes(rom)
    ix = index or load_index()
    graph = graph_of(ix)
    chg = changes(vanilla, rom)
    plan = rewire_plan(ix, chg, graph)
    by = {(e["map"], e["index"]): e for e in ix["entrances"]}
    dests = ix["destinations"]
    sworld = {int(m): sorted(v) for m, v in ix.get("worlds", {}).get("snes", {}).items()}
    new = {(e["map"], e["index"]): (f["dest"], f["dest_x"], f["dest_y"]) for e, f, k in chg if k == "dest"}
    users = collections.defaultdict(list)         # door object -> the SNES entrances it serves
    for e in ix["entrances"]:
        for d in e["doors"]:
            if (e["map"], e["index"]) not in users[(d["file"], d["id"])]:
                users[(d["file"], d["id"])].append((e["map"], e["index"]))
    facing = {}                                   # a destination's facing: vanilla's entrances landing there
    for e in ix["entrances"]:
        facing.setdefault(dest_key(e["dest"], e["dest_x"], e["dest_y"]), (e["flags"] >> 3) & 3)
    pr_ids = {r["map_name"]: int(r["id"]) for r in P.Table("map")}
    sd = SeedDoors(out)

    def dest_of(k):
        e = by[k]
        return new.get(k, (e["dest"], e["dest_x"], e["dest_y"]))

    def target(k, door):
        """(target (map_id, point_id) or None, how, reason) of SNES entrance k through PR door `door`."""
        if k not in new:
            return [door["map_id"], door["point_id"]], "vanilla", None
        dk = dest_key(*new[k])
        arr = dests.get(dk)
        if not (arr and arr["arrivals"]):
            return None, None, "destination: " + ((arr or {}).get("reason") or "not in the index")
        a = pick_arrival(arr["arrivals"], door["pr"], graph)
        return list(sd.point(a, facing.get(dk, 2))), a["how"], None

    # 1. the entrances the plan rewires: their doors (an object once: a second setting is a conflict)
    status = {}                                   # door object -> ("set", target) / ("conflict", reason) / ("shared", None)
    wanted = {}                                   # (entrance, door object) -> the target it was set for
    conflicts = []
    held = {}
    for p in plan:
        f = p["seed"]
        k = (p["entrance"]["map"], p["entrance"]["index"])
        for d in p["held"]:
            held.setdefault((d["file"], d["id"]), d)
        for d, a in p["doors"]:
            tgt = list(sd.point(a, facing.get(dest_key(f["dest"], f["dest_x"], f["dest_y"]), 2)))
            why = sd.set_door(d, tgt)
            if why:
                conflicts.append(dict(_ref(d), entrance=list(k), target=tgt, reason=why))
                status.setdefault((d["file"], d["id"]), ("conflict", why))
            else:
                status[(d["file"], d["id"])] = ("set", tgt)
                wanted[(k, d["file"], d["id"])] = tgt
    # 2. doors several SNES entrances share that BC sent apart: set when every version lands on one PR arrival,
    # else left vanilla's with each version's target for the plugin's redirect
    shared = []
    for (rel, oid), d in sorted(held.items()):
        versions = []
        for k in users[(rel, oid)]:
            if by[k].get("dup"):
                continue
            tgt, how, why = target(k, d)
            versions.append({"entrance": list(k), "world": sworld.get(k[0], []), "dest": list(dest_of(k)),
                             "changed": k in new, "target": tgt, "how": how, "reason": why})
        tgts = {tuple(v["target"]) if v["target"] else None for v in versions}
        if len(tgts) == 1 and None not in tgts:
            tgt = list(tgts.pop())
            why = None if tgt == [d["map_id"], d["point_id"]] else sd.set_door(d, tgt)
            if why is None:
                status[(rel, oid)] = ("set", tgt)
                for v in versions:
                    wanted[(tuple(v["entrance"]), rel, oid)] = tgt
            else:
                conflicts.append(dict(_ref(d), entrance=[v["entrance"] for v in versions], target=tgt, reason=why))
                status.setdefault((rel, oid), ("conflict", why))
            continue
        status[(rel, oid)] = ("shared", None)
        by_world = collections.defaultdict(set)
        for v in versions:
            by_world[tuple(v["world"])].add(tuple(v["target"]) if v["target"] else None)
        split = ("world" if set(by_world) == {(0,), (1,)} and all(len(t) == 1 for t in by_world.values()) else "story")
        o, _ = sd.find(d)
        rec = dict(_ref(d), pr_map_id=pr_ids.get(d["pr"]), entity_id=_props(o).get("entity_id") if o else None,
                   split=split, versions=versions)
        if split == "world":
            off, on = next(iter(by_world[(0,)])), next(iter(by_world[(1,)]))
            rec["redirect"] = {"flag": list(WOR_FLAG), "off": list(off) if off else None, "on": list(on) if on else None}
        shared.append(rec)
    # the redirect's key (the door's PR map, its vanilla destination): unique when every door object there that
    # still goes to that destination in the seed's copies (its map's entity_default.json and the door's own
    # file) is a shared door of the same SNES entrances (the twins of one door)
    serves = {(s["file"], s["id"]): sorted(tuple(v["entrance"]) for v in s["versions"]) for s in shared}
    for s in shared:
        rels = {s["file"], s["file"].rsplit("/", 1)[0] + "/entity_default.json"}
        there = {(rel, o["id"]) for rel in rels for lay in _groups(sd.doc(rel)) for o in lay["objects"]
                 if (_props(o).get("map_id"), _props(o).get("point_id", 0)) == tuple(s["vanilla"])}
        s["key_unique"] = all(serves.get(x) == serves[(s["file"], s["id"])] for x in there)
    # 3. per entrance: rewired (some or all of its doors set to its destination), or why not
    rewired, not_rewired = [], []
    for p in plan:
        e, f = p["entrance"], p["seed"]
        k = (e["map"], e["index"])
        rec = {"entrance": list(k), "snes": [e["x"], e["y"]],
               "vanilla_dest": [e["dest"], e["dest_x"], e["dest_y"]], "dest": [f["dest"], f["dest_x"], f["dest_y"]]}
        done, left = [], []
        for d in e["doors"]:
            st = status.get((d["file"], d["id"]), ("untouched", None))
            if st[0] == "set" and wanted.get((k, d["file"], d["id"])) == st[1]:
                done.append(dict(_ref(d), to=st[1]))
            else:
                left.append(dict(_ref(d), status=st[0] if st[0] != "set" else "set for another entrance"))
        if done:
            rewired.append(dict(rec, doors=done, partial=bool(left), **({"left": left} if left else {})))
        else:
            reason = p["reason"] or "every PR door of it was set otherwise (conflicts)"
            not_rewired.append(dict(rec, reason=reason, doors=[_ref(d) for d in e["doors"]]))
    written = sd.finish()
    kinds = collections.Counter(k for _, _, k in chg)
    summary = {"changed": dict(kinds), "dest_changed": len(plan), "rewired": len(rewired),
               "rewired_partial": sum(1 for r in rewired if r["partial"]), "objects_set": len(sd.set),
               "new_points": len(sd.new_points), "files": len(written), "not_rewired": len(not_rewired),
               "shared_doors": len(shared), "shared_world": sum(1 for s in shared if s["split"] == "world"),
               "conflicts": len(conflicts)}
    doc = {"_about": "Beyond Chaos strangejourney on the PR (tools/bc_entrances.py apply). rewired: each entrance BC "
                     "dealt a new destination whose PR door objects (file, Tiled id) are set to: [map_id, point_id] "
                     "(partial: some of its doors are left: shared or conflicting); new_points: PointIns added; "
                     "not_rewired: the reason; shared: doors several SNES entrances share that the seed sends apart, "
                     "left vanilla's, with each version's target for the plugin's redirect (split world: by the "
                     "World of Ruin flag, `redirect`; story: by the story version of the place); conflicts: an object "
                     "wanted two ways (the first setting stands)",
           "flags": flags, "summary": summary, "rewired": rewired, "new_points": sd.new_points,
           "not_rewired": not_rewired, "shared": shared, "conflicts": conflicts, "files": written,
           "added": [[f["map"], f["x"], f["y"]] for _, f, k in chg if k == "added"]}
    with open(os.path.join(out, DOORS_JSON), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
    log(f"strangejourney: {len(rewired)}/{len(plan)} new destinations rewired ({summary['objects_set']} PR doors, "
        f"{len(sd.new_points)} new PointIns, {len(written)} files); {len(shared)} shared doors for the plugin "
        f"({summary['shared_world']} per world); {len(not_rewired)} not rewired; {len(conflicts)} conflicts")
    return written, summary


# --- CLI ----------------------------------------------------------------------------------------------
def _rom():
    import ff6snes as S
    if not os.path.exists(P.VANILLA_ROM):
        raise SystemExit(f"no US ROM at {P.VANILLA_ROM}")
    return S.rom_bytes(P.VANILLA_ROM)


def print_coverage(c):
    print(f"doors: {c['doors_matched']}/{c['entrances']} short entrances matched "
          f"({c['doors_agreeing']} with the PR door's own destination agreeing, {c['doors_shared']} on shared doors)")
    print(f"  BC's shuffle pool: {c['pool_matched']}/{c['pool']} matched ({c['pool_agreeing']} agreeing, "
          f"{c['pool_shared']} shared)")
    print(f"destinations: {c['destinations_matched']}/{c['destinations']} matched (first arrival: {c['destinations_by_how']}); "
          f"the pool's {c['pool_destinations_matched']}/{c['pool_destinations']}")
    print(f"PR rooms found by following doors: {c['rooms_found']}")
    print("unmatched doors (all / pool):")
    for r, n in c["door_reasons"].items():
        print(f"  {n:4d} / {c['pool_door_reasons'].get(r, 0):4d}  {r}")
    print("unmatched destinations:")
    for r, n in c["destination_reasons"].items():
        print(f"  {n:4d}  {r}")


def print_diff(r):
    print(f"short entrances changed: {r['changed']} (flags: only the dest word's flag bits, which BC clears)")
    print(f"new destinations: {r['dest_changed']}; rewirable (PR door and arrival both known): {r['rewirable']} "
          f"({r['rewirable_partial']} on some of their PR copies; {r['rewirable_door_agrees']} through a door whose "
          f"vanilla destination agrees); {r['pr_objects_rewired']} PR objects ({r['pr_object_conflicts']} set two ways); "
          f"first arrival {r['rewirable_arrival_how']}; PointIns to add: {r['new_points']}")
    print(f"held by shared PR doors only: {r['shared_only']} ({r['shared_only_world']} World of Balance/Ruin versions: "
          f"a per-world door; the rest story versions of one map)")
    print("not rewirable:")
    for reason, n in r["not_rewirable"].items():
        print(f"  {n:4d}  {reason}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("index", "diff", "show", "apply", "tables"))
    ap.add_argument("out", nargs="?", help="apply: a seed folder (its files/ and bc_doors.json); tables: a JSON file")
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--flags", default=None, help="BC flags (default: the New Player preset + strangejourney)")
    ap.add_argument("--index", default=INDEX_FILE)
    ap.add_argument("--romfree", action="store_true", help="BC on data/bc_base.bin, as the player's generator runs it")
    a = ap.parse_args()
    if a.cmd == "index":
        doc = build_index(_rom())
        write_index(doc, a.index)
        print(f"wrote {os.path.relpath(a.index)}")
        print_coverage(doc["coverage"])
    elif a.cmd == "show":
        print_coverage(load_index(a.index)["coverage"])
    elif a.cmd in ("apply", "tables"):
        if not a.out:
            raise SystemExit(f"{a.cmd}: OUT needed")
        vanilla, seed_rom, flags = make_seed(a.seed, a.flags, None if a.romfree else _rom(), romfree=a.romfree)
        if a.cmd == "tables":       # BC's short entrances and what it changed (tests: ROM against ROM-free)
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump({"short": {str(m): es for m, es in short_entrances(seed_rom).items()},
                           "changes": [[e, s, k] for e, s, k in changes(vanilla, seed_rom)]}, f)
        else:
            os.makedirs(a.out, exist_ok=True)
            apply(a.out, flags, seed_rom, vanilla, index=load_index(a.index))
    else:
        index = load_index(a.index)
        vanilla, seed_rom, flags = make_seed(a.seed, a.flags, _rom())
        r = diff_report(index, vanilla, seed_rom, Pr().graph())
        print(f"seed {a.seed}, flags: {flags}")
        print_diff(r)


if __name__ == "__main__":
    main()
