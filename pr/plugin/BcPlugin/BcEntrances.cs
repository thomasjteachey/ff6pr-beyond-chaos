using System;
using System.IO;
using System.Linq;
using HarmonyLib;
using Last.Interpreter;
using Last.Management;
using Last.Map;
using PrKit;

namespace BeyondChaos.PR
{
    // strangejourney's per-world doors (BcDoorRules: bc_doors.json's "shared" doors split by world). A door the
    // party walks into ends in EventProcedure.EventGotoMap(LoadData, skipFade, skipBgm) with the LoadData set to
    // the door's destination (Worlds Collide's Doma entrance hooks the same call: the technique is copied, not
    // WC's code). A prefix there: when the change starts on a listed door's map, goes to that door's destination
    // in the map file, and the party stands within a tile of the door (a script's ChangeMap to the same place from
    // elsewhere on the map is left alone), the LoadData is pointed at the World of Balance's or the World of
    // Ruin's target by the switch flag the file names (kScenarioFlag2 41). No seed, no bc_doors.json, or a map
    // change that isn't a listed door's: nothing is touched.
    static class BcEntrances
    {
        const string DoorsJson = "bc_doors.json";
        static string loaded = "";
        static BcDoorRules.Table table;
        static string note = "no seed";
        internal static string Last = "none";
        internal static int Redirected;

        internal static void Patch(Harmony h)
        {
            var m = AccessTools.Method(typeof(EventProcedure), "EventGotoMap");
            if (m == null) throw new MissingMethodException("EventProcedure.EventGotoMap");
            h.Patch(m, prefix: new HarmonyMethod(typeof(BcEntrances), nameof(EventGotoMap_Prefix)));
            Plugin.L.LogInfo("[bc] doors: map changes hooked (strangejourney's per-world doors)");
        }

        // the active seed's door table (read again when the active seed changes); null: none
        internal static BcDoorRules.Table Table
        {
            get
            {
                Refresh();
                return table;
            }
        }

        static void Refresh()
        {
            var s = Plugin.BcMode ? BcSeeds.Active : null;
            var id = s == null ? "" : s.Id + "|" + s.Dir;
            if (id == loaded) return;
            loaded = id;
            table = null;
            if (s == null)
            {
                note = "no seed";
                return;
            }
            var path = Path.Combine(s.Dir ?? "", DoorsJson);
            if (!File.Exists(path))
            {
                note = $"seed {s.Id}: no {DoorsJson} (no strangejourney)";
                return;
            }
            try
            {
                table = BcDoorRules.Parse(File.ReadAllText(path));
                note = $"seed {s.Id}: {table.Doors.Count} per-world doors ({table.Doors.Count(d => d.Changes)} change a map change), " +
                       $"{table.Skipped.Count} left out, {table.Story} story splits (not the plugin's) of {table.Shared} shared";
                Plugin.L.LogInfo("[bc] doors: " + note);
                foreach (var why in table.Skipped) Plugin.L.LogWarning("[bc] doors: left out " + why);
            }
            catch (Exception e)
            {
                table = null;
                note = $"seed {s.Id}: can't read {DoorsJson}: {e.Message}";
                Kit.Warn("[bc] doors: " + note);
            }
        }

        // the story flag a redirect names (kScenarioFlag2 41), or null when it can't be read
        static bool? Flag(string category, int index)
        {
            if (!Enum.TryParse<DataStorage.Category>(category, out var c)) return null;
            var ds = DataStorage.Instance;
            if (ds == null) return null;
            return ds.Get(c, index) == 1;
        }

        // the party's cell on the field (the map files' tiles: x right, y down), or null off the field
        static (int X, int Y)? PlayerCell()
        {
            var fc = UnityEngine.Object.FindObjectOfType<global::FieldMap>()?.fieldController;
            var p = fc?.player;
            if (p == null) return null;
            var c = fc.ConvertWorldPositionToCellPosition(p.transform.position);
            return (UnityEngine.Mathf.RoundToInt(c.x), UnityEngine.Mathf.RoundToInt(c.y));
        }

        public static void EventGotoMap_Prefix(LoadData __0)
        {
            try
            {
                if (__0 == null || !Plugin.BcMode || BcSeeds.Active == null) return;
                var t = Table;
                if (t == null || t.Doors.Count == 0) return;
                int from = UserDataManager.Instance()?.CurrentMapId ?? -1;
                int toMap = __0.MapId, toPoint = __0.Point;
                if (t.At(from, toMap, toPoint) == null) return;          // not a listed door's map change
                var cell = PlayerCell();
                if (cell == null) return;
                var (x, y) = cell.Value;
                var door = BcDoorRules.Find(t, from, toMap, toPoint, x, y);
                var to = BcDoorRules.Resolve(t, from, toMap, toPoint, x, y, Flag);
                if (to == null)
                {
                    Last = door == null
                        ? $"map {from} -> {toMap} {toPoint} with the party at {x},{y}: no listed door within a tile (left alone)"
                        : $"map {from} -> {toMap} {toPoint} through {door.Pr} #{door.Id}: {World(door)}, no change";
                    Plugin.L.LogInfo("[bc] doors: " + Last);
                    return;
                }
                __0.NextMapData(to[0], to[1], (ViewType)0);
                Redirected++;
                Last = $"map {from} -> {toMap} {toPoint} through {door?.Pr} #{door?.Id} at {door?.X},{door?.Y} (party at {x},{y}): " +
                       $"{World(door)}, to map {to[0]} point {to[1]}";
                Plugin.L.LogInfo("[bc] doors: " + Last);
            }
            catch (Exception e) { Hooks.WarnOnce("bc-doors", e); }
        }

        static string World(BcDoorRules.Door d)
        {
            var on = d == null ? null : Flag(d.FlagCategory, d.FlagIndex);
            return on == null ? "switch unknown" : on.Value ? "World of Ruin" : "World of Balance";
        }

        // --- harness ------------------------------------------------------------------------------------------
        //   bcdoors                              the table: how many per-world doors, the last map change through one
        //   bcdoors list                         every per-world door (map, tile, destination, both targets)
        //   bcdoors MAP TOMAP TOPOINT [wob|wor]  what a map change from MAP to (TOMAP, TOPOINT) becomes (no walking: the
        //                                        party's tile isn't checked; no world: the flag as it is now)
        internal static void Register()
        {
            Harness.Register("bcdoors", Command,
                "bcdoors [list | MAP TOMAP TOPOINT [wob|wor]]: strangejourney's per-world doors (bc_doors.json): how many are " +
                "loaded and the last map change through one; list: each door; MAP TOMAP TOPOINT: what that map change " +
                "becomes in the World of Balance / Ruin (no world: the flag now), the party's tile not checked");
        }

        static string Command(string[] a)
        {
            var t = Table;
            if (a.Length > 0 && a[0] == "list")
                return t == null ? "doors: " + note
                    : $"doors: {t.Doors.Count}: " + string.Join("; ", t.Doors.Select(d => d.ToString()));
            if (a.Length == 0)
            {
                var udm = UserDataManager.Instance();
                var cell = PlayerCell();
                return $"doors: {note}; redirected {Redirected}; last {Last}; map {udm?.CurrentMapId} cell " +
                       $"{(cell == null ? "?" : $"{cell.Value.X},{cell.Value.Y}")}; World of Ruin {Flag(BcDoorRules.WorCategory, BcDoorRules.WorIndex)?.ToString() ?? "?"}";
            }
            if (a.Length < 3 || !int.TryParse(a[0], out int map) || !int.TryParse(a[1], out int toMap) || !int.TryParse(a[2], out int toPoint))
                return "error: bcdoors [list | MAP TOMAP TOPOINT [wob|wor]]";
            if (t == null) return "doors: " + note;
            bool? wor = a.Length > 3 ? a[3] == "wor" ? true : a[3] == "wob" ? false : (bool?)null : null;
            if (a.Length > 3 && wor == null) return "error: the world is wob or wor";
            Func<string, int, bool?> flag = wor == null ? Flag : (c, i) => wor;
            var door = BcDoorRules.Find(t, map, toMap, toPoint, null, null);
            if (door == null) return $"doors: map {map} -> {toMap} {toPoint}: no listed door (left alone)";
            var to = BcDoorRules.Resolve(t, map, toMap, toPoint, null, null, flag);
            var world = flag(door.FlagCategory, door.FlagIndex) is bool w ? (w ? "World of Ruin" : "World of Balance") : "switch unknown";
            return $"doors: map {map} -> {toMap} {toPoint} in the {world}: " +
                   (to == null ? "unchanged" : $"map {to[0]} point {to[1]}") + $" (door {door})";
        }
    }
}
