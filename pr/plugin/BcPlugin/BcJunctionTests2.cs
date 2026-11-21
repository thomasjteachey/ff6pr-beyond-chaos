using System;
using System.Collections.Generic;
using System.Linq;
using Last.Battle;
using Last.Defaine;
using Last.Systems;
using PrKit;
using static BeyondChaos.PR.BcJunctionTests;
using Calc = BeyondChaos.PR.BcJunctionDamage.Calc;

namespace BeyondChaos.PR
{
    // The junction effects' checks, second wave: each gives effects, queues acts through the same queue the
    // effects use (free casts: MP topped up) and checks the damage hook's record of what fired, and the outcome.
    static class BcJunctionTests2
    {
        const int Fire = 40, Cure = 32, AttackCmd = 1, MagicCmd = 7;

        static List<Calc> Calcs(float since) => BcJunctionDamage.Recent.Where(c => c.Time >= since).ToList();
        static bool Fired(Calc c, string key) => c.Fired.Any(f => f.StartsWith(key));
        static string Tags(Calc c) => string.Join(" ", c.Fired);

        // the same fighter (the game hands out a new wrapper per lookup: compare the native objects)
        static bool Same(BattleUnitData a, BattleUnitData b) => a != null && b != null && a.Pointer == b.Pointer;

        static void Cast(BattleUnitData who, BattleUnitData at, int ability, int cmd = MagicCmd) =>
            BcJunctionTriggers.Cast(who, at, ability, true, "test", cmd, counter: false);

        static void Ready()
        {
            BcSelfTests.Sturdy();
            foreach (var p in BcJunction.Party()) { SetHp(p, 9999); SetMp(p, 999); }
        }

        // a test with acts queued at its start and a check once `n` of the logged calcs (by `who` at `at`) are in
        static void Calcs(string name, int n, Action<float> start, Func<List<Calc>, float, string> check,
                          Func<Calc, bool> which = null)
        {
            Add(name, began => { Ready(); start(began); }, began =>
            {
                var cs = Calcs(began).Where(which ?? (_ => true)).ToList();
                return cs.Count < n ? null : check(cs, began);
            });
        }

        internal static void Register()
        {
            Register3();
            Register4();
            Register5();
            // element Boost, Font and Sink on one Fire: x1.5 x1.25 x0.75
            Calcs("elements", 1, b =>
            {
                BcJunction.Grant(P(0), "boost_fire");
                BcJunction.Grant(P(1), "fire_font");
                BcJunction.Grant(LivingEnemy(), "fire_sink");
                Cast(P(0), LivingEnemy(), Fire);
            }, (cs, b) =>
            {
                var c = cs[0];
                bool ok = Fired(c, "boost_fire") && Fired(c, "fire_font") && Fired(c, "fire_sink") && Math.Abs(c.Factor - 1.40625) < 0.01;
                return (ok ? "ok: " : "FAILED: ") + $"{Tags(c)}; factor {c.Factor:0.###}; {c.Value} -> {c.ValueAfter}";
            }, c => Same(c.Attacker, P(0)) && c.Ability?.Id == Fire);   // not party member 0's auto-battle MagiTek
            // Physical Boost and Loner (x1/2 per missing ally below 5)
            Calcs("physical", 1, b =>
            {
                BcJunction.Grant(P(0), "boost_phys", "loner");
                Act(P(0), LivingEnemy(), AttackAbility(), AttackCmd);
            }, (cs, b) =>
            {
                var c = cs[0];
                int side = BcJunction.Party().Count(BcJunction.Alive);
                double want = 1.5 * 0.5 * Math.Max(0, 5 - side);
                bool ok = Fired(c, "boost_phys") && Fired(c, "loner") && Math.Abs(c.Factor - want) < 0.01;
                return (ok ? "ok: " : "FAILED: ") + $"{Tags(c)}; factor {c.Factor:0.###} (want {want}, {side} standing); {c.Value} -> {c.ValueAfter}";
            }, c => Same(c.Attacker, P(0)) && c.Command == AttackCmd);
            // Fire Pierce against a monster made to absorb Fire for the test: a hit, not a heal
            Calcs("pierce", 1, b =>
            {
                var e = LivingEnemy();
                e.BattleUnitDataInfo?.BattleTempParameter?.SetTempAttribute(1, BcJunctionDamage.Absorb);
                BcJunction.Grant(P(0), "pierce_fire");
                Cast(P(0), e, Fire);
            }, (cs, b) =>
            {
                var c = cs[0];
                LivingEnemy()?.BattleUnitDataInfo?.BattleTempParameter?.RemoveTempAttribute(1);
                bool ok = c.Hit == HitType.Hit || c.Hit == HitType.Critical;
                return (ok ? "ok: " : "FAILED: ") + $"Fire on an absorber with Fire Pierce: {c.Hit} {c.Value} ({Tags(c)})";
            }, c => Same(c.Attacker, P(0)) && c.Ability?.Id == Fire);
            // Reverse: a Cure from the holder hurts
            Add("reverse", b => { Ready(); BcJunction.Grant(P(0), "reverse"); SetHp(P(1), 5000); Cast(P(0), P(1), Cure); }, b =>
            {
                var l = Mine(b, P(0), Cure).FirstOrDefault();
                if (l == null) return null;
                var t = On(l, P(1));
                return t != null && t.HpAfter < t.HpBefore ? $"ok: Cure hurt: HP {t.HpBefore} -> {t.HpAfter}" : $"FAILED: HP {t?.HpBefore} -> {t?.HpAfter}";
            });
            // Astral: a strike hits MP, not HP
            Add("astral", b => { Ready(); var e = LivingEnemy(); SetMp(e, 500); BcJunction.Grant(P(0), "astral"); Act(P(0), e, AttackAbility(), AttackCmd); }, b =>
            {
                var l = Mine(b, P(0), AttackAbility()).FirstOrDefault();
                if (l == null) return null;
                var t = l.Units.FirstOrDefault(x => x.Targeted);
                return t != null && t.HpAfter == t.HpBefore && t.MpAfter < t.MpBefore
                    ? $"ok: MP {t.MpBefore} -> {t.MpAfter}, HP kept" : $"FAILED: HP {t?.HpBefore} -> {t?.HpAfter}, MP {t?.MpBefore} -> {t?.MpAfter}";
            });
            // MP Switch: of 8 monster strikes at the holder, some hit MP instead (50%)
            Add("mp_switch", b => { Ready(); BcJunction.Grant(P(1), "mp_switch"); for (int i = 0; i < 8; i++) Act(LivingEnemy(), P(1), AttackAbility(), AttackCmd); }, b =>
            {
                var ls = Mine(b, LivingEnemy(), AttackAbility());
                if (ls.Count < 8) return null;
                var on = ls.Select(l => On(l, P(1))).Where(x => x != null && x.Targeted).ToList();
                int mp = on.Count(x => x.MpAfter < x.MpBefore && x.HpAfter == x.HpBefore);
                return mp >= 1 && mp < on.Count ? $"ok: {mp} of {on.Count} strikes hit MP" : $"FAILED: {mp} of {on.Count} hit MP";
            });
            // Null Sleep: a sleeping holder can't be hit
            Add("null_sleep", b =>
            {
                Ready();
                BattlePlugManager.Instance()?.BattleConditionController?.InterruptAddCondition(P(2), ConditionType.Sleep);
                BcJunction.Grant(P(2), "null_sleep");
                for (int i = 0; i < 3; i++) Act(LivingEnemy(), P(2), AttackAbility(), AttackCmd);
            }, b =>
            {
                var ls = Mine(b, LivingEnemy(), AttackAbility());
                if (ls.Count < 3) return null;
                var on = ls.Select(l => On(l, P(2))).Where(x => x != null && x.Targeted).ToList();
                BattlePlugManager.Instance()?.BattleConditionController?.InterruptRemoveCondition(P(2), ConditionType.Sleep);
                return on.All(x => x.Damage == 0) ? $"ok: {on.Count} strikes at the sleeper did nothing" : $"FAILED: damage {string.Join(",", on.Select(x => x.Damage))}";
            });
            // SOS: Near Fatal fires each SOS effect once (here Haste and Regen, free self-casts)
            Add("sos", b =>
            {
                Ready();
                var u = P(3) ?? P(0);
                BcJunction.Grant(u, "critical_haste", "critical_regen");
                SetHp(u, Math.Max(1, MaxHp(u) / 10));
                BattlePlugManager.Instance()?.BattleConditionController?.InterruptAddCondition(u, ConditionType.Dying);
                BcJunctionTriggers.CheckSos();
            }, b =>
            {
                var u = P(3) ?? P(0);
                bool haste = BcJunction.HasStatus(u, ConditionType.Heist), regen = BcJunction.HasStatus(u, ConditionType.Regeneration);
                if (!(haste && regen) && Now - b < 20) return null;
                return haste && regen ? $"ok: Near Fatal: Haste and Regen on {BcJunction.Who(u)} ({BcJunctionTriggers.Sos} SOS so far)" : $"FAILED: Haste {haste}, Regen {regen}";
            });
            // Counter All: of 8 monster strikes, some answered with an Attack (25%)
            Add("counter_all", b => { Ready(); BcJunction.Grant(P(0), "counter_all"); for (int i = 0; i < 8; i++) Act(LivingEnemy(), P(0), AttackAbility(), AttackCmd); }, b =>
            {
                var ls = Mine(b, LivingEnemy(), AttackAbility());
                if (ls.Count < 8 || Now - b < 12) return null;
                int counters = Since(b, P(0)).Count(l => l.Act.Counter);   // not its auto-battle acts
                return counters >= 1 ? $"ok: {counters} counterattacks to 8 strikes (25% expected)" : "FAILED: no counterattack to 8 strikes";
            });
            // Hamedo: half the strikes miss and are answered
            Add("hamedo", b => { Ready(); BcJunction.Grant(P(1), "hamedo"); for (int i = 0; i < 8; i++) Act(LivingEnemy(), P(1), AttackAbility(), AttackCmd); }, b =>
            {
                var ls = Mine(b, LivingEnemy(), AttackAbility());
                if (ls.Count < 8 || Now - b < 12) return null;
                var on = ls.Select(l => On(l, P(1))).Where(x => x != null && x.Targeted).ToList();
                int missed = on.Count(x => x.Damage == 0), counters = Since(b, P(1)).Count(l => l.Act.Counter);
                return missed >= 1 && counters >= 1 ? $"ok: {missed} of {on.Count} missed, {counters} counters" : $"FAILED: {missed} missed, {counters} counters";
            });
            // Return Magic: a monster's Fire at the holder comes back
            Add("return_magic", b => { Ready(); BcJunction.Grant(P(2), "return_magic"); Cast(LivingEnemy(), P(2), Fire); }, b =>
            {
                var back = Since(b, P(2)).FirstOrDefault(l => l.Act.Ability?.Id == Fire);
                if (back == null) return Now - b < 15 ? null : "FAILED: no Fire back";
                return $"ok: {BcJunction.Who(P(2))} cast Fire back at {BcJunction.Who(back.Act.Targets.FirstOrDefault())}";
            });
            // Vampire: the attacker gets back what it dealt
            Add("vampire", b => { Ready(); BcJunction.Grant(P(0), "vampire"); SetHp(P(0), 1000); Act(P(0), LivingEnemy(), AttackAbility(), AttackCmd); }, b =>
            {
                var l = Mine(b, P(0), AttackAbility()).FirstOrDefault();
                if (l == null) return null;
                int dealt = l.Units.Where(x => x.Targeted).Sum(x => x.Damage);
                return Hp(P(0)) > 1000 ? $"ok: dealt {dealt}, HP 1000 -> {Hp(P(0))}" : $"FAILED: dealt {dealt}, HP {Hp(P(0))}";
            });
            // Gilgam Heart: gil for the HP lost
            Add("gilgam_heart", b => { Ready(); BcJunction.Grant(P(0), "gilgam_heart"); Act(LivingEnemy(), P(0), AttackAbility(), AttackCmd); gil = Gil(); }, b =>
            {
                var l = Mine(b, LivingEnemy(), AttackAbility()).FirstOrDefault();
                if (l == null) return null;
                var t = On(l, P(0));
                int got = Gil() - gil;
                return t != null && got == t.Damage ? $"ok: lost {t.Damage} HP, +{got} gil" : $"FAILED: lost {t?.Damage}, +{got} gil";
            });
            // Corrosive: the target's max HP drops by a quarter of the damage; Juggler: a physical hit makes Def >= MDef
            Add("corrosive_juggler", b =>
            {
                Ready();
                var e = LivingEnemy();
                maxWas = MaxHp(e);
                BcJunction.Grant(P(0), "corrosive");
                BcJunction.Grant(e, "juggler");
                Act(P(0), e, AttackAbility(), AttackCmd);
            }, b =>
            {
                var l = Mine(b, P(0), AttackAbility()).FirstOrDefault();
                if (l == null) return null;
                var t = l.Units.FirstOrDefault(x => x.Targeted);
                var p = t?.Unit.BattleUnitDataInfo?.Parameter;
                if (t == null || p == null) return "FAILED: no target";
                int want = (Math.Min(t.Damage, t.HpBefore) + 2) >> 2;
                bool corr = MaxHp(t.Unit) == Math.Max(1, maxWas - want);
                bool jug = p.ConfirmedDefense() >= p.ConfirmedAbilityDefense();
                return corr && jug ? $"ok: max HP {maxWas} -> {MaxHp(t.Unit)} after {t.Damage}; Def {p.ConfirmedDefense()} >= MDef {p.ConfirmedAbilityDefense()}"
                                   : $"FAILED: max HP {maxWas} -> {MaxHp(t.Unit)} (want -{want}), Def {p.ConfirmedDefense()} MDef {p.ConfirmedAbilityDefense()}";
            });
        }

        static int gil, maxWas, kept;

        static void Stock(string item)
        {
            int c = BcJunctionTriggers.Item(item);
            if (c > 0) new Last.Management.OwnedItemClient().AddOwnedItem(c, 2);
        }

        internal static void Register4()
        {
            // Repel Fire: a monster's Fire at the holder bounces (it isn't hit)
            Add("repel", b => { Ready(); BcJunction.Grant(P(1), "repel_fire"); Cast(LivingEnemy(), P(1), Fire); }, b =>
            {
                var l = Since(b, LivingEnemy()).FirstOrDefault(x => x.Act.Ability?.Id == Fire);
                if (l == null) return Now - b < 15 ? null : $"FAILED: no Fire landed ({BcJunctionMore.Repelled} repels)";
                var me = On(l, P(1));
                bool hit = me != null && me.Targeted && me.Damage > 0;
                return !hit && BcJunctionMore.Repelled > 0 ? $"ok: Fire bounced off {BcJunction.Who(P(1))} ({BcJunctionMore.Repelled} repels)"
                                                           : $"FAILED: holder hit {me?.Damage} ({BcJunctionMore.Repelled} repels)";
            });
            // Flinch: the attacker's strikes cut a monster's gauge to a quarter (50% each; 6 strikes)
            Add("flinch", b => { Ready(); BcJunction.Grant(P(0), "flinch"); for (int i = 0; i < 6; i++) Act(P(0), LivingEnemy(), AttackAbility(), AttackCmd); }, b =>
            {
                if (Mine(b, P(0), AttackAbility()).Count < 6) return null;
                return BcJunctionTriggers.Flinches > 0 ? $"ok: {BcJunctionTriggers.Flinches} flinches in 6 strikes" : "FAILED: no flinch in 6 strikes";
            });
            // Discordant: the target's level ends in the attacker's HP's last digit
            Add("discordant", b => { Ready(); SetHp(P(0), 4567); BcJunction.Grant(P(0), "discordant"); Act(P(0), LivingEnemy(), AttackAbility(), AttackCmd); }, b =>
            {
                var l = Mine(b, P(0), AttackAbility()).FirstOrDefault();
                if (l == null) return null;
                var t = l.Act.Targets.FirstOrDefault();
                int lv = BcJunctionStats.Level(t), raw = BcJunctionStats.RawLevel(t), hpDigit = (l.Units.FirstOrDefault(x => x.Unit.Pointer == P(0).Pointer)?.HpBefore ?? 4567) % 10;
                return lv == BcJunctionMath.Discordant(raw, hpDigit) ? $"ok: level {raw} -> {lv}" : $"FAILED: level {raw} -> {lv} (HP digit {hpDigit})";
            });
            // Sunken State: a physical hit makes the holder cast Vanish on itself
            Add("sunken_state", b => { Ready(); BcJunction.Grant(P(1), "sunken_state"); Act(LivingEnemy(), P(1), AttackAbility(), AttackCmd); }, b =>
            {
                bool vanish = BcJunction.HasStatus(P(1), ConditionType.Vanish) || BcJunction.HasStatus(P(1), ConditionType.Transparent);
                if (!vanish && Now - b < 15) return null;
                BattlePlugManager.Instance()?.BattleConditionController?.InterruptRemoveCondition(P(1), ConditionType.Vanish);
                return vanish ? "ok: the hit made it vanish" : "FAILED: no Vanish";
            });
            // Resonate: an attack trades the statuses the two don't share (here the holder's Haste goes to the target)
            Add("resonate", b =>
            {
                Ready();
                BattlePlugManager.Instance()?.BattleConditionController?.InterruptAddCondition(P(0), ConditionType.Heist);
                BcJunction.Grant(P(0), "resonate");
                Act(P(0), LivingEnemy(), AttackAbility(), AttackCmd);
            }, b =>
            {
                var l = Since(b, P(0)).FirstOrDefault();
                if (l == null) return null;
                var t = l.Act.Targets.FirstOrDefault();
                bool moved = t != null && BcJunction.HasStatus(t, ConditionType.Heist) && !BcJunction.HasStatus(P(0), ConditionType.Heist);
                return moved ? $"ok: Haste moved to {BcJunction.Who(t)} ({BcJunctionTriggers.Swaps} swaps)" : $"FAILED: {BcJunctionTriggers.Swaps} swaps";
            });
            // Freebie: of 12 Potions used, some aren't used up (25%)
            Add("freebie", b =>
            {
                Ready(); Stock("potion"); Stock("potion"); Stock("potion"); Stock("potion"); Stock("potion"); Stock("potion");
                BcJunction.Grant(P(0), "freebie");
                for (int i = 0; i < 12; i++) BcJunctionItems.UseItem(P(0), new[] { P(1) }, BcJunctionTriggers.Item("potion"), "test");
            }, b =>
            {
                if (Since(b, P(0)).Count(l => l.Act.Command?.Id == BcJunctionFormulas.ItemsCommand) < 12 && Now - b < 30) return null;
                return BcJunctionRewards.Freebies > 0 ? $"ok: {BcJunctionRewards.Freebies} Potions kept of 12" : "FAILED: no Potion kept in 12";
            });
        }

        internal static void Register5()
        {
            // Overheal: a Cure on an ally near max raises its HP past max
            Add("overheal", b => { Ready(); BcJunction.Grant(P(0), "overheal"); SetHp(P(1), Math.Max(1, MaxHp(P(1)) - 5)); Cast(P(0), P(1), Cure); }, b =>
            {
                var l = Mine(b, P(0), Cure).FirstOrDefault();
                if (l == null) return null;
                var t = On(l, P(1));
                int hp = Hp(P(1)), max = MaxHp(P(1));
                return hp > max ? $"ok: HP {t?.HpBefore} -> {hp} (max {max})" : $"FAILED: HP {hp}, max {max} ({BcJunctionExtra.Overheals} overheals)";
            });
            // Focus: Confusion on a holder doesn't take its menu away (the PR's act-picker swap is skipped)
            Add("focus", b =>
            {
                Ready();
                kept = BcJunctionControl.Kept;
                BcJunction.Grant(P(0), "focus");
                BattlePlugManager.Instance()?.BattleConditionController?.InterruptAddCondition(P(0), ConditionType.Confusion);
            }, b =>
            {
                if (BcJunctionControl.Kept == kept && Now - b < 5) return null;
                BattlePlugManager.Instance()?.BattleConditionController?.InterruptRemoveCondition(P(0), ConditionType.Confusion);
                return BcJunctionControl.Kept > kept ? "ok: Confused, the holder kept its menu" : "FAILED: the act-picker swap wasn't seen";
            });
            // Caller: a holder that has summoned may summon again
            Tests.Add(new T
            {
                Name = "caller", Timeout = 5,
                Check = () =>
                {
                    Begin();
                    var bm = BattlePlugManager.Instance();
                    int id = P(0)?.GetOwnedCharacterData()?.characterStatusId ?? 0;
                    bm.MemorizeUsedMagicStoneAbility(id);
                    bool before = bm.IsUsedMagicStoneAbilityInBattle(id);
                    BcJunction.Grant(P(0), "caller");
                    bool after = bm.IsUsedMagicStoneAbilityInBattle(id);
                    End();
                    return before && !after ? "ok: summoned once, may summon again" : $"FAILED: used {before} -> {after}";
                },
            });
            // Gaia: the battlefield's dance (the PR's learning table by the battle's background) and its element
            Tests.Add(new T
            {
                Name = "gaia_field", Timeout = 5,
                Check = () =>
                {
                    int d = BcJunctionExtra.Dance(), bit = BcJunctionExtra.GaiaElementBit();
                    return d >= 0 ? $"ok: dance {d}, element {BcJunctionDamage.ElementKey[bit]}" : "FAILED: no dance for this battle's background";
                },
            });
        }

        internal static void Register3()
        {
            // Auto-Potion: hurt, the holder drinks a Potion (one from the inventory)
            Add("auto_potion", b => { Ready(); Stock("potion"); BcJunction.Grant(P(1), "auto_potion"); SetHp(P(1), 3000); Act(LivingEnemy(), P(1), AttackAbility(), AttackCmd); }, b =>
            {
                var drink = Since(b, P(1)).FirstOrDefault(l => l.Act.Command?.Id == BcJunctionFormulas.ItemsCommand);
                if (drink == null) return Now - b < 15 ? null : $"FAILED: no Potion ({BcJunctionItems.Used} item reactions)";
                var me = On(drink, P(1));
                return me != null && me.HpAfter > me.HpBefore ? $"ok: Potion: HP {me.HpBefore} -> {me.HpAfter}" : $"FAILED: Potion landed, HP {me?.HpBefore} -> {me?.HpAfter}";
            });
            // Auto-Down: an ally falls, the holder uses a Phoenix Down on it
            Add("auto_down", b =>
            {
                Ready(); Stock("fenix");
                BcJunction.Grant(P(0), "auto_down");
                SetHp(P(2) ?? P(1), 1);
                Act(LivingEnemy(), P(2) ?? P(1), AttackAbility(), AttackCmd);
            }, b =>
            {
                var t = P(2) ?? P(1);
                var use = Since(b, P(0)).FirstOrDefault(l => l.Act.Command?.Id == BcJunctionFormulas.ItemsCommand);
                if (use == null) return Now - b < 15 ? null : $"FAILED: no Phoenix Down (fell: {Since(b, LivingEnemy()).Any(l => On(l, t)?.Died == true)})";
                bool up = BcJunction.Alive(t);
                return up ? $"ok: {BcJunction.Who(t)} fell and was raised" : "FAILED: the Phoenix Down didn't raise";
            });
            // Immortal: the holder falls and rises as a Zombie
            Add("immortal", b =>
            {
                Ready();
                var u = P(3) ?? P(1);
                BcJunction.Grant(u, "immortal");
                SetHp(u, 1);
                Act(LivingEnemy(), u, AttackAbility(), AttackCmd);
            }, b =>
            {
                var u = P(3) ?? P(1);
                bool zombie = BcJunction.HasStatus(u, ConditionType.Zombie);
                if (!zombie && Now - b < 20) return null;
                var cc = BattlePlugManager.Instance()?.BattleConditionController;
                if (zombie) { cc?.InterruptRemoveCondition(u, ConditionType.Zombie); SetHp(u, 5000); }
                return zombie ? $"ok: {BcJunction.Who(u)} rose as a Zombie ({BcJunctionTriggers.DeathCasts} death casts)" : $"FAILED: no Zombie ({BcJunctionTriggers.DeathCasts} death casts; {BcJunctionTriggers.LastNote})";
            });
        }
        static int Gil() => Last.Management.UserDataManager.Instance()?.OwendGil ?? 0;
    }
}
