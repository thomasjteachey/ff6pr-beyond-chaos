using System;
using System.Collections.Generic;
using System.Text.Json;

namespace BeyondChaos.PR
{
    // Beyond Chaos's strangejourney doors the seed step can't set in the map files: one PR door that both worlds'
    // versions of a place share (the PR keeps one Narshe for the World of Balance and Ruin; SNES maps 20 and 32
    // both enter it) which the seed sends to two places. tools/bc_entrances.py apply leaves the door vanilla's
    // and lists it in the seed folder's bc_doors.json "shared" with split "world" and
    //   "redirect": {"flag": ["kScenarioFlag2", 41], "off": [map, point] | null, "on": [map, point] | null}
    // (the World of Ruin flag: off = the World of Balance's target, on = the World of Ruin's; null: no PR arrival
    // for that version, left vanilla's). BcEntrances changes the map change the door starts; this is the part
    // without the game (plugin/BcBattle.Tests checks it offline). Story splits ("split": "story") are another
    // step's and are left as the seed's files set them.
    public static class BcDoorRules
    {
        public const int Reach = 1;   // the party's cell within a tile of the door's, either axis

        public sealed class Door
        {
            public int Map;                 // the PR map the door is on (pr_map_id)
            public int X, Y;                // its tile (the map file's: x right, y down; the game's cells)
            public int ToMap, ToPoint;      // its destination in the map file (vanilla's): the map change it starts
            public string FlagCategory = "";
            public int FlagIndex;           // the switch: kScenarioFlag2 41, the World of Ruin
            public int[] Off, On;           // [map, point] with the switch off / on; null: leave the change alone
            public string Pr = "", File = "";
            public int Id;                  // the door object (Tiled id) in File, for reports

            public bool Changes => Differs(Off) || Differs(On);
            bool Differs(int[] t) => t != null && (t[0] != ToMap || t[1] != ToPoint);
            public override string ToString() =>
                $"{Pr} #{Id} at {X},{Y} (map {Map}) -> {ToMap} {ToPoint}: off {Str(Off)}, on {Str(On)} by {FlagCategory} {FlagIndex}";
        }

        public sealed class Table
        {
            public readonly List<Door> Doors = new List<Door>();
            public int Shared, Story;                                 // bc_doors.json's shared records; story splits (not ours)
            public readonly List<string> Skipped = new List<string>(); // world records left out, and why
            public string Flags = "";
            readonly Dictionary<(int, int, int), List<Door>> byKey = new Dictionary<(int, int, int), List<Door>>();

            public void Add(Door d)
            {
                Doors.Add(d);
                var k = (d.Map, d.ToMap, d.ToPoint);
                if (!byKey.TryGetValue(k, out var l)) byKey[k] = l = new List<Door>();
                l.Add(d);
            }

            // the listed doors on `map` whose map change goes to (toMap, toPoint); null: none (cheap: every map change asks)
            public List<Door> At(int map, int toMap, int toPoint) =>
                byKey.TryGetValue((map, toMap, toPoint), out var l) ? l : null;
        }

        public static string Str(int[] t) => t == null ? "none" : $"{t[0]} {t[1]}";

        // bc_doors.json -> the per-world doors. A record is left out (Skipped) when it lacks a field this needs or
        // its key isn't unique (key_unique false: another door object on its map goes to the same destination,
        // so a map change there can't be told apart by its target).
        public static Table Parse(string json)
        {
            var t = new Table();
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object) return t;
            if (root.TryGetProperty("flags", out var fl) && fl.ValueKind == JsonValueKind.String) t.Flags = fl.GetString();
            if (!root.TryGetProperty("shared", out var shared) || shared.ValueKind != JsonValueKind.Array) return t;
            foreach (var s in shared.EnumerateArray())
            {
                t.Shared++;
                if (Str(s, "split") != "world")
                {
                    t.Story++;
                    continue;
                }
                var name = $"{Str(s, "pr")} #{Int(s, "id") ?? -1}";
                if (!s.TryGetProperty("redirect", out var r) || r.ValueKind != JsonValueKind.Object) { t.Skipped.Add(name + ": no redirect"); continue; }
                int? map = Int(s, "pr_map_id"), x = Int(s, "x"), y = Int(s, "y");
                var van = Pair(s, "vanilla");
                if (map == null || x == null || y == null || van == null) { t.Skipped.Add(name + ": no map, tile or destination"); continue; }
                if (s.TryGetProperty("key_unique", out var ku) && ku.ValueKind == JsonValueKind.False)
                {
                    t.Skipped.Add(name + ": key not unique (another door there goes to the same place)");
                    continue;
                }
                if (!r.TryGetProperty("flag", out var f) || f.ValueKind != JsonValueKind.Array || f.GetArrayLength() != 2 ||
                    f[0].ValueKind != JsonValueKind.String || f[1].ValueKind != JsonValueKind.Number)
                {
                    t.Skipped.Add(name + ": no switch flag");
                    continue;
                }
                t.Add(new Door
                {
                    Map = map.Value, X = x.Value, Y = y.Value, ToMap = van[0], ToPoint = van[1],
                    FlagCategory = f[0].GetString(), FlagIndex = f[1].GetInt32(),
                    Off = Pair(r, "off"), On = Pair(r, "on"),
                    Pr = Str(s, "pr"), File = Str(s, "file"), Id = Int(s, "id") ?? -1,
                });
            }
            return t;
        }

        // A map change's new target, or null to leave it as it is. The change from PR map `map` to (toMap, toPoint)
        // is a listed door's when the party stands within Reach of the door (px, py: its cell; null: not checked,
        // the harness's question without walking): then the redirect for the switch's state (flagOn: a story
        // flag's state, null when it can't be read: left alone). Null too for no table, no such door, a version
        // with no target, or a target the change already has.
        public static int[] Resolve(Table t, int map, int toMap, int toPoint, int? px, int? py, Func<string, int, bool?> flagOn)
        {
            var d = Find(t, map, toMap, toPoint, px, py);
            if (d == null || flagOn == null) return null;
            var on = flagOn(d.FlagCategory, d.FlagIndex);
            if (on == null) return null;
            var to = on.Value ? d.On : d.Off;
            return to == null || (to[0] == toMap && to[1] == toPoint) ? null : to;
        }

        // the listed door a map change goes through: on `map`, to (toMap, toPoint), the nearest within Reach of
        // (px, py) (no position: the first listed)
        public static Door Find(Table t, int map, int toMap, int toPoint, int? px, int? py)
        {
            var doors = t?.At(map, toMap, toPoint);
            if (doors == null) return null;
            if (px == null || py == null) return doors[0];
            Door best = null;
            int bestD = int.MaxValue;
            foreach (var d in doors)
            {
                int dx = Math.Abs(px.Value - d.X), dy = Math.Abs(py.Value - d.Y);
                if (dx > Reach || dy > Reach || dx + dy >= bestD) continue;
                best = d;
                bestD = dx + dy;
            }
            return best;
        }

        // the World of Ruin flag as bc_entrances writes it (WcEvents.CollapseFlag's): for tests and the harness
        public const string WorCategory = "kScenarioFlag2";
        public const int WorIndex = 41;

        static string Str(JsonElement e, string k) =>
            e.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : "";

        static int? Int(JsonElement e, string k) =>
            e.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out int i) ? i : (int?)null;

        static int[] Pair(JsonElement e, string k)
        {
            if (!e.TryGetProperty(k, out var v) || v.ValueKind != JsonValueKind.Array || v.GetArrayLength() != 2) return null;
            if (v[0].ValueKind != JsonValueKind.Number || v[1].ValueKind != JsonValueKind.Number) return null;
            return new[] { v[0].GetInt32(), v[1].GetInt32() };
        }
    }
}
