using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Battle;
using Last.Data;
using Last.Defaine;
using PrKit;

namespace BeyondChaos.PR
{
    // Junction effects at the start of a battle (BC's patch_junction_initiative: C2/25FA, the end of each
    // fighter's turn of vanilla's battle-start ATB loop C2/2575; BC's spec pr/build/bc_junction/spec_C.json).
    // Here: after the PR sets the battle's starting gauges (BattleProgressATB.InitATBGauge), for every fighter:
    //   First Strike   its gauge full (acts at once; monsters too)
    //   Regenerator    starts with Regen
    //   Auto-Reraise   starts with Reraise (a living fighter; one revival, not given again)
    //   Final Fenix    starts with Reraise; its revival casts Phoenix on its side instead (BcJunctionDeath)
    //   Plague         every fighter on the other side starts Doom's countdown (BC sets the countdown, not the
    //                  status: here the PR's Doom, whose timer the SNES status clock runs)
    //   Juggernaut     its level for the battle (round up) halved
    //   Burst          its level for the battle x1.5 (round up), at most 127
    static class BcJunctionStart
    {
        internal static int Starts, Full, Given;

        internal static void Register(Harmony h)
        {
            Hooks.Patch(h, typeof(BattleProgressATB), "InitATBGauge", typeof(BcJunctionStart), postfix: nameof(InitATBGauge_Postfix));
        }

        public static void InitATBGauge_Postfix(BattleProgressATB __instance)
        {
            BcJunctionStats.Clear();
            BcJunctionTicks.Clear();
            if (!BcJunction.On || !Hooks.IsA<BattleProgressATB>(__instance)) return;
            BcJunctionTriggers.BattleStart();
            try
            {
                Starts++;
                BcJunction.Invalidate();
                var all = BcJunction.Party().Concat(BcJunction.Enemies()).ToList();
                foreach (var u in all) For(u, __instance, all);
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-start", e); }
        }

        static bool Has(BattleUnitData u, string key) => BcJunction.Used(key) && BcJunction.Has(u, key);

        // one fighter's start-of-battle effects (the self-tests call it mid-battle)
        internal static void For(BattleUnitData u, BattleProgressATB atb, List<BattleUnitData> all)
        {
            var cc = BattlePlugManager.Instance()?.BattleConditionController;
            bool living = BcJunction.Alive(u);
            if (Has(u, "initiative") && atb != null)
            {
                atb.ChangeATBGaugeByUnitData(u, 100f);
                Full++;
            }
            if (Has(u, "regenerator")) Add(cc, u, ConditionType.Regeneration, "regenerator");
            BcJunctionMore.EsperDefenseStart(u);
            BcJunctionMore.InnateRunic(u);
            if (living && (Has(u, "auto_reraise") || Has(u, "final_fenix"))) Add(cc, u, ConditionType.Reraise, "reraise");
            if (Has(u, "plague"))
                foreach (var foe in all.Where(f => !BcJunction.SameSide(f, u) && BcJunction.Alive(f)))
                    if (!BcJunction.HasStatus(foe, ConditionType.Doom)) Add(cc, foe, ConditionType.Doom, "plague");
            bool jug = Has(u, "juggernaut"), burst = Has(u, "burst");
            if (!jug && !burst) return;
            int lv = BcJunctionStats.RawLevel(u);
            int now = lv;
            if (jug) now = BcJunctionMath.JuggernautStart(now);
            if (burst) now = BcJunctionMath.BurstStart(now);
            BcJunctionStats.SetLevel(u, now);
            Kit.Info($"{BcJunction.Tag} {BcJunction.Who(u)}: level {lv} -> {now} for the battle ({(jug ? "Juggernaut" : "")}{(jug && burst ? " + " : "")}{(burst ? "Burst" : "")})");
        }

        internal static BattleProgressATB Atb() => BattlePlugManager.Instance()?.BattleProgress?.TryCast<BattleProgressATB>();
        internal static float Gauge(BattleUnitData u) { try { return Atb()?.GetAtbGaugeByUnitData(u) ?? -1; } catch { return -1; } }

        static void Add(BattleConditionController cc, BattleUnitData u, ConditionType t, string why)
        {
            if (cc == null || u == null || BcJunction.HasStatus(u, t)) return;
            cc.InterruptAddCondition(u, t);
            Given++;
            Hooks.NoteOnce("bc-junction-start-" + why, () => $"{BcJunction.Tag} {BcJunction.Who(u)} starts the battle with {t} ({why})");
        }


        internal static int LevelOf(BattleUnitData u) => BcJunctionStats.Level(u);

    }
}
