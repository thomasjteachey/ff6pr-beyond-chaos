"""Put Beyond Chaos on this PC's game for a test run, and take it off again exactly.

  .venv/Scripts/python tools/bc_testinstall.py install   # the game closed
  .venv/Scripts/python tools/bc_testinstall.py restore   # back as it was; BC to the shelf
  .venv/Scripts/python tools/bc_testinstall.py status

tools/deploy.sh switches Brave New World and Worlds Collide and knows no third game-data mod, so a
Beyond Chaos install left in place would load beside whichever mod deploy.sh installs next. This
script sets the active game-data mods aside in a holding folder of its own (BepInEx/bc-test-held,
recorded in BepInEx/bc_testinstall.json), installs BC (plugin, bc_flags.json, its data folder's
baseline, its Magicite folder, a dev config pointing the generator at this project), and `restore`
moves BC to the shelf in deploy.sh's layout (BepInEx/mod-shelf/BeyondChaos, mod-shelf/magicite/
BeyondChaos: nothing loads there) and the held mods back. BC's seeds stay in BepInEx/BeyondChaos.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.dirname(HERE)
PROJECT = os.path.dirname(PR)
sys.path.insert(0, HERE)
import kitpath  # noqa: E402,F401
from prkit import games  # noqa: E402

MOD = "BeyondChaos"
OTHERS = ["BraveNewWorld", "WorldsCollide"]       # the game-data mods deploy.sh switches
STATE = "bc_testinstall.json"
HELD = "bc-test-held"
DLL = os.path.join(PR, "plugin", "BcPlugin", "bin", "Release", "net6.0", "BeyondChaos.PR.dll")
FLAGS = os.path.join(PR, "plugin", "BcPlugin", "bc_flags.json")
BUILD = os.path.join(PR, "build", "BeyondChaos")
CONFIG = """[Generator]

## The ff6-mod project folder, for a development PC without the bundle.
# Setting type: String
# Default value:
ProjectDir = {project}

"""


def game():
    g = games.get("ff6")
    if not g.installed:
        raise SystemExit("FF6 PR isn't installed")
    return g


def move(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        raise SystemExit(f"{dst} is already there: not moving {src} over it")
    shutil.move(src, dst)
    print(f"  {src} -> {dst}")


def mirror(src, dst):
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)


def install():
    g = game()
    if g.running():
        raise SystemExit("the game is running: close it (or wait for the other session's run)")
    state_path = os.path.join(g.bepinex, STATE)
    if os.path.exists(state_path):
        raise SystemExit(f"already installed for a test ({state_path}): restore first")
    held = os.path.join(g.bepinex, HELD)
    state = {"held": []}
    for name in OTHERS:
        for kind, path in (("plugin", os.path.join(g.plugins_dir, name)), ("magicite", os.path.join(g.magicite_dir, name))):
            if os.path.isdir(path):
                dst = os.path.join(held, kind, name)
                move(path, dst)
                state["held"].append([path, dst])
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    plugin = os.path.join(g.plugins_dir, MOD)
    shelved = os.path.join(g.shelf_dir, MOD)
    if not os.path.isdir(plugin) and os.path.isdir(shelved):
        move(shelved, plugin)
    os.makedirs(plugin, exist_ok=True)
    shutil.copy2(DLL, plugin)
    shutil.copy2(FLAGS, plugin)
    data = os.path.join(g.bepinex, MOD)
    os.makedirs(data, exist_ok=True)
    mirror(os.path.join(BUILD, "plugin", "baseline"), os.path.join(data, "baseline"))
    shelved_mg = os.path.join(g.shelf_dir, "magicite", MOD)
    if os.path.isdir(shelved_mg):
        shutil.rmtree(shelved_mg)
    mirror(os.path.join(BUILD, "magicite", MOD), os.path.join(g.magicite_dir, MOD))
    cfg = os.path.join(g.bepinex, "config", "ff6mod.beyondchaos.cfg")
    if not os.path.exists(cfg):
        with open(cfg, "w", encoding="utf-8") as f:
            f.write(CONFIG.format(project=PROJECT))
    print(f"installed {MOD} for a test; {len(state['held'])} folders held in {held}")


def restore():
    g = game()
    if g.running():
        raise SystemExit("the game is running: wait for it to close")
    state_path = os.path.join(g.bepinex, STATE)
    if not os.path.exists(state_path):
        raise SystemExit("not installed for a test (no state file)")
    state = json.load(open(state_path, encoding="utf-8"))
    plugin = os.path.join(g.plugins_dir, MOD)
    if os.path.isdir(plugin):
        dst = os.path.join(g.shelf_dir, MOD)
        shutil.rmtree(dst, ignore_errors=True)
        move(plugin, dst)
    mg = os.path.join(g.magicite_dir, MOD)
    if os.path.isdir(mg):
        dst = os.path.join(g.shelf_dir, "magicite", MOD)
        shutil.rmtree(dst, ignore_errors=True)
        move(mg, dst)
    for original, held in state["held"]:
        move(held, original)
    os.remove(state_path)
    print(f"restored: {MOD} on the shelf, {len(state['held'])} folders back")


def status():
    g = game()
    print(f"game running: {g.running()}")
    print(f"BC plugin: {os.path.isdir(os.path.join(g.plugins_dir, MOD))}; BC Magicite: {os.path.isdir(os.path.join(g.magicite_dir, MOD))}")
    for name in OTHERS:
        print(f"{name}: plugin {os.path.isdir(os.path.join(g.plugins_dir, name))}, Magicite {os.path.isdir(os.path.join(g.magicite_dir, name))}")
    print(f"test install state: {os.path.exists(os.path.join(g.bepinex, STATE))}")


if __name__ == "__main__":
    {"install": install, "restore": restore, "status": status}.get(sys.argv[1] if len(sys.argv) > 1 else "status", status)()
