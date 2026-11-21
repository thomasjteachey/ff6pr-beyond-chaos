using System;
using System.Collections.Generic;
using System.Linq;

namespace BeyondChaos.PR
{
    // Beyond Chaos's battle rules that need no game (bc-battle): the plugin's hooks call these, and
    // plugin/BcBattle.Tests checks them offline (no game, no BepInEx).
    public static class BcBattleRules
    {
        public const int ChainCap = 16;   // BC's chain has no cap; a run of 16 heads is 1 in 65536

        // The acts after the first of one of BC's commands: the ability each one uses (0: the row's own).
        //   multiple (MultipleSpellSub)  count acts in all;  chain (ChainSpellSub): again while the coin says so
        //   combo (ComboSpellSub)        skill A, then skill B
        //   N times / chain of a combo   each round is A then B
        public static List<int> ActPlan(string kind, string inner, int count, IReadOnlyList<int> abilities, Func<bool> coin, int chainCap = ChainCap)
        {
            var more = new List<int>();
            abilities ??= Array.Empty<int>();
            var round = inner == "combo" && abilities.Count > 1 ? new[] { 0 }.Concat(abilities.Skip(1)).ToArray() : new[] { 0 };
            var rest = round.Skip(1);           // the first round's other acts (the row ran its first)
            switch (kind)
            {
                case "multiple":
                    more.AddRange(rest);
                    for (int i = 1; i < count; i++) more.AddRange(round);
                    break;
                case "chain":
                    more.AddRange(rest);
                    for (int n = 0; n < chainCap && coin(); n++) more.AddRange(round);
                    break;
                case "combo":
                    more.AddRange(abilities.Skip(1));
                    break;
            }
            return more;
        }

        // `bcselftest start` filter: comma-separated words; a test runs if its name holds one of the plain words
        // (none: every test) and none of the words starting with "!" ("commands,items" / "!junction")
        public static bool FilterMatches(string testName, string filter)
        {
            var words = (filter ?? "").ToLowerInvariant().Split(',').Select(w => w.Trim()).Where(w => w != "" && w != "all").ToList();
            var want = words.Where(w => !w.StartsWith("!")).ToList();
            var not = words.Where(w => w.StartsWith("!")).Select(w => w.Substring(1)).ToList();
            var n = (testName ?? "").ToLowerInvariant();
            return (want.Count == 0 || want.Any(n.Contains)) && !not.Any(n.Contains);
        }

        // levelcap: the level a level-up pass may read (0: no cap)
        public static int CappedLevel(int level, int cap) => cap > 0 && level > cap ? cap : level;

        // norng: GetRandWeight with every roll 0 picks the first entry that weighs anything (-1: none)
        public static int FirstWeighted(IReadOnlyList<float> weights)
        {
            for (int i = 0; weights != null && i < weights.Count; i++) if (weights[i] > 0) return i;
            return -1;
        }

        // Vigor +50% (C2/0F30: Vigor += Vigor / 2 after the equipment sums), capped
        public static int VigorBoost(int vigor, int max = 255) => Math.Min(max, vigor + vigor / 2);

        // a hidden relic's (mementomori) stat added to the PR's, kept in 0..max
        public static int AddStat(int stat, int bonus, int max = 255) => Math.Max(0, Math.Min(max, stat + bonus));

        // cursepower: the Cursed Shield's battle counter (the PR uncurses at 256) moved so this battle uncurses it
        // when it reaches BC's goal; else unchanged
        public static int CurseCounter(int counter, int goal) => goal > 0 && goal < 256 && counter + 1 >= goal && counter < 255 ? 255 : counter;
    }
}
