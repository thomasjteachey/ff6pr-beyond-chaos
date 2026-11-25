"""Beyond Chaos on this PC's game as a player installs it, for a test run (the PC test runner's): from the player
zip (kit.py package bc), with no Magicite folder, none of the game's files and no project config, so the plugin
must make them from the game at its first start (bc_gamedata.py setup) and make seeds with its bundled Python,
ROM-free. Built on tools/bc_testinstall.py (which holds BNW and WC aside and puts everything back).

Inside a test batch: when the batch's own BC test install (bc_testinstall install: BC's development layout) is in
place, `install` restores it first and notes so (BepInEx/bc_playertest.json); `restore` then puts the development
install back, so the batch's later BC steps find what they expect. Nothing to do before or after it in a request.

  .venv/Scripts/python tools/bc_playertest.py install [ZIP]   # the game closed; ZIP: build/dist/BeyondChaos-PR*.zip
  .venv/Scripts/python tools/bc_playertest.py restore         # = bc_testinstall restore, the bundle's generator removed
  .venv/Scripts/python tools/bc_playertest.py status
"""
import glob
import json
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
NOTE = "bc_playertest.json"          # BepInEx/: {"dev_install_before": bool}, while a player install is in place
CFG = "ff6mod.beyondchaos.cfg"       # BepInEx/config/: the plugin's config (a dev PC's ProjectDir lives there)
CFG_KEPT = "bc_playertest.cfg"       # BepInEx/: that config as it was before the player install, put back by restore


def latest_zip():
    found = sorted(glob.glob(os.path.join(PR, "build", "dist", "BeyondChaos-PR*.zip")), key=os.path.getmtime)
    if not found:
        raise SystemExit("no player zip in build/dist (kit.py package bc)")
    return found[-1]


def install(zip_path=None):
    zip_path = zip_path or latest_zip()
    g = T.game()
    note = os.path.join(g.bepinex, NOTE)
    if os.path.exists(note):
        raise SystemExit(f"a player install is already in place ({note}): restore first")
    dev_before = os.path.exists(os.path.join(g.bepinex, T.STATE))
    # the config exactly as it is now (a player's install has none, and the plugin then writes one of its own
    # with ProjectDir empty): restore puts these bytes back, so the PC's later dev runs find their generator
    cfg_path = os.path.join(g.bepinex, "config", CFG)
    kept = os.path.join(g.bepinex, CFG_KEPT)
    if os.path.exists(cfg_path):
        shutil.copyfile(cfg_path, kept)
    elif os.path.exists(kept):
        os.remove(kept)
    if dev_before:
        print("the batch's BC test install is in place: restored first (put back by `restore`)")
        T.restore()
    with open(note, "w", encoding="utf-8") as f:
        json.dump({"dev_install_before": dev_before, "config_kept": os.path.exists(kept)}, f)
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
    note = os.path.join(g.bepinex, NOTE)
    dev_before = False
    if os.path.exists(note):
        try:
            dev_before = bool(json.load(open(note, encoding="utf-8")).get("dev_install_before"))
        except (OSError, ValueError):
            pass
    T.restore()
    shutil.rmtree(os.path.join(g.bepinex, T.MOD, "generator"), ignore_errors=True)
    print("the bundle's generator removed (seeds stay in BepInEx/BeyondChaos/seeds)")
    # the config byte for byte as before the player install (or none, if there was none)
    cfg_path = os.path.join(g.bepinex, "config", CFG)
    kept = os.path.join(g.bepinex, CFG_KEPT)
    if os.path.exists(kept):
        os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
        shutil.copyfile(kept, cfg_path)
        os.remove(kept)
        print(f"config put back as it was ({CFG})")
    elif os.path.exists(note) and os.path.exists(cfg_path):
        os.remove(cfg_path)
        print(f"config removed: there was none before the player install ({CFG})")
    if os.path.exists(note):
        os.remove(note)
    if dev_before:
        T.install()
        print("the batch's BC test install put back, as it was before the player install")


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
