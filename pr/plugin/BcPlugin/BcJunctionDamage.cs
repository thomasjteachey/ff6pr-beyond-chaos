using System;
using System.Collections.Generic;
using System.Linq;
using Last.Battle;
using Last.Data;
using Last.Data.Master;
using Last.Data.User;
using Last.Defaine;
using Last.Systems;
using PrKit;
using HarmonyLib;
using Il2CppIntMap = Il2CppSystem.Collections.Generic.Dictionary<int, int>;

namespace BeyondChaos.PR
{
    // Junction effects on the damage and healing formulas (BC's patch_junction_damage_modification /
    // elemental_pierce / elemental_repel / boost_crit / faith / barehanded / potent_venom...): the PR works out
    // each hit in CalcControllerProvider (GetFightStatus, GetMagicStatus, GetRecoveryStatus, GetThrowStatus and
    // the fixed-base forms); the prefix records the hit (who, whom, the ability, its elements), the target's
    // element table is read with the effects' responses while the game computes it, and the postfix scales the
    // game's value by the effects' factors (as BNW's BattleFormulas and T-Edition's TedDamage do).
    static class BcJunctionDamage
    {
        // SNES element bits 0-7 (fire ice bolt poison wind pearl earth water) -> the PR's attribute ids
        internal static readonly int[] ElementAttr = { 1, 2, 3, 6, 8, 7, 4, 5 };
        internal static readonly string[] ElementKey = { "fire", "ice", "bolt", "poison", "wind", "pearl", "earth", "water" };
        // the game's element responses (TEdition DamageSteps): normal, weak, half, null, absorb
        internal const int Normal = 0, Weak = 1, Half = 2, Null = 3, Absorb = 4;
        internal static int Cap = 9999;

        internal enum Kind { Fight, Magic, Heal, Throw }

        internal sealed class Calc
        {
            public CalcControllerProvider C;
            public Kind Kind;
            public BattleUnitData Attacker, Target;
            public Ability Ability;
            public OwnedItemData Item;
            public int Command;
            public int[] Elements = Array.Empty<int>();      // PR attribute ids of the attack
            public int[] EsperElements;                       // Esper Attack: the attacker's esper's elements (null: none)
            public bool Physical => Kind == Kind.Fight || Kind == Kind.Throw;
            public bool Heal => Kind == Kind.Heal;
            public double Factor = 1;
            public float Time = UnityEngine.Time.realtimeSinceStartup;
            public readonly List<string> Fired = new List<string>();
            public int[] ResponsesBefore;                     // the target's responses before the effects (tests, the log)
            public Dictionary<int, int> Responses;            // the effects' element responses for the target (null: none)
            public int Value, ValueAfter;                     // the game's result, and after the effects
            public HitType Hit;                               // the game's hit type
            public HitType? HitAfter;                         // an effect's new hit type (a heal turned to damage...)
            public int CapOver;                               // an effect's higher cap (Overheal); 0: the game's
            public int CapFor() => Math.Max(Cap, CapOver);
            public bool HasElement(int snesBit) => Elements.Contains(ElementAttr[snesBit]);
            public void Scale(string key, double f) { Factor *= f; Fired.Add($"{key} x{f:0.###}"); }
            public bool Missed;
            public void ForceMiss(string key) { Missed = true; HitAfter = HitType.Miss; Fired.Add($"{key} miss"); }
            public bool Damaging => Hit == HitType.Hit || Hit == HitType.Critical;
        }

        // the effects: a factor on the result, and element responses for the target (BcJunctionEffects registers them)
        internal static readonly List<(string Name, Action<Calc> Run)> Rules = new List<(string, Action<Calc>)>();
        internal static readonly List<(string Name, Action<Calc, Dictionary<int, int>>)> ResponseRules =
            new List<(string, Action<Calc, Dictionary<int, int>>)>();

        internal static Calc Last;          // self-tests: the last hit worked out
        internal static readonly List<Calc> Recent = new List<Calc>();   // self-tests: the hits worked out (while Logging)
        internal static bool Logging;
        internal static int Applied;
        [ThreadStatic] static Calc current;
        internal static Calc Current => current;    // the hit being worked out (stat hooks read it)

        public static void Patch(Harmony h)
        {
            var calc = typeof(CalcControllerProvider);
            Hooks.Patch(h, calc, "GetFightStatus", typeof(BcJunctionDamage), prefix: nameof(Fight_Prefix), postfix: nameof(Calc_Postfix));
            Hooks.Patch(h, calc, "GetMagicStatus", typeof(BcJunctionDamage), prefix: nameof(Magic_Prefix), postfix: nameof(Calc_Postfix));
            Hooks.Patch(h, calc, "GetRecoveryStatus", typeof(BcJunctionDamage), prefix: nameof(Heal_Prefix), postfix: nameof(Calc_Postfix));
            Hooks.Patch(h, calc, "GetThrowStatus", typeof(BcJunctionDamage), prefix: nameof(Throw_Prefix), postfix: nameof(Calc_Postfix));
            Hooks.Patch(h, calc, "GetFixedBaseValueMagicStatus", typeof(BcJunctionDamage), prefix: nameof(Magic_Prefix), postfix: nameof(Calc_Postfix));
            Hooks.Patch(h, calc, "GetFixedBaseValueRecoveryStatus", typeof(BcJunctionDamage), prefix: nameof(Heal_Prefix), postfix: nameof(Calc_Postfix));
            Hooks.Patch(h, typeof(PlayerCharacterParameter), "ConfirmedResistanceAttributeList", typeof(BcJunctionDamage), postfix: nameof(Resist_Postfix));
            Hooks.Patch(h, typeof(EnemyCharacterParameter), "ConfirmedResistanceAttributeList", typeof(BcJunctionDamage), postfix: nameof(Resist_Postfix));
        }

        public static void Fight_Prefix(CalcControllerProvider __instance, ref Calc __state) => Enter(__instance, ref __state, Kind.Fight);
        public static void Magic_Prefix(CalcControllerProvider __instance, ref Calc __state) => Enter(__instance, ref __state, Kind.Magic);
        public static void Heal_Prefix(CalcControllerProvider __instance, ref Calc __state) => Enter(__instance, ref __state, Kind.Heal);
        public static void Throw_Prefix(CalcControllerProvider __instance, ref Calc __state) => Enter(__instance, ref __state, Kind.Throw);

        static void Enter(CalcControllerProvider c, ref Calc state, Kind kind)
        {
            state = null;
            if (current != null || c == null || !BcJunction.On || !Hooks.IsA<CalcControllerProvider>(c)) return;
            try
            {
                var target = c.target;
                var attacker = c.attack;
                if (target == null || attacker == null) return;
                var calc = new Calc
                {
                    C = c, Kind = kind, Ability = c.ability, Item = c.item,
                    Attacker = c.GetUnitData(attacker), Target = c.GetUnitData(target),
                    Command = c.calcInfo?.command?.Id ?? 0,
                };
                calc.Elements = Elements(c, calc.Ability, calc.Physical);
                // the responses first (the game reads the table while it computes)
                var responses = new Dictionary<int, int>();
                foreach (var (name, run) in ResponseRules)
                {
                    try { run(calc, responses); }
                    catch (Exception e) { Hooks.WarnOnce("bc-junction-response-" + name, e); }
                }
                if (responses.Count > 0) calc.Responses = responses;
                state = calc;
                current = calc;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-damage-enter", e); }
        }

        public static void Calc_Postfix(CalcControllerProvider __instance, ICalcResult __result, Calc __state)
        {
            if (__state == null) return;
            if (current == __state) current = null;
            try
            {
                if (__result == null) return;
                var calc = __state;
                var hit = __result.GetHitType();
                int value = __result.GetValue(false);
                calc.Value = value;
                calc.Hit = hit;
                foreach (var (name, run) in Rules)
                {
                    try { run(calc); }
                    catch (Exception e) { Hooks.WarnOnce("bc-junction-rule-" + name, e); }
                }
                Last = calc;
                BcJunctionActs.Current?.Calcs.Add(calc);
                if (Logging) { Recent.Add(calc); if (Recent.Count > 300) Recent.RemoveRange(0, 100); }
                bool scaled = (hit == HitType.Hit || hit == HitType.Critical || hit == HitType.Recovery) && value > 0;
                if (calc.Missed) calc.ValueAfter = 0;
                else if (scaled && Math.Abs(calc.Factor - 1.0) > 1e-9)
                {
                    int now = (int)Math.Min(calc.CapFor(), Math.Max(calc.Factor > 0 ? 1 : 0, Math.Floor(value * calc.Factor)));
                    if (now != value)
                    {
                        __result.SetValue(now);
                        Applied++;
                    }
                    calc.ValueAfter = now;
                }
                else calc.ValueAfter = value;
                if (calc.HitAfter.HasValue && calc.HitAfter.Value != hit)
                    __result.TryCast<CalcResult>()?.SetStatus(calc.ValueAfter, calc.HitAfter.Value, __result.GetHitCount(),
                        calc.Missed ? new Il2CppSystem.Collections.Generic.List<Condition>() : __result.GetConditions());
                if (calc.Fired.Count > 0)
                    Hooks.NoteOnce("bc-junction-damage", () => $"{BcJunction.Tag} first damage effect: {string.Join(", ", calc.Fired)} " +
                                                               $"({BcJunction.Who(calc.Attacker)} -> {BcJunction.Who(calc.Target)}, {value} -> {calc.ValueAfter})");
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-damage-result", e); }
        }

        // the target's element table while its hit is worked out, with the effects' responses
        public static void Resist_Postfix(CharacterParameterBase __instance, ref Il2CppIntMap __result)
        {
            var calc = current;
            if (calc?.Responses == null || __instance == null || calc.C == null || calc.C.target == null ||
                __instance.Pointer != calc.C.target.Pointer) return;
            try
            {
                var m = new Il2CppIntMap();
                if (__result != null)
                    foreach (var kv in __result) m[kv.Key] = kv.Value;
                if (calc.ResponsesBefore == null)
                    calc.ResponsesBefore = calc.Elements.Select(e => m.ContainsKey(e) ? m[e] : Normal).ToArray();
                foreach (var kv in calc.Responses) m[kv.Key] = kv.Value;
                __result = m;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-resist", e); }
        }

        // the attack's elements as the game takes them (TedDamage.Elements: the ability's, and a character's
        // striking weapon's for a physical hit)
        internal static int[] Elements(CalcControllerProvider c, Ability ability, bool physical)
        {
            var set = new SortedSet<int>();
            try
            {
                if (ability != null)
                {
                    var arr = c.GetAbilityAttributeArray(ability);
                    if (arr != null) foreach (var a in arr) if (a > 0) set.Add(a);
                }
                if (physical && c.userCharaData != null)
                {
                    var pp = c.attack?.TryCast<PlayerCharacterParameter>();
                    var ci = c.calcInfo;
                    if (pp != null && ci != null)
                    {
                        var arm = ci.userWeapon != null && ci.userLeftWeapon != null && ci.userRightWeapon != null &&
                                  ci.userWeapon.Id == ci.userLeftWeapon.Id && ci.userWeapon.Id != ci.userRightWeapon.Id
                            ? BattleActData.ArmType.Left : BattleActData.ArmType.Right;
                        var list = pp.GetArmConfirmedActiveAttributeList(arm);
                        if (list != null) foreach (var a in list) if (a > 0) set.Add(a);
                    }
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-elements", e); }
            return set.ToArray();
        }
    }
}
