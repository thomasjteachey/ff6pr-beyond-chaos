using System;
using System.Collections.Generic;
using System.Linq;
using Last.Battle;
using Last.Defaine;
using Last.Systems;
using PrKit;
using Calc = BeyondChaos.PR.BcJunctionDamage.Calc;
using Kind = BeyondChaos.PR.BcJunctionDamage.Kind;

namespace BeyondChaos.PR
{
    // Junction effects on the numbers of a hit (BC's patch_junction_damage_modification at C2/336F and
    // patch_junction_damage_trigger at C2/62EF; spec pr/build/bc_junction/spec_A.json). BC works on the strike's
    // base ($11B0, before defense, crits and the split) and then on each target's pending amount; here each
    // target's result from the game's formula (BcJunctionDamage), the same factors in BC's order:
    //   damage_modification (the attacker's strike):
    //     1 Esper Attack: the equipped esper's elements join the attack's (for these steps and Pierce)
    //     2 each element (Fire, Ice, Lightning, Poison, Wind, Holy, Earth, Water): the attacker's <element> Boost
    //       x1.5, then x1.25 per living <element> Font holder, x0.75 per living <element> Sink holder (either side)
    //     3 Summon Boost x1.5 (an esper's summon)   4 Nuke (no element, not physical, not a heal): Boost x1.5,
    //       Font x1.25 / Sink x0.75 per holder        5 Physical: Boost x1.5, Font/Sink per holder
    //     6 Loner: x1/2 x (5 - the living on the attacker's side)   7 Crisis Arm: x(current HP mod 10)/4
    //     8 Gaia Boost (the battlefield's element) x1.5   9 Atma Force: x1.5 x (side's HP / side's max HP)
    //   Crit Boost: a critical x1.5 more (the game's own x2 after)
    //   damage_trigger (each target's amount): Heal Boost x1.5, Heal Font x1.25 / Sink x0.75 per holder (heals);
    //     Blood Mage: no healing of itself with an MP-cost heal; Brace: a defending target x1/2; Catch: a thrown
    //     weapon does nothing to the holder (and, half the time, a party holder catches one); Double Time: x1/2;
    //     Chemist: an item x2; Reverse: damage heals and healing hurts; Precision: a multi-target act doesn't
    //     hurt the attacker's side. Then 9999.
    //   Pierce (C2/0BD3): the attacker's <element> Pierce: the target can't absorb, nullify or halve that element
    //     (weakness stays); Art License: a sketched attack pierces every element; Esper Attack: the esper's.
    static class BcJunctionFormulas
    {
        // the PR's summon abilities (SNES espers 0-26: tools/idmap.py _ESPERS)
        internal static readonly HashSet<int> Summons = new HashSet<int>
            { 88, 92, 93, 90, 107, 96, 95, 99, 91, 103, 106, 111, 115, 112, 109, 114, 113, 89, 101, 98, 97, 102, 100, 94, 105, 108, 110 };
        internal static readonly int[] SummonOf =      // by SNES esper index
            { 88, 92, 93, 90, 107, 96, 95, 99, 91, 103, 106, 111, 115, 112, 109, 114, 113, 89, 101, 98, 97, 102, 100, 94, 105, 108, 110 };
        internal const int ItemsCommand = 3, ThrowCommand = 13;
        internal static int Caught;

        internal static void Register()
        {
            BcJunctionDamage.Rules.Add(("strike", Strike));
            BcJunctionDamage.Rules.Add(("crit", Crit));
            BcJunctionDamage.Rules.Add(("trigger", Trigger));
            BcJunctionDamage.ResponseRules.Add(("pierce", Pierce));
        }

        static bool Has(BattleUnitData u, string key) => BcJunction.Used(key) && BcJunction.Has(u, key);

        // how many living fighters have an effect (each check its own Jammer roll), only if anyone could
        static int Count(string key) => BcJunction.Used(key) ? BcJunction.CountLiving(key) : 0;

        static bool Healing(Calc c) => c.Hit == HitType.Recovery || c.Hit == HitType.MPRecovery;
        static bool Damage(Calc c) => c.Hit == HitType.Hit || c.Hit == HitType.Critical || c.Hit == HitType.MPHit;

        // the SNES element bits of the attack (its own and, with Esper Attack, the esper's)
        internal static List<int> ElementBits(Calc c)
        {
            var bits = new List<int>();
            for (int b = 0; b < 8; b++)
                if (c.HasElement(b) || (c.EsperElements != null && c.EsperElements.Contains(BcJunctionDamage.ElementAttr[b]))) bits.Add(b);
            return bits;
        }

        // --- damage_modification ------------------------------------------------------------------------

        static void Strike(Calc c)
        {
            if (!Damage(c) && !Healing(c)) return;
            var a = c.Attacker;
            if (a == null) return;
            // 1 Esper Attack: the esper's elements (characters with an esper)
            if (c.EsperElements == null && Has(a, "esper_attack")) c.EsperElements = EsperElements(a);
            // 2 elements
            foreach (int b in ElementBits(c))
            {
                var e = BcJunctionDamage.ElementKey[b];
                if (Has(a, "boost_" + e)) c.Scale("boost_" + e, 1.5);
                for (int n = Count(e + "_font"); n > 0; n--) c.Scale(e + "_font", 1.25);
                for (int n = Count(e + "_sink"); n > 0; n--) c.Scale(e + "_sink", 0.75);
            }
            // 3 Summon Boost
            if (c.Ability != null && Summons.Contains(c.Ability.Id) && Has(a, "boost_esper")) c.Scale("boost_esper", 1.5);
            // 4 Nuke: no element, not physical, not a heal
            if (ElementBits(c).Count == 0 && !c.Physical && !c.Heal && Damage(c))
            {
                if (Has(a, "boost_nuke")) c.Scale("boost_nuke", 1.5);
                for (int n = Count("nuke_font"); n > 0; n--) c.Scale("nuke_font", 1.25);
                for (int n = Count("nuke_sink"); n > 0; n--) c.Scale("nuke_sink", 0.75);
            }
            // 5 Physical
            if (c.Physical)
            {
                if (Has(a, "boost_phys")) c.Scale("boost_phys", 1.5);
                for (int n = Count("phys_font"); n > 0; n--) c.Scale("phys_font", 1.25);
                for (int n = Count("phys_sink"); n > 0; n--) c.Scale("phys_sink", 0.75);
            }
            // 6 Loner: x1/2 x (5 - the living on the attacker's side, itself included)
            if (Has(a, "loner"))
            {
                int side = (BcJunction.IsPlayer(a) ? BcJunction.Party() : BcJunction.Enemies()).Count(BcJunction.Alive);
                c.Scale("loner", BcJunctionMath.Loner(side));
            }
            // 7 Crisis Arm: x(current HP mod 10) / 4
            if (Has(a, "crisis_arm"))
            {
                int hp = a.BattleUnitDataInfo?.Parameter?.CurrentHP ?? 0;
                c.Scale("crisis_arm", BcJunctionMath.CrisisArm(hp));
            }
            // 8 Gaia Boost: the battlefield's element
            if (Has(a, "gaia_boost"))
            {
                int g = BcJunctionField.GaiaElementBit();
                if (g >= 0 && ElementBits(c).Contains(g)) c.Scale("gaia_boost", 1.5);
            }
            // 9 Atma Force: x1.5 x the side's HP fraction (BC: expected HP by level; here the side's max HP)
            if (Has(a, "atma_force"))
            {
                long cur = 0, max = 0;
                foreach (var u in BcJunction.IsPlayer(a) ? BcJunction.Party() : BcJunction.Enemies())
                {
                    var p = u.BattleUnitDataInfo?.Parameter;
                    if (p == null || u.IsRemove) continue;
                    cur += Math.Max(0, p.CurrentHP);
                    max += Math.Max(1, p.ConfirmedMaxHp());
                }
                if (max > 0) c.Scale("atma_force", BcJunctionMath.AtmaForce(cur, max));
            }
        }

        static void Crit(Calc c)
        {
            if (c.Hit == HitType.Critical && c.Attacker != null && Has(c.Attacker, "boost_crit")) c.Scale("boost_crit", 1.5);
        }

        // --- damage_trigger -----------------------------------------------------------------------------

        static void Trigger(Calc c)
        {
            var a = c.Attacker;
            var t = c.Target;
            if (a == null || t == null || c.Missed) return;
            bool heal = Healing(c), dmg = Damage(c);
            if (!heal && !dmg) return;
            if (heal)
            {
                if (Has(a, "heal_boost")) c.Scale("heal_boost", 1.5);
                for (int n = Count("heal_font"); n > 0; n--) c.Scale("heal_font", 1.25);
                for (int n = Count("heal_sink"); n > 0; n--) c.Scale("heal_sink", 0.75);
                // Blood Mage: a heal with an MP cost doesn't heal its own caster
                if (a.Pointer == t.Pointer && (c.Ability?.UseValue ?? 0) > 0 && c.Heal && Has(a, "blood_mage"))
                    c.Scale("blood_mage", 0);
            }
            if (dmg && BcJunction.HasStatus(t, ConditionType.Defend) && Has(t, "brace")) c.Scale("brace", 0.5);
            if (c.Command == ThrowCommand && Has(t, "catch"))
            {
                c.Scale("catch", 0);
                if (BcJunction.IsPlayer(t) && BcJunction.Rng.Next(2) == 0) BcJunctionRewards.Catch(t, c.Item);
            }
            if (Has(a, "double_time")) c.Scale("double_time", 0.5);
            if (c.Command == ItemsCommand && Has(a, "chemist")) c.Scale("chemist", 2);
            if (Has(a, "reverse"))
            {
                c.HitAfter = c.Hit == HitType.Recovery ? HitType.Hit : c.Hit == HitType.MPRecovery ? HitType.MPHit
                           : c.Hit == HitType.MPHit ? HitType.MPRecovery : HitType.Recovery;
                c.Fired.Add("reverse");
            }
            if (dmg && (BcJunctionActs.Current?.Targets.Count ?? 1) >= 2 && BcJunction.SameSide(a, t) && Has(a, "precision"))
                c.ForceMiss("precision");
        }

        // --- Pierce / Art License / Esper Attack: no absorb, null or half for those elements -----------------

        static void Pierce(Calc c, Dictionary<int, int> responses)
        {
            var a = c.Attacker;
            if (a == null || c.Heal) return;
            bool art = Has(a, "art_license") && BcJunctionActs.Current?.Data?.UseActAbilityType == BattleActData.ActAbilityType.Sketch;
            if (Has(a, "esper_attack")) c.EsperElements = EsperElements(a);
            var table = TargetTable(c);
            for (int b = 0; b < 8; b++)
            {
                int attr = BcJunctionDamage.ElementAttr[b];
                bool own = c.Elements.Contains(attr), esper = c.EsperElements != null && c.EsperElements.Contains(attr);
                if (!own && !esper) continue;
                if (!(art || esper || Has(a, "pierce_" + BcJunctionDamage.ElementKey[b]))) continue;
                int r = table != null && table.TryGetValue(attr, out int v) ? v : BcJunctionDamage.Normal;
                if (r == BcJunctionDamage.Half || r == BcJunctionDamage.Null || r == BcJunctionDamage.Absorb)
                {
                    responses[attr] = BcJunctionDamage.Normal;
                    c.Fired.Add($"pierce {attr}");
                }
            }
        }

        // the target's element table as the game has it (without the effects)
        internal static Dictionary<int, int> TargetTable(Calc c)
        {
            try
            {
                var m = c.C?.target?.ConfirmedResistanceAttributeList();
                if (m == null) return null;
                var d = new Dictionary<int, int>();
                foreach (var kv in m) d[kv.Key] = kv.Value;
                return d;
            }
            catch { return null; }
        }

        // a character's equipped esper's summon elements (PR attribute ids), from the seed's record
        internal static int[] EsperElements(BattleUnitData u)
        {
            var oc = u?.GetOwnedCharacterData();
            if (oc == null || oc.MagicStoneId <= 0) return Array.Empty<int>();
            return BcJunctionField.EsperInfo(oc.MagicStoneId)?.Elements ?? Array.Empty<int>();
        }
    }
}
