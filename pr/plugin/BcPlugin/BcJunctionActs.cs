using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Battle;
using Last.Data.Master;
using Last.Defaine;
using Last.Systems;
using Last.Data;
using PrKit;

namespace BeyondChaos.PR
{
    // The act hub for junction effects that react to an act landing (BcJunction.cs says who has what).
    // The PR runs every function of an act inside FunctionGroupInfo.HitCalc: the first function's targets, each
    // function's PrevCalc, then each function's HitCalc and UpdateParameter (HP/MP/conditions applied per
    // target in UpdateParameterSub); the numbers are shown later from the stored results (ViewEntity).
    // FunctionGroupInfo's own UpdateParameter/StartFunction are empty shared stubs: never hook those
    // (tools/decomp/bc_junction, pattern pr/tools/ghidra/bc_junction.txt).
    // So: the prefix is "the act is about to land" (BC's pre-hit hooks), the postfix "it landed" (BC's hit,
    // damage, status, death and SOS hooks), with each fighter's HP/MP/statuses before and after.
    static class BcJunctionActs
    {
        internal sealed class Act
        {
            public BattleActData Data;
            public BattleUnitData Attacker;
            public Command Command;
            public Ability Ability;              // the first (the act's skill)
            public List<BattleUnitData> Targets = new List<BattleUnitData>();
            public bool Counter, Copied, Ours;   // Ours: queued by a junction effect
            public bool Test;                     // queued by a self-test (BcJunctionTests): effects treat it as the fighter's own
            public List<BcJunctionDamage.Calc> Calcs = new List<BcJunctionDamage.Calc>();
        }

        internal sealed class Landed
        {
            public BattleUnitData Unit;
            public int HpBefore, HpAfter, MpBefore, MpAfter, MaxHp;
            public HashSet<ConditionType> Before = new HashSet<ConditionType>(), After = new HashSet<ConditionType>();
            public ICalcResult Result;            // the act's result for this unit (null: not a target)
            public HitType Hit = HitType.Non;
            public int Damage => Math.Max(0, HpBefore - HpAfter);
            public int Healed => Math.Max(0, HpAfter - HpBefore);
            // HP to 0 counts: the PR gives Wound after HitCalc (BcJunctionMath.Fell)
            public bool Died => BcJunctionMath.Fell(HpBefore, HpAfter, Before.Contains(ConditionType.UnableFight), After.Contains(ConditionType.UnableFight));
            public bool Gained(ConditionType t) => !Before.Contains(t) && After.Contains(t);
            public bool Lost(ConditionType t) => Before.Contains(t) && !After.Contains(t);
            public bool Targeted => Result != null;
            public bool Missed => Hit == HitType.Miss;
        }

        // handlers: before (may change the act's targets or results' inputs), after (the outcome)
        internal static readonly List<(string Name, Action<Act> Run)> Before = new List<(string, Action<Act>)>();
        internal static readonly List<(string Name, Action<Act, List<Landed>> Run)> After = new List<(string, Action<Act, List<Landed>>)>();

        internal static int Seen, Errors;
        internal static Act Current;              // the act landing now (damage hooks read it)
        static readonly HashSet<IntPtr> ours = new HashSet<IntPtr>();

        public static void Patch(Harmony h)
        {
            Hooks.Patch(h, typeof(FunctionGroupInfo), "HitCalc", typeof(BcJunctionActs),
                prefix: nameof(HitCalc_Prefix), postfix: nameof(HitCalc_Postfix));
        }

        public sealed class State
        {
            public Act Act;
            public List<Landed> Units;
        }

        public static void HitCalc_Prefix(FunctionGroupInfo __instance, out State __state)
        {
            __state = null;
            if (!BcJunction.On || !Hooks.IsA<FunctionGroupInfo>(__instance)) return;
            try
            {
                var data = __instance.battleActData;
                if (data == null) return;
                var act = new Act
                {
                    Data = data,
                    Attacker = data.AttackUnitData,
                    Command = data.Command,
                    Ability = data.abilityList != null && data.abilityList.Count > 0 ? data.abilityList[0] : null,
                    Counter = data.isCounter,
                    Copied = data.isCopiedAct,
                    Ours = ours.Contains(data.Pointer),
                };
                act.Test = TakeTest(data, act);
                var targets = data.TargetUnitDatas;
                if (targets != null)
                    foreach (var t in targets) if (t != null) act.Targets.Add(t);
                Current = act;
                foreach (var (name, run) in Before)
                {
                    try { run(act); }
                    catch (Exception e) { Errors++; Hooks.WarnOnce("bc-junction-before-" + name, e); }
                }
                __state = new State { Act = act, Units = Snapshot() };
                Seen++;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-acts-prefix", e); }
        }

        public static void HitCalc_Postfix(FunctionGroupInfo __instance, State __state)
        {
            if (__state == null) return;
            try
            {
                Current = null;
                var results = __instance.GetICalcResult();
                foreach (var l in __state.Units)
                {
                    var p = l.Unit.BattleUnitDataInfo?.Parameter;
                    if (p == null) continue;
                    l.HpAfter = p.CurrentHP;
                    l.MpAfter = p.CurrentMP;
                    l.After = Conditions(l.Unit);
                    if (results != null && results.ContainsKey(l.Unit))
                    {
                        l.Result = results[l.Unit];
                        try { l.Hit = l.Result.GetHitType(); } catch { l.Hit = HitType.Non; }
                    }
                }
                RouteConvertedHits(__state.Act, __state.Units);
                BcJunction.Invalidate();
                foreach (var (name, run) in After)
                {
                    try { run(__state.Act, __state.Units); }
                    catch (Exception e) { Errors++; Hooks.WarnOnce("bc-junction-after-" + name, e); }
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-acts-postfix", e); }
        }

        // PR's battle functions pick the HP/MP application path before the formula returns. Changing
        // CalcResult's HitType changes the number shown, but not that path. Move the applied amount
        // here, after UpdateParameterSub, before the junction after-hit/death handlers inspect it.
        static void RouteConvertedHits(Act act, List<Landed> units)
        {
            foreach (var l in units)
            {
                var calcs = act.Calcs.Where(c => c.Target?.Pointer == l.Unit.Pointer).ToList();
                if (calcs.Count == 0) { RouteFullRecovery(act, l); continue; }
                if (calcs.Count > 1) { RouteMultiple(act, l, calcs); continue; }
                var changed = calcs.Where(c => c.HitAfter.HasValue && c.HitAfter.Value != c.Hit && c.ValueAfter > 0).ToList();
                if (changed.Count != 1 || calcs.Count != 1) continue;
                var c = changed[0];
                var p = l.Unit.BattleUnitDataInfo?.Parameter;
                if (p == null) continue;
                int hp = l.HpAfter, mp = l.MpAfter, amount = c.ValueAfter;
                bool hpDamage = c.Hit == HitType.Hit || c.Hit == HitType.Critical;
                bool hpHeal = c.Hit == HitType.Recovery;
                bool mpDamage = c.Hit == HitType.MPHit;
                bool mpHeal = c.Hit == HitType.MPRecovery;
                bool toHpDamage = c.HitAfter == HitType.Hit || c.HitAfter == HitType.Critical;
                bool toHpHeal = c.HitAfter == HitType.Recovery;
                bool toMpDamage = c.HitAfter == HitType.MPHit;
                bool toMpHeal = c.HitAfter == HitType.MPRecovery;
                if (!(hpDamage || hpHeal || mpDamage || mpHeal) ||
                    !(toHpDamage || toHpHeal || toMpDamage || toMpHeal)) continue;
                if (hpDamage) hp = Math.Min(l.MaxHp, hp + Math.Min(amount, Math.Max(0, l.HpBefore - hp)));
                else if (hpHeal) hp = Math.Max(0, hp - Math.Min(amount, Math.Max(0, hp - l.HpBefore)));
                else if (mpDamage) mp = Math.Min(p.ConfirmedMaxMp(), mp + Math.Min(amount, Math.Max(0, l.MpBefore - mp)));
                else if (mpHeal) mp = Math.Max(0, mp - Math.Min(amount, Math.Max(0, mp - l.MpBefore)));
                if (toHpDamage) hp = Math.Max(0, hp - amount);
                else if (toHpHeal) hp = Math.Min(l.MaxHp, hp + amount);
                else if (toMpDamage) mp = Math.Max(0, mp - amount);
                else if (toMpHeal) mp = Math.Min(p.ConfirmedMaxMp(), mp + amount);
                Commit(l, hp, mp);
            }
        }

        // Multi-function abilities can work out HP and MP in the same HitCalc. Only reroute
        // when replaying every original result from the before snapshot reproduces the game's
        // observed HP/MP. This leaves acts with other HP/MP side effects on the game's path.
        static void RouteMultiple(Act act, Landed l, List<BcJunctionDamage.Calc> calcs)
        {
            if (!calcs.Any(c => c.HitAfter.HasValue && c.HitAfter.Value != c.Hit && c.ValueAfter > 0)) return;
            var p = l.Unit.BattleUnitDataInfo?.Parameter;
            if (p == null) return;
            var resources = RecoveryResources(act.Ability, calcs);
            int maxMp = p.ConfirmedMaxMp(), hp = l.HpBefore, mp = l.MpBefore;
            for (int i = 0; i < calcs.Count; i++)
                if (!Apply(ref hp, ref mp, l.MaxHp, maxMp, ResourceHit(calcs[i].Hit, resources, i), calcs[i].ValueAfter)) return;
            if (hp != l.HpAfter || mp != l.MpAfter) return;
            hp = l.HpBefore;
            mp = l.MpBefore;
            for (int i = 0; i < calcs.Count; i++)
                if (!Apply(ref hp, ref mp, l.MaxHp, maxMp, ResourceHit(calcs[i].HitAfter ?? calcs[i].Hit, resources, i), calcs[i].ValueAfter)) return;
            Commit(l, hp, mp);
        }

        // RecoveryFunction can return HitType.Recovery for both HP and MP functions;
        // FunctionGroup's value2 selects the resource. Use it only when its formula
        // recovery entries line up exactly with the calculated results.
        static int[] RecoveryResources(Ability ability, List<BcJunctionDamage.Calc> calcs)
        {
            if (ability == null || calcs.Any(c => c.Kind != BcJunctionDamage.Kind.Heal)) return null;
            var g = MasterManager.Instance?.GetData<FunctionGroup>(ability.BattleFunctionGroupId);
            if (g == null) return null;
            var modes = new[] { (g.Function1Id, g.Function1Value1, g.Function1Value2),
                                (g.Function2Id, g.Function2Value1, g.Function2Value2),
                                (g.Function3Id, g.Function3Value1, g.Function3Value2) };
            var resources = modes.Where(m => m.Item1 == 1 && m.Item2 == 2).Select(m => m.Item3).ToArray();
            return resources.Length == calcs.Count && resources.All(r => r == 2 || r == 3) ? resources : null;
        }

        static HitType ResourceHit(HitType hit, int[] resources, int index)
        {
            if (resources == null || resources[index] != 3) return hit;
            if (hit == HitType.Recovery) return HitType.MPRecovery;
            if (hit == HitType.Hit || hit == HitType.Critical) return HitType.MPHit;
            return hit;
        }

        // The game's full-restore RecoveryFunction mode bypasses CalcControllerProvider:
        // ability 765 uses one such function for HP and one for MP. Reverse treats each
        // full restore as damage to that resource, guarded by the observed max recovery.
        static void RouteFullRecovery(Act act, Landed l)
        {
            if (!l.Targeted || !BcJunction.Has(act.Attacker, "reverse") || l.HpBefore <= 0) return;
            var p = l.Unit.BattleUnitDataInfo?.Parameter;
            var g = act.Ability == null ? null : MasterManager.Instance?.GetData<FunctionGroup>(act.Ability.BattleFunctionGroupId);
            if (p == null || g == null) return;
            var modes = new[] { (g.Function1Id, g.Function1Value1, g.Function1Value2),
                                (g.Function2Id, g.Function2Value1, g.Function2Value2),
                                (g.Function3Id, g.Function3Value1, g.Function3Value2) };
            var full = modes.Where(m => m.Item1 == 1 && m.Item2 == 1).Select(m => m.Item3).ToArray();
            if (full.Length != 2 || full[0] != 2 || full[1] != 3 ||
                l.HpAfter != l.MaxHp || l.MpAfter != p.ConfirmedMaxMp()) return;
            Commit(l, 0, 0);
        }

        static bool Apply(ref int hp, ref int mp, int maxHp, int maxMp, HitType hit, int amount)
        {
            if (amount <= 0 || hit == HitType.Miss || hit == HitType.Non) return true;
            switch (hit)
            {
                case HitType.Hit:
                case HitType.Critical: hp = Math.Max(0, hp - amount); return true;
                case HitType.Recovery: hp = Math.Min(maxHp, hp + amount); return true;
                case HitType.MPHit: mp = Math.Max(0, mp - amount); return true;
                case HitType.MPRecovery: mp = Math.Min(maxMp, mp + amount); return true;
                default: return false;
            }
        }

        static void Commit(Landed l, int hp, int mp)
        {
            var p = l.Unit.BattleUnitDataInfo?.Parameter;
            if (p == null) return;
            p.CurrentHP = hp;
            p.CurrentMP = mp;
            l.HpAfter = hp;
            l.MpAfter = mp;
            if (hp > 0 && !l.Before.Contains(ConditionType.UnableFight) && l.After.Contains(ConditionType.UnableFight))
            {
                BattlePlugManager.Instance()?.BattleConditionController?.InterruptRemoveCondition(l.Unit, ConditionType.UnableFight);
                l.After = Conditions(l.Unit);
            }
            else if (hp == 0 && l.HpBefore > 0 && !l.After.Contains(ConditionType.UnableFight))
            {
                BattlePlugManager.Instance()?.BattleConditionController?.InterruptAddCondition(l.Unit, ConditionType.UnableFight);
                l.After = Conditions(l.Unit);
            }
        }

        static List<Landed> Snapshot()
        {
            var list = new List<Landed>();
            foreach (var u in BcJunction.Party().Concat(BcJunction.Enemies()))
            {
                var p = u.BattleUnitDataInfo?.Parameter;
                if (p == null) continue;
                list.Add(new Landed
                {
                    Unit = u, HpBefore = p.CurrentHP, MpBefore = p.CurrentMP, MaxHp = p.ConfirmedMaxHp(),
                    Before = Conditions(u),
                });
            }
            return list;
        }

        internal static HashSet<ConditionType> Conditions(BattleUnitData u)
        {
            var set = new HashSet<ConditionType>();
            try
            {
                var c = u?.BattleUnitDataInfo?.GetConfirmedConditionType();
                if (c != null) foreach (var t in c) set.Add(t);
            }
            catch { }
            return set;
        }

        // --- the self-tests' own acts --------------------------------------------------------------------
        // Matched by fighter, ability and command, not by object: bc-selftest-4's party acts never matched by pointer
        // (a party member's act may run as another BattleActData). An act's later HitCalcs (if it has more than one
        // function group) match by its object once one has matched. Test acts aren't Ours: the effects answer them as they answer a
        // fighter's own act (Return Magic, Freebie, Double Time skip effect acts).
        sealed class Pending
        {
            public BattleActData Data;
            public IntPtr Who;
            public int Ability, Command;          // Ability -1: any (an item act)
        }

        static readonly List<Pending> tests = new List<Pending>();
        static readonly HashSet<IntPtr> testActs = new HashSet<IntPtr>();

        static bool TakeTest(BattleActData data, Act act)
        {
            if (testActs.Contains(data.Pointer)) return true;
            if (tests.Count == 0 || act.Attacker == null) return false;
            int ability = act.Ability?.Id ?? 0, command = act.Command?.Id ?? 0;
            int i = tests.FindIndex(p => p.Data.Pointer == data.Pointer);
            if (i < 0) i = tests.FindIndex(p => p.Who == act.Attacker.Pointer && (p.Ability < 0 || p.Ability == ability) && p.Command == command);
            if (i < 0) return false;
            tests.RemoveAt(i);
            testActs.Add(data.Pointer);
            if (testActs.Count > 500) testActs.Clear();
            return true;
        }

        // a self-test's act. A party member's goes as an interrupting counter: bc-selftest-4's party acts queued as
        // Normal never ran (the PR's acts for a party member follow its own picks: fixedPlayerBattleActDataStack, auto-
        // battle's), and its interrupts that weren't counters were built but never landed (a Cure that healed nobody);
        // its counters landed and applied (Counter All, Hamedo, SOS, the item reactions). A monster's goes as Normal.
        internal static BattleActData QueueTest(BattleUnitData who, IList<BattleUnitData> targets, int ability, int command = 0)
        {
            bool party = BcJunction.IsPlayer(who);
            var act = Queue(who, targets, ability, command, counter: party, interrupt: party, effect: false);
            if (act == null) return null;
            tests.Add(new Pending { Data = act, Who = who.Pointer, Ability = ability, Command = act.Command?.Id ?? 0 });
            return act;
        }

        // an item act a self-test queued (BcJunctionItems.UseItem): matched the same way
        internal static void ExpectTest(BattleActData act)
        {
            if (act?.AttackUnitData == null) return;
            tests.Add(new Pending { Data = act, Who = act.AttackUnitData.Pointer, Ability = -1, Command = act.Command?.Id ?? 0 });
        }

        // a check's end: its acts that haven't landed are taken off the game's stacks (bc-selftest-4: freebie's last
        // four Potions landed in overheal's check)
        internal static int DropTests()
        {
            int n = 0;
            var ex = BattlePlugManager.Instance()?.BattleActExection;
            foreach (var p in tests)
                try
                {
                    if (ex?.BattleActDataStackInterrupt != null && ex.BattleActDataStackInterrupt.Remove(p.Data)) n++;
                    else if (ex?.BattleActDataStack != null && ex.BattleActDataStack.Remove(p.Data)) n++;
                }
                catch (Exception e) { Hooks.WarnOnce("bc-junction-drop-test", e); }
            tests.Clear();
            testActs.Clear();
            return n;
        }

        // --- queueing an act of a junction effect -------------------------------------------------------

        // a fighter's act with a PR ability (a counter, an SOS spell...), queued as the game queues acts;
        // command: the PR command row the act runs under (0: the ability's own magic/attack row)
        internal static BattleActData Queue(BattleUnitData who, IList<BattleUnitData> targets, int ability, int command = 0,
            bool counter = false, bool interrupt = true, bool effect = true)
        {
            var bm = BattlePlugManager.Instance();
            if (bm == null || who == null || targets == null || targets.Count == 0) return null;
            var mm = MasterManager.Instance;
            var ab = mm.GetData<Ability>(ability);
            if (ab == null) { Kit.Warn($"{BcJunction.Tag} no ability {ability}"); return null; }
            var cmd = mm.GetData<Command>(command > 0 ? command : DefaultCommand(ab));
            var abilities = new Il2CppSystem.Collections.Generic.List<Ability>();
            abilities.Add(ab);
            var arr = new Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppReferenceArray<BattleUnitData>(targets.Count);
            for (int i = 0; i < targets.Count; i++) arr[i] = targets[i];
            bool foes = !BcJunction.SameSide(who, targets[0]);
            var tt = targets.Count > 1 ? (foes ? BattleActData.TargetType.AllEnemy : BattleActData.TargetType.AllMember)
                                       : (foes ? BattleActData.TargetType.SingleEnemy : BattleActData.TargetType.SingleMember);
            var act = new BattleActData(who, arr, cmd, abilities,
                interrupt ? BattleActData.ActType.Interrupt : BattleActData.ActType.Normal, tt,
                BattleActData.ArmType.Right, (BattleActData.ActAbilityType)0, 1, false);
            act.isCounter = counter;
            if (effect)
            {
                ours.Add(act.Pointer);
                if (ours.Count > 500) ours.Clear();
            }
            bm.BattleActExection.SetBattleActData(act);
            return act;
        }

        // the command an ability runs under when the effect names none: Attack (1) for an attack (type 4), else Magic (7)
        internal static int DefaultCommand(Ability ab) => ab != null && ab.TypeId == 4 ? 1 : 7;
    }
}
