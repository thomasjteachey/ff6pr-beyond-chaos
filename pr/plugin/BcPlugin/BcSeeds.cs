using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using PrKit;
using PrKit.Ff6;
using PrKit.Seeds;

namespace BeyondChaos.PR
{
    // Beyond Chaos's seeds made in game (BepInEx/BeyondChaos/seeds/<id>/, tools/bc_seed.py: BC's own
    // code, then the shared porter) on the kit's seed library: tables and text set live, chest maps /
    // AI slots / data files swapped in the BeyondChaos Magicite folder (tools/bc_live.py), each save
    // remembers its seed. What a BC seed holds beyond its tables: bc_seed.json.
    static class BcSeeds
    {
        public sealed class Seed : SeedInfo
        {
            public string Mode = "normal", SeedString = "";
            public SnesAiData SnesAi;                                        // every monster's BC script, run by BcEnemyAi
            public HashSet<int> Magitek = new HashSet<int>();                // characters dealt MagiTek as a command
            public Dictionary<int, int> MonsterChests = new Dictionary<int, int>();   // chest flag -> party (ChestBattles)
            public HashSet<string> Boxes = new HashSet<string>();            // the SNES boxes' PR scripts
            public Dictionary<int, int> EsperBonusVanilla = new Dictionary<int, int>(), EsperBonus = new Dictionary<int, int>();
            public Dictionary<int, int[]> Coliseum = new Dictionary<int, int[]>();
            public Dictionary<string, int[]> CommandWeapons = new Dictionary<string, int[]>();
            public Dictionary<int, int> AuctionItems = new Dictionary<int, int>();   // sale's vanilla content -> BC's (bc_data)
            public Dictionary<int, Command> Commands = new Dictionary<int, Command>();   // BC's commands by PR command id
            public List<(string Title, string[] Lines)> Guide = new List<(string, string[])>();   // tools/bc_guide.py
            public int GuideMessages;                                        // the in-game guide's messages (sc_bc_guide; BcGuide)
        }

        // one of BC's replaced commands (tools/bc_commands.py): what its PR command row runs, and the rest
        public sealed class Command
        {
            public string Kind = "skill", Name = "", BcName = "";
            public int Ability, Count = 1;
            public int[] Abilities = System.Array.Empty<int>();
        }

        internal static readonly SeedGenerator Gen = new SeedGenerator
        {
            Tag = "bc", Script = "bc_seed.py", SeedJson = "bc_seed.json", BundleDir = () => Plugin.Data?.Generator ?? "",
        };

        // a player's install: BC's copies of the game's own files (the generator's vanilla folder and cache, the
        // baseline, the Magicite folder), made from this game on its first start (tools/bc_gamedata.py with the
        // bundled Python; the zip carries none of them). Plugin.Load runs it before anything reads them.
        internal static readonly GameData Setup = new GameData
        {
            Tag = "[bc]", Title = "Beyond Chaos", Script = "bc_gamedata.py", MagiciteFolder = Plugin.ModFolder, Generator = Gen,
            Info = msg => Plugin.L.LogInfo(msg), Fail = msg => Plugin.L.LogError(msg),
        };

        internal static readonly SeedLibrary Lib = new SeedLibrary
        {
            Tag = "[bc]", TestTag = "[bc test]", JsonName = "bc_seed.json",
            Root = () => Plugin.Data.Seeds, BaselineDir = () => Plugin.Data.Baseline,
            ModDir = () => MagiciteDir.FolderPath(Plugin.ModFolder),
            Parse = (id, dir) => Parse(id, dir),
            ModOn = () => Plugin.BcMode,
            Warn = msg => Plugin.Screen?.Toast(msg),
            // whole data files a BC seed swaps (the Veldt's misc asset, battle_extra_data, scripts: the guide's
            // and BC's light events' (BcEvents); only the stems of files that changed are offered): the game's
            // cached copies go too, so the next load reads the seed's
            EvictAlso = name => name == "serial_misc_assets" || name == "battle_extra_data" || name == BcGuide.Script
                                || name.StartsWith("sc_"),
        };

        public static Seed Active => (Seed)Lib.Active;

        static Seed Parse(string id, string dir)
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(dir, "bc_seed.json")));
            var r = doc.RootElement;
            var s = new Seed { Id = id, Dir = dir };
            SeedLibrary.ReadCommon(s, r);
            if (r.TryGetProperty("mode", out var m) && m.ValueKind == JsonValueKind.String) s.Mode = m.GetString();
            if (r.TryGetProperty("seed_string", out var ss) && ss.ValueKind == JsonValueKind.String) s.SeedString = ss.GetString();
            if (r.TryGetProperty("snes_ai", out var sai) && sai.ValueKind == JsonValueKind.Object) s.SnesAi = SnesAiData.Parse(sai);
            if (r.TryGetProperty("magitek", out var mt))
                foreach (var x in mt.EnumerateArray()) s.Magitek.Add(x.GetInt32());
            if (r.TryGetProperty("monster_chests", out var mch) && mch.ValueKind == JsonValueKind.Object)
                foreach (var p in mch.EnumerateObject()) s.MonsterChests[int.Parse(p.Name)] = p.Value.GetInt32();
            if (r.TryGetProperty("boxes", out var bxs))
                foreach (var x in bxs.EnumerateArray()) s.Boxes.Add(x.GetString());
            if (r.TryGetProperty("esper_bonus", out var eb))
            {
                foreach (var x in eb.GetProperty("vanilla").EnumerateArray()) s.EsperBonusVanilla[x[0].GetInt32()] = x[1].GetInt32();
                foreach (var x in eb.GetProperty("seed").EnumerateArray()) s.EsperBonus[x[0].GetInt32()] = x[1].GetInt32();
            }
            if (r.TryGetProperty("coliseum", out var col))
                foreach (var x in col.EnumerateArray())
                    s.Coliseum[x[0].GetInt32()] = new[] { x[1].GetInt32(), x[2].GetInt32(), x[3].GetInt32(), x[4].GetInt32(), x[5].GetInt32(),
                                                          x.GetArrayLength() > 6 ? x[6].GetInt32() : 0 };
            if (r.TryGetProperty("command_weapons", out var cwp))
                foreach (var p in cwp.EnumerateObject())
                    s.CommandWeapons[p.Name] = p.Value.GetProperty("seed").EnumerateArray().Select(x => x.GetInt32()).ToArray();
            if (r.TryGetProperty("auction_items", out var auc) && auc.ValueKind == JsonValueKind.Object)
                foreach (var p in auc.EnumerateObject())
                    if (int.TryParse(p.Name, out int sale) && p.Value.ValueKind == JsonValueKind.Number) s.AuctionItems[sale] = p.Value.GetInt32();
            if (r.TryGetProperty("guide", out var guide) && guide.ValueKind == JsonValueKind.Array)
                foreach (var g in guide.EnumerateArray())
                    s.Guide.Add((g.GetProperty("title").GetString(),
                                 g.GetProperty("lines").EnumerateArray().Select(x => x.GetString()).ToArray()));
            if (r.TryGetProperty("guide_messages", out var gm) && gm.ValueKind == JsonValueKind.Number) s.GuideMessages = gm.GetInt32();
            if (r.TryGetProperty("commands", out var cmds) && cmds.ValueKind == JsonValueKind.Object)
                foreach (var p in cmds.EnumerateObject())
                {
                    var c = p.Value;
                    string Str(string k) => c.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : "";
                    int Int(string k, int d) => c.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetInt32() : d;
                    s.Commands[int.Parse(p.Name)] = new Command
                    {
                        Kind = c.TryGetProperty("chain", out var ch) && ch.ValueKind == JsonValueKind.True ? "chain" : Str("kind"),
                        Name = Str("name"), BcName = Str("bc_name"), Ability = Int("ability", 0), Count = Int("count", 1),
                        Abilities = c.TryGetProperty("abilities", out var ab) && ab.ValueKind == JsonValueKind.Array
                            ? ab.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.Number).Select(x => x.GetInt32()).ToArray()
                            : System.Array.Empty<int>(),
                    };
                }
            return s;
        }

        public static string ModeLabel(string mode) =>
            Plugin.FlagDefs?.Modes.FirstOrDefault(m => m.Name == mode)?.Label ?? mode;
    }
}
