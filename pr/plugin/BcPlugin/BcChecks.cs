using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using PrKit;
using PrKit.Ff6;

namespace BeyondChaos.PR
{
    // Beyond Chaos's in-game checks on the kit's self-test runner (PrKit/SelfTests.cs, MODDING.md "Testing"): each check
    // is a [SelfTest] method in any BcPlugin file. Run from the harness:
    //   selftest bc.*            start the checks named (names, a prefix `bc.data.*`, or `*`); the command answers when
    //                            they're done: "selftest done: N passed, M failed [...]"
    //   selftest                 the last run's results
    // Fixtures: "field" and "battle" (the kit's), "seed" (a BC seed active). Lines: "[selftest] PASS|FAIL <test>: <what>"
    // in the log. Checks: bc.data.* (here), bc.battle.* (bc-battle's and the junction's registered battle tests:
    // BcSelfTests.KitEntries). Beside the older commands (bcdata, bcskills, bcselftest) for one more test batch.
    static class BcChecks
    {
        // the kit's harness glue (PrKit.SelfTestHarness: the polled `selftest` command, the field/battle fixtures);
        // BC adds its "seed" fixture
        internal static void Register()
        {
            SelfTests.Fixtures["seed"] = t => new[] { t.Until(() => Plugin.BcMode && BcSeeds.Active != null, 60, "a Beyond Chaos seed active") };
            SelfTestHarness.Extra = BcSelfTests.KitEntries;     // + bc-battle's registered battle tests: bc.battle.<name>
            SelfTestHarness.Install(typeof(Plugin).Assembly, line => Plugin.L.LogInfo(line));
        }

        // per frame (BcHarness.Update): the runner on the game's clock
        internal static void Update() => SelfTestHarness.Update();

        // the active seed's bc_seed.json (what the generator wrote: coral, espers, event_gifts, auction_items...)
        static JsonElement SeedJson()
        {
            var s = BcSeeds.Active;
            var path = s?.Dir == null ? null : Path.Combine(s.Dir, "bc_seed.json");
            if (path == null || !File.Exists(path)) return default;
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            return doc.RootElement.Clone();
        }

        static string Text(string key)
        {
            try { return PrKit.GameText.Get(key) ?? ""; }
            catch (Exception) { return ""; }
        }

        // --- the seed's data (bc-seeds) ---------------------------------------------------------------------------

        [SelfTest("bc.data.coliseum", Needs = "seed", Doc = "the game's own Colosseum lookups answer the seed's matches (kit SnesColiseum)")]
        static IEnumerable<TestStep> Coliseum(TestContext t)
        {
            var s = BcSeeds.Active;
            if (s.Coliseum.Count == 0) { t.Note("no Colosseum matches in this seed"); yield break; }
            var bad = SnesColiseum.Check(s.Coliseum.Keys, 255);
            t.Check(bad == null, bad == null ? $"{s.Coliseum.Count} wagers answered from the seed" : "differs: " + bad);
        }

        [SelfTest("bc.data.weapons", Needs = "field", Doc = "the Runic/Bushido weapon lists are the seed's (kit SnesCommandWeapons)")]
        static IEnumerable<TestStep> Weapons(TestContext t)
        {
            yield return t.Until(() => SnesCommandWeapons.Apply(), 30, "the game's weapon lists");
            var s = BcSeeds.Active;
            foreach (var command in new[] { "runic", "bushido" })
                if (s != null && s.CommandWeapons.TryGetValue(command, out var want))
                    t.Check(SnesCommandWeapons.Last.Contains($"{command}: ") && SnesCommandWeapons.Last.Contains(want.Length.ToString()),
                            $"{command}: the seed's {want.Length} weapons ({SnesCommandWeapons.Last})");
        }

        [SelfTest("bc.data.auction", Needs = "seed", Doc = "the auction's four sales give BC's items (BcData's GetItem hook) and name them")]
        static IEnumerable<TestStep> Auction(TestContext t)
        {
            var s = BcSeeds.Active;
            if (s.AuctionItems.Count == 0) { t.Note("no auction changes (`t` off)"); yield break; }
            t.Check(s.AuctionItems.Count == 4, $"{s.AuctionItems.Count} sales changed");
            foreach (var key in new[] { "E0424_00_111_a_01", "E1055_00_111_a_01", "E0751_00_111_a_01", "E0752_00_111_a_01" })
                t.Check(Text(key).StartsWith("...a fine "), $"{key}: {Text(key)}");
        }

        [SelfTest("bc.data.text", Needs = "seed", Doc = "the seed's text as the game reads it: the Coral, esper names, gift lines (bc_data, bc_gifts)")]
        static IEnumerable<TestStep> SeedText(TestContext t)
        {
            var j = SeedJson();
            t.Check(j.ValueKind == JsonValueKind.Object, "bc_seed.json read");
            if (j.ValueKind != JsonValueKind.Object) yield break;
            if (j.TryGetProperty("coral", out var coral))
                t.Check(Text("MSG_KEY_NAME_06").Contains(coral.GetString()), $"the Coral is {coral.GetString()}: {Text("MSG_KEY_NAME_06")}");
            if (j.TryGetProperty("espers", out var espers) && espers.ValueKind == JsonValueKind.Object)
            {
                if (espers.TryGetProperty("Ragnarok", out var sword))
                    t.Check(Text("MSG_WEAPON_NAME_25").EndsWith(sword.GetString()), $"the Ragnarok sword is {Text("MSG_WEAPON_NAME_25")}");
                if (espers.TryGetProperty("Ifrit", out var ifrit))
                    t.Check(Text("E0399_00_398_a_01").Contains(ifrit.GetString()), $"Ifrit's gift line: {Text("E0399_00_398_a_01")}");
            }
            if (j.TryGetProperty("event_gifts", out var gifts) && gifts.ValueKind == JsonValueKind.Object)
            {
                int n = 0, named = 0;
                foreach (var g in gifts.EnumerateObject())
                {
                    var line = Text($"BC_GIFT_{g.Name}_0");
                    if (line == "") continue;
                    n++;
                    if (line.Contains(g.Value.GetString().Replace(" gil", ""))) named++;
                }
                t.Check(n == 0 || named == n, $"gift lines naming BC's item: {named} of {n}");
            }
        }
    }
}
