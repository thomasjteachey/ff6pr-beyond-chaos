using System;
using System.Collections.Generic;
using System.Linq;
using BeyondChaos.PR;

// Beyond Chaos's game-free battle rules (BcBattleRules), checked offline.
static class Program
{
    static int failures, checks;

    static void Check(bool ok, string what)
    {
        checks++;
        if (ok) return;
        failures++;
        Console.WriteLine("FAIL " + what);
    }

    static string S(IEnumerable<int> xs) => string.Join(" ", xs);

    static int Main()
    {
        // repeats, chains, combos (BC's MultipleSpellSub / ChainSpellSub / ComboSpellSub)
        var ab = new[] { 10, 20 };
        Check(S(BcBattleRules.ActPlan("multiple", "combo", 3, ab, () => false)) == "20 0 20 0 20", "three rounds of a combo: B, then (A, B) twice");
        int heads = 0;
        Check(S(BcBattleRules.ActPlan("chain", "combo", 1, ab, () => heads++ < 2)) == "20 0 20 0 20", "a chain of a combo, two heads");
        Check(S(BcBattleRules.ActPlan("multiple", "random", 4, new[] { 10 }, () => false)) == "0 0 0", "x4 of a random skill: three more rolls");
        Check(S(BcBattleRules.ActPlan("multiple", "skill", 2, new[] { 10 }, () => true)) == "0", "Double: one more");
        Check(S(BcBattleRules.ActPlan("combo", "combo", 1, ab, () => true)) == "20", "a combo: B after A");
        Check(BcBattleRules.ActPlan("skill", "skill", 1, new[] { 10 }, () => true).Count == 0, "one skill: nothing more");
        Check(BcBattleRules.ActPlan("chain", "skill", 1, new[] { 10 }, () => true).Count == BcBattleRules.ChainCap, "a chain stops at the cap");
        Check(BcBattleRules.ActPlan("chain", "skill", 1, new[] { 10 }, () => false).Count == 0, "a chain on tails: no more");
        Check(BcBattleRules.ActPlan("multiple", "combo", 2, new[] { 10 }, () => false).SequenceEqual(new[] { 0 }), "a combo list of one skill acts as a skill");

        // the self-test filter
        Check(BcBattleRules.FilterMatches("commands: rows", ""), "no filter: every test");
        Check(BcBattleRules.FilterMatches("commands: rows", "all"), "all: every test");
        Check(!BcBattleRules.FilterMatches("junction acts", "!junction"), "!junction drops a junction test");
        Check(BcBattleRules.FilterMatches("items: Vigor +50%", "!junction"), "!junction keeps the rest");
        Check(BcBattleRules.FilterMatches("codes: levelcap", "commands, codes"), "two words: either");
        Check(!BcBattleRules.FilterMatches("items: Vigor +50%", "commands,codes"), "not in the words: out");
        Check(!BcBattleRules.FilterMatches("codes: norng", "codes,!norng"), "a word and an exclusion");

        // levelcap, norng's weighted pick, Vigor +50%, mementomori's stats, cursepower's counter
        Check(BcBattleRules.CappedLevel(45, 38) == 38 && BcBattleRules.CappedLevel(30, 38) == 30 && BcBattleRules.CappedLevel(60, 0) == 60, "level caps");
        Check(BcBattleRules.FirstWeighted(new float[] { 0, 3, 5 }) == 1 && BcBattleRules.FirstWeighted(new float[] { 0, 0 }) == -1, "norng picks the first entry with weight");
        Check(BcBattleRules.VigorBoost(40) == 60 && BcBattleRules.VigorBoost(41) == 61 && BcBattleRules.VigorBoost(200) == 255, "Vigor +50%, capped");
        Check(BcBattleRules.AddStat(120, 10, 128) == 128 && BcBattleRules.AddStat(5, -10) == 0 && BcBattleRules.AddStat(50, 7) == 57, "a hidden relic's stat");
        Check(BcBattleRules.CurseCounter(9, 10) == 255, "cursepower: the 10th battle (9 counted) uncurses");
        Check(BcBattleRules.CurseCounter(8, 10) == 8, "cursepower: the 9th (8 counted) doesn't");
        Check(BcBattleRules.CurseCounter(40, 0) == 40 && BcBattleRules.CurseCounter(40, 256) == 40, "cursepower off: the PR's own count");

        Console.WriteLine($"BcBattle.Tests: {checks - failures} of {checks} passed");
        return failures == 0 ? 0 : 1;
    }
}
