using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Battle;
using Last.Defaine;
using PrKit;
using Kind = BeyondChaos.PR.BcJunctionDamage.Kind;

namespace BeyondChaos.PR
{
    // The junction effects that don't share a hook file: registers each family's handlers on the act hub
    // (BcJunctionActs) and the damage hooks (BcJunctionDamage). Specs: pr/build/bc_junction/spec_*.json (BC's
    // patches read), the PR port's choices in bc-junction.md.
    static class BcJunctionEffects
    {
        internal const int AttackCommand = 1, MugCommand = 11;

        internal static void Register(Harmony h)
        {
            BcJunctionDamage.Rules.Add(("dog", Dog));
        }

        static bool Has(BattleUnitData u, string key) => BcJunction.Used(key) && BcJunction.Has(u, key);

        static int TargetCount => BcJunctionActs.Current?.Targets.Count ?? 1;

        // Dog (C2/2282): a single-target Attack/Mug strike at a party member with Dog: as if it had Interceptor,
        // blocked half the time (here a miss: the PR plays no dog for it)
        static void Dog(BcJunctionDamage.Calc c)
        {
            if (c.Kind != Kind.Fight || !c.Damaging || !BcJunction.IsPlayer(c.Target)) return;
            if (c.Command != AttackCommand && c.Command != MugCommand) return;
            if (TargetCount != 1 || !Has(c.Target, "dog")) return;
            if (BcJunction.Rng.Next(2) == 0) c.ForceMiss("dog");
        }
    }
}
