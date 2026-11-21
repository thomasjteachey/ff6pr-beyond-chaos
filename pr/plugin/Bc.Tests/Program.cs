using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using PrKit.Seeds;

// Beyond Chaos's flags on the kit's flag model: presets round-trip, every row the screen offers steps and
// toggles into a flag string BC's parser accepts (tests/test_bc.py reads the cases this writes).
static class Program
{
    static int failures;

    static void Check(bool ok, string what)
    {
        if (ok) return;
        failures++;
        Console.WriteLine("FAIL " + what);
    }

    static int Main(string[] args)
    {
        var path = args.Length > 0 ? args[0] : Path.Combine("..", "BcPlugin", "bc_flags.json");
        var outPath = args.Length > 1 ? args[1] : "bc_flags_cases.tsv";
        var set = FlagSet.Load(File.ReadAllText(path));
        Check(set.Style == FlagStyle.Colon, "BC's flags use the colon style");
        Console.WriteLine($"BC {set.Version}: {set.Flags.Count} flags, {set.Sections.Count} sections, {set.Presets.Count} presets, {set.Modes.Count} modes");
        var cases = new List<(string Name, string Flags)>();

        // presets: parse -> serialize keeps every flag and value, nothing unknown
        foreach (var p in set.Presets)
        {
            var v = new FlagValues(set);
            v.Parse(p.Value);
            Check(v.Unknown.Count == 0, $"preset {p.Key}: unknown tokens {string.Join(" ", v.Unknown)}");
            var again = v.Serialize();
            var want = new HashSet<string>(p.Value.Split(' ', StringSplitOptions.RemoveEmptyEntries).Select(t => t.ToLowerInvariant()));
            var have = new HashSet<string>(again.Split(' ', StringSplitOptions.RemoveEmptyEntries));
            Check(want.SetEquals(have), $"preset {p.Key}: {string.Join(" ", want.Except(have))} lost, {string.Join(" ", have.Except(want))} added");
            var v2 = new FlagValues(set);
            v2.Parse(again);
            Check(v2.Serialize() == again, $"preset {p.Key}: serialize is stable");
            cases.Add(("preset " + p.Key, again));
        }

        // every flag: on with its default, and each value it steps through (with New Player's flags around it)
        var basis = set.Presets.TryGetValue("New Player", out var np) ? np : "";
        foreach (var d in set.Flags.Values)
        {
            var v = new FlagValues(set);
            v.Parse(basis);
            v.Set(d.Flag);
            Check(v.IsOn(d.Flag), $"{d.Flag} turns on");
            cases.Add(($"{d.Flag} on", v.Serialize()));
            if (d.Nargs == 0) { v.Step(d, 0, -1); Check(!v.IsOn(d.Flag), $"{d.Flag} turns off"); continue; }
            var seen = new HashSet<string>();
            for (int i = 0; i < 300 && v.IsOn(d.Flag); i++)
            {
                var value = v.Values(d.Flag).FirstOrDefault() ?? "";
                if (!seen.Add(value)) break;
                cases.Add(($"{d.Flag}={value}", v.Serialize()));
                v.Step(d, 0, +1, d.Type == FlagType.Float ? 7 : 1);
            }
            // a long press left stops at the first value; the next press goes below it (BC's special
            // value such as "random", then off)
            v.Step(d, 0, -1, 100000);
            Check(v.IsOn(d.Flag), $"{d.Flag}: a long press left stops at the first value");
            if (d.Special != null && v.Values(d.Flag).FirstOrDefault() != d.Special)
            {
                v.Step(d, 0, -1);
                Check(v.Values(d.Flag).FirstOrDefault() == d.Special, $"{d.Flag}: below its range is {d.Special}");
            }
            v.Step(d, 0, -1);
            Check(!v.IsOn(d.Flag), $"{d.Flag}: below its first value is off");
        }

        // conflicts: turning a flag on turns its conflicts off
        foreach (var d in set.Flags.Values.Where(d => d.Conflicts.Length > 0))
            foreach (var c in d.Conflicts.Where(set.Flags.ContainsKey))
            {
                var v = new FlagValues(set);
                v.Set(c);
                v.Set(d.Flag);
                Check(!v.IsOn(c) && v.IsOn(d.Flag), $"{d.Flag} turns {c} off");
            }

        File.WriteAllLines(outPath, cases.Select(c => c.Name + "\t" + c.Flags));
        Console.WriteLine($"{cases.Count} flag strings -> {outPath}; {failures} failures");
        return failures == 0 ? 0 : 1;
    }
}
