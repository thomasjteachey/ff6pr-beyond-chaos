using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Battle;
using Last.Data.Master;
using Last.Data.User;
using Last.Defaine;
using Last.Management;
using PrKit;

namespace BeyondChaos.PR
{
    // Junction effects that use items by themselves (BC's damage_trigger Auto-Potion and status_trigger
    // Auto-Down / Auto-Revivify / Auto-Remedy; spec_A/B.json). The act is the PR's own item act (BattleActData
    // with the Items command and the item), queued as an interrupt; a party member's uses one from the
    // inventory (exactly one: if the game takes one too, it's given back), a monster's costs nothing.
    //   Auto-Potion   the holder, hurt (not fatally, not by a status tick, not by its own reaction), drinks a
    //                 Potion (the SNES's; a monster: half the time); with Salve, on all its allies
    //   Auto-Down     an ally falls: each holder that can act uses a Phoenix Down on it
    //   Auto-Revivify an ally turns Zombie: Holy Water
    //   Auto-Remedy   an ally takes Blind, Poison, Imp, Petrify, Silence or Sap: the item for it (Remedy for
    //                 several) (a monster's ally: half the time)
    static class BcJunctionItems
    {
        internal static int Used;
        static readonly Dictionary<IntPtr, (int Content, int Before)> pending = new Dictionary<IntPtr, (int, int)>();

        internal static void Register(Harmony h)
        {
            BcJunctionActs.After.Add(("items", After));
            BcJunctionActs.After.Add(("items-count", Count));
        }

        static bool Has(BattleUnitData u, string key) => BcJunction.Used(key) && BcJunction.Has(u, key);

        static int Owned(int content)
        {
            try
            {
                var list = UserDataManager.Instance()?.normalOwnedItems;
                if (list == null) return 0;
                foreach (var kv in list) if (kv.Value != null && kv.Value.ContentId == content) return kv.Value.Count;
            }
            catch { }
            return 0;
        }

        // the item act (the self-tests call it)
        internal static BattleActData UseItem(BattleUnitData who, IList<BattleUnitData> targets, int content, string why)
        {
            if (who == null || targets == null || targets.Count == 0 || content <= 0) return null;
            bool party = BcJunction.IsPlayer(who);
            int before = Owned(content);
            if (party && before <= 0) return null;
            var bm = BattlePlugManager.Instance();
            var mm = MasterManager.Instance;
            var c = mm.GetData<Content>(content);
            var cmd = mm.GetData<Command>(BcJunctionFormulas.ItemsCommand);
            if (bm == null || c == null || cmd == null) return null;
            var item = new OwnedItemClient().CreateOwnedItem(c, 1);
            var items = new Il2CppSystem.Collections.Generic.List<OwnedItemData>();
            items.Add(item);
            var arr = new Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppReferenceArray<BattleUnitData>(targets.Count);
            for (int i = 0; i < targets.Count; i++) arr[i] = targets[i];
            var tt = targets.Count > 1 ? BattleActData.TargetType.AllMember : BattleActData.TargetType.SingleMember;
            var act = new BattleActData(who, arr, cmd, items, BattleActData.ActType.Interrupt, tt, BattleActData.ArmType.Right, false);
            act.isCounter = true;
            if (party)
            {
                new OwnedItemClient().RemoveOwnedItem(content, 1);
                pending[act.Pointer] = (content, before);
            }
            bm.BattleActExection.SetBattleActData(act);
            Used++;
            Kit.Info($"{BcJunction.Tag} {why}: {BcJunction.Who(who)} uses item {content} on {string.Join(", ", targets.Select(BcJunction.Who))}");
            return act;
        }

        // a party member's reaction uses exactly one: if the game took one more, it goes back
        static void Count(BcJunctionActs.Act act, List<BcJunctionActs.Landed> units)
        {
            if (!pending.TryGetValue(act.Data.Pointer, out var p)) return;
            pending.Remove(act.Data.Pointer);
            int now = Owned(p.Content);
            if (now < p.Before - 1) new OwnedItemClient().AddOwnedItem(p.Content, p.Before - 1 - now);
        }

        static bool CanAct(BattleUnitData u) =>
            BcJunction.Alive(u) && !new[] { ConditionType.Zombie, ConditionType.Bersak, ConditionType.Confusion, ConditionType.Sleep,
                ConditionType.Stop, ConditionType.Freeze, ConditionType.Mineralization }.Any(c => BcJunction.HasStatus(u, c));

        static readonly (ConditionType Status, string Item)[] Cures =
        {
            (ConditionType.Poison, "antidote"), (ConditionType.Blind, "eyedrop"), (ConditionType.Mineralization, "soft"),
            (ConditionType.Silence, "echoscreen"), (ConditionType.Mute, "echoscreen"), (ConditionType.Kappa, "greencherry"),
        };
        static readonly ConditionType[] Ailments =
            { ConditionType.Blind, ConditionType.Poison, ConditionType.Kappa, ConditionType.Mineralization, ConditionType.Silence, ConditionType.Mute, ConditionType.Slip };

        static void After(BcJunctionActs.Act act, List<BcJunctionActs.Landed> units)
        {
            bool reaction = act.Command?.Id == BcJunctionFormulas.ItemsCommand && act.Counter;
            foreach (var l in units)
            {
                var t = l.Unit;
                // Auto-Potion
                if (!reaction && l.Damage > 0 && !l.Died && Has(t, "auto_potion") && (BcJunction.IsPlayer(t) || BcJunction.Rng.Next(2) == 0))
                {
                    var on = Has(t, "salve") ? (BcJunction.IsPlayer(t) ? BcJunction.Party() : BcJunction.Enemies()).Where(BcJunction.Alive).ToList()
                                             : new List<BattleUnitData> { t };
                    UseItem(t, on, BcJunctionTriggers.Item("potion"), "Auto-Potion");
                }
                // Auto-Down / Auto-Revivify / Auto-Remedy: one category a change (Wound first)
                string key = null, item = null;
                if (l.Gained(ConditionType.UnableFight)) { key = "auto_down"; item = "fenix"; }
                else if (l.Gained(ConditionType.Zombie)) { key = "auto_revivify"; item = "holywater"; }
                else
                {
                    var got = Ailments.Where(l.Gained).ToList();
                    if (got.Count > 0)
                    {
                        key = "auto_remedy";
                        var single = Cures.Where(c => got.Contains(c.Status)).Select(c => c.Item).Distinct().ToList();
                        item = single.Count == 1 && got.All(g => Cures.Any(c => c.Status == g && c.Item == single[0])) ? single[0] : "remedy";
                    }
                }
                if (key == null || !BcJunction.Used(key)) continue;
                if (!BcJunction.IsPlayer(t) && BcJunction.Rng.Next(2) != 0) continue;
                foreach (var x in (BcJunction.IsPlayer(t) ? BcJunction.Party() : BcJunction.Enemies()).ToList())
                {
                    if ((x.Pointer != t.Pointer && !CanAct(x)) || !BcJunction.Has(x, key)) continue;
                    int content = BcJunctionTriggers.Item(item);
                    if (BcJunction.IsPlayer(x) && Owned(content) <= 0 && item != "remedy") content = BcJunctionTriggers.Item("remedy");
                    UseItem(x, new[] { t }, content, key);
                }
            }
        }
    }
}
