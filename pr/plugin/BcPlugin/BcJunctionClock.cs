using System;
using System.Linq;
using Last.Battle;
using Last.Defaine;
using PrKit;
using PrKit.Ff6;

namespace BeyondChaos.PR
{
    // Junction effects on the SNES status clock (BC's patch_junction_time_font_sink C2/09E4, patch_junction_miasma
    // C2/5AD6; spec pr/data/bc_junction_spec.json; the numbers in BcJunctionMath, tested offline):
    //   Time Font / Sink   every fighter's clock add ($3ADD) x1.25 per net living Font, x0.75 per net Sink, cap 255
    //                      (status timers and Poison/Regen ticks; not the ATB)
    //   Miasma             a Poisoned fighter's step: each living holder's 25% roll makes it a Poison step
    //   Regenerator        a Regen holder's step: 50% a Regen step (after Miasma)
    //   Juggernaut / Burst each step, 50%: the battle level drifts up / down (BcJunctionMath.JuggernautStep/BurstStep)
    // BC replaces the 8-step table's slot where the step reads it (after the tick is sent): the kit's StepKind is
    // that read (the table's kind 'R' Regen/Sap, 'P' Poison, '-' in; the kind to use out; not called while stopped).
    static class BcJunctionClock
    {
        internal static int Filtered, Forced, Drifts;

        internal static void Register()
        {
            SnesStatusTicks.Configure = Configure;
        }

        static void Configure(BattleUnitData u, SnesStatusClock clock)
        {
            if (!BcJunction.On || u == null || clock == null) { if (clock != null) { clock.AddFilter = null; clock.StepKind = null; } return; }
            int net = (BcJunction.Used("time_font") ? BcJunction.CountLiving("time_font") : 0) -
                      (BcJunction.Used("time_sink") ? BcJunction.CountLiving("time_sink") : 0);
            clock.AddFilter = net == 0 ? null : (Func<int, int>)(add => { Filtered++; return BcJunctionMath.TimeAdd(add, net); });
            bool miasma = BcJunction.Used("miasma"), regen = BcJunction.Used("regenerator") && BcJunction.HasRaw(u, "regenerator");
            bool drift = BcJunction.HasRaw(u, "juggernaut") || BcJunction.HasRaw(u, "burst");
            clock.StepKind = !(miasma || regen || drift) ? null : (Func<SnesStatusClock, char, char>)((c, kind) => Step(u, c, kind));
        }

        static char Step(BattleUnitData u, SnesStatusClock c, char kind)
        {
            // Juggernaut / Burst: BC's main-level-modulation, the same 50% roll for both
            if ((BcJunction.HasRaw(u, "juggernaut") || BcJunction.HasRaw(u, "burst")) && BcJunction.Rng.Next(2) == 0)
            {
                int baseLv = BcJunctionStats.RawLevel(u), lv = BcJunctionStats.Level(u), now = lv;
                if (BcJunction.Has(u, "juggernaut")) now = BcJunctionMath.JuggernautStep(now, baseLv, BcJunction.Rng.Next);
                if (BcJunction.Has(u, "burst")) now = BcJunctionMath.BurstStep(now, baseLv, BcJunction.Rng.Next);
                if (now != lv) { BcJunctionStats.SetLevel(u, now); Drifts++; }
            }
            bool poisoned = (c.Statuses & SnesStatus.Poison) != 0;
            bool regen = (c.Statuses & SnesStatus.Regen) != 0 && BcJunction.Has(u, "regenerator");
            int holders = poisoned && BcJunction.Used("miasma") ? BcJunction.Living().Count(h => BcJunction.HasRaw(h, "miasma")) : 0;
            int slot = kind == 'R' ? 0 : kind == 'P' ? 2 : 1;
            int now2 = BcJunctionMath.StepSlot(slot, poisoned, holders, regen, BcJunction.Rng.Next);
            if (now2 == slot) return kind;
            Forced++;
            return now2 == 0 ? 'R' : now2 == 2 ? 'P' : kind;
        }
    }
}
