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
                    () =>
                    {
                        skip = !BcJunction.Load();
                        if (skip || test.Start == null) return;
                        // a check that acts needs someone to act on (bc-5: the monsters dead of the start check's
                        // Doom, LivingEnemy() was null and elements, pierce and corrosive_juggler threw NREs)
                        if (LivingEnemy() == null) throw new InvalidOperationException("no living monster to test on (the battle is over)");
                        if (P(0) == null) throw new InvalidOperationException("no party member 0");
                        test.Start();
                    },
                    test.Timeout,
                    // however it ended (answer, time-out, a throw): its effects, statuses and HP hold go
                    () => { if (!skip) End(); });
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
                var l = Mine(began, P(0), AttackAbility()).FirstOrDefault();
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
                var acts = Mine(began, LivingEnemy(), AttackAbility());
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
                var acts = Mine(began, LivingEnemy(), AttackAbility());
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
            Tidy();
            BcHarness.HoldHp = true;     // the check's own HP stays (bckeep tops up to 9999 otherwise)
        }

        internal static void End()
        {
            BcJunctionActs.DropTests();
            BcJunction.Granted.Clear();
            BcJunction.Testing = false;
            BcJunction.Invalidate();
            Tidy();
            BcHarness.HoldHp = false;
        }

        // The statuses the checks give (or effects give in them) taken off every fighter, the party's fallen raised,
        // and the battle's level / max HP / Def changes dropped, so each check starts from the same battle. bc-5: the
        // start check's Plague Doom stayed on all four monsters and killed them ~53 s later (the PR's countdown, 40 at
        // ~1.33 s), which ended the battle for the 24 checks after it; its Reraise on Biggs would also have raised
        // auto_down's target before the Phoenix Down, and resonate's Haste on party member 0 answered sos's "Haste".
        static readonly ConditionType[] Scratch =
        {
            ConditionType.Doom, ConditionType.Heist, ConditionType.Regeneration, ConditionType.Reraise, ConditionType.Sleep,
            ConditionType.Confusion, ConditionType.Zombie, ConditionType.Vanish, ConditionType.Transparent,
        };

        internal static void Tidy()
        {
            var cc = BattlePlugManager.Instance()?.BattleConditionController;
            if (cc == null) return;
            foreach (var u in BcJunction.Party().Concat(BcJunction.Enemies()).ToList())
                foreach (var s in Scratch)
                    if (BcJunction.HasStatus(u, s))
                        try { cc.InterruptRemoveCondition(u, s); } catch (Exception e) { Hooks.WarnOnce("bc-junction-tidy", e); }
            // bc-selftest-4: Biggs fell in auto_down and stayed down (bckeep's top-up left him "9999 HP, Wound"), so
            // return_magic's holder never acted and every check after it had two of the three fighters
            foreach (var p in BcJunction.Party().ToList())
                if (BcJunction.HasStatus(p, ConditionType.UnableFight) || Hp(p) <= 0)
                    try
                    {
                        cc.InterruptRemoveCondition(p, ConditionType.UnableFight);
                        SetHp(p, Math.Max(1, Math.Min(9999, MaxHp(p))));
                    }
                    catch (Exception e) { Hooks.WarnOnce("bc-junction-tidy-raise", e); }
            BcJunctionStats.Clear();
        }

        // the acts the check queued itself (Act / Cast: BcJunctionActs.QueueTest marks them Test) by `who` since `since`,
        // with `ability` (0: any): not an auto-battle act of the same fighter (bckeep's auto: MagiTek every ~2 s in
        // bc-5), a monster's own AI act, or an act an effect queued (a party member's test acts are counters too)
        internal static List<Log> Mine(float since, BattleUnitData who, int ability = 0) =>
            Since(since, who).Where(l => l.Act.Test && (ability == 0 || l.Act.Ability?.Id == ability)).ToList();

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

        // max MP raised to it first (the New Game party's Wedge and Biggs may have none: mp_switch needs MP > 0)
        internal static void SetMp(BattleUnitData u, int mp)
        {
            var p = u?.BattleUnitDataInfo?.Parameter;
            if (p == null) return;
            try { if (p.BaseMaxMp < mp) p.BaseMaxMp = mp; } catch (Exception e) { Hooks.WarnOnce("bc-junction-test-maxmp", e); }
            p.CurrentMP = mp;
        }

        // the Attack command's ability (a plain strike for either side)
        internal static int AttackAbility() => MasterManager.Instance.GetData<Command>(1)?.AbilityId ?? 1;

        // the check's own act (BcJunctionActs.QueueTest: a party member's as a counter, a monster's as Normal); null
        // when it was queued
        internal static string Act(BattleUnitData who, BattleUnitData target, int ability, int command = 0)
        {
            if (who == null || target == null) return "no fighter";
            var a = BcJunctionActs.QueueTest(who, new[] { target }, ability, command);
            return a == null ? $"ability {ability} not queued" : null;
        }

        // what the act hub saw land on `u` since `since` (for failure lines: the next run says why)
        internal static string Seen(float since, BattleUnitData u)
        {
            if (u == null) return "nobody";
            var on = Since(since).Select(l => (l, x: On(l, u))).Where(p => p.x != null && p.x.Targeted).Take(4)
                .Select(p => $"{BcJunction.Who(p.l.Act.Attacker)} {p.l.Act.Ability?.Id ?? 0}/{p.l.Act.Command?.Id ?? 0}{(p.l.Act.Test ? " test" : "")}: " +
                             $"{p.x.Hit} HP {p.x.HpBefore}->{p.x.HpAfter} MP {p.x.MpBefore}->{p.x.MpAfter}{(p.x.Died ? " fell" : "")}").ToList();
            return on.Count == 0 ? $"no act landed on {BcJunction.Who(u)}" : $"on {BcJunction.Who(u)}: " + string.Join("; ", on);
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
