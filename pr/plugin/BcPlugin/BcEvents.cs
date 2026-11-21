using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using HarmonyLib;
using Last.Interpreter;
using Last.Interpreter.Instructions;
using Last.Data.Master;
using Last.Data.User;
using Last.Management;
using PrKit;

namespace BeyondChaos.PR
{
    // Beyond Chaos's light events (tools/bc_events.py: the seed's scripts, lines and tables, and bc_events.json
    // in the seed folder for this class). Our scripts call SysCall "BC:<name> [args]" where the plugin does a
    // seed's part; the game's SysCall instruction looks names up in its table, so a prefix takes ours and
    // leaves every other call alone. Hooks: shadowstays (the PR's after-battle draw for Shadow leaving).
    //   BC:log <text>       a line in the log (tests)
    //   BC:join S L         character S joins (the game's call), raised to level L
    //   BC:gil N / BC:pay N N gil more / take N if the party has it (map-local 0 = 1 paid, else 0)
    //   BC:reserve S / BC:leave S   character S to the reserve / out of the party (r: names the game's table lacks)
    // Harness: bcev (the seed's event flags and the field state), bcflag CAT IDX [VALUE] (a story flag).
    static class BcEvents
    {
        internal const string Json = "bc_events.json";
        static string loadedFor;
        static HashSet<string> flags = new HashSet<string>();
        static JsonDocument doc;
        internal static string Last = "";

        // the active seed's bc_events.json (read again when the seed changes)
        static JsonElement? Root
        {
            get
            {
                var s = BcSeeds.Active;
                var id = s == null ? null : s.Id + "|" + s.Dir;
                if (id != loadedFor)
                {
                    loadedFor = id;
                    flags = new HashSet<string>();
                    doc?.Dispose();
                    doc = null;
                    try
                    {
                        var path = s == null ? null : Path.Combine(s.Dir, Json);
                        if (path != null && File.Exists(path))
                        {
                            doc = JsonDocument.Parse(File.ReadAllText(path));
                            if (doc.RootElement.TryGetProperty("flags", out var f))
                                foreach (var x in f.EnumerateArray()) flags.Add(x.GetString());
                        }
                    }
                    catch (Exception e) { Plugin.L.LogWarning($"[bc] events: {Json} unreadable: {e.Message}"); }
                }
                return doc?.RootElement;
            }
        }

        // the seed has this event flag (and BC's data is installed)
        internal static bool On(string flag) => Plugin.BcMode && Root != null && flags.Contains(flag);

        internal static JsonElement? Part(string flag) =>
            On(flag) && Root.Value.TryGetProperty(flag, out var p) ? p : (JsonElement?)null;

        internal static int Flag(DataStorage.Category c, int index) => DataStorage.Instance?.Get(c, index) ?? -1;

        public static void Patch(Harmony h)
        {
            var m = AccessTools.Method(typeof(External.Misc), "SystemCall");
            if (m != null) h.Patch(m, prefix: new HarmonyMethod(typeof(BcEvents), nameof(SystemCall_Prefix)));
            else Plugin.L.LogWarning("[bc] no External.Misc.SystemCall: BC's event calls are off");
            var sel = AccessTools.Method(typeof(External.Message), "Select");
            if (sel != null) h.Patch(sel, prefix: new HarmonyMethod(typeof(BcEvents), nameof(Select_Prefix)));
            var organize = AccessTools.Method(typeof(Last.Interpreter.Instructions.SystemCall.Current), "OrganizePartyCommon");
            if (organize != null) h.Patch(organize, prefix: new HarmonyMethod(typeof(BcEvents), nameof(OrganizePartyCommon_Prefix)));
            else Plugin.L.LogWarning("[bc] no Current.OrganizePartyCommon: h (random final party) is off");
            var join = AccessTools.Method(typeof(Last.Interpreter.Instructions.SystemCall.Current), "JoinCharacter");
            if (join != null) h.Patch(join, postfix: new HarmonyMethod(typeof(BcEvents), nameof(JoinCharacter_Postfix)));
            var lot = AccessTools.Method(typeof(Last.Interpreter.Instructions.SystemCall.Current), "LotSecedeShadow");
            if (lot != null) h.Patch(lot, prefix: new HarmonyMethod(typeof(BcEvents), nameof(LotSecedeShadow_Prefix)));
            else Plugin.L.LogWarning("[bc] no Current.LotSecedeShadow: shadowstays is off");
        }

        // tests (harness bcskipnaming): a script's naming screens pass with the default name (headless runs can't type)
        static bool SkipNaming;

        public static bool SystemCall_Prefix(MainCore mc, ref int __result)
        {
            string name;
            try
            {
                var sv = mc?.op?.sValues;
                name = sv != null && sv.Length > 0 ? sv[0] : null;
            }
            catch { return true; }
            if (SkipNaming && name != null && name.StartsWith("名前入力："))
            {
                __result = 0;
                if (mc.IsFirstClock()) Note($"naming skipped (tests): {name}");
                return false;
            }
            if (name == null || !name.StartsWith("BC:")) return true;
            __result = 0;
            try
            {
                var parts = name.Substring(3).Split(' ');
                Note($"call {name}");
                switch (parts[0])
                {
                    case "log":
                        break;
                    case "join":      // BC:join STATUS LEVEL: the character joins (the game's own call), then raised to LEVEL
                        if (mc.IsFirstClock() && parts.Length > 2 && int.TryParse(parts[1], out var who) && int.TryParse(parts[2], out var lv))
                            Join(who, lv);
                        break;
                    case "pay":       // BC:pay N: take N gil if the party has it; map-local 0 = 1 paid, 0 not (as RemoveGil)
                        if (mc.IsFirstClock() && parts.Length > 1 && int.TryParse(parts[1], out var price))
                        {
                            var udm = UserDataManager.Instance();
                            bool paid = udm != null && udm.OwendGil >= price;
                            if (paid) new OwnedItemClient().RemoveGil(price);
                            DataStorage.Instance?.Set(DataStorage.Category.kMapLocalVariable, 0, paid ? 1 : 0);
                            Note($"pay {price}: {(paid ? "paid" : "not enough gil")} (now {udm?.OwendGil})");
                        }
                        break;
                    case "reserve":   // BC:reserve S: character S to the reserve (the game's own, for a name its table lacks)
                        if (mc.IsFirstClock() && parts.Length > 1 && int.TryParse(parts[1], out var rs))
                            global::Last.Interpreter.Instructions.SystemCall.Current.MoveReserveCommon(rs);
                        break;
                    case "leave":     // BC:leave S: character S leaves the party
                        if (mc.IsFirstClock() && parts.Length > 1 && int.TryParse(parts[1], out var ls))
                            global::Last.Interpreter.Instructions.SystemCall.Current.SecedeCharacter(ls, false);
                        break;
                    case "gil":       // BC:gil N: N gil more
                        if (mc.IsFirstClock() && parts.Length > 1 && int.TryParse(parts[1], out var gil))
                            new OwnedItemClient().AddGil(gil);
                        break;
                    default:
                        Plugin.L.LogWarning($"[bc] events: unknown call {name}");
                        break;
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-syscall", e); }
            return false;
        }

        // a character joins as the game's join calls do (JoinTina = JoinCharacter(1, -1, 1, true, false, false)), then is
        // raised to `level` as the PR's own CorrectLevel raises a joiner (BNW's JoinLevels.Raise: the level's total exp, the
        // stat-up provider, the owned-character client); BC sets levels with the SNES's char_props averaging
        internal static void Join(int status, int level)
        {
            var udm = UserDataManager.Instance();
            bool there = false;
            foreach (var c in udm.GetPartyMemberData()) if (c.characterStatusId == status) there = true;
            if (!there) global::Last.Interpreter.Instructions.SystemCall.Current.JoinCharacter(status, -1, (global::Last.Defaine.User.CorpsId)1, true, false, false);
            OwnedCharacterData owned = null;
            foreach (var c in udm.GetOwnedCharactersClone(true)) if (c != null && c.characterStatusId == status) owned = c;
            int before = owned?.Parameter?.AddtionalLevel ?? 0;
            if (owned?.Parameter != null && level > before)
            {
                var row = MasterManager.Instance?.GetData<ExpTable>(level);
                if (row != null)
                {
                    owned.AdditionalExp = row.TotalExp;
                    var current = StatusUpProviderInstanceManager.Instance()?.GetCurrentProvider();
                    var provider = current?.TryCast<global::Last.Systems.StatusUpProvider>();
                    var result = provider != null ? provider.Execution(owned, DateTime.Now.Millisecond, null) : current?.Execution(owned, DateTime.Now.Millisecond, null);
                    if (result != null) new OwnedCharacterClient().SetOwnedCharacter(result);
                }
            }
            Note($"join {status}: level {before} -> {level} (BC's)");
        }

        // h (BC: C3/AA25, the final battle's order menu closes on its first frame with the 12 slots shuffled): the PR's
        // final battle (SysCall パーティ編成：ラストバトル = Current.OrganizeLastBattleParty) opens its party menu with
        // OrganizePartyCommon(3 parties, ..., isLastBattle): party 1 starts the fight, parties 2 and 3 step in, in the
        // order corps2[0], [1], corps3[0], [1], corps2[2], [3], corps3[2], [3] (decompiled tools/decomp/bc_lastbattle).
        // In such a seed the menu doesn't open: the selectable characters go to the three parties at random.
        static readonly System.Random Rng = new System.Random();
        internal static string LastFinalParty = "";

        public static bool OrganizePartyCommon_Prefix(int partyNum, bool isFirstClock, bool isLastBattle, ref int __result)
        {
            try
            {
                if (!isLastBattle || !On("h")) return true;
                if (isFirstClock) RandomFinalParty();
                __result = 0;
                return false;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-final-party", e); return true; }
        }

        internal static string RandomFinalParty()
        {
            var udm = UserDataManager.Instance();
            var ids = new List<int>();
            foreach (var c in udm.OwnedCharacterList)
                if (c != null && c.IsEnableCorps && c.characterStatusId >= 1 && c.characterStatusId <= 14) ids.Add(c.Id);
            for (int i = ids.Count - 1; i > 0; i--) { int j = Rng.Next(i + 1); (ids[i], ids[j]) = (ids[j], ids[i]); }
            var corps = CorpsClient.Instance();
            for (int slot = 0; slot < 3; slot++)
                for (int i = 0; i < 4; i++)
                {
                    int k = slot * 4 + i;
                    corps.SetSlot((UserDataManager.CorpsSlot)slot, i, k < ids.Count ? ids[k] : 0);
                }
            corps.SwitchSlot(UserDataManager.CorpsSlot.Slot1);
            LastFinalParty = string.Join(" | ", Enumerable.Range(0, 3).Select(slot =>
                string.Join(" ", ids.Skip(slot * 4).Take(4).Select(id => udm.OwnedCharacterList.ToArray().FirstOrDefault(c => c?.Id == id)?.characterStatusId ?? 0))));
            Note($"final battle's parties at random (h): {LastFinalParty}");
            return LastFinalParty;
        }

        // worringtriad's start Lores (BC: ED/F564, bc_events.json "worringtriad"."lores"): known by whoever holds Lore
        // (BC shuffles commands); taught again on every join (PrKit.Ff6.StartSkills, idempotent: a save keeps them)
        internal static int StartLores()
        {
            var part = Part("worringtriad");
            if (part == null || !part.Value.TryGetProperty("lores", out var l) || l.ValueKind != JsonValueKind.Array) return 0;
            return PrKit.Ff6.StartSkills.Teach(PrKit.Ff6.StartSkills.Lore, l.EnumerateArray().Select(x => x.GetInt32()));
        }

        public static void JoinCharacter_Postfix()
        {
            try { if (On("worringtriad")) StartLores(); }
            catch (Exception e) { Hooks.WarnOnce("bc-lores", e); }
        }

        // tests (harness bcanswer): a script's menus answered from a queue, at once (nothing queued: the game's own menu)
        static readonly Queue<int> Answers = new Queue<int>();
        internal static readonly List<string> Selects = new List<string>();

        public static bool Select_Prefix(MainCore mc, ref int __result)
        {
            if (Answers.Count == 0) return true;
            int a = Answers.Dequeue();
            DataStorage.Instance?.SetMessageSelection(a);
            try { Selects.Add(string.Join("/", (mc?.op?.sValues ?? new string[0]).Where(v => !string.IsNullOrEmpty(v))) + $" -> {a}"); } catch (Exception) { }
            Note($"menu answered {a} (script {MapScripts.Current})");
            __result = 0;
            return false;
        }

        // shadowstays (BC: C2/4885): Shadow's random leaving after a battle (SysCall シャドウ離脱抽選 in the battle
        // scripts: Current.LotSecedeShadow, decompiled in tools/decomp/shadow_leave) takes its "stays" path, as
        // Worlds Collide's game does (WcEvents.LotSecedeShadow_Prefix)
        internal static int ShadowKept;
        static readonly int TowerOfZealots = (int)global::Last.Defaine.ConditionType.TowerOfZealots;

        public static bool LotSecedeShadow_Prefix(ref int __result)
        {
            try
            {
                if (!On("shadowstays")) return true;
                DataStorage.Instance?.Set(DataStorage.Category.kScriptLocalVariable, 3, 0);
                __result = 0;
                ShadowKept++;
                return false;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-shadow", e); return true; }
        }

        static void Note(string what)
        {
            Last = what;
            Plugin.L.LogInfo("[bc] events: " + what);
        }

        // --- harness --------------------------------------------------------------------------------------
        internal static void Register()
        {
            Harness.Register("bcev", _ => State(), "bcev: the seed's event flags (bc_events.json), map, cell, party, gil, the last BC: call");
            Harness.Register("bcflag", a =>
            {
                if (a.Length < 2 || !int.TryParse(a[1], out var i)) return "error: bcflag CATEGORY INDEX [VALUE] (ScenarioFlag1..4, TreasureFlag1..4, MapLocalVariable...)";
                if (!Enum.TryParse<DataStorage.Category>("k" + a[0], out var cat)) return $"error: no category {a[0]}";
                if (a.Length > 2 && int.TryParse(a[2], out var v)) DataStorage.Instance?.Set(cat, i, v);
                return $"{a[0]} {i} = {Flag(cat, i)}";
            }, "bcflag CATEGORY INDEX [VALUE]: read (or set) a story flag");
            Harness.Register("bcanswer", a =>
            {
                Answers.Clear();
                foreach (var x in a) if (int.TryParse(x, out var n)) Answers.Enqueue(n);
                Selects.Clear();
                return $"{Answers.Count} menu answers queued";
            }, "bcanswer N...: the next script menus are answered N... at once (tests)");
            Harness.Register("bcselects", _ => $"menus: {string.Join(" | ", Selects)}; left {Answers.Count}", "bcselects: the menus bcanswer answered");
            Harness.Register("bcfinalparty", _ => On("h") ? "final parties: " + RandomFinalParty() : "error: no h in this seed",
                "bcfinalparty: h's random final-battle parties now (status ids, party 1 | 2 | 3)");
            Harness.Register("bcevgen", EvGen, "bcevgen SEED FLAG...: make a Beyond Chaos seed with exactly these flags (normal mode), apply it");
            Harness.Register("bcmsg", a => a.Length < 1 ? "error: bcmsg KEY" : $"msg {a[0]} = {GameText.Get(a[0]) ?? "(none)"}",
                "bcmsg KEY: a message's text as the game has it now (the seed's lines set live)");
            Harness.Register("bcskipnaming", a =>
            {
                SkipNaming = a.Length > 0 && a[0] == "on";
                return $"naming screens {(SkipNaming ? "skipped" : "shown")}";
            }, "bcskipnaming on|off: scripts' naming screens pass with the default name (tests)");
            Harness.Register("bcgil", a =>
            {
                if (a.Length < 1 || !int.TryParse(a[0], out var n) || n < 1) return "error: bcgil N";
                new OwnedItemClient().AddGil(n);
                return State();
            }, "bcgil N: N gil more (tests: Mobliz's letters at once cost 2500)");
            Harness.Register("bcjoin", a =>
            {
                if (a.Length < 1 || !int.TryParse(a[0], out var id) || id < 1 || id > 14) return "error: bcjoin STATUS (1 Terra .. 14 Umaro)";
                global::Last.Interpreter.Instructions.SystemCall.Current.JoinCharacter(id, -1, (global::Last.Defaine.User.CorpsId)1, true, false, false);
                return State();
            }, "bcjoin STATUS: a character joins the party (the game's own join call; 4 = Shadow)");
        }

        // a seed with exactly these flags (the harness's bcgen takes a preset): made in game, applied
        static string genId;

        static string EvGen(string[] a, int tick)
        {
            if (tick == 0)
            {
                if (!LiveData.Ready) return "error: the game's data isn't loaded yet";
                if (a.Length < 2) return "error: bcevgen SEED FLAG...";
                genId = PrKit.Seeds.SeedLibrary.NewId(a[0]) + "-test";
                var err = BcSeeds.Gen.Start(a[0], string.Join(" ", a.Skip(1)), BcSeeds.Lib.DirFor(genId), ("mode", "normal"));
                return err != null ? "error: " + err : null;
            }
            if (!BcSeeds.Gen.TakeResult(out bool ok, out string error, out string dir)) return null;
            if (!ok) return $"error: {error}";
            var s = BcSeeds.Lib.Load(Path.GetFileName(dir));
            if (s == null) return "error: the seed was made but can't be read";
            var aerr = BcSeeds.Lib.Apply(s);
            if (aerr != null) return "error: apply: " + aerr;
            return $"seed {s.SeedText} made in {s.Seconds:0.0} s; {BcSeeds.Lib.LastApply}; {State()}";
        }

        internal static string State()
        {
            var r = Root;
            var udm = UserDataManager.Instance();
            string party = "?";
            try { party = string.Join(" ", udm.GetPartyMemberData().ToArray().Select(c => $"{c.characterStatusId}:Lv{c.Parameter.ConfirmedLevel()}")); }
            catch (Exception) { }
            string owned = "?";      // every playable character the player has (the reserve too)
            try { owned = string.Join(" ", PrKit.Ff6.StartSkills.Owned().Select(c => c.characterStatusId).Distinct().OrderBy(x => x)); }
            catch (Exception) { }
            string cell = "?";
            try
            {
                var fc = UnityEngine.Object.FindObjectOfType<global::FieldMap>()?.fieldController;
                if (fc?.player != null)
                {
                    var c = fc.ConvertWorldPositionToCellPosition(fc.player.transform.position);
                    cell = $"{UnityEngine.Mathf.Round(c.x)},{UnityEngine.Mathf.Round(c.y)}";
                }
            }
            catch (Exception) { }
            string battle = "";
            try
            {
                var b = global::Last.Battle.BattlePlugManager.Instance();
                if (b != null && b.IsBattle())
                {
                    int tower = 0, n = 0;
                    var players = b.GetPlayerUnits().Where(u => u != null).Select(u =>
                    {
                        var list = u.BattleUnitDataInfo?.Parameter?.CurrentConditionList;
                        var cs = new List<int>();
                        if (list != null) foreach (var c in list) if (c != null) cs.Add(c.ConditionType);
                        n++;
                        if (cs.Contains(TowerOfZealots)) tower++;
                        return $"{u.GetOwnedCharacterData()?.characterStatusId}[{string.Join(",", cs)}]";
                    }).ToList();
                    battle = $"; battle players {string.Join(" ", players)}; tower status on {tower} of {n} players; " +
                             $"monsters [{string.Join(" ", b.GetEnemyUnits().Where(e => e?.GetMonster() != null).Select(e => $"{e.GetMonster().Id}:{e.BattleUnitDataInfo?.Parameter?.CurrentHP}"))}]";
                }
            }
            catch (Exception e) { battle = $"; battle ? ({e.GetType().Name})"; }
            string lores = "";
            try
            {
                var part = Part("worringtriad");
                if (part != null && part.Value.TryGetProperty("lores", out var l) && l.ValueKind == JsonValueKind.Array)
                {
                    var ids = l.EnumerateArray().Select(x => x.GetInt32()).ToList();
                    var holders = PrKit.Ff6.StartSkills.Holders(PrKit.Ff6.StartSkills.Lore);
                    lores = holders.Count == 0
                        ? $"; lores {ids.Count}: nobody holds Lore, pending {PrKit.Ff6.StartSkills.Pending(PrKit.Ff6.StartSkills.Lore)}"
                        : $"; lores {ids.Count}: known by [{string.Join(" ", holders.Select(h => $"{h.characterStatusId}:{ids.Count(x => PrKit.Ff6.StartSkills.Knows(h, x))}"))}]";
                }
            }
            catch (Exception e) { lores = $"; lores ? ({e.GetType().Name})"; }
            return $"events [{(r == null ? "no seed events" : string.Join(" ", flags))}]; map {udm?.CurrentMapId} cell {cell}; " +
                   $"party {party}; owned [{owned}]; gil {udm?.OwendGil}; script {MapScripts.Current} busy {MapScripts.Busy}; shadow kept {ShadowKept}; last {Last}{lores}{battle}";
        }
    }
}
