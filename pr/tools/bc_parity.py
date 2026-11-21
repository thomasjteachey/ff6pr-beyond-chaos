"""The ROM-free Beyond Chaos generator against the real-ROM one (dev tool, needs the vanilla ROM): the same seed
made both ways must give the same seed folder (as tools/wc_parity.py does for WC).

  python tools/bc_parity.py [--keep DIR] [--draws] [--live] SEED PRESET_OR_- [FLAGS...]

PRESET is one of BC's presets ("New Player", "Intermediate Player", ...: tools/bc_trace.py preset_flags) or
- for none. Runs tools/bc_seed.py with FF6_BC_ROMFREE=0 and =1 and compares every file the plugin applies
(master tables, messages, files/), bc_seed.json (all but its timestamps) and BC's own log (bc_log.txt, the
game guide BC writes). --draws first compares BC's random draws stage by stage (tools/bc_trace.py, faster to
read when something differs). Both seeds are made from one snapshot of the tools and pr/data (other sessions edit
them all day; --live: from the tools as they are). Exit 0 when they're the same.
"""
import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401

VOLATILE = ("created", "seconds")


def snapshot(tmp):
    """A frozen copy of the tools (and pr/data, the flag list) both generations run from: other sessions edit
    these files all day, and a step that changed between the two runs would show as a difference. The game's
    extract (FF6PR_ROOT), BC's source and its working folder stay the project's."""
    import bc_run
    snap = os.path.join(tmp, "snapshot")
    shutil.rmtree(snap, ignore_errors=True)
    shutil.copytree(HERE, os.path.join(snap, "tools"), ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(os.path.join(ROOT, "data"), os.path.join(snap, "data"))
    os.makedirs(os.path.join(snap, "plugin", "BcPlugin"))
    shutil.copy2(os.path.join(ROOT, "plugin", "BcPlugin", "bc_flags.json"), os.path.join(snap, "plugin", "BcPlugin"))
    # FF6's resident waveforms as the player bundle has them (data/ff6_resident.json: bc_music.bundle_data): the
    # snapshot has no ROM beside it, so without this its ROM-free seed would lack them and differ from BC's exe's
    import bc_music
    res = bc_music.resident_source()
    if isinstance(res, dict):
        bc_music.SS.write_resident_file(res, os.path.join(snap, "data", bc_music.RESIDENT_FILE))
    env = {"FF6PR_ROOT": ROOT, "FF6_BC_SRC": os.path.abspath(bc_run.SRC), "FF6_BC_HOME": os.path.abspath(bc_run.HOME)}
    return snap, env


SNAP = None   # (folder, env) when a snapshot is in use


def make(seed, preset, flags, out, romfree):
    env = dict(os.environ, FF6_BC_ROMFREE="1" if romfree else "0", PYTHONIOENCODING="utf-8", PYTHONWARNINGS="ignore")
    tools, cwd = HERE, ROOT
    if SNAP:
        env.update(SNAP[1])
        tools, cwd = os.path.join(SNAP[0], "tools"), SNAP[0]
    cmd = [sys.executable, os.path.join(tools, "bc_seed.py"), "--seed", seed, "--out", out]
    if preset and preset != "-":
        cmd += ["--preset", preset]
    if flags:
        cmd += ["--flags=" + " ".join(flags)]
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise SystemExit(f"{'ROM-free' if romfree else 'real ROM'} generation failed: {(p.stdout + p.stderr)[-1500:]}")
    return p.stdout.strip().splitlines()[-1]


def compare(a, b):
    diffs = []
    for root, _, files in os.walk(a):
        for fn in files:
            pa = os.path.join(root, fn)
            rel = os.path.relpath(pa, a)
            pb = os.path.join(b, rel)
            if fn == "generate.log":
                continue
            if not os.path.exists(pb):
                diffs.append(f"only in the real-ROM seed: {rel}")
            elif fn == "bc_seed.json":
                ja, jb = (json.load(open(x, encoding="utf-8")) for x in (pa, pb))
                for k in sorted(set(ja) | set(jb)):
                    if k not in VOLATILE and ja.get(k) != jb.get(k):
                        diffs.append(f"bc_seed.json: {k} differs")
            elif fn.endswith(".txt") and not filecmp.cmp(pa, pb, shallow=False):
                la, lb = (open(x, encoding="utf-8", errors="replace").read().splitlines() for x in (pa, pb))
                first = next((i for i, (x, y) in enumerate(zip(la, lb)) if x != y), min(len(la), len(lb)))
                diffs.append(f"{rel} differs from line {first + 1}: {la[first:first + 1]} / {lb[first:first + 1]}")
            elif not filecmp.cmp(pa, pb, shallow=False):
                diffs.append(f"differs: {rel}")
    for root, _, files in os.walk(b):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), b)
            if fn != "generate.log" and not os.path.exists(os.path.join(a, rel)):
                diffs.append(f"only in the ROM-free seed: {rel}")
    return diffs


def draws(seed, preset, flags, tmp):
    """BC's draws both ways (tools/bc_trace.py record --draws-only), compared stage by stage."""
    import bc_trace
    runs = []
    for romfree in (False, True):
        d = os.path.join(tmp, "draws_romfree" if romfree else "draws_rom")
        cmd = [sys.executable, "-W", "ignore", os.path.join(HERE, "bc_trace.py"), "record", d, "--seed", seed,
               "--draws-only"] + (["--preset", preset] if preset and preset != "-" else []) + \
              (["--flags=" + " ".join(flags)] if flags else []) + (["--romfree"] if romfree else [])
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode != 0:
            raise SystemExit(f"bc_trace failed: {(p.stdout + p.stderr)[-1500:]}")
        runs.append(d)
    return bc_trace.diff(*runs)


def main(argv):
    global SNAP
    keep, with_draws, live = None, False, False
    while argv[:1] in (["--keep"], ["--draws"], ["--live"]):
        if argv[0] == "--keep":
            keep, argv = argv[1], argv[2:]
        elif argv[0] == "--draws":
            with_draws, argv = True, argv[1:]
        else:
            live, argv = True, argv[1:]
    seed, preset, flags = argv[0], argv[1], argv[2:]
    tmp = os.path.abspath(keep) if keep else tempfile.mkdtemp(prefix="bc_parity_")
    os.makedirs(tmp, exist_ok=True)
    a, b = os.path.join(tmp, "rom"), os.path.join(tmp, "romfree")
    if not live:
        SNAP = snapshot(tmp)
    try:
        if with_draws and draws(seed, preset, flags, tmp):
            print("BC's draws differ")
            return 1
        print("real ROM: ", make(seed, preset, flags, a, False))
        print("ROM-free: ", make(seed, preset, flags, b, True))
        diffs = compare(a, b)
        print("\n".join(diffs) if diffs else "the same seed folder")
        return 1 if diffs else 0
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
