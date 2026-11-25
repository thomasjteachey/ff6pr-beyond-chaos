using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using BeyondChaos.PR;

// Beyond Chaos's game-free rules (BcBattleRules, BcDoorRules), checked offline.
// dotnet run -c Debug [-- SEED/bc_doors.json]: a seed's door table is checked too when given.
static class Program
{
    static int failures, checks;

    static void Check(bool ok, string what)
    {
        checks++;
        if (ok) return;
        failures++;
        Console.WriteLine("FAIL " + what);
    }

    static string S(IEnumerable<int> xs) => string.Join(" ", xs);

    static int Main(string[] args)
    {
        // repeats, chains, combos (BC's MultipleSpellSub / ChainSpellSub / ComboSpellSub)
        var ab = new[] { 10, 20 };
        Check(S(BcBattleRules.ActPlan("multiple", "combo", 3, ab, () => false)) == "20 0 20 0 20", "three rounds of a combo: B, then (A, B) twice");
        int heads = 0;
        Check(S(BcBattleRules.ActPlan("chain", "combo", 1, ab, () => heads++ < 2)) == "20 0 20 0 20", "a chain of a combo, two heads");
        Check(S(BcBattleRules.ActPlan("multiple", "random", 4, new[] { 10 }, () => false)) == "0 0 0", "x4 of a random skill: three more rolls");
        Check(S(BcBattleRules.ActPlan("multiple", "skill", 2, new[] { 10 }, () => true)) == "0", "Double: one more");
        Check(S(BcBattleRules.ActPlan("combo", "combo", 1, ab, () => true)) == "20", "a combo: B after A");
        Check(BcBattleRules.ActPlan("skill", "skill", 1, new[] { 10 }, () => true).Count == 0, "one skill: nothing more");
        Check(BcBattleRules.ActPlan("chain", "skill", 1, new[] { 10 }, () => true).Count == BcBattleRules.ChainCap, "a chain stops at the cap");
        Check(BcBattleRules.ActPlan("chain", "skill", 1, new[] { 10 }, () => false).Count == 0, "a chain on tails: no more");
        Check(BcBattleRules.ActPlan("multiple", "combo", 2, new[] { 10 }, () => false).SequenceEqual(new[] { 0 }), "a combo list of one skill acts as a skill");
        // every act's own skill (bc-selftest-4: seed 9859608359's "Arise + Cyclonic", PR abilities 35 then 315, ran 315 315)
        var arise = new[] { 35, 315 };
        Check(S(BcBattleRules.ActAbilities(35, BcBattleRules.ActPlan("combo", "combo", 1, arise, () => true))) == "35 315", "a combo: Arise, then Cyclonic");
        Check(S(BcBattleRules.ActAbilities(35, BcBattleRules.ActPlan("multiple", "combo", 3, arise, () => false))) == "35 315 35 315 35 315",
              "three rounds of a combo: A B A B A B");
        Check(S(BcBattleRules.ActAbilities(10, BcBattleRules.ActPlan("multiple", "skill", 2, new[] { 10 }, () => true))) == "10 10", "Double: the skill twice");
        Check(S(BcBattleRules.ActAbilities(7, null)) == "7", "one act: the row's");

        // the self-test filter
        Check(BcBattleRules.FilterMatches("commands: rows", ""), "no filter: every test");
        Check(BcBattleRules.FilterMatches("commands: rows", "all"), "all: every test");
        Check(!BcBattleRules.FilterMatches("junction acts", "!junction"), "!junction drops a junction test");
        Check(BcBattleRules.FilterMatches("items: Vigor +50%", "!junction"), "!junction keeps the rest");
        Check(BcBattleRules.FilterMatches("codes: levelcap", "commands, codes"), "two words: either");
        Check(!BcBattleRules.FilterMatches("items: Vigor +50%", "commands,codes"), "not in the words: out");
        Check(!BcBattleRules.FilterMatches("codes: norng", "codes,!norng"), "a word and an exclusion");

        // levelcap, norng's weighted pick, Vigor +50%, mementomori's stats, cursepower's counter
        Check(BcBattleRules.CappedLevel(45, 38) == 38 && BcBattleRules.CappedLevel(30, 38) == 30 && BcBattleRules.CappedLevel(60, 0) == 60, "level caps");
        Check(BcBattleRules.FirstWeighted(new float[] { 0, 3, 5 }) == 1 && BcBattleRules.FirstWeighted(new float[] { 0, 0 }) == -1, "norng picks the first entry with weight");
        Check(BcBattleRules.VigorBoost(40) == 60 && BcBattleRules.VigorBoost(41) == 61 && BcBattleRules.VigorBoost(200) == 255, "Vigor +50%, capped");
        Check(BcBattleRules.AddStat(120, 10, 128) == 128 && BcBattleRules.AddStat(5, -10) == 0 && BcBattleRules.AddStat(50, 7) == 57, "a hidden relic's stat");
        Check(BcBattleRules.CurseCounter(9, 10) == 255, "cursepower: the 10th battle (9 counted) uncurses");
        Check(BcBattleRules.CurseCounter(8, 10) == 8, "cursepower: the 9th (8 counted) doesn't");
        Check(BcBattleRules.CurseCounter(40, 0) == 40 && BcBattleRules.CurseCounter(40, 256) == 40, "cursepower off: the PR's own count");

        // the self-tests' fixture: a battle on its victory screen is over (bc-5), and bckeep leaves a check's HP alone
        Check(BcBattleRules.BattleOver(true, 0, 4, 3) == null, "a live battle runs the checks");
        Check(BcBattleRules.BattleOver(true, 1, 4, 3) != null, "won (WinResult): over, though IsBattle() is still true");
        Check(BcBattleRules.BattleOver(true, 0, 0, 3) == "no living monster", "every monster down (bc-5: Doom left by the start check): over");
        Check(BcBattleRules.BattleOver(true, 0, 2, 0) != null && BcBattleRules.BattleOver(false, 0, 2, 3) == "not in a battle", "no party / no battle: over");
        Check(BcBattleRules.KeepAliveHp(3000, false) == 9999 && BcBattleRules.KeepAliveHp(12000, false) == 12000, "bckeep tops HP up to 9999, never down");
        Check(BcBattleRules.KeepAliveHp(3000, true) == 3000 && BcBattleRules.KeepAliveHp(1, true) == 1, "a check holding HP keeps its 3000 / 1 (auto_potion, auto_down, immortal)");
        Check(BcBattleRules.KeepAliveHp(0, false) == 0, "a fallen member isn't raised by bckeep");

        Doors();
        if (args.Length > 0) DoorsFile(args[0]);

        Console.WriteLine($"BcBattle.Tests: {checks - failures} of {checks} passed");
        return failures == 0 ? 0 : 1;
    }

    // --- strangejourney's per-world doors (BcDoorRules: bc_doors.json "shared", split "world") -----------------------
    // the World of Ruin flag (kScenarioFlag2 41) set or not; any other flag can't be read
    static Func<string, int, bool?> World(bool ruin) =>
        (c, i) => c == BcDoorRules.WorCategory && i == BcDoorRules.WorIndex ? ruin : (bool?)null;

    static string T(int[] t) => BcDoorRules.Str(t);

    static string Rec(int id, string pr, int map, int x, int y, string vanilla, string split, string unique, string redirect) =>
        $@"{{""file"": ""{pr}/entity_default.json"", ""id"": {id}, ""pr"": ""{pr}"", ""x"": {x}, ""y"": {y}, ""vanilla"": {vanilla}, " +
        $@"""pr_map_id"": {(map < 0 ? "null" : map.ToString())}, ""split"": ""{split}"", ""key_unique"": {unique}" +
        (redirect == null ? "" : $@", ""redirect"": {redirect}") + "}";

    static string Wor(string off, string on) => $@"{{""flag"": [""kScenarioFlag2"", 41], ""off"": {off}, ""on"": {on}}}";

    static void Doors()
    {
        var recs = new[]
        {
            Rec(51, "Map_20010", 3, 32, 30, "[9, 1]", "world", "true", Wor("[393, 2]", "[76, 3]")),      // both worlds move
            Rec(9, "Map_20010", 3, 33, 54, "[4, 1]", "world", "true", Wor("[4, 1]", "[5, 1]")),          // World of Ruin only
            Rec(56, "Map_20010", 3, 43, 11, "[13, 1]", "world", "true", Wor("[389, 1]", "null")),        // no arrival in the WoR
            Rec(7, "Map_20020", 18, 10, 10, "[30, 1]", "world", "true",
                @"{""flag"": [""kScenarioFlag1"", 5], ""off"": [31, 1], ""on"": [32, 1]}"),                 // another switch
            Rec(3, "Map_20200", 50, 5, 5, "[40, 1]", "story", "true", null),                              // a story split
            Rec(4, "Map_20300", 60, 6, 6, "[41, 1]", "world", "false", Wor("[42, 1]", "[43, 1]")),       // key not unique
            Rec(5, "Map_20400", -1, 7, 7, "[44, 1]", "world", "true", Wor("[45, 1]", "[46, 1]")),        // no PR map id
            Rec(1, "Map_20500", 77, 20, 20, "[70, 1]", "world", "true", Wor("[71, 1]", "[72, 1]")),      // two doors, one key
            Rec(2, "Map_20500", 77, 24, 20, "[70, 1]", "world", "true", Wor("[73, 1]", "[74, 1]")),
        };
        var t = BcDoorRules.Parse(@"{""flags"": ""b c strangejourney"", ""shared"": [" + string.Join(",", recs) + "]}");
        Check(t.Shared == 9 && t.Story == 1, $"doors: 9 shared records, 1 story split (not the plugin's): {t.Shared}, {t.Story}");
        Check(t.Doors.Count == 6, $"doors: 6 per-world doors loaded ({t.Doors.Count})");
        Check(t.Skipped.Count == 2 && t.Skipped.Any(x => x.Contains("key not unique")) && t.Skipped.Any(x => x.Contains("no map")),
              "doors: a key that isn't unique and a record without its map are left out: " + string.Join(" | ", t.Skipped));
        Check(t.Flags == "b c strangejourney", "doors: the seed's flags read");
        Check(BcDoorRules.Parse("{}").Doors.Count == 0 && BcDoorRules.Parse(@"{""shared"": []}").Doors.Count == 0, "doors: a file with no shared doors: none");

        // on / off by the World of Ruin flag, at the door (Narshe's 32,30 -> vanilla's map 9 point 1)
        Check(T(BcDoorRules.Resolve(t, 3, 9, 1, 32, 30, World(false))) == "393 2", "doors: World of Balance: the off target");
        Check(T(BcDoorRules.Resolve(t, 3, 9, 1, 32, 30, World(true))) == "76 3", "doors: World of Ruin: the on target");
        Check(T(BcDoorRules.Resolve(t, 3, 9, 1, 32, 31, World(false))) == "393 2", "doors: a tile below the door (walking in): redirected");
        Check(T(BcDoorRules.Resolve(t, 3, 9, 1, 31, 29, World(true))) == "76 3", "doors: a tile off diagonally: redirected");
        // the wrong map, the wrong target, the party too far, no table
        Check(BcDoorRules.Resolve(t, 4, 9, 1, 32, 30, World(false)) == null, "doors: the same target from another map: left alone");
        Check(BcDoorRules.Resolve(t, 3, 9, 2, 32, 30, World(false)) == null, "doors: another point of the same map: left alone");
        Check(BcDoorRules.Resolve(t, 3, 393, 2, 32, 30, World(false)) == null, "doors: the redirect's own target: left alone");
        Check(BcDoorRules.Resolve(t, 3, 9, 1, 32, 32, World(false)) == null, "doors: the party two tiles away (a script's ChangeMap): left alone");
        Check(BcDoorRules.Resolve(t, 3, 9, 1, 34, 30, World(true)) == null, "doors: two tiles to the side: left alone");
        Check(BcDoorRules.Resolve(null, 3, 9, 1, 32, 30, World(false)) == null, "doors: no table (no strangejourney): left alone");
        Check(BcDoorRules.Resolve(new BcDoorRules.Table(), 3, 9, 1, 32, 30, World(false)) == null, "doors: an empty table: left alone");
        Check(BcDoorRules.Resolve(t, 3, 9, 1, 32, 30, (c, i) => null) == null, "doors: the flag can't be read: left alone");
        Check(BcDoorRules.Resolve(t, 3, 9, 1, 32, 30, null) == null, "doors: no flag reader: left alone");
        // a world whose version keeps vanilla's target, or has none
        Check(BcDoorRules.Resolve(t, 3, 4, 1, 33, 54, World(false)) == null, "doors: off is vanilla's target: no change in the World of Balance");
        Check(T(BcDoorRules.Resolve(t, 3, 4, 1, 33, 54, World(true))) == "5 1", "doors: ... and the on target in the World of Ruin");
        Check(T(BcDoorRules.Resolve(t, 3, 13, 1, 43, 11, World(false))) == "389 1", "doors: the off target with on null");
        Check(BcDoorRules.Resolve(t, 3, 13, 1, 43, 11, World(true)) == null, "doors: on null (no PR arrival for that version): left alone");
        // the file's own flag is the switch (any other flag can't be read here: left alone)
        Check(BcDoorRules.Resolve(t, 18, 30, 1, 10, 10, World(true)) == null, "doors: a redirect on another flag isn't switched by the World of Ruin's");
        Check(T(BcDoorRules.Resolve(t, 18, 30, 1, 10, 10, (c, i) => c == "kScenarioFlag1" && i == 5)) == "32 1", "doors: ... its own flag set: on");
        // story splits and left-out records are never touched
        Check(t.At(50, 40, 1) == null && BcDoorRules.Resolve(t, 50, 40, 1, 5, 5, World(true)) == null, "doors: a story split isn't the plugin's");
        Check(BcDoorRules.Resolve(t, 60, 41, 1, 6, 6, World(true)) == null, "doors: a key that isn't unique: left alone");
        // two listed doors with one key: the one the party stands at
        Check(T(BcDoorRules.Resolve(t, 77, 70, 1, 20, 21, World(false))) == "71 1" && T(BcDoorRules.Resolve(t, 77, 70, 1, 24, 19, World(false))) == "73 1",
              "doors: two doors to one place: the nearer one's redirect");
        Check(BcDoorRules.Resolve(t, 77, 70, 1, 22, 20, World(false)) == null, "doors: between them, two tiles from each: left alone");
        // the harness's question: no position
        Check(T(BcDoorRules.Resolve(t, 3, 9, 1, null, null, World(true))) == "76 3", "doors: no position (bcdoors MAP TOMAP TOPOINT wor): the door's redirect");
        Check(BcDoorRules.Find(t, 3, 9, 1, 32, 30)?.Id == 51 && BcDoorRules.Find(t, 3, 9, 1, 40, 40) == null, "doors: Find names the door at the party");
    }

    // a seed's bc_doors.json (tools/bc_entrances.py apply): every per-world door redirects at its own tile, by world
    static void DoorsFile(string path)
    {
        if (!File.Exists(path))
        {
            Check(false, $"doors file: {path} not found");
            return;
        }
        var t = BcDoorRules.Parse(File.ReadAllText(path));
        int changes = 0;
        foreach (var d in t.Doors)
        {
            int[] Want(int[] to) => to == null || (to[0] == d.ToMap && to[1] == d.ToPoint) ? null : to;
            var off = BcDoorRules.Resolve(t, d.Map, d.ToMap, d.ToPoint, d.X, d.Y, World(false));
            var on = BcDoorRules.Resolve(t, d.Map, d.ToMap, d.ToPoint, d.X, d.Y + 1, World(true));
            Check(T(off) == T(Want(d.Off)) && T(on) == T(Want(d.On)), $"doors file: {d}: World of Balance {T(off)}, World of Ruin {T(on)}");
            Check(BcDoorRules.Resolve(t, d.Map, d.ToMap, d.ToPoint, d.X + 2, d.Y, World(true)) == null, $"doors file: {d}: two tiles off, left alone");
            if (d.Changes) changes++;
        }
        Check(t.Doors.Count > 0, "doors file: per-world doors loaded");
        Console.WriteLine($"doors file {Path.GetFileName(path)}: {t.Doors.Count} per-world doors ({changes} change a map change), " +
                          $"{t.Skipped.Count} left out, {t.Story} story splits of {t.Shared} shared");
    }
}
