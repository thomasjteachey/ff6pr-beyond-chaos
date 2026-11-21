using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Battle;
using Last.Data.Master;
using Action = System.Action;
using PrKit;

namespace BeyondChaos.PR
{
    // A class whose static Register() adds BC self-tests (BcSelfTests.Add): found by this attribute when the
    // harness starts, so a feature brings its own tests and nobody edits a central list.
    [AttributeUsage(AttributeTargets.Class)]
    internal sealed class SelfTestProviderAttribute : Attribute { }

    // Beyond Chaos's in-battle self-tests (as Brave New World's FormulaProbe.AddSelfTest): one headless
    // battle answers every check. The PC test runner's recipe: until startup done; bcgen ...; tofield;
    // bckeep on (auto); battle 25; enemyhp 30000; bcselftest start [filter]; until "bcselftest done". Tests
    // come from [SelfTestProvider] classes (their static Register) or any code calling Add. A test is
    //   Start   run once in the battle (queue an act, set a monster's HP...); may be null
    //   Check   polled every half second: null while waiting, else the result line ("ok ..." / "FAILED ...")
    // and gets Timeout seconds. The act log (Acts) holds every act the game builds while the tests run
    // (Serial.FF6.Calc.FunctionProvider.CreateActFunction: the unit, command, abilities and targets).
    static class BcSelfTests
    {
        internal sealed class Test
        {
            public string Name;
            public Action Start;
            public Func<string> Check;
            public Action Finish;     // run once when the test has its result, however it got it (answer, time-out, throw)
            public float Timeout = 40;
            internal float Began;
            internal string Result;
            internal bool Finished;
        }

        internal sealed class Act
        {
            public BattleUnitData Unit;
            public int Command;
            public int[] Abilities;
            public BattleUnitData[] Targets;
            public float Time;
            public bool Copied, Counter;
        }

        static readonly List<Test> tests = new List<Test>();
        internal static readonly List<Act> Acts = new List<Act>();
        static bool logging, hooked;
        static List<Test> run;

        internal static void Add(string name, Func<string> check, Action start = null, float timeout = 40, Action finish = null)
        {
            tests.RemoveAll(t => t.Name == name);
            tests.Add(new Test { Name = name, Check = check, Start = start, Timeout = timeout, Finish = finish });
        }

        static void Done(Test t, string result)
        {
            t.Result = result;
            FinishOnce(t);
        }

        static void FinishOnce(Test t)
        {
            if (t.Finished) return;
            t.Finished = true;
            try { t.Finish?.Invoke(); }
            catch (Exception e) { Hooks.WarnOnce("bc-selftest-finish-" + t.Name, e); }
        }

        // --- the battle the tests run in ------------------------------------------------------------------

        // null while the battle can run a test, else why not (IsBattle() alone stays true on the victory screen)
        internal static string Over()
        {
            var bm = BattlePlugManager.Instance();
            bool inBattle = bm != null && bm.IsBattle();
            int end = 0, party = 0;
            if (inBattle)
            {
                try { end = (int)bm.BattleEndJugment.GetEndJugment(); } catch (Exception) { }
                try { party = (bm.GetPlayerUnits() ?? new BattlePlayerData[0]).Count(p => p != null && p.BattleUnitDataInfo?.Parameter?.CurrentHP > 0); }
                catch (Exception) { }
            }
            return BcBattleRules.BattleOver(inBattle, end, inBattle ? LivingEnemies().Count : 0, party);
        }

        // The battle's end held off while the tests run (BattleEndJugment.SetEnabled(false), as the kit's AI host does
        // while monsters are made): the PR declares a Win whenever the battle's script isn't running
        // (BattleEndJugment.Execute: Integrator.IsMainCoreAlive false -> result 1; tools/decomp/battle_end), and a
        // harness-started battle sometimes has none (bc-5 bc-selftest-2 and bc-battle-2: won at the first act with
        // every monster at full HP). Put back when the run is done.
        static bool holding;

        static void Hold(bool on)
        {
            holding = on;
            try { BattlePlugManager.Instance()?.BattleEndJugment?.SetEnabled(!on); }
            catch (Exception e) { Hooks.WarnOnce("bc-selftest-hold", e); }
        }

        // per frame (BcHarness.Update): the hold kept (another hook may enable the judgment again)
        internal static void Update()
        {
            if (!holding) return;
            try
            {
                var bm = BattlePlugManager.Instance();
                if (bm == null || !bm.IsBattle()) { holding = false; return; }
                var j = bm.BattleEndJugment;
                if (j != null && j.GetEnabled()) j.SetEnabled(false);
            }
            catch (Exception e) { Hooks.WarnOnce("bc-selftest-hold-update", e); }
        }

        // the battle's own script (sc_b_0239 for most parties: the monsters' AI and the end of the battle)
        static string BattleScript()
        {
            try
            {
                var integ = Last.Interpreter.Integrator.Instance;
                return integ != null && integ.IsMainCoreAlive() ? $"battle script {integ.scriptName} running"
                                                                : "no battle script running (the game would end this battle at the first act: the end is held while the tests run)";
            }
            catch (Exception) { return "battle script ?"; }   // (no exception name: test runners grep for those)
        }

        // the harness command and the battle features' tests (BcHarness.Register calls this)
        internal static void Register()
        {
            Harness.Register("bcselftest", SelfTest, "bcselftest start [filter] | bcselftest: Beyond Chaos's battle self-tests (in a battle; bckeep on first): start them, then each call advances them and reports, ending with 'bcselftest done: ...'");
            Harness.Register("bcselftests", _ => string.Join(", ", tests.Select(t => t.Name)), "bcselftests: the registered battle self-tests");
            // every [SelfTestProvider] class of this plugin registers its own tests
            Type[] types;
            try { types = typeof(BcSelfTests).Assembly.GetTypes(); }
            catch (System.Reflection.ReflectionTypeLoadException e) { types = e.Types.Where(t => t != null).ToArray(); }
            var providers = new List<string>();
            foreach (var t in types)
            {
                if (t.GetCustomAttributes(typeof(SelfTestProviderAttribute), false).Length == 0) continue;
                var m = t.GetMethod("Register", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.Public |
                                                System.Reflection.BindingFlags.NonPublic, null, Type.EmptyTypes, null);
                if (m == null) { Kit.Warn($"[bc selftest] {t.Name} has no static Register()"); continue; }
                try { m.Invoke(null, null); providers.Add(t.Name); }
                catch (Exception e) { Kit.Warn($"[bc selftest] {t.Name}.Register: {e.InnerException?.Message ?? e.Message}"); }
            }
            Kit.Info($"[bc selftest] {tests.Count} tests from {string.Join(", ", providers)} and direct registrations");
        }

        static void Hook()
        {
            if (hooked) return;
            hooked = true;
            var provider = Hooks.TypeByName("Serial.FF6.Calc.FunctionProvider");
            var m = provider == null ? null : AccessTools.Method(provider, "CreateActFunction");
            if (m != null) new Harmony(Plugin.Guid + ".selftests").Patch(m, prefix: new HarmonyMethod(typeof(BcSelfTests), nameof(CreateActFunction_Prefix)));
            else Kit.Warn("[bc selftest] no FunctionProvider.CreateActFunction: no act log");
        }

        public static void CreateActFunction_Prefix(BattleActData battleActData)
        {
            if (!logging || battleActData == null) return;
            try
            {
                Acts.Add(new Act
                {
                    Unit = battleActData.AttackUnitData,
                    Command = battleActData.Command?.Id ?? 0,
                    Abilities = battleActData.abilityList == null ? Array.Empty<int>() : battleActData.abilityList.ToArray().Where(a => a != null).Select(a => a.Id).ToArray(),
                    Targets = battleActData.TargetUnitDatas == null ? Array.Empty<BattleUnitData>() : battleActData.TargetUnitDatas.ToArray(),
                    Time = UnityEngine.Time.realtimeSinceStartup,
                    Copied = battleActData.isCopiedAct, Counter = battleActData.isCounter,
                });
                if (Acts.Count > 2000) Acts.RemoveRange(0, 500);
            }
            catch (Exception e) { Hooks.WarnOnce("bc-selftest-act", e); }
        }

        // "bcselftest start [filter]" begins (returns at once); "bcselftest" advances the tests one step and
        // reports, ending with "bcselftest done: ..." (the runner: until "bcselftest done" check bcselftest)
        static string SelfTest(string[] a)
        {
            float now = UnityEngine.Time.realtimeSinceStartup;
            if (a.Length > 0 && a[0] == "start")
            {
                var bm = BattlePlugManager.Instance();
                if (bm == null || !bm.IsBattle()) return "error: not in a battle";
                var over = Over();
                if (over != null) return $"error: the battle can't run the tests: {over}";
                if (BcSeeds.Active == null) return "error: no Beyond Chaos seed active (bcapply <id>)";
                Hook();
                // filter: words separated by commas; a test runs if its name holds one of the plain words (none:
                // every test) and none of the words starting with "!" ("commands,items" / "!junction")
                var filter = a.Length > 1 ? string.Join(" ", a.Skip(1)) : "";
                run = tests.Where(t => BcBattleRules.FilterMatches(t.Name, filter)).ToList();
                if (run.Count == 0) return $"error: no self-test matches '{filter}'";
                Acts.Clear();
                logging = true;
                foreach (var t in run) { t.Result = null; t.Began = -1; t.Finished = false; }
                var script = BattleScript();
                Hold(true);
                Kit.Info($"[bc selftest] {run.Count} tests ({script}): {string.Join(", ", run.Select(t => t.Name))}");
                return $"bcselftest started: {run.Count} tests; {script}";
            }
            if (run == null) return "error: bcselftest start first";
            var ended = Over();
            // the tests with no Start answer first, whatever their order; then one test with a Start at a time
            // (their acts don't mix), so a slow battle check never holds up an instant one
            foreach (var t in run.Where(x => x.Start == null).Concat(run.Where(x => x.Start != null)))
            {
                if (t.Result != null) continue;
                if (t.Began < 0)
                {
                    if (ended != null) { Done(t, $"FAILED: the battle ended before it started ({ended})"); continue; }
                    if (t.Start != null && run.Any(o => o != t && o.Began >= 0 && o.Result == null && o.Start != null)) break;
                    t.Began = now;
                    try { t.Start?.Invoke(); }
                    catch (Exception e) { Done(t, $"FAILED: start: {e.GetType().Name}: {e.Message}"); Kit.Info($"[bc selftest] {t.Name}: {t.Result}"); continue; }
                }
                string line;
                try { line = t.Check(); }
                catch (Exception e) { line = $"FAILED: {e.GetType().Name}: {e.Message} at {(e.StackTrace ?? "").Split((char)10).FirstOrDefault()?.Trim()}"; }
                if (line == null && now - t.Began > t.Timeout) line = $"FAILED: no answer in {t.Timeout:0} s";
                if (line == null && ended != null) line = $"FAILED: the battle ended first ({ended})";
                if (line == null) { if (t.Start != null) break; continue; }
                Done(t, line);
                Kit.Info($"[bc selftest] {t.Name}: {line}");
            }
            var waiting = run.Where(t => t.Result == null).ToList();
            if (waiting.Count > 0)
                return $"bcselftest running: {run.Count - waiting.Count} of {run.Count} answered; now {waiting[0].Name}";
            logging = false;
            if (holding) Hold(false);
            int failed = run.Count(t => !t.Result.StartsWith("ok"));
            return $"bcselftest done: {run.Count - failed} passed, {failed} failed; " +
                   string.Join("; ", run.Select(t => $"{t.Name}: {t.Result}"));
        }

        // --- on the kit's self-test runner (PrKit/SelfTests.cs; BcChecks' `selftest`) -----------------------------
        // Every registered test is also the kit runner's `bc.battle.<name>` (Needs "battle"): the same Start and Check,
        // run one at a time (`selftest bc.battle.*`, or one by name). `bcselftest` above stays for one more test batch
        // (the BC lead's plan, 2026-11-21), then goes.
        internal const string KitPrefix = "bc.battle.";

        internal static IEnumerable<SelfTests.Entry> KitEntries()
        {
            var body = typeof(BcSelfTests).GetMethod(nameof(KitTest), System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic);
            foreach (var t in tests)
                yield return new SelfTests.Entry
                {
                    Name = KitPrefix + t.Name,
                    Info = new SelfTestAttribute(KitPrefix + t.Name) { Needs = "battle", Timeout = t.Timeout + 150, Doc = "BC battle self-test" },
                    Method = body,
                };
        }

        static IEnumerable<TestStep> KitTest(TestContext ctx)
        {
            var t = tests.FirstOrDefault(x => KitPrefix + x.Name == ctx.Name);
            if (!ctx.Check(t != null, "registered") || !ctx.Check(BcSeeds.Active != null, "a Beyond Chaos seed active")) yield break;
            var over = Over();
            if (!ctx.Check(over == null, over ?? "the battle can run it")) yield break;
            Hook();
            logging = true;
            t.Finished = false;
            Hold(true);     // kept after the test: the kit runs the next one at once (bcselftest's done puts it back)
            try
            {
                if (t.Start != null)
                {
                    string bad = null;
                    try { t.Start(); }
                    catch (Exception e) { bad = $"start: {e.GetType().Name}: {e.Message}"; }
                    if (bad != null) { ctx.Check(false, bad); yield break; }
                }
                string line = null, ended = null;
                yield return ctx.Until(() =>
                {
                    try { line = t.Check(); }
                    catch (Exception e) { line = $"FAILED: {e.GetType().Name}: {e.Message}"; }
                    ended = Over();
                    return line != null || ended != null;
                }, t.Timeout, t.Name);
                ctx.Check(line != null && line.StartsWith("ok"), line ?? $"the battle ended first ({ended})");
            }
            finally { FinishOnce(t); }
        }

        // --- helpers for tests ------------------------------------------------------------------------

        internal static BattlePlayerData Player(int slot)
        {
            var p = BattlePlugManager.Instance()?.GetPlayerUnits();
            return p != null && slot >= 0 && slot < p.Length ? p[slot] : null;
        }

        internal static List<BattleUnitData> LivingEnemies() =>
            (BattlePlugManager.Instance()?.GetEnemyUnits() ?? new BattleEnemyData[0])
                .Where(e => e != null && e.BattleUnitDataInfo?.Parameter?.CurrentHP > 0).Cast<BattleUnitData>().ToList();

        // every living monster's HP to hp (so the test's acts have someone to hit)
        internal static void Sturdy(int hp = 30000)
        {
            foreach (var e in LivingEnemies())
            {
                var p = e.BattleUnitDataInfo.Parameter;
                if (p.BaseMaxHp < hp) p.BaseMaxHp = hp;
                p.CurrentHP = hp;
            }
        }

        // a party member's act with a PR command (its row's ability), queued as the game queues the player's
        internal static string Queue(int slot, int commandId, IList<BattleUnitData> targets, int ability = 0)
        {
            var bm = BattlePlugManager.Instance();
            var who = Player(slot);
            if (bm == null || who == null) return $"no party member in slot {slot}";
            var mm = MasterManager.Instance;
            var cmd = mm.GetData<Command>(commandId);
            var ab = mm.GetData<Ability>(ability != 0 ? ability : cmd?.AbilityId ?? 0);
            if (cmd == null || ab == null) return $"command {commandId} has no ability";
            var abilities = new Il2CppSystem.Collections.Generic.List<Ability>();
            abilities.Add(ab);
            var arr = new Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppReferenceArray<BattleUnitData>(targets.Count);
            for (int i = 0; i < targets.Count; i++) arr[i] = targets[i];
            var act = new BattleActData(who, arr, cmd, abilities, BattleActData.ActType.Normal,
                targets.Count > 1 ? BattleActData.TargetType.AllEnemy : BattleActData.TargetType.SingleEnemy,
                BattleActData.ArmType.Right, (BattleActData.ActAbilityType)0, 1, false);
            bm.BattleActExection.SetBattleActData(act);
            return null;
        }

        // the acts a unit made with a command since a time
        internal static List<Act> ActsBy(BattleUnitData who, int command, float since) =>
            Acts.Where(x => x.Time >= since && x.Command == command && who != null && x.Unit != null && x.Unit.Pointer == who.Pointer).ToList();
    }
}
