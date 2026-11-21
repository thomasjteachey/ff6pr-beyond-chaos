# Beyond Chaos on the Pixel Remaster

Owner: BC lead. Moved verbatim from `pr/PORTING.md` on 2026-11-20 (roadmap item 5); `git log --follow` / the split commit trace any paragraph. Status rows stay in `pr/PORTING.md`.

## Status

**By the source audit (2026-11-21, pr/docs/bc-audit.md section 5): each area's figure below is its audited
features (tested 1, ported 0.8, partial 0.4, missing 0); feature-weighted the port is 57.7%. Earlier figures were
estimates.**

**Beyond Chaos, weighted** (2026-11-20, a mod of its own on the kit and WC's base; plan in
"Beyond Chaos port" below; Normal mode first, the cave modes and `d` later. Re-measured the same day by
the BC lead against every flag in `plugin/BcPlugin/bc_flags.json` (20 yes, 11 partly, 82 no, 2 n/a): rows
added for BC's junction effects and the cave modes, more events counted; owners are the BC child sessions):

| Area | Weight | Done | Points | Owner |
|---|---|---|---|---|
| Seeds in game: options screen (BC's flags, codes and modes), generator (BC's own code, ROM-free, a seed = BC's exe's), live apply, saves keep their seed (2026-11-20: all but ROM-free and the player's bundle; checked headless in game) | 15 | 67% | 10.05 | bc-seeds |
| Randomized data through the porter: characters, commands, espers, items, shops, chests, monsters, formations, encounters, Colosseum, Slots, dances, MagiTek; left: the partly-ported data flags (b, g, i, o, t, bsiab), y, alphalores, cursepower, dancingmaduin, fightclub, and WC's plugin features BC's data needs (natural magic, esper bonuses, Coliseum, rages, steal) moved into the kit | 25 | 63% | 15.75 | bc-seeds |
| Custom commands (`w`): R-/W-/X-/9x commands, combos, R-Limit, R-Chaos, allcombos, nocombos, endless9, replaceeverything, metronome, suplexwrecks, desperation (2026-11-20: all as PR command rows, random ones on the PR's random-ability function, Random Ice seen working in a battle; repeats and combos in the plugin, their battle test pending) | 12 | 82% | 9.84 | bc-battle |
| Item specials: procs, breaks, relic bits; MBlock; collateraldamage, electricboogaloo, nobreaks, unbreakable, masseffect, darkworld (2026-11-20: the porter carries BC's weapon effects; each "?" item's description says what changed; left: MBlock, 7 armor procs, 3 relic bits, the break codes) | 6 | 57% | 3.42 | bc-battle |
| Names and explanations in the PR's own words (no SNES abbreviations; 2026-11-20: items, skills and commands in the PR's words, all fitting the game's boxes; a per-seed guide for newcomers, on the BC screen and in game right after the opening's controls tutorial (`BcGuide.cs`: sc_bc_guide on Map_20010 when the field help closes; the game's message window, a Yes/No question then a page a topic); built and offline-tested, its in-game check queued: bc-guide-1; BC's new character names through the porter's new `character_names` option (port_names.port_character_names: MSG_CHAR_NAME_01..14; New Player renames all 14: Terra is "Kei"), its monster names through `monster_names`, both switched on in bc_seed.py by bc-seeds; a "Who's who" guide page ("Kei is Terra (looks like ...)"); left: the Coral key item's rename) | 4 | 24% | 0.96 | BC lead |
| About 30 small codes that are plugin code (swdtechspeed, norng, playsitself, dearestmolulu, levelcap, mementomori, naturalstats, supernatural, informativemiss, magicnumbers, mpparty, equipanything, espercutegf, l, u, ...) (2026-11-20: the boosts (data), dancelessons, esper bonuses for `e`) | 8 | 64% | 5.12 | bc-battle |
| Junction effects: espffect, effectmas, effectory, effectster, treaffect, jejentojori (BC's `bcg_junction.py`, ~57 SNES assembly patches, each a battle effect, as plugin code) | 8 | 40% | 3.2 | bc-junction |
| Light events: worringtriad, r, h, notawaiter, lessfanatical, regionofdoom, mimetime, rushforpower, airship, shadowstays, j, k (+ alasdraco's text) | 8 | 66% | 5.28 | bc-events |
| Sprites: makeover (characters, its sprite categories, cloneparty, partyparty, quikdraw, kupokupo, bravenudeworld), remonsterate (monsters), palettes (c, p, n), s | 10 | 73% | 7.3 | BC lead (bc-sprites done; in game 11-21) |
| Music: johnnydmad, johnnyachaotic (an SNES sound chip and FF6's driver in the plugin, streamed over the game's track); alasdraco (the opera) later | 10 | 90% | 9 | BC lead (bc-music done) |
| Testing and release (2026-11-20: offline tests, headless runs through the PC test runner; the player's bundle and zip by bc-seeds (2026-11-20: bundled Python, generator/bundle.json, a player install set up in 9.7 s; its in-game check bc-player-1 queued); left: PC + Deck installs, a playthrough of a seed, the release) | 4 | 50% | 2 | BC lead |
| Other modes: ancientcave, speedcave, racecave (BC's `ancient.py`), `d` (random final dungeon, `towerrandomizer.py`, with morefanatical, which BC applies only inside `d`'s tower remap), strangejourney (entrances); scoped 2026-11-20: all three reuse vanilla room layouts (no new map art): strangejourney rewires the PR's own exits (small), `d` clones ~23 rooms into spare map ids and rewires them (medium), the cave modes do that for 300/85/50 rooms plus rest stops and new start/end scripts (largest); order strangejourney, `d`, caves (plan: the lead's notes, bc-lead.md) | 12 | 5% | 0.6 | BC lead (a bc-modes session when RAM allows) |
| Divergent paths (thescenarionottaken: PowerPanda's scenario, BC's `tables/divergentedits.txt`: 549 writes, ~504 KB: 144 dialogue lines rewritten, NPC/event tables, ~9 KB of event code, ~303 KB of repacked map tilemaps, the World of Balance map and exits; Terra + Banon via Baren Falls and the Veldt, Sabin + Edgar via Doma and the Phantom Train, Locke + Celes straight to Narshe; needs the kit's snes_rooms/snes_maps for its layouts) | 8 | 0% | 0 | BC lead (later, its own session) |
| **Total** (weighted: points / 130 weights) | **130** | | **72.52 = ~56%** | |

## Live progress (newest first)

- 2026-11-21 11:45 (BC lead): source audit (pr/docs/bc-audit.md: 149 BC features vs BC CE 6.1.3; 17 tested in game,
  63 ported, 32 partial, 24 missing, 3 left out, 10 n/a): 57.7% by feature, ~56% by area (table above, dashboard
  rows set from it; was a ~77% estimate). 0.1.0 held for: techniques following shuffled commands (subagent),
  bingoboingo crashing generation, stale bc_flags statuses, Dance/Rage menu text (bc-seeds); plus bc-8, guide-2b,
  bc-9. The audit's section 3 is the work list.
- 2026-11-21 10:45 (BC lead): bc-7 (the 0.1.0 gate: the player bundle's own generator, startup 0 failed, 164/164
  rows, 555/555 files, data self-tests 4/0) passed; zip being rebuilt from main. bc-art-2b PASS: sprites done
  (100%; bc-sprites' section moved in below). bc-guide-2 failed on the harness (bcgen 2 s before startup was done):
  rerun bc-guide-2b. The kit's next map table (staged2: 19 lookalikes now door pairs) changes no area song and no
  entrance's first choice: OK'd. ~77%.
- 2026-11-21 10:05 (BC lead): strangejourney's per-world doors in the plugin (BcEntrances.cs, BcDoorRules.cs): a
  prefix on EventProcedure.EventGotoMap points a shared door's map change at the World of Balance or World of Ruin
  target from bc_doors.json (kScenarioFlag2 bit 41), only on the door's own map, for its vanilla target, with the
  party within a tile of it; `bcdoors` for tests. Seed 1234567890: all 55 per-world doors resolve. BcBattle.Tests
  60/60. In-game check bc-doors sent to QA (Narshe door #51 both ways). Story-version splits (~119) stay as the
  seed files set them (index pairing work).
- 2026-11-21 09:50 (BC lead): the kit's table marks lookalikes (another place's room by tiles alone, 537 of 1338
  rows); bc_music and bc_entrances skip them. The SNES song 0 rooms (keep what plays: Mobliz's houses keep BC's
  town song) now inherit their area's song through the PR door graph (inherit_kept: a room that names its track
  again, its real SNES pairs all keeping the song), which the lookalikes had covered by accident. Seed 1234567890: 87
  PR maps with BC area songs, each from a real pair or inherited. Entrance index: same coverage, 22 rooms more by
  doors. make_seed runs BC in a child process when BC already ran in the process (BC keeps module state; the
  parity test ran first). BC Python tests 128 OK (parity forced). bc-5's commands pass voided by QA (no-script
  battle, harness fixed by the kit lead): rerun bc-10.
- 2026-11-21 09:25 (BC lead): bc-5's in-game self-tests (junction 8/24, battle 12/8) traced to the checks themselves:
  junction `start` left Plague's Doom on every monster (the battle was won mid-run; 21 checks ran on the victory
  screen, IsBattle() stays true there), bckeep's HP 9999 top-up undid the heal/fall checks, and the battle run's
  fight was won 2 s in (no battle script running: the game's end judgment). Checks now clean up, drive and read
  only their own acts, see a finished battle; bcselftest holds the end judgment while it runs (test-only). Landed
  (wt/bc-selftest3); BcBattle.Tests 30/30, BcJunction.Tests 51/51. Rerun bc-8 on the PC after bc-7 (the 0.1.0
  gate). bc_live's baseline carries strangejourney's 334 files (bc-seeds; bundle ROM-free seed 40 s). Next: the
  plugin's world-door redirect (55 doors).
- 2026-11-21 09:00 (BC lead): on the kit's new map table (world/cross per pair, 1338 pairs): area songs rank a
  shared PR map's pairs by how they were found (manual, chests/exits, doors, tiles, layout), then coverage; a
  cross-world pair drops only when a same-world pair found structurally is as sure. Seed 1234567890: 96 maps; World
  of Ruin Mobliz (and its interiors) and Kohlingen no longer take the World of Balance town's BC song (BC changed
  only those), Figaro Castle's World of Balance basement keeps BC's basement song (its SNES rooms read as World of
  Ruin only by the cave). bc_entrances now uses the kit's door tools (snes_maps.PrDoors, grow_doors, world_labels:
  its own pass, lifted into the kit); the rebuilt index is identical. BC Python tests 119 OK.
- 2026-11-21 08:35 (BC lead): strangejourney's seed step landed (tools/bc_entrances.py apply, in bc_seed.py after
  bc_events): BC's shuffled short entrances on the PR's doors. Seed 1234567890: 666 of 951 new destinations rewired
  through 804 door objects (0 set two ways), 5 new arrival points, ~386 map files; out/bc_doors.json lists the 285
  not rewired (with reasons) and 174 doors several versions share (55 by world: the plugin redirects them by the
  World of Ruin flag, next; ~119 by story version: mostly an index pairing problem, Doma vs Cyan's Dream, the tower,
  South Figaro Cave, to fix on the kit's new world tags). Index rebuilt on main's snes_maps; test_bc_entrances 19/19.
  Pending: bc_live's baseline (bc-seeds), the plugin redirect, an in-game run. Cave modes, `d`, divergent: not started.
- 2026-11-21 08:10 (BC lead): area songs (tools/bc_music.py): a PR map two SNES maps share plays the surer pair's
  song (hand-confirmed, then coverage), not whichever SNES map comes first; a pair across worlds (snes_maps' new
  `cross` tag) counts only when the PR map has no pair of its own world; the pairs now come from snes_maps.table(),
  so the hand-confirmed overrides give 6 more PR maps BC's songs (seed 1234567890: 81 maps, was 75; no song
  changed on the 75). The bundle's compact copy carries cross/manual/coverage. tests/test_bc_music.py (8).
  bc-sprites archived (done; bc-art-2b in bc-6 decides bc-08).
- 2026-11-21 (BC lead): public repo github.com/thomasjteachey/ff6pr-beyond-chaos created and first pushed (tools/bc_publish.py:
  BC's plugin and test projects, tools/bc_*.py, data/bc_*.json, tests, this doc; the kit and Beyond Chaos at 27de07a as
  submodules; no ROM, bc_base.bin or release assets). bc-junction's clock hooks landed on the kit's new timing core
  (Time Font/Sink, Miasma, Regenerator, Juggernaut/Burst; BcJunction.Tests 51/51): all 173 junction effects are in.
  WcTest turn_cycle counts turns from the first gauge filled while recording. ~71%.

## Beyond Chaos port (2026-11-20; the user: "i don't want to skip the sprites and music")

Beyond Chaos (CE 6.1.3, MIT, github.com/FF6BeyondChaos/BeyondChaosRandomizer) as a mod of its own,
played like WC: seeds and flags chosen in the game, made in seconds, applied without a restart.
Normal mode first; ancientcave / speedcave / racecave and `d` (random final dungeon) later.
Separate from WC and BNW (own plugin `plugin/BcPlugin`, own Magicite folder `BeyondChaos`, own data
folder `BepInEx/BeyondChaos`, own saves `ModSaves "BeyondChaos"`, own repo pinned to the kit).

- **Source** (2026-11-20): `mods/beyond-chaos/src` = BC's git at commit 27de07a (main, "Update
  version to 6.1.3"; the tag CE-6.1.3 is on an earlier commit that lacks four of the release's
  fixes; the exe in `mods/beyond-chaos/CE-6.1.3` ships no Python). Run as the exe runs it
  (`sys._MEIPASS` = the source, the working folder holding `custom/` and `remonsterate/` from the
  release; `tools/bc_run.py`, BC's web mode on buffers): the New Player seed 9859608359 = the exe's
  ROM byte for byte, 14-16 s on the PC with the ROM. **A seed number gives BC's exe's game**: BC
  reseeds (`seed + counter`) before each stage, so a ROM-free stand-in only has to keep its own
  stage's draws.
- **Generator** (`tools/bc_run.py`, `bc_seed.py`): BC's `randomize()` in process on buffers, then
  the shared porter, into a seed folder of full tables + text + changed files (as `wc_seed.py`,
  `wc_live.py`). ROM-free next (as WC: `bc_basedata.py` traces what BC reads, ships the ROM's
  data tables only; graphics/text/maps/code BC only rewrites get stand-ins).
- **Kit first**: the seed system (flag model, options screen, generator runner, seed library
  with live apply and save hooks, data folder, title-menu entry, pad input) and the SNES-parity
  battle code BC needs as-is (ATB, status ticks/clock, autobattle, encounters, the Veldt) move
  from `plugin/WcPlugin` into `plugin/PrKit`, opt-in per plugin, WC switched over and kept green.
  Shared features (natural magic, skills following commands, esper bonuses, Colosseum, rages,
  steal, exp/gp/mp boosts) after.
- **New**: custom commands (`w`; BC writes them in assembly, here plugin code); item specials;
  ~30 codes (nicerpoison, slowerbg don't apply); light events (worringtriad, r, notawaiter,
  lessfanatical, regionofdoom, mimetime, thescenarionottaken, j, k).
- **Names**: no SNES abbreviations ("R-Ice", "CleanSw", "BehemothSui?"): BC's naming code is
  patched at seed time to give full names in the PR's words (its spell, item, esper and monster
  names; "Random Ice", "Clean Sweep"), limited by each window's pixel width (proportional font;
  the PR's own translations fit 11-13 characters in the battle command window), not a count.
- **Sprites** (`makeover`: ~670 SNES 4bpp sheets + 40x40 portraits + palettes -> the PR's 32x32
  field/battle frames and 40x40 portraits at seed time; also gives WC custom sprites),
  **monsters** (`remonsterate`: 13,418 PNGs swapped in through a plugin hook), **palettes** (`c`,
  `p`, `n`: recolouring the PR's RGBA art, built in the kit for BNW's ~220 recolours too).
- **Music** (`johnnydmad`: ~380 MML songs, ~500 BRR samples): FF6's SNES sound driver can't ship,
  so the plugin emulates the SNES sound chip and re-implements the driver from the community
  disassembly, streaming songs in place of the game's track (fades, battle music, resuming
  after a fight, the volume setting). FF6's own songs in BC's shuffle use the PR's `.mab` files.
  Checked against `tools/snes_harness.py` on the same seed. Opera (`alasdraco`) later.
- **Ask before releasing**: the sprites, monster images and samples are from other games (BC
  ships them openly): ship them in the zip, or fetch BC's release on the player's machine?

Done 2026-11-20 (the first stretch):
- **The kit's seed system** (`plugin/PrKit/Seeds`, opt-in `<PrKitSeeds>true</PrKitSeeds>`, namespace
  `PrKit.Seeds`): `Flags.cs` (WC's flag model, now also BC's `name:value` style, special values like
  "random", conflicts, requirements, child rows, modes), `SeedLibrary.cs` (seeds on disk, live apply with
  file swaps and cache eviction, the startup apply, the save/load hooks that keep each save's seed; a
  mod's own rules as callbacks), `SeedGenerator.cs`, `SeedScreen.cs` (the options screen; a mod
  subclasses it), `PadInput.cs`, `TitleMenuEntry.cs`, `ModDataDir.cs`, `ChestBattles.cs` (chests a seed
  made monster boxes). Python: `tools/seed_live.py` (managed tables/files, the baseline) and
  `seed_info.py` (Coliseum, esper bonuses, Runic/Bushido weapons, MagiTek, monster chests), with
  `wc_live.py` / `wc_seed.py` on them. **WC on it**: WcFlags.cs moved to the kit; WcSeeds, WcGenerator,
  WcInput, WcTitleMenu and WcDataDir are facades over the kit's classes (same names, same logs);
  WcScreen (with the Track pages) stays WC's until it moves onto SeedScreen. Checked: WC's baseline and a
  Moogle Cup seed byte-identical before/after, Wc.Tests 416 strings identical, and the BNW
  coordinator's headless WC run on the refactored plugin: 0 failures (seed made in game and applied,
  New Game checks). **The SNES battle rules too** (same day): `PrKit/Ff6/SnesAtb.cs` (ATB fill, command
  waits, Jump's air time), `SnesStatusTicks.cs` + `SnesStatusClock.cs` (Regen/Sap/Poison on the SNES's
  clock, the status timers), `SnesAutobattle.cs` (auto-battle with commands the PR knows only as an
  accessory's), moved by name from WC's WcAtb/WcStatusTicks/WcStatusClock/WcAutobattle; each has `On`,
  `Testing`, `Tag` and perf hooks a mod sets (WC: `WcParity.cs`; BC: on in a BC game with a seed).
  WC builds, Wc.Tests identical. Headless on the kit's code (PC test runner): status_ticks passes (Regen and
  Sap every 8.519 s, Poison every 17.039 s, Haste's Regen 6.39-6.92 s, Poison ticking mid-Jump, nothing
  while stopped); atb's rates all = the SNES's, its 2.5 s "real fill" read 0.84 of real time on a busy PC
  (it divided by real seconds; the gauge fills by game time: the check now uses game time, rerun pending);
  turn_cycle, status_timers, mug_auto, snes_rules queued (WcTest runs one check per launch). Left WC's: WcEncounters (WC's vanilla tables; BC will read its
  rates from its ROM as BNW does, `port_encounter_rates.py`), WcVeldt (BC's Veldt table already lists
  every copy of a formation: port_veldt), and the shared features (natural magic, esper bonuses,
  Coliseum, rages, steal, exp/gp/mp boosts): BC needs those next.
- **Generator**: `tools/bc_run.py` (BC on buffers, web mode with the console's two path globals set),
  `bc_seed.py` (`--seed --mode --flags --preset --out [--keep-port]`; ~20 s on the PC, 16 of them BC),
  `bc_live.py` (BC's baseline: the shared one plus the Veldt's misc asset, which BC's formations
  change), `bc_bundle.py` (Magicite folder + baseline; no player bundle yet), `bc_flags_export.py`
  (115 flags, 10 sections, 6 modes, 7 presets; labels in the PR's words, a port status per flag). The
  porter's `PR_SEED_LIVE=1` (port_chests.live_seed): a live seed adds no files, so chests a seed made
  monster boxes are left to the plugin (`seed_info.monster_chests`, 21 in the test seed).
- **Plugin** `plugin/BcPlugin` (BeyondChaos.PR 0.1.0): the title menu's "Beyond Chaos" entry, the
  options screen (Mode row, numeric seeds as BC's, mode-forbidden flags dimmed), seeds made in game and
  applied live, saves keep their seed (own save files: ModSaves "BeyondChaos"), monster-box chests,
  monsters on BC's own SNES AI (the kit's SnesAiHost), harness commands `bc`, `bcgen`, `bcapply`,
  `bccheck`, `bcscreen`. Headless run (2026-11-20, `tools/bc_testinstall.py install|restore` around it:
  deploy.sh knows no third game-data mod, so BC goes back to the shelf after a test): seed 9859608359
  made in game in 26 s and applied live (18,253 rows in 21 tables, 0 failed, 2,413 texts, 473 files;
  164/164 sampled rows and every file match), vanilla and back, the screen's self-test (11 pages, 112
  rows, 560 steps) and controller flow, no exceptions, saves blocked. Not run yet: a BC battle.
- **Names** (`tools/pr_names.py`, in the porter for items and skills): a changed SNES name that is the
  same thing's SNES name (perhaps cut short, perhaps with BC's "?") gets the PR's name: "BehemothSui?"
  -> "Behemoth Suit?", "Titanium?" -> "Saucer?", "Fire Knuckl?" -> "Burning Fist?"; BC's Bushido names in
  the skill table's spare slots are no longer taken for renames (Fang stays Fang). A name of BC's own
  (Raiden, its monster names) stays. Commands get theirs with the custom commands (BC's meaning of each
  is recorded at seed time; widths measured in game with the game's font: its font bundles are
  obfuscated with a fixed keystream, so offline metrics aren't available).
- **BC's commands** (`tools/bc_commands.py`, `plugin/BcPlugin/BcCommands.cs`): BC's command maker is
  wrapped where it names each command (`CommandBlock.newname`: no draws, the ROM stays the exe's) to
  record what each does; each becomes the PR command row of its slot (BC replaces a command for
  everyone who has it): one skill = a direct command running that ability (as Pray or Shock: no
  submenu, no MP); a random skill = a new ability on the PR's own random-ability function (46, as
  Bar-Bar-Bar) with a new random group carrying BC's odds; N times / chain / combo = the first act from
  the row, the rest queued by the plugin as copies of the player's act (`BattleActExection.
  SetBattleActData`; a combo's second act gets skill B). Names in the PR's words: the test seed's are
  Random Dance, Chain Valigarmanda, Magitek Laser + Carbuncle, Tsunami (BC's CleanSw), Arise +
  Cyclonic, Random Magic, Libra (Scan), Random Ice. Widths: harness `textwidth` measures with the
  game's own fonts, `tools/bc_names.py` compares each BC name with the widest name the game shows in
  that list in any of its Latin-script languages. Harness `bccommands`, `bckeep`, `bcuse SLOT CMD` for
  battle checks. In game (PC test runner, 2026-11-20): all 8 rows as written (`bccommands`, no mismatch);
  Random Ice used in the opening battle: its ability 7732 (function 46) rolled Absolute Zero (324), which
  then hit. Repeats and combos: rerun pending (the first battle's monsters died before them). BC's command
  targeting variants (self, random, everyone) aren't carried (the ability's own targeting is used).
  Widths: the battle command list's boxes are 256 px at size 32 with best fit (the game's menus shrink a
  longer text instead of cutting it; even its own French skill names overflow their 215 px box): every
  name of the test seed fits but Magitek Laser + Carbuncle, shown at 88% (`bc_names.py report`).
- **ROM-free** (2026-11-20, bc-seeds): a seed is made with no SNES ROM, = BeyondChaos.exe's. Tools:
  `tools/bc_trace.py` (record: every random draw, by generator and line, and every ROM byte BC reads, by
  the BC function that read it; whole-ROM copies apart; `diff` stage by stage; `port`: what our porter and
  post-steps read of both ROMs), `bc_basedata.py` (the shipped data, `data/bc_base.bin`, by category),
  `bc_romfree.py` (stand-ins), `bc_parity.py` (a seed made on the ROM and ROM-free, folders compared);
  `bc_seed.py` runs ROM-free wherever there's no ROM (FF6_BC_ROMFREE=1/0 forces it).
  - What BC reads: 330-370 KB per seed of 82,000-186,000 draws (New Player, Intermediate, Advanced,
    Chaotic presets traced; 44 reseeded stages each, plus remonsterate's own generator). The earlier
    "whole ROM" was johnnydmad's and the opera's `fout.read()`, the checksum and the bank-00 mirrors: copies.
  - Not needed for a single draw (stand-ins, all four presets, every draw equal): character sprites and
    portraits (makeover copies them), dialogue, location names, the sound program (johnnydmad checks 16
    bytes of it: BC's own constant put in place), the opening (its transformers re-run; the Magitek
    palette only through its 32 bytes' brightness classes), game code BC's patches check (validation
    not enforced, as BC's noverify patches; remonsterate's own in its child process too).
  - Needed and shipped (215.9 KB, 96.5 KB compressed): data tables 104 KB (as WC's, plus a few tables
    inside the code banks: encounter rates and roll, battle palette numbers, moulds, portrait pointers,
    battle songs); palettes 24 KB (BC's recolouring draws per colour hue/brightness class: c, p, makeover);
    map tables 37 KB (event triggers, NPCs: makeover recolours NPCs by sprite/palette number; entrances);
    event code 1 KB (bytes BC checks or walks: auction house, dragons, recruits, esper scenes); code 45
    bytes (bits BC patches, what bc_codes checks); shapes 50 KB: the monster sprites remonsterate keeps,
    reduced to "blank or one marker pixel" per 8x8 tile (its draws depend on how many different shapes
    there are, so a retry after "out of stencil slots" happens as on the ROM) — no art.
    The user's call (asked 2026-11-20 via the lead): ship palettes/maps/events/code as data, or derive.
  - Fixed on the way: `bc_run.run` returned BC's pre-remonsterate output buffer (remonsterate hands back a
    new one; the exe writes that one). BC's console exe can't make remonsterate seeds at all (its child
    re-runs the console's argument parser): remonsterate's exe parity rests on the source.
  - The porter's `port_sprites` finds a monster's sprite by its graphics pointer for BC
    (`profile.sprite_identity = "pointer"`), not by 96 bytes of its tiles (no graphics ROM-free).
  - `bc_seed.py` serializes its port step (`mods/BCSeed.lock`): several generators at once on the dev PC
    clobbered each other's mods/BCSeed.
- **Player bundle** (`tools/bc_bundle.py`, modkit.json bc: `package_leave_out`, `package_magicite: false`,
  `player_setup: bc_gamedata.py`): generator/python (CPython + Pillow), tools/ (the closure of bc_seed and
  bc_gamedata), bc/ (BC's source at 27de07a, no GUI/tests, its LICENSE), bc_home/ (custom/, remonsterate/),
  data/bc_base.bin, the recipe (tools/gamedata.py: the kit's, from WC's), bundle.json last.
  `--dev`: only the baselines and the Magicite folder. BcPlugin runs `bc_gamedata.py setup` first thing
  (PrKit/Seeds/GameData.cs). BC's art from other games: one setting (`FF6_BC_ASSETS` bundle|release;
  tools/bc_assets.py fetches the pinned packs BC's own updater installs: BeyondChaosSprites 3.8,
  BeyondChaosMonsterSprites 3.1, the release's custom/opera, music/samples at 27de07a; every file sha1-checked).

### Sprites (bc-sprites, 2026-11-20/21; tested in game: bc-art-1, bc-art-2, bc-art-2b PASS 2026-11-21)

- **Sprites** (bc-sprites, 2026-11-20): BC's makeover / `s` / `c` per SNES sprite slot, captured as BC chooses (its
  get_sprite_swaps and manage_palettes wrapped, no draws) and read from its output (palette indexes, palettes,
  portrait ids). The PR's character art is SNES-sized, so BC's 677 custom sheets go in 1:1 (kit
  tools/snes_charsprites.py: pose map of every PR frame, portraits, packing); vanilla art moved between slots is
  the PR's own, recoloured with BC's palette (Lab, per-slot shades). Served live by the kit's ArtSwap (by address,
  atlas and new keys), from the seed's sprites/ folder: no Magicite files, no restart. remonsterate: each picture
  as remonsterate converts it, on a monster image key of its own, placed where the SNES draws it, with a bestiary
  thumbnail. `c`+`m` monster palettes: the PR's images recoloured per seed. `n`: the PR's window sprites in BC's
  window colours. `p`: n/a (the PR's effects aren't palette art). Merchant's slot has no PR art. Themed modes
  (suplexwrecks, bravenudeworld, quikdraw, halloween, kupokupo) come through the same change_to. alasdraco's
  singers on the PR's opera NPCs (not Ralse: his PR look is every scholar's). `y`: partly; the Shiva/Ifrit/
  Tritoch fights keep their PR look (BC draws them as the replacement esper's SNES summon graphic, which a
  ROM-free player doesn't have; the PR's summon art isn't monster-image art).

### Light events (bc-events, 2026-11-20/21)
- **How**: `tools/bc_events.py` rewrites each flag's PR scripts and map files per seed into the seed folder; the
  baseline has them as vanilla's (`bc_events.files()`, own scripts Exit-only, own entity layers empty). Its new lines go
  in as BC_EV_* keys in the seed's system_en; it rewords the PR's own lines in the seed's story_mes_en (the baseline
  restores `bc_events.story_keys()`); it edits tables (monster_party, script); and it writes `bc_events.json` for
  `plugin/BcPlugin/BcEvents.cs` (SysCalls "BC:join/pay/reserve/leave/gil/log" and hooks). BC's choices are read from
  BC's own output or captured as BC makes them (`bc_events.prepare`: the clock's shuffles, the WoR recruits, the
  opera's dialogue variables). Nothing is drawn by us, so a seed number stays the exe's game. It's ROM-free: no reads of
  the ROM's dialogue (bc-seeds' parity runs: the same seed folder with and without the ROM). Flags fail one at a
  time: a flag that throws is left as the game's own, and the rest still apply.
- **Per flag**:
  - `j`: the Phantom Forest's doors from BC's exits, the train exit moved, the forced walk to the spring cut.
  - `k`: the Zozo clock's answer from BC, and BC's 8 hints on the townsfolk's own lines.
  - `lessfanatical`: the Cultists' Tower parties lose their magic-only battle script (9024 -> 0).
  - `regionofdoom`: the Falcon's wheel offers "(Find Doom Gaze.)", which lifts off into the PR's own sky fight.
  - `shadowstays`: the PR's Shadow-leaves draw always says stay.
  - `rushforpower`: Vargas' HP and AI, as data.
  - `h`: the final battle's three parties at random, with no menu.
  - `airship`: the Blackjack waits outside Narshe after the moogles, and the Falcon is ready at the collapse. The
    Floating Continent is always on the Blackjack's wheel, and 13 chocobo stables call the airship.
  - `worringtriad`: the opening goes straight to the World of Ruin at Albrook. It uses the PR's own World of Balance
    end state (300 story flags), Celes and BC's free character at BC's levels, BC's items, espers, gil and Lores (the
    Lore holder learns them on joining).
  - `notawaiter`: 157 vanilla scenes cut to what they do (the kit's `tools/pr_scene_cut.py`). Banon gives BC's two
    items, and the Mobliz letters can all go at once for 2,500 gil.
  - `r`: the World of Ruin recruit scenes recast for BC's characters. That covers the named join/naming/reserve calls,
    character checks, NPC sprites and the name boxes, plus a naming screen for a newcomer who was never named. BC's
    Falcon character joins when the Falcon rises.
  - `mimetime`: Gogo waits in BC's World of Ruin room disguised as BC's character, in an entity layer and talk script
    of our own (script table rows 9200-9211). With that character in the party he gives the Zone Eater's own lines
    and joins. With `o`, `w` or `t` the Zone Eater holds Gau instead, speaking his own PR lines from the Veldt.
  - `alasdraco` (text): BC's cast, factions, pronouns and thrown item in 41 of the PR's own opera lines and the
    roles' name boxes. Only words change, so the sung lines keep the music's timing.
- **Not carried / later**:
  - `airship`'s party menus without the forced Locke/Celes: the PR fixes those members in game code, not data.
  - `worringtriad`: the seed guide never shows, because it waits for the opening.
  - The name boxes (story_cha_en, for `r` and `alasdraco`) wait for one kit edit: PrKit LiveData routing a seed's
    story_cha file to the speaker table (with the kit lead). Until then `bc_events.SPEAKERS_LIVE` is off.
  - `thescenarionottaken` → bc-13; `morefanatical` → bc-12 (with `d`).
- **Story flags**: ScenarioFlag4 0-31 are Beyond Chaos's own (`bc_events.BC_FLAGS`). No vanilla script touches
  ScenarioFlag4 0-131; Worlds Collide uses 0-131 only in its own games. In use: 1 = Doom Gaze search pending
  (regionofdoom), 2 = Gogo found (mimetime). Script table ids 9200-9299 are bc-events' (9200-9211: Gogo's rooms).
- **Tests**: `tests/test_bc_events.py` (17, offline, on BC's real output for seed 9859608359; ~15 s with its cache).
  In game: harness `bcev` (flags, map, party, owned, gil, Lores, battle state), `bcflag`, `bcevgen`, `bcjoin`,
  `bcanswer`, `bcgil`, `bcmsg`, `bcskipnaming`, `bcfinalparty`, `bcselects`.

## Findings for other BC sessions
- In a ROM-free seed BC's output has zeros where BC didn't write and the ROM had graphics, text, code or
  music. Read BC's choices (wrap at seed time, or its spoiler log), BC's own files, the PR's art. If a
  tool needs another small vanilla data table, add it to `EXTRA` + `RULES` in tools/bc_basedata.py (or ask
  bc-seeds), then `tools/bc_basedata.py build`; check with `tools/bc_parity.py`.
- Told: bc-sprites (portraits from graphics; portrait pointers added), bc-music (song/sample tables;
  battle-song slots added), bc-events (event bytes from BC's output).
- **BC's "?" items** (the user: "what does the question mark mean though? ... BC is unparseable", then "? is
  fine if that's what it means"): `questionablecontent` marks equipment BC's item randomizer changed, and
  only BC's spoiler log says how. `tools/bc_items.py` writes it into each such item's description in the
  PR's words, from BC's log (spells cast when used / on a hit / taught, elements, special features) and the
  seed's PR tables next to the game's: "Behemoth Suit?: Changed: Casts Death when used in battle (and
  breaks); Defense 92 (was 94); Magic Defense 63 (was 73); Strength +5 (was +6)." (30 items in the test
  seed; at most ~150 characters, element changes grouped.)
- **A guide for newcomers** (the user: "if there are many signifiers like this, we need to add a tutorial at
  the beginning (right after the controls tutorial)", then "explain what Random and Chain means. basically
  explain everything a new player might not know about beyond chaos"): `tools/bc_guide.py` writes each
  seed's guide into bc_seed.json, built from its flags and data and only for what the port carries: an
  opening page, each of the seed's new commands (what it uses, a Random command's skills with their odds,
  which command it replaced), the command words (Random, Double/Triple, Chain, A + B), shuffled commands,
  characters, rerolled equipment and the "?", espers, battles, treasure and monster boxes, dances, names,
  dash, the boosts (23 pages in the test seed). On the Beyond Chaos screen now ("Guide to this seed", a
  row a topic, its text in the help box; built, not yet seen in game). In the game right after the opening
  controls tutorial, in the game's own message window: built by the old BC session before it handed over
  (2026-11-20): the opening's last scene (sc_e_0001_5, map 3) ends in ShowHelpAndExit (the controls
  tutorial); when that help closes, `BcGuide.cs` starts `sc_bc_guide` (listed in Map_20010's package.json by
  the baseline, its lines BC_GUIDE_00.. set per seed by `bc_guide.write_in_game`): a Yes/No question, then a
  "-Title-" page a topic, as the Narshe school's lessons (25 messages for seed 1234567890). Kit:
  `PrKit/MapScripts.cs` (Current, Busy, MapId, Start) and the harness's `script` on it plus `speed [x]`
  (Time.timeScale, to fast-forward long scenes in tests). Offline tests pass; in game: bc-guide-1, queued.
- **Codes that are data** (`tools/bc_codes.py`, run by bc_seed.py on the seed's full tables):
  `dancelessons` (the PR's off-terrain dance step groups 37-44 lose the stumble, ability 262 at 50; the
  steps keep their odds between them). `expboost`/`gpboost`/`mpboost` were data all along (BC writes
  the monsters' EXP and gil and the formations' AP; the porter carries them). Equipment: the porter
  carries BC's weapon effects (27 in the test seed); left for the plugin: MBlock bonuses (7 weapons),
  7 armor procs, 3 relic bits.
- **Tests**: `tests/test_bc.py` (every flag on the screen; every string the screen makes, 348 from
  `plugin/Bc.Tests`, read by BC's own parser as meant; BC's source = the exe's ROM; BC_SEED_TEST=1: a
  seed folder's shape), `PR_MOD=BCSeed tests/test_mod.py` after `bc_seed.py --keep-port` (48 run, 0
  failures).
- **Light events, how**: the kit's SNES event decoder and SNES -> PR script translator (tools/snes_events.py,
  event_translate.py, MODDING.md "SNES events -> PR scripts"; owned by the ted-events session) read BC's
  event patches as they are on its US-layout ROM, so worringtriad / notawaiter / lessfanatical etc. start
  from translated scripts, with the translator's `SysCall "SNES:..."` stubs left for the plugin.
- **Next**: the parity battle code into the kit (BC needs it as WC does), BC's custom commands (`w`)
  with full names, item specials, the small codes, ROM-free + the player's bundle (ask about shipping
  BC's sprites/images/samples first), then sprites and music.

**Workstreams** (2026-11-20, the BC lead session, started by the BNW coordinator; at most 4 BC children at
once; owners in the BC table under Status; the lead's notes, with each child's files, are `bc-lead.md` in the
shared side-session notes folder; children keep their findings in `bc-<name>.md` there and the lead merges them
here):
- **bc-seeds**: the ROM-free generator (BC's data tables only, stand-ins where BC only rewrites, a parity
  check per stage), the player setup and bundle (bundled Python, game-file copies made on the player's
  machine, `kit.py package bc`), the data flags still partly or not ported, WC's plugin features BC's data
  needs moved into the kit.
- **bc-battle**: custom commands in battle (repeats, combos, targeting, the command-maker codes), item
  specials and break codes, the small codes that are plugin code, then the junction effects; a BC self-test
  registry so one headless battle checks many.
- **bc-sprites**: makeover (BC's SNES sheets to the PR's field/battle frames and portraits, a pose map any
  FF6 mod can use), remonsterate (BC's monster images on the PR's monster image keys), palettes (`c`, `p`, `n`).
- **bc-events** (started from a card by the user, 2026-11-20, after the user lifted the child cap): BC's light events on the kit's SNES event translator.
- **bc-junction** (started the same way): BC's junction effects (6 flags, ~57 SNES patches), moved off
  bc-battle so they run in parallel.
- **bc-music**: the kit's SNES sound player (`PrKit/Snes`: an S-DSP and FF6's driver re-implemented, PCM
  streamed in place of the game's track; T-Edition's songs will use it), BC's songs per seed.
- **The lead**: the plan, this table and the progress page, integration; the guide in game after the controls
  tutorial; light events; testing and release; the cave modes, `d` and strangejourney after Normal mode.
- **The user's answers** (2026-11-20): BC's art and samples from other games (custom/ sprites, remonsterate/, music/ with
  its samples) ship in the player's zip ("i've gotten permissions from every mod owner so you can go ahead and bundle
  any art/assets/music"); the generator's data file ships the ROM's data tables plus ~62 KB of palettes, map tables and
  event bytes ("yes you can ship the 62kb"). Never shipped: the SNES ROM, any other SNES data, the PR's own files. FF6's SNES sound driver and its built-in instrument samples may ship (the user: "i have permission for the SNES sound drive and build-in instrument sounds").
- **Codes with no meaning in the PR** (2026-11-20, bc-battle's list, the lead agreed; shown as n/a with the reason on
  the BC screen): sketch (an SNES memory-corruption glitch), relicmyhat (the PR's equipment and shop screens already do
  it), tastetherainbow (SNES aura palette cycling), removeflashing (SNES animation-script bytes; the PR's effects are its
  own, as with WC's left-out battle flashes), and `b`'s SNES-only fixes (the random-table shuffle, X-Zone/Runic hide, Imp
  skimp, Gogo portrait, item-return buffer, Flyaway, death abuse; `b`'s data parts are carried). equipanything is "partly" (2026-11-20, bc-battle's BcEquipAnything: in a BC game with the code, head, body and relic
  armor can be held in a hand, as the PR's shields are; left out: consumables in a hand (the PR's equip lists hold only
  weapons and armor), "anyone may hold it" (the PR's job check doesn't know the slot), an armor read as a weapon). Re-homed: morefanatical to the `d` row, thescenarionottaken to its own row, espercutegf to bc-junction.
