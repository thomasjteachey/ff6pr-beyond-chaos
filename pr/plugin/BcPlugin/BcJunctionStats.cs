using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Battle;
using Last.Data;
using PrKit;

namespace BeyondChaos.PR
{
    // Junction effects that change a fighter's numbers for the rest of a battle (BC writes the battle copies:
    // $3B18 level, $3C1C max HP, $3BB8/$3BB9 Def/MDef, $3B54/$3B55 Evade/MBlock):
    //   Juggernaut / Burst (start of battle), Discordant (level's ones digit), Corrosive (max HP / MP lowered),
    //   Juggler (Def <-> MDef, Evade <-> MBlock swapped to suit the last hit).
    // The PR's stat getters (Player/EnemyCharacterParameter.Confirmed*) answer with the battle's changes, keyed by
    // the parameter object (a party member's battle parameters and its character record's both); cleared when a
    // battle starts and ignored outside battles.
    static class BcJunctionStats
    {
        sealed class Change
        {
            public int? Level;            // the level for the battle
            public int MaxHpLess, MaxMpLess;
            public bool SwapDef, SwapEvade;
        }

        static readonly Dictionary<IntPtr, Change> changes = new Dictionary<IntPtr, Change>();
        internal static Func<BattleUnitData, int> MaxMp;      // Blood/Gold Mage: a fighter's max MP (-1: the game's)
        [ThreadStatic] static bool reading;

        internal static void Register(Harmony h)
        {
            foreach (var t in new[] { typeof(PlayerCharacterParameter), typeof(EnemyCharacterParameter) })
            {
                Hooks.Patch(h, t, "ConfirmedLevel", typeof(BcJunctionStats), postfix: nameof(Level_Postfix));
                Hooks.Patch(h, t, "ConfirmedMaxHp", typeof(BcJunctionStats), postfix: nameof(MaxHp_Postfix));
                Hooks.Patch(h, t, "ConfirmedMaxMp", typeof(BcJunctionStats), postfix: nameof(MaxMp_Postfix));
                Hooks.Patch(h, t, "ConfirmedDefense", typeof(BcJunctionStats), postfix: nameof(Defense_Postfix));
                Hooks.Patch(h, t, "ConfirmedAbilityDefense", typeof(BcJunctionStats), postfix: nameof(AbilityDefense_Postfix));
                Hooks.Patch(h, t, "ConfirmedEvasionRate", typeof(BcJunctionStats), postfix: nameof(Evasion_Postfix));
                Hooks.Patch(h, t, "ConfirmedAbilityEvasionRate", typeof(BcJunctionStats), postfix: nameof(AbilityEvasion_Postfix));
            }
        }

        internal static void Clear() { lock (changes) changes.Clear(); }

        static IEnumerable<IntPtr> Keys(BattleUnitData u)
        {
            var p = u?.BattleUnitDataInfo?.Parameter;
            if (p != null) yield return p.Pointer;
            var oc = u?.GetOwnedCharacterData()?.Parameter;
            if (oc != null && (p == null || oc.Pointer != p.Pointer)) yield return oc.Pointer;
        }

        static Change For(BattleUnitData u, Func<Change, bool> edit)
        {
            Change first = null;
            var keys = Keys(u).ToList();
            lock (changes)
                foreach (var k in keys)
                {
                    if (!changes.TryGetValue(k, out var c)) changes[k] = c = new Change();
                    edit(c);
                    first ??= c;
                }
            return first;
        }

        // the game's own value (no battle change), for working changes out
        internal static T Raw<T>(Func<T> read)
        {
            bool was = reading;
            reading = true;
            try { return read(); }
            finally { reading = was; }
        }

        internal static int RawLevel(BattleUnitData u) => Raw(() => u?.BattleUnitDataInfo?.Parameter?.ConfirmedLevel() ?? 0);
        internal static void SetLevel(BattleUnitData u, int level) => For(u, c => { c.Level = Math.Max(1, Math.Min(99, level)); return true; });
        internal static int Level(BattleUnitData u) => u?.BattleUnitDataInfo?.Parameter?.ConfirmedLevel() ?? 0;
        internal static void LowerMax(BattleUnitData u, int hp, int mp) => For(u, c => { c.MaxHpLess += hp; c.MaxMpLess += mp; return true; });
        internal static void Swap(BattleUnitData u, bool def, bool evade) => For(u, c => { if (def) c.SwapDef = !c.SwapDef; if (evade) c.SwapEvade = !c.SwapEvade; return true; });

        static bool Get(CharacterParameterBase p, out Change c)
        {
            c = null;
            if (reading || p == null || changes.Count == 0) return false;
            lock (changes)
                if (!changes.TryGetValue(p.Pointer, out c)) return false;
            var bm = BattlePlugManager.Instance();
            if (bm == null || !bm.IsBattle()) { lock (changes) changes.Clear(); return false; }
            return true;
        }

        public static void Level_Postfix(CharacterParameterBase __instance, ref int __result)
        {
            if (Get(__instance, out var c) && c.Level.HasValue) __result = c.Level.Value;
        }

        public static void MaxHp_Postfix(CharacterParameterBase __instance, ref int __result)
        {
            if (Get(__instance, out var c) && c.MaxHpLess > 0) __result = Math.Max(1, __result - c.MaxHpLess);
        }

        public static void MaxMp_Postfix(CharacterParameterBase __instance, ref int __result)
        {
            if (Get(__instance, out var c) && c.MaxMpLess > 0) __result = Math.Max(0, __result - c.MaxMpLess);
            if (MaxMp == null || reading || __instance == null || (!BcJunction.Used("blood_mage") && !BcJunction.Used("gold_mage"))) return;
            var bm = BattlePlugManager.Instance();
            if (bm == null || !bm.IsBattle()) return;
            foreach (var u in BcJunction.Party().Concat(BcJunction.Enemies()))
            {
                var p = u.BattleUnitDataInfo?.Parameter;
                var oc = u.GetOwnedCharacterData()?.Parameter;
                if (p?.Pointer != __instance.Pointer && oc?.Pointer != __instance.Pointer) continue;
                int m = MaxMp(u);
                if (m >= 0) __result = m;
                return;
            }
        }

        public static void Defense_Postfix(CharacterParameterBase __instance, ref int __result)
        {
            if (Get(__instance, out var c) && c.SwapDef) __result = Raw(() => __instance.ConfirmedAbilityDefense());
        }

        public static void AbilityDefense_Postfix(CharacterParameterBase __instance, ref int __result)
        {
            if (Get(__instance, out var c) && c.SwapDef) __result = Raw(() => __instance.ConfirmedDefense());
        }

        public static void Evasion_Postfix(CharacterParameterBase __instance, ref int __result)
        {
            if (Get(__instance, out var c) && c.SwapEvade) __result = Raw(() => __instance.ConfirmedAbilityEvasionRate());
        }

        public static void AbilityEvasion_Postfix(CharacterParameterBase __instance, ref int __result)
        {
            if (Get(__instance, out var c) && c.SwapEvade) __result = Raw(() => __instance.ConfirmedEvasionRate());
        }

        // Juggler: after a hit, the holder's guard suits the hit's kind: a physical hit makes Def >= MDef and Evade
        // >= MBlock (the PR's rates: higher is better), a magic one the reverse
        internal static void Juggle(BattleUnitData u, bool physical)
        {
            var p = u?.BattleUnitDataInfo?.Parameter;
            if (p == null) return;
            int def = p.ConfirmedDefense(), mdef = p.ConfirmedAbilityDefense();
            int eva = p.ConfirmedEvasionRate(), mbl = p.ConfirmedAbilityEvasionRate();
            bool swapDef = physical ? def < mdef : mdef < def;
            bool swapEva = physical ? eva < mbl : mbl < eva;
            if (swapDef || swapEva) Swap(u, swapDef, swapEva);
        }
    }
}
