using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Last.Data.Master;
using Last.Data.User;
using PrKit;
using PrKit.Ff6;

namespace BeyondChaos.PR
{
    // Beyond Chaos's skills when it moves commands (the kit's StartSkills / SnesRages / SnesNaturalMagic). In the SNES
    // SwdTech, Blitz, Lore, Dance and Rage knowledge is the party's; BC's code makes it so for any holder of the command
    // (randomizer.py:744-791, 5564-5570; review: bc-skills-review.md in the BC lead's notes). Here:
    //  `o` (shuffle commands):
    //    - SwdTech / Blitz: every Bushido / Blitz learning row (Cyan's and Sabin's jobs) at or below the highest level
    //      any owned character reached, to the command's holders (BC drops the Cyan-/Sabin-only checks);
    //    - Lores: every lore cast in a won battle (any caster, monster versions through the game's
    //      exchange_learning_ability table, lores through Rage too), to the Lore holders;
    //    - Dances: a won battle teaches its background's dance, to the Dance holders;
    //    - BC's starting Lores (ED/F564, rerolled: bc_seed.json start_lores), to the Lore holders;
    //    - every set shared among the holders (StartSkills.Sync), on joins and every few seconds in the field.
    //  `o` or `w`: a won battle teaches its formation's rages (BC's auto_learn_rage; the kit's SnesRages hook).
    //  Learned while nobody holds the command: kept on an owned character (the save keeps it; the sync shares it with a
    //  later holder), as the SNES keeps the party's set.
    //  natural magic BC changed (bc_seed.json natural_moved): new list taught by level, the PR's built-ins it no longer
    //  gives un-learned (kit SnesNaturalMagic).
    // Not here: `o`'s empty starting rage list (the PR builds Gau's rages into him), Gau's auto-recruit (an event patch).
    static class BcSkills
    {
        const int BushidoJob = 3, BlitzJob = 6, LoreFirst = 140, LoreLast = 163, DanceFirst = 164;
        static int frames;
        internal static string LastSync = "", LastNatural = "", LastWin = "";

        static bool On(params string[] flags)
        {
            var s = BcSeeds.Active;
            if (!Plugin.BcMode || s == null) return false;
            var have = (s.Flags ?? "").Split(' ');
            return flags.Any(f => have.Contains(f));
        }

        public static void Patch(Harmony h)
        {
            StartSkills.Tag = SnesRages.Tag = SnesNaturalMagic.Tag = "[bc]";
            SnesRages.LearnRagesOnWin = () => On("o", "w");
            SnesRages.Apply(h, ownTriggers: true);
            Hooks.Patch(h, typeof(Last.Systems.BattleResultProvider), "Genelate", typeof(BcSkills), prefix: nameof(Result_Prefix));
            PrKit.Harness.Register("bcskills", _ => Check(),
                "bcskills: BC's shared skills (o), rages after wins (o/w), lores and dances after wins (o): per character, what each set counts");
        }

        // --- a won battle (the result screen's data): its lores and its background's dance (`o`) ----------------------
        public static void Result_Prefix(global::Last.Battle.BattleSkillUpInformation battleSkillUpInformation)
        {
            if (!On("o")) return;
            try
            {
                var lores = new HashSet<int>();
                var list = battleSkillUpInformation?.BattleActLogDataList;
                var exchange = new Dictionary<int, int>();
                var table = global::Misc.MiscAssetDescAccessor.Desc?.exchange_learning_ability;
                if (table != null)
                    foreach (var e in table) if (e != null) exchange[e.before_ability_id] = e.after_ability_id;
                if (list != null)
                    for (int i = 0; i < list.Count; i++)
                    {
                        var abilities = list[i]?.BattleActData?.abilityList;
                        if (abilities == null) continue;
                        for (int k = 0; k < abilities.Count; k++)
                        {
                            var a = abilities[k];
                            if (a == null) continue;
                            int id = exchange.TryGetValue(a.Id, out int lore) ? lore : a.Id;
                            if (id >= LoreFirst && id <= LoreLast) lores.Add(id);
                        }
                    }
                var notes = new List<string>();
                if (lores.Count > 0) notes.Add($"lores {string.Join(",", lores)} ({TeachOrKeep(StartSkills.Lore, lores)} taught)");
                int dance = BcJunctionExtra.Dance();
                if (dance >= 0) notes.Add($"dance {DanceFirst + dance} ({TeachOrKeep(StartSkills.Dance, new[] { DanceFirst + dance })} taught)");
                if (notes.Count > 0) { LastWin = string.Join("; ", notes); Plugin.L.LogInfo("[bc] won battle: " + LastWin); }
            }
            catch (Exception e) { Hooks.WarnOnce("bc-skills-win", e); }
        }

        // to the command's holders; with none, kept on an owned character (the save keeps it, the sync shares it later)
        static int TeachOrKeep(int command, IEnumerable<int> ids)
        {
            var list = ids.ToList();
            if (StartSkills.Holders(command).Count > 0) return StartSkills.Teach(command, list, queue: false);
            var keeper = StartSkills.Owned().FirstOrDefault();
            if (keeper == null) return 0;
            return list.Count(id => !StartSkills.Knows(keeper, id) && StartSkills.Teach(keeper, id));
        }

        // the queued rages (SnesRages, won while nobody held Rage), kept on an owned character
        static void KeepPending()
        {
            foreach (var command in new[] { StartSkills.Rage, StartSkills.Lore, StartSkills.Dance })
                if (StartSkills.Pending(command) > 0 && StartSkills.Holders(command).Count == 0 && StartSkills.Owned().Any())
                    TeachOrKeep(command, StartSkills.TakePending(command));
        }

        // SwdTech / Blitz: the learning rows of Cyan's / Sabin's jobs at or below the highest owned level, to the holders
        static int ByHighestLevel()
        {
            var owned = StartSkills.Owned().ToList();
            if (owned.Count == 0) return 0;
            int top = owned.Max(c => c.Parameter.ConfirmedLevel());
            var mm = MasterManager.Instance;
            var want = new Dictionary<int, List<int>> { [StartSkills.Bushido] = new List<int>(), [StartSkills.Blitz] = new List<int>() };
            foreach (var kv in mm.GetList<Learning>())
            {
                var l = kv.Value;
                if (l == null || l.TypeId != 1 || l.Value1 > top || (l.JobId != BushidoJob && l.JobId != BlitzJob)) continue;
                var content = mm.GetData<Content>(l.ContentId);
                if (content == null || content.TypeId != 4) continue;
                int id = content.TypeValue, command = l.JobId == BushidoJob ? StartSkills.Bushido : StartSkills.Blitz;
                if ((command == StartSkills.Bushido && id >= 124 && id <= 131) || (command == StartSkills.Blitz && id >= 132 && id <= 139))
                    want[command].Add(id);
            }
            return want.Sum(kv => kv.Value.Count > 0 ? StartSkills.Teach(kv.Key, kv.Value, queue: false) : 0);
        }

        // the seed's changed natural magic on the owned characters it concerns
        static void Natural(HashSet<int> moved)
        {
            var notes = new List<string>();
            foreach (var c in StartSkills.Owned().Where(c => moved.Contains(c.characterStatusId)).ToList())
            {
                int level = c.Parameter.ConfirmedLevel();
                var taught = SnesNaturalMagic.Natural(c, level).Where(id => !StartSkills.Knows(c, id) && StartSkills.Teach(c, id)).ToList();
                if (taught.Count > 0) notes.Add($"{c.characterStatusId} at {level} learned [{string.Join(" ", taught)}]");
            }
            var gone = SnesNaturalMagic.RepairBuiltIns(id => moved.Contains(id), c => SnesNaturalMagic.Natural(c, c.Parameter.ConfirmedLevel()), null);
            if (gone != "") notes.Add($"built-ins un-learned {gone}");
            if (notes.Count == 0) return;
            LastNatural = string.Join("; ", notes);
            Plugin.L.LogInfo("[bc] natural magic: " + LastNatural);
        }

        static bool Busy()
        {
            if (Harness.InBattle) return true;
            try { return global::Last.Interpreter.Integrator.Instance?.IsMainCoreAlive() ?? false; }
            catch (Exception) { return false; }
        }

        // per frame (BcData.Update): every ~3 s in the field (not in battle or during an event)
        public static void Update()
        {
            if (++frames % 180 != 0 || !Plugin.BcMode || BcSeeds.Active == null || Busy()) return;
            var s = BcSeeds.Active;
            if (s.NaturalMoved.Count > 0)
                try { Natural(s.NaturalMoved); } catch (Exception e) { Hooks.WarnOnce("bc-natural", e); }
            bool o = On("o"), w = On("w");
            if (!o && !w) return;
            try
            {
                var notes = new List<string>();
                if (o)
                {
                    int n = 0;
                    if (s.StartLores.Count > 0) n += StartSkills.Teach(StartSkills.Lore, s.StartLores, queue: false);
                    n += ByHighestLevel();
                    if (n > 0) notes.Add($"{n} start lores / SwdTech / Blitz taught");
                }
                KeepPending();
                var sync = o ? StartSkills.Sync() : StartSkills.Sync(new[] { StartSkills.Rage });
                if (sync != "") notes.Add(sync);
                if (notes.Count > 0) LastSync = string.Join("; ", notes);
            }
            catch (Exception e) { Hooks.WarnOnce("bc-skills", e); }
        }

        // what QA checks: per owned character its level, commands and each set's count; whether each set is shared
        static string Check()
        {
            var s = BcSeeds.Active;
            if (s == null) return "bcskills: no seed";
            var sets = StartSkills.Sets;
            string Count(OwnedCharacterData c, int first, int last) =>
                c.OwnedAbilityList == null ? "0" : c.OwnedAbilityList.ToArray().Count(a => a?.Ability != null && a.Ability.Id >= first && a.Ability.Id <= last && a.SkillLevel >= 100).ToString();
            var owned = StartSkills.Owned().ToList();
            var chars = owned.Select(c =>
                $"{c.characterStatusId}:Lv{c.Parameter.ConfirmedLevel()}[{string.Join(",", c.CommandList?.ToArray().Where(x => x != null).Select(x => x.Id) ?? Enumerable.Empty<int>())}]" +
                $" Bu{Count(c, 124, 131)}/Bl{Count(c, 132, 139)}/Lo{Count(c, 140, 163)}/Da{Count(c, 164, 171)}/Ra{Count(c, 800, 1054)}");
            var shared = sets.Select(x =>
            {
                var holders = StartSkills.Holders(x.Command);
                if (holders.Count == 0) return $"{x.Command}: no holder";
                var known = new HashSet<int>(owned.SelectMany(c => c.OwnedAbilityList?.ToArray() ?? new OwnedAbility[0])
                    .Where(a => a?.Ability != null && a.Ability.Id >= x.First && a.Ability.Id <= x.Last && a.SkillLevel >= 100).Select(a => a.Ability.Id));
                bool all = holders.All(h => known.All(id => StartSkills.Knows(h, id)));
                return $"{x.Command}: shared {(all ? "yes" : "no")} ({known.Count})";
            });
            return $"bcskills: share {(On("o") ? "on" : "off")}, rages on wins {(On("o", "w") ? "on" : "off")}; wins {SnesRages.Wins}; " +
                   $"chars [{string.Join(" | ", chars)}]; sets [{string.Join("; ", shared)}]; " +
                   $"last win: {LastWin}; last rages: {SnesRages.Last}; last sync: {LastSync}; start lores {s.StartLores.Count}; " +
                   $"natural magic changed for [{string.Join(",", s.NaturalMoved)}]: {LastNatural}";
        }
    }
}
