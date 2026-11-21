using System;
using System.Collections.Generic;
using System.Linq;
using Last.Battle;
using Last.Data.Master;
using Last.Defaine;
using PrKit;
using Action = System.Action;

namespace BeyondChaos.PR
{
    // Junction effects' battle self-tests, on bc-battle's registry (BcSelfTests.Add; the runner's recipe: boot;
    // bcapply <seed>; battle <n>; bckeep on; bcselftest start junction; until "bcselftest done"). Each test gives a
    // party member or a monster an effect (BcJunction.Grant), sets the scene (HP, statuses), queues acts and
    // checks what came of them (the act hub's log: every act landing, with each fighter's HP before and after).
    static class BcJunctionTests
    {
        // every act that landed while the tests run (BcJunctionActs.After)
        internal sealed class Log
        {
            public BcJunctionActs.Act Act;
            public List<BcJunctionActs.Landed> Units;
            public float Time;
        }

        internal static readonly List<Log> Landed = new List<Log>();
        static bool logging;

        internal static void Register()
        {
            BcJunctionActs.After.Add(("test-log", (act, units) =>
            {
                if (!logging) return;
                Landed.Add(new Log { Act = act, Units = units, Time = UnityEngine.Time.realtimeSinceStartup });
                if (Landed.Count > 400) Landed.RemoveRange(0, 100);
            }));
            Core();
            BcJunctionTests2.Register();
            // only on a seed made with junction flags (bcjgen): on another seed each check answers at once and
            // queues nothing, so other features' self-test runs ("bcselftest start") aren't held up
            foreach (var t in Tests)
            {
                var test = t;
                bool skip = false;
                BcSelfTests.Add("junction " + test.Name,
                    () => skip ? "ok: skipped (this seed has no junction effects; bcjgen makes one)" : test.Check(),
                    () => { skip = !BcJunction.Load(); if (!skip) test.Start?.Invoke(); },
                    test.Timeout);
            }
        }

        // --- the hub and the who-has-what check --------------------------------------------------------------

        static void Core()
        {
            // the seed's record: every fighter's effects work out, and a party member wearing an item with effects has them
            Tests.Add(new T
            {
                Name = "record", Timeout = 10,
                Check = () =>
                {
                    if (!BcJunction.Load()) return "FAILED: the seed has no junction record (bcjgen makes one)";
                    var parts = new List<string>();
                    foreach (var u in BcJunction.Party().Concat(BcJunction.Enemies()))
                        parts.Add($"{BcJunction.Who(u)} {BcJunction.Effects(u).Count}");
                    return $"ok: {BcJunction.InUse.Count} effects in the seed; fighters: {string.Join(", ", parts)}";
                },
            });
            // the act hub: a party member's strike lands and is seen with the target's HP before and after
            Add("acts", began =>
            {
                BcSelfTests.Sturdy();
                var e = LivingEnemy();
                Act(P(0), e, AttackAbility(), 1);
            }, began =>
            {
                var l = Since(began, P(0)).FirstOrDefault();
                if (l == null) return null;
                var hit = l.Units.FirstOrDefault(x => x.Targeted);
                return hit == null ? "FAILED: the act landed with no target result"
                    : $"ok: {BcJunction.Who(l.Act.Attacker)} -> {BcJunction.Who(hit.Unit)}: {hit.Hit}, HP {hit.HpBefore} -> {hit.HpAfter}; acts seen {BcJunctionActs.Seen}";
            });
            // Taunt: a monster's strikes at slot 0 go to slot 1 (a party taunter qualifies on 50% of strikes)
            Add("taunt", began =>
            {
                BcSelfTests.Sturdy();
                foreach (var p in BcJunction.Party()) SetHp(p, 9999);
                BcJunction.Grant(P(1), "taunt");
                for (int i = 0; i < 8; i++) Act(LivingEnemy(), P(0), AttackAbility(), 1);
            }, began =>
            {
                var acts = Since(began, LivingEnemy());
                if (acts.Count < 8) return null;
                int toTaunter = acts.Count(l => l.Units.Any(x => x.Targeted && x.Unit.Pointer == P(1).Pointer));
                int toOriginal = acts.Count(l => l.Units.Any(x => x.Targeted && x.Unit.Pointer == P(0).Pointer));
                return toTaunter >= 1 && toTaunter + toOriginal == acts.Count
                    ? $"ok: {toTaunter} of {acts.Count} strikes went to the taunter, {toOriginal} to the target (50% each expected)"
                    : $"FAILED: taunter {toTaunter}, target {toOriginal} of {acts.Count}";
            });
            // the battle's start, done again mid-battle for the fighters given effects: First Strike, Regenerator,
            // Auto-Reraise, Plague (from a party member: the monsters' Doom), Juggernaut and Burst
            Tests.Add(new T
            {
                Name = "start", Timeout = 10,
                Check = () =>
                {
                    Begin();
                    var all = BcJunction.Party().Concat(BcJunction.Enemies()).ToList();
                    var atb = BcJunctionStart.Atb();
                    var p0 = P(0); var p1 = P(1); var p2 = P(2) ?? P(1); var p3 = P(3) ?? P(0);
                    atb?.ChangeATBGaugeByUnitData(p0, 0f);
                    int lv1 = BcJunctionStart.LevelOf(p1), lv2 = BcJunctionStart.LevelOf(p2);
                    BcJunction.Grant(p0, "initiative");
                    BcJunction.Grant(p1, "regenerator", "juggernaut");
                    BcJunction.Grant(p2, "auto_reraise", "burst");
                    BcJunction.Grant(p3, "plague");
                    foreach (var u in new[] { p0, p1, p2, p3 }.Distinct()) BcJunctionStart.For(u, atb, all);
                    float gauge = BcJunctionStart.Gauge(p0);
                    bool regen = BcJunction.HasStatus(p1, ConditionType.Regeneration);
                    bool reraise = BcJunction.HasStatus(p2, ConditionType.Reraise);
                    var e = LivingEnemy();
                    bool doom = e != null && BcJunction.HasStatus(e, ConditionType.Doom);
                    int jl = BcJunctionStart.LevelOf(p1), bl = BcJunctionStart.LevelOf(p2);
                    End();
                    var bad = new List<string>();
                    if (gauge < 99) bad.Add($"gauge {gauge}");
                    if (!regen) bad.Add("no Regen");
                    if (!reraise) bad.Add("no Reraise");
                    if (!doom) bad.Add("monster has no Doom");
                    if (jl != (lv1 + 1) / 2) bad.Add($"Juggernaut level {lv1} -> {jl}");
                    int want = Math.Min(99, lv2 + (lv2 + 1) / 2);   // BC: 127; the PR's levels stop at 99
                    if (p2 != p1 && bl != want) bad.Add($"Burst level {lv2} -> {bl} (want {want})");
                    return bad.Count == 0 ? $"ok: gauge {gauge}, Regen, Reraise, Doom, levels {lv1}->{jl}, {lv2}->{bl}" : "FAILED: " + string.Join(", ", bad);
                },
            });
            // Dog: a monster's strikes at a party member with Dog are blocked half the time
            Add("dog", began =>
            {
                BcSelfTests.Sturdy();
                foreach (var p in BcJunction.Party()) SetHp(p, 9999);
                BcJunction.Grant(P(0), "dog");
                for (int i = 0; i < 10; i++) Act(LivingEnemy(), P(0), AttackAbility(), 1);
            }, began =>
            {
                var acts = Since(began, LivingEnemy());
                if (acts.Count < 10) return null;
                var on = acts.Select(l => On(l, P(0))).Where(x => x != null && x.Targeted).ToList();
                int missed = on.Count(x => x.Missed || x.Damage == 0);
                return missed >= 1 && missed < on.Count
                    ? $"ok: {missed} of {on.Count} strikes blocked (50% expected)"
                    : $"FAILED: {missed} of {on.Count} blocked";
            });
        }

        internal sealed class T
        {
            public string Name;
            public Action Start;
            public Func<string> Check;
            public float Timeout = 40;
        }

        internal static readonly List<T> Tests = new List<T>();

        // --- helpers ------------------------------------------------------------------------------------

        internal static float Now => UnityEngine.Time.realtimeSinceStartup;

        internal static void Begin()
        {
            logging = true;
            BcJunction.Testing = true;
            BcJunctionDamage.Logging = true;
            BcJunction.Granted.Clear();
            BcJunction.Invalidate();
        }

        internal static void End()
        {
            BcJunction.Granted.Clear();
            BcJunction.Testing = false;
            BcJunction.Invalidate();
        }

        internal static BattleUnitData P(int slot) => BcJunction.Party().Skip(slot).FirstOrDefault();
        internal static BattleUnitData E(int slot) => BcJunction.Enemies().Skip(slot).FirstOrDefault();
        internal static BattleUnitData LivingEnemy() => BcJunction.Enemies().FirstOrDefault(BcJunction.Alive);

        internal static int Hp(BattleUnitData u) => u?.BattleUnitDataInfo?.Parameter?.CurrentHP ?? -1;
        internal static int MaxHp(BattleUnitData u) => u?.BattleUnitDataInfo?.Parameter?.ConfirmedMaxHp() ?? -1;
        internal static int Mp(BattleUnitData u) => u?.BattleUnitDataInfo?.Parameter?.CurrentMP ?? -1;

        internal static void SetHp(BattleUnitData u, int hp)
        {
            var p = u?.BattleUnitDataInfo?.Parameter;
            if (p == null) return;
            if (p.BaseMaxHp < hp) p.BaseMaxHp = hp;
            p.CurrentHP = hp;
        }

        internal static void SetMp(BattleUnitData u, int mp)
        {
            var p = u?.BattleUnitDataInfo?.Parameter;
            if (p != null) p.CurrentMP = mp;
        }

        // the Attack command's ability (a plain strike for either side)
        internal static int AttackAbility() => MasterManager.Instance.GetData<Command>(1)?.AbilityId ?? 1;

        // an act queued as the game queues them (a monster's too); null when it was queued
        internal static string Act(BattleUnitData who, BattleUnitData target, int ability, int command = 0)
        {
            if (who == null || target == null) return "no fighter";
            var a = BcJunctionActs.Queue(who, new[] { target }, ability, command, interrupt: false);
            return a == null ? $"ability {ability} not queued" : null;
        }

        // the acts that landed since `since` by `who` (null: anyone)
        internal static List<Log> Since(float since, BattleUnitData who = null) =>
            Landed.Where(l => l.Time >= since && (who == null || (l.Act.Attacker != null && l.Act.Attacker.Pointer == who.Pointer))).ToList();

        internal static BcJunctionActs.Landed On(Log l, BattleUnitData u) => l.Units.FirstOrDefault(x => x.Unit.Pointer == u.Pointer);

        // a test that queues `count` acts and checks them when they have all landed
        internal static void Add(string name, Action<float> start, Func<float, string> check, float timeout = 45)
        {
            float began = 0;
            Tests.Add(new T
            {
                Name = name, Timeout = timeout,
                Start = () => { Begin(); began = Now; start(began); },
                Check = () =>
                {
                    var r = check(began);
                    if (r != null) End();
                    return r;
                },
            });
        }
    }
}
