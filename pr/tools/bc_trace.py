"""Record a Beyond Chaos run: every random draw and every ROM byte it reads, by the BC line that did it
(the ROM-free generator's dev tool, as tools/wc_trace.py was WC's: PORTING.md "WC without an SNES ROM").

  .venv/Scripts/python tools/bc_trace.py record OUT_DIR [--seed N] [--mode normal] [--preset "New Player"]
                                                [--flags "..."] [--romfree]
  .venv/Scripts/python tools/bc_trace.py diff OUT_A OUT_B      the first draw two runs disagree on, per generator
  .venv/Scripts/python tools/bc_trace.py sites OUT_DIR [--min N] the reads by BC function, largest first
  .venv/Scripts/python tools/bc_trace.py port OUT.json [--seed/--preset/--flags/--romfree]
                                      the ROM bytes our side reads (tools/bc_seed.py after BC: the porter,
                                      bc_items, seed_info ...), vanilla's and BC's output's, by function

record runs BC (tools/bc_run.py, BC's own code) on the vanilla ROM, or with --romfree on the generator's
shipped data and stand-ins (tools/bc_romfree.py), and writes:
  OUT_DIR/draws.txt     one line per draw: "gen kind arg result site" (gen: g = the random module's own,
                        r1, r2, ... each random.Random BC makes, in creation order; seed lines too)
  OUT_DIR/reads.json    {site: {"in": regions, "out": regions, "n": bytes}}: input-buffer bytes read, and
                        output-buffer bytes read before BC wrote them (both are the ROM's), by the BC
                        function that asked (past BC's generic readers), as merged [start, end) regions
  OUT_DIR/out.bin       BC's output (zlib'd behind bc_run.OUT_MAGIC); OUT_DIR/spoiler.txt its log
Whole-ROM reads (the music's and the opera's `fout.read()`) hand back bytes that keep recording, through
johnnydmad's byte_insert, so its own table reads count and its copies don't. Copies BC makes of the whole
ROM (the checksum, the ExHiROM mirror of bank 00, remonsterate's mirror) show under their own sites.
remonsterate runs in this process (BC starts it in a child process) so its reads are recorded too.

Two runs with the same draws made the same choices (BC reseeds before each stage: a stage's draws depend
only on its own reads); with the same tables the porter reads, the same seed (tools/bc_parity.py).
"""
import argparse
import collections
import io
import json
import os
import random as _random
import re
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401

SIZE = 8 * 2 ** 20
SKIP_DRAW = ("random.py", "bc_trace.py")
# BC's generic readers: a read is put on the first frame past these
GENERIC = ("bc_trace.py", "<frozen", os.sep + "io.py", os.sep + "utils.py", "tablereader.py", "insertmfvi.py:byte_insert",
           "insertmfvi.py:int_insert", "insertmfvi.py:bytes_to_int")
BULK = 0x8000

DRAWS = []
READS = collections.defaultdict(lambda: {"in": [], "out": []})
_src = ""


def _rel(fn):
    if _src and fn.startswith(_src):
        return fn[len(_src) + 1:].replace(os.sep, "/")
    return os.path.basename(fn)


def draw_site():
    f = sys._getframe(2)
    while f is not None:
        fn = f.f_code.co_filename
        if not fn.endswith(SKIP_DRAW):
            return f"{_rel(fn)}:{f.f_code.co_name}:{f.f_lineno}"
        f = f.f_back
    return "?"


def read_site():
    f = sys._getframe(2)
    while f is not None:
        fn = f.f_code.co_filename
        key = fn + ":" + f.f_code.co_name
        if not any(g in key for g in GENERIC):
            return f"{_rel(fn)}:{f.f_code.co_name}"
        f = f.f_back
    return "?"


def trace_random():
    """Record every draw: the random module's own generator and each random.Random made after this."""
    labels = {}

    def label(inst):
        k = id(inst)
        if k not in labels:
            labels[k] = "g" if inst is _random._inst else f"r{len(labels) + (0 if _random._inst and id(_random._inst) in labels else 1)}"
        return labels[k]

    g = _random._inst
    c_random, c_bits, c_seed = g.random, g.getrandbits, g.seed

    def g_random():
        r = c_random()
        DRAWS.append(("g", "r", 0, repr(r), draw_site()))
        return r

    def g_bits(k):
        r = c_bits(k)
        DRAWS.append(("g", "b", k, r, draw_site()))
        return r

    def g_seed(a=None, version=2):
        DRAWS.append(("g", "seed", 0, repr(a), draw_site()))
        return c_seed(a, version)

    g.random, g.getrandbits, g.seed = g_random, g_bits, g_seed
    _random.random, _random.getrandbits, _random.seed = g_random, g_bits, g_seed
    labels[id(g)] = "g"
    counter = [0]
    base = _random.Random

    made = collections.Counter()

    class TRandom(base):
        def __init__(self, x=None):
            # labelled by where it's made (the same in every run: a module reloaded makes its second)
            site = draw_site().rsplit(":", 1)[0].replace(" ", "_")
            made[site] += 1
            self._trace_label = f"{site}#{made[site]}"
            super().__init__(x)

        def seed(self, a=None, version=2):
            if hasattr(self, "_trace_label"):
                DRAWS.append((self._trace_label, "seed", 0, repr(a), draw_site()))
            return super().seed(a, version)

        def random(self):
            r = super().random()
            DRAWS.append((self._trace_label, "r", 0, repr(r), draw_site()))
            return r

        def getrandbits(self, k):
            r = super().getrandbits(k)
            DRAWS.append((self._trace_label, "b", k, r, draw_site()))
            return r

    _random.Random = TRandom


def _note(which, start, end):
    if end > start:
        READS[read_site()][which].append((start, end))


_ZERO_RUN = re.compile(rb"\x00+")


class Shared:
    written = bytearray(SIZE)        # output-buffer bytes BC wrote (no longer the ROM's)


class TracedBytes(bytes):
    """A whole-ROM read's bytes: indexing and slicing record the ROM bytes read (those not written since)."""

    def __getitem__(self, i):
        if isinstance(i, slice):
            start, stop, step = i.indices(len(self))
            if step == 1 and stop > start:
                _note_unwritten(start, stop)
        elif isinstance(i, int):
            j = i if i >= 0 else len(self) + i
            if j < SIZE and not Shared.written[j]:
                _note("out", j, j + 1)
        return bytes.__getitem__(self, i)


def _note_unwritten(start, stop):
    stop = min(stop, SIZE)
    if stop <= start:
        return
    w = Shared.written[start:stop]
    if not any(w):
        _note("out", start, stop)
        return
    for m in _ZERO_RUN.finditer(bytes(w)):
        _note("out", start + m.start(), start + m.end())


def traced_byte_insert(original):
    def byte_insert(data, position, newdata, maxlength=0, end=0):
        out = original(bytes(data), position, newdata, maxlength, end)
        # what was written: newdata (cut to maxlength, or to end - position + 1) at position
        w = len(newdata)
        if end:
            maxlength = end - position + 1
        if maxlength:
            w = min(w, maxlength)
        if position < SIZE:
            Shared.written[position:min(SIZE, position + max(0, w))] = b"\1" * max(0, min(SIZE, position + w) - position)
        return TracedBytes(out)
    return byte_insert


class Traced(io.BytesIO):
    """BC's input ("in") or output ("out") buffer, recording reads."""

    def __init__(self, data, which):
        super().__init__(data)
        self.which = which

    def read(self, n=-1):
        pos = self.tell()
        data = super().read(n)
        end = pos + len(data)
        if self.which == "in":
            if len(data) >= BULK:
                _note("in", pos, end)     # (BC reads the input in tables; a big read is shown as one)
                return data
            _note("in", pos, end)
            return data
        if len(data) >= BULK:
            # a whole-ROM read: the bytes record what's used of them, not the copy itself
            READS[read_site()]["bulk"] = READS[read_site()].get("bulk", 0) + len(data)
            return TracedBytes(data) if pos == 0 else data
        _note_unwritten(pos, end)
        return data

    def write(self, b):
        pos = self.tell()
        n = super().write(b)
        if self.which == "out":
            end = min(SIZE, pos + n)
            if isinstance(b, TracedBytes) and pos == 0:
                pass            # the whole ROM written back: its byte_inserts were marked as they happened
            elif end > pos:
                Shared.written[pos:end] = b"\1" * (end - pos)
        return n


def merge(regions, gap=0):
    out = []
    for s, e in sorted(regions):
        if out and s <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


class FakeConn:
    def __init__(self, box):
        self.box = box

    def send(self, obj):
        if isinstance(obj, BaseException):
            # a child process's exception arrives pickled, without its frames: here they'd keep the failed
            # attempt's images (13,000 of them) alive through the retry
            obj.__traceback__ = obj.__context__ = obj.__cause__ = None
        self.box.append(obj)

    def poll(self, timeout=None):
        return bool(self.box)

    def recv(self):
        if not self.box:
            raise EOFError
        return self.box.pop(0)


def fake_pipe():
    box = []
    return FakeConn(box), FakeConn(box)


class FakeProcess:
    """remonsterate in this process (BC starts a child process): its reads and draws are recorded."""

    def __init__(self, target=None, args=(), kwargs=None):
        self.target, self.args, self.kwargs = target, args, kwargs or {}
        self.box = None

    def start(self):
        # a fresh remonsterate each attempt, as a child process gets (BC retries after an overflow: the
        # first attempt's palettes and sprites must not carry over)
        import importlib
        for name in [m for m in sys.modules if m == "remonsterate" or m.startswith("remonsterate.")]:
            del sys.modules[name]
        import gc
        gc.collect()
        target = getattr(importlib.import_module(self.target.__module__), self.target.__name__)
        conn = self.args[0]
        self.box = conn.box
        target(*self.args, **self.kwargs)

    def is_alive(self):
        return bool(self.box)


def record(out_dir, seed, mode, flags, romfree=False, draws_only=False):
    global _src
    os.makedirs(out_dir, exist_ok=True)
    trace_random()
    import bc_run
    _src = os.path.abspath(bc_run.SRC)
    import prdata as P
    import ff6snes as S
    if romfree:
        import bc_basedata
        rom = bc_basedata.load()
    else:
        rom = bytes(S.rom_bytes(P.VANILLA_ROM))
    calls = {"n": 0}
    original = io.BytesIO

    class Tap(io.BytesIO):
        def __new__(cls, data=b""):
            calls["n"] += 1
            if calls["n"] <= 2 and not draws_only:
                return Traced(data, "in" if calls["n"] == 1 else "out")
            return original(data)

    def prepare():
        import randomizer
        randomizer.Process, randomizer.Pipe = FakeProcess, fake_pipe
        if draws_only:
            return
        for modname in ("music.mfvitools.insertmfvi", "music.musicrandomizer", "music.jukebox", "musicinterface"):
            m = sys.modules.get(modname)
            if m is not None and hasattr(m, "byte_insert"):
                if not hasattr(m.byte_insert, "_traced"):
                    orig = sys.modules["music.mfvitools.insertmfvi"].__dict__.get("_orig_byte_insert") or m.byte_insert
                    sys.modules["music.mfvitools.insertmfvi"]._orig_byte_insert = orig
                    f = traced_byte_insert(orig)
                    f._traced = True
                    m.byte_insert = f

    bc_run.io.BytesIO = Tap
    t = time.time()
    try:
        data, spoiler = bc_run.run(rom, seed, mode, flags, say=lambda _: None, prepare=prepare, romfree=romfree)
    finally:
        bc_run.io.BytesIO = original
    secs = time.time() - t
    with open(os.path.join(out_dir, "draws.txt"), "w", encoding="utf-8") as f:
        for gen, kind, arg, res, site in DRAWS:
            f.write(f"{gen} {kind} {arg} {res} {site}\n")
    reads = {}
    for site, v in READS.items():
        r = {k: merge(v[k]) for k in ("in", "out")}
        r["n"] = sum(e - s for k in ("in", "out") for s, e in r[k])
        if v.get("bulk"):
            r["bulk"] = v["bulk"]
        reads[site] = r
    with open(os.path.join(out_dir, "reads.json"), "w", encoding="utf-8") as f:
        json.dump(dict(sorted(reads.items(), key=lambda kv: -kv[1]["n"])), f, indent=0)
    bc_run.write_output(os.path.join(out_dir, "out.bin"), data)
    with open(os.path.join(out_dir, "spoiler.txt"), "w", encoding="utf-8") as f:
        f.write(spoiler)
    with open(os.path.join(out_dir, "run.json"), "w", encoding="utf-8") as f:
        json.dump({"seed": seed, "mode": mode, "flags": flags, "romfree": romfree, "seconds": round(secs, 1),
                   "draws": len(DRAWS)}, f)
    allr = merge([tuple(x) for v in reads.values() for k in ("in", "out") for x in v[k]])
    print(f"{len(DRAWS)} draws, {sum(e - s for s, e in allr)} ROM bytes read in {len(allr)} regions by "
          f"{len(reads)} sites, {secs:.1f} s -> {out_dir}")


def load_draws(d):
    streams = collections.defaultdict(list)
    with open(os.path.join(d, "draws.txt"), encoding="utf-8") as f:
        for line in f:
            gen, kind, arg, res, site = line.rstrip("\n").split(" ", 4)
            streams[gen].append((kind, arg, res, site))
    return streams


def stages(draws):
    """The random module's draws cut at each reseed (BC's stages): [(seed line, [draws])]."""
    out = [("start", [])]
    for d in draws:
        if d[0] == "seed":
            out.append((d[2], []))
        else:
            out[-1][1].append(d)
    return out


def diff(a, b):
    sa, sb = load_draws(a), load_draws(b)
    same = True
    for gen in sorted(set(sa) & set(sb)):
        ga, gb = stages(sa[gen]), stages(sb[gen])
        if len(ga) < 3:
            continue
        bad = []
        for i, ((sda, xa), (sdb, xb)) in enumerate(zip(ga, gb)):
            j = next((j for j, (p, q) in enumerate(zip(xa, xb)) if p[:3] != q[:3]), None)
            if j is None and len(xa) == len(xb) and sda == sdb:
                continue
            j = min(len(xa), len(xb)) if j is None else j
            first = xa[j][3] if j < len(xa) else "-"
            other = xb[j][3] if j < len(xb) else "-"
            bad.append(i)
            print(f"{gen} stage {i} (seed {sda}): {len(xa)} / {len(xb)} draws, first differing #{j}: A {first} / B {other}")
        if len(ga) != len(gb):
            print(f"{gen} stages: {len(ga)} / {len(gb)}")
        print(f"{gen}: {len(ga)} stages, {len(bad)} differ")
    for gen in sorted(set(sa) | set(sb)):
        xa, xb = sa.get(gen, []), sb.get(gen, [])
        i = next((i for i, (p, q) in enumerate(zip(xa, xb)) if p[:3] != q[:3]), None)
        if i is None and len(xa) == len(xb):
            print(f"{gen}: {len(xa)} draws, the same")
            continue
        same = False
        if i is None:
            i = min(len(xa), len(xb))
        print(f"{gen}: differ at draw {i} of {len(xa)} / {len(xb)}")
        for j in range(max(0, i - 3), i + 2):
            pa = xa[j] if j < len(xa) else None
            pb = xb[j] if j < len(xb) else None
            print(f"   {j}: A {pa}\n   {' ' * len(str(j))}  B {pb}")
    return 0 if same else 1


def sites(d, least=1):
    reads = json.load(open(os.path.join(d, "reads.json"), encoding="utf-8"))
    for site, v in reads.items():
        if v["n"] < least and not v.get("bulk"):
            continue
        regs = v["in"] + v["out"]
        span = ", ".join(f"{s:06X}-{e:06X}" for s, e in regs[:6]) + (" ..." if len(regs) > 6 else "")
        print(f"{v['n']:8d} {site}{' (bulk ' + str(v['bulk']) + ')' if v.get('bulk') else ''}: {span}")


def port_trace(out, seed, preset, flags, romfree):
    """tools/bc_seed.py in this process, every ROM it reads (vanilla's, BC's output) traced by function."""
    import tempfile
    import port_trace
    import ff6snes as S
    import prdata as P
    port_trace.TracedBytes.log = collections.defaultdict(set)
    original = S.rom_bytes

    def rom_bytes(path):
        data = original(path)
        if isinstance(data, port_trace.TracedBytes):
            return data
        tb = port_trace.TracedBytes(data)
        tb.label = "vanilla" if os.path.abspath(path) == os.path.abspath(P.VANILLA_ROM) else "bc"
        return tb

    S.rom_bytes = rom_bytes
    if romfree:
        os.environ["FF6_BC_ROMFREE"] = "1"
    # BC's output as bc_seed hands it to its steps directly (bc_events, bc_sprites ...): traced too
    import bc_run
    run = bc_run.run

    def traced_run(*a, **kw):
        data, spoiler = run(*a, **kw)
        tb = port_trace.TracedBytes(data)
        tb.label = "bc"
        return tb, spoiler

    bc_run.run = traced_run
    import bc_seed
    tmp = tempfile.mkdtemp(prefix="bc_port_trace_")
    sys.argv = ["bc_seed.py", "--seed", seed, "--out", os.path.join(tmp, "seed")] +         (["--preset", preset] if preset else []) + (["--flags=" + flags] if flags else [])
    try:
        bc_seed.main()
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    res = {}
    for (lab, who), addrs in sorted(port_trace.TracedBytes.log.items()):
        regs = merge([(x, x + 1) for x in addrs], gap=16)
        res.setdefault(lab, {})[who] = {"bytes": len(addrs), "regions": [[hex(a), hex(b)] for a, b in regs]}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    for lab, mods in res.items():
        print(lab, sum(v["bytes"] for v in mods.values()), "bytes by", len(mods), "functions")


def preset_flags(name):
    """One of BC's presets (its config.SUPPORTED_PRESETS)."""
    import bc_run
    sys.path.insert(0, os.path.abspath(bc_run.SRC))
    cwd = os.getcwd()
    try:
        os.chdir(bc_run.HOME)
        import config
    finally:
        os.chdir(cwd)
    return config.SUPPORTED_PRESETS[name]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("out")
    r.add_argument("--seed", default="9859608359")
    r.add_argument("--mode", default="normal")
    r.add_argument("--preset", default="")
    r.add_argument("--flags", default="")
    r.add_argument("--romfree", action="store_true")
    r.add_argument("--draws-only", action="store_true", help="no read tracing (fast)")
    d = sub.add_parser("diff")
    d.add_argument("a")
    d.add_argument("b")
    p = sub.add_parser("port")
    p.add_argument("out")
    p.add_argument("--seed", default="9859608359")
    p.add_argument("--preset", default="")
    p.add_argument("--flags", default="")
    p.add_argument("--romfree", action="store_true")
    s = sub.add_parser("sites")
    s.add_argument("dir")
    s.add_argument("--min", type=int, default=1)
    a = ap.parse_args()
    if a.cmd == "record":
        flags = " ".join(((preset_flags(a.preset) if a.preset else "") + " " + a.flags).split())
        record(a.out, a.seed, a.mode, flags, a.romfree, a.draws_only)
    elif a.cmd == "port":
        port_trace(a.out, a.seed, a.preset, a.flags, a.romfree)
    elif a.cmd == "diff":
        raise SystemExit(diff(a.a, a.b))
    else:
        sites(a.dir, a.min)


if __name__ == "__main__":
    main()
