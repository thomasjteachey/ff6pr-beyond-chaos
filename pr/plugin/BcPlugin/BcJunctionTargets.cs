using System;
using System.Collections.Generic;
using System.Linq;
using Last.Battle;
using PrKit;

namespace BeyondChaos.PR
{
    // Junction effects on whom an act lands on (BC's patch_junction_taunt_salve: C2/58ED, the step where vanilla
    // reduces an act's targets to one at random, and C2/5930, the target clean-up). Here: the act hub's "about
    // to land" step (BcJunctionActs.Before), on an act with one target on the other side from the attacker.
    //   Taunt       the target's side: monsters with Taunt always, party members with Taunt each on a 50% roll,
    //               are the candidates. A monster's act goes to one of them at random (even from another
    //               taunter); a party member's act goes to one of them unless its target is one already.
    //   Camouflage  after Taunt: a target with Camouflage passes the act to a random teammate without it (if any).
    // Cover (BC's patch_junction_cover, C2/1254 in vanilla's cover routine; the PR's own cover step is
    // TargetFunction.ProtectExtractTarget, run for physical strikes: BNW's CoverRules found it):
    //   True Paladin  a strike at one fighter is taken by a random fighter with True Paladin from the pool (no
    //                 Near Fatal needed, unlike the True Knight relic)
    //   Popularity    a strike at a fighter with Popularity is taken by a random fighter from the pool
    //   the pool: able fighters other than the target (not Wound/Petrify/Vanish/Zombie/Sleep/Confuse/Stop/
    //   Hide/Freeze), 50% the target's side only, else (Popular target) both sides. The game's own cover
    //   (True Knight) only when neither gives a guard.
    // (BC's spec: pr/build/bc_junction/spec_C.json; the PR port's notes: bc-junction.md.)
    static class BcJunctionTargets
    {
        internal static int Taunted, Camouflaged;
        internal static string LastNote = "";

        internal static int Covers;

        internal static void Register(HarmonyLib.Harmony h)
        {
            BcJunctionActs.Before.Add(("taunt", TauntAndCamouflage));
            Hooks.Patch(h, typeof(Last.Battle.Function.TargetFunction), "ProtectExtractTarget", typeof(BcJunctionTargets), postfix: nameof(Cover_Postfix));
        }

        static readonly Last.Defaine.ConditionType[] NoGuard =
        {
            Last.Defaine.ConditionType.UnableFight, Last.Defaine.ConditionType.Mineralization, Last.Defaine.ConditionType.Vanish,
            Last.Defaine.ConditionType.Transparent, Last.Defaine.ConditionType.Zombie, Last.Defaine.ConditionType.Sleep,
            Last.Defaine.ConditionType.Confusion, Last.Defaine.ConditionType.Stop, Last.Defaine.ConditionType.Hide,
            Last.Defaine.ConditionType.Freeze,
        };

        public static void Cover_Postfix(ref BattleActData __result)
        {
            if (__result == null || !BcJunction.On) return;
            if (!BcJunction.Used("true_paladin") && !BcJunction.Used("popular")) return;
            try
            {
                var act = __result;
                var targets = act.TargetUnitDatas;
                var target = act.ProtectedTarget ?? (targets != null && targets.Length == 1 ? targets[0] : null);
                if (target == null || targets == null || targets.Length != 1) return;
                bool popular = BcJunction.Used("popular") && BcJunction.Has(target, "popular");
                bool bothSides = popular && BcJunction.Rng.Next(2) == 0;
                var pool = BcJunction.Party().Concat(BcJunction.Enemies())
                    .Where(u => u.Pointer != target.Pointer && BcJunction.Alive(u) && (bothSides || BcJunction.SameSide(u, target)))
                    .Where(u => !NoGuard.Any(c => BcJunction.HasStatus(u, c))).ToList();
                if (pool.Count == 0) return;
                var paladins = BcJunction.Used("true_paladin") ? pool.Where(u => BcJunction.Has(u, "true_paladin")).ToList() : new List<BattleUnitData>();
                BattleUnitData guard = paladins.Count > 0 ? paladins[BcJunction.Rng.Next(paladins.Count)]
                                     : popular ? pool[BcJunction.Rng.Next(pool.Count)] : null;
                if (guard == null) return;
                act.SetProtectData(guard, target, null);
                var t = new Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppReferenceArray<BattleUnitData>(1);
                t[0] = guard;
                act.TargetUnitDatas = t;
                Covers++;
                LastNote = $"{BcJunction.Who(guard)} covers {BcJunction.Who(target)} ({(paladins.Count > 0 ? "True Paladin" : "Popularity")})";
                Hooks.NoteOnce("bc-junction-cover", () => $"{BcJunction.Tag} first cover: {LastNote}");
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-cover", e); }
        }

        static void TauntAndCamouflage(BcJunctionActs.Act act)
        {
            if (act.Targets.Count != 1 || act.Attacker == null) return;
            if (!BcJunction.Used("taunt") && !BcJunction.Used("camouflage")) return;
            var target = act.Targets[0];
            if (BcJunction.SameSide(act.Attacker, target)) return;
            bool targetIsParty = BcJunction.IsPlayer(target);
            var team = (targetIsParty ? BcJunction.Party() : BcJunction.Enemies()).Where(BcJunction.Alive).ToList();
            if (team.Count < 2) return;
            var now = target;
            if (BcJunction.Used("taunt"))
            {
                var taunters = team.Where(u => (!targetIsParty || BcJunction.Rng.Next(2) == 0) && BcJunction.Has(u, "taunt")).ToList();
                if (taunters.Count > 0)
                {
                    int pick = BcJunctionMath.TauntPick(taunters.Count, !BcJunction.IsPlayer(act.Attacker),
                                                        taunters.Any(u => u.Pointer == target.Pointer), BcJunction.Rng.Next(taunters.Count));
                    if (pick >= 0)
                    {
                        now = taunters[pick];
                        if (now.Pointer != target.Pointer) Taunted++;
                    }
                }
            }
            if (BcJunction.Used("camouflage") && BcJunction.Has(now, "camouflage"))
            {
                var open = team.Where(u => u.Pointer != now.Pointer && !BcJunction.Has(u, "camouflage")).ToList();
                if (open.Count > 0)
                {
                    now = open[BcJunction.Rng.Next(open.Count)];
                    Camouflaged++;
                }
            }
            if (now.Pointer == target.Pointer) return;
            if (!Retarget(act, now)) return;
            LastNote = $"{BcJunction.Who(act.Attacker)}'s act: {BcJunction.Who(target)} -> {BcJunction.Who(now)}";
            Hooks.NoteOnce("bc-junction-taunt", () => $"{BcJunction.Tag} first retarget (Taunt/Camouflage): {LastNote}");
        }

        // the act's target becomes `to` (before the PR works out the act's functions: FunctionGroupInfo.HitCalc
        // starts with the first function's targets, taken from the act)
        internal static bool Retarget(BcJunctionActs.Act act, BattleUnitData to)
        {
            try
            {
                var arr = new Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppReferenceArray<BattleUnitData>(1);
                arr[0] = to;
                act.Data.TargetUnitDatas = arr;
                act.Targets.Clear();
                act.Targets.Add(to);
                return true;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-retarget", e); return false; }
        }
    }
}
