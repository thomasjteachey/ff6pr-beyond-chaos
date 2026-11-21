"""Beyond Chaos on this PC's game as a player installs it, for a test run (the PC test runner's): from the player
zip (kit.py package bc), with no Magicite folder, none of the game's files and no project config, so the plugin
must make them from the game at its first start (bc_gamedata.py setup) and make seeds with its bundled Python,
ROM-free. Built on tools/bc_testinstall.py (which holds BNW and WC aside and puts everything back).

  .venv/Scripts/python tools/bc_playertest.py install [ZIP]   # the game closed; ZIP: build/dist/BeyondChaos-PR*.zip
  .venv/Scripts/python tools/bc_playertest.py restore         # = bc_testinstall restore, the bundle's generator removed
  .venv/Scripts/python tools/bc_playertest.py status
"""
import glob
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
import bc_testinstall as T  # noqa: E402

LEFT_OUT = ["generator/vanilla", "generator/cache", "baseline/files", "baseline/vanilla_data"]   # = modkit.json


def latest_zip():
    found = sorted(glob.glob(os.path.join(PR, "build", "dist", "BeyondChaos-PR*.zip")), key=os.path.getmtime)
    if not found:
        raise SystemExit("no player zip in build/dist (kit.py package bc)")
    return found[-1]


def install(zip_path=None):
    zip_path = zip_path or latest_zip()
    g = T.game()
    T.install()                          # BNW/WC held aside, BC's dev layout in place: now made a player's
    data = os.path.join(g.bepinex, T.MOD)
    mg = os.path.join(g.magicite_dir, T.MOD)
    shutil.rmtree(mg, ignore_errors=True)
    for part in ("generator", "baseline"):
        shutil.rmtree(os.path.join(data, part), ignore_errors=True)
    cfg = os.path.join(g.bepinex, "config", "ff6mod.beyondchaos.cfg")
    if os.path.exists(cfg):
        os.remove(cfg)                   # no ProjectDir: the bundled generator
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.startswith("BepInEx/")]
        bad = [n for n in z.namelist() if n.lower().endswith((".sfc", ".smc"))]
        if bad:
            raise SystemExit(f"the zip has an SNES ROM: {bad[:3]}")
        for n in names:
            if n.endswith("/"):
                continue
            dest = os.path.join(g.install, *n.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(n) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    made = [p for p in LEFT_OUT if os.path.exists(os.path.join(data, *p.split("/")))]
    if made or os.path.isdir(mg):
        raise SystemExit(f"not a player's install: {made or [mg]} already there")
    print(f"installed {T.MOD} as a player's zip ({os.path.basename(zip_path)}, {len(names)} files): no Magicite folder, "
          f"no game files, no project config")


def restore():
    g = T.game()
    T.restore()
    shutil.rmtree(os.path.join(g.bepinex, T.MOD, "generator"), ignore_errors=True)
    print("the bundle's generator removed (seeds stay in BepInEx/BeyondChaos/seeds)")


def status():
    g = T.game()
    T.status()
    data = os.path.join(g.bepinex, T.MOD)
    gen = os.path.join(data, "generator")
    print(f"bundle: {os.path.exists(os.path.join(gen, 'bundle.json'))}; set up: "
          f"{os.path.exists(os.path.join(gen, 'vanilla', '.complete'))}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "install":
        install(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "restore":
        restore()
    else:
        status()
