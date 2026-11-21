using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Battle;
using Last.Defaine;
using Last.Systems;
using PrKit;
using Calc = BeyondChaos.PR.BcJunctionDamage.Calc;
using Kind = BeyondChaos.PR.BcJunctionDamage.Kind;

namespace BeyondChaos.PR
{
    // Junction effects that add to a strike (BC's patch_junction_hit_trigger, deaths_door; spec_B.json):
    //   Gunblade (attacker)    an Attack strike spends a Super Ball (a party member's from the inventory, a
    //                          monster's from its steal slots): the strike is a sure critical, and a HyperDrive
    //                          follows at the target, free
    //   Add Steal (attacker)   50% a strike that hits a monster also steals from it (the PR's odds: (50 + level -
    //                          its level) / 128, the rare item 1 in 8; one steal a monster, as the PR has it)
    //   Death's Door (attacker) a spell that kills outright (Death, Doom...) missing a target deals it the
    //                          attacker's missing HP instead (a monster attacker: an eighth)
    //   Quickening (caster)    a spell with an MP cost is cast again at the same targets while the caster can pay
    //                          1.5x the last cost (in MP, and as much HP), up to 255
    static class BcJunctionProcs
    {
        internal static int Gunblades, Steals, DoorHits, Quickenings;
        static readonly HashSet<IntPtr> gunbladeStrike = new HashSet<IntPtr>();
        static readonly Dictionary<IntPtr, int> chainCost = new Dictionary<IntPtr, int>();   // a Quickening echo's cost

        internal static void Register(Harmony h)
        {
            BcJunctionActs.Before.Add(("gunblade", GunbladeBefore));
            BcJunctionDamage.Rules.Add(("gunblade", GunbladeHit));
            BcJunctionActs.After.Add(("procs", After));
        }

        static bool Has(BattleUnitData u, string key) => BcJunction.Used(key) && BcJunction.Has(u, key);

        // --- Gunblade --------------------------------------------------------------------------------------------

        static void GunbladeBefore(BcJunctionActs.Act act)
        {
            gunbladeStrike.Clear();
            var a = act.Attacker;
            if (a == null || act.Command?.Id != BcJunctionEffects.AttackCommand || !Has(a, "gunblade")) return;
            int ball = BcJunctionTriggers.Item("superball");
            if (ball <= 0) return;
            if (BcJunction.IsPlayer(a))
            {
                var items = new Last.Management.OwnedItemClient();
                if (!items.HasItem(ball)) return;
                items.RemoveOwnedItem(ball, 1);
            }
            else
            {
                // a monster's Super Ball: from its steal slots (not once it has been stolen from)
                var m = a.GetMonster();
                if (m == null || (m.StealContentId1 != ball && m.StealContentId2 != ball) || BcJunction.HeldItems(a.TryCast<BattleEnemyData>(), m).Count == 0) return;
            }
            gunbladeStrike.Add(a.Pointer);
            Gunblades++;
        }

        static void GunbladeHit(Calc c)
        {
            if (c.Attacker == null || !gunbladeStrike.Contains(c.Attacker.Pointer) || c.Kind != Kind.Fight) return;
            if (c.Hit == HitType.Hit) { c.HitAfter = HitType.Critical; c.Scale("gunblade crit", 2); }
        }

        // --- after the strike -----------------------------------------------------------------------------------

        static void After(BcJunctionActs.Act act, List<BcJunctionActs.Landed> units)
        {
            var a = act.Attacker;
            if (a == null) return;
            var hit = units.Where(l => l.Targeted && !l.Missed && l.Unit.Pointer != a.Pointer).ToList();
            if (gunbladeStrike.Contains(a.Pointer))
            {
                gunbladeStrike.Remove(a.Pointer);
                var t = hit.FirstOrDefault()?.Unit ?? act.Targets.FirstOrDefault();
                if (t != null && BcJunction.Alive(t)) BcJunctionTriggers.Cast(a, t, BcJunctionTriggers.Spell("hyperdrive"), true, "Gunblade");
            }
            // Add Steal: the party's strikes at monsters
            if (BcJunction.IsPlayer(a) && BcJunction.Rng.Next(2) == 0 && Has(a, "add_steal"))
                foreach (var l in hit.Where(l => !BcJunction.IsPlayer(l.Unit)))
                    Steal(a, l.Unit);
            // Death's Door: an instant-death spell that missed
            var inflicts = BcJunctionMore.Inflicts(act.Ability);
            if ((inflicts.Contains(ConditionType.UnableFight) || inflicts.Contains(ConditionType.Doom)) && Has(a, "deaths_door"))
            {
                var ap = a.BattleUnitDataInfo?.Parameter;
                foreach (var l in units.Where(l => l.Targeted && (l.Missed || (!l.Died && l.Damage == 0)) && l.Unit.Pointer != a.Pointer && BcJunction.Alive(l.Unit)))
                {
                    if (ap == null) break;
                    int dmg = BcJunctionMath.DeathsDoor(ap.ConfirmedMaxHp(), ap.CurrentHP, !BcJunction.IsPlayer(a));
                    var tp = l.Unit.BattleUnitDataInfo.Parameter;
                    if (dmg > 0) tp.CurrentHP = Math.Max(0, tp.CurrentHP - dmg);
                    else if (dmg < 0) tp.CurrentHP = Math.Min(tp.ConfirmedMaxHp(), tp.CurrentHP - dmg);
                    if (tp.CurrentHP == 0) BattlePlugManager.Instance()?.BattleConditionController?.InterruptAddCondition(l.Unit, ConditionType.UnableFight);
                    DoorHits++;
                }
            }
            Quicken(act, units);
        }

        static void Steal(BattleUnitData thief, BattleUnitData monster)
        {
            var e = monster.TryCast<BattleEnemyData>();
            var m = e?.MonsterMaster ?? monster.GetMonster();
            var plug = BattlePlugManager.Instance()?.BattleStealItemPlug;
            if (m == null || e == null || plug == null || plug.StealCountMaxByMonster(e.UniqueId, 1)) return;
            if (!BcJunctionMath.StealHits(BcJunctionStats.Level(thief), BcJunctionStats.Level(monster), BcJunction.Rng.Next(128))) return;
            int item = BcJunction.Rng.Next(8) == 0 ? m.StealContentId2 : m.StealContentId1;
            if (item <= 0) item = m.StealContentId1 > 0 ? m.StealContentId1 : m.StealContentId2;
            if (item <= 0) return;
            plug.CountUpStealMonster(e.UniqueId, 1);
            new Last.Management.OwnedItemClient().AddOwnedItem(item, 1);
            Steals++;
            Kit.Info($"{BcJunction.Tag} Add Steal: {BcJunction.Who(thief)} stole item {item} from monster {m.Id}");
        }

        // --- Quickening ----------------------------------------------------------------------------------------

        static void Quicken(BcJunctionActs.Act act, List<BcJunctionActs.Landed> units)
        {
            var a = act.Attacker;
            int baseCost = act.Ability?.UseValue ?? 0;
            if (baseCost <= 0 || !Has(a, "quickening") || !BcJunction.Alive(a)) return;
            var p = a.BattleUnitDataInfo?.Parameter;
            if (p == null) return;
            int last = chainCost.TryGetValue(act.Data.Pointer, out int c) ? c : baseCost;
            chainCost.Remove(act.Data.Pointer);
            int next = BcJunctionMath.QuickeningCost(last, baseCost);
            if (p.CurrentMP < next || p.CurrentHP <= next) return;
            var targets = act.Targets.Where(BcJunction.Alive).ToList();
            if (targets.Count == 0) return;
            // the echo: its extra cost (past the spell's own, which the game takes) and the HP, now
            p.CurrentMP -= Math.Max(0, next - baseCost);
            p.CurrentHP = Math.Max(1, p.CurrentHP - next);
            var echo = BcJunctionActs.Queue(a, targets, act.Ability.Id, act.Command?.Id ?? 7, counter: true);
            if (echo == null) return;
            chainCost[echo.Pointer] = next;
            Quickenings++;
            Kit.Info($"{BcJunction.Tag} Quickening: {BcJunction.Who(a)} casts ability {act.Ability.Id} again for {next} MP and HP");
        }
    }
}
