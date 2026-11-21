using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Battle;
using Last.Battle.Function;
using Last.Data;
using Last.Data.Master;
using Last.Defaine;
using Last.Systems;
using PrKit;
using Calc = BeyondChaos.PR.BcJunctionDamage.Calc;

namespace BeyondChaos.PR
{
    // More junction effects, each on its own PR hook (specs pr/build/bc_junction/spec_A/B/C.json):
    //   Repel <element> (target)   a spell of that element bounces off the holder as off Reflect (no Reflect
    //                              needed; not physical attacks): TargetFunction.CheckToReflectAct
    //   Repel Nuke (target)        the same for non-elemental spells with power (BC tests the caster when the
    //                              spell doesn't ignore defense: a register mix-up; here the target, as meant)
    //   Prism Wall (either)        a non-elemental spell that ignores defense rolls a random element for the
    //                              target's Repel checks (BC: only Repel uses it)
    //   Null Reflect (attacker)    its acts never bounce (Reflect, Repel)
    //   Reflect Boost              a bounced spell: x1.25 for each holder past the first among caster + reflectors
    //   Faith (either)             a spell between holders ignores magic evasion (BC: sure to hit)
    //   Barehanded (character)     both hands empty: each hand's attack = 5 x level + its own, at most 255
    //   Nihopalaoa (attacker)      its items hurt instead of healing
    //   Esper Defense (character)  immune to its esper's element and, for a foe-aimed (or lifting) summon, to the
    //                              statuses it sets; starts with the statuses its esper's ally-aimed summon sets
    //   Blood Mage / Gold Mage     MP is HP / 8 (gil / 32, at most 999); a spell's MP comes out of HP x8 (gil x32)
    //   Double Time                after its turn the gauge restarts half full (and its numbers are halved:
    //                              BcJunctionFormulas)
    //   Instant Act                no wait between choosing a command and acting (the PR's chant time 0)
    //   Potent Venom (attacker)    an act that inflicts Poison: a target that didn't take it (immune, or the roll
    //                              missed) is poisoned anyway half the time
    //   Maintenance (target)       a monster can't steal the party's gil from the holder (the gil comes back)
    //   Sneeze Guard (target)      a removing attack (Sneeze, Baba Breath: the SNES's spells setting Hide) from the
    //                              other side skips the holder (BC: the attack loses it as a target)
    //   Innate Runic               always in Runic's stance (the PR's MagicSealSword condition: given at the start,
    //                              put back after each act), so it soaks up spells as Runic does
    static class BcJunctionMore
    {
        internal static int Repelled, NullReflected, Faiths, HalfGauges, Waits;

        internal static void Register(Harmony h)
        {
            Hooks.Patch(h, typeof(TargetFunction), "CheckToReflectAct", typeof(BcJunctionMore), postfix: nameof(Reflect_Postfix));
            Hooks.Patch(h, typeof(PlayerCharacterParameter), "ConfirmedAbilityEvasionRate", typeof(BcJunctionMore), postfix: nameof(MBlock_Postfix));
            Hooks.Patch(h, typeof(EnemyCharacterParameter), "ConfirmedAbilityEvasionRate", typeof(BcJunctionMore), postfix: nameof(MBlock_Postfix));
            Hooks.Patch(h, typeof(PlayerCharacterParameter), "GetArmConfirmedAttack", typeof(BcJunctionMore), postfix: nameof(Arm_Postfix));
            Hooks.Patch(h, typeof(BattleProgressATBFF6), "GetChantingTime", typeof(BcJunctionMore), postfix: nameof(Chant_Postfix));
            Hooks.Patch(h, typeof(PlayerCharacterParameter), "ConfirmedResistanceCondtionList", typeof(BcJunctionMore), postfix: nameof(Protect_Postfix));
            BcJunctionDamage.Rules.Add(("more", OnHit));
            BcJunctionDamage.ResponseRules.Add(("esper_defense", EsperDefense));
            BcJunctionActs.Before.Add(("mp-mages", MagesBefore));
            BcJunctionActs.After.Add(("mp-mages", MagesAfter));
            BcJunctionActs.After.Add(("double-time", (act, units) =>
            {
                if (act.Attacker != null && !act.Counter && !act.Ours && Has(act.Attacker, "double_time")) halfGauge.Add(act.Attacker.Pointer);
            }));
            BcJunctionStats.MaxMp = MaxMp;
            BcJunctionActs.Before.Add(("maintenance", act => gilBefore = Gil()));
            BcJunctionActs.After.Add(("venom-maintenance", VenomAndMaintenance));
            BcJunctionActs.Before.Add(("sneeze_guard", SneezeGuard));
            BcJunctionActs.After.Add(("esper_attack_rider", EsperRider));
            BcJunctionActs.After.Add(("innate_runic", (act, units) => { foreach (var u in BcJunction.Party().Concat(BcJunction.Enemies()).ToList()) InnateRunic(u); }));
        }

        static bool Has(BattleUnitData u, string key) => BcJunction.Used(key) && BcJunction.Has(u, key);

        // --- an ability's elements (attribute id, else its attribute group) -------------------------------------

        static readonly Dictionary<int, int[]> groups = new Dictionary<int, int[]>();

        internal static int[] Elements(Ability a)
        {
            if (a == null) return Array.Empty<int>();
            if (a.AttributeId > 0) return new[] { a.AttributeId };
            if (a.AttributeGroupId <= 0) return Array.Empty<int>();
            lock (groups)
            {
                if (groups.TryGetValue(a.AttributeGroupId, out var g)) return g;
                var list = new List<int>();
                var all = Master.All<AttributeGroup>();
                if (all != null)
                    foreach (var kv in all)
                        if (kv.Value != null && kv.Value.GroupId == a.AttributeGroupId && kv.Value.AttributeId > 0) list.Add(kv.Value.AttributeId);
                return groups[a.AttributeGroupId] = list.ToArray();
            }
        }

        static bool PhysicalAbility(Ability a) => a != null && (a.TypeId == 4 || a.TypeId == 15 || a.TypeId == 16);

        // --- Reflect: Null Reflect, Repel, Prism Wall ---------------------------------------------------------

        public static void Reflect_Postfix(BattleActData battleActData, BattleUnitData target, ref bool __result)
        {
            if (!BcJunction.On || battleActData == null || target == null) return;
            try
            {
                var a = battleActData.AttackUnitData;
                if (a != null && __result && Has(a, "null_reflect")) { __result = false; NullReflected++; return; }
                if (__result || a != null && Has(a, "null_reflect")) return;
                var ab = battleActData.abilityList != null && battleActData.abilityList.Count > 0 ? battleActData.abilityList[0] : null;
                if (ab == null || PhysicalAbility(ab) || a == null || a.Pointer == target.Pointer) return;
                var el = Elements(ab);
                if (el.Length == 0 && TestIgnoresDefense(ab) && (Has(a, "prism_wall") || Has(target, "prism_wall")))
                    el = new[] { BcJunctionDamage.ElementAttr[BcJunction.Rng.Next(8)] };
                for (int b = 0; b < 8; b++)
                    if (el.Contains(BcJunctionDamage.ElementAttr[b]) && Has(target, "repel_" + BcJunctionDamage.ElementKey[b]))
                    {
                        __result = true;
                        Repelled++;
                        Hooks.NoteOnce("bc-junction-repel", () => $"{BcJunction.Tag} first Repel: {BcJunction.Who(target)} bounces ability {ab.Id}");
                        return;
                    }
                if (el.Length == 0 && ab.StandardValue > 0 && Has(target, "repel_nuke")) { __result = true; Repelled++; }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-reflect", e); }
        }

        static bool TestIgnoresDefense(Ability a)
        {
            try { return TEditionLike.IgnoresDefense(a); }
            catch { return false; }
        }

        // --- the hit: Reflect Boost, Nihopalaoa ---------------------------------------------------------------

        static void OnHit(Calc c)
        {
            var a = c.Attacker;
            if (a == null) return;
            var act = BcJunctionActs.Current?.Data;
            var reflectors = act?.ReflectUnitDatas;
            if (reflectors != null && reflectors.Length > 0 && BcJunction.Used("reflect_boost"))
            {
                var set = new HashSet<IntPtr> { a.Pointer };
                foreach (var r in reflectors) if (r != null) set.Add(r.Pointer);
                int n = BcJunction.Party().Concat(BcJunction.Enemies()).Count(u => set.Contains(u.Pointer) && BcJunction.Has(u, "reflect_boost"));
                if (n > 1) c.Scale("reflect_boost", BcJunctionMath.ReflectBoost(n));
            }
            if (c.Command == BcJunctionFormulas.ItemsCommand && (c.Hit == HitType.Recovery) && Has(a, "nihopalaoa"))
            {
                c.HitAfter = HitType.Hit;
                c.Fired.Add("nihopalaoa");
            }
        }

        // --- Faith: no magic evasion between holders ----------------------------------------------------------

        public static void MBlock_Postfix(CharacterParameterBase __instance, ref int __result)
        {
            var c = BcJunctionDamage.Current;
            if (c == null || c.Physical || __result == 0 || __instance == null || c.C?.target == null || __instance.Pointer != c.C.target.Pointer) return;
            if (!BcJunction.Used("faith")) return;
            if (BcJunction.Has(c.Attacker, "faith") || BcJunction.Has(c.Target, "faith")) { __result = 0; Faiths++; }
        }

        // --- Barehanded ---------------------------------------------------------------------------------------

        public static void Arm_Postfix(PlayerCharacterParameter __instance, ref int __result)
        {
            if (!BcJunction.Used("barehanded") || __instance == null) return;
            try
            {
                var bm = BattlePlugManager.Instance();
                if (bm == null || !bm.IsBattle()) return;
                foreach (var u in BcJunction.Party())
                {
                    var oc = u.GetOwnedCharacterData();
                    var p = u.BattleUnitDataInfo?.Parameter;
                    if (oc == null || (p?.Pointer != __instance.Pointer && oc.Parameter?.Pointer != __instance.Pointer)) continue;
                    if (!EmptyHands(oc) || !BcJunction.Has(u, "barehanded")) return;
                    int lv = BcJunctionStats.Level(u);
                    __result = Math.Min(255, 5 * lv + __result);
                    return;
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-barehanded", e); }
        }

        static bool EmptyHands(Last.Data.User.OwnedCharacterData oc)
        {
            var eq = oc.EquipmentData;
            if (eq == null) return true;
            foreach (var kv in eq)
                if ((kv.Key == EquipSlotType.Slot1 || kv.Key == EquipSlotType.Slot2) && kv.Value != null && kv.Value.ContentId > 0 && !IsEmptySlotItem(kv.Value.ContentId))
                    return false;
            return true;
        }

        // the PR's "nothing equipped" rows (tools/port.py PR_EMPTY_SLOT: 93 for the hands)
        static bool IsEmptySlotItem(int contentId) => contentId == EmptyHandContent;
        internal static int EmptyHandContent = 93;

        // --- Esper Defense ------------------------------------------------------------------------------------

        static void EsperDefense(Calc c, Dictionary<int, int> responses)
        {
            var t = c.Target;
            if (t == null || c.Heal || !BcJunction.IsPlayer(t) || !Has(t, "esper_defense")) return;
            var oc = t.GetOwnedCharacterData();
            var e = oc != null && oc.MagicStoneId > 0 ? BcJunctionField.EsperInfo(oc.MagicStoneId) : null;
            if (e == null) return;
            foreach (int attr in e.Elements)
                if (c.Elements.Contains(attr)) { responses[attr] = BcJunctionDamage.Null; c.Fired.Add($"esper_defense {attr}"); }
        }

        // Esper Defense: a foe-aimed (or status-lifting) summon's statuses can't touch the holder (BC clears them from
        // its vulnerability masks): those conditions read as resisted (1) while in battle
        internal static int Protections;

        public static void Protect_Postfix(PlayerCharacterParameter __instance, ref Il2CppSystem.Collections.Generic.Dictionary<int, int> __result)
        {
            if (__instance == null || !BcJunction.Used("esper_defense") || !BcJunction.On) return;
            try
            {
                var bm = BattlePlugManager.Instance();
                if (bm == null || !bm.IsBattle()) return;
                foreach (var u in BcJunction.Party())
                {
                    var oc = u.GetOwnedCharacterData();
                    if (oc == null || (u.BattleUnitDataInfo?.Parameter?.Pointer != __instance.Pointer && oc.Parameter?.Pointer != __instance.Pointer)) continue;
                    if (oc.MagicStoneId <= 0 || !BcJunction.HasRaw(u, "esper_defense")) return;
                    var e = BcJunctionField.EsperInfo(oc.MagicStoneId);
                    if (e == null || !(e.Foe || e.Lift) || e.Protect.Length == 0) return;
                    var m = new Il2CppSystem.Collections.Generic.Dictionary<int, int>();
                    if (__result != null) foreach (var kv in __result) m[kv.Key] = kv.Value;
                    foreach (int c in e.Protect) if (!m.ContainsKey(c)) m[c] = 1;
                    __result = m;
                    Protections++;
                    return;
                }
            }
            catch (Exception ex) { Hooks.WarnOnce("bc-junction-esper-protect", ex); }
        }

        // the start statuses (BcJunctionStart calls it for each party member)
        internal static void EsperDefenseStart(BattleUnitData u)
        {
            if (!BcJunction.IsPlayer(u) || !Has(u, "esper_defense")) return;
            var oc = u.GetOwnedCharacterData();
            var e = oc != null && oc.MagicStoneId > 0 ? BcJunctionField.EsperInfo(oc.MagicStoneId) : null;
            if (e == null || e.Foe || e.Lift) return;
            var cc = BattlePlugManager.Instance()?.BattleConditionController;
            foreach (int s in e.Statuses)
            {
                if (s == 29) continue;                      // never Hide (BC forces it off)
                var t = BcJunction.ConditionOf(s);
                if (t != ConditionType.Non && !BcJunction.HasStatus(u, t)) cc?.InterruptAddCondition(u, t);
            }
        }

        // --- Blood Mage / Gold Mage ---------------------------------------------------------------------------

        static int MaxMp(BattleUnitData u) => Has(u, "blood_mage") || Has(u, "gold_mage") ? 999 : -1;

        static int MageMp(BattleUnitData u)
        {
            if (Has(u, "blood_mage")) return BcJunctionMath.BloodMageMp(u.BattleUnitDataInfo?.Parameter?.CurrentHP ?? 0);
            if (Has(u, "gold_mage")) return BcJunctionMath.GoldMageMp(Last.Management.UserDataManager.Instance()?.OwendGil ?? 0);
            return -1;
        }

        static readonly Dictionary<IntPtr, int> mageMp = new Dictionary<IntPtr, int>();

        internal static void SyncMages()
        {
            if (!BcJunction.Used("blood_mage") && !BcJunction.Used("gold_mage")) return;
            foreach (var u in BcJunction.Party().Concat(BcJunction.Enemies()))
            {
                int mp = MageMp(u);
                var p = u.BattleUnitDataInfo?.Parameter;
                if (mp < 0 || p == null) continue;
                if (p.CurrentMP != mp) p.CurrentMP = mp;
            }
        }

        static void MagesBefore(BcJunctionActs.Act act)
        {
            var a = act.Attacker;
            if (a == null) return;
            SyncMages();
            var p = a.BattleUnitDataInfo?.Parameter;
            if (p != null && MageMp(a) >= 0) mageMp[a.Pointer] = p.CurrentMP;
        }

        static void MagesAfter(BcJunctionActs.Act act, List<BcJunctionActs.Landed> units)
        {
            var a = act.Attacker;
            if (a == null || !mageMp.TryGetValue(a.Pointer, out int before)) return;
            mageMp.Remove(a.Pointer);
            var p = a.BattleUnitDataInfo?.Parameter;
            if (p == null) return;
            int spent = before - p.CurrentMP;
            if (spent <= 0) return;
            if (Has(a, "blood_mage")) p.CurrentHP = Math.Max(0, p.CurrentHP - BcJunctionMath.BloodMageCost(spent));
            else if (Has(a, "gold_mage")) new Last.Management.OwnedItemClient().RemoveGil(Math.Min(BcJunctionMath.GoldMageCost(spent), Last.Management.UserDataManager.Instance()?.OwendGil ?? 0));
            SyncMages();
        }

        // --- what an ability inflicts (its condition group's conditions) ---------------------------------------

        static readonly Dictionary<int, HashSet<ConditionType>> inflicts = new Dictionary<int, HashSet<ConditionType>>();

        internal static HashSet<ConditionType> Inflicts(Ability a)
        {
            var none = new HashSet<ConditionType>();
            if (a == null || a.ConditionGroupId <= 0) return none;
            lock (inflicts)
            {
                if (inflicts.TryGetValue(a.ConditionGroupId, out var set)) return set;
                set = new HashSet<ConditionType>();
                var groups = Master.All<ConditionGroup>();
                var conds = Master.All<Condition>();
                if (groups != null && conds != null)
                    foreach (var kv in groups)
                        if (kv.Value != null && kv.Value.GroupId == a.ConditionGroupId && conds.ContainsKey(kv.Value.ConditionId))
                            set.Add((ConditionType)conds[kv.Value.ConditionId].ConditionType);
                return inflicts[a.ConditionGroupId] = set;
            }
        }

        static int gilBefore;
        static int Gil() => Last.Management.UserDataManager.Instance()?.OwendGil ?? 0;
        internal static int Venoms, GilKept;

        static void VenomAndMaintenance(BcJunctionActs.Act act, List<BcJunctionActs.Landed> units)
        {
            var a = act.Attacker;
            if (a == null) return;
            if (Has(a, "potent_venom") && Inflicts(act.Ability).Contains(ConditionType.Poison))
            {
                var cc = BattlePlugManager.Instance()?.BattleConditionController;
                foreach (var l in units.Where(l => l.Targeted && !l.Before.Contains(ConditionType.Poison) && !l.After.Contains(ConditionType.Poison)))
                    if (BcJunction.Alive(l.Unit) && BcJunction.Rng.Next(2) == 0) { cc?.InterruptAddCondition(l.Unit, ConditionType.Poison); Venoms++; }
            }
            int lost = gilBefore - Gil();
            if (lost > 0 && !BcJunction.IsPlayer(a) && BcJunction.Used("maintenance") &&
                units.Any(l => l.Targeted && BcJunction.IsPlayer(l.Unit) && BcJunction.Has(l.Unit, "maintenance")))
            {
                new Last.Management.OwnedItemClient().AddGil(lost);
                GilKept += lost;
                Kit.Info($"{BcJunction.Tag} Maintenance: {lost} gil a monster took came back");
            }
        }

        // --- Esper Attack's status rider (C2/0B8E): 25% a target hit by the holder gets its esper's statuses (a
        // status-lifting esper's: loses them); immunities apply (the game's own add)
        internal static int Riders;

        static void EsperRider(BcJunctionActs.Act act, List<BcJunctionActs.Landed> units)
        {
            var a = act.Attacker;
            if (a == null || !BcJunction.IsPlayer(a) || !Has(a, "esper_attack")) return;
            var oc = a.GetOwnedCharacterData();
            var e = oc != null && oc.MagicStoneId > 0 ? BcJunctionField.EsperInfo(oc.MagicStoneId) : null;
            if (e == null || e.Statuses.Length == 0) return;
            var cc = BattlePlugManager.Instance()?.BattleConditionController;
            foreach (var l in units.Where(l => l.Targeted && !l.Missed && BcJunction.Alive(l.Unit)))
            {
                if (BcJunction.Rng.Next(4) != 0) continue;
                foreach (int s in e.Statuses)
                {
                    var t = BcJunction.ConditionOf(s);
                    if (t == ConditionType.Non || t == ConditionType.UnableFight || t == ConditionType.Hide) continue;
                    if (e.Lift) { if (BcJunction.HasStatus(l.Unit, t)) cc?.InterruptRemoveCondition(l.Unit, t); }
                    else if (!BcJunction.HasStatus(l.Unit, t)) cc?.InterruptAddCondition(l.Unit, t);
                }
                Riders++;
            }
        }

        // --- Sneeze Guard, Innate Runic ------------------------------------------------------------------------

        internal static readonly HashSet<int> Removers = new HashSet<int> { 340, 371 };   // Sneeze, Baba Breath
        internal static int Guarded, Stances;

        static void SneezeGuard(BcJunctionActs.Act act)
        {
            var a = act.Attacker;
            if (a == null || act.Ability == null || !Removers.Contains(act.Ability.Id) || !BcJunction.Used("sneeze_guard")) return;
            var keep = act.Targets.Where(t => BcJunction.SameSide(a, t) || !BcJunction.Has(t, "sneeze_guard")).ToList();
            if (keep.Count == act.Targets.Count || keep.Count == 0) return;     // none left: the game's own (BC: no target)
            var arr = new Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppReferenceArray<BattleUnitData>(keep.Count);
            for (int i = 0; i < keep.Count; i++) arr[i] = keep[i];
            act.Data.TargetUnitDatas = arr;
            act.Targets.Clear();
            act.Targets.AddRange(keep);
            Guarded++;
        }

        internal static void InnateRunic(BattleUnitData u)
        {
            if (u == null || !BcJunction.Used("innate_runic") || !BcJunction.Alive(u) || BcJunction.HasStatus(u, ConditionType.MagicSealSword)) return;
            if (!BcJunction.HasRaw(u, "innate_runic")) return;
            BattlePlugManager.Instance()?.BattleConditionController?.InterruptAddCondition(u, ConditionType.MagicSealSword);
            Stances++;
        }

        // --- Double Time, Instant Act --------------------------------------------------------------------------

        static readonly HashSet<IntPtr> halfGauge = new HashSet<IntPtr>();

        // per frame: a Double Time holder's gauge, once the game empties it after its turn, restarts half full
        internal static void Update()
        {
            if (halfGauge.Count == 0) return;
            var atb = BcJunctionStart.Atb();
            if (atb == null) { halfGauge.Clear(); return; }
            foreach (var u in BcJunction.Party().Concat(BcJunction.Enemies()))
            {
                if (!halfGauge.Contains(u.Pointer)) continue;
                float g = BcJunctionStart.Gauge(u);
                if (g >= 0 && g < 50)
                {
                    atb.ChangeATBGaugeByUnitData(u, 50f);
                    halfGauge.Remove(u.Pointer);
                    HalfGauges++;
                }
            }
        }

        public static void Chant_Postfix(BattleActData battleActData, ref float __result)
        {
            if (__result <= 0 || battleActData == null || !BcJunction.On) return;
            var a = battleActData.AttackUnitData;
            if (a == null) return;
            var ab = battleActData.abilityList != null && battleActData.abilityList.Count > 0 ? battleActData.abilityList[0] : null;
            bool jump = ab != null && (ab.TypeId == 15 || ab.TypeId == 16);
            if (Has(a, "instant_act") || (jump && Has(a, "highwind")))
            {
                __result = 0f;
                Waits++;
            }
        }
    }

    // content flag 5 = ignore defense (BNW's formula probe; as T-Edition's TedDamage.IgnoresDefense)
    static class TEditionLike
    {
        static readonly Dictionary<int, bool> cache = new Dictionary<int, bool>();

        internal static bool IgnoresDefense(Ability a)
        {
            if (a == null || a.ContentFlagGroupId == 0) return false;
            lock (cache)
            {
                if (cache.TryGetValue(a.ContentFlagGroupId, out bool known)) return known;
                bool found = false;
                var list = Master.All<ContentFlagGroup>();
                if (list != null)
                    foreach (var kv in list)
                        if (kv.Value != null && kv.Value.GroupId == a.ContentFlagGroupId && kv.Value.ContentFlagId == 5) { found = true; break; }
                return cache[a.ContentFlagGroupId] = found;
            }
        }
    }
}
