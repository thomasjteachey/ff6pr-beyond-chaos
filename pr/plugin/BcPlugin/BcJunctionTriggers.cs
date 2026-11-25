using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using HarmonyLib;
using Last.Battle;
using Last.Data.Master;
using Last.Defaine;
using Last.Systems;
using PrKit;
using Calc = BeyondChaos.PR.BcJunctionDamage.Calc;
using Kind = BeyondChaos.PR.BcJunctionDamage.Kind;

namespace BeyondChaos.PR
{
    // Junction effects that answer something happening in battle with an act or a change (BC's prehit_trigger,
    // hit_trigger, critical_trigger, death_trigger, status_trigger, damage_trigger's reactions, mp_switch, and
    // the junction commands $40-$45 they queue; spec pr/build/bc_junction/spec_A/B.json). An act BC queues
    // (its counter queue or the special-action queue) is here an interrupt act queued as the game queues acts
    // (BcJunctionActs.Queue); BC's free casts (no MP: the SOS spells, death casts, procs) have the caster's MP
    // topped up for the act and put back after.
    //   SOS (critical_*)   the first time in a battle a fighter is Near Fatal (checked after each act and at the
    //                      battle's start): each SOS effect it has fires once: a free self-cast (Haste, Berserk,
    //                      Float, Vanish, Teleport, Quick, Curaga, Esuna, Regen, Reraise, Golem, Fenrir, Mysidian
    //                      Rabbit, Cold Dust (Freeze), Escape) or a command (Runic, Gil Toss, its esper's summon,
    //                      Jump, Defend, Dance, Trance)
    //   before an act lands, per target on the other side (not a Decisive attacker's act):
    //     Flinch (attacker, 50%): the target's gauge to a quarter;  Counter All (target, 25%): Attack back;
    //     Discordant (attacker): the target's level ends in the attacker's HP's last digit;
    //     Return Magic (target): a spell with an MP cost cast back at the attacker (a character needs the MP);
    //     Esper Counter (target): a spell of its esper (learn rate / 64) at the attacker, free;
    //     Sunken State (target): a physical hit makes it cast Vanish on itself, free;
    //     Hamedo (target, 50%): an Attack misses and it attacks back;  Resonate (either): statuses swapped
    //   on the hit: Null Freeze / Null Sleep (a frozen / sleeping holder can't be hit), Astral (HP <-> MP),
    //     Vorpal (physical ignores defense), MP Switch (target, 50%: non-lethal HP damage becomes MP damage),
    //     Ravenous (drains x1.25)
    //   after it lands: Vampire (the attacker drains what it dealt), Esper Magic (a spell of the attacker's esper
    //     follows, learn rate / 64), Meatbone Cut (a target at 1/8 HP or less, hurt, answers with Revenge),
    //     Corrosive (the attacker's damage lowers the target's max HP by a quarter of it), Juggler, Damage Split
    //     (a quarter of a non-lethal hit goes back to the attacker), Distribute (healing past max HP goes to the
    //     holder's allies), death casts (Immortal: Choke Smoke on itself; Final Spiral: Spiraler; Final Summon:
    //     its esper; Final Ripple: Rippler at the killer), Firestarter (an ally frozen: Fire on the side)
    static class BcJunctionTriggers
    {
        internal static int Sos, Counters, Procs, DeathCasts, Swaps, Drains, Flinches;
        internal static int CounterOffers, CounterRolls, CounterReady, CounterEffect;
        internal static string LastNote = "";
        static readonly HashSet<IntPtr> sosDone = new HashSet<IntPtr>();
        static readonly Dictionary<IntPtr, (BattleUnitData Who, int Mp)> freeActs = new Dictionary<IntPtr, (BattleUnitData, int)>();
        static readonly HashSet<IntPtr> hamedoMiss = new HashSet<IntPtr>();   // targets whose Hamedo dodged the act landing now
        static bool decisive;

        internal static void Register(Harmony h)
        {
            BcJunctionActs.Before.Add(("free-mp", FreeBefore));
            BcJunctionActs.Before.Add(("prehit", PreHit));
            BcJunctionDamage.Rules.Add(("hit", OnHit));
            BcJunctionActs.After.Add(("free-mp", FreeAfter));
            BcJunctionActs.After.Add(("after", AfterAct));
            BcJunctionActs.After.Add(("sos", (act, units) => CheckSos()));
        }

        internal static void BattleStart()
        {
            sosDone.Clear();
            freeActs.Clear();
        }

        static bool Has(BattleUnitData u, string key) => BcJunction.Used(key) && BcJunction.Has(u, key);

        // --- the seed's spells and items (tools/bc_junction.py triggers) ------------------------------------------

        static int stamp = -1;
        static readonly Dictionary<string, int> spells = new Dictionary<string, int>(), items = new Dictionary<string, int>();

        internal static int Spell(string name)
        {
            BcBattleData.Refresh();
            if (stamp != BcBattleData.Stamp)
            {
                stamp = BcBattleData.Stamp;
                spells.Clear(); items.Clear();
                var j = BcBattleData.Section("junction");
                foreach (var (key, into) in new[] { ("spells", spells), ("items", items) })
                    if (j.ValueKind == JsonValueKind.Object && j.TryGetProperty(key, out var m) && m.ValueKind == JsonValueKind.Object)
                        foreach (var p in m.EnumerateObject())
                            if (p.Value.ValueKind == JsonValueKind.Number) into[p.Name] = p.Value.GetInt32();
            }
            return spells.TryGetValue(name, out int id) ? id : 0;
        }

        internal static int Item(string name) { Spell(""); return items.TryGetValue(name, out int id) ? id : 0; }

        // --- queueing -------------------------------------------------------------------------------------

        // an act of a junction effect; free: no MP (topped up for the act, put back after)
        internal static BattleActData Cast(BattleUnitData who, BattleUnitData target, int ability, bool free, string why, int command = 0, bool counter = true)
        {
            if (who == null || target == null || ability <= 0) return null;
            var act = BcJunctionActs.Queue(who, new[] { target }, ability, command, counter: counter);
            if (act == null) return null;
            if (free) freeActs[act.Pointer] = (who, -1);
            LastNote = $"{why}: {BcJunction.Who(who)} -> ability {ability} at {BcJunction.Who(target)}";
            Hooks.NoteOnce("bc-junction-cast-" + why, () => $"{BcJunction.Tag} first {LastNote}");
            return act;
        }

        static void FreeBefore(BcJunctionActs.Act act)
        {
            if (!freeActs.TryGetValue(act.Data.Pointer, out var f)) return;
            var p = f.Who?.BattleUnitDataInfo?.Parameter;
            if (p == null) return;
            freeActs[act.Data.Pointer] = (f.Who, p.CurrentMP);
            int cost = act.Ability?.UseValue ?? 0;
            if (p.CurrentMP < cost) p.CurrentMP = cost;
        }

        static void FreeAfter(BcJunctionActs.Act act, List<BcJunctionActs.Landed> units)
        {
            if (!freeActs.TryGetValue(act.Data.Pointer, out var f)) return;
            freeActs.Remove(act.Data.Pointer);
            var p = f.Who?.BattleUnitDataInfo?.Parameter;
            if (p != null && f.Mp >= 0) p.CurrentMP = f.Mp;
        }

        // --- SOS ------------------------------------------------------------------------------------------

        static readonly (string Key, string Spell)[] SosSpells =
        {
            ("critical_haste", "haste"), ("critical_bserk", "bserk"), ("critical_float", "float"), ("critical_vanish", "vanish"),
            ("critical_warp", "warp"), ("critical_quick", "quick"), ("critical_cure3", "cure3"), ("critical_remedy", "remedy"),
            ("critical_regen", "regen"), ("critical_life3", "life3"), ("critical_golem", "golem"), ("critical_fenrir", "fenrir"),
            ("critical_rabbit", "lagomorph"), ("critical_freeze", "colddust"),
        };
        // the SOS commands, by PR command id (the command row's own ability); the esper's summon apart
        static readonly (string Key, int Command)[] SosCommands =
        {
            ("critical_runic", 16), ("critical_gprain", 21), ("critical_jump", 30), ("critical_defend", 2),
            ("critical_morph", 8), ("critical_dance", 22),
        };

        internal static void CheckSos()
        {
            if (!BcJunction.InUse.Any(k => k.StartsWith("critical_")) && !BcJunction.Testing) return;
            foreach (var u in BcJunction.Party().Concat(BcJunction.Enemies()).ToList())
            {
                if (sosDone.Contains(u.Pointer) || !BcJunction.Alive(u) || !BcJunction.HasStatus(u, ConditionType.Dying)) continue;
                var fx = BcJunction.Effects(u).Where(k => k.StartsWith("critical_")).ToList();
                if (fx.Count == 0) continue;
                sosDone.Add(u.Pointer);
                Fire(u);
            }
        }

        // the holder's SOS effects (the self-tests call it)
        internal static int Fire(BattleUnitData u)
        {
            int n = 0;
            foreach (var (key, spell) in SosSpells)
                if (Has(u, key) && Cast(u, u, Spell(spell), true, "SOS " + spell) != null) n++;
            foreach (var (key, cmd) in SosCommands)
            {
                if (!Has(u, key)) continue;
                var row = MasterManager.Instance.GetData<Command>(cmd);
                if (row == null || row.AbilityId <= 0) continue;
                var target = cmd == 2 || cmd == 16 || cmd == 8 ? u : LastAttacker(u) ?? Foe(u);
                if (target != null && Cast(u, target, row.AbilityId, true, "SOS command " + cmd, cmd) != null) n++;
            }
            if (Has(u, "critical_esper"))
            {
                int summon = SummonOf(u);
                var target = Foe(u);
                if (summon > 0 && target != null && Cast(u, target, summon, true, "SOS Summon") != null) n++;
            }
            if (Has(u, "critical_escape") && Cast(u, u, Spell("escape"), true, "SOS Escape") != null) n++;
            Sos += n;
            return n;
        }

        // a character's equipped esper's summon; a monster's: a random esper's (BC: random 0..26)
        internal static int SummonOf(BattleUnitData u)
        {
            var oc = u?.GetOwnedCharacterData();
            if (oc != null)
                return oc.MagicStoneId > 0 ? BcJunctionField.EsperInfo(oc.MagicStoneId)?.Summon ?? 0 : 0;
            return BcJunctionFormulas.SummonOf[BcJunction.Rng.Next(BcJunctionFormulas.SummonOf.Length)];
        }

        static readonly Dictionary<IntPtr, BattleUnitData> lastHit = new Dictionary<IntPtr, BattleUnitData>();
        static BattleUnitData LastAttacker(BattleUnitData u) => lastHit.TryGetValue(u.Pointer, out var a) && BcJunction.Alive(a) ? a : null;

        static BattleUnitData Foe(BattleUnitData u)
        {
            var foes = (BcJunction.IsPlayer(u) ? BcJunction.Enemies() : BcJunction.Party()).Where(BcJunction.Alive).ToList();
            return foes.Count == 0 ? null : foes[BcJunction.Rng.Next(foes.Count)];
        }

        static bool CanAct(BattleUnitData u) =>
            BcJunction.Alive(u) && !new[] { ConditionType.Zombie, ConditionType.Bersak, ConditionType.Confusion, ConditionType.Sleep,
                ConditionType.Stop, ConditionType.Freeze, ConditionType.Mineralization }.Any(c => BcJunction.HasStatus(u, c));

        static bool Physical(BcJunctionActs.Act act) =>
            act.Command?.Id == BcJunctionEffects.AttackCommand || act.Command?.Id == BcJunctionEffects.MugCommand || act.Command?.Id == 30 ||
            (act.Ability?.TypeId ?? 0) == 4;

        // --- before an act lands ----------------------------------------------------------------------------

        static void PreHit(BcJunctionActs.Act act)
        {
            hamedoMiss.Clear();
            var a = act.Attacker;
            if (a == null) return;
            decisive = Has(a, "decisive");
            foreach (var t in act.Targets.ToList())
            {
                if (t == null || t.Pointer == a.Pointer) continue;
                lastHit[t.Pointer] = a;
                bool foes = !BcJunction.SameSide(a, t);
                if (Has(a, "resonate") || Has(t, "resonate")) Resonate(a, t);
                if (decisive) continue;
                if (foes && BcJunction.Rng.Next(2) == 0 && Has(a, "flinch"))
                {
                    float g = BcJunctionStart.Gauge(t);
                    if (g >= 4) { BcJunctionStart.Atb()?.ChangeATBGaugeByUnitData(t, g / 4); Flinches++; }
                }
                if (foes)
                {
                    CounterOffers++;
                    if (BcJunction.Rng.Next(4) == 0)
                    {
                        CounterRolls++;
                        if (CanAct(t))
                        {
                            CounterReady++;
                            if (Has(t, "counter_all"))
                            {
                                CounterEffect++;
                                if (Cast(t, a, BcJunctionTests.AttackAbility(), false, "Counter All", BcJunctionEffects.AttackCommand) != null) Counters++;
                            }
                        }
                    }
                }
                if (Has(a, "discordant"))
                {
                    int hp = a.BattleUnitDataInfo?.Parameter?.CurrentHP ?? 0;
                    BcJunctionStats.SetLevel(t, BcJunctionMath.Discordant(BcJunctionStats.Level(t), hp));
                }
                int cost = act.Ability?.UseValue ?? 0;
                if (cost > 0 && !act.Ours && (!act.Counter || act.Test) && Has(t, "return_magic"))
                {
                    bool character = BcJunction.IsPlayer(t);
                    if (!character || (t.BattleUnitDataInfo?.Parameter?.CurrentMP ?? 0) >= cost)
                        if (Cast(t, a, act.Ability.Id, false, "Return Magic", 7) != null) Counters++;
                }
                if (BcJunction.IsPlayer(t) && Has(t, "esper_counter"))
                {
                    int sp = EsperSpell(t, !BcJunction.IsPlayer(a));
                    if (sp > 0 && Cast(t, a, sp, true, "Esper Counter") != null) Counters++;
                }
                if (Physical(act) && !BcJunction.HasStatus(t, ConditionType.Vanish) && Has(t, "sunken_state"))
                    Cast(t, t, Spell("vanish"), true, "Sunken State");
                if (Physical(act) && act.Command?.Id == BcJunctionEffects.AttackCommand && BcJunction.Rng.Next(2) == 0 && Has(t, "hamedo"))
                {
                    hamedoMiss.Add(t.Pointer);
                    if (CanAct(t) && Cast(t, a, BcJunctionTests.AttackAbility(), false, "Hamedo", BcJunctionEffects.AttackCommand) != null) Counters++;
                }
            }
        }

        // Resonate: the statuses the two don't share change hands (BC's masks: no Magitek, Petrify, Wound, Near Fatal)
        static readonly ConditionType[] Swappable =
        {
            ConditionType.Blind, ConditionType.Zombie, ConditionType.Poison, ConditionType.Vanish, ConditionType.Kappa, ConditionType.Doom,
            ConditionType.Blink, ConditionType.Silence, ConditionType.Bersak, ConditionType.Confusion, ConditionType.Slip, ConditionType.Sleep,
            ConditionType.Regeneration, ConditionType.Slow, ConditionType.Heist, ConditionType.Stop, ConditionType.Shell, ConditionType.Protect,
            ConditionType.Reflex, ConditionType.Reraise, ConditionType.Leviteto,
        };

        static void Resonate(BattleUnitData a, BattleUnitData t)
        {
            var cc = BattlePlugManager.Instance()?.BattleConditionController;
            if (cc == null) return;
            foreach (var c in Swappable)
            {
                bool ha = BcJunction.HasStatus(a, c), ht = BcJunction.HasStatus(t, c);
                if (ha == ht) continue;
                var from = ha ? a : t;
                var to = ha ? t : a;
                cc.InterruptRemoveCondition(from, c);
                cc.InterruptAddCondition(to, c);
                Swaps++;
            }
        }

        // a spell of the holder's equipped esper (BC: r = rand(0..63); slots 5..1, the matching class only, the
        // first whose learn rate takes r below 0); foe: an enemy-type spell; 0: none
        internal static int EsperSpell(BattleUnitData u, bool foe)
        {
            var oc = u?.GetOwnedCharacterData();
            var e = oc != null && oc.MagicStoneId > 0 ? BcJunctionField.EsperInfo(oc.MagicStoneId) : null;
            if (e == null || e.Spells.Count == 0) return 0;
            return BcJunctionMath.EsperSpell(e.Spells, foe, BcJunction.Rng.Next(64));
        }

        // --- on the hit (the damage hook) ---------------------------------------------------------------------

        static void OnHit(Calc c)
        {
            var a = c.Attacker;
            var t = c.Target;
            if (a == null || t == null) return;
            if (BcJunction.HasStatus(t, ConditionType.Freeze) && Has(t, "null_freeze")) { c.ForceMiss("null_freeze"); return; }
            if (BcJunction.HasStatus(t, ConditionType.Sleep) && Has(t, "null_sleep")) { c.ForceMiss("null_sleep"); return; }
            if (hamedoMiss.Contains(t.Pointer) && c.Physical) { c.ForceMiss("hamedo"); return; }
            var hit = c.HitAfter ?? c.Hit;
            if (Has(a, "astral"))
            {
                c.HitAfter = hit == HitType.Hit || hit == HitType.Critical ? HitType.MPHit : hit == HitType.MPHit ? HitType.Hit
                           : hit == HitType.Recovery ? HitType.MPRecovery : hit == HitType.MPRecovery ? HitType.Recovery : (HitType?)null;
                if (c.HitAfter.HasValue) c.Fired.Add("astral");
                hit = c.HitAfter ?? hit;
            }
            if (c.Physical && (hit == HitType.Hit || hit == HitType.Critical) && Has(a, "vorpal"))
            {
                // ignore defense: the game's x(255 - Def)/256 + 1 and Protect's x170/256 undone
                int def = t.BattleUnitDataInfo?.Parameter?.ConfirmedDefense() ?? 0;
                bool protect = BcJunction.HasStatus(t, ConditionType.Protect) || BcJunction.HasStatus(t, ConditionType.Proteus);
                c.Scale("vorpal", BcJunctionMath.Vorpal(def, protect));
            }
            if ((hit == HitType.HpAbs || hit == HitType.MpAbs) && Has(a, "ravenous")) c.Scale("ravenous", 1.25);
            if ((hit == HitType.Hit || hit == HitType.Critical) && a.Pointer != t.Pointer && Has(t, "mp_switch") &&
                !Has(t, "blood_mage") && !Has(t, "gold_mage"))
            {
                var p = t.BattleUnitDataInfo?.Parameter;
                int dealt = (int)Math.Floor(c.Value * c.Factor);
                if (p != null && p.CurrentMP > 0 && dealt > 0 && dealt < p.CurrentHP && BcJunction.Rng.Next(2) == 0)
                {
                    c.HitAfter = HitType.MPHit;
                    c.Fired.Add("mp_switch");
                }
            }
        }

        // --- after an act lands ---------------------------------------------------------------------------

        static void AfterAct(BcJunctionActs.Act act, List<BcJunctionActs.Landed> units)
        {
            var a = act.Attacker;
            if (a == null) return;
            var landed = units.Where(l => l.Targeted).ToList();
            int dealt = landed.Where(l => l.Unit.Pointer != a.Pointer).Sum(l => Math.Min(l.Damage, l.HpBefore));
            // Vampire: the attacker drains what it dealt (Ravenous: no cap at its missing HP)
            if (dealt > 0 && Has(a, "vampire"))
            {
                var p = a.BattleUnitDataInfo?.Parameter;
                if (p != null && BcJunction.Alive(a))
                {
                    int max = p.ConfirmedMaxHp();
                    int heal = BcJunctionMath.VampireHeal(dealt, p.CurrentHP, max, Has(a, "ravenous"));
                    p.CurrentHP = Math.Min(max, p.CurrentHP + heal);
                    Drains++;
                }
            }
            // Esper Magic: a spell of the attacker's esper follows (not after its own procs and free casts)
            if (!act.Ours && BcJunction.IsPlayer(a) && landed.Count > 0 && Has(a, "esper_magic"))
            {
                var target = landed[0].Unit;
                int sp = EsperSpell(a, !BcJunction.IsPlayer(target));
                if (sp > 0 && Cast(a, target, sp, true, "Esper Magic", counter: false) != null) Procs++;
            }
            foreach (var l in landed)
            {
                var t = l.Unit;
                // Meatbone Cut: already at 1/8 HP or less, hurt but alive, answers with Revenge
                if (!decisive && l.Damage > 0 && !l.Died && t.Pointer != a.Pointer && BcJunctionMath.MeatboneReady(l.HpBefore, l.MaxHp) &&
                    BcJunction.Alive(a) && Has(t, "meatbone_cut"))
                    if (Cast(t, a, Spell("revenge"), true, "Meatbone Cut") != null) Counters++;
                // Corrosive: a quarter of the damage off the target's max HP for the battle
                if (l.Damage > 0 && Has(a, "corrosive"))
                    BcJunctionStats.LowerMax(t, BcJunctionMath.CorrosiveLoss(l.Damage, l.HpBefore), 0);
                if ((l.Damage > 0 || l.Healed > 0) && Has(t, "juggler")) BcJunctionStats.Juggle(t, Physical(act));
                // Damage Split: a quarter of a non-lethal hit goes back to the attacker
                if (l.Damage > 0 && !l.Died && t.Pointer != a.Pointer && Has(t, "damage_split"))
                {
                    int q = BcJunctionMath.SplitShare(l.Damage, false);
                    var tp = t.BattleUnitDataInfo?.Parameter;
                    var ap = a.BattleUnitDataInfo?.Parameter;
                    if (q > 0 && tp != null && ap != null)
                    {
                        tp.CurrentHP = Math.Min(tp.ConfirmedMaxHp(), tp.CurrentHP + q);
                        ap.CurrentHP = Math.Max(BcJunction.Alive(a) ? 1 : 0, ap.CurrentHP - q);
                    }
                }
                // Distribute: healing past the holder's max goes to its living allies, shared out
                if (l.Healed > 0 && Has(t, "distribute"))
                {
                    var res = l.Result;
                    int healAmount = res != null ? res.GetValue(false) : l.Healed;
                    var allies = (BcJunction.IsPlayer(t) ? BcJunction.Party() : BcJunction.Enemies()).Where(u => u.Pointer != t.Pointer && BcJunction.Alive(u)).ToList();
                    int share = BcJunctionMath.DistributeShare(healAmount, l.HpBefore, l.MaxHp, allies.Count);
                    if (share > 0)
                        foreach (var u in allies)
                        {
                            var p = u.BattleUnitDataInfo.Parameter;
                            p.CurrentHP = Math.Min(p.ConfirmedMaxHp(), p.CurrentHP + share);
                        }
                }
                // death casts (not from a Decisive attacker)
                if (l.Died && !decisive) DeathCasts += Death(t, a);
                // Final Fenix: its Reraise spent, Phoenix revives its side
                if (l.Lost(ConditionType.Reraise) && BcJunction.Alive(t) && Has(t, "final_fenix") &&
                    Cast(t, t, Spell("phoenix"), true, "Final Fenix") != null) DeathCasts++;
                // Firestarter: an ally frozen: Fire on the holder's side
                if (l.Gained(ConditionType.Freeze))
                    foreach (var f in (BcJunction.IsPlayer(t) ? BcJunction.Party() : BcJunction.Enemies()).Where(u => u.Pointer != t.Pointer && CanAct(u)).ToList())
                        if (Has(f, "firestarter")) Cast(f, t, Spell("fire"), true, "Firestarter");
            }
        }

        // a fighter's death casts (the self-tests call it)
        internal static int Death(BattleUnitData dead, BattleUnitData killer)
        {
            int n = 0;
            if (Has(dead, "immortal"))
            {
                // PR drops queued actions from a fallen caster. Choke Smoke's BC outcome is
                // revival as a Zombie; apply it at the death trigger instead.
                var p = dead.BattleUnitDataInfo?.Parameter;
                var cc = BattlePlugManager.Instance()?.BattleConditionController;
                if (p != null && cc != null)
                {
                    p.CurrentHP = Math.Max(1, p.CurrentHP);
                    cc.InterruptRemoveCondition(dead, ConditionType.UnableFight);
                    cc.InterruptAddCondition(dead, ConditionType.Zombie);
                    LastNote = $"Immortal: {BcJunction.Who(dead)} rose as a Zombie";
                    n++;
                }
            }
            if (Has(dead, "final_spiral") && Cast(dead, dead, Spell("spiraler"), true, "Final Spiral") != null) n++;
            if (Has(dead, "final_esper"))
            {
                int summon = SummonOf(dead);
                var target = Foe(dead);
                if (summon > 0 && target != null && Cast(dead, target, summon, true, "Final Summon") != null) n++;
            }
            if (Has(dead, "final_ripple") && killer != null && killer.Pointer != dead.Pointer && BcJunction.Alive(killer) &&
                Cast(dead, killer, Spell("rippler"), true, "Final Ripple") != null) n++;
            return n;
        }
    }
}
