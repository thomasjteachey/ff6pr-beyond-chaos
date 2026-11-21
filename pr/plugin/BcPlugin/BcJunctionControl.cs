using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Battle;
using Last.Defaine;
using PrKit;

namespace BeyondChaos.PR
{
    // Junction effects on who controls a fighter and on its commands (BC's patch_junction_focus, caller,
    // unlimited, instant_run; the PR's hooks found by bc-junction's readers, 2026-11-20):
    //   Focus (party)        keeps the command menu while Confused, Berserk, dancing or raging; Commander gives it
    //                        to the other party members while the holder stands able. Lucid Dead (Zombie) and
    //                        Necromancer the same for Zombie. The PR gives a fighter under those statuses its own
    //                        act-picker (ActSelectBaseController.SetAct: ActSelectBersak, ActSelectConfusion,
    //                        FF6ActSelectConfusion, ActSelectDance, ActSelectRampage, ActSelectAutoCayenne,
    //                        ActSelectZombie); for a holder the swap doesn't happen, so the player keeps the menu
    //                        (the statuses' other effects stay). Decided when the status starts.
    //   Caller (character)   can summon its esper again in the same battle (BattlePlugManager.
    //                        IsUsedMagicStoneAbilityInBattle answers no). BC's in-battle esper switching (Left/Right
    //                        in the Magic menu) isn't ported.
    //   Unlimited (party)    desperation attacks open at once (the PR's 25.6 s battle-time gate) and are tried
    //                        12 times a strike (1 - (15/16)^12 = 54%, BC's 17/32), again and again
    //   Instant Run (party)  a party with a holder always gets away (BattleFucntion16FF6.IsEscape; battles you
    //                        can't flee never reach it)
    //   Salve (party)        a single-target healing or curing item (bc_junction.py salve_items) can be aimed at one
    //                        or all of a side: the target cursor's range (BattleTargetSelectController.SetDefaultTarget,
    //                        touch and keys) 7 -> 6 for the holder's item
    static class BcJunctionControl
    {
        internal static int Kept, Summons, Desperations, Runs;

        internal static void Register(Harmony h)
        {
            Hooks.Patch(h, typeof(ActSelectBaseController), "SetAct", typeof(BcJunctionControl), prefix: nameof(SetAct_Prefix));
            Hooks.Patch(h, typeof(BattlePlugManager), "IsUsedMagicStoneAbilityInBattle", typeof(BcJunctionControl), postfix: nameof(Used_Postfix));
            Hooks.Patch(h, typeof(BattleProgressATBFF6), "CheckAndChangeDyingSpecialAbility", typeof(BcJunctionControl), prefix: nameof(Dying_Prefix));
            Hooks.Patch(h, typeof(Last.Battle.Function.BattleFucntion16FF6), "IsEscape", typeof(BcJunctionControl), postfix: nameof(Escape_Postfix));
            // Salve: both target cursors (touch, keys)
            foreach (var t in new[] { typeof(Last.UI.Touch.BattleTargetSelectController), typeof(Last.UI.KeyInput.BattleTargetSelectController) })
            {
                Hooks.Patch(h, AccessTools.Method(t, "SetTargetData"), typeof(BcJunctionControl), prefix: nameof(Target_Prefix));
                Hooks.Patch(h, AccessTools.Method(t, "SetCommandData", new[] { typeof(Last.Data.Master.Command), typeof(Last.Data.User.OwnedItemData) }),
                            typeof(BcJunctionControl), prefix: nameof(Item_Prefix));
                Hooks.Patch(h, AccessTools.Method(t, "SetDefaultTarget"), typeof(BcJunctionControl), prefix: nameof(Range_Prefix));
            }
        }

        // --- Salve: a single-target healing item aimed at one or all of a side --------------------------------

        static BattleUnitData actor;
        static int pendingItem;
        internal static int Widened;
        static int stamp = -1;
        static readonly HashSet<int> salveItems = new HashSet<int>();

        static bool SalveItem(int content)
        {
            BcBattleData.Refresh();
            if (stamp != BcBattleData.Stamp)
            {
                stamp = BcBattleData.Stamp;
                salveItems.Clear();
                var j = BcBattleData.Section("junction");
                if (j.ValueKind == System.Text.Json.JsonValueKind.Object && j.TryGetProperty("salve_items", out var a) && a.ValueKind == System.Text.Json.JsonValueKind.Array)
                    foreach (var x in a.EnumerateArray()) salveItems.Add(x.GetInt32());
            }
            return salveItems.Contains(content);
        }

        public static void Target_Prefix(BattlePlayerData useTarget) => actor = useTarget;
        public static void Item_Prefix(Last.Data.User.OwnedItemData item) => pendingItem = item?.ContentId ?? 0;

        public static void Range_Prefix(ref Last.Defaine.Master.AbilityRangeType range)
        {
            if (!BcJunction.Used("salve") || actor == null || pendingItem <= 0) return;
            try
            {
                if ((int)range != 7 || !SalveItem(pendingItem) || !BcJunction.Has(actor, "salve")) return;   // 7: one of a side
                range = (Last.Defaine.Master.AbilityRangeType)6;                                                  // 6: one or all of a side
                Widened++;
                Hooks.NoteOnce("bc-junction-salve", () => $"{BcJunction.Tag} Salve: {BcJunction.Who(actor)} may aim item {pendingItem} at a whole side");
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-salve", e); }
        }

        static bool Has(BattleUnitData u, string key) => BcJunction.Used(key) && BcJunction.Has(u, key);

        // --- Focus / Commander / Lucid Dead / Necromancer -----------------------------------------------------

        static readonly ConditionType[] NotAble =
        {
            ConditionType.UnableFight, ConditionType.Mineralization, ConditionType.Zombie, ConditionType.Sleep, ConditionType.Confusion,
            ConditionType.Bersak, ConditionType.Silence, ConditionType.Mute, ConditionType.Stop, ConditionType.Freeze, ConditionType.Hide,
        };

        static bool Able(BattleUnitData u) => BcJunction.Alive(u) && !NotAble.Any(c => BcJunction.HasStatus(u, c));

        // the holder or (Commander/Necromancer) another able party member has it
        static bool Keeps(BattleUnitData u, string own, string ally) =>
            Has(u, own) || BcJunction.Party().Any(o => o.Pointer != u.Pointer && Able(o) && Has(o, ally));

        public static bool SetAct_Prefix(ActSelectBaseController __instance, ActSelect actSelect)
        {
            if (actSelect == null || __instance == null || !BcJunction.On) return true;
            if (!BcJunction.Used("focus") && !BcJunction.Used("commander") && !BcJunction.Used("lucid_dead") && !BcJunction.Used("necromancer")) return true;
            try
            {
                var u = __instance.MyUnit;
                if (u == null || !BcJunction.IsPlayer(u)) return true;
                bool zombie = actSelect.TryCast<ActSelectZombie>() != null;
                bool other = actSelect.TryCast<ActSelectBersak>() != null || actSelect.TryCast<ActSelectConfusion>() != null ||
                             actSelect.TryCast<FF6ActSelectConfusion>() != null || actSelect.TryCast<ActSelectDance>() != null ||
                             actSelect.TryCast<ActSelectRampage>() != null || actSelect.TryCast<ActSelectAutoCayenne>() != null;
                if (!(zombie ? Keeps(u, "lucid_dead", "necromancer") : other && Keeps(u, "focus", "commander"))) return true;
                Kept++;
                Hooks.NoteOnce("bc-junction-focus", () => $"{BcJunction.Tag} {BcJunction.Who(u)} keeps its command menu ({(zombie ? "Lucid Dead" : "Focus")})");
                return false;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-focus", e); return true; }
        }

        // --- Caller: summon again ---------------------------------------------------------------------------

        public static void Used_Postfix(int characterStatusId, ref bool __result)
        {
            if (!__result || !BcJunction.Used("caller") || !BcJunction.On) return;
            foreach (var u in BcJunction.Party())
                if (u.GetOwnedCharacterData()?.characterStatusId == characterStatusId && BcJunction.HasRaw(u, "caller"))
                {
                    __result = false;
                    Summons++;
                    return;
                }
        }

        // --- Unlimited: desperation attacks ---------------------------------------------------------------

        const float DesperationGate = 25.6f;      // the PR's battle time before the first desperation attack
        [ThreadStatic] static bool trying;

        public static bool Dying_Prefix(BattleProgressATBFF6 __instance, BattleActData battleActData)
        {
            if (trying || battleActData == null || __instance == null || !BcJunction.Used("unlimited")) return true;
            try
            {
                var u = battleActData.AttackUnitData;
                var oc = u?.GetOwnedCharacterData();
                if (oc == null || !BcJunction.Has(u, "unlimited")) return true;
                int id = oc.characterStatusId;
                var gate = __instance.dyingSpecialAbilityCurrentTime;
                if (gate == null) return true;
                int before = battleActData.abilityList != null && battleActData.abilityList.Count > 0 ? battleActData.abilityList[0].Id : 0;
                trying = true;
                try
                {
                    for (int i = 0; i < 11; i++)
                    {
                        gate[id] = DesperationGate;
                        __instance.CheckAndChangeDyingSpecialAbility(battleActData);
                        int now = battleActData.abilityList != null && battleActData.abilityList.Count > 0 ? battleActData.abilityList[0].Id : 0;
                        if (now != before) { Desperations++; gate[id] = DesperationGate; return false; }
                    }
                }
                finally { trying = false; }
                gate[id] = DesperationGate;     // the 12th try: the game's own call
                return true;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-junction-unlimited", e); trying = false; return true; }
        }

        // --- Instant Run ------------------------------------------------------------------------------------

        public static void Escape_Postfix(ref bool __result)
        {
            if (__result || !BcJunction.Used("instant_run") || !BcJunction.On) return;
            if (BcJunction.Party().Any(u => BcJunction.Alive(u) && BcJunction.Has(u, "instant_run"))) { __result = true; Runs++; }
        }
    }
}
