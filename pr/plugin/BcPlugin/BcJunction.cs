using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Last.Battle;
using Last.Defaine;
using PrKit;

namespace BeyondChaos.PR
{
    // Beyond Chaos's junction effects (BC's bcg_junction.py + its 57 SNES patches; flags espffect,
    // effectmas, effectory, effectster, treaffect, jejentojori): who has which effect, read from the seed's
    // bc_battle.json "junction" (tools/bc_junction.py: BC's own lists, read back from its output). The
    // effects themselves are BcJunction<Hook>.cs, grouped by the battle hook they share.
    //
    // Who has an effect (BC's patch_junction_core.txt jun-checker):
    //   a party member: the always list, its character's list, its equipped esper's, each equipped item's,
    //                   each status it has, the monster it Rages as; minus the blacklists of the same (not Rage's)
    //   a monster:      always, the every-monster list, the items it holds (the ones it can still be stolen, then
    //                   its drops; treaffect), its own list, each status it has; minus every-monster/items/own/
    //                   status blacklists
    //   then Junction Jammer: a random living fighter is picked; if it has Junction Jammer, the check fails.
    static class BcJunction
    {
        internal const string Tag = "[bc junction]";
        internal static readonly System.Random Rng = new System.Random();
        internal static bool Testing;                    // self-tests: Grant/Deny override the seed
        internal static readonly Dictionary<IntPtr, HashSet<string>> Granted = new Dictionary<IntPtr, HashSet<string>>();

        // --- startup (Plugin.cs: Defer("junction", () => BcJunction.Patch(harmony))) -----------------------

        internal static void Patch(HarmonyLib.Harmony h)
        {
            BcJunctionActs.Patch(h);
            BcJunctionDamage.Patch(h);
            BcJunctionTargets.Register(h);
            BcJunctionStart.Register(h);
            BcJunctionFormulas.Register();
            BcJunctionRewards.Register(h);
            BcJunctionStats.Register(h);
            BcJunctionTriggers.Register(h);
            BcJunctionMore.Register(h);
            BcJunctionTicks.Register(h);
            BcJunctionClock.Register();
            BcJunctionProcs.Register(h);
            BcJunctionItems.Register(h);
            BcJunctionExtra.Register(h);
            BcJunctionControl.Register(h);
            BcJunctionEffects.Register(h);
            Harness.Register("bcjunction", Report, "bcjunction: the junction effects each fighter has now (in a battle), or the seed's record");
            Harness.Register("bcjgen", Gen, "bcjgen [SEED]: make and apply a New Player seed with the six junction flags (espffect effectmas effectory effectster treaffect jejentojori)");
            Harness.Register("bcjgrant", GrantCommand, "bcjgrant <slot|e<slot>> <key|-key> ... | bcjgrant clear: give a fighter junction effects for a test (the seed's own are kept)");
            BcJunctionTests.Register();
            Kit.Info($"{Tag} hooks in: acts, damage; {BcJunctionActs.Before.Count + BcJunctionActs.After.Count} act effects, " +
                     $"{BcJunctionDamage.Rules.Count + BcJunctionDamage.ResponseRules.Count} damage effects");
        }

        static string Report(string[] a)
        {
            if (!Plugin.BcMode || BcSeeds.Active == null) return "error: no Beyond Chaos seed active";
            bool loaded = Load();
            var bm = BattlePlugManager.Instance();
            if (bm == null || !bm.IsBattle())
                return $"bcjunction: seed {BcSeeds.Active.Id}: {(loaded ? $"{InUse.Count} effects in use: {string.Join(" ", InUse.OrderBy(k => k))}" : "no junction effects")}";
            var parts = new List<string>();
            int i = 0;
            foreach (var u in Party()) parts.Add($"p{i++} {Who(u)}: [{string.Join(" ", Effects(u).OrderBy(k => k))}]");
            i = 0;
            foreach (var u in Enemies()) parts.Add($"e{i++} {Who(u)}: [{string.Join(" ", Effects(u).OrderBy(k => k))}]");
            return $"bcjunction: {string.Join("; ", parts)}; jams {Jams}";
        }

        internal const string TestFlags = "espffect effectmas effectory effectster treaffect mementomori:6 jejentojori";
        static string genId;

        static string Gen(string[] a, int tick)
        {
            if (tick == 0)
            {
                if (!LiveData.Ready) return "error: the game's data isn't loaded yet";
                var seed = a.Length > 0 ? a[0] : "9859608359";
                if (!Plugin.FlagDefs.Presets.TryGetValue("New Player", out var flags)) return "error: no New Player preset";
                genId = PrKit.Seeds.SeedLibrary.NewId(seed) + "-jun";
                var err = BcSeeds.Gen.Start(seed, flags + " " + TestFlags, BcSeeds.Lib.DirFor(genId), ("mode", "normal"));
                return err != null ? "error: " + err : null;
            }
            if (!BcSeeds.Gen.TakeResult(out bool ok, out string error, out string dir)) return null;
            if (!ok) return $"error: {error}";
            var s = BcSeeds.Lib.Load(System.IO.Path.GetFileName(dir));
            if (s == null) return "error: the seed was made but can't be read";
            var aerr = BcSeeds.Lib.Apply(s);
            if (aerr != null) return "error: apply: " + aerr;
            stamp = -1;
            bool loaded = Load();
            return $"bcjgen: seed {s.SeedText} ({s.Id}) made in {BcSeeds.Gen.Seconds:0.0} s; {BcSeeds.Lib.LastApply}; " +
                   (loaded ? $"junction: {InUse.Count} effects in use" : "junction: none (bc_battle.json has no junction section)");
        }

        // per frame (Plugin.cs BcRunner.Update): effects that wait on the game (Double Time's gauge), MP for the mages
        internal static void Update()
        {
            try
            {
                if (!Plugin.BcMode || BcSeeds.Active == null || !any) return;
                var bm = BattlePlugManager.Instance();
                if (bm == null || !bm.IsBattle()) return;
                BcJunctionMore.Update();
                if (UnityEngine.Time.frameCount % 15 == 0) BcJunctionMore.SyncMages();
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-update", e); }
        }

        // a fighter by "0".."3" (party slot) or "e0".."e5" (monster slot)
        internal static BattleUnitData Unit(string s)
        {
            bool enemy = s.StartsWith("e");
            if (!int.TryParse(enemy ? s.Substring(1) : s, out int n)) return null;
            var arr = enemy ? Enemies().ToList() : Party().ToList();
            return n >= 0 && n < arr.Count ? arr[n] : null;
        }

        static string GrantCommand(string[] a)
        {
            if (a.Length >= 1 && a[0] == "clear") { Granted.Clear(); Invalidate(); Testing = false; return "bcjgrant: cleared"; }
            if (a.Length < 2) return "usage: bcjgrant <slot|e<slot>> <key|-key> ...";
            var u = Unit(a[0]);
            if (u == null) return $"error: no fighter {a[0]}";
            Grant(u, a.Skip(1).ToArray());
            return $"bcjgrant: {Who(u)}: [{string.Join(" ", Effects(u).OrderBy(k => k))}]";
        }

        // self-tests and the harness: give (or, "-key", take) effects; the seed's own stay
        internal static void Grant(BattleUnitData u, params string[] keys)
        {
            Testing = true;
            if (!Granted.TryGetValue(u.Pointer, out var set)) Granted[u.Pointer] = set = new HashSet<string>();
            foreach (var k in keys)
            {
                set.Remove(k.StartsWith("-") ? k.Substring(1) : "-" + k);
                set.Add(k);
            }
            Invalidate();
        }

        internal static void Ungrant(BattleUnitData u)
        {
            if (u != null) Granted.Remove(u.Pointer);
            if (Granted.Count == 0) Testing = false;
            Invalidate();
        }

        // --- the seed's record --------------------------------------------------------------------------

        sealed class Lists
        {
            public readonly HashSet<string> Has = new HashSet<string>(), Not = new HashSet<string>();
        }

        static int stamp = -1;
        static bool any;
        static readonly HashSet<string> always = new HashSet<string>();
        static readonly Dictionary<int, Lists> characters = new Dictionary<int, Lists>(), espers = new Dictionary<int, Lists>(),
            equipment = new Dictionary<int, Lists>(), statuses = new Dictionary<int, Lists>(), monsters = new Dictionary<int, Lists>();
        static readonly Lists everyMonster = new Lists();
        static bool monsterSteal, monsterDrop;
        internal static readonly HashSet<string> InUse = new HashSet<string>();

        // reads the record when the active seed changed; true when this seed has junction effects
        internal static bool Load()
        {
            BcBattleData.Refresh();
            if (stamp == BcBattleData.Stamp) return any;
            stamp = BcBattleData.Stamp;
            always.Clear(); characters.Clear(); espers.Clear(); equipment.Clear(); statuses.Clear(); monsters.Clear();
            everyMonster.Has.Clear(); everyMonster.Not.Clear(); InUse.Clear();
            monsterSteal = monsterDrop = false;
            var j = BcBattleData.Section("junction");
            any = j.ValueKind == JsonValueKind.Object;
            if (!any) return false;
            try
            {
                if (j.TryGetProperty("always", out var a) && a.ValueKind == JsonValueKind.Array)
                    foreach (var k in a.EnumerateArray()) always.Add(k.GetString());
                ReadSide(j, "characters", characters);
                ReadSide(j, "espers", espers);
                ReadSide(j, "equipment", equipment);
                ReadSide(j, "statuses", statuses);
                ReadSide(j, "monsters", monsters);
                if (j.TryGetProperty("every_monster", out var em)) ReadLists(em, everyMonster);
                if (j.TryGetProperty("monster_items", out var mi))
                {
                    monsterSteal = mi.Bool("steal");
                    monsterDrop = mi.Bool("drop");
                }
                InUse.UnionWith(always);
                InUse.UnionWith(everyMonster.Has);
                foreach (var d in new[] { characters, espers, equipment, statuses, monsters })
                    foreach (var l in d.Values) InUse.UnionWith(l.Has);
                Kit.Info($"{Tag} seed {BcSeeds.Active?.Id}: {InUse.Count} effects in use; espers {espers.Count}, equipment {equipment.Count}, " +
                         $"monsters {monsters.Count}, statuses {statuses.Count}, characters {characters.Count}, always {always.Count}; " +
                         $"monsters' items: steal {monsterSteal}, drop {monsterDrop}");
            }
            catch (Exception e) { Kit.Warn($"{Tag} can't read the seed's junctions: {e.Message}"); any = false; }
            return any;
        }

        static void ReadSide(JsonElement j, string name, Dictionary<int, Lists> into)
        {
            if (!j.TryGetProperty(name, out var side) || side.ValueKind != JsonValueKind.Object) return;
            foreach (var p in side.EnumerateObject())
                if (int.TryParse(p.Name, out int id))
                {
                    var l = new Lists();
                    ReadLists(p.Value, l);
                    into[id] = l;
                }
        }

        static void ReadLists(JsonElement e, Lists l)
        {
            if (e.ValueKind != JsonValueKind.Object) return;
            if (e.TryGetProperty("has", out var h) && h.ValueKind == JsonValueKind.Array)
                foreach (var k in h.EnumerateArray()) l.Has.Add(k.GetString());
            if (e.TryGetProperty("not", out var n) && n.ValueKind == JsonValueKind.Array)
                foreach (var k in n.EnumerateArray()) l.Not.Add(k.GetString());
        }

        // a BC game with junction effects (hooks return at once otherwise)
        internal static bool On => Plugin.BcMode && BcSeeds.Active != null && (Load() || Testing);

        // the seed gives someone this effect (hooks for effects nobody has can skip their work)
        internal static bool Used(string key) => InUse.Contains(key) || (Testing && Granted.Values.Any(s => s.Contains(key)));

        // --- statuses: BC's 32 (SNES order, bcg_junction_manifest status_names) as the PR's conditions -----

        internal static readonly string[] StatusNames =
        {
            "Blind", "Zombie", "Poison", "Magitek", "Clear", "Imp", "Petrify", "Wound", "Condemned", "Near Fatal", "Image",
            "Mute", "Berserk", "Muddled", "Seizure", "Sleep", "Dance", "Regen", "Slow", "Haste", "Stop", "Shell", "Safe",
            "Reflect", "Rage", "Freeze", "Life 3", "Morph", "Control", "Hide", "Intercept", "Float",
        };

        static readonly Dictionary<ConditionType, int> statusIndex = new Dictionary<ConditionType, int>
        {
            [ConditionType.Blind] = 0, [ConditionType.Zombie] = 1, [ConditionType.Poison] = 2, [ConditionType.Madou] = 3,
            [ConditionType.Vanish] = 4, [ConditionType.Transparent] = 4, [ConditionType.Kappa] = 5,
            [ConditionType.Mineralization] = 6, [ConditionType.UnableFight] = 7, [ConditionType.Doom] = 8,
            [ConditionType.DoomEx] = 8, [ConditionType.Dying] = 9, [ConditionType.Blink] = 10, [ConditionType.Silence] = 11,
            [ConditionType.Mute] = 11, [ConditionType.Bersak] = 12, [ConditionType.Confusion] = 13, [ConditionType.Slip] = 14,
            [ConditionType.Sleep] = 15, [ConditionType.Dance] = 16, [ConditionType.Regeneration] = 17, [ConditionType.Slow] = 18,
            [ConditionType.Heist] = 19, [ConditionType.Stop] = 20, [ConditionType.Shell] = 21, [ConditionType.Protect] = 22,
            [ConditionType.Proteus] = 22, [ConditionType.Reflex] = 23, [ConditionType.Rampage] = 24, [ConditionType.Freeze] = 25,
            [ConditionType.Reraise] = 26, [ConditionType.Trance] = 27, [ConditionType.Manipulate] = 28, [ConditionType.Hide] = 29,
            [ConditionType.WildFang] = 30, [ConditionType.Leviteto] = 31,
        };

        internal static int StatusIndex(ConditionType t) => statusIndex.TryGetValue(t, out int i) ? i : -1;

        // a BC status index as the PR's condition (the first of the table's for it; Non: none)
        internal static ConditionType ConditionOf(int index)
        {
            foreach (var kv in statusIndex) if (kv.Value == index) return kv.Key;
            return ConditionType.Non;
        }

        // the BC status indexes a unit has now
        internal static List<int> Statuses(BattleUnitData u)
        {
            var list = new List<int>();
            try
            {
                var conds = u?.BattleUnitDataInfo?.GetConfirmedConditionType();
                if (conds == null) return list;
                foreach (var c in conds)
                {
                    int i = StatusIndex(c);
                    if (i >= 0 && !list.Contains(i)) list.Add(i);
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-statuses", e); }
            return list;
        }

        internal static bool HasStatus(BattleUnitData u, ConditionType t)
        {
            try
            {
                var conds = u?.BattleUnitDataInfo?.GetConfirmedConditionType();
                return conds != null && conds.Contains(t);
            }
            catch { return false; }
        }

        // --- who has what -------------------------------------------------------------------------------

        // a unit's effects before Junction Jammer, cached for the frame (equipment and statuses change between acts)
        static int cacheFrame = -1;
        static readonly Dictionary<IntPtr, HashSet<string>> cache = new Dictionary<IntPtr, HashSet<string>>();

        internal static HashSet<string> Effects(BattleUnitData u)
        {
            if (u == null) return Empty;
            int frame = UnityEngine.Time.frameCount;
            if (frame != cacheFrame) { cache.Clear(); cacheFrame = frame; }
            if (cache.TryGetValue(u.Pointer, out var set)) return set;
            set = Compute(u);
            cache[u.Pointer] = set;
            return set;
        }

        static readonly HashSet<string> Empty = new HashSet<string>();
        internal static void Invalidate() => cache.Clear();

        static HashSet<string> Compute(BattleUnitData u)
        {
            var has = new HashSet<string>(always);
            var not = new HashSet<string>();
            try
            {
                var player = u.TryCast<BattlePlayerData>();
                if (player != null)
                {
                    var oc = player.ownedCharacterData;
                    if (oc != null)
                    {
                        Add(characters, oc.characterStatusId, has, not);
                        if (oc.MagicStoneId > 0) Add(espers, oc.MagicStoneId, has, not);
                        var eq = oc.EquipmentData;
                        if (eq != null)
                            foreach (var item in eq.Values)
                                if (item != null && item.ContentId > 0) Add(equipment, item.ContentId, has, not);
                    }
                    foreach (int s in Statuses(u)) Add(statuses, s, has, not);
                    // Rage: the monster Gau is raging as (its whitelist only, as BC's jun-check-rage)
                    int rage = RageMonster(u);
                    if (rage > 0 && monsters.TryGetValue(rage, out var rl)) has.UnionWith(rl.Has);
                }
                else
                {
                    var enemy = u.TryCast<BattleEnemyData>();
                    var m = enemy?.MonsterMaster ?? u.GetMonster();
                    has.UnionWith(everyMonster.Has);
                    not.UnionWith(everyMonster.Not);
                    if (m != null)
                    {
                        foreach (int item in HeldItems(enemy, m)) Add(equipment, item, has, not);
                        Add(monsters, m.Id, has, not);
                    }
                    foreach (int s in Statuses(u)) Add(statuses, s, has, not);
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-compute", e); }
            has.ExceptWith(not);
            if (Testing && Granted.TryGetValue(u.Pointer, out var g))
            {
                foreach (var k in g)
                    if (k.StartsWith("-")) has.Remove(k.Substring(1)); else has.Add(k);
            }
            return has;
        }

        static void Add(Dictionary<int, Lists> d, int id, HashSet<string> has, HashSet<string> not)
        {
            if (!d.TryGetValue(id, out var l)) return;
            has.UnionWith(l.Has);
            not.UnionWith(l.Not);
        }

        // the monster a unit Rages as (0: none)
        internal static int RageMonster(BattleUnitData u)
        {
            try
            {
                var fs = u?.BattleUnitDataInfo?.BattleConditionFunction;
                if (fs == null) return 0;
                foreach (var f in fs)
                {
                    var r = f?.TryCast<RampageConditionFunction>();
                    if (r != null) return r.GetMonsterId();
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-rage", e); }
            return 0;
        }

        // the items a monster holds for BC's treaffect: the ones it can still be stolen (none after a steal: the
        // SNES empties both slots), then its drops
        internal static List<int> HeldItems(BattleEnemyData enemy, Last.Data.Master.Monster m)
        {
            var items = new List<int>();
            if (m == null || !(monsterSteal || monsterDrop)) return items;
            if (monsterSteal && !Stolen(enemy))
                foreach (int c in new[] { m.StealContentId1, m.StealContentId2, m.StealContentId3, m.StealContentId4 })
                    if (c > 0) items.Add(c);
            if (monsterDrop)
                foreach (int c in new[] { m.DropContentId1, m.DropContentId2, m.DropContentId3, m.DropContentId4, m.DropContentId5, m.DropContentId6, m.DropContentId7, m.DropContentId8 })
                    if (c > 0) items.Add(c);
            return items;
        }

        static bool Stolen(BattleEnemyData enemy)
        {
            try
            {
                var plug = BattlePlugManager.Instance()?.BattleStealItemPlug;
                return enemy != null && plug != null && plug.StealCountMaxByMonster(enemy.UniqueId, 1);
            }
            catch { return false; }
        }

        // BC's jun-checker: the unit has the effect, and no Junction Jammer roll stops it
        internal static bool Has(BattleUnitData u, string key)
        {
            if (u == null || !Effects(u).Contains(key)) return false;
            return !Jammed();
        }

        // the effect without the Jammer roll (displays, self-tests)
        internal static bool HasRaw(BattleUnitData u, string key) => u != null && Effects(u).Contains(key);

        internal static int Jams;   // checks Junction Jammer stopped (self-tests, the log)

        // a random living fighter; Junction Jammer on it fails the check (BC: every passing check rolls)
        static bool Jammed()
        {
            if (!Used("junction_jammer")) return false;
            var living = Living();
            if (living.Count == 0) return false;
            var pick = living[Rng.Next(living.Count)];
            if (!Effects(pick).Contains("junction_jammer")) return false;
            Jams++;
            return true;
        }

        // --- the battle's fighters --------------------------------------------------------------------------

        internal static IEnumerable<BattleUnitData> Party()
        {
            var p = BattlePlugManager.Instance()?.GetPlayerUnits();
            if (p == null) yield break;
            foreach (var u in p) if (u != null) yield return u;
        }

        internal static IEnumerable<BattleUnitData> Enemies()
        {
            var e = BattlePlugManager.Instance()?.GetEnemyUnits();
            if (e == null) yield break;
            foreach (var u in e) if (u != null) yield return u;
        }

        internal static bool Alive(BattleUnitData u)
        {
            var p = u?.BattleUnitDataInfo?.Parameter;
            if (p == null || p.CurrentHP <= 0) return false;
            if (u.IsRemove) return false;
            return !HasStatus(u, ConditionType.UnableFight) && !HasStatus(u, ConditionType.Mineralization);
        }

        internal static List<BattleUnitData> Living() => Party().Concat(Enemies()).Where(Alive).ToList();

        internal static bool IsPlayer(BattleUnitData u) => u != null && u.TryCast<BattlePlayerData>() != null;

        internal static bool SameSide(BattleUnitData a, BattleUnitData b) => a != null && b != null && IsPlayer(a) == IsPlayer(b);

        internal static string Who(BattleUnitData u)
        {
            try
            {
                if (u == null) return "nobody";
                var oc = u.GetOwnedCharacterData();
                if (oc != null) return oc.Name;
                var m = u.GetMonster();
                return m != null ? $"monster {m.Id}" : "?";
            }
            catch { return "?"; }
        }

        // how many living fighters have an effect (BC's jun-check-count-all-living, each counted with its own roll)
        internal static int CountLiving(string key) => Living().Count(u => Has(u, key));
    }
}
