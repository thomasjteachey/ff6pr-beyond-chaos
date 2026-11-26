using System.Collections.Generic;
using System.Linq;
using PrKit.Seeds;

namespace BeyondChaos.PR
{
    // The Beyond Chaos screen: the kit's options screen with BC's own rules. Seeds are numbers (BC keeps
    // the last 10 digits), a seed has a mode (Normal first; the cave modes later), and the mode decides
    // which flags may be on (BC's Mode.forced_flags / prohibited_flags). Every flag, ported or not, goes
    // to BC's own randomizer, so a seed is the one BC's exe makes from the same seed, mode and flags.
    sealed class BcScreen : SeedScreen
    {
        public BcScreen()
        {
            Name = "Beyond Chaos";
            Tag = "[bc screen]";
        }

        public override string Title => $"Beyond Chaos {Defs?.Version?.Replace("CE-", "CE ")}";
        public override string SeedHelp =>
            "The same seed, mode and flags make the same game as Beyond Chaos CE 6.1.3's own randomizer. " +
            "A: type a seed (digits). Left/right: a new random seed.";
        public override string PresetHelp => "Beyond Chaos's presets (New Player ... Race Insane) set every flag. Change any flag on the pages after this one (L/R).";
        public override string FlagsHelp => "A: edit as text (BC's own flag string: \"b c e ... expboost:2.0\"; Ctrl+V pastes).";
        public override string PortNote => "Pages marked * work partly in the Pixel Remaster port so far, dimmed ones not yet (BC's assembly, " +
                                           "events, sprites, music). Every flag still goes into BC's own seed.";
        public override string PortHelp(string port) => port switch
        {
            "no" => "Not in the Pixel Remaster port yet: Beyond Chaos still makes its seed with it, but its effect isn't in this game. ",
            "partly" => "Partly in the Pixel Remaster port (BC's data yes, its assembly / events not all yet). ",
            "na" => "No bearing on the Pixel Remaster: ",       // each such flag's help gives the reason (bc_flags_export PORT_NOTE)
            "later" => "Not in the Pixel Remaster port yet: ",
            _ => "",
        };

        // BC: int(seed) % 10**10; a random one as BC makes it when the seed is left blank (the time)
        public override string RandomSeed() => new System.Random().NextInt64(1, 10_000_000_000).ToString();
        public override bool SeedChar(char c) => char.IsDigit(c);
        public override string SeedRule => "Beyond Chaos seeds are numbers (up to 10 digits).";

        public override bool LooksLikeFlags(string text)
        {
            var v = new FlagValues(Defs);
            v.Parse(text);
            return v.Count > 0;
        }

        public override (string Name, string Value)[] ExtraArgs() => new[] { ("mode", modeName) };

        protected override void OnActiveSeed(SeedInfo s)
        {
            if (s is BcSeeds.Seed b) modeName = b.Mode;
        }

        protected override string SeedLabel(SeedInfo s) => s.SeedText;
        protected override string SeedValue(SeedInfo s) => s is BcSeeds.Seed b ? BcSeeds.ModeLabel(b.Mode) : "";
        protected override string SeedDetails(SeedInfo s) =>
            $"Mode: {(s is BcSeeds.Seed b ? BcSeeds.ModeLabel(b.Mode) : "?")}   Flags: {s.Flags}";

        Mode CurrentMode => Defs.Modes.FirstOrDefault(m => m.Name == modeName);

        protected override IEnumerable<Row> MoreMainRows()
        {
            var modes = Defs.Modes;
            if (modes.Count == 0) yield break;
            var mode = CurrentMode ?? modes[0];
            // bc_flags.json's modes say which are ported (tools/bc_flags_export.py PORTED_MODES); the others show what's coming
            var portedLabels = string.Join(", ", modes.Where(m => m.Ported).Select(m => m.Label));
            var later = string.Join(", ", modes.Where(m => !m.Ported).Select(m => m.Label));
            yield return new Row
            {
                Label = "Mode",
                Value = mode.Label + (mode.Ported ? "" : "  (not yet in this port)"),
                Help = mode.Help + (mode.Ported ? "" : $"  Not yet in the Pixel Remaster port (ported: {portedLabels})."),
                Step = (d, _) =>
                {
                    // the ported modes only
                    var ported = modes.Where(m => m.Ported).ToList();
                    if (ported.Count == 0) return;
                    int i = ported.FindIndex(m => m.Name == modeName);
                    i = ((i < 0 ? 0 : i) + d + ported.Count) % ported.Count;
                    modeName = ported[i].Name;
                },
                Activate = () => Say(modes.Count(m => m.Ported) > 1
                    ? "Left/right: change the mode." + (later.Length > 0 ? $" ({later}: later in this port.)" : "")
                    : $"Only {portedLabels} is in the port so far ({later} later)."),
            };
        }

        // a page after Seed: the current seed's guide (tools/bc_guide.py), one row a topic, its text below
        protected override int PageCount => base.PageCount + (ModOn() ? 1 : 0);
        protected override string PageTitle(int i) => i == 0 ? base.PageTitle(0) : i == 1 ? "Guide to this seed" : base.PageTitle(i - 1);
        protected override string PagePort(int i) => i <= 1 ? "yes" : base.PagePort(i - 1);
        protected override List<Row> PageRows(int i) => i == 0 ? base.PageRows(0) : i == 1 ? GuideRows() : base.PageRows(i - 1);
        protected override Section PageSection(int i) => i <= 1 ? null : base.PageSection(i - 1);

        List<Row> GuideRows()
        {
            var rows = new List<Row>();
            var s = BcSeeds.Active;
            if (s == null || s.Guide.Count == 0)
            {
                rows.Add(new Row { Header = true, Label = s == null ? "No seed yet: generate one on the Seed page." : "This seed was made before guides: generate it again." });
                return rows;
            }
            rows.Add(new Row { Header = true, Label = $"Seed {s.SeedText}: what's different (A or the help below explains each)" });
            foreach (var (title, lines) in s.Guide)
            {
                var text = string.Join(" ", lines);
                rows.Add(new Row { Label = title, Help = text, Indent = 1, Activate = () => Say(text, 12) });
            }
            return rows;
        }

        protected override string Blocked(FlagDef d)
        {
            var mode = CurrentMode;
            if (mode == null) return null;
            if (mode.Prohibited.Contains(d.Flag)) return $"Not with {mode.Label}";
            if (mode.Forced.Contains(d.Flag)) return $"Always on with {mode.Label}";
            return null;
        }
    }
}
