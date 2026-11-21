using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;
using HarmonyLib;
using Last.Battle;
using Last.Data;
using Last.Data.Master;
using PrKit;

namespace BeyondChaos.PR
{
    // Junction effects that needed the PR's terrain, raw HP or Sketch roll (found by bc-junction's readers,
    // 2026-11-20; spec pr/data/bc_junction_spec.json):
    //   Gaia Boost (attacker)   attacks of the battlefield's element x1.5 (BcJunctionFormulas step 8). The battlefield:
    //                           the battle's background (BattleOption.GetNowBackGroundAssetId) -> its dance in the PR's
    //                           learning table (type 3: value1 background, content 494-501 = dances 0-7) -> BC's
    //                           element for that dance (Wind, Holy, Fire, Lightning, Earth, Water, Poison, Ice)
    //   Gaia Assist (either)    25% for each holder on a counterable act between two fighters: a random step of the
    //                           battlefield's dance (its on-terrain step group, the steps' odds) that fits (an enemy-type
    //                           step between foes, an ally-type one between allies) is cast at the other, free
    //   Overheal (healer)       healing past max HP raises HP to max + a quarter of the excess (at most max/4 more); the
    //                           PR's HP setter clamps to max, so the raw field is written (the next HP change clamps it)
    //   Art License (sketcher)  its Sketch always works (unsketchable monsters still fail): WC's -scis hooks
    //                           (UniqueUpdateParameterProvider.IsResistanceSketch postfix arms, the next GetRandPlus(100)
    //                           of the frame answers 0), only for a holder's act
    static class BcJunctionExtra
    {
        internal static int GaiaProcs, Overheals, SketchesForced;
        static Harmony harmony;

        internal static void Register(Harmony h)
        {
            harmony = h;
            BcJunctionActs.Before.Add(("gaia_assist", GaiaAssist));
            BcJunctionActs.After.Add(("overheal", Overheal));
            var resist = AccessTools.Method(typeof(Serial.FF6.Calc.UniqueUpdateParameterProvider), "IsResistanceSketch");
            if (resist != null) h.Patch(resist, postfix: new HarmonyMethod(typeof(BcJunctionExtra), nameof(Resist_Postfix)));
            else Kit.Warn($"{BcJunction.Tag} no UniqueUpdateParameterProvider.IsResistanceSketch: Art License's sure Sketch is off");
        }

        static bool Has(BattleUnitData u, string key) => BcJunction.Used(key) && BcJunction.Has(u, key);

        // --- the battlefield's dance ---------------------------------------------------------------------------

        // dance index (0-7) -> BC's Gaia element (SNES element bit): Wind, Holy, Fire, Lightning, Earth, Water, Poison, Ice
        static readonly int[] DanceElementBit = { 4, 5, 0, 2, 6, 7, 3, 1 };
        static readonly Dictionary<int, int> danceOfBackground = new Dictionary<int, int>();

        internal static int Dance()
        {
            try
            {
                var opt = BattlePlugManager.Instance()?.BattleOption;
                if (opt == null) return -1;
                int bg = opt.GetNowBackGroundAssetId();
                if (danceOfBackground.Count == 0)
                {
                    var all = Master.All<Learning>();
                    if (all != null)
                        foreach (var kv in all)
                        {
                            var l = kv.Value;
                            if (l != null && l.TypeId == 3 && l.ContentId >= 494 && l.ContentId <= 501) danceOfBackground[l.Value1] = l.ContentId - 494;
                        }
                }
                return danceOfBackground.TryGetValue(bg, out int d) ? d : -1;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-dance", e); return -1; }
        }

        internal static int GaiaElementBit()
        {
            int d = Dance();
            return d >= 0 && d < 8 ? DanceElementBit[d] : -1;
        }

        // --- Gaia Assist ------------------------------------------------------------------------------------

        static int stamp = -1;
        static readonly HashSet<int> allySteps = new HashSet<int>();

        static bool AllyStep(int ability)
        {
            BcBattleData.Refresh();
            if (stamp != BcBattleData.Stamp)
            {
                stamp = BcBattleData.Stamp;
                allySteps.Clear();
                var j = BcBattleData.Section("junction");
                if (j.ValueKind == JsonValueKind.Object && j.TryGetProperty("dance_ally_steps", out var a) && a.ValueKind == JsonValueKind.Array)
                    foreach (var x in a.EnumerateArray()) allySteps.Add(x.GetInt32());
            }
            return allySteps.Contains(ability);
        }

        // a random step of the battlefield's dance (its on-terrain group: dance + 1), by the steps' odds; 0: none
        static int Step(int dance)
        {
            var rows = new List<(int Ability, int Rate)>();
            var all = Master.All<AbilityRandomGroup>();
            if (all != null)
                foreach (var kv in all)
                    if (kv.Value != null && kv.Value.GroupId == dance + 1 && kv.Value.InvocationRate > 0) rows.Add((kv.Value.AbilityId, kv.Value.InvocationRate));
            int total = rows.Sum(r => r.Rate);
            if (total <= 0) return 0;
            int roll = BcJunction.Rng.Next(total);
            foreach (var r in rows) { if (roll < r.Rate) return r.Ability; roll -= r.Rate; }
            return 0;
        }

        static void GaiaAssist(BcJunctionActs.Act act)
        {
            var a = act.Attacker;
            if (a == null || act.Ours || act.Targets.Count == 0 || !BcJunction.Used("gaia_assist")) return;
            int dance = Dance();
            if (dance < 0) return;
            foreach (var t in act.Targets.ToList())
            {
                if (t == null || t.Pointer == a.Pointer) continue;
                bool foes = !BcJunction.SameSide(a, t);
                foreach (var (from, to) in new[] { (a, t), (t, a) })
                {
                    if (BcJunction.Rng.Next(4) != 0 || !BcJunction.Alive(from) || !Has(from, "gaia_assist")) continue;
                    int step = Step(dance);
                    if (step <= 0 || AllyStep(step) == foes) continue;   // the step must fit: enemy-type between foes
                    if (BcJunctionTriggers.Cast(from, to, step, true, "Gaia Assist") != null) GaiaProcs++;
                }
            }
        }

        // --- Overheal ----------------------------------------------------------------------------------------

        // the field the HP setter writes before it clamps (CharacterParameterBase +0x14, decompiled set_CurrentHP)
        const int CurrentHpOffset = 0x14;

        static void Overheal(BcJunctionActs.Act act, List<BcJunctionActs.Landed> units)
        {
            var a = act.Attacker;
            if (a == null || !Has(a, "overheal")) return;
            foreach (var l in units.Where(l => l.Targeted && l.Healed > 0))
            {
                int heal = 0;
                try { heal = l.Result?.GetValue(false) ?? 0; } catch { }
                int now = BcJunctionMath.OverhealHp(l.HpBefore, Math.Max(heal, l.Healed), l.MaxHp);
                var p = l.Unit.BattleUnitDataInfo?.Parameter;
                if (p == null || now <= p.CurrentHP) continue;
                Marshal.WriteInt32(p.Pointer, CurrentHpOffset, now);
                Overheals++;
                Hooks.NoteOnce("bc-junction-overheal", () => $"{BcJunction.Tag} Overheal: {BcJunction.Who(l.Unit)} HP {l.HpBefore} -> {now} (max {l.MaxHp})");
            }
        }

        // --- Art License: a holder's Sketch always works ---------------------------------------------------------

        static int sketchFrame = -1;
        static bool randPatched;

        public static void Resist_Postfix(bool __result)
        {
            if (__result || !BcJunction.Used("art_license")) return;
            var a = BcJunctionActs.Current?.Attacker;
            if (a == null || !BcJunction.Has(a, "art_license")) return;
            if (!randPatched && harmony != null)
            {
                randPatched = true;
                var rand = AccessTools.Method(typeof(global::CommonUtility), "GetRandPlus", new[] { typeof(int) });
                if (rand != null) harmony.Patch(rand, prefix: new HarmonyMethod(typeof(BcJunctionExtra), nameof(Rand_Prefix)));
            }
            sketchFrame = UnityEngine.Time.frameCount;
        }

        public static bool Rand_Prefix(int max, ref int __result)
        {
            if (sketchFrame < 0 || max != 100) return true;
            bool now = sketchFrame == UnityEngine.Time.frameCount;
            sketchFrame = -1;
            if (!now) return true;
            SketchesForced++;
            __result = 0;
            return false;
        }
    }
}
