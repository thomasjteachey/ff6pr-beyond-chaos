using System;
using System.Linq;
using HarmonyLib;
using PrKit.Ff6;

namespace BeyondChaos.PR
{
    // Beyond Chaos's randomized data that the game keeps in code or scripts, answered from the seed (bc_seed.json,
    // tools/seed_info.py, tools/bc_data.py):
    //  - the Colosseum's opponent, reward and whether the reward shows (the kit's SnesColiseum: `t`; fightclub hides)
    //  - the weapons that allow Runic and Bushido (the kit's SnesCommandWeapons: `i`)
    //  - the auction house's four sales (`t`): only they GetItem their vanilla contents (Angel Wings 287, Angel Ring
    //    288, Zephyr Cloak 291, Hero's Ring 300); each gives BC's item (the auctioneer's lines are the seed's text).
    //    As Worlds Collide's -ari (WcItems.GetItem_Prefix); to the kit when WC's moves there.
    // Off without a BC seed (the game's own tables and items).
    static class BcData
    {
        internal static string LastSale = "";

        public static void Patch(Harmony h)
        {
            SnesColiseum.Apply(h, new SnesColiseumMod
            {
                Name = "bc",
                On = () => Plugin.BcMode && BcSeeds.Active != null && BcSeeds.Active.Coliseum.Count > 0,
                Match = wager => BcSeeds.Active != null && BcSeeds.Active.Coliseum.TryGetValue(wager, out var m) ? m : null,
            });
            SnesCommandWeapons.Tag = "[bc]";
            SnesCommandWeapons.SeedKey = () => Plugin.BcMode && BcSeeds.Active != null ? BcSeeds.Active.Id : "";
            SnesCommandWeapons.Seed = command =>
                BcSeeds.Active != null && BcSeeds.Active.CommandWeapons.TryGetValue(command, out var list) ? list : null;
            var get = AccessTools.Method(typeof(global::Last.Interpreter.Instructions.External.Item), "GetItem");
            if (get != null) h.Patch(get, prefix: new HarmonyMethod(typeof(BcData), nameof(GetItem_Prefix)),
                                     postfix: new HarmonyMethod(typeof(BcData), nameof(GetItem_Postfix)));
            PrKit.Harness.Register("bcdata", _ => Check(),
                "bcdata: the game's own Colosseum lookups against the seed's matches, the Runic/Bushido weapon lists, the auction's sales");
            BcSkills.Patch(h);      // o/w: rages after wins, o: shared sets, lores and dances after wins
        }

        // per frame (BcRunner): the weapon lists follow the active seed
        public static void Update()
        {
            SnesCommandWeapons.Poll();
            BcSkills.Update();      // o/w: the party's skill sets (kit StartSkills, SnesRages), natural magic BC changed
        }

        public static void GetItem_Prefix(global::Last.Interpreter.MainCore mc, out int __state)
        {
            __state = 0;
            try
            {
                var iv = mc?.op?.iValues;
                var s = BcSeeds.Active;
                if (iv == null || iv.Length == 0 || !Plugin.BcMode || s == null) return;
                if (!s.AuctionItems.TryGetValue(iv[0], out int to)) return;
                __state = iv[0];
                iv[0] = to;
                LastSale = $"auction sale {__state} -> {to}";
                Plugin.L.LogInfo("[bc] " + LastSale);
            }
            catch (Exception e) { PrKit.Hooks.WarnOnce("bc-auction", e); }
        }

        public static void GetItem_Postfix(global::Last.Interpreter.MainCore mc, int __state)
        {
            if (__state == 0) return;
            try { mc.op.iValues[0] = __state; } catch (Exception e) { PrKit.Hooks.WarnOnce("bc-auction-restore", e); }
        }

        static string Check()
        {
            var s = BcSeeds.Active;
            if (s == null) return "bcdata: no seed";
            SnesCommandWeapons.Apply();
            var bad = s.Coliseum.Count == 0 ? null : SnesColiseum.Check(s.Coliseum.Keys, 255);
            return $"bcdata: coliseum {(s.Coliseum.Count == 0 ? "no matches" : bad == null ? $"ok ({s.Coliseum.Count} wagers)" : "FAILED " + bad)}; " +
                   $"weapons {SnesCommandWeapons.Last}; auction {s.AuctionItems.Count} sales {string.Join(",", s.AuctionItems)}" +
                   (LastSale != "" ? $" (last: {LastSale})" : "") +
                   // the seed's text as the game reads it (bc_data's Coral, bc_gifts' esper names and gift lines):
                   // against bc_seed.json's coral / espers / event_gifts
                   "; text " + string.Join(" | ", TextKeys.Select(k => $"{k}={Text(k)}"));
        }

        static readonly string[] TextKeys = { "MSG_KEY_NAME_06", "MSG_MAP_NAME_54", "MSG_WEAPON_NAME_25",
                                              "E0399_00_398_a_01", "E0450_00_408_a_02", "BC_GIFT_B30E5_0" };

        static string Text(string key)
        {
            try { return PrKit.GameText.Get(key) ?? "(none)"; }
            catch (Exception e) { return "(" + e.GetType().Name + ")"; }
        }
    }
}
