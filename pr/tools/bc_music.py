"""Beyond Chaos's music for a seed (johnnydmad / johnnyachaotic): its songs, for the plugin's SNES player.

  bc_music.apply(out_dir, rom, vanilla_rom, flags, log)    # from tools/bc_seed.py, after BC ran in process

BC (johnnydmad) compiles ~380 MML songs into FF6's sound format and writes them, with its BRR samples,
into the ROM's song slots; it also gives some areas a slot of their own (Phantom Forest, Daryl's Tomb,
villages...: $51-$5D), four battle and boss tiers ($5E-$61), a Dancing Mad made of three boss songs
($3B) and per-formation battle songs. This reads what it chose, without touching its draws (the seed
stays the exe's): johnnydmad's own tracklist (which file went in which slot) and the songs and samples
in BC's output, and writes the seed's music folder:

  music/songs.json + songs.bin   the song pack (tools/snes_songs.py; plugin/PrKit/Snes plays it)
  music/bc_music.json            what plays where in the PR:
      songs:      slot -> {name, file, variant, title, category, pr_bgm}: pr_bgm when the song is one of
                  FF6's own (BC's ff6_* transcriptions, its fixed songs): the game plays its own track
      pr_to_slot: the PR's bgm id -> FF6's slot (tools/snes_songs.py FF6_SONG_PR_BGM)
      maps:       PR map id -> {"from": [PR bgm ids], "slot": s}: the area plays BC's slot s instead
                  (s = -1: keep the music that's playing)
      formations: PR monster party id -> {"slot": s (-1: keep the field music), "fanfare": bool}
Nothing here is shipped: it is made on the player's machine from their seed. BC's samples are its own
BRR files (MIT); the 8 tiny waveforms FF6's driver keeps resident (programs $00-$07, wind/rain layers)
are FF6's and are not in the pack: the plugin's player synthesizes stand-ins.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import snes_songs as SS  # noqa: E402

MAP_SONGS = 0x2D8F00 + 0x1C      # + map * 0x21: a map's song
MAP_SIZE = 0x21
FORM_AUX = 0xF5900               # + formation * 4: byte 3 bits 3-5 = battle song index, bit 7 = keep music
BATTLE_SONGS = 0x2BF3B           # the 8 battle song slots the index picks from
PAUSE_SONGS = 0x506F9            # the sound code's list of songs that keep the song they interrupt (BC writes it)
FORMATIONS = 576
# BC's ff6_* file names that aren't a track name of BC's (track_ids.txt) -> FF6's slot
FF6_ALIASES = {"forest": 0x18, "final": 0x50, "dmad": 0x3B, "inn": 0x38, "death": 0x3E, "fanfare": 0x2F,
               "balance": 0x06, "omen3": 0x04}
# ff6_dmad's variants: where it starts -> the PR's track for that part
DMAD_PARTS = {"start2": 66, "start3": 67}
# BC's event changes that the map table doesn't show (musicrandomizer.process_map_music): SNES map ->
# (vanilla song played there by its entrance event, BC's slot)
EVENT_MAPS = {0xA2: (0x2A, 0x5C), 0xC0: (0x2A, 0x5C)}


def _say(log, m):
    if log:
        log(m)


def ff6_slot(file, names):
    """FF6's slot of one of BC's ff6_* songs (its file name), else None."""
    base = os.path.splitext(os.path.basename(file or ""))[0]
    if not base.startswith("ff6_"):
        return None
    key = base[4:]
    for k in (key, key.split("_")[0]):
        if k in FF6_ALIASES:
            return FF6_ALIASES[k]
        if k in names and names[k] <= 0x50:
            return names[k]
    return None


def tracklist():
    """johnnydmad's choices after a run in this process: {slot: {name, file, variant, title, category}}."""
    mr = sys.modules.get("music.musicrandomizer")
    tl = getattr(mr, "tracklist", None) if mr else None
    if tl is None:
        return None, {}
    names = dict(mr.track_name_ids)
    cats = {}
    try:
        with open(mr.resource_path(os.path.join(mr.TABLE_PATH, "track_ids.txt")), encoding="utf-8") as f:
            for line in f:
                line = line.split("#")[0]
                if ":" in line and "," in line:
                    i, rest = line.split(":", 1)
                    n, c = [x.strip() for x in rest.split(",")[:2]]
                    cats[n] = c
    except OSError:
        pass
    out = {}
    for name, e in tl.data.items():
        slot = names.get(name)
        if slot is None:
            continue
        mml = e.mml if isinstance(e.mml, str) else "".join(e.mml or [])
        title = re.search(r"(?<=#TITLE )([^;\n]*)", mml or "", re.IGNORECASE)
        album = re.search(r"(?<=#ALBUM )([^;\n]*)", mml or "", re.IGNORECASE)
        rel = (e.file or "").replace("\\", "/")
        for marker in ("/music/", "music/"):
            if marker in rel:
                rel = rel.split(marker, 1)[1]
        out[slot] = {"name": name, "file": rel, "variant": e.variant, "category": cats.get(name, ""),
                     "title": " - ".join(x.group(0).strip() for x in (album, title) if x) or None}
    return out, names


MAP_PAIRS_FILE = "bc_music_maps.json"    # the generator bundle's copy of the SNES -> PR map pairs (bundle_data)


def map_pairs():
    """{SNES map id (str): [{"pr_id": PR map id, "cross", "how", "coverage"}, ...]}: tools/snes_maps.py's
    table (data/snes_pr_maps.json with its hand-confirmed pairs first; less its lookalikes: a tiles/layout pair
    whose PR room is another place's, like Mobliz's inn on Thamasa's, or another room of the same basement), or the
    generator bundle's compact
    copy beside this file ([pr_id, cross, how, coverage] per pair; older copies' bare ids or manual flag still read)."""
    path = os.path.join(HERE, MAP_PAIRS_FILE)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        out = {}
        for k, v in d.items():
            out[k] = [{"pr_id": e} if isinstance(e, int) else
                      {"pr_id": e[0], "cross": bool(e[1]), "coverage": e[3],
                       "how": e[2] if isinstance(e[2], str) else ("manual" if e[2] else "")}
                      for e in v]
        return out
    if not os.path.exists(os.path.join(ROOT, "data", "snes_pr_maps.json")):
        return None
    import snes_maps as SM
    return {str(m): [dict(mt._asdict()) for mt in ms if mt.pr_id is not None and not getattr(mt, "lookalike", False)]
            for m, ms in SM.table().items()}


# how surely a pair is right, by how snes_maps found it (data/snes_pr_maps.json "_source"): hand-confirmed; by chest
# contents or by following exits; by vanilla's doors from a pair; by the layouts alone (many interiors share one); an
# event copy of another map's layout
HOW_RANK = {"manual": 0, "chests": 1, "exits": 1, "door": 2, "door-in": 2, "tiles": 3, "layout": 4}


def pair_rank(e):
    """How surely a PR map is this SNES map's room, for a PR map two SNES maps share (lower first): by how the pair
    was found (HOW_RANK), then by how much of the room matched."""
    return (HOW_RANK.get(e.get("how"), 5), -(e.get("coverage") or 0.0))


def same_world(cands):
    """A PR map's pairs [(rank, SNES map, entry)] less its cross pairs (snes_maps' "cross": the SNES map one world's
    alone, the PR map the other's alone, as each side's nearest world map by doors says) that a pair of the PR map's
    own world, found structurally (hand-confirmed, chests, exits, doors) and at least as surely, outweighs. The world
    tag is a hint (the airship isn't a door; Figaro Castle's basement is nearest the World of Ruin by its cave, though
    both worlds use it), so cross pairs stay when the PR map's only same-world pairs are lookalike layouts (the
    World of Balance basement, like its World of Ruin twin, takes BC's basement song); World of Ruin Mobliz and
    Kohlingen, paired by exits with both SNES towns, take only the World of Ruin town's (seed 1234567890: BC changed
    only the World of Balance towns')."""
    same = [c[0][0] for c in cands if not c[2].get("cross")]
    if not same or min(same) >= HOW_RANK["tiles"]:     # lookalike layouts never outweigh a pair
        return cands
    best = min(same)
    return [c for c in cands if not c[2].get("cross") or c[0][0] < best]


def bundle_data(tools_dir):
    """For tools/bc_bundle.py: the map pairs bc_music needs, compact, into the generator's tools/; and FF6's
    resident waveforms into the generator's data/ (from the developer's ROM; the user may ship them)."""
    pairs = map_pairs() or {}
    compact = {}
    for k, v in pairs.items():
        best = {}
        for e in v:    # one entry per PR map: its best pair (a SNES map can list a PR map at two offsets)
            if e["pr_id"] not in best or pair_rank(e) < pair_rank(best[e["pr_id"]]):
                best[e["pr_id"]] = e
        compact[k] = [[i, int(bool(e.get("cross"))), e.get("how") or "", round(e.get("coverage") or 0.0, 3)]
                      for i, e in sorted(best.items())]
    with open(os.path.join(tools_dir, MAP_PAIRS_FILE), "w", encoding="utf-8") as f:
        json.dump(compact, f, separators=(",", ":"))
    res = resident_source()
    if isinstance(res, dict):
        data = os.path.join(os.path.dirname(tools_dir), "data")
        os.makedirs(data, exist_ok=True)
        SS.write_resident_file(res, os.path.join(data, RESIDENT_FILE))
    return os.path.join(tools_dir, MAP_PAIRS_FILE)


def map_overrides(vanilla, rom, log=None):
    """PR maps whose SNES map BC gave another song: {pr map id: {"from": [PR bgm ids], "slot": s}}."""
    import csv
    pairs = map_pairs()
    if pairs is None:
        _say(log, "music: no SNES -> PR map pairs (data/snes_pr_maps.json): no area songs")
        return {}
    import prdata as P
    bgm, names = {}, {}
    try:
        with open(os.path.join(P.VANILLA, "master", "Assets", "GameAssets", "Serial", "Data", "Master", "map.csv"),
                  encoding="utf-8") as f:
            for r in csv.DictReader(f):
                bgm[int(r["id"])] = int(r["bgm_id"] or 0)
                names[int(r["id"])] = r["map_name"]
    except OSError:
        pass
    # a PR map two SNES maps share (a town's two worlds, rooms the PR merged, lookalike layouts) plays the song of
    # the SNES map that is surest its room (pair_rank), among those BC changed, leaving out the cross-world pairs a
    # same-world pair outweighs (same_world)
    by_pr = {}
    for sm, lst in pairs.items():
        for e in lst:
            by_pr.setdefault(e["pr_id"], []).append((pair_rank(e), int(sm), e))
    out = {}
    for pid, cands in sorted(by_pr.items()):
        cands = same_world(cands)
        got = []
        for rank, sm, e in sorted(cands, key=lambda c: (c[0], c[1])):
            a = MAP_SONGS + sm * MAP_SIZE
            if a >= len(vanilla) or a >= len(rom):
                continue
            vs, bs = vanilla[a], rom[a]
            if sm in EVENT_MAPS and rom[a] == EVENT_MAPS[sm][0]:
                vs, bs = EVENT_MAPS[sm]
            if vs == bs:
                continue
            f = set()
            if vs in SS.FF6_SONG_PR_BGM:
                f.add(SS.FF6_SONG_PR_BGM[vs])
            if bgm.get(pid):
                f.add(bgm[pid])
            if f:
                got.append((sm, bs or -1, f))
        if not got:
            continue
        sm, slot, f = got[0]
        for sm2, slot2, f2 in got[1:]:
            if slot2 == slot:
                f |= f2
            else:
                _say(log, f"music: PR map {pid} is SNES maps {sm:#x} (slot {slot:#x}) and {sm2:#x} (slot {slot2:#x}); "
                          f"{sm:#x}'s kept (its pair is surer)")
        out[pid] = {"from": sorted(f), "slot": slot, "snes_map": sm}
    return inherit_kept(out, by_pr, vanilla, rom, bgm, names, door_graph(), log)


def door_graph():
    """{PR map name: {PR maps its vanilla doors lead to or come from}}: the entrance index's copy (bc_entrances, in
    the generator bundle too); None without it."""
    try:
        import bc_entrances
        return bc_entrances.graph_of(bc_entrances.load_index())
    except Exception:  # noqa: BLE001 - no index: no inherited area songs
        return None


def inherit_kept(out, by_pr, vanilla, rom, bgm, names, graph, log=None):
    """The area songs `out` plus the rooms that keep them: on the SNES a map whose song is 0 keeps the song that
    plays (Mobliz's houses keep BC's town song), while the PR's room names its track again (Map_20111_4: the town's
    21) and the game asks for it, so without a rule of its own it would play the game's track. A PR room with no
    rule, a track of its own (not 0: the PR keeps the song itself), and real SNES pairs that all keep the song in
    BC's game too, takes the rule of the rooms its doors join that play that track as an area song, when they agree
    on one slot (to a fixed point: a house's back room too)."""
    if not graph:
        return out
    ids = {n: i for i, n in names.items()}

    def keeps(cands):
        for _, sm, _ in cands:
            a = MAP_SONGS + sm * MAP_SIZE
            if a >= len(vanilla) or a >= len(rom) or vanilla[a] != 0 or rom[a] != 0:
                return False
        return bool(cands)
    kept = {pid for pid, cands in by_pr.items() if pid not in out and bgm.get(pid) and keeps(cands)}
    added = 0
    while True:
        new = {}
        for pid in kept - set(out):
            b = bgm[pid]
            slots = {out[n]["slot"] for n in (ids.get(x) for x in graph.get(names.get(pid), ())) if n in out and b in out[n]["from"]}
            if len(slots) == 1:
                src = next(n for n in (ids.get(x) for x in graph.get(names.get(pid), ())) if n in out and b in out[n]["from"])
                new[pid] = {"from": [b], "slot": slots.pop(), "snes_map": out[src].get("snes_map"), "kept_from": src}
        if not new:
            break
        out.update(new)
        added += len(new)
    if added:
        _say(log, f"music: {added} PR rooms keep their area's song (SNES song 0: the song that plays)")
    return out


def formations(rom, vanilla, log=None):
    """PR monster party -> BC's battle song for it (slot, -1 to keep the field song) where it differs from
    what the PR's own data plays."""
    import idmap
    table = rom[BATTLE_SONGS:BATTLE_SONGS + 8]
    vtable = vanilla[BATTLE_SONGS:BATTLE_SONGS + 8]
    out = {}
    for f in range(FORMATIONS):
        a = FORM_AUX + 4 * f
        d, vd = rom[a:a + 4], vanilla[a:a + 4]
        keep = bool(d[3] & 0x80)
        slot = -1 if keep else table[(d[3] >> 3) & 7]
        vkeep = bool(vd[3] & 0x80)
        vslot = -1 if vkeep else vtable[(vd[3] >> 3) & 7]
        row = {"slot": slot, "fanfare": not bool(d[1] & 0x02)}
        if slot != vslot or row["fanfare"] != (not bool(vd[1] & 0x02)) or slot in (0x5E, 0x5F, 0x60, 0x61, 0x3B):
            row["snes"] = f
            out[idmap.party(f)] = row
    return out


RESIDENT_FILE = "ff6_resident.json"    # the generator bundle's copy of FF6's resident waveforms (bundle_data)


def resident_source():
    """FF6's resident waveforms (programs $00-$07; the user may ship them, 2026-11-20): the generator bundle's
    data/ff6_resident.json, else the real US ROM on a developer's PC (in ROM-free runs too, so seeds stay the
    same both ways); None: the player synthesizes stand-ins."""
    f = os.path.join(ROOT, "data", RESIDENT_FILE)
    if os.path.exists(f):
        return f
    import prdata as P
    for rom in (os.environ.get("FF6_VANILLA_ROM"), os.path.join(ROOT, "rom", P.ROM_NAME),
                os.path.join(ROOT, "..", "rom", "vanilla", P.ROM_NAME), P.VANILLA_ROM):
        if rom and os.path.exists(rom) and not rom.endswith(".bin"):
            import ff6snes as S
            res = SS.read_resident(S.rom_bytes(rom))
            if any(any(r["brr"]) for r in res.values()):
                return res
    return None


def pause_songs(rom):
    """The songs after which the interrupted song resumes (the sound code's list at C5/06F9, which BC rewrites
    to its battle tiers; up to the first id >= $80 or $00)."""
    out = []
    for b in rom[PAUSE_SONGS:PAUSE_SONGS + 8]:
        if b == 0 or b >= 0x80:
            break
        out.append(b)
    return out


def apply(out_dir, rom, vanilla_rom, flags, log=None):
    """The seed's music folder; returns a summary for bc_seed.json (None without BC's music codes)."""
    flagset = set(flags.split())
    if not flagset & {"johnnydmad", "johnnyachaotic"}:
        return None
    import ff6snes as S
    data = bytes(S.rom_bytes(rom) if isinstance(rom, str) else rom)
    data = SS.unheader(data)
    vanilla = SS.unheader(bytes(S.rom_bytes(vanilla_rom))) if vanilla_rom else b""
    tl, names = tracklist()
    if tl is None:
        _say(log, "music: johnnydmad's tracklist isn't loaded (BC didn't run here): slot names unknown")
        tl = {}
    got = SS.read_ff6_songs(data)
    songs = got["songs"]
    info = {}
    for slot, song in songs.items():
        t = tl.get(slot, {})
        song["name"] = t.get("name") or f"song {slot:02X}"
        if t.get("title"):
            song["title"] = t["title"]
        if t.get("file"):
            song["file"] = t["file"] + (f"?{t['variant']}" if t.get("variant") else "")
        pr = None
        own = ff6_slot(t.get("file"), names)
        if own is not None:
            pr = SS.FF6_SONG_PR_BGM.get(own)
            if own == 0x3B and t.get("variant") in DMAD_PARTS:
                pr = DMAD_PARTS[t["variant"]]       # Dancing Mad from its 2nd or 3rd part
        elif t.get("category") in ("fixed",) or (t.get("category") == "opera" and "alasdraco" not in flagset):
            pr = SS.FF6_SONG_PR_BGM.get(slot)   # FF6's own song in its own place
        info[f"{slot:02X}"] = {**{k: t.get(k) for k in ("name", "file", "variant", "category", "title")}, "pr_bgm": pr}
    music = os.path.join(out_dir, "music")
    SS.write_pack(music, songs, got["samples"], meta={"source": "beyond chaos (johnnydmad)"})
    res = resident_source()
    if res is not None:
        SS.add_resident(music, res)
    maps = map_overrides(vanilla, data, log) if vanilla else {}
    forms = formations(data, vanilla, log) if vanilla else {}
    doc = {"version": 1, "flags": sorted(flagset & {"johnnydmad", "johnnyachaotic", "alasdraco"}),
           "songs": info,
           "pr_to_slot": {str(b): s for b, s in sorted(SS.pr_bgm_to_song().items())},
           "maps": {str(k): v for k, v in sorted(maps.items())},
           "formations": {str(k): v for k, v in sorted(forms.items())},
           # the PR's Dancing Mad parts 2 and 3 while slot $3B plays: its conditional jump (the SNES's tiers)
           "jumps": [[66, 0x3B], [67, 0x3B]],
           # songs that keep the field song for after them (after any other it starts over)
           "pause_songs": pause_songs(data)}
    with open(os.path.join(music, "bc_music.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    low = sum(1 for s in songs.values() if any(p < 0x20 for p in SS.scan_song(s["data"])["programs"]))
    ours = sum(1 for v in info.values() if v["pr_bgm"] is None)
    _say(log, f"music: {len(songs)} songs ({ours} BC's own, {len(songs) - ours} FF6's: the game's tracks), "
              f"{len(got['samples'])} samples, {len(maps)} PR maps with an area song, {len(forms)} formations; "
              f"{low} songs use the driver's resident waveforms")
    return {"songs": len(songs), "bc_songs": ours, "samples": len(got["samples"]), "maps": len(maps),
            "formations": len(forms)}


if __name__ == "__main__":
    # testing: BC on a seed in this process, then the music folder (no port)
    import argparse
    import bc_run
    import ff6snes as S
    import prdata as P
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="9859608359")
    ap.add_argument("--mode", default="normal")
    ap.add_argument("--flags", default="")
    ap.add_argument("--preset", default="New Player")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    flags = a.flags
    if a.preset:
        import bc_seed
        flags = " ".join((bc_seed.PRESETS[a.preset] + " " + flags).split())
    data, _ = bc_run.run(S.rom_bytes(P.VANILLA_ROM), a.seed, a.mode, flags, say=lambda m: None)
    os.makedirs(a.out, exist_ok=True)
    print(apply(a.out, data, P.VANILLA_ROM, flags, print))
