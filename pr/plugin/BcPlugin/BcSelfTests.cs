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
            public float Timeout = 40;
            internal float Began;
            internal string Result;
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

        internal static void Add(string name, Func<string> check, Action start = null, float timeout = 40)
        {
            tests.RemoveAll(t => t.Name == name);
            tests.Add(new Test { Name = name, Check = check, Start = start, Timeout = timeout });
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
                if (BcSeeds.Active == null) return "error: no Beyond Chaos seed active (bcapply <id>)";
                Hook();
                // filter: words separated by commas; a test runs if its name holds one of the plain words (none:
                // every test) and none of the words starting with "!" ("commands,items" / "!junction")
var filter = a.Length > 1 ? string.Join(" ", a.Skip(1)) : "";
                run = tests.Where(t => BcBattleRules.FilterMatches(t.Name, filter)).ToList();
                if (run.Count == 0) return $"error: no self-test matches '{filter}'";
                Acts.Clear();
                logging = true;
                foreach (var t in run) { t.Result = null; t.Began = -1; }
                Kit.Info($"[bc selftest] {run.Count} tests: {string.Join(", ", run.Select(t => t.Name))}");
                return $"bcselftest started: {run.Count} tests";
            }
            if (run == null) return "error: bcselftest start first";
            var battle = BattlePlugManager.Instance();
            bool inBattle = battle != null && battle.IsBattle();
            // the tests with no Start answer first, whatever their order; then one test with a Start at a time
            // (their acts don't mix), so a slow battle check never holds up an instant one
            foreach (var t in run.Where(x => x.Start == null).Concat(run.Where(x => x.Start != null)))
            {
                if (t.Result != null) continue;
                if (t.Began < 0)
                {
                    if (!inBattle) { t.Result = "FAILED: the battle ended before it started"; continue; }
                    if (t.Start != null && run.Any(o => o != t && o.Began >= 0 && o.Result == null && o.Start != null)) break;
                    t.Began = now;
                    try { t.Start?.Invoke(); }
                    catch (Exception e) { t.Result = $"FAILED: start: {e.GetType().Name}: {e.Message}"; Kit.Info($"[bc selftest] {t.Name}: {t.Result}"); continue; }
                }
                string line;
                try { line = t.Check(); }
                catch (Exception e) { line = $"FAILED: {e.GetType().Name}: {e.Message} at {(e.StackTrace ?? "").Split((char)10).FirstOrDefault()?.Trim()}"; }
                if (line == null && now - t.Began > t.Timeout) line = $"FAILED: no answer in {t.Timeout:0} s";
                if (line == null && !inBattle) line = "FAILED: the battle ended first";
                if (line == null) { if (t.Start != null) break; continue; }
                t.Result = line;
                Kit.Info($"[bc selftest] {t.Name}: {line}");
            }
            var waiting = run.Where(t => t.Result == null).ToList();
            if (waiting.Count > 0)
                return $"bcselftest running: {run.Count - waiting.Count} of {run.Count} answered; now {waiting[0].Name}";
            logging = false;
            int failed = run.Count(t => !t.Result.StartsWith("ok"));
            return $"bcselftest done: {run.Count - failed} passed, {failed} failed; " +
                   string.Join("; ", run.Select(t => $"{t.Name}: {t.Result}"));
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
