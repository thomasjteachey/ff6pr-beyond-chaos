using System;
using System.IO;
using HarmonyLib;
using PrKit;
using PrKit.Seeds;
using PrKit.Snes;

namespace BeyondChaos.PR
{
    // Beyond Chaos's music (johnnydmad / johnnyachaotic): each seed's songs (tools/bc_music.py: BC's
    // compiled songs and samples, music/songs.json + songs.bin, and what plays where, music/bc_music.json
    // in the kit's BgmRules format) on the kit's SNES music player, in place of the game's tracks
    // (PrKit/Snes: SnesBgm does the game side). Where BC's shuffle put one of FF6's own songs, the game
    // plays its own track for it. Harness: bcmusic [play SLOT | stop | suspend | resume | jump | log | state].
    static class BcMusic
    {
        static string loadedDir;

        internal static void Init()
        {
            var prev = BcSeeds.Lib.AfterApply;
            BcSeeds.Lib.AfterApply = s =>
            {
                prev?.Invoke(s);
                Load(s);
            };
        }

        static void Load(SeedInfo s)
        {
            string dir = s == null ? null : Path.Combine(s.Dir, "music");
            if (dir != null && !File.Exists(Path.Combine(dir, "songs.json"))) dir = null;
            if (dir == loadedDir) return;
            loadedDir = dir;
            try
            {
                if (dir == null)
                {
                    SnesBgm.SetMusic(null, null);
                    return;
                }
                var pack = SongPack.Load(dir);
                var rules = BgmRules.Load(File.ReadAllText(Path.Combine(dir, "bc_music.json")));
                if (rules.Jumps.Count == 0)
                {
                    // seeds made before bc_music.py wrote them: Dancing Mad's parts 2 and 3
                    rules.Jumps.Add((66, 0x3B));
                    rules.Jumps.Add((67, 0x3B));
                }
                SnesBgm.SetMusic(pack, rules);
                int own = 0;
                foreach (var kv in rules.Songs) if (kv.Value.GameTrack == null) own++;
                Kit.Info($"[bc music] {pack.Songs.Count} songs ({own} BC's), {pack.SampleCount} samples, {rules.Maps.Count} area songs, " +
                         $"{rules.Battles.Count} formations from {dir}");
            }
            catch (Exception e)
            {
                SnesBgm.SetMusic(null, null);
                Kit.Warn($"[bc music] {dir}: {e.GetType().Name}: {e.Message}; the game's own music");
            }
        }

        internal static void Patch(Harmony h)
        {
            SnesBgm.Tag = "[bc music]";
            SnesBgm.Name = "bc music";
            SnesBgm.On = () => Plugin.BcMode;
            SnesBgm.Patch(h);
            SnesBgm.RegisterHarness("bcmusic");
        }

        internal static void Update() => SnesBgm.Update();
    }
}
