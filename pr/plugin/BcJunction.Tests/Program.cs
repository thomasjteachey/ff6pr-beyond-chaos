using System;
using System.Collections.Generic;
using BeyondChaos.PR;
using M = BeyondChaos.PR.BcJunctionMath;

// Beyond Chaos's junction numbers, offline (BcJunctionMath; BC's rules: pr/data/bc_junction_spec.json).
static class Program
{
    static int failed, passed;

    static void Check(bool ok, string what)
    {
        if (ok) passed++;
        else { failed++; Console.WriteLine("FAILED: " + what); }
    }

    static void Near(double got, double want, string what) => Check(Math.Abs(got - want) < 1e-9, $"{what}: {got} (want {want})");

    // BC's clock effects on the kit's SnesStatusClock hooks, as BcJunctionClock sets them
    static void Clock()
    {
        var rng = new Random(1);
        // count steps and ticks over n visits; ticks land at once (the plugin's tick functions clear Due*)
        (int steps, int poison, int regen) Run(PrKit.Ff6.SnesStatus s, Func<int, int> add, Func<PrKit.Ff6.SnesStatusClock, char, char> kind, int visits)
        {
            var c = new PrKit.Ff6.SnesStatusClock(0) { AddFilter = add, StepKind = kind };
            int st = 0, p = 0, r = 0;
            for (int i = 0; i < visits; i++)
            {
                if (c.Visit(s, rng)) st++;
                if (c.DuePoison) { p++; c.DuePoison = false; }
                if (c.DueRegen) { r++; c.DueRegen = false; }
            }
            return (st, p, r);
        }
        var none = PrKit.Ff6.SnesStatus.None;
        var vanilla = Run(none, null, null, 1024);
        var font = Run(none, a => M.TimeAdd(a, 1), null, 1024);
        var sink = Run(none, a => M.TimeAdd(a, -1), null, 1024);
        Check(vanilla.steps == 256 && font.steps == 320 && sink.steps == 192, $"time font/sink steps {vanilla.steps}/{font.steps}/{sink.steps} (want 256/320/192)");
        // Miasma: a Poisoned fighter, a holder whose roll always hits: every step is a Poison step (vanilla 1 in 8)
        char Miasma(PrKit.Ff6.SnesStatusClock c, char k)
        {
            bool poisoned = (c.Statuses & PrKit.Ff6.SnesStatus.Poison) != 0;
            int slot = k == 'R' ? 0 : k == 'P' ? 2 : 1;
            int now = M.StepSlot(slot, poisoned, 1, false, n => 0);
            return now == slot ? k : now == 0 ? 'R' : now == 2 ? 'P' : k;
        }
        var pv = Run(PrKit.Ff6.SnesStatus.Poison, null, null, 1024);
        var pm = Run(PrKit.Ff6.SnesStatus.Poison, null, Miasma, 1024);
        Check(pv.poison == 32 && pm.poison >= 250, $"miasma: poison ticks {pv.poison} -> {pm.poison} (want 32 -> ~255)");
        // Regenerator on a fighter with Regen and Poison: every step a Regen step; the table's Poison slots are lost
        char Regen(PrKit.Ff6.SnesStatusClock c, char k)
        {
            bool regen = (c.Statuses & PrKit.Ff6.SnesStatus.Regen) != 0;
            int slot = k == 'R' ? 0 : k == 'P' ? 2 : 1;
            int now = M.StepSlot(slot, false, 0, regen, n => 0);
            return now == slot ? k : now == 0 ? 'R' : now == 2 ? 'P' : k;
        }
        var both = PrKit.Ff6.SnesStatus.Poison | PrKit.Ff6.SnesStatus.Regen;
        var rv = Run(both, null, null, 1024);
        var rr = Run(both, null, Regen, 1024);
        Check(rv.regen >= 63 && rv.regen <= 64 && rv.poison == 32 && rr.regen >= 250 && rr.poison == 0,
              $"regenerator: regen {rv.regen} -> {rr.regen}, poison {rv.poison} -> {rr.poison} (want 64 -> ~255, 32 -> 0)");
    }

    static int Main()
    {
        // element step: Boost x1.5, Font x1.25 each, Sink x0.75 each (BC's per-holder floors aside)
        Near(M.ElementFactor(true, 1, 1), 1.40625, "boost + font + sink");
        Near(M.ElementFactor(false, 2, 0), 1.5625, "two fonts");
        Near(M.ElementFactor(false, 0, 0), 1, "nothing");
        // Loner: characters 4 -> x0.5, alone x2; monsters 5-6 -> 0
        Near(M.Loner(4), 0.5, "loner 4"); Near(M.Loner(1), 2, "loner alone"); Near(M.Loner(6), 0, "loner 6");
        // Crisis Arm: HP mod 10 / 4
        Near(M.CrisisArm(1237), 1.75, "crisis 1237"); Near(M.CrisisArm(990), 0, "crisis 990");
        Near(M.AtmaForce(500, 1000), 0.75, "atma half");
        Near(M.Vorpal(0, false), 256.0 / 255, "vorpal def 0");
        Near(M.ReflectBoost(1), 1, "reflect boost 1"); Near(M.ReflectBoost(3), 1.5625, "reflect boost 3");
        // levels
        Check(M.JuggernautStart(99) == 50 && M.JuggernautStart(1) == 1, "juggernaut start");
        Check(M.BurstStart(30) == 45 && M.BurstStart(85) == 99, "burst start (PR cap 99)");
        Check(M.JuggernautStep(40, 50, n => 5) == 41, "juggernaut below base climbs");
        Check(M.JuggernautStep(52, 50, n => 1) == 52 && M.JuggernautStep(52, 50, n => 0) == 53, "juggernaut above base: 1/(over+1)");
        Check(M.BurstStep(60, 50, n => 5) == 59, "burst above base sinks");
        Check(M.BurstStep(45, 50, n => 1) == 45 && M.BurstStep(45, 50, n => 0) == 44, "burst below base: 1/(under+2)");
        Check(M.Discordant(47, 1234) == 44, "discordant 47, HP 1234");
        Check(M.Discordant(7, 1230) == 1, "discordant to 0 -> 1");
        // after a hit
        Check(M.CorrosiveLoss(100, 1000) == 25 && M.CorrosiveLoss(5000, 300) == 75, "corrosive");
        Check(M.SplitShare(401, false) == 100 && M.SplitShare(401, true) == 0, "damage split");
        Check(M.DistributeShare(1000, 800, 1000, 3) == 266, "distribute");
        Check(M.VampireHeal(500, 900, 1000, false) == 100 && M.VampireHeal(500, 900, 1000, true) == 625, "vampire");
        Check(M.MeatboneReady(125, 1000) && !M.MeatboneReady(126, 1000), "meatbone 1/8");
        Check(M.QuickeningCost(10, 10) == 15 && M.QuickeningCost(15, 10) == 23 && M.QuickeningCost(200, 10) == 255, "quickening chain");
        Check(M.DeathsDoor(1000, 400, false) == 600 && M.DeathsDoor(8000, 0, true) == 1000, "death's door");
        // MP
        Check(M.BloodMageMp(9999) == 999 && M.BloodMageMp(800) == 100, "blood mage MP");
        Check(M.GoldMageMp(3200) == 100 && M.GoldMageMp(1000000) == 999, "gold mage MP");
        Check(M.MpTick(100, 1000, 200) == 20 && M.MpTick(-3, 1000, 10) == -1, "MP regen tick");
        // rewards
        Check(M.GilgamPay(500, M.MaxGil - 10) == 10 && M.GilgamPay(500, 0) == 500, "gilgam heart cap");
        Check(M.DoubleApExtra(10) == 10 && M.DoubleApExtra(200) == 55 && M.DoubleApExtra(0) == 0, "double AP");
        Check(M.PoachItem(1, 2, 3, 4, false, 0, 31) == 1 && M.PoachItem(1, 2, 3, 4, false, 0, 32) == 2, "poach steal pair");
        Check(M.PoachItem(1, 2, 3, 4, false, 1, 200) == 4 && M.PoachItem(1, 2, 3, 4, true, 1, 200) == 3, "poach drop pair / imp harvest");
        Check(M.StealHits(30, 20, 59) && !M.StealHits(30, 20, 60), "add steal odds");
        // esper spells: slot 5 down, wanted class only, rate / 64
        var sp = new List<(int, int, bool)> { (10, 101, true), (5, 102, false), (20, 103, true) };
        Check(M.EsperSpell(sp, true, 0) == 103 && M.EsperSpell(sp, true, 19) == 103, "esper spell: last slot first");
        Check(M.EsperSpell(sp, true, 20) == 101 && M.EsperSpell(sp, true, 30) == 0, "esper spell: then the next, then none");
        Check(M.EsperSpell(sp, false, 4) == 102 && M.EsperSpell(sp, false, 5) == 0, "esper spell: ally class");
        // taunt
        Check(M.TauntPick(2, true, true, 3) == 1, "taunt: a monster's act re-picks");
        Check(M.TauntPick(2, false, true, 0) == -1 && M.TauntPick(0, true, false, 0) == -1, "taunt: kept");
        // the status clock: Time Font/Sink (spec: normal +1 -> 80, +2 -> 100, -1 -> 48, -2 -> 36; Haste +1 -> 105; cap 255)
        Check(M.TimeAdd(64, 1) == 80 && M.TimeAdd(64, 2) == 100 && M.TimeAdd(64, -1) == 48 && M.TimeAdd(64, -2) == 36, "time font/sink");
        Check(M.TimeAdd(84, 1) == 105 && M.TimeAdd(64, 0) == 64 && M.TimeAdd(200, 3) == 255, "time font haste / cap");
        // Miasma / Regenerator: the step's table slot
        Check(M.StepSlot(4, true, 2, false, n => n == 4 ? 1 : 0) == 4, "miasma misses");
        Check(M.StepSlot(4, true, 2, false, n => 0) == 2, "miasma hits");
        Check(M.StepSlot(2, false, 2, true, n => 0) == 0, "regenerator");
        Check(M.StepSlot(5, false, 3, false, n => 0) == 5, "no poison: miasma does nothing");
        // Overheal: 900/1000 healed 500 -> 1000 + (400+2)/4 = 1100; a heal that doesn't pass max is a plain heal
        Check(M.OverhealHp(900, 500, 1000) == 1100 && M.OverhealHp(500, 300, 1000) == 800, "overheal");
        Check(M.OverhealHp(1100, 3000, 1000) == 1100 + (1000 + 2) / 4, "overheal from above max: excess capped at max HP");
        Clock();
        Console.WriteLine($"bc junction math: {passed} passed, {failed} failed");
        return failed == 0 ? 0 : 1;
    }
}
