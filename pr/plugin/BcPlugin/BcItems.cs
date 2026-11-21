using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using HarmonyLib;
using Last.Battle;
using Last.Data;
using Last.Data.User;
using PrKit;
using Il2CppIntMap = Il2CppSystem.Collections.Generic.Dictionary<int, int>;

namespace BeyondChaos.PR
{
    // Beyond Chaos's item specials the PR's tables can't hold (the rest is data: tools/bc_items.py rewrites the
    // seed's equipment in BC's item layout: item-use spells and breaks, procs, MBlock and Evade on weapons,
    // command changers, throwing, the statuses equipment wears). From bc_battle.json "items":
    //   vigor    equipment with BC's "Vigor +50%" (SNES byte 11 bit 7, C2/0F30: Vigor += Vigor/2 after the
    //            equipment sums; the PR builds it into the Hyper Wrist only): Strength x1.5 (to 255)
    //   immune   a weapon's status immunities (bytes 6-7; the PR's weapons have no such column)
    //   rerise   monsters BC starts with Rerise (status byte 4 bit 2, its HP cap: darkworld makes it common)
    //   auto     auto Stop (byte 8 bit 4, which no vanilla item has: the SNES sets it once at battle start, $3C6D;
    //            as a wear condition the PR would keep it on): given at battle start (auto Slow is the porter's)
    static class BcItems
    {
        static int stamp = -1;
        static readonly HashSet<int> vigor = new HashSet<int>(), rerise = new HashSet<int>();
        const int Reraise = 31;     // the PR's (Life 3's function 9 condition)
        static readonly Dictionary<int, int[]> immune = new Dictionary<int, int[]>(), auto = new Dictionary<int, int[]>();
        internal static int VigorBoosts, Immunities, AutoGiven;

        static void Load()
        {
            BcBattleData.Refresh();
            if (stamp == BcBattleData.Stamp) return;
            stamp = BcBattleData.Stamp;
            vigor.Clear(); immune.Clear(); auto.Clear(); rerise.Clear();
            var it = BcBattleData.Section("items");
            if (it.ValueKind != JsonValueKind.Object) return;
            if (it.TryGetProperty("vigor", out var v) && v.ValueKind == JsonValueKind.Array)
                foreach (var x in v.EnumerateArray()) vigor.Add(x.GetInt32());
            if (it.TryGetProperty("rerise", out var rr) && rr.ValueKind == JsonValueKind.Array)
                foreach (var x in rr.EnumerateArray()) rerise.Add(x.GetInt32());
            // monsters using equipment (collateraldamage): its item-use spell, into the AI's item map
            var ai = BcSeeds.Active?.SnesAi;
            int added = 0;
            if (ai != null && it.TryGetProperty("monster_item_use", out var mu) && mu.ValueKind == JsonValueKind.Object)
                foreach (var p in mu.EnumerateObject())
                    if (int.TryParse(p.Name, out int item) && !ai.ItemUse.ContainsKey(item)) { ai.ItemUse[item] = p.Value.GetInt32(); added++; }
            if (added > 0) Kit.Info($"[bc] items: {added} pieces of equipment monsters can use (their item-use spell)");
            foreach (var (name, into) in new[] { ("immune", immune), ("auto", auto) })
                if (it.TryGetProperty(name, out var m) && m.ValueKind == JsonValueKind.Object)
                    foreach (var p in m.EnumerateObject())
                        if (int.TryParse(p.Name, out int cid)) into[cid] = p.Value.EnumerateArray().Select(x => x.GetInt32()).ToArray();
            Kit.Info($"[bc] items: {vigor.Count} with Vigor +50%, {immune.Count} weapons with immunities, {auto.Count} with auto Stop");
        }

        static bool Any => Plugin.BcMode && BcSeeds.Active != null;

        internal static IEnumerable<int> Worn(OwnedCharacterData c)
        {
            var eq = c?.EquipmentData;
            if (eq == null) yield break;
            foreach (var it in eq.Values)
                if (it != null) yield return it.ContentId;
        }

        public static void Patch(Harmony h)
        {
            var p = typeof(PlayerCharacterParameter);
            int n = 0;
            if (Hooks.Patch(h, p, "ConfirmedPower", typeof(BcItems), postfix: nameof(Power_Postfix))) n++;
            if (Hooks.Patch(h, p, "ConfirmedResistanceCondtionList", typeof(BcItems), postfix: nameof(Protect_Postfix))) n++;
            Kit.Info($"[bc] items: {n} of 2 parameter hooks");
        }

        public static void Power_Postfix(PlayerCharacterParameter __instance, ref int __result)
        {
            if (!Any) return;
            try
            {
                Load();
                if (vigor.Count == 0 || !Worn(__instance?.parent).Any(vigor.Contains)) return;
                __result = BcBattleRules.VigorBoost(__result);
                VigorBoosts++;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-items-vigor", e); }
        }

        public static void Protect_Postfix(PlayerCharacterParameter __instance, ref Il2CppIntMap __result)
        {
            if (!Any) return;
            try
            {
                Load();
                if (immune.Count == 0) return;
                var add = Worn(__instance?.parent).Where(immune.ContainsKey).SelectMany(c => immune[c]).Distinct().ToList();
                if (add.Count == 0) return;
                var dst = new Il2CppIntMap();
                if (__result != null)
                    foreach (var kv in __result) dst[kv.Key] = kv.Value;
                foreach (var c in add)
                    if (!dst.ContainsKey(c)) { dst[c] = 1; Immunities++; }
                __result = dst;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-items-immune", e); }
        }

        // self-tests (BcItemTests): an item made one of BC's for a moment
        static int testCid;
        internal static void TestVigor(int cid, bool on) { Load(); if (on) vigor.Add(cid); else vigor.Remove(cid); }
        internal static void TestImmune(int cid, int cond)
        {
            Load();
            if (cond != 0) immune[cid] = new[] { cond }; else immune.Remove(cid);
        }
        internal static void TestAuto(int? cid, int cond)
        {
            Load();
            if (cid == null) { if (testCid != 0) auto.Remove(testCid); testCid = 0; return; }
            testCid = cid.Value;
            auto[testCid] = new[] { cond };
            given = false;       // the next frame gives it, as at a battle's start
        }

        // auto Slow / Stop once per battle, as soon as the party is there
        static bool given;

        internal static void Update()
        {
            try
            {
                var bm = BattlePlugManager.Instance();
                if (bm == null || !bm.IsBattle()) { given = false; return; }
                if (given || !Any) return;
                Load();
                var players = bm.GetPlayerUnits();
                if (players == null || players.Length == 0) return;
                given = true;
                // monsters BC starts with Rerise (its HP cap: tools/bc_items.py rerise)
                if (rerise.Count > 0)
                    foreach (var e in bm.GetEnemyUnits() ?? new BattleEnemyData[0])
                    {
                        var id = e?.GetMonster()?.Id ?? 0;
                        if (!rerise.Contains(id) || e.BattleUnitDataInfo?.Parameter?.CurrentHP <= 0) continue;
                        bm.BattleConditionController?.InterruptAddCondition(e, Reraise);
                        AutoGiven++;
                        Kit.Info($"[bc] items: monster {id} starts the battle with Rerise (BC's HP cap)");
                    }
                if (auto.Count == 0) return;
                foreach (var p in players)
                {
                    var oc = p?.ownedCharacterData;
                    if (oc == null || p.BattleUnitDataInfo?.Parameter?.CurrentHP <= 0) continue;
                    foreach (var c in Worn(oc).Where(auto.ContainsKey).SelectMany(c => auto[c]).Distinct())
                    {
                        bm.BattleConditionController?.InterruptAddCondition(p, c);
                        AutoGiven++;
                        Kit.Info($"[bc] items: {oc.Name} starts the battle with condition {c} (BC's equipment)");
                    }
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-items-auto", e); }
        }
    }

    // BcItems' battle self-tests (BcSelfTests): each plugin rule on party member 0's own first piece of
    // equipment, made one of BC's for the test (the seed's lists are put back after)
    [SelfTestProvider]
    static class BcItemTests
    {
        internal static void Register()
        {
            BcSelfTests.Add("items: Vigor +50%", Vigor);
            BcSelfTests.Add("items: a weapon's status immunity", Immunity);
            float t0 = 0;
            BcSelfTests.Add("items: auto Slow at battle start", () =>
            {
                var who = BcSelfTests.Player(0);
                var list = who?.BattleUnitDataInfo?.Parameter?.CurrentConditionList;
                bool slow = false;
                if (list != null) foreach (var c in list) if (c != null && c.Id == SlowId) slow = true;
                if (!slow && UnityEngine.Time.realtimeSinceStartup - t0 < 5) return null;
                BcItems.TestAuto(null, 0);
                return slow ? $"ok: {who.ownedCharacterData?.Name} has Slow ({SlowId})" : "FAILED: no Slow";
            }, () =>
            {
                t0 = UnityEngine.Time.realtimeSinceStartup;
                var who = BcSelfTests.Player(0);
                var cid = BcItems.Worn(who?.ownedCharacterData).FirstOrDefault(c => c != 0);
                if (cid == 0) throw new InvalidOperationException("party member 0 wears nothing");
                BcItems.TestAuto(cid, SlowId);
            });
        }

        const int SlowId = 25, ClearId = 33;

        static string Vigor()
        {
            var who = BcSelfTests.Player(0)?.ownedCharacterData;
            var p = who?.Parameter;
            var cid = BcItems.Worn(who).FirstOrDefault(c => c != 0);
            if (p == null || cid == 0) return "FAILED: party member 0 wears nothing";
            int before = p.ConfirmedPower();
            BcItems.TestVigor(cid, true);
            int after;
            try { after = p.ConfirmedPower(); }
            finally { BcItems.TestVigor(cid, false); }
            int want = Math.Min(255, before + before / 2);
            return after == want ? $"ok: {who.Name}'s Strength {before} -> {after}" : $"FAILED: {before} -> {after}, wanted {want}";
        }

        static string Immunity()
        {
            var who = BcSelfTests.Player(0)?.ownedCharacterData;
            var p = who?.Parameter;
            var cid = BcItems.Worn(who).FirstOrDefault(c => c != 0);
            if (p == null || cid == 0) return "FAILED: party member 0 wears nothing";
            bool before = p.ConfirmedResistanceCondtionList()?.ContainsKey(ClearId) == true;
            BcItems.TestImmune(cid, ClearId);
            bool after;
            try { after = p.ConfirmedResistanceCondtionList()?.ContainsKey(ClearId) == true; }
            finally { BcItems.TestImmune(cid, 0); }
            return after ? $"ok: {who.Name} resists Vanish ({ClearId}) with item {cid} (before: {before})" : "FAILED: no Vanish resistance";
        }
    }
}
