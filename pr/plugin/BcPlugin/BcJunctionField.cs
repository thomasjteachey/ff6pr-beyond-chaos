using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using PrKit;

namespace BeyondChaos.PR
{
    // What junction effects read about the seed beyond who has what (bc_battle.json "junction"):
    //   esper_info   each esper's summon in BC's ROM (tools/bc_junction.py esper_info): its elements (PR
    //                attribute ids), the statuses it sets (BC status indexes), aimed at foes, lifts statuses,
    //                the PR's summon ability (Esper Attack, Esper Defense, Esper Magic, Caller, SOS Summon...)
    //   the battlefield's Gaia element (Gaia Boost, Gaia Assist): not found in the PR yet (-1)
    static class BcJunctionField
    {
        internal sealed class Esper
        {
            public int ContentId, Index, Summon;
            public int[] Elements = Array.Empty<int>();
            public int[] Statuses = Array.Empty<int>();
            public int[] Protect = Array.Empty<int>();    // PR condition ids its statuses map to (Esper Defense)
            public bool Foe, Lift;
            public List<(int Rate, int Ability, bool Foe)> Spells = new List<(int, int, bool)>();   // slots 1-5
        }

        static int stamp = -1;
        static readonly Dictionary<int, Esper> espers = new Dictionary<int, Esper>();

        internal static Esper EsperInfo(int contentId)
        {
            BcBattleData.Refresh();
            if (stamp != BcBattleData.Stamp)
            {
                stamp = BcBattleData.Stamp;
                espers.Clear();
                try
                {
                    var j = BcBattleData.Section("junction");
                    if (j.ValueKind == JsonValueKind.Object && j.TryGetProperty("esper_info", out var ei) && ei.ValueKind == JsonValueKind.Object)
                        foreach (var p in ei.EnumerateObject())
                        {
                            if (!int.TryParse(p.Name, out int cid)) continue;
                            var v = p.Value;
                            espers[cid] = new Esper
                            {
                                ContentId = cid, Index = v.Int("esper"), Summon = v.Int("summon"),
                                Elements = Ints(v, "elements"), Statuses = Ints(v, "statuses"), Protect = Ints(v, "protect"),
                                Foe = v.Bool("foe"), Lift = v.Bool("lift"),
                            };
                            if (v.TryGetProperty("spells", out var sp) && sp.ValueKind == JsonValueKind.Array)
                                foreach (var sx in sp.EnumerateArray())
                                    if (sx.ValueKind == JsonValueKind.Array && sx.GetArrayLength() >= 3)
                                        espers[cid].Spells.Add((sx[0].GetInt32(), sx[1].GetInt32(), sx[2].ValueKind == JsonValueKind.True));
                        }
                }
                catch (Exception e) { Hooks.WarnOnce("bc-junction-esper-info", e); }
            }
            return espers.TryGetValue(contentId, out var x) ? x : null;
        }

        static int[] Ints(JsonElement e, string key) =>
            e.TryGetProperty(key, out var a) && a.ValueKind == JsonValueKind.Array ? a.EnumerateArray().Select(x => x.GetInt32()).ToArray() : Array.Empty<int>();

        // the SNES element bit of the battlefield's dance (BC: ED/8E5B[background] -> Wind, Holy, Fire, Lightning,
        // Earth, Water, Poison, Ice); -1 while the PR's terrain isn't read
        internal static int GaiaElementBit() => BcJunctionExtra.GaiaElementBit();
    }
}
