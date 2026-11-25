"""Every monster party a Beyond Chaos seed folder sends the player to, checked against the seed's own
monster_party.csv (the full table: vanilla's rows plus the seed's). The PR dropped ~40 SNES formations
(idmap.party's formation + 1 has no row for them), so a seed step that names a formation's party without
making it would start a battle the game can't build (the NP seed's chest 207 -> party 507, 2026-11-21).

Where a seed names a party:
  monster_set.csv      random encounters (monster_set1..6)
  scripts              Encount / EncountBoss in every script the seed writes (event battles, monster boxes,
                       bc_events' scenes); the game's own scripts name vanilla parties, which every seed keeps
  the Veldt            misc serial_misc_assets beast_field_encount_table (port_veldt)
  bc_seed.json         monster_chests (seed_info.monster_chests), the Colosseum's opponents (coliseum[3])

    python tools/bc_party_refs.py SEED_DIR...      # prints each folder's missing parties (exit 1 if any)
"""
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
import seed_live as L  # noqa: E402

VELDT = "misc/Assets/GameAssets/Serial/Data/Misc/serial_misc_assets.json"


def _master(seed_dir, table):
    return os.path.join(seed_dir, *L.MASTER_PATH.split("/"), table + ".csv")


def parties(seed_dir):
    """The seed's monster_party ids (its full table)."""
    with open(_master(seed_dir, "monster_party"), encoding="utf-8", newline="") as f:
        return {int(r[0]) for i, r in enumerate(csv.reader(f)) if i and r and r[0].isdigit()}


def refs(seed_dir):
    """{party id: [where it's named]} for every party the seed folder sends the player to."""
    out = {}

    def add(pid, where):
        pid = int(pid or 0)
        if pid > 0:
            out.setdefault(pid, []).append(where)
    path = _master(seed_dir, "monster_set")
    if os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                for k in range(1, 7):
                    add(r.get(f"monster_set{k}"), f"monster_set {r['id']}")
    for path in glob.glob(os.path.join(seed_dir, "**", "*.json"), recursive=True):
        rel = os.path.relpath(path, seed_dir).replace("\\", "/")
        if rel == "bc_seed.json" or "/keys/" in rel:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict):
            continue
        for m in doc.get("Mnemonics") or []:
            if str(m.get("mnemonic", "")).startswith("Encount"):
                iv = (m.get("operands") or {}).get("iValues") or [0]
                add(iv[0], f"script {doc.get('Name') or os.path.basename(path)}")
        for g in doc.get("beast_field_encount_table") or []:
            for e in g.get("party_table") or []:
                for k in ("monster_party_id", "encount_target_party_id"):
                    add(e.get(k), f"Veldt entry {e.get('id')}")
                for o in e.get("encount_target_other_ids") or []:
                    add(o, f"Veldt entry {e.get('id')} (opener)")
    info_path = os.path.join(seed_dir, "bc_seed.json")
    if os.path.exists(info_path):
        with open(info_path, encoding="utf-8") as f:
            info = json.load(f)
        for flag, pid in (info.get("monster_chests") or {}).items():
            add(pid, f"monster chest {flag}")
        for m in info.get("coliseum") or []:
            if isinstance(m, list) and len(m) > 3:
                add(m[3], f"Colosseum wager {m[0]}")
    return out


def missing(seed_dir):
    """{party id: [where]} for the parties the seed names that its monster_party.csv lacks."""
    have = parties(seed_dir)
    return {p: w for p, w in sorted(refs(seed_dir).items()) if p not in have}


def main(argv):
    bad = False
    for d in argv:
        r, m = refs(d), missing(d)
        print(f"{d}: {len(r)} parties named, {len(m)} missing" + "".join(f"\n  {p}: {', '.join(w[:4])}" for p, w in m.items()))
        bad |= bool(m)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
