using System;
using System.Collections.Generic;
using System.Linq;

namespace BeyondChaos.PR
{
    // The numbers of Beyond Chaos's junction effects, game-free (no game types: plugin/BcJunction.Tests runs
    // them offline). Each is BC's rule as its patch has it (pr/data/bc_junction_spec.json); the hooks in
    // BcJunction*.cs read the game, call these and write the result back.
    public static class BcJunctionMath
    {
        // --- damage_modification (C2/336F) ----------------------------------------------------------------

        // one element of the strike: the attacker's Boost x1.5, then x1.25 per living Font holder, x0.75 per Sink
        public static double ElementFactor(bool boost, int fonts, int sinks) =>
            (boost ? 1.5 : 1) * Math.Pow(1.25, Math.Max(0, fonts)) * Math.Pow(0.75, Math.Max(0, sinks));

        // Loner: x1/2 x (5 - the living on the attacker's side, itself included), never below 0
        public static double Loner(int livingOnSide) => 0.5 * Math.Max(0, 5 - livingOnSide);

        // Crisis Arm: x(current HP mod 10) / 4
        public static double CrisisArm(int hp) => (Math.Max(0, hp) % 10) / 4.0;

        // Atma Force: x1.5 x the side's HP / its expected HP (here the side's max HP)
        public static double AtmaForce(long hp, long maxHp) => maxHp <= 0 ? 1 : 1.5 * Math.Max(0, hp) / maxHp;

        // Vorpal: the game's defense step (x(255 - Def)/256 + 1) and Protect's x170/256 undone
        public static double Vorpal(int def, bool protect) =>
            256.0 / Math.Max(1, 255 - Math.Min(Math.Max(def, 0), 254)) * (protect ? 256.0 / 170 : 1);

        // Reflect Boost: x1.25 for each holder past the first among the caster and the reflectors
        public static double ReflectBoost(int holders) => Math.Pow(1.25, Math.Max(0, holders - 1));

        // Repel <element> / Repel Nuke: the SNES element bit (0-7) whose Repel bounces the spell off the target, 8 for
        // Repel Nuke (a non-elemental spell with power), -1: it lands. Never a physical attack or a self-cast.
        // elements: the spell's PR attribute ids; elementAttr: SNES bit -> PR attribute id; repels(bit): the target's
        public static int RepelBit(IReadOnlyCollection<int> elements, IReadOnlyList<int> elementAttr, Func<int, bool> repels,
                                   bool repelNuke, int power, bool physical, bool self)
        {
            if (physical || self) return -1;
            elements ??= Array.Empty<int>();
            for (int b = 0; b < 8 && b < elementAttr.Count; b++)
                if (elements.Contains(elementAttr[b]) && repels(b)) return b;
            return elements.Count == 0 && power > 0 && repelNuke ? 8 : -1;
        }

        // --- a fighter falling in an act -----------------------------------------------------------------------

        // The act felled the unit: its HP went from above 0 to 0, or it took Wound. The PR gives Wound after the act's
        // HitCalc (BattleConditionController.UpdateConditionHp), so the act hub sees HP 0 without it (bc-selftest-4: a
        // party member killed with an Auto-Down holder beside it got no Phoenix Down; Immortal, the death casts, Poach
        // and VIP read the same).
        public static bool Fell(int hpBefore, int hpAfter, bool woundBefore, bool woundAfter) =>
            !woundBefore && hpBefore > 0 && (woundAfter || hpAfter <= 0);

        // --- levels (Juggernaut, Burst, Discordant) ------------------------------------------------------------

        public const int MaxLevel = 99;      // BC caps Burst at 127; the PR's levels stop at 99

        public static int JuggernautStart(int level) => Math.Max(1, (level + 1) / 2);
        public static int BurstStart(int level) => Math.Min(MaxLevel, Math.Min(127, level + (level + 1) / 2));

        // a status step's drift (after the step's 50% roll): `roll(n)` = a random 0..n-1
        public static int JuggernautStep(int level, int baseLevel, Func<int, int> roll) =>
            level <= baseLevel || roll(level - baseLevel + 1) == 0 ? Math.Min(MaxLevel, level + 1) : level;
        public static int BurstStep(int level, int baseLevel, Func<int, int> roll) =>
            level >= baseLevel || roll(baseLevel - level + 2) == 0 ? Math.Max(1, level - 1) : level;

        // Discordant: the target's level ends in the attacker's HP's last digit (0 -> 1)
        public static int Discordant(int level, int attackerHp)
        {
            int now = level / 10 * 10 + Math.Max(0, attackerHp) % 10;
            return now == 0 ? 1 : now;
        }

        // --- the status clock (C2/09E4, C2/5AD6) ----------------------------------------------------------------

        // Time Font / Sink: a fighter's status-clock add ($3ADD: 64, Haste 84, Slow 32) with n = living Fonts -
        // living Sinks: v = add x 32; each net Font v += v/4, each net Sink v = v/2 + v/4; add = min(255, v / 32)
        public static int TimeAdd(int add, int net)
        {
            long v = (long)add * 32;
            for (int i = 0; i < net; i++) v += v / 4;
            for (int i = 0; i > net; i--) v = v / 2 + v / 4;
            return (int)Math.Min(255, v / 32);
        }

        // Miasma / Regenerator: the 8-step table slot a status step reads (0 Regen/Sap, 2 Poison): a Poisoned
        // fighter's step becomes a Poison step if any living Miasma holder's 25% roll hits; then a Regen holder's
        // with Regenerator becomes a Regen step on a 50% roll. roll(n) = a random 0..n-1
        public static int StepSlot(int slot, bool poisoned, int miasmaHolders, bool regenerator, Func<int, int> roll)
        {
            if (poisoned)
                for (int i = 0; i < miasmaHolders; i++)
                    if (roll(4) == 0) { slot = 2; break; }
            if (regenerator && roll(2) == 0) slot = 0;
            return slot;
        }

        // --- after a hit ---------------------------------------------------------------------------------------

        // Corrosive: the max HP the target loses, from the damage it took (capped at its HP before the hit)
        public static int CorrosiveLoss(int damage, int hpBefore) => (Math.Min(damage, Math.Max(0, hpBefore)) + 2) >> 2;

        // Damage Split: the share of a non-lethal hit that goes back to the attacker
        public static int SplitShare(int damage, bool lethal) => lethal ? 0 : Math.Max(0, damage) / 4;

        // Distribute: healing past max HP, shared out among the other living allies (remainder lost)
        public static int DistributeShare(int heal, int hpBefore, int maxHp, int allies) =>
            allies <= 0 ? 0 : Math.Max(0, heal - (maxHp - hpBefore)) / allies;

        // Vampire: what the attacker gets back (Ravenous: x1.25 and no cap at its missing HP)
        public static int VampireHeal(int dealt, int hp, int maxHp, bool ravenous) =>
            ravenous ? dealt + dealt / 4 : Math.Max(0, Math.Min(dealt, maxHp - hp));

        // Overheal: HP after a heal past max: base = max(HP, max HP); + (the excess, at most max HP, + 2) / 4
        public static int OverhealHp(int hpBefore, int heal, int maxHp)
        {
            if (hpBefore + heal <= maxHp) return hpBefore + heal;          // a plain heal
            int baseHp = Math.Max(hpBefore, maxHp);
            int excess = Math.Max(0, Math.Min(hpBefore + heal - baseHp, maxHp));
            return Math.Min(65535, Math.Max(hpBefore, baseHp + ((excess + 2) >> 2)));
        }

        // Meatbone Cut: the holder was already at 1/8 of its max HP or less before the hit
        public static bool MeatboneReady(int hpBefore, int maxHp) => hpBefore <= maxHp / 8;

        // Quickening: the next echo's cost (x1.5 rounded up, at least the spell's own, at most 255)
        public static int QuickeningCost(int last, int spellCost) => Math.Min(255, Math.Max((last * 3 + 1) / 2, spellCost));

        // Death's Door: what a missed instant-death spell deals instead (a monster attacker: an eighth)
        public static int DeathsDoor(int attackerMaxHp, int attackerHp, bool monsterAttacker)
        {
            int d = attackerMaxHp - attackerHp;
            return Math.Min(9999, monsterAttacker ? d / 8 : d);
        }

        // --- MP --------------------------------------------------------------------------------------------------

        public static int BloodMageMp(int hp) => Math.Min(999, Math.Max(0, hp / 8));
        public static int GoldMageMp(int gil) => Math.Min(999, Math.Max(0, gil / 32));
        public static int BloodMageCost(int mp) => 8 * Math.Max(0, mp);
        public static int GoldMageCost(int mp) => 32 * Math.Max(0, mp);

        // MP Regen: a tick's HP change as the same share of max MP (at least 1)
        public static int MpTick(int hpDelta, int maxHp, int maxMp) =>
            hpDelta == 0 ? 0 : Math.Sign(hpDelta) * Math.Max(1, (int)Math.Round(Math.Abs(hpDelta) * (double)maxMp / Math.Max(1, maxHp)));

        // --- rewards ---------------------------------------------------------------------------------------------

        public const int MaxGil = 9999999;
        public static int GilgamPay(int hpLost, int gil) => Math.Max(0, Math.Min(hpLost, MaxGil - gil));

        // Double AP: the extra AP for the holder (the battle's x2, at most 255)
        public static int DoubleApExtra(int ap) => ap <= 0 ? 0 : Math.Max(0, Math.Min(ap, 255 - ap));

        // Poach / Imp Harvest: which of a monster's items (steal pair 50% / drop pair 50%; the rare one 32 in 256,
        // always for Imp Harvest); rolls: coin (0/1: 0 = steal pair), byte (0-255)
        public static int PoachItem(int stealRare, int stealCommon, int dropRare, int dropCommon, bool impHarvest, int coin, int byteRoll)
        {
            bool steal = coin == 0;
            int rare = steal ? stealRare : dropRare, common = steal ? stealCommon : dropCommon;
            return impHarvest || byteRoll < 32 ? rare : common;
        }

        // Add Steal: the PR's steal odds (50 + level - target level) / 128
        public static bool StealHits(int level, int targetLevel, int roll128) => roll128 < 50 + level - targetLevel;

        // --- Esper Magic / Esper Counter: a spell from the esper's list ---------------------------------------------

        // BC: r = 0..63; from the last slot down, the spells of the wanted class take their learn rate off r; the
        // first to take it below 0 is cast (so a spell's chance is its rate / 64). 0: none.
        public static int EsperSpell(IList<(int Rate, int Ability, bool Foe)> spells, bool foe, int r64)
        {
            int r = r64;
            for (int i = spells.Count - 1; i >= 0; i--)
            {
                if (spells[i].Foe != foe) continue;
                r -= spells[i].Rate;
                if (r < 0) return spells[i].Ability;
            }
            return 0;
        }

        // --- Taunt ----------------------------------------------------------------------------------------------

        // the new target index among `taunters` (-1: unchanged): a monster's act always picks among them, a party
        // member's only when its target isn't one already; pick = a random 0..count-1
        public static int TauntPick(int taunterCount, bool attackerIsMonster, bool targetIsTaunter, int pick) =>
            taunterCount == 0 || (!attackerIsMonster && targetIsTaunter) ? -1 : pick % taunterCount;
    }
}
