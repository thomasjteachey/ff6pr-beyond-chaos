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
            public bool Died => HpBefore > 0 && !Before.Contains(ConditionType.UnableFight) && After.Contains(ConditionType.UnableFight);
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
                BcJunction.Invalidate();
                foreach (var (name, run) in After)
                {
                    try { run(__state.Act, __state.Units); }
                    catch (Exception e) { Errors++; Hooks.WarnOnce("bc-junction-after-" + name, e); }
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-acts-postfix", e); }
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

        // --- queueing an act of a junction effect -------------------------------------------------------

        // a fighter's act with a PR ability (a counter, an SOS spell...), queued as the game queues acts;
        // command: the PR command row the act runs under (0: the ability's own magic/attack row)
        internal static BattleActData Queue(BattleUnitData who, IList<BattleUnitData> targets, int ability, int command = 0,
            bool counter = false, bool interrupt = true)
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
            ours.Add(act.Pointer);
            if (ours.Count > 500) ours.Clear();
            bm.BattleActExection.SetBattleActData(act);
            return act;
        }

        // the command an ability runs under when the effect names none: Attack (1) for an attack (type 4), else Magic (7)
        internal static int DefaultCommand(Ability ab) => ab != null && ab.TypeId == 4 ? 1 : 7;
    }
}
