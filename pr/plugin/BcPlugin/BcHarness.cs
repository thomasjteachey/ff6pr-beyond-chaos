using System;
using System.IO;
using System.Linq;
using Last.Data.Master;
using Last.Management;
using PrKit;
using PrKit.Seeds;

namespace BeyondChaos.PR
{
    // Beyond Chaos's commands for the kit's headless harness (kit.py run ff6 --harness; tools/game_harness.py):
    //   bc                       the mod's state: data, active seed, generator
    //   bcgen SEED [MODE] [PRESET words...]   make a seed in game (BC + the porter), apply it, check it
    //   bcapply ID|none          switch seeds (none: the game's own data), then check
    //   bccheck                  the live rows and Magicite files against the active seed's folder
    //   bcscreen                 the options screen's self-test (every page, every row) and controller flow
    static class BcHarness
    {
        internal static void Register()
        {
            Harness.Register("bc", _ => Status(), "bc: Beyond Chaos's data, active seed and generator");
            Harness.Register("bcgen", Gen, "bcgen SEED [MODE] [PRESET...]: make a Beyond Chaos seed in game, apply it, check it");
            Harness.Register("bcapply", a =>
            {
                var id = a.Length > 0 ? a[0] : "none";
                var s = id == "none" ? null : BcSeeds.Lib.Load(id);
                if (id != "none" && s == null) return $"error: no seed {id}";
                var err = BcSeeds.Lib.Apply(s);
                return err != null ? "error: " + err : $"{BcSeeds.Lib.LastApply}; {Check()}";
            }, "bcapply ID|none: apply an earlier seed (none: the game's own data) and check it");
            Harness.Register("bccheck", _ => Check(), "bccheck: the live rows and Magicite files against the active seed");
            Harness.Register("bcscreen", _ => $"{Plugin.Screen.SelfTest()}; nav: {Plugin.Screen.NavTest()}", "bcscreen: the options screen's self-test");
            Harness.Register("bckeep", a =>
            {
                Keep = a.Length == 0 || a[0] != "off";
                Auto = !(a.Length > 1 && a[1] == "manual");
                return $"keep battles moving: {(Keep ? $"on (Active mode, {(Auto ? "auto" : "no auto: only queued acts")}, party HP 9999)" : "off")}";
            }, "bckeep on|off [manual]: a headless battle keeps moving (Active mode, auto battle unless manual, the party's HP at 9999)");
            Harness.Register("enemyhp", a =>
            {
                int hp = a.Length > 0 && int.TryParse(a[0], out var v) ? v : 9999;
                var bm = Last.Battle.BattlePlugManager.Instance();
                if (bm == null || !bm.IsBattle()) return "error: not in a battle";
                int n = 0;
                foreach (var e in bm.GetEnemyUnits())
                {
                    var p = e?.BattleUnitDataInfo?.Parameter;
                    if (p == null || p.CurrentHP <= 0) continue;
                    if (p.BaseMaxHp < hp) p.BaseMaxHp = hp;
                    p.CurrentHP = hp;
                    n++;
                }
                return $"{n} monsters at {hp} HP";
            }, "enemyhp N: every living monster's HP to N (default 9999)");
            Harness.Register("bcuse", Use, "bcuse SLOT COMMAND: party member SLOT (0-3) uses PR command COMMAND on the first monster, as the game queues an act");
            Harness.Register("bccommands", _ => Commands(), "bccommands: BC's commands as the game has them now (row, ability, name)");
            Harness.Register("uitext", UiText, "uitext FILTER|all OUT.txt: every UI text (hidden ones too) whose path contains FILTER: box size, font size, best fit, overflow, text");
            Harness.Register("textwidth", TextWidth, "textwidth IN.json OUT.json: each string's width in each font the game's UI uses (tools/bc_names.py)");
            Harness.Register("bcguide", a => a.Length > 0 && a[0] == "start" ? BcGuide.Start() : BcGuide.State(),
                "bcguide [start]: the seed's guide after the opening's controls tutorial (its state; start: run it now, on map 3)");
            Harness.StateParts.Add(() => Plugin.BcMode ? BcGuide.State() : "guide off (no BC data)");
            BcSelfTests.Register();   // bc-battle: bcselftest (the battle side's in-battle checks), bcselftests
            BcEvents.Register();      // bc-events: bcev (the seed's event flags, map, party), bcflag
            Kit.Info("[bc] harness commands: bc, bcgen, bcapply, bccheck, bcscreen, bcguide, textwidth");
        }

        // --- battles (the PC test runner's recipe, as Brave New World's AiFights) -----------------------
        internal static bool Keep, Auto = true;

        // every frame while on: Wait mode freezes a headless battle on command menus nobody answers
        internal static void Update()
        {
            if (!Keep) return;
            try
            {
                var udm = Last.Management.UserDataManager.Instance();
                if (udm?.Config != null && udm.Config.BattleModeIndex != 0) udm.Config.BattleModeIndex = 0;
                var bm = Last.Battle.BattlePlugManager.Instance();
                if (bm == null || !bm.IsBattle()) return;
                Last.UI.BattleUIManager.Instance?.SetIsAuto(Auto);
                foreach (var p in bm.GetPlayerUnits())
                {
                    var prm = p?.BattleUnitDataInfo?.Parameter;
                    if (prm == null || prm.CurrentHP <= 0) continue;
                    if (prm.BaseMaxHp < 9999) prm.BaseMaxHp = 9999;
                    if (prm.CurrentHP < 9999) prm.CurrentHP = 9999;
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-keep", e); }
        }

        // a party member's act with a command, at the first living monster, queued as the game queues the
        // player's (BattleActExection.SetBattleActData: BcCommands' hook sees it as it sees a real pick)
        static string Use(string[] a)
        {
            if (a.Length < 2 || !int.TryParse(a[0], out int slot) || !int.TryParse(a[1], out int id)) return "error: bcuse SLOT COMMAND";
            var bm = Last.Battle.BattlePlugManager.Instance();
            if (bm == null || !bm.IsBattle()) return "error: not in a battle";
            var players = bm.GetPlayerUnits();
            if (players == null || slot < 0 || slot >= players.Length || players[slot] == null) return $"error: no party member in slot {slot}";
            var enemy = bm.GetEnemyUnits()?.FirstOrDefault(e => e != null && e.BattleUnitDataInfo?.Parameter?.CurrentHP > 0);
            if (enemy == null) return "error: no living monster";
            var mm = MasterManager.Instance;
            var cmd = mm.GetData<Command>(id);
            var ab = cmd == null ? null : mm.GetData<Ability>(cmd.AbilityId);
            if (ab == null) return $"error: command {id} has no ability";
            var abilities = new Il2CppSystem.Collections.Generic.List<Ability>();
            abilities.Add(ab);
            var targets = new Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppReferenceArray<Last.Battle.BattleUnitData>(1);
            targets[0] = enemy;
            var act = new Last.Battle.BattleActData(players[slot], targets, cmd, abilities, Last.Battle.BattleActData.ActType.Normal,
                Last.Battle.BattleActData.TargetType.SingleEnemy, Last.Battle.BattleActData.ArmType.Right, (Last.Battle.BattleActData.ActAbilityType)0, 1, false);
            int before = BcCommands.Extra;
            bm.BattleActExection.SetBattleActData(act);
            return $"slot {slot} uses {GameText.Get(cmd.MesIdName)} (command {id}, ability {ab.Id}) on monster {enemy.TryCast<Last.Battle.BattleEnemyData>()?.GetMonster()?.Id}; " +
                   $"{BcCommands.Extra - before} extra acts queued{(BcCommands.LastNote != "" ? " (" + BcCommands.LastNote + ")" : "")}";
        }

        static string Commands()
        {
            var s = BcSeeds.Active;
            if (s == null) return "no seed";
            var mm = MasterManager.Instance;
            var parts = new System.Collections.Generic.List<string>();
            foreach (var (id, c) in s.Commands.OrderBy(kv => kv.Key))
            {
                var row = mm.GetData<Command>(id);
                var name = row == null ? "?" : GameText.Get(row.MesIdName);
                bool ok = row != null && row.AbilityId == c.Ability && row.ListType == 0 && row.ExecutionType == 1 && name == c.Name;
                parts.Add($"{id} {name} ({c.Kind}, ability {row?.AbilityId}, list {row?.ListType}, exec {row?.ExecutionType}){(ok ? "" : " MISMATCH")}");
            }
            return $"{s.Commands.Count} commands: " + string.Join("; ", parts) + $"; extra acts so far {BcCommands.Extra}";
        }

        // The windows a name shows in, as the game built them: each UI text's path in its scene, its box
        // (RectTransform), font size, best fit (Unity shrinks the text to fit when on) and overflow
        static string UiText(string[] a)
        {
            if (a.Length < 2) return "error: uitext FILTER OUT.txt";
            // "all" (or an empty / quoted-empty filter): every text
            var filter = a[0] == "all" || a[0].Trim('"', '\'') == "" ? "" : a[0].ToLowerInvariant();
            var lines = new System.Collections.Generic.List<string>();
            foreach (var o in UnityEngine.Resources.FindObjectsOfTypeAll(Il2CppInterop.Runtime.Il2CppType.Of<UnityEngine.UI.Text>()))
            {
                var t = o?.TryCast<UnityEngine.UI.Text>();
                if (t == null) continue;
                var path = new System.Text.StringBuilder();
                for (var tr = t.transform; tr != null; tr = tr.parent) path.Insert(0, "/" + tr.name);
                var p = path.ToString();
                if (!p.ToLowerInvariant().Contains(filter)) continue;
                var r = t.rectTransform.rect;
                lines.Add($"{p}\tw {r.width:0.#} h {r.height:0.#}\tsize {t.fontSize}\tbestfit {t.resizeTextForBestFit} ({t.resizeTextMinSize}-{t.resizeTextMaxSize})" +
                          $"\tover {t.horizontalOverflow}\tfont {t.font?.name}\tactive {t.gameObject.activeInHierarchy}\t\"{(t.text ?? "").Replace("\n", " ")}\"");
            }
            File.WriteAllLines(a[1], lines);
            return $"uitext: {lines.Count} texts matching '{a[0]}' -> {a[1]}";
        }

        // Names are limited by width in a proportional font, not by a count (the user: no SNES
        // abbreviations; the PR's translations fit 11-13 characters in the same windows). IN.json:
        // {"strings": [...], "size": 40}; OUT.json: {fonts: {font: {string: width}}}, measured as the
        // game lays text out (a UI Text's preferred width, every font a UI text on screen uses).
        static string TextWidth(string[] a)
        {
            if (a.Length < 2) return "error: textwidth IN.json OUT.json";
            using var doc = System.Text.Json.JsonDocument.Parse(File.ReadAllText(a[0]));
            var strings = doc.RootElement.GetProperty("strings").EnumerateArray().Select(x => x.GetString()).ToList();
            int size = doc.RootElement.TryGetProperty("size", out var sz) ? sz.GetInt32() : 40;
            var fonts = new System.Collections.Generic.Dictionary<string, UnityEngine.Font>();
            foreach (var t in UnityEngine.Object.FindObjectsOfType<UnityEngine.UI.Text>())
                if (t != null && t.font != null && !fonts.ContainsKey(t.font.name)) fonts[t.font.name] = t.font;
            if (fonts.Count == 0) return "error: no UI text with a font on screen";
            var go = new UnityEngine.GameObject("bc-textwidth");
            var result = new System.Collections.Generic.Dictionary<string, System.Collections.Generic.Dictionary<string, float>>();
            try
            {
                var text = go.AddComponent<UnityEngine.UI.Text>();
                text.fontSize = size;
                text.horizontalOverflow = UnityEngine.HorizontalWrapMode.Overflow;
                text.verticalOverflow = UnityEngine.VerticalWrapMode.Overflow;
                text.supportRichText = false;
                foreach (var (name, font) in fonts)
                {
                    text.font = font;
                    var widths = new System.Collections.Generic.Dictionary<string, float>();
                    foreach (var s in strings)
                    {
                        text.text = s;
                        widths[s] = text.preferredWidth;
                    }
                    result[name] = widths;
                }
            }
            finally { UnityEngine.Object.Destroy(go); }
            File.WriteAllText(a[1], System.Text.Json.JsonSerializer.Serialize(new { size, fonts = result }));
            return $"textwidth: {strings.Count} strings in {fonts.Count} fonts ({string.Join(", ", fonts.Keys)}) -> {a[1]}";
        }

        static string Status()
        {
            var a = BcSeeds.Active;
            var (py, script, err) = BcSeeds.Gen.Resolve();
            return $"bc mode {Plugin.BcMode}; {BcSeeds.Lib.Count()} seeds; active {(a == null ? "none" : $"{a.Id} ({a.SeedText}, {a.Mode}, {a.Rows} rows, {a.Files.Length} files, {a.MonsterChests.Count} box chests, AI {(a.SnesAi != null ? "yes" : "no")})")}; " +
                   $"startup {(BcSeeds.Lib.StartupDone ? $"done ({BcSeeds.Lib.StartupFailed} failed)" : "pending")}; generator {err ?? py + " " + script}";
        }

        static string genId;

        static string Gen(string[] a, int tick)
        {
            if (tick == 0)
            {
                if (!LiveData.Ready) return "error: the game's data isn't loaded yet";
                var seed = a.Length > 0 ? a[0] : "9859608359";
                var mode = a.Length > 1 ? a[1] : "normal";
                var preset = a.Length > 2 ? string.Join(" ", a.Skip(2)) : "New Player";
                if (!Plugin.FlagDefs.Presets.TryGetValue(preset, out var flags)) return $"error: no preset '{preset}'";
                genId = SeedLibrary.NewId(seed) + "-test";
                var err = BcSeeds.Gen.Start(seed, flags, BcSeeds.Lib.DirFor(genId), ("mode", mode));
                return err != null ? "error: " + err : null;
            }
            if (!BcSeeds.Gen.TakeResult(out bool ok, out string error, out string dir)) return null;   // still making it
            if (!ok) return $"error: {error}";
            var s = BcSeeds.Lib.Load(Path.GetFileName(dir));
            if (s == null) return "error: the seed was made but can't be read";
            var aerr = BcSeeds.Lib.Apply(s);
            if (aerr != null) return "error: apply: " + aerr;
            return $"seed {s.SeedText} made in {s.Seconds:0.0} s (generator) / {BcSeeds.Gen.Seconds:0.0} s; {BcSeeds.Lib.LastApply}; {Check()}";
        }

        // the active seed's tables as the game now has them (a few columns of three tables) and its files
        // in the Magicite folder
        internal static string Check()
        {
            var s = BcSeeds.Active;
            var mm = MasterManager.Instance;
            var dir = s?.Dir ?? Path.Combine(Plugin.Data.Baseline, "vanilla_data");
            int rows = 0, bad = 0;
            string firstBad = null;
            foreach (var (table, col, get) in new (string, string, Func<int, string>)[]
                     {
                         ("monster", "hp", id => $"{mm.GetData<Monster>(id)?.Hp}"),
                         ("item", "buy", id => $"{mm.GetData<Item>(id)?.Buy}"),
                         ("character_status", "strength", id => $"{mm.GetData<CharacterStatus>(id)?.Strength}"),
                     })
            {
                var csv = Path.Combine(dir, LiveData.MasterDir, table + ".csv");
                if (!File.Exists(csv)) continue;
                var lines = File.ReadAllLines(csv);
                int ci = Array.IndexOf(lines[0].Split(','), col);
                foreach (var line in lines.Skip(1).Where(l => l.Length > 0).Take(80))
                {
                    var c = line.Split(',');
                    if (!int.TryParse(c[0], out int id)) continue;
                    rows++;
                    var have = get(id);
                    if (have == c[ci]) continue;
                    bad++;
                    firstBad ??= $"{table} {id} {col}: game {have}, seed {c[ci]}";
                }
            }
            int files = 0, badFiles = 0;
            if (s != null)
                foreach (var rel in s.Files)
                {
                    files++;
                    var mine = Path.Combine(s.Dir, "files", rel);
                    var live = Path.Combine(MagiciteDir.FolderPath(Plugin.ModFolder), rel);
                    if (!File.Exists(live) || new FileInfo(live).Length != new FileInfo(mine).Length ||
                        !File.ReadAllBytes(live).AsSpan().SequenceEqual(File.ReadAllBytes(mine))) badFiles++;
                }
            return $"check: {rows - bad}/{rows} rows as the seed's{(firstBad != null ? $" (first wrong: {firstBad})" : "")}, " +
                   $"{files - badFiles}/{files} files in place";
        }
    }
}
