using System;
using System.IO;
using HarmonyLib;
using PrKit;
using PrKit.Seeds;

namespace BeyondChaos.PR
{
    // Beyond Chaos's art per seed: the characters' sprites and portraits BC's makeover / `s` / `c` give
    // each SNES sprite slot (tools/bc_sprites.py) and remonsterate's monster images (tools/bc_monsters.py),
    // made by the generator into the seed's sprites/ folder (PNG sheets + art.json) and served by the
    // kit's ArtSwap: applied with the seed, no restart, the game's own art where a seed changes nothing.
    // Harness: bcart [load GROUP KEY | atlas GROUP ATLAS FRAME].
    static class BcSprites
    {
        // with the seed library's apply (startup, the screen's Play, a save's own seed, none)
        internal static void Init()
        {
            var prev = BcSeeds.Lib.AfterApply;
            BcSeeds.Lib.AfterApply = s =>
            {
                prev?.Invoke(s);
                Apply(s);
            };
        }

        internal static void Patch(Harmony h)
        {
            ArtSwap.Tag = "[bc art]";
            ArtSwap.Install(h);
            ArtHarness.Register("bcart", "the seed's");    // the seed's art (BC's sprites, portraits, monsters)
        }

        static void Apply(SeedInfo s)
        {
            try
            {
                var dir = s == null ? null : Path.Combine(s.Dir, "sprites");
                ArtSwap.Load(dir != null && File.Exists(Path.Combine(dir, "art.json")) ? dir : null);
            }
            catch (Exception e) { Kit.Warn($"[bc art] {e.Message}"); }
        }
    }
}
