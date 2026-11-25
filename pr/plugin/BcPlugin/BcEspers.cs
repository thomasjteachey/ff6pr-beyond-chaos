using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Data.User;
using Last.Defaine.Audio;
using Last.Management;
using PrKit;
using Serial.FF6.UI;
using UnityEngine;
using DetailsController = Serial.FF6.UI.KeyInput.MagicStoneDetailsController;
using ListController = Serial.FF6.UI.KeyInput.MagicStoneListController;
using ListContent = Serial.FF6.UI.KeyInput.MagicStoneListContentController;

namespace BeyondChaos.PR
{
    // dancingmaduin: the seed's 27 character masks restrict who may equip each esper.
    // Both the Magicite menu and the party screen commit through SetMagicStone.
    static class BcEspers
    {
        static OwnedCharacterData listTarget;
        static readonly HashSet<IntPtr> greyed = new HashSet<IntPtr>();
        static readonly Color32 Grey = new Color32(140, 140, 150, 255);

        internal static void Patch(Harmony harmony)
        {
            var method = AccessTools.Method(typeof(OwnedCharacterClient), "SetMagicStone");
            if (method != null)
            {
                harmony.Patch(method, prefix: new HarmonyMethod(typeof(BcEspers), nameof(SetMagicStone_Prefix)));
                Kit.Info("[bc] dancingmaduin: esper equip restriction hooked");
            }
            Hooks.Patch(harmony, typeof(ListController), "Show", typeof(BcEspers), prefix: nameof(ListShow_Prefix));
            Hooks.Patch(harmony, typeof(ListController), "ListUpdate", typeof(BcEspers), prefix: nameof(ListShow_Prefix),
                args: new[] { typeof(OwnedCharacterData), typeof(Il2CppSystem.Collections.Generic.List<OwnedCharacterData>),
                              typeof(Il2CppSystem.Collections.Generic.List<int>), typeof(Il2CppSystem.Collections.Generic.List<int>) });
            Hooks.Patch(harmony, typeof(ListController), "ContentUpdate", typeof(BcEspers), postfix: nameof(ContentUpdate_Postfix));
            Hooks.Patch(harmony, typeof(ListContent), "SetFocus", typeof(BcEspers), postfix: nameof(ContentFocus_Postfix));
            Hooks.Patch(harmony, typeof(DetailsController), "EquipMagicStone", typeof(BcEspers), prefix: nameof(Equip_Prefix),
                args: new[] { typeof(OwnedCharacterData), typeof(Il2CppSystem.Collections.Generic.List<OwnedCharacterData>), typeof(bool) });
        }

        static bool CanEquip(int statusId, int contentId)
        {
            var allowed = BcSeeds.Active?.EsperEquip;
            return !Plugin.BcMode || statusId > 14 || allowed == null ||
                   !allowed.TryGetValue(contentId, out var users) || users.Contains(statusId);
        }

        public static void ListShow_Prefix(ListController __instance, OwnedCharacterData target)
        {
            if (Hooks.IsA<ListController>(__instance)) listTarget = target;
        }

        public static void ContentUpdate_Postfix(ListController __instance, MagicStoneListData data, GameObject gameObject)
        {
            if (data == null || gameObject == null || !Hooks.IsA<ListController>(__instance)) return;
            try
            {
                var content = gameObject.GetComponent<ListContent>() ?? gameObject.GetComponentInChildren<ListContent>(true);
                var name = content?.view?.ItemNameView;
                if (name == null) return;
                var target = listTarget ?? __instance.targetCharacter;
                bool grey = data.IsOwned && target != null && !CanEquip(target.characterStatusId, data.ContentId);
                if (grey)
                {
                    greyed.Add(content.Pointer);
                    name.SetTextColor(Grey);
                }
                else if (greyed.Remove(content.Pointer)) name.SetFocusColor(false);
            }
            catch (Exception e) { Hooks.WarnOnce("bc-esper-list", e); }
        }

        public static void ContentFocus_Postfix(ListContent __instance)
        {
            try
            {
                if (__instance == null || !Hooks.IsA<ListContent>(__instance)) return;
                if (Plugin.BcMode && greyed.Contains(__instance.Pointer))
                    __instance.view?.ItemNameView?.SetTextColor(Grey);
                else greyed.Remove(__instance.Pointer);
            }
            catch (Exception e) { Hooks.WarnOnce("bc-esper-focus", e); }
        }

        public static bool Equip_Prefix(DetailsController __instance, OwnedCharacterData target)
        {
            if (!Plugin.BcMode || !Hooks.IsA<DetailsController>(__instance)) return true;
            try
            {
                var who = target ?? __instance.targetCharacter;
                var stone = __instance.targetmagicStone;
                if (who == null || stone == null || CanEquip(who.characterStatusId, stone.ContentId)) return true;
                AudioManager.Instance?.PlaySe(SystemSeDefine.BeepId, 0f, 0f, 0f);
                return false;
            }
            catch (Exception e) { Hooks.WarnOnce("bc-esper-menu-equip", e); return true; }
        }

        public static bool SetMagicStone_Prefix(int characterId, int contentId)
        {
            try
            {
                var owned = UserDataManager.Instance()?.OwnedCharacterList;
                if (owned == null) return true;
                foreach (var character in owned)
                {
                    if (character == null || character.Id != characterId) continue;
                    if (CanEquip(character.characterStatusId, contentId)) return true;
                    Plugin.Screen?.Toast($"{character.Name} can't equip that magicite in this seed");
                    Plugin.L.LogInfo($"[bc] dancingmaduin: {character.characterStatusId} can't equip {contentId}");
                    return false;
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-esper-equip", e); }
            return true;
        }
    }
}
