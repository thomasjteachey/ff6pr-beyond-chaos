"""Beyond Chaos's spoiler log in the Pixel Remaster's names: bc_log_pr.txt beside BC's bc_log.txt (audit item 33).

BC writes its game guide (bc_log.txt: characters, espers, item magic, monsters, treasure) with the SNES's names
("ValiantKnife", "Bolt 2", "ALEXANDR"), which the Pixel Remaster doesn't use. This copy names the same things as the
player's game does: each SNES item, spell/skill and esper name in the seed's ROM, matched by its id (idmap) to the
seed folder's own name for it (the porter's, BC's renamed items included). BC's own file stays as BC wrote it
(test_bc's parity check reads it).

  python tools/bc_spoiler.py SEED_DIR ROM     (bc_seed.py runs it on every seed)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401

OUT_NAME = "bc_log_pr.txt"
HEADER = ("Beyond Chaos's game guide for this seed, in the names the Pixel Remaster uses (BC's own, with the SNES's "
          "names: bc_log.txt).\n")
MIN_LEN = 3          # shorter SNES names ("Imp" is 3) are too easily part of other words to replace safely


def _rom(data):
    """ff6snes's Rom over bytes already read (bc_seed keeps the seed's ROM in memory only)."""
    import ff6snes as S
    r = S.Rom.__new__(S.Rom)
    r.data = bytes(data)
    return r


def _plain(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def name_pairs(out, rom):
    """{SNES name as BC's log writes it: the seed's PR name} for items, spells/skills and espers (an esper's name
    also in capitals, as the log's esper headings are). A name the PR keeps maps to itself, and so does a SNES name
    two things share with different PR names (the item Remedy and the spell Remedy, the PR's Esuna): kept whole, they
    keep a shorter name inside them from being renamed ("Crystal Helm" isn't "Crystal" the sword + " Helm")."""
    import ff6snes as S
    import idmap as M
    import prdata as P
    import bc_commands
    r = rom if hasattr(rom, "table") else _rom(S.rom_bytes(rom) if isinstance(rom, str) else rom)
    content = bc_commands._tables(out, ["content"])["content"]
    _, msg = bc_commands._messages(out)
    vmsg = P.messages("system", "en")

    def pr_name(cid):
        row = content.rows.get(cid) if cid else None
        if not row:
            return ""
        key = row["mes_id_name"]
        return _plain(msg.get(key) if key in msg else vmsg.get(key, ""))

    ability_content = {int(x["type_value"]): int(x["id"]) for x in content.rows.values() if x["type_id"] == "4"}
    claims = {}

    def add(snes, pr):
        snes, pr = (snes or "").strip(), (pr or "").strip()
        if len(snes) >= MIN_LEN and pr:
            claims.setdefault(snes, set()).add(pr)

    for it in S.items(r)[:256]:
        add(it.name, pr_name(M.item_content(it.id)))
    for i, name in enumerate(S.spell_names(r)[:256]):
        ab = M.spell(i)
        add(name, pr_name(ability_content.get(ab)) if ab else "")
        if name.startswith("L? "):                 # BC's log writes the Lore "L? Pearl" as "L.? Pearl"
            add("L.? " + name[3:], pr_name(ability_content.get(ab)) if ab else "")
    for e in S.espers(r):
        name = pr_name(M.esper_content(e.id))
        add(e.name, name)
        add(e.name.upper(), name.upper())
    return {k: next(iter(v)) if len(v) == 1 else k for k, v in claims.items()}


MONSTER_HEADER = re.compile(r"^(.+?) \(Level \d+\)\r?$", re.M)   # the log's monster entries: "Doom Drgn (Level 54)"
MONSTER_LINE = re.compile(r"^(?:.+? \(Level \d+\)|\*?Enemy \d+: .*)\r?$")   # ... and a chest's monsters


def _subber(pairs):
    names = sorted(pairs, key=len, reverse=True)
    rx = re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w-])")
    return lambda s: rx.sub(lambda m: pairs[m.group(0)], s)


def rename(text, pairs, keep=()):
    """Every whole-word SNES name in text -> its PR name, in one pass (the longest name first, so "Bolt 2" isn't
    read as "Bolt"; a replacement is never renamed again). keep: names a line naming monsters (a monster's entry,
    a chest's "Enemy" line) leaves as they are: the PR shows BC's monster names, and the boss Doom isn't the spell
    Doom (the PR's Death) that a SKILLS line means."""
    if not any(k != v for k, v in pairs.items()):
        return text
    plain = _subber(pairs)
    monsters = _subber({**pairs, **{k: k for k in keep if k}}) if keep else plain
    return "\n".join(monsters(line) if MONSTER_LINE.match(line) else plain(line) for line in text.split("\n"))


def write(out, rom, spoiler=None, log=print):
    """bc_log_pr.txt in the seed folder `out` from BC's log (spoiler, or out/bc_log.txt); returns how many names
    it changed."""
    if spoiler is None:
        with open(os.path.join(out, "bc_log.txt"), encoding="utf-8") as f:
            spoiler = f.read()
    pairs = name_pairs(out, rom)
    text = rename(spoiler, pairs, keep=set(MONSTER_HEADER.findall(spoiler)))
    lines = sum(1 for a, b in zip(spoiler.splitlines(), text.splitlines()) if a != b)
    with open(os.path.join(out, OUT_NAME), "w", encoding="utf-8") as f:
        f.write(HEADER + "\n" + text)
    renamed = sum(1 for k, v in pairs.items() if k != v)
    log(f"bc spoiler: {OUT_NAME}: {renamed} SNES names in the PR's, {lines} lines changed")
    return renamed


if __name__ == "__main__":
    write(sys.argv[1], sys.argv[2])
