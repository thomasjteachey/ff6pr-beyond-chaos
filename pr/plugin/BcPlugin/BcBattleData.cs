using System;
using System.IO;
using System.Text.Json;
using PrKit;

namespace BeyondChaos.PR
{
    // What the battle side (BcCommands, BcItems, BcCodes, BcJunction) reads from the active seed's folder,
    // apart from what BcSeeds parses: bc_seed.json (its "commands" with the targeting fields
    // tools/bc_commands.py adds) and bc_battle.json (tools/bc_items.py, bc_codes.py, bc_junction.py: one
    // section each). Read once per seed; Stamp changes whenever the active seed does.
    static class BcBattleData
    {
        static string loaded = "";
        internal static int Stamp;
        internal static JsonElement Seed, Battle;     // ValueKind Undefined: none

        // the active seed's data (cheap when unchanged: called from hooks and per frame)
        internal static void Refresh()
        {
            var s = Plugin.BcMode ? BcSeeds.Active : null;
            var id = s == null ? "" : s.Id + "|" + s.Dir;
            if (id == loaded) return;
            loaded = id;
            Stamp++;
            Seed = Read(s?.Dir, "bc_seed.json");
            Battle = Read(s?.Dir, "bc_battle.json");
        }

        static JsonElement Read(string dir, string name)
        {
            if (dir == null) return default;
            var path = Path.Combine(dir, name);
            if (!File.Exists(path)) return default;
            try
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(path));
                return doc.RootElement.Clone();
            }
            catch (Exception e)
            {
                Kit.Warn($"[bc] can't read {path}: {e.Message}");
                return default;
            }
        }

        // a section of bc_battle.json (or of bc_seed.json), or default
        internal static JsonElement Section(string name, bool seedJson = false)
        {
            Refresh();
            var root = seedJson ? Seed : Battle;
            return root.ValueKind == JsonValueKind.Object && root.TryGetProperty(name, out var v) ? v : default;
        }

        internal static string Str(this JsonElement e, string key, string d = "") =>
            e.ValueKind == JsonValueKind.Object && e.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : d;

        internal static int Int(this JsonElement e, string key, int d = 0) =>
            e.ValueKind == JsonValueKind.Object && e.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetInt32() : d;

        internal static bool Bool(this JsonElement e, string key) =>
            e.ValueKind == JsonValueKind.Object && e.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.True;
    }
}

namespace BeyondChaos.PR
{
    // the battle side's one entry (Plugin.cs: a Defer line and a BcRunner.Update line): codes, item
    // specials (BcCommands has its own Defer line; junction effects are the bc-junction session's)
    static class BcBattle
    {
        internal static void Patch(HarmonyLib.Harmony h)
        {
            BcCodes.Patch(h);
            BcItems.Patch(h);
            BcWeaponSpecials.Patch(h);
        }

        internal static void Update()
        {
            BcItems.Update();
            BcWeaponSpecials.Update();
            BcEquipAnything.Update();
            BcNoRng.Update();
            BcPlaysItself.Update();
            BcMagicNumbers.Update();
        }
    }
}
