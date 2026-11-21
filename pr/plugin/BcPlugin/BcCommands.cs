using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using HarmonyLib;
using Last.Battle;
using PrKit;

namespace BeyondChaos.PR
{
    // Beyond Chaos's commands that act more than once (tools/bc_commands.py writes the PR command row
    // with the first act; the seed's json has the rest):
    //   N times ("W-", "3x"... BC's MultipleSpellSub)   N acts of the same skill (a random one rolls each time)
    //   chain ("?-", ChainSpellSub)   one act, then another while a coin flip says so (BC: random bit 0 set)
    //   combo (ComboSpellSub)          skill A, then skill B
    //   N times / chain of a combo     each round is A then B
    // Each extra act is a copy of the player's own (BattleActData's copy constructor: the same unit,
    // targets and command) queued the way the game queues the player's act (BattleActExection.
    // SetBattleActData), with the combo's next skill in its ability list. Acts the PR makes itself from
    // an act (a random command's pick: BattleFunction46.CreateAbility) carry no command, so they never
    // come back here.
    // BC's targeting variants are data (the row's ability is a copy with the command's targeting:
    // only self, everyone...), except "a random one" (BC's 0xC0, and a side on a skill that hits one):
    // the SNES hits one unit of the chosen ones at random, so each act here keeps one of its targets.
    static class BcCommands
    {
        internal static int Extra, Retargeted;    // extra acts queued, random targets picked (self-tests, the log)
        internal static string LastNote = "";
        static bool adding;
        static readonly System.Random rng = new System.Random();
        const int ChainCap = BcBattleRules.ChainCap;

        public static void Patch(Harmony h)
        {
            var m = typeof(BattleActExection).GetMethods()
                .FirstOrDefault(x => x.Name == "SetBattleActData" && x.GetParameters().Length == 1 &&
                                     x.GetParameters()[0].ParameterType == typeof(BattleActData));
            if (m == null) { Kit.Warn("[bc] commands: BattleActExection.SetBattleActData(BattleActData) not found: BC's repeating commands act once"); return; }
            Hooks.Patch(h, m, typeof(BcCommands), postfix: nameof(SetBattleActData_Postfix));
            Kit.Info("[bc] commands: BC's repeating, combo and random-target commands hooked");
            // MagiTek outside the armor: for whoever BC's command shuffle dealt it to, and for everyone when
            // BC made the MagiTek command something else (metronome: Random Chaos)
            PrKit.Ff6.SnesMagitek.Tag = "[bc]";
            PrKit.Ff6.SnesMagitek.Dealt = id =>
            {
                var s = Plugin.BcMode ? BcSeeds.Active : null;
                return s != null && (s.Magitek.Contains(id) || s.Commands.ContainsKey(PrKit.Ff6.SnesMagitek.Command));
            };
            PrKit.Ff6.SnesMagitek.Patch(h);
        }

        // self-tests: a command made to act as another kind (BcCommandTests), by PR command id
        internal static readonly Dictionary<int, (BcSeeds.Command Command, string Inner, bool RandomTarget)> TestCommands =
            new Dictionary<int, (BcSeeds.Command, string, bool)>();

        // the command's extra fields in bc_seed.json (inner kind, random target), by PR command id
        static int stamp = -1;
        static readonly Dictionary<int, (string Inner, bool RandomTarget)> extra = new Dictionary<int, (string, bool)>();

        internal static (string Inner, bool RandomTarget) Extras(int id)
        {
            BcBattleData.Refresh();
            if (stamp != BcBattleData.Stamp)
            {
                stamp = BcBattleData.Stamp;
                extra.Clear();
                var cmds = BcBattleData.Section("commands", seedJson: true);
                if (cmds.ValueKind == JsonValueKind.Object)
                    foreach (var p in cmds.EnumerateObject())
                        if (int.TryParse(p.Name, out int cid))
                            extra[cid] = (p.Value.Str("inner", p.Value.Str("kind")), p.Value.Str("target") == "random");
            }
            return extra.TryGetValue(id, out var e) ? e : ("", false);
        }

        // the acts after the first: the ability each one uses (0: the act's own)
        internal static List<int> Plan(BcSeeds.Command c, string inner, Func<bool> coin) =>
            BcBattleRules.ActPlan(c.Kind, inner, c.Count, c.Abilities, coin, ChainCap);

        public static void SetBattleActData_Postfix(BattleActExection __instance, BattleActData battleActData)
        {
            if (adding || battleActData == null || !Plugin.BcMode) return;
            try
            {
                var s = BcSeeds.Active;
                var cmd = battleActData.Command;
                if (s == null || cmd == null) return;
                if (!TestCommands.TryGetValue(cmd.Id, out var test) && !s.Commands.ContainsKey(cmd.Id)) return;
                var c = test.Command ?? s.Commands[cmd.Id];
                if (battleActData.isCounter || battleActData.isCopiedAct || battleActData.AttackUnitData?.TryCast<BattlePlayerData>() == null) return;
                var (inner, randomTarget) = test.Command != null ? (test.Inner, test.RandomTarget) : Extras(cmd.Id);
                var targets = battleActData.TargetUnitDatas;
                if (randomTarget) PickOne(battleActData, targets);
                var more = Plan(c, inner, () => rng.Next(2) == 1);
                if (more.Count == 0) return;
                adding = true;
                try
                {
                    var first = c.Ability;
                    foreach (var ability in more)
                    {
                        var copy = new BattleActData(battleActData);
                        var id = ability == 0 ? first : ability;
                        var a = Last.Data.Master.MasterManager.Instance?.GetData<Last.Data.Master.Ability>(id);
                        if (a != null && copy.abilityList != null)
                        {
                            copy.abilityList.Clear();
                            copy.abilityList.Add(a);
                        }
                        if (randomTarget) PickOne(copy, targets);
                        __instance.SetBattleActData(copy);
                        Extra++;
                    }
                }
                finally { adding = false; }
                LastNote = $"{c.Name}: {more.Count} more act{(more.Count == 1 ? "" : "s")} ({c.Kind}{(inner == "combo" && c.Kind != "combo" ? " of a combo" : "")})";
                Hooks.NoteOnce("bc-commands-" + c.Kind + inner, () => $"[bc] commands: {LastNote}");
            }
            catch (Exception e) { Hooks.WarnOnce("bc-commands", e); }
        }

        // one living unit of the chosen ones, at random (each act its own pick, as each SNES cast)
        static void PickOne(BattleActData act, Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppReferenceArray<BattleUnitData> from)
        {
            if (from == null || from.Length <= 1) return;
            var alive = new List<BattleUnitData>();
            foreach (var u in from)
                if (u != null && u.BattleUnitDataInfo?.Parameter?.CurrentHP > 0) alive.Add(u);
            if (alive.Count == 0) return;
            var one = new Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppReferenceArray<BattleUnitData>(1);
            one[0] = alive[rng.Next(alive.Count)];
            act.TargetUnitDatas = one;
            Retargeted++;
            Hooks.NoteOnce("bc-commands-random-target", () => $"[bc] commands: {act.Command?.Id}'s act hits one of its {from.Length} targets at random");
        }
    }

    // BcCommands' battle self-tests (BcSelfTests): the seed's rows, the act plans, and each kind of BC
    // command the seed has used once by party member 0, plus two made for the test from the seed's own
    // rows: three rounds of a combo, and a skill hitting a random one of its targets
    [SelfTestProvider]
    static class BcCommandTests
    {
        internal static void Register()
        {
            BcSelfTests.Add("commands: rows", Rows);
            BcSelfTests.Add("commands: plans", Plans);
            RegisterDesperation();
            foreach (var kind in new[] { "skill", "random", "combo", "chain", "multiple" })
            {
                int id = 0;
                float t0 = 0;
                BcSelfTests.Add($"commands: {kind} in battle", () => Used(kind, id, t0), () =>
                {
                    id = Pick(c => c.Kind == kind);
                    t0 = UnityEngine.Time.realtimeSinceStartup;
                    if (id != 0) Use(id, 1);
                });
            }
            {
                int id = 0;
                float t0 = 0;
                BcSelfTests.Add("commands: three rounds of a combo", () =>
                {
                    if (id == 0) return "ok: skipped (no combo command in this seed)";
                    var c = BcCommands.TestCommands[id].Command;
                    var got = Got(id, t0);
                    var want = new[] { c.Abilities[0], c.Abilities[1], c.Abilities[0], c.Abilities[1], c.Abilities[0], c.Abilities[1] };
                    if (got.Count < want.Length) return null;
                    BcCommands.TestCommands.Remove(id);
                    var seq = got.Take(want.Length).Select(a => a.Abilities.FirstOrDefault()).ToArray();
                    return seq.SequenceEqual(want) ? $"ok: {string.Join(" ", seq)}" : $"FAILED: acts {string.Join(" ", seq)}, wanted {string.Join(" ", want)}";
                }, () =>
                {
                    id = Pick(c => c.Kind == "combo" && c.Abilities.Length >= 2);
                    t0 = UnityEngine.Time.realtimeSinceStartup;
                    if (id == 0) return;
                    var s = BcSeeds.Active.Commands[id];
                    BcCommands.TestCommands[id] = (new BcSeeds.Command { Kind = "multiple", Count = 3, Name = s.Name, Ability = s.Ability, Abilities = s.Abilities }, "combo", false);
                    Use(id, 1);
                });
            }
            {
                int id = 0, of = 0;
                float t0 = 0;
                BcSelfTests.Add("commands: a random one of the targets", () =>
                {
                    if (id == 0) return "ok: skipped (no single-skill command in this seed)";
                    var got = Got(id, t0);
                    if (got.Count < 2) return null;
                    BcCommands.TestCommands.Remove(id);
                    var counts = got.Take(2).Select(a => a.Targets.Length).ToArray();
                    return counts.All(n => n == 1) || of < 2 ? $"ok: 2 acts, {string.Join(" and ", counts)} target(s) each of {of}"
                                                                : $"FAILED: targets per act {string.Join(", ", counts)} (of {of})";
                }, () =>
                {
                    id = Pick(c => c.Kind == "skill");
                    t0 = UnityEngine.Time.realtimeSinceStartup;
                    if (id == 0) return;
                    var s = BcSeeds.Active.Commands[id];
                    BcCommands.TestCommands[id] = (new BcSeeds.Command { Kind = "multiple", Count = 2, Name = s.Name, Ability = s.Ability, Abilities = s.Abilities }, "skill", true);
                    of = Use(id, 8);
                });
            }
        }

        // R-Limit (desperation): BC's random list of the 12 desperation attacks (SNES F0-FB, PR 228-239) for
        // anyone: each one run from a BC command by party member 0, whoever that is
        internal static readonly int[] Desperation = { 228, 229, 230, 231, 232, 233, 234, 235, 236, 237, 238, 239 };

        static void RegisterDesperation()
        {
            int id = 0;
            float t0 = 0;
            BcSelfTests.Add("commands: desperation attacks from any character", () =>
            {
                if (id == 0) return "ok: skipped (no single-skill command in this seed)";
                var ran = Got(id, t0).SelectMany(a => a.Abilities).ToHashSet();
                var missing = Desperation.Where(a => !ran.Contains(a)).ToList();
                if (missing.Count > 0 && UnityEngine.Time.realtimeSinceStartup - t0 < 50) return null;
                BcCommands.TestCommands.Remove(id);
                return missing.Count == 0 ? $"ok: all 12 ran ({string.Join(" ", Desperation)})" : $"FAILED: never ran {string.Join(" ", missing)}";
            }, () =>
            {
                id = Pick(c => c.Kind == "skill");
                t0 = UnityEngine.Time.realtimeSinceStartup;
                if (id == 0) return;
                var s = BcSeeds.Active.Commands[id];
                BcCommands.TestCommands[id] = (new BcSeeds.Command { Kind = "skill", Name = s.Name, Ability = s.Ability, Abilities = s.Abilities }, "skill", false);
                BcSelfTests.Sturdy();
                var target = BcSelfTests.LivingEnemies().Take(1).ToList();
                foreach (var ab in Desperation)
                {
                    var err = BcSelfTests.Queue(0, id, target, ab);
                    if (err != null) throw new InvalidOperationException(err);
                }
            }, timeout: 60);
        }

        static int Pick(Func<BcSeeds.Command, bool> want) =>
            BcSeeds.Active?.Commands.Where(kv => want(kv.Value)).Select(kv => kv.Key).OrderBy(k => k).FirstOrDefault() ?? 0;

        // party member 0 uses command id on up to n living monsters; returns how many
        static int Use(int id, int n)
        {
            BcSelfTests.Sturdy();
            var targets = BcSelfTests.LivingEnemies().Take(n).ToList();
            var err = BcSelfTests.Queue(0, id, targets);
            if (err != null) throw new InvalidOperationException(err);
            return targets.Count;
        }

        // party member 0's acts since t0 with command id, or the PR's own acts made from them (a random
        // command's pick has no command)
        static List<BcSelfTests.Act> Got(int id, float t0)
        {
            var who = BcSelfTests.Player(0);
            return BcSelfTests.Acts.Where(a => a.Time >= t0 && who != null && a.Unit != null && a.Unit.Pointer == who.Pointer &&
                                               (a.Command == id || a.Command == 0)).ToList();
        }

        static string Rows()
        {
            var s = BcSeeds.Active;
            var mm = Last.Data.Master.MasterManager.Instance;
            var bad = new List<string>();
            foreach (var (id, c) in s.Commands)
            {
                var row = mm.GetData<Last.Data.Master.Command>(id);
                if (row == null || row.AbilityId != c.Ability || row.ListType != 0 || row.ExecutionType != 1) bad.Add($"{id}");
                else if (mm.GetData<Last.Data.Master.Ability>(c.Ability) == null) bad.Add($"{id} (no ability {c.Ability})");
            }
            return bad.Count == 0 ? $"ok: {s.Commands.Count} rows as the seed's" : $"FAILED: rows {string.Join(", ", bad)}";
        }

        static string Plans()
        {
            var combo = new BcSeeds.Command { Kind = "multiple", Count = 3, Abilities = new[] { 10, 20 } };
            var p1 = BcCommands.Plan(combo, "combo", () => false);
            var heads = 0;
            var chain = new BcSeeds.Command { Kind = "chain", Abilities = new[] { 10, 20 } };
            var p2 = BcCommands.Plan(chain, "combo", () => heads++ < 2);
            var p3 = BcCommands.Plan(new BcSeeds.Command { Kind = "multiple", Count = 4, Abilities = new[] { 10 } }, "random", () => false);
            var p4 = BcCommands.Plan(new BcSeeds.Command { Kind = "combo", Abilities = new[] { 10, 20 } }, "combo", () => true);
            string S(List<int> p) => string.Join(" ", p);
            bool ok = S(p1) == "20 0 20 0 20" && S(p2) == "20 0 20 0 20" && S(p3) == "0 0 0" && S(p4) == "20";
            return (ok ? "ok: " : "FAILED: ") + $"x3 combo [{S(p1)}], chain combo 2 heads [{S(p2)}], x4 [{S(p3)}], combo [{S(p4)}]";
        }

        static string Used(string kind, int id, float t0)
        {
            if (id == 0) return $"ok: skipped (no {kind} command in this seed)";
            var c = BcSeeds.Active.Commands[id];
            var got = Got(id, t0);
            var abilities = got.Select(a => a.Abilities.FirstOrDefault()).ToList();
            var inner = BcCommands.Extras(id).Inner;
            switch (kind)
            {
                case "skill":
                    if (got.Count < 1) return null;
                    return abilities[0] == c.Ability ? $"ok: {c.Name} ran ability {c.Ability}" : $"FAILED: ran {abilities[0]}, wanted {c.Ability}";
                case "random":
                    if (got.Count < 2) return null;
                    return abilities[0] == c.Ability && c.Abilities.Contains(abilities[1])
                        ? $"ok: {c.Name} ({c.Ability}) rolled {abilities[1]}"
                        : $"FAILED: acts {string.Join(" ", abilities)} ({c.Name}: {c.Ability} of [{string.Join(" ", c.Abilities)}])";
                case "combo":
                    if (got.Count < c.Abilities.Length) return null;
                    return abilities.Take(c.Abilities.Length).SequenceEqual(c.Abilities)
                        ? $"ok: {c.Name}: {string.Join(" then ", abilities.Take(c.Abilities.Length))}"
                        : $"FAILED: acts {string.Join(" ", abilities)}, wanted {string.Join(" ", c.Abilities)}";
                case "chain":
                    // the coin is BC's: at least one act; the rest get 15 s
                    if (got.Count < 1 || UnityEngine.Time.realtimeSinceStartup - t0 < 15) return null;
                    return $"ok: {c.Name}: {got.Count} act(s)";
                default:
                    int want = c.Count * (inner == "combo" ? Math.Max(1, c.Abilities.Length) : 1) * (inner == "random" ? 2 : 1);
                    if (got.Count < want) return null;
                    return $"ok: {c.Name}: {got.Count} acts (wanted {want})";
            }
        }
    }
}
