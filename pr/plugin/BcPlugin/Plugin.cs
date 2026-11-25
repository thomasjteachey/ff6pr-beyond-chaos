using System;
using System.Collections.Generic;
using System.IO;
using BepInEx;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using PrKit;
using PrKit.Seeds;
using UnityEngine;

namespace BeyondChaos.PR
{
    // Beyond Chaos (CE 6.1.3) for the Pixel Remaster: make and play BC seeds inside the game, with BC's
    // flags, codes and modes, no restart (the kit's seed system: PrKit/Seeds; the generator is BC's own
    // code, tools/bc_seed.py, so a seed is BC's exe's seed). A mod of its own: Worlds Collide and Brave New
    // World are separate mods, one active per install. PORTING.md "Beyond Chaos port" is the plan.
    [BepInPlugin(Guid, "Beyond Chaos (Pixel Remaster)", Version)]
    public class Plugin : BasePlugin
    {
        public const string Guid = "ff6mod.beyondchaos";
        public const string Version = "0.1.0";
        public const string ModFolder = "BeyondChaos";   // its Magicite folder and its data folder (BepInEx/BeyondChaos)
        internal static ManualLogSource L;
        internal static string Folder;
        internal static bool BcMode;
        internal static FeatureHost Features;
        internal static FlagSet FlagDefs;
        internal static ModDataDir Data;
        internal static BcScreen Screen;

        public override void Load()
        {
            L = Log;
            var clock = System.Diagnostics.Stopwatch.StartNew();
            Folder = Path.GetDirectoryName(typeof(Plugin).Assembly.Location) ?? ".";
            Kit.Init(Log, "Beyond Chaos");
            Data = new ModDataDir(ModFolder, "[bc]");
            Directory.CreateDirectory(Data.Root);
            BcSeeds.Gen.PythonSetting = Config.Bind("Generator", "Python", "",
                "python.exe for the seed generator. Empty: the bundled one (BepInEx/BeyondChaos/generator/python), else ProjectDir's pr/.venv.").Value.Trim();
            BcSeeds.Gen.ScriptSetting = Config.Bind("Generator", "Script", "",
                "bc_seed.py. Empty: the bundled one (generator/tools), else ProjectDir's pr/tools.").Value.Trim();
            BcSeeds.Gen.ProjectDir = Config.Bind("Generator", "ProjectDir", "",
                "The ff6-mod project folder, for a development PC without the bundle.").Value.Trim();
            BcSeeds.Lib.Keep = Config.Bind("Seeds", "Keep", 30, "How many generated seeds to keep (seeds that saves use are always kept).").Value;

            BcSeeds.Setup.Data = Data;
            BcSeeds.Setup.EnsureSetUp();   // a player's install: the game's files it works from, made from this game (once)
            // Beyond Chaos's data: its Magicite folder in Magicite's import directory
            BcMode = MagiciteDir.Has(ModFolder);
            if (BcMode) L.LogInfo($"Beyond Chaos's data: {MagiciteDir.FolderPath(ModFolder)}");
            else L.LogWarning($"Beyond Chaos's data isn't installed (no {ModFolder} folder in {MagiciteDir.ImportDir}): seeds are off");
            try
            {
                FlagDefs = FlagSet.Load(File.ReadAllText(Path.Combine(Folder, "bc_flags.json")));
            }
            catch (Exception e)
            {
                L.LogError($"can't read bc_flags.json: {e.Message}; the Beyond Chaos screen is off");
                return;
            }
            var harmony = new Harmony(Guid);
            // BC's own saves, apart from vanilla's and the other mods' (PrKit/ModSaves.cs), synced by Steam Cloud
            if (BcMode) ModSaves.Apply(harmony, ModFolder);
            // one controller, one input on the Steam Deck; the kit's test runs (a harness, no saves)
            Features = new FeatureHost(Config, harmony);
            Features.Add(new SingleGamepad());
            Features.ApplyAll();
            PadInput.Tag = "[bc]";
            PadInput.Patch(harmony);
            BcSeeds.Lib.Init();
            BcSeeds.Lib.Patch(harmony);
            BcSprites.Init();      // bc-sprites: the seed's art (characters, portraits, monsters) with each apply
            BcMusic.Init();        // bc-music: the seed's songs (johnnydmad) on the kit's SNES player, with each apply
            Screen = new BcScreen { Defs = FlagDefs, Lib = BcSeeds.Lib, Gen = BcSeeds.Gen, ModOn = () => BcMode };
            // the rest waits for the game's first frames (BcRunner, one part a frame): a shorter console
            // before the game window, as Worlds Collide does
            Defer("title menu", () =>
            {
                TitleMenuEntry.Label = "Beyond Chaos";
                TitleMenuEntry.Tag = "[bc]";
                TitleMenuEntry.Open = () => Screen.Show(true);
                TitleMenuEntry.Patch(harmony);
            });
            Defer("chest battles", () =>
            {
                ChestBattles.Tag = "[bc]";
                ChestBattles.Chests = () => BcMode ? BcSeeds.Active?.MonsterChests : null;
                ChestBattles.Patch(harmony);
            });
            // the SNES's battle rules (the kit's, from Worlds Collide): ATB fill and command waits, the status
            // clock (Regen/Sap/Poison ticks, Stop/Sleep/Reflect/Freeze/Condemned timers), auto-battle with
            // commands the PR only knows as an accessory's (BC deals them directly too)
            System.Func<bool> rules = () => BcMode && BcSeeds.Active != null;
            PrKit.Ff6.SnesAtb.On = rules; PrKit.Ff6.SnesAtb.Tag = "[bc]";
            PrKit.Ff6.SnesStatusTicks.On = rules; PrKit.Ff6.SnesStatusTicks.Tag = "[bc]";
            PrKit.Ff6.SnesAutobattle.On = rules; PrKit.Ff6.SnesAutobattle.Tag = "[bc]";
            Defer("atb", () => PrKit.Ff6.SnesAtb.Patch(harmony));
            Defer("status ticks", () => PrKit.Ff6.SnesStatusTicks.Patch(harmony));
            Defer("autobattle", () => PrKit.Ff6.SnesAutobattle.Patch(harmony));
            // the espers' level-up bonuses BC's `e` randomizes (the kit's, from Worlds Collide's)
            PrKit.Ff6.SnesEsperBonus.Seed = () => BcMode ? BcSeeds.Active?.EsperBonus : null;
            PrKit.Ff6.SnesEsperBonus.Vanilla = () => BcMode ? BcSeeds.Active?.EsperBonusVanilla : null;
            PrKit.Ff6.SnesEsperBonus.Tag = "[bc]";
            Defer("esper bonuses", () => PrKit.Ff6.SnesEsperBonus.Patch(harmony));
            Defer("esper restrictions", () => BcEspers.Patch(harmony));
            Defer("seed data", () => BcData.Patch(harmony));       // bc-seeds: Colosseum, Runic/Bushido weapons (kit SnesColiseum, SnesCommandWeapons)
            Defer("enemy ai", () => BcEnemyAi.Patch(harmony));
            Defer("commands", () => BcCommands.Patch(harmony));
            Defer("battle side", () => BcBattle.Patch(harmony));   // bc-battle: codes, item specials, junction effects
            Defer("junction", () => BcJunction.Patch(harmony));    // bc-junction: BC's junction effects (BcJunction*.cs)
            Defer("events", () => BcEvents.Patch(harmony));        // bc-events: BC's light events (SysCall "BC:...", shadowstays...)
            Defer("guide movement", () => BcGuide.Patch(harmony)); // the guide's Msg/Select must not also move the player
            Defer("art", () => BcSprites.Patch(harmony));          // bc-sprites: the kit's ArtSwap serves the seed's sprites/
            Defer("music", () => BcMusic.Patch(harmony));          // bc-music: BC's songs in place of the game's tracks (BcMusic.cs)
            Defer("doors", () => BcEntrances.Patch(harmony));      // strangejourney: the doors both worlds share, by world (BcEntrances.cs)
            Defer("harness", BcHarness.Register);
            var (py, script, err) = BcSeeds.Gen.Resolve();
            L.LogInfo($"Beyond Chaos {FlagDefs.Version}: {FlagDefs.Flags.Count} flags, {FlagDefs.Modes.Count} modes, {FlagDefs.Presets.Count} presets; generator: " +
                      (err ?? $"{py} {script}"));
            AddComponent<BcRunner>();
            L.LogInfo($"[bc] load: {clock.Elapsed.TotalSeconds:0.00} s; {Deferred.Count} parts wait for the first frames");
        }

        // the start's later parts, one a frame from the first (BcRunner.Update)
        static readonly Queue<(string Name, Action Run)> Deferred = new Queue<(string, Action)>();
        internal static bool Started => Deferred.Count == 0;

        static void Defer(string name, Action run) => Deferred.Enqueue((name, run));

        internal static void RunDeferred()
        {
            if (Deferred.Count == 0) return;
            var (name, run) = Deferred.Dequeue();
            try { run(); }
            catch (Exception e) { L.LogError($"[bc] {name} failed: {e.GetType().Name}: {e.Message}"); }
            if (Deferred.Count == 0) L.LogInfo("[bc] started");
        }
    }

    // per-frame driver (its own class name: IL2CPP registers runners by name)
    public class BcRunner : MonoBehaviour
    {
        public BcRunner(IntPtr ptr) : base(ptr) { }

        void Update()
        {
            if (!Plugin.Started)
            {
                Plugin.RunDeferred();
                return;
            }
            try
            {
                Plugin.Features?.Update();
                BcSeeds.Lib.Update();
                if (Plugin.Screen.Active) { Plugin.Screen.Poll(); Plugin.Screen.Update(); }
                ChestBattles.Update();
                BcEnemyAi.Update();
                PrKit.Ff6.SnesStatusTicks.Track();
                PrKit.Ff6.SnesAutobattle.Watch();
                BcGuide.Update();
                BcEvents.Update();                   // bc-events: the race modes' way back to the title
                BcBattle.Update();
                BcJunction.Update();                 // bc-junction: per-frame junction effects
                BcMusic.Update();
                BcData.Update();                     // bc-seeds: Runic/Bushido weapon lists follow the seed
                BcHarness.Update();
            }
            catch (Exception e) { Hooks.WarnOnce("bc-update", e); }
        }

        void OnGUI()
        {
            if (!Plugin.Started || Plugin.Screen == null || !Plugin.Screen.Active) return;
            try { Plugin.Screen.Draw(); }
            catch (Exception e) { Hooks.WarnOnce("bc-draw", e); }
        }
    }
}
