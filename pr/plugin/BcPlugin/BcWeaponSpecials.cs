using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using HarmonyLib;
using Il2CppInterop.Runtime;
using Il2CppInterop.Runtime.InteropTypes.Arrays;
using Last.Battle;
using Last.Data.User;
using PrKit;

namespace BeyondChaos.PR
{
    // Weapon special actions BC gives a weapon that had none (itemrandomizer.mutate_special_action, byte 27's high
    // nibble) where the PR decides them by weapon id in code, not data (bc_battle.json items.special, both ids):
    //   atma         Atma Weapon's damage (CalcExecuteFF6.PhysicalExecution's isEquipmentUltimaWeapon; the PR tests
    //                its constant UltimaWeaponId 30): set for a strike with one of BC's
    //   valiant      Valiant Knife's (isValiantKnife): the same
    //   mp_critical  criticals that spend MP (CalcExecuteCorrection.UseMpCriticalWeaponIds)
    //   heal         a hit that heals (CalcExecuteCorrection.NormalAttackHeal)
    //   fragile      a weapon that may break (BattleActExectionSerial.UseBrokenWeaponIds, with Ogre Nix's chance in
    //                UseBrokenWeaponPercentTable)
    // The lists get BC's weapons added (the game's own stay), in the id space the game's own entries use (vanilla's
    // weapons are in them: weapon ids or content ids); a seed without them puts the game's lists back.
    static class BcWeaponSpecials
    {
        static readonly int[] VanillaMpCritical = { 14, 28, 29, 61 }, VanillaHeal = { 53 }, VanillaFragile = { 25 };   // weapon ids
        const int OgreNix = 25;
        static int stamp = -1;
        static readonly Dictionary<string, List<(int Weapon, int Content)>> special = new Dictionary<string, List<(int, int)>>();
        static readonly HashSet<int> atma = new HashSet<int>(), valiant = new HashSet<int>();   // content ids
        static readonly Dictionary<string, int[]> original = new Dictionary<string, int[]>();
        internal static string LastApply = "";
        internal static int Strikes;

        internal static void Patch(Harmony h)
        {
            var m = AccessTools.Method(typeof(CalcExecuteFF6), "PhysicalExecution");
            if (m == null) { Kit.Warn("[bc] weapon specials: CalcExecuteFF6.PhysicalExecution not found: Atma/Valiant stay the game's"); return; }
            h.Patch(m, prefix: new HarmonyMethod(typeof(BcWeaponSpecials), nameof(Physical_Prefix)));
            Kit.Info("[bc] weapon specials: hooked");
        }

        static void Load()
        {
            BcBattleData.Refresh();
            if (stamp == BcBattleData.Stamp) return;
            stamp = BcBattleData.Stamp;
            special.Clear(); atma.Clear(); valiant.Clear();
            var it = BcBattleData.Section("items");
            if (it.ValueKind == JsonValueKind.Object && it.TryGetProperty("special", out var sp) && sp.ValueKind == JsonValueKind.Object)
                foreach (var p in sp.EnumerateObject())
                    special[p.Name] = p.Value.EnumerateArray().Select(x => (x.Int("weapon", 0), x.Int("content", 0))).ToList();
            if (special.TryGetValue("atma", out var a)) foreach (var x in a) atma.Add(x.Content);
            if (special.TryGetValue("valiant", out var v)) foreach (var x in v) valiant.Add(x.Content);
            ApplyLists();
        }

        static List<(int Weapon, int Content)> Of(string kind) =>
            Plugin.BcMode && BcSeeds.Active != null && special.TryGetValue(kind, out var l) ? l : new List<(int, int)>();

        // the game's lists with BC's weapons added (or put back as they were)
        static void ApplyLists()
        {
            var parts = new List<string>();
            parts.Add(Rewrite(typeof(CalcExecuteCorrection), "UseMpCriticalWeaponIds", VanillaMpCritical, Of("mp_critical")));
            parts.Add(Rewrite(typeof(CalcExecuteCorrection), "NormalAttackHeal", VanillaHeal, Of("heal")));
            parts.Add(Rewrite(typeof(Serial.FF6.Battle.BattleActExectionSerial), "UseBrokenWeaponIds", VanillaFragile, Of("fragile")));
            FragileChances(Of("fragile"));
            LastApply = string.Join("; ", parts.Where(x => x != ""));
            if (LastApply != "") Kit.Info($"[bc] weapon specials: {LastApply}");
        }

        static PropertyInfo Prop(Type t, string member)
        {
            InitClass(t);
            return t.GetProperty(member, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
        }

        static string Rewrite(Type t, string member, int[] vanillaWeapons, List<(int Weapon, int Content)> add)
        {
            try
            {
                var prop = Prop(t, member);
                if (prop == null) return $"{member}: not found";
                var key = t.Name + "." + member;
                var cur = (prop.GetValue(null) as Il2CppStructArray<int>)?.ToArray();
                if (cur == null) return $"{member}: unreadable";
                if (!original.ContainsKey(key)) original[key] = cur;
                var game = original[key];
                // which ids the game's list holds: vanilla's weapons by weapon id, else content ids
                bool weaponIds = vanillaWeapons.All(game.Contains);
                var want = game.Concat(add.Select(x => weaponIds ? x.Weapon : x.Content)).Distinct().ToArray();
                if (cur.SequenceEqual(want)) return "";
                prop.SetValue(null, new Il2CppStructArray<int>(want));
                return $"{member}: [{string.Join(" ", game)}] -> [{string.Join(" ", want)}] ({(weaponIds ? "weapon" : "content")} ids)";
            }
            catch (Exception e) { Hooks.WarnOnce("bc-weapon-specials-" + member, e); return $"{member}: {e.GetType().Name}"; }
        }

        // a fragile weapon of BC's breaks as often as Ogre Nix
        static void FragileChances(List<(int Weapon, int Content)> add)
        {
            try
            {
                var prop = Prop(typeof(Serial.FF6.Battle.BattleActExectionSerial), "UseBrokenWeaponPercentTable");
                var table = prop?.GetValue(null) as Il2CppSystem.Collections.Generic.Dictionary<int, int>;
                if (table == null || add.Count == 0) return;
                int key = table.ContainsKey(OgreNix) ? OgreNix : -1;
                if (key < 0) { foreach (var kv in table) { key = kv.Key; break; } }
                if (key < 0 || !table.ContainsKey(key)) return;
                bool weaponIds = table.ContainsKey(OgreNix);
                foreach (var (w, c) in add)
                {
                    int id = weaponIds ? w : c;
                    if (!table.ContainsKey(id)) table[id] = table[key];
                }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-weapon-specials-fragile", e); }
        }

        static void InitClass(Type t)
        {
            var store = typeof(Il2CppClassPointerStore<>).MakeGenericType(t);
            var field = store.GetField("NativeClassPtr", BindingFlags.Public | BindingFlags.Static);
            var ptr = (IntPtr)(field?.GetValue(null) ?? IntPtr.Zero);
            if (ptr == IntPtr.Zero)
            {
                System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(t.TypeHandle);
                ptr = (IntPtr)(field?.GetValue(null) ?? IntPtr.Zero);
            }
            if (ptr != IntPtr.Zero) IL2CPP.il2cpp_runtime_class_init(ptr);
        }

        // each frame (BcBattle.Update): the lists follow the active seed
        internal static void Update()
        {
            try { Load(); }
            catch (Exception e) { Hooks.WarnOnce("bc-weapon-specials", e); }
        }

        // a strike by someone with one of BC's Atma / Valiant weapons: the act's item, else the weapons equipped (the
        // PR's own flag is "is equipped with" Atma Weapon)
        public static void Physical_Prefix(OwnedCharacterData userCharacterData, OwnedItemData item, ref bool isEquipmentUltimaWeapon, ref bool isValiantKnife)
        {
            if ((atma.Count == 0 && valiant.Count == 0) || !Plugin.BcMode || BcSeeds.Active == null) return;
            try
            {
                var held = new List<int>();
                if (item != null) held.Add(item.ContentId);
                else held.AddRange(BcItems.Worn(userCharacterData));
                if (!isEquipmentUltimaWeapon && held.Any(atma.Contains)) { isEquipmentUltimaWeapon = true; Strikes++; }
                if (!isValiantKnife && held.Any(valiant.Contains)) { isValiantKnife = true; Strikes++; }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-weapon-specials-strike", e); }
        }
    }
}
