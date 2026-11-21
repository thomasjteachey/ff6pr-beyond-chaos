"""Beyond Chaos's art and samples from other games: in the player's zip (as BC's own downloads carry them), or
fetched on the player's machine from BC's GitHub releases, the same packs BC's own updater installs. One
setting: generator/bc_assets.json "source" ("bundle" | "release"), written by tools/bc_bundle.py (ASSETS).

The packs are pinned (a seed's draws depend on which sprites and images there are: makeover's list,
remonsterate's images_and_tags.txt), and every file is checked against the build's sha1 list:

  character sprites  FF6BeyondChaos/BeyondChaosSprites 3.8          -> bc_home/custom (sprites/, lists)
  monster images     FF6BeyondChaos/BeyondChaosMonsterSprites 3.1   -> bc_home/remonsterate
  opera              BC's release CE-6.1.3 (BeyondChaos.zip)         -> bc_home/custom/opera
  music samples      BC's source at 27de07a (music/samples)         -> bc/music/samples

  python tools/bc_assets.py status|fetch [GEN]     (GEN: the generator folder; default: this file's parent)

tools/bc_seed.py calls ensure() before BC runs (a "release" install fetches once, the first seed).
"""
import hashlib
import io
import json
import os
import shutil
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.dirname(HERE)
CONFIG = "bc_assets.json"
API = "https://api.github.com/repos/FF6BeyondChaos/"
PACKS = [
    # name, where it lands (generator-relative), how to get the zip, the zip's folder to take (None: its root)
    ("character sprites", "bc_home/custom", ("release", "BeyondChaosSprites", "3.8"), None),
    ("monster images", "bc_home/remonsterate", ("release", "BeyondChaosMonsterSprites", "3.1"), None),
    ("opera", "bc_home/custom/opera", ("release", "BeyondChaosRandomizer", "CE-6.1.3"), "custom/opera"),
    ("music samples", "bc/music/samples",
     ("archive", "BeyondChaosRandomizer", "27de07a012640ed297b36f94e81bdd8128f3c3b1"), "BeyondChaos/music/samples"),
]


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest(gen, roots):
    """{generator-relative path: sha1} of every file under roots (the build, before they're left out)."""
    out = {}
    for root in roots:
        top = os.path.join(gen, *root.split("/"))
        if os.path.isfile(top):
            out[root] = _sha1(top)
            continue
        for r, _, fs in os.walk(top):
            for f in fs:
                p = os.path.join(r, f)
                out[os.path.relpath(p, gen).replace("\\", "/")] = _sha1(p)
    return dict(sorted(out.items()))


def config(gen=GEN):
    try:
        with open(os.path.join(gen, CONFIG), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"source": "bundle"}


def missing(gen=GEN):
    cfg = config(gen)
    return [rel for rel, sha in cfg.get("files", {}).items()
            if not os.path.exists(os.path.join(gen, *rel.split("/"))) or _sha1(os.path.join(gen, *rel.split("/"))) != sha]


def _get(url, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": "ff6pr-beyond-chaos", **({"Accept": accept} if accept else {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def _zip_for(kind, repo, ref):
    mirror = os.environ.get("FF6_BC_ASSETS_MIRROR")      # tests: a folder of <repo>-<ref>.zip
    if mirror:
        with open(os.path.join(mirror, f"{repo}-{ref}.zip"), "rb") as f:
            return f.read()
    if kind == "archive":
        return _get(f"https://github.com/FF6BeyondChaos/{repo}/archive/{ref}.zip")
    rel = json.loads(_get(API + f"{repo}/releases/tags/{ref}", "application/vnd.github+json"))
    asset = next(a for a in rel["assets"] if a["name"].lower().endswith(".zip"))
    return _get(asset["browser_download_url"])


def fetch(gen=GEN, say=print):
    """Each pack that has a missing or changed file: downloaded, its files put in place, every file checked."""
    cfg = config(gen)
    want = cfg.get("files", {})
    for name, dest, (kind, repo, ref), folder in PACKS:
        mine = {rel: sha for rel, sha in want.items() if rel.startswith(dest + "/")}
        if not mine or not [rel for rel in mine if rel in missing(gen)]:
            continue
        say(f"fetching Beyond Chaos's {name} ({repo} {ref[:12]}), once")
        z = zipfile.ZipFile(io.BytesIO(_zip_for(kind, repo, ref)))
        names = z.namelist()
        top = os.path.commonprefix([n for n in names if "/" in n]).split("/")[0] + "/" if kind == "archive" else ""
        prefix = top + (folder + "/" if folder else "")
        for n in names:
            if n.endswith("/") or not n.startswith(prefix):
                continue
            rel = dest + "/" + n[len(prefix):]
            if rel not in mine:
                continue
            path = os.path.join(gen, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with z.open(n) as src, open(path, "wb") as out:
                shutil.copyfileobj(src, out)
    bad = missing(gen)
    if bad:
        raise SystemExit(f"Beyond Chaos's art: {len(bad)} files missing or different after fetching: {bad[:5]}")


def ensure(gen=GEN, say=print):
    """Before BC runs: a "release" install fetches what's missing; a "bundle" one has it all."""
    if config(gen).get("source") == "release" and missing(gen):
        fetch(gen, say)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    gen = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else GEN
    if cmd == "fetch":
        fetch(gen)
    m = missing(gen)
    print(f"source {config(gen).get('source')}: " + (f"{len(m)} files missing" if m else "all in place"))
    sys.exit(1 if m else 0)
