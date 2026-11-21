using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Battle;
using Last.Data;
using Last.Data.User;
using Last.Defaine;
using Last.Management;
using Last.Systems;
using PrKit;

namespace BeyondChaos.PR
{
    // Junction effects that give or keep things (BC's patch_junction_poach, freebie, gilgam_heart, victory_cry,
    // double_ap, vip, the Catch part of damage_trigger; spec pr/build/bc_junction/spec_A.json, spec_C.json):
    //   Poach        a monster the holder kills with Attack drops an item at once: 50% its steal pair, 50% its
    //                drop pair; the rare one 12.5% (32/256), else the common one (an empty slot: nothing)
    //   Imp Harvest  the same on an Imp monster, always the rare one (else Poach)
    //   Freebie      25% an item the holder uses (or throws) isn't used up
    //   Catch        a thrown weapon does the holder no harm; half the time a party holder catches one
    //   Gilgam Heart the party gets 1 gil for each HP the holder loses (and lives); a monster holder pays too
    //   Victory Cry  a living holder at a won battle's end: HP and MP full, ailments but Vanish and Imp cured
    //   Double AP    a won battle's AP x2 for the holder (at most 255)
    //   VIP          the holder falling (no Reraise to save it) ends the battle as a loss, as Banon's does
    static class BcJunctionRewards
    {
        internal static int Poached, Freebies, CaughtItems, GilGiven, Cries, ApDoubled, VipLosses;
        internal static string LastNote = "";
        const int MaxGil = 9999999;

        internal static void Register(Harmony h)
        {
            BcJunctionActs.After.Add(("rewards", AfterAct));
            Hooks.Patch(h, typeof(BattleResultProvider), "Genelate", typeof(BcJunctionRewards), prefix: nameof(Result_Prefix), postfix: nameof(Result_Postfix));
        }

        static bool Has(BattleUnitData u, string key) => BcJunction.Used(key) && BcJunction.Has(u, key);

        static void Give(int contentId, string why)
        {
            if (contentId <= 0) return;
            new OwnedItemClient().AddOwnedItem(contentId, 1);
            LastNote = $"{why}: item {contentId}";
            Hooks.NoteOnce("bc-junction-give-" + why, () => $"{BcJunction.Tag} {LastNote}");
        }

        internal static void Catch(BattleUnitData holder, OwnedItemData thrown)
        {
            if (thrown == null) return;
            CaughtItems++;
            Give(thrown.ContentId, $"{BcJunction.Who(holder)} caught a thrown weapon");
        }

        static void AfterAct(BcJunctionActs.Act act, List<BcJunctionActs.Landed> units)
        {
            var a = act.Attacker;
            int cmd = act.Command?.Id ?? 0;
            // Poach / Imp Harvest: a monster killed by the holder's Attack
            if (a != null && BcJunction.IsPlayer(a) && cmd == BcJunctionEffects.AttackCommand && (BcJunction.Used("poach") || BcJunction.Used("imp_harvest")))
                foreach (var l in units.Where(l => l.Targeted && l.Died && !BcJunction.IsPlayer(l.Unit)))
                {
                    var m = l.Unit.GetMonster();
                    if (m == null) continue;
                    bool imp = l.Before.Contains(ConditionType.Kappa) && Has(a, "imp_harvest");
                    if (!imp && !Has(a, "poach")) continue;
                    int item = BcJunctionMath.PoachItem(m.StealContentId2, m.StealContentId1, m.DropContentId2, m.DropContentId1, imp,
                                                        BcJunction.Rng.Next(2), BcJunction.Rng.Next(256));
                    if (item <= 0) continue;
                    Poached++;
                    Give(item, $"{BcJunction.Who(a)} {(imp ? "harvested" : "poached")} from monster {m.Id}");
                }
            // Freebie: 25% the item isn't used up (put back)
            if (a != null && (cmd == BcJunctionFormulas.ItemsCommand || cmd == BcJunctionFormulas.ThrowCommand) && !act.Ours &&
                BcJunction.Rng.Next(4) == 0 && Has(a, "freebie"))
            {
                var items = act.Data.itemList;
                var item = items != null && items.Count > 0 ? items[0] : null;
                if (item != null)
                {
                    Freebies++;
                    Give(item.ContentId, $"{BcJunction.Who(a)}'s Freebie");
                }
            }
            foreach (var l in units)
            {
                // Gilgam Heart: gil for the HP lost (the holder lives)
                if (l.Damage > 0 && l.HpAfter > 0 && Has(l.Unit, "gilgam_heart"))
                {
                    var udm = UserDataManager.Instance();
                    int now = udm?.OwendGil ?? 0;
                    int add = BcJunctionMath.GilgamPay(l.Damage, now);
                    if (add > 0)
                    {
                        new OwnedItemClient().AddGil(add);
                        GilGiven += add;
                        Hooks.NoteOnce("bc-junction-gilgam", () => $"{BcJunction.Tag} Gilgam Heart: {BcJunction.Who(l.Unit)} lost {l.Damage} HP: +{add} gil");
                    }
                }
                // VIP: a party holder falls with no Reraise to raise it
                if (l.Died && BcJunction.IsPlayer(l.Unit) && !l.After.Contains(ConditionType.Reraise) && Has(l.Unit, "vip"))
                    Lose(l.Unit);
            }
        }

        // the battle lost: every party member falls (the game's own defeat follows)
        static void Lose(BattleUnitData vip)
        {
            VipLosses++;
            Kit.Info($"{BcJunction.Tag} VIP: {BcJunction.Who(vip)} fell: the battle is lost");
            var cc = BattlePlugManager.Instance()?.BattleConditionController;
            foreach (var p in BcJunction.Party().Where(BcJunction.Alive).ToList())
            {
                var par = p.BattleUnitDataInfo?.Parameter;
                if (par != null) par.CurrentHP = 0;
                cc?.InterruptAddCondition(p, ConditionType.UnableFight);
            }
        }

        // --- a won battle's end: Victory Cry, Double AP -----------------------------------------------------

        static readonly ConditionType[] Cured =
        {
            ConditionType.Blind, ConditionType.Zombie, ConditionType.Poison, ConditionType.Mineralization, ConditionType.Doom,
            ConditionType.DoomEx, ConditionType.Dying, ConditionType.Blink, ConditionType.Silence, ConditionType.Mute,
            ConditionType.Bersak, ConditionType.Confusion, ConditionType.Slip, ConditionType.Sleep,
        };

        public sealed class ResultState
        {
            public Dictionary<int, int> Ap = new Dictionary<int, int>();   // Double AP holders: character status id -> AP before
        }

        public static void Result_Prefix(BattleResultProvider __instance, out ResultState __state)
        {
            __state = null;
            if (!BcJunction.On || !Hooks.IsA<BattleResultProvider>(__instance)) return;
            try
            {
                var cc = BattlePlugManager.Instance()?.BattleConditionController;
                var st = new ResultState();
                foreach (var p in BcJunction.Party().Where(BcJunction.Alive))
                {
                    var oc = p.GetOwnedCharacterData();
                    if (oc == null) continue;
                    if (Has(p, "victory_cry"))
                    {
                        var bp = p.BattleUnitDataInfo?.Parameter;
                        foreach (var par in new CharacterParameterBase[] { bp, oc.Parameter })
                        {
                            if (par == null) continue;
                            par.CurrentHP = par.ConfirmedMaxHp();
                            par.CurrentMP = par.ConfirmedMaxMp();
                        }
                        foreach (var t in Cured)
                            if (BcJunction.HasStatus(p, t)) cc?.InterruptRemoveCondition(p, t);
                        Cries++;
                        Kit.Info($"{BcJunction.Tag} Victory Cry: {oc.Name} restored");
                    }
                    if (Has(p, "double_ap")) st.Ap[oc.characterStatusId] = oc.MagicLearningValue;
                }
                if (st.Ap.Count > 0) __state = st;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-result-prefix", e); }
        }

        public static void Result_Postfix(BattleResultData __result, ResultState __state)
        {
            if (__state == null || __result == null) return;
            try
            {
                int ap = Math.Max(__result.GetMp, __result.GetAbp);
                if (ap <= 0) return;
                int extra = BcJunctionMath.DoubleApExtra(ap);
                if (extra <= 0) return;
                var udm = UserDataManager.Instance();
                var owned = udm?.GetOwnedCharactersClone(false);
                if (owned == null) return;
                var client = new OwnedCharacterClient();
                foreach (var oc in owned)
                {
                    if (oc == null || !__state.Ap.ContainsKey(oc.characterStatusId)) continue;
                    oc.MagicLearningValue += extra;
                    client.SetOwnedCharacter(oc);
                    ApDoubled++;
                    Kit.Info($"{BcJunction.Tag} Double AP: {oc.Name} +{extra} AP ({ap} -> {ap + extra})");
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-result-postfix", e); }
        }
    }
}
