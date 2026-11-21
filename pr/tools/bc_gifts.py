"""Beyond Chaos's event gifts on the Pixel Remaster: the items and gil BC's `t` rerolls in events (BC's
chestrandomizer.mutate_event_items: 28 gifts, `bsiab` lets them be any item), given by the PR's own scripts.

  .venv/Scripts/python tools/bc_gifts.py files        # the PR scripts a seed may change (the baseline's)
  .venv/Scripts/python tools/bc_gifts.py check        # every gift's give and line found in vanilla's scripts
  .venv/Scripts/python tools/bc_gifts.py magicite-lines   # (dev) data/bc_magicite.json from the kit's dialogue map

BC's choices come from its run (bc_data.prepare records each gift as BC rerolls it: bc_seed.json event_items),
never drawn here. Each gift is one of BC's event pointers; GIFTS says which PR scripts give it (GetItem of the
PR's vanilla content: every such op in that script) and which lines name it (Msg of that key, pointed at a line of
the seed's own, BC_GIFT_*, in system_en; or the Tag that names the item for T0001_01_01). Scripts come from the
seed folder when another step wrote them (bc_events: notawaiter's cut scenes carry BC's skip items already, so a
script with no vanilla give left is passed by), else vanilla's; bc_live puts every script here in the baseline.

Not here: the opening's two Sleeping Bags (CA/A00A, CA/A00C: the PR's opening gives none), the text BC shows
with gifts the PR gives silently (Kohlingen's six, the Ragnarok sword, the Masamune, the Auto Crossbow), monster
boxes (BC never puts one in an event gift: its event gifts have no monster set).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
import prdata as P  # noqa: E402
import pr_script as S  # noqa: E402

GIL = 1                          # the PR's content for gil (GetItem [1, amount])
KEY = "BC_GIFT_{:05X}_{}"        # the seed's lines (system_en)
TAG = "<tag>"                    # the line is the Tag ITEM_N + T0001_01_01 ("Obtained (ITEM_N)!")
GOT = ("<CT>Obtained {name}!", "<CT>Obtained {gil} gil!")
FOUND = ("{name}...", "{gil} gil...")
WOLF = ("Grrr... You'll never get this {name}!", "Grrr... You'll never get this {gil} gil!")

# BC's event pointer -> ([(script, the PR's vanilla content given there)], [(script, line key or TAG, texts)])
GIFTS = {
    0xCA00A: ([], []),                                   # Narshe, the opening's Sleeping Bag: none in the PR
    0xCA00C: ([], []),
    0xCD59E: ([("sc_e_0439", 304)], [("sc_e_0437", "E0437_00_020_a_04", WOLF),        # the Lone Wolf's Gold Hairpin
                                     ("sc_e_0439", "E0439_00_020_a_03", GOT)]),
    0xA66B4: ([("sc_e_0026", 38)], []),                  # Figaro: the Auto Crossbow
    0xAFB0B: ([("sc_e_0062", 307)], [("sc_e_0062", "E0062_00_066_a_14", GOT)]),        # Banon's Gauntlet
    0xAFFD2: ([("sc_e_0062_1", 308), ("sc_e_1073", 308)],                              # the Genji Glove
              [("sc_e_0062_1", "E0062_01_067_a_47", GOT), ("sc_e_1073", "E0062_01_067_a_47", GOT)]),
    0xC6883: ([("sc_e_0238", 328)], [("sc_e_0238", "E0238_00_090_a_02", GOT)]),        # Mobliz: Tintinnabulum
    0xBC432: ([("sc_e_0244", 2)], [("sc_e_0244", "E0244_00_378_a_01", FOUND)]),        # Crescent Mountain: Potion
    0xB30E5: ([("sc_e_0450", 29)], [("sc_e_0450", "E0450_00_408_a_02", GOT)]),         # the Sealed Gate's four
    0xB3103: ([("sc_e_0451", 27)], [("sc_e_0451", "E0451_00_408_a_01", GOT)]),
    0xB3121: ([("sc_e_0452", 14)], [("sc_e_0452", "E0452_00_408_a_01", GOT)]),
    0xB313F: ([("sc_e_0453", GIL)], [("sc_e_0453", "E0453_00_408_a_01", GOT)]),
    0xC9257: ([("sc_e_0506", 328)], [("sc_e_0506", "E0506_00_166_a_08", GOT)]),        # Vector's dinner: two
    0xC926C: ([("sc_e_0506", 322)], [("sc_e_0506", "E0506_00_166_a_09", GOT)]),
    0xB4A84: ([("sc_e_0767_1", GIL)], [("sc_e_0767_1", "E0453_00_408_a_01", GOT)]),    # Owzer's paintings' four
    0xB4AC4: ([("sc_e_0768_1", 2)], [("sc_e_0768_1", TAG, GOT)]),
    0xB4B03: ([("sc_e_0769_1", 5)], [("sc_e_0769_1", TAG, GOT)]),
    0xB4B42: ([("sc_e_0770_1", 14)], [("sc_e_0770_1", TAG, GOT)]),
    0xB99F4: ([("sc_e_0939_2", 142)], []),               # Doma, Cyan's dream: the Masamune
    0xC3240: ([("sc_e_0828_4", 4)], []),                 # the Phoenix Cave's treasures (Locke's return): six
    0xC3242: ([("sc_e_0828_4", 10)], []),
    0xC3244: ([("sc_e_0828_4", 7)], []),
    0xC3246: ([("sc_e_0828_4", 8)], []),
    0xC3248: ([("sc_e_0828_4", 207)], []),
    0xC324A: ([("sc_e_0828_4", 103)], []),
    0xC0B67: ([("sc_e_0873", 121)], []),                 # Narshe's smith: the Ragnarok sword
    0xC0B80: ([("sc_e_0874", 213)], [("sc_e_0874", "E0847_00_015_a_02", GOT)]),        # the Cursed Shield
    0xC5598: ([("sc_e_0879_1", 127)], [("sc_e_0879_1", "E0879_00_483_a_01", GOT)]),    # Fanatics' Tower: Holy Lance
}
BC_ITEM, BC_GIL = 0x40, 0x80     # BC's content types (gil: contents x 100)


def scripts():
    names = set(MAGICITE_SCRIPTS)
    for gives, lines in GIFTS.values():
        names |= {s for s, _ in gives} | {s for s, _, _ in lines}
    return sorted(names)


def files():
    """Every Magicite file a seed's gifts may change (bc_live.own_files)."""
    return sorted(S.rel(n) for n in scripts())


def name_key(content):
    row = P.Table("content").rows.get(int(content))
    return row["mes_id_name"] if row else None


def content_name(content):
    text = P.messages("system", "en").get(name_key(content) or "", "")
    return re.sub(r"<[^>]*>", "", text).strip()


def _ops(sc):
    return sc.get("Mnemonics", [])


def _iv(m):
    return (m.get("operands") or {}).get("iValues") or []


def _sv(m):
    return (m.get("operands") or {}).get("sValues") or []


def give_ops(sc, content):
    return [i for i, m in enumerate(_ops(sc)) if m["mnemonic"] == "GetItem" and _iv(m) and _iv(m)[0] == content]


def line_ops(sc, key):
    """Msg ops showing `key`; for TAG: [(the Tag op naming the item, the T0001_01_01 Msg after it)]."""
    ops = _ops(sc)
    if key != TAG:
        return [i for i, m in enumerate(ops) if m["mnemonic"] == "Msg" and _sv(m)[:1] == [key]]
    out = []
    for i, m in enumerate(ops):
        if m["mnemonic"] == "Tag" and _sv(m)[:1] == ["ITEM_N"]:
            j = next((j for j in range(i + 1, min(len(ops), i + 4))
                      if ops[j]["mnemonic"] == "Msg" and _sv(ops[j])[:1] == ["T0001_01_01"]), None)
            if j is not None:
                out.append((i, j))
    return out


def apply(out, event_items, flags, log=print):
    """BC's rerolled gifts (bc_seed.json event_items: [{pointer, before, after: {type, contents}}]) into the seed
    folder `out`: its scripts in files/<rel>, its lines in system_en. Returns (files written, {pointer: what})."""
    import bc_events
    ctx = bc_events.Ctx(out, flags)
    plan = {}          # script -> [(op, new values)] found first on the script as it was, then applied
    lines, done = [], {}
    for e in event_items or []:
        ptr, after = e.get("pointer"), e.get("after") or {}
        gives, says = GIFTS.get(ptr, (None, None))
        if not gives:
            continue
        kind, value = after.get("type"), after.get("contents")
        if kind == BC_ITEM:
            import idmap as M
            new, count = M.item_content(value), 1
            if not new:
                log(f"bc_gifts: {ptr:05X}: BC's item {value:#x} has no PR content")
                continue
            if all(van == new for _, van in gives):
                continue               # BC's reroll gave the PR's own item: its scripts and lines as they are
            text = {"name": content_name(new)}
        elif kind == BC_GIL:
            new, count = GIL, value * 100
            text = {"gil": count}
        else:
            log(f"bc_gifts: {ptr:05X}: BC's content type {kind} isn't ported")
            continue
        found = 0
        for script, van in gives:
            sc = ctx.script(script)
            for i in give_ops(sc, van):
                plan.setdefault(script, []).append((i, "give", (new, count)))
                found += 1
        if not found:
            log(f"bc_gifts: {ptr:05X}: no vanilla give left in {[s for s, _ in gives]} (another step's)")
            continue
        for n, (script, key, texts) in enumerate(says):
            sc = ctx.script(script)
            line = texts[0 if kind == BC_ITEM else 1].format(**text)
            if key == TAG and kind == BC_ITEM:
                for t, _ in line_ops(sc, TAG):
                    plan.setdefault(script, []).append((t, "tag", name_key(new)))
                continue
            k = KEY.format(ptr, n)
            ops = [j for _, j in line_ops(sc, TAG)] if key == TAG else line_ops(sc, key)
            for i in ops:
                plan.setdefault(script, []).append((i, "msg", k))
            if ops:
                lines.append((k, line))
        done[f"{ptr:05X}"] = text.get("name") or f"{text['gil']} gil"
    for script, changes in plan.items():
        sc = ctx.script(script)
        ops = _ops(sc)
        for i, what, v in changes:
            o = ops[i].setdefault("operands", {})
            if what == "give":
                iv = list(_iv(ops[i])) + [0] * max(0, 2 - len(_iv(ops[i])))
                iv[0], iv[1] = v
                o["iValues"] = iv
            else:
                sv = list(_sv(ops[i]))
                sv[1 if what == "tag" else 0] = v
                o["sValues"] = sv
        ctx.set_script(script, sc)
    written = []
    for name, (rel, sc) in sorted(ctx.scripts.items()):
        if name not in plan:
            continue
        dest = os.path.join(out, "files", *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(json.dumps(sc, ensure_ascii=False, separators=(",", ":")))
        written.append(rel)
    if lines:
        import seed_live as L
        path = os.path.join(out, *L.MESSAGE_PATH.split("/"), "system_en.txt")
        with open(path, "a", encoding="utf-8", newline="") as f:
            for k, t in lines:
                f.write(f"{k}\t{t}\r\n")
    if done:
        log(f"bc_gifts: {len(done)} gifts in {len(written)} scripts")
    return written, done


# --- `y`: BC's espers shuffled (esperrandomizer.randomize_magicite) -------------------------------------------------
# BC rewrites each esper gift (event commands 86/87 at the addresses in its tables/magicite.txt) with the esper's
# replacement, names the replacement in that gift's dialogues (dialogue variables), the Phoenix Cave after Phoenix's
# replacement and the Ragnarok sword after Ragnarok's; the bosses' names come with the porter's monster names.
# Here: every esper GetItem in the PR's scripts that give magicite, the PR's lines for BC's dialogues (from the kit's
# dialogue map: bc_magicite.json, made by `magicite-lines`), MSG_MAP_NAME_54 and the sword's name.
MAGICITE_JSON = os.path.join(HERE, "..", "data", "bc_magicite.json")   # {BC's address: [PR story keys]}
MAGICITE_SCRIPTS = ["sc_e_0303", "sc_e_0304", "sc_e_0305", "sc_e_0306", "sc_e_0399", "sc_e_0400", "sc_e_0402",
                    "sc_e_0422", "sc_e_0423", "sc_e_0427", "sc_e_0640", "sc_e_0651", "sc_e_0775", "sc_e_0780_1",
                    "sc_e_0789_1", "sc_e_0828_4", "sc_e_0873", "sc_e_0886", "sc_e_0890", "sc_e_0940", "sc_e_0963",
                    "sc_e_0964_2", "sc_e_0975"]
PHOENIX_CAVE = ("MSG_MAP_NAME_54", "Phoenix")
SWORD = 121                            # the PR's Ragnarok sword (content): its name is Ragnarok's replacement's
ESPERS = 27


def magicite_table():
    """BC's tables/magicite.txt: [(address, [SNES dialogues])]."""
    import bc_run
    out = []
    with open(os.path.join(bc_run.SRC, "tables", "magicite.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if line:
                parts = [x.strip() for x in line.split(",")]
                out.append((int(parts[0], 16), [int(d, 16) for d in parts[1:]]))
    return out


def magicite_lines():
    """(dev, from the kit's dialogue map) {address: [PR story keys]} for BC's magicite dialogues."""
    import event_translate as E
    dk = E.dialog_keys()
    return {f"{a:05X}": sorted({k for d in ds for k in dk.get(d, [])}) for a, ds in magicite_table()}


def story_keys():
    """Every story line a seed's espers may rename (the baseline keeps them as the game has them)."""
    try:
        with open(MAGICITE_JSON, encoding="utf-8") as f:
            return sorted({k for keys in json.load(f).values() for k in keys})
    except OSError:
        return []


def esper_map(rom, vanilla):
    """{the esper BC's table gives in vanilla: the one BC's seed gives there} (event commands 86/87 xx: 0x36+id;
    BC writes xx at its address + 1 whatever its other patches made of the command: the Narshe smith's scene moves
    its 86 two bytes, BC's esper byte lands at both)."""
    out = {}
    for a, _ in magicite_table():
        if vanilla[a] in (0x86, 0x87):
            o, n = vanilla[a + 1] - 0x36, rom[a + 1] - 0x36
            if 0 <= o < ESPERS and 0 <= n < ESPERS:
                out[o] = n
    return out


def _esper_name(i):
    import idmap as M
    return content_name(M.esper_content(i))


def espers(out, rom, vanilla, flags, log=print):
    """`y`: BC's esper shuffle into the seed folder (scripts in files/<rel>, story_mes_en and system_en lines).
    Returns (files written, {vanilla esper name: the seed's})."""
    import idmap as M
    import bc_events
    import bc_data
    if "y" not in flags.split():
        return [], {}
    m = {o: n for o, n in esper_map(rom, vanilla).items() if o != n}
    if not m:
        return [], {}
    cmap = {M.esper_content(o): M.esper_content(n) for o, n in m.items()}
    ctx = bc_events.Ctx(out, flags)
    written = []
    for name in MAGICITE_SCRIPTS:
        sc = ctx.script(name)
        hits = [(i, cmap[_iv(op)[0]]) for i, op in enumerate(_ops(sc))      # gives, and the Ancient Castle's
                if op["mnemonic"] in ("GetItem", "RemoveItem") and _iv(op) and _iv(op)[0] in cmap]   # Odin taken
        for i, new in hits:                     # found first, then changed (two espers may trade places)
            iv = list(_iv(_ops(sc)[i]))
            iv[0] = new
            _ops(sc)[i]["operands"]["iValues"] = iv
        if hits:
            rel = ctx.scripts[name][0]
            dest = os.path.join(out, "files", *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(json.dumps(sc, ensure_ascii=False, separators=(",", ":")))
            written.append(rel)
    names = {o: (_esper_name(o), _esper_name(n)) for o, n in m.items()}
    # the lines: each gift's dialogues name its esper's replacement (one pass: espers may trade names)
    with open(MAGICITE_JSON, encoding="utf-8") as f:
        keys_of = json.load(f)
    van = {}
    for a, _ in magicite_table():
        o = vanilla[a + 1] - 0x36 if vanilla[a] in (0x86, 0x87) else None
        if o in names:
            for k in keys_of.get(f"{a:05X}", []):
                van.setdefault(k, set()).add(o)
    text = bc_data.story_lines(sorted(van))
    lines = {}
    for k, os_ in van.items():
        if k not in text:
            continue
        swap = {names[o][0]: names[o][1] for o in os_}
        pat = re.compile("|".join(re.escape(x) for x in sorted(swap, key=len, reverse=True)))
        new = pat.sub(lambda mt: swap[mt.group(0)], text[k])
        if new != text[k]:
            lines[k] = new
    if lines:
        bc_data._story(out, lines)
    # the Phoenix Cave and the Ragnarok sword (system_en, in place)
    sysl = {}
    ph = next((o for o in m if _esper_name(o) == PHOENIX_CAVE[1]), None)
    if ph is not None:
        sysl[PHOENIX_CAVE[0]] = f"{_esper_name(m[ph])} Cave"
    rg = next((o for o in m if _esper_name(o) == "Ragnarok"), None)
    if rg is not None:
        key = name_key(SWORD)
        icon = re.match(r"(<[^>]*>)*", P.messages("system", "en").get(key, "")).group(0)
        sysl[key] = icon + _esper_name(m[rg])
    if sysl:
        path, lines_, keys = bc_data._messages(out)
        for k, v in sysl.items():
            if k in keys:
                lines_[keys[k]] = f"{k}\t{v}"
            else:
                lines_.append(f"{k}\t{v}")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("\r\n".join(lines_))
    log(f"bc_gifts: espers {', '.join(f'{a}->{b}' for a, b in names.values())}; {len(lines)} lines")
    return written, {a: b for a, b in names.values()}


def check():
    """Every gift's vanilla give and line found in vanilla's scripts (the table above is right)."""
    bad = []
    for ptr, (gives, says) in GIFTS.items():
        for script, van in gives:
            if not give_ops(S.load(script), van):
                bad.append(f"{ptr:05X}: no GetItem {van} in {script}")
        for script, key, _ in says:
            if not line_ops(S.load(script), key):
                bad.append(f"{ptr:05X}: no {key} in {script}")
    import idmap as M
    espers = {M.esper_content(i) for i in range(ESPERS)}
    for name in MAGICITE_SCRIPTS:
        if not [op for op in _ops(S.load(name)) if op["mnemonic"] == "GetItem" and _iv(op)[:1] and _iv(op)[0] in espers]:
            bad.append(f"no magicite given in {name}")
    try:
        if magicite_lines() != json.load(open(MAGICITE_JSON, encoding="utf-8")):
            bad.append(f"{MAGICITE_JSON} is out of date: magicite-lines")
    except OSError as e:
        print(f"(the dialogue map isn't here: {e})")
    for b in bad:
        print(b)
    print("ok" if not bad else f"{len(bad)} missing")
    return not bad


if __name__ == "__main__":
    if sys.argv[1:] == ["files"]:
        print("\n".join(files()))
    elif sys.argv[1:] == ["magicite-lines"]:
        with open(MAGICITE_JSON, "w", encoding="utf-8") as f:
            json.dump(magicite_lines(), f, indent=1, sort_keys=True)
        print(MAGICITE_JSON)
    elif sys.argv[1:] == ["check"]:
        sys.exit(0 if check() else 1)
    else:
        sys.exit(__doc__)
