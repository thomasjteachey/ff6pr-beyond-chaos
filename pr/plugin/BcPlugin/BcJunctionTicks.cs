using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Battle;
using Last.Defaine;
using PrKit;

namespace BeyondChaos.PR
{
    // Junction effects on the status ticks (BC's patch_junction_leech, mp_regen, miasma; spec_B.json):
    //   MP Regen     a holder's Regen restores MP (and Sap drains MP) instead of HP: here the tick's HP change
    //                undone and the same share of max MP given or taken
    //   Leech        a fighter's damage tick (Poison, Sap) heals every living holder on the other side by as much
    //                (BC also gives fighters without Regen a Sap-like tick while a foe has Leech: needs the kit
    //                status clock's step hook, asked of the BC lead)
    // Time Font/Sink, Miasma, Regenerator's ticks and Juggernaut/Burst's drift: BcJunctionClock (the kit's clock hooks).
    static class BcJunctionTicks
    {
        internal static int Leeched, MpTicks, Drifts;

        internal static void Register(Harmony h)
        {
            Hooks.Patch(h, typeof(RegenerationConditionFunction), "Update", typeof(BcJunctionTicks), prefix: nameof(Tick_Prefix), postfix: nameof(Regen_Postfix));
            Hooks.Patch(h, typeof(SlipConditionFunction), "Update", typeof(BcJunctionTicks), prefix: nameof(Tick_Prefix), postfix: nameof(Sap_Postfix));
            Hooks.Patch(h, typeof(PoisonConditionFunction), "UpdateSub", typeof(BcJunctionTicks), prefix: nameof(Tick_Prefix), postfix: nameof(Poison_Postfix));
        }

        public static void Tick_Prefix(BattleConditionFunction __instance, out (int Hp, int Mp) __state)
        {
            __state = (-1, -1);
            if (!BcJunction.On || __instance == null) return;
            var p = __instance.BattleUnitData?.BattleUnitDataInfo?.Parameter;
            if (p != null) __state = (p.CurrentHP, p.CurrentMP);
        }

        public static void Regen_Postfix(BattleConditionFunction __instance, (int Hp, int Mp) __state) => After(__instance, __state, false);
        public static void Sap_Postfix(BattleConditionFunction __instance, (int Hp, int Mp) __state) => After(__instance, __state, true);
        public static void Poison_Postfix(BattleConditionFunction __instance, (int Hp, int Mp) __state) => After(__instance, __state, true);

        static void After(BattleConditionFunction f, (int Hp, int Mp) was, bool damage)
        {
            if (was.Hp < 0) return;
            try
            {
                var u = f.BattleUnitData;
                var p = u?.BattleUnitDataInfo?.Parameter;
                if (p == null) return;
                int delta = p.CurrentHP - was.Hp;
                if (delta == 0) return;
                bool sap = f.TryCast<SlipConditionFunction>() != null, regen = f.TryCast<RegenerationConditionFunction>() != null;
                if ((regen || sap) && BcJunction.Used("mp_regen") && BcJunction.Has(u, "mp_regen"))
                {
                    int maxHp = Math.Max(1, p.ConfirmedMaxHp()), maxMp = p.ConfirmedMaxMp();
                    p.CurrentHP = was.Hp;
                    p.CurrentMP = Math.Max(0, Math.Min(maxMp, p.CurrentMP + BcJunctionMath.MpTick(delta, maxHp, maxMp)));
                    MpTicks++;
                    return;
                }
                if (delta < 0 && damage && BcJunction.Used("leech"))
                    foreach (var h in (BcJunction.IsPlayer(u) ? BcJunction.Enemies() : BcJunction.Party()).Where(BcJunction.Alive).ToList())
                    {
                        if (!BcJunction.Has(h, "leech")) continue;
                        var hp = h.BattleUnitDataInfo.Parameter;
                        hp.CurrentHP = Math.Min(hp.ConfirmedMaxHp(), hp.CurrentHP - delta);
                        Leeched++;
                    }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-tick", e); }
        }

        // Juggernaut / Burst's drift: on the kit's status clock (BcJunctionClock, SnesStatusClock.StepKind)
        internal static void Clear() { }
    }
}
