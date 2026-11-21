using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Last.Battle;
using Last.Data;
using HarmonyLib;
using PrKit;
using PrKit.Ff6;

namespace BeyondChaos.PR
{
    // Beyond Chaos's small codes that are plugin code (the data ones are tools/bc_codes.py's), reading the
    // seed's bc_battle.json "codes" (BcBattleData). PORTING.md "Beyond Chaos port" lists which code is where.
    static class BcCodes
    {
        // a code's part in bc_battle.json "codes" (default: off)
        internal static JsonElement Code(string name)
        {
            var c = BcBattleData.Section("codes");
            return c.ValueKind == JsonValueKind.Object && c.TryGetProperty(name, out var v) ? v : default;
        }

        internal static bool On(string name) => Code(name).ValueKind != JsonValueKind.Undefined;
        internal static bool InformTest;     // self-test: informative misses on whatever the seed says

        // a flag or code in the active seed's flag string (BC's own words: "suplexwrecks", "b", "cap_type:chaos")
        internal static bool HasFlag(string name)
        {
            var f = BcSeeds.Active?.Flags;
            if (string.IsNullOrEmpty(f)) return false;
            foreach (var w in f.Split(' ')) if (w == name || w.StartsWith(name + ":")) return true;
            return false;
        }

        public static void Patch(Harmony h)
        {
            BcEncounters.Patch(h);
            // `l`: BC's Blitz inputs (C4/7A40, read at seed time) asked for and shown by the PR's Blitz
            SnesBlitzInputs.Tag = "[bc]";
            SnesBlitzInputs.Seed = BlitzInputs;
            SnesBlitzInputs.Patch(h);
            BcLevelCap.Patch(h);
            BcCursePower.Patch(h);
            BcNoRng.Patch(h);
            BcMpParty.Patch(h);
            BcPlaysItself.Patch(h);
            BcMementoMori.Patch(h);
            BcMagicNumbers.Patch(h);
            // `informativemiss`: Null / Fail in place of Miss (the kit's copy of Bropedio's patch, as BNW's)
            SnesInformativeMiss.Apply(h, new SnesInformativeMissMod
            {
                Name = "Beyond Chaos", Tag = "[bc]",
                Enabled = () => Plugin.BcMode && BcSeeds.Active != null && (InformTest || On("informativemiss")),
            });
            // Suplex misses the monsters the SNES won't let it hit (monster byte $13 bit 2; BC never changes that bit,
            // so vanilla's list is the seed's), except with suplexwrecks, which clears it on every monster
            SnesSuplex.Apply(h, new SnesSuplexMod
            {
                Name = "Beyond Chaos",
                Enabled = () => Plugin.BcMode && BcSeeds.Active != null && !HasFlag("suplexwrecks"),
            });
        }

        static int blitzStamp = -1;
        static System.Collections.Generic.Dictionary<int, int[]> blitz;

        static System.Collections.Generic.IReadOnlyDictionary<int, int[]> BlitzInputs()
        {
            if (!Plugin.BcMode || BcSeeds.Active == null) return null;
            BcBattleData.Refresh();
            if (blitzStamp != BcBattleData.Stamp)
            {
                blitzStamp = BcBattleData.Stamp;
                blitz = null;
                var l = Code("l");
                if (l.ValueKind == JsonValueKind.Object)
                {
                    blitz = new System.Collections.Generic.Dictionary<int, int[]>();
                    foreach (var p in l.EnumerateObject())
                        if (int.TryParse(p.Name, out int ab)) blitz[ab] = System.Linq.Enumerable.ToArray(System.Linq.Enumerable.Select(p.Value.EnumerateArray(), x => x.GetInt32()));
                }
            }
            return blitz;
        }
    }

    // BC's random battles as its ROM counts them on the SNES: the kit's SnesEncounters (the SNES's danger
    // counter on the PR's steps, as Worlds Collide and Brave New World) with the rules tools/bc_battle.py read
    // from BC's output ROM (tools/port_encounter_rates.py: rate tables C0/C29F and C0/C2BF, zone and map codes,
    // the battle roll, the party odds). `dearestmolulu` is those tables (BC: no battles without an encounter
    // relic; the relics' rows raise them), so it needs nothing more here.
    static class BcEncounters
    {
        static int stamp = -1;
        static SnesEncounterRules rules;

        internal static SnesEncounterRules Rules
        {
            get
            {
                BcBattleData.Refresh();
                if (stamp != BcBattleData.Stamp)
                {
                    stamp = BcBattleData.Stamp;
                    rules = null;
                    var e = BcBattleData.Section("encounters");
                    if (e.ValueKind == JsonValueKind.Object)
                    {
                        try { rules = SnesEncounterRules.Parse(e); }
                        catch (Exception ex) { Kit.Warn($"[bc] encounters: the seed's rules don't read: {ex.Message} (the game's own step counter)"); }
                    }
                    Kit.Info($"[bc] encounters: {(rules != null ? "BC's SNES rules (" + rules.Name + ")" : "the game's own step counter (no rules in the seed)")}");
                }
                return rules;
            }
        }

        sealed class Bc : SnesEncounterMod
        {
            public override SnesEncounterRules Rules => BcEncounters.Rules ?? SnesEncounterRules.Vanilla;
            public override bool Active => Plugin.BcMode && BcSeeds.Active != null && BcEncounters.Rules != null;
            public override string Tag => "bc";
        }

        internal static void Patch(Harmony h) => SnesEncounters.Patch(h, new Bc());
    }

    // `levelcap` (+ cap_type, cap_min, cap_max; BC's caps read back from F0/3173): a character stops levelling at
    // his cap (SNES C2/6070 -> F0/30A3 in battle, the join levelling and the raise-to-average events) and keeps
    // gaining EXP. The PR levels a character in StatusUpProvider.Execution (battles; Current.CorrectLevel sets
    // the EXP of a join's level and calls it too), reading the level from ExpUtility.GetExpLevel: while it runs
    // for a capped character the level answers no higher than the cap. Not carried: capped members not
    // counting in the EXP split, the Status screen's "next level" for a capped character.
    static class BcLevelCap
    {
        static int stamp = -1, capNow;
        static readonly Dictionary<int, int> caps = new Dictionary<int, int>();
        internal static int Capped;
        internal static readonly Dictionary<int, int> TestCaps = new Dictionary<int, int>();

        internal static int CapOf(int characterStatusId)
        {
            if (TestCaps.TryGetValue(characterStatusId, out var t)) return t;
            if (!Plugin.BcMode || BcSeeds.Active == null) return 0;
            BcBattleData.Refresh();
            if (stamp != BcBattleData.Stamp)
            {
                stamp = BcBattleData.Stamp;
                caps.Clear();
                var lc = BcCodes.Code("levelcap");
                if (lc.ValueKind == JsonValueKind.Object && lc.TryGetProperty("caps", out var c) && c.ValueKind == JsonValueKind.Object)
                    foreach (var p in c.EnumerateObject())
                        if (int.TryParse(p.Name, out int id)) caps[id] = p.Value.GetInt32();
                if (caps.Count > 0) Kit.Info($"[bc] levelcap: {string.Join(", ", caps.Select(kv => $"{kv.Key}:{kv.Value}"))}");
            }
            return caps.TryGetValue(characterStatusId, out var cap) ? cap : 0;
        }

        internal static void Patch(Harmony h)
        {
            int n = 0;
            if (Hooks.Patch(h, typeof(Last.Systems.StatusUpProvider), "Execution", typeof(BcLevelCap), prefix: nameof(Execution_Prefix), postfix: nameof(Execution_Postfix))) n++;
            if (Hooks.Patch(h, typeof(Last.Systems.ExpUtility), "GetExpLevel", typeof(BcLevelCap), postfix: nameof(GetExpLevel_Postfix))) n++;
            Kit.Info($"[bc] levelcap: {n} of 2 hooks");
        }

        public static void Execution_Prefix(Last.Data.User.OwnedCharacterData target)
        {
            try { capNow = target == null ? 0 : CapOf(target.characterStatusId); }
            catch (Exception e) { capNow = 0; Hooks.WarnOnce("bc-levelcap", e); }
        }

        public static void Execution_Postfix() => capNow = 0;

        public static void GetExpLevel_Postfix(ref int __result)
        {
            int was = __result;
            __result = BcBattleRules.CappedLevel(__result, capNow);
            if (__result != was) Capped++;
        }
    }

    // `cursepower` (N read back from BC's C2/6001 patch): the Cursed Shield uncurses after its N-th battle
    // (vanilla 256). The PR counts in a script variable (kScenarioVariable 9) in Current.CursedShield, run
    // after each battle: +1 when a party member wears it (content 213), uncursed at 256. Before that call, a
    // count that this battle takes to N goes to 255, so the game's own check uncurses it.
    static class BcCursePower
    {
        const int ShieldContent = 213, Counter = 9;

        internal static int Goal()
        {
            var c = BcCodes.Code("cursepower");
            return c.ValueKind == JsonValueKind.Object ? c.Int("battles", 0) : 0;
        }

        internal static void Patch(Harmony h)
        {
            if (Hooks.Patch(h, typeof(Last.Interpreter.Instructions.SystemCall.Current), "CursedShield", typeof(BcCursePower), prefix: nameof(CursedShield_Prefix)))
                Kit.Info("[bc] cursepower: hooked");
        }

        public static void CursedShield_Prefix()
        {
            try
            {
                if (!Plugin.BcMode || BcSeeds.Active == null) return;
                int goal = Goal();
                if (goal <= 0 || goal >= 256) return;
                var ds = Last.Interpreter.DataStorage.Instance;
                var bm = BattlePlugManager.Instance();
                if (ds == null || bm == null) return;
                bool worn = false;
                foreach (var p in bm.GetPlayerUnits() ?? new BattlePlayerData[0])
                    if (BcItems.Worn(p?.ownedCharacterData).Contains(ShieldContent)) worn = true;
                if (!worn) return;
                int n = ds.Get(Last.Interpreter.DataStorage.Category.kScenarioVariable, Counter);
                if (BcBattleRules.CurseCounter(n, goal) != n)
                {
                    ds.Set(Last.Interpreter.DataStorage.Category.kScenarioVariable, Counter, 255);
                    Kit.Info($"[bc] cursepower: battle {n + 1} of {goal} with the Cursed Shield: it uncurses now");
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-cursepower", e); }
        }
    }

    // `norng` (BC zeroed the SNES's random table C0/FD00): every battle roll is 0. In a battle the PR's own
    // rolls (CommonUtility.GetRand / GetRandPlus / GetRandWeight / GetBoolRand) answer their lowest value, and
    // the kit's SNES AI interpreter (BC's monster scripts) draws 0. As on the SNES: the minimum damage
    // variance, a critical whenever one can happen, the rare steal and drop, the AI's first choice.
    static class BcNoRng
    {
        static bool on;
        static int stamp = -1;
        internal static bool TestOn;
        internal static int Forced;

        internal static bool On
        {
            get
            {
                if (TestOn) return true;
                if (!Plugin.BcMode || BcSeeds.Active == null) return false;
                BcBattleData.Refresh();
                if (stamp != BcBattleData.Stamp) { stamp = BcBattleData.Stamp; on = BcCodes.On("norng"); }
                return on;
            }
        }

        static bool Now => On && (BattlePlugManager.Instance()?.IsBattle() ?? false);

        sealed class Zero : System.Random
        {
            public override int Next() => 0;
            public override int Next(int max) => 0;
            public override int Next(int min, int max) => min;
            public override double NextDouble() => 0;
        }

        internal static void Patch(Harmony h)
        {
            var t = typeof(global::CommonUtility);
            int n = 0;
            foreach (var m in t.GetMethods(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static))
            {
                string post = m.Name switch
                {
                    "GetRand" or "GetRandPlus" => m.ReturnType == typeof(float) ? nameof(Float_Postfix) : nameof(Int_Postfix),
                    "GetRandWeight" => nameof(Weight_Postfix),
                    "GetBoolRand" => nameof(Bool_Postfix),
                    _ => null,
                };
                if (post == null) continue;
                try { h.Patch(m, postfix: new HarmonyMethod(typeof(BcNoRng), post)); n++; }
                catch (Exception e) { Kit.Warn($"[bc] norng: {m.Name}: {e.Message}"); }
            }
            Kit.Info($"[bc] norng: {n} random functions hooked");
        }

        // the kit's AI interpreter: its fight's generator draws 0 (BcBattle.Update, each frame in a battle)
        internal static void Update()
        {
            if (!Now) return;
            var f = PrKit.Ff6.SnesAiHost.Current;
            if (f != null && !(f.Rng is Zero)) f.Rng = new Zero();
        }

        public static void Int_Postfix(object[] __args, ref int __result)
        {
            if (!Now) return;
            __result = __args.Length >= 2 ? (int)__args[0] : 0;
            Forced++;
        }

        public static void Float_Postfix(object[] __args, ref float __result)
        {
            if (!Now) return;
            __result = __args.Length >= 2 ? (float)__args[0] : 0f;
            Forced++;
        }

        public static void Weight_Postfix(object[] __args, ref int __result)
        {
            if (!Now) return;
            try
            {
                if (__args[0] is Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppStructArray<int> w)
                {
                    for (int i = 0; i < w.Length; i++) if (w[i] > 0) { __result = i; Forced++; return; }
                }
                else if (__args[0] is Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppStructArray<float> f)
                {
                    for (int i = 0; i < f.Length; i++) if (f[i] > 0) { __result = i; Forced++; return; }
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-norng-weight", e); }
        }

        public static void Bool_Postfix(int weight, ref bool __result)
        {
            if (!Now) return;
            __result = weight > 0;
            Forced++;
        }
    }

    // BcCodes' battle self-tests (BcSelfTests)
    [SelfTestProvider]
    static class BcCodeTests
    {
        internal static void Register()
        {
            BcSelfTests.Add("codes: levelcap", LevelCap);
            BcSelfTests.Add("codes: norng", NoRng);
            BcSelfTests.Add("codes: Blitz inputs", Blitz);
            BcSelfTests.Add("codes: mementomori", Memento);
            BcSelfTests.Add("codes: equipanything", () =>
            {
                BcEquipAnything.TestOn = true;
                BcEquipAnything.Update();
                bool head = Last.Systems.EquipUtility.IsEquipSlot(Last.Data.Master.MasterManager.Instance.GetData<Last.Data.Master.PartsGroup>(3),
                                                                  Last.Defaine.EquipSlotType.Slot1, Last.Defaine.EquipSlotType.Slot1, false);
                BcEquipAnything.TestOn = false;
                BcEquipAnything.Update();
                bool after = Last.Systems.EquipUtility.IsEquipSlot(Last.Data.Master.MasterManager.Instance.GetData<Last.Data.Master.PartsGroup>(3),
                                                                   Last.Defaine.EquipSlotType.Slot1, Last.Defaine.EquipSlotType.Slot1, false);
                return head && !after ? "ok: a helmet fits a hand with the code, not without" : $"FAILED: with the code {head}, without {after}";
            });
            {
                int shown0 = 0;
                float t0 = 0;
                BcSelfTests.Add("codes: informativemiss", () =>
                {
                    if (UnityEngine.Time.realtimeSinceStartup - t0 < 1) return null;
                    BcCodes.InformTest = false;
                    var lang = (int)(Last.Management.MessageManager.Instance?.currentLanguage ?? 0);
                    if (SnesInformativeMiss.Shown > shown0) return $"ok: a FAIL popup drawn in place of Miss ({SnesInformativeMiss.Shown - shown0})";
                    return lang != 2 ? $"ok: skipped (the game's language is {lang}, not English: Miss stays)" : "FAILED: no FAIL popup";
                }, () =>
                {
                    t0 = UnityEngine.Time.realtimeSinceStartup;
                    shown0 = SnesInformativeMiss.Shown;
                    BcCodes.InformTest = true;
                    SnesInformativeMiss.Forced = SnesInformativeMiss.Kind.Fail;
                    BattleUtility.CreateDamageView(BcSelfTests.LivingEnemies().FirstOrDefault(), 0, false, true);
                }, timeout: 10);
            }
            {
                ViewDamageEntity view = null;
                float t0 = 0;
                BcSelfTests.Add("codes: magicnumbers", () =>
                {
                    if (UnityEngine.Time.realtimeSinceStartup - t0 < 1) return null;
                    BcMagicNumbers.TestOn = false;
                    if (view == null) return "FAILED: no popup made";
                    var g = view.GetComponentsInChildren<UnityEngine.UI.Graphic>(true);
                    var tinted = g.Count(x => x != null && Math.Abs(x.color.b - 1f) < 0.01f && Math.Abs(x.color.r - 0.78f) < 0.01f);
                    return BcMagicNumbers.Tinted > 0 ? $"ok: the MP damage popup taken ({BcMagicNumbers.Tinted}); {tinted} of {g.Length} images violet"
                                                     : "FAILED: the popup wasn't taken for tinting";
                }, () =>
                {
                    t0 = UnityEngine.Time.realtimeSinceStartup;
                    BcMagicNumbers.TestOn = true;
                    var target = BcSelfTests.LivingEnemies().FirstOrDefault();
                    BcMagicNumbers.Basic_Prefix(Last.Systems.HitType.MPHit);
                    try { view = BattleUtility.CreateDamageView(target, 123, false, false); }
                    finally { BcMagicNumbers.Basic_Postfix(); }
                }, timeout: 10);
            }
        }

        // party member 0 capped at his level: the level an EXP far past it reads, then a real level-up pass
        static string LevelCap()
        {
            var who = BcSelfTests.Player(0)?.ownedCharacterData;
            var prm = who?.Parameter;
            if (prm == null) return "FAILED: no party member 0";
            int lv = prm.BaseLevel, id = who.characterStatusId, exp = who.AdditionalExp;
            BcLevelCap.TestCaps[id] = lv;
            try
            {
                BcLevelCap.Execution_Prefix(who);
                int read = Last.Systems.ExpUtility.GetExpLevel(1, 15000000);
                BcLevelCap.Execution_Postfix();
                if (read != lv) return $"FAILED: level read {read} at the cap {lv}";
                string real = "not run";
                var provider = Last.Management.StatusUpProviderInstanceManager.Instance()?.GetCurrentProvider()?.TryCast<Last.Systems.StatusUpProvider>();
                if (provider != null)
                {
                    who.AdditionalExp = exp + 5000000;
                    try { provider.Execution(who, 0, null); real = $"level {prm.BaseLevel} after a level-up pass with 5,000,000 more EXP"; }
                    catch (Exception e) { real = $"the level-up pass threw {e.GetType().Name}"; }
                    finally { who.AdditionalExp = exp; }
                    if (prm.BaseLevel != lv) return $"FAILED: {who.Name} went from {lv} to {prm.BaseLevel} past the cap";
                }
                return $"ok: {who.Name} capped at {lv} (reads {read}; {real})";
            }
            finally { BcLevelCap.TestCaps.Remove(id); }
        }

        static string NoRng()
        {
            BcNoRng.TestOn = true;
            try
            {
                int a = global::CommonUtility.GetRand(100), b = global::CommonUtility.GetRand(5, 10);
                bool c = global::CommonUtility.GetBoolRand(1, 100);
                var w = new Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppStructArray<int>(3);
                w[0] = 0; w[1] = 3; w[2] = 5;
                int d = global::CommonUtility.GetRandWeight(w);
                bool ok = a == 0 && b == 5 && c && d == 1;
                return (ok ? "ok: " : "FAILED: ") + $"GetRand(100) {a}, GetRand(5,10) {b}, GetBoolRand(1,100) {c}, weights 0/3/5 -> {d}";
            }
            finally { BcNoRng.TestOn = false; }
        }

        // party member 0 given a hidden relic for the test: a relic with Strength, then one with a worn status
        static string Memento()
        {
            var who = BcSelfTests.Player(0)?.ownedCharacterData;
            var p = who?.Parameter;
            if (p == null) return "FAILED: no party member 0";
            var armors = new List<Last.Data.Master.Armor>();
            foreach (var a in Last.Data.Master.MasterManager.Instance.GetList<Last.Data.Master.Armor>().Values) if (a != null) armors.Add(a);
            var strong = armors.FirstOrDefault(a => a.Strength > 0);
            var worn = armors.FirstOrDefault(a => a.WearConditionGroupId != 0 && a.Strength == 0);
            if (strong == null || worn == null) return "FAILED: no test relic in the armor table";
            int id = who.characterStatusId;
            int before = p.ConfirmedPower();
            int n0 = p.GetEquipmentConfirmedConditionList()?.Count ?? 0;
            try
            {
                BcMementoMori.TestRelics[id] = strong.Id;
                int after = p.ConfirmedPower();
                BcMementoMori.TestRelics[id] = worn.Id;
                int n1 = p.GetEquipmentConfirmedConditionList()?.Count ?? 0;
                bool ok = after == Math.Min(255, before + strong.Strength) && n1 > n0;
                return (ok ? "ok: " : "FAILED: ") + $"Strength {before} -> {after} with armor {strong.Id} (+{strong.Strength}); worn statuses {n0} -> {n1} with armor {worn.Id}";
            }
            finally { BcMementoMori.TestRelics.Remove(id); }
        }

        // the PR's own lists for the eight Blitzes and the SNES buttons it stands for (learned once a seed has `l`)
        static string Blitz()
        {
            return $"ok: hooked; {SnesBlitzInputs.Served} lists served from the seed; mapping {(SnesBlitzInputs.Learned == "" ? "not learned yet (no seed with `l` asked)" : SnesBlitzInputs.Learned)}";
        }
    }

    // `playsitself` (BC: C2/091F's branch makes every character act as Umaro does: no command menu, a random
    // command of his own from the "usable automatically" tables C2/04D0 and C2/04D4, a random skill under a list
    // command (C2/04D8: a castable spell for Magic, a known Blitz, Lore, Dance...)): the party stays on the PR's
    // auto-battle in a BC battle with it, so no command menu opens, and each time the auto-battle builds an act
    // (ActSelectAuto.CreateActDataAuto: the replay of the remembered act, aimed by the game) that act is first
    // made a random allowed command of the character's own, with a random ability it knows and can pay for.
    static class BcPlaysItself
    {
        static int stamp = -1;
        static bool on;
        static readonly HashSet<int> allowed = new HashSet<int>();
        static readonly System.Random Rng = new System.Random();
        internal static int Frames, Picks;
        internal static string LastPick = "";

        internal static bool On
        {
            get
            {
                if (!Plugin.BcMode || BcSeeds.Active == null) return false;
                BcBattleData.Refresh();
                if (stamp != BcBattleData.Stamp)
                {
                    stamp = BcBattleData.Stamp;
                    var c = BcCodes.Code("playsitself");
                    on = c.ValueKind != JsonValueKind.Undefined;
                    allowed.Clear();
                    if (c.ValueKind == JsonValueKind.Object && c.TryGetProperty("commands", out var cmds) && cmds.ValueKind == JsonValueKind.Array)
                        foreach (var x in cmds.EnumerateArray()) allowed.Add(x.GetInt32());
                }
                return on;
            }
        }

        internal static void Patch(Harmony h)
        {
            var m = AccessTools.Method(typeof(ActSelectAuto), "CreateActDataAuto", new[] { typeof(BattleActData) });
            if (m == null) { Kit.Warn("[bc] playsitself: ActSelectAuto.CreateActDataAuto(BattleActData) not found: the auto-battle repeats acts"); return; }
            h.Patch(m, prefix: new HarmonyMethod(typeof(BcPlaysItself), nameof(CreateActDataAuto_Prefix)) { priority = Priority.First });
            Kit.Info("[bc] playsitself: hooked");
        }

        internal static void Update()
        {
            if (!On) return;
            var bm = BattlePlugManager.Instance();
            if (bm == null || !bm.IsBattle()) return;
            try
            {
                Last.UI.BattleUIManager.Instance?.SetIsAuto(true);
                if (Frames++ == 0) Kit.Info("[bc] playsitself: the party fights on auto-battle (no command menus)");
            }
            catch (Exception e) { Hooks.WarnOnce("bc-playsitself", e); }
        }

        // the act the auto-battle is about to rebuild becomes a random allowed command (before the kit's own
        // autobattle prefix, which still rebuilds a Mug its way)
        public static void CreateActDataAuto_Prefix(BattleActData __0)
        {
            try
            {
                if (__0 == null || !On || allowed.Count == 0) return;
                var owned = __0.AttackUnitData?.TryCast<BattlePlayerData>()?.ownedCharacterData;
                if (owned?.CommandList == null) return;
                var mm = Last.Data.Master.MasterManager.Instance;
                var options = new List<(Last.Data.Master.Command Cmd, Last.Data.Master.Ability Ab)>();
                int mp = owned.Parameter?.CurrentMP ?? 0;
                foreach (var cmd in owned.CommandList)
                {
                    if (cmd == null || !allowed.Contains(cmd.Id)) continue;
                    if (cmd.ListType == 0 && cmd.AbilityId != 0)
                    {
                        var ab = mm.GetData<Last.Data.Master.Ability>(cmd.AbilityId);
                        if (ab != null) options.Add((cmd, ab));
                        continue;
                    }
                    var dict = owned.AbilityDictionary;
                    if (dict == null || !dict.ContainsKey(cmd)) continue;
                    var known = new List<Last.Data.Master.Ability>();
                    foreach (var oa in dict[cmd])
                        if (oa?.Ability != null && oa.Ability.UseValue <= mp) known.Add(oa.Ability);
                    if (known.Count > 0) options.Add((cmd, known[Rng.Next(known.Count)]));
                }
                if (options.Count == 0) return;
                var (c, a) = options[Rng.Next(options.Count)];
                __0.Command = c;
                if (__0.abilityList == null) __0.abilityList = new Il2CppSystem.Collections.Generic.List<Last.Data.Master.Ability>();
                __0.abilityList.Clear();
                __0.abilityList.Add(a);
                Picks++;
                LastPick = $"{owned.Name}: command {c.Id}, ability {a.Id} (of {options.Count} commands)";
                Hooks.NoteOnce("bc-playsitself-pick", () => $"[bc] playsitself: {LastPick}");
            }
            catch (Exception e) { Hooks.WarnOnce("bc-playsitself-pick", e); }
        }
    }

    // `mpparty`: after a party select the SNES's party-rebuild subroutine (CA/CBAF) restores each character's HP
    // (event command $8B id $7F) and, with BC's code, his MP ($8C id $7F). The PR's party select
    // (Current.OrganizePartyCommon -> PartySettingClient.Open) refills neither, so when it closes every
    // character's HP and MP go to max in a BC game with the code.
    static class BcMpParty
    {
        internal static int Refilled;

        internal static void Patch(Harmony h)
        {
            if (Hooks.Patch(h, typeof(Last.Management.PartySettingClient), "Close", typeof(BcMpParty), postfix: nameof(Close_Postfix)))
                Kit.Info("[bc] mpparty: hooked");
        }

        public static void Close_Postfix()
        {
            try
            {
                if (!Plugin.BcMode || BcSeeds.Active == null || !BcCodes.On("mpparty")) return;
                var list = Last.Management.UserDataManager.Instance()?.OwnedCharacterList;
                if (list == null) return;
                int n = 0;
                foreach (var c in list)
                {
                    var p = c?.Parameter;
                    if (p == null || p.CurrentHP <= 0) continue;
                    p.CurrentHP = p.ConfirmedMaxHp();
                    p.CurrentMP = p.ConfirmedMaxMp();
                    n++;
                }
                Refilled += n;
                Kit.Info($"[bc] mpparty: {n} characters' HP and MP refilled after the party select");
            }
            catch (Exception e) { Hooks.WarnOnce("bc-mpparty", e); }
        }
    }

    // `mementomori` (BC: C2/0E9A -> C4/B8CF, the stat loader adds a 7th, invisible relic per chosen character once
    // recruited; its stats, statuses, protections and relic flags all apply): the relic of each character, read
    // back from BC's stubs (bc_battle.json codes.mementomori.relics), added through the PR's parameter getters:
    // stats (Strength, Speed, Stamina, Magic, Defense, Magic Defense, Evade, MBlock, max HP/MP), worn statuses
    // (its wear_condition group), status protections (resistance_condition), element responses
    // (resistance_attribute) and equip abilities (wear functions 62: HP/MP +%, Offering, Genji, Gauntlet...).
    // Not carried: relic effects the PR keys on an equipped item's id (Sprint Shoes, Moogle Charm, ...), command
    // changers (BC never picks them for this), spells it teaches, the Status screen's line.
    static class BcMementoMori
    {
        static int stamp = -1;
        static readonly Dictionary<int, int> relics = new Dictionary<int, int>();     // character status id -> armor id
        internal static readonly Dictionary<int, int> TestRelics = new Dictionary<int, int>();
        internal static int Applied;

        internal static Last.Data.Master.Armor RelicOf(PlayerCharacterParameter p)
        {
            var who = p?.parent;
            if (who == null) return null;
            int id = who.characterStatusId;
            if (!TestRelics.TryGetValue(id, out int armor))
            {
                if (!Plugin.BcMode || BcSeeds.Active == null) return null;
                BcBattleData.Refresh();
                if (stamp != BcBattleData.Stamp)
                {
                    stamp = BcBattleData.Stamp;
                    relics.Clear();
                    var m = BcCodes.Code("mementomori");
                    if (m.ValueKind == JsonValueKind.Object && m.TryGetProperty("relics", out var r) && r.ValueKind == JsonValueKind.Object)
                        foreach (var x in r.EnumerateObject())
                            if (int.TryParse(x.Name, out int c)) relics[c] = x.Value.Int("armor", 0);
                    if (relics.Count > 0) Kit.Info($"[bc] mementomori: {string.Join(", ", relics.Select(kv => $"{kv.Key}: armor {kv.Value}"))}");
                }
                if (!relics.TryGetValue(id, out armor)) return null;
            }
            return Last.Data.Master.MasterManager.Instance?.GetData<Last.Data.Master.Armor>(armor);
        }

        internal static void Patch(Harmony h)
        {
            var p = typeof(PlayerCharacterParameter);
            int n = 0;
            foreach (var (getter, post) in new[]
            {
                ("ConfirmedPower", nameof(Power_Postfix)), ("ConfirmedAgility", nameof(Agility_Postfix)),
                ("ConfirmedVitality", nameof(Vitality_Postfix)), ("ConfirmedMagic", nameof(Magic_Postfix)),
                ("ConfirmedDefense", nameof(Defense_Postfix)), ("ConfirmedAbilityDefense", nameof(AbilityDefense_Postfix)),
                ("ConfirmedEvasionRate", nameof(Evasion_Postfix)), ("ConfirmedAbilityEvasionRate", nameof(AbilityEvasion_Postfix)),
                ("ConfirmedResistanceCondtionList", nameof(Protect_Postfix)), ("GetEquipmentConfirmedConditionList", nameof(Worn_Postfix)),
            })
                if (Hooks.Patch(h, p, getter, typeof(BcMementoMori), postfix: post)) n++;
            if (Hooks.Patch(h, typeof(Last.Data.User.OwnedCharacterData), "UpdateParameter", typeof(BcMementoMori), postfix: nameof(UpdateParameter_Postfix))) n++;
            Kit.Info($"[bc] mementomori: {n} of 11 hooks");
        }

        static void Add(PlayerCharacterParameter p, ref int result, Func<Last.Data.Master.Armor, int> of, int max = 255)
        {
            try
            {
                var a = RelicOf(p);
                if (a == null) return;
                int v = of(a);
                if (v == 0) return;
                result = BcBattleRules.AddStat(result, v, max);
                Applied++;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-mementomori", e); }
        }

        public static void Power_Postfix(PlayerCharacterParameter __instance, ref int __result) => Add(__instance, ref __result, a => a.Strength);
        public static void Agility_Postfix(PlayerCharacterParameter __instance, ref int __result) => Add(__instance, ref __result, a => a.Agility);
        public static void Vitality_Postfix(PlayerCharacterParameter __instance, ref int __result) => Add(__instance, ref __result, a => a.Vitality);
        public static void Magic_Postfix(PlayerCharacterParameter __instance, ref int __result) => Add(__instance, ref __result, a => a.Magic);
        public static void Defense_Postfix(PlayerCharacterParameter __instance, ref int __result) => Add(__instance, ref __result, a => a.Defense);
        public static void AbilityDefense_Postfix(PlayerCharacterParameter __instance, ref int __result) => Add(__instance, ref __result, a => a.AbilityDefense);
        public static void Evasion_Postfix(PlayerCharacterParameter __instance, ref int __result) => Add(__instance, ref __result, a => a.EvasionRate);
        public static void AbilityEvasion_Postfix(PlayerCharacterParameter __instance, ref int __result) => Add(__instance, ref __result, a => a.AbilityEvasionRate);

        // the relic's condition group members (condition ids)
        static IEnumerable<int> GroupMembers(int group)
        {
            if (group == 0) yield break;
            var list = Last.Data.Master.MasterManager.Instance?.GetList<Last.Data.Master.ConditionGroup>();
            if (list == null) yield break;
            foreach (var r in list.Values)
                if (r != null && r.GroupId == group) yield return r.ConditionId;
        }

        public static void Protect_Postfix(PlayerCharacterParameter __instance, ref Il2CppSystem.Collections.Generic.Dictionary<int, int> __result)
        {
            try
            {
                var a = RelicOf(__instance);
                if (a == null || a.ResistanceCondition == 0) return;
                var dst = new Il2CppSystem.Collections.Generic.Dictionary<int, int>();
                if (__result != null) foreach (var kv in __result) dst[kv.Key] = kv.Value;
                foreach (var c in GroupMembers(a.ResistanceCondition)) if (!dst.ContainsKey(c)) dst[c] = 1;
                __result = dst;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-mementomori-protect", e); }
        }

        public static void Worn_Postfix(PlayerCharacterParameter __instance, ref Il2CppSystem.Collections.Generic.List<Last.Data.Master.Condition> __result)
        {
            try
            {
                var a = RelicOf(__instance);
                if (a == null || a.WearConditionGroupId == 0) return;
                var mm = Last.Data.Master.MasterManager.Instance;
                var have = new HashSet<int>();
                var list = new Il2CppSystem.Collections.Generic.List<Last.Data.Master.Condition>();
                if (__result != null) foreach (var c in __result) { list.Add(c); if (c != null) have.Add(c.Id); }
                foreach (var id in GroupMembers(a.WearConditionGroupId))
                {
                    if (have.Contains(id)) continue;
                    var cond = mm.GetData<Last.Data.Master.Condition>(id);
                    if (cond != null) list.Add(cond);
                }
                __result = list;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-mementomori-worn", e); }
        }

        // equip abilities (wear function 62's ability ids) join the character's list after the game rebuilds it
        public static void UpdateParameter_Postfix(Last.Data.User.OwnedCharacterData __instance)
        {
            try
            {
                var a = RelicOf(__instance?.Parameter);
                if (a == null || a.WearFunctionGroupId == 0) return;
                var fg = Last.Data.Master.MasterManager.Instance?.GetData<Last.Data.Master.FunctionGroup>(a.WearFunctionGroupId);
                var list = __instance.EquipmentAbilitys;
                if (fg == null || list == null) return;
                foreach (var (fn, v) in new[] { (fg.Function1Id, fg.Function1Value1), (fg.Function2Id, fg.Function2Value1), (fg.Function3Id, fg.Function3Value1) })
                    if (fn == 62 && v != 0 && !list.Contains(v)) list.Add(v);
            }
            catch (Exception e) { Hooks.WarnOnce("bc-mementomori-abilities", e); }
        }
    }

    // `magicnumbers` (BC: SilentEnigma's "Decoupled Color-Coded MP Digits", C2/63A8: MP damage and MP healing in
    // colours of their own). The PR shows MP like HP (BattleBasicFunction.CreateDamageView: hit type 5 MPHit as
    // damage, 6 MPRecovery as healing, then BattleUtility.CreateDamageView(unit, value, isRecovery, isMiss)); the
    // hit type is caught there and the popup the game then makes is tinted for its first seconds: MP damage
    // violet, MP healing light blue (alpha left to the popup's own animation).
    static class BcMagicNumbers
    {
        static readonly UnityEngine.Color MpDamage = new UnityEngine.Color(0.78f, 0.6f, 1f), MpHeal = new UnityEngine.Color(0.5f, 0.85f, 1f);
        const float Seconds = 2.5f;
        static int stamp = -1, hitType = -1;
        static bool on;
        internal static bool TestOn;
        internal static int Tinted;
        static readonly List<(ViewDamageEntity View, UnityEngine.Color Color, float Until)> views = new List<(ViewDamageEntity, UnityEngine.Color, float)>();

        static bool On
        {
            get
            {
                if (TestOn) return true;
                if (!Plugin.BcMode || BcSeeds.Active == null) return false;
                BcBattleData.Refresh();
                if (stamp != BcBattleData.Stamp) { stamp = BcBattleData.Stamp; on = BcCodes.On("magicnumbers"); }
                return on;
            }
        }

        internal static void Patch(Harmony h)
        {
            int n = 0;
            if (Hooks.Patch(h, typeof(Last.Battle.Function.BattleBasicFunction), "CreateDamageView", typeof(BcMagicNumbers),
                            prefix: nameof(Basic_Prefix), postfix: nameof(Basic_Postfix))) n++;
            var m = AccessTools.Method(typeof(BattleUtility), "CreateDamageView", new[] { typeof(BattleUnitData), typeof(int), typeof(bool), typeof(bool) });
            if (m != null) { h.Patch(m, postfix: new HarmonyMethod(typeof(BcMagicNumbers), nameof(View_Postfix))); n++; }
            Kit.Info($"[bc] magicnumbers: {n} of 2 hooks");
        }

        public static void Basic_Prefix(Last.Systems.HitType hitType) => BcMagicNumbers.hitType = (int)hitType;
        public static void Basic_Postfix() => hitType = -1;

        public static void View_Postfix(ViewDamageEntity __result)
        {
            try
            {
                if (__result == null || (hitType != 5 && hitType != 6) || !On) return;
                views.Add((__result, hitType == 5 ? MpDamage : MpHeal, UnityEngine.Time.realtimeSinceStartup + Seconds));
                Tinted++;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-magicnumbers", e); }
        }

        // the popup's images take the colour each frame (its digits are made over its first frames)
        internal static void Update()
        {
            if (views.Count == 0) return;
            float now = UnityEngine.Time.realtimeSinceStartup;
            for (int i = views.Count - 1; i >= 0; i--)
            {
                var (v, col, until) = views[i];
                try
                {
                    if (v == null || v.WasCollected || now > until) { views.RemoveAt(i); continue; }
                    foreach (var g in v.GetComponentsInChildren<UnityEngine.UI.Graphic>(true))
                        if (g != null) g.color = new UnityEngine.Color(col.r, col.g, col.b, g.color.a);
                    foreach (var r in v.GetComponentsInChildren<UnityEngine.SpriteRenderer>(true))
                        if (r != null) r.color = new UnityEngine.Color(col.r, col.g, col.b, r.color.a);
                }
                catch (Exception e) { views.RemoveAt(i); Hooks.WarnOnce("bc-magicnumbers-tint", e); }
            }
        }
    }

    // `equipanything` (BC: C3/9B8B and C3/9B99 skip the hand slots' "weapon or shield" and "can this character equip
    // it" tests). The PR decides an item's slots by its parts group (EquipUtility.IsEquipSlot / GetCanEquipSlots on
    // parts_group's equip1..6_possible) and already wears armor in a hand (shields: parts group 2, slots 1-2). In a
    // BC game with the code the head, body and relic groups (3, 4, 5) also allow slots 1-2, set on the game's live
    // PartsGroup rows (and put back otherwise). Not carried: consumables in a hand (the PR's equip lists hold
    // weapons and armor only), the "anyone may hold it" part (each item's own equip group still decides), and the
    // SNES reading a held item as a weapon (the PR treats armor in a hand as it treats a shield).
    static class BcEquipAnything
    {
        static readonly int[] Groups = { 3, 4, 5 };
        static bool applied;
        internal static bool TestOn;
        internal static string LastNote = "";

        internal static void Update()
        {
            bool want = TestOn || (Plugin.BcMode && BcSeeds.Active != null && BcCodes.On("equipanything"));
            if (want == applied) return;
            try
            {
                var mm = Last.Data.Master.MasterManager.Instance;
                if (mm == null) return;
                int n = 0;
                foreach (var g in Groups)
                {
                    var row = mm.GetData<Last.Data.Master.PartsGroup>(g);
                    if (row == null) continue;
                    row.Equip1Possible = want ? 1 : 0;
                    row.Equip2Possible = want ? 1 : 0;
                    n++;
                }
                applied = want;
                LastNote = $"{n} parts groups {(want ? "allow" : "no longer allow")} the hand slots";
                Kit.Info($"[bc] equipanything: {LastNote}");
            }
            catch (Exception e) { Hooks.WarnOnce("bc-equipanything", e); }
        }
    }
}
