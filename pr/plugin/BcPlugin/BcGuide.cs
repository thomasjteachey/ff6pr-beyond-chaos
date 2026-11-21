using System;
using Last.Management;
using PrKit;
using UnityEngine;

namespace BeyondChaos.PR
{
    // The seed's guide for someone new to Beyond Chaos (tools/bc_guide.py: the script sc_bc_guide and its
    // messages, made with the seed), shown once, right after the opening's controls tutorial (the user,
    // 2026-11-20): the opening's last scene (sc_e_0001_5, Narshe's outskirts, game map 3) ends with
    // ShowHelpAndExit, the field help; once that closes and nothing else runs, the guide's script runs there
    // in the game's own message window, a question first (No skips it). No hooks: the runner watches the
    // interpreter's script and the field help.
    static class BcGuide
    {
        internal const string Opening = "sc_e_0001_5", Script = "sc_bc_guide";
        internal const int OpeningMap = 3;     // Map_20010, where the guide's script is listed (bc_live.write_baseline)
        const float NoHelpAfter = 3f;          // the scene ended and no help opened: the guide anyway

        enum Step { Idle, Opening, Help, Ready }
        static Step step;
        static float ended = -1;
        static bool armed = true;              // once per run of the opening's scene (its name stays after it ends)
        internal static string Last = "idle";
        internal static int Started;

        static bool Wanted => Plugin.BcMode && (BcSeeds.Active?.GuideMessages ?? 0) > 0;

        static bool HelpOpen()
        {
            try { return FieldHelpClient.Instance()?.IsOpen() ?? false; }
            catch (Exception) { return false; }
        }

        internal static void Update()
        {
            switch (step)
            {
                case Step.Idle:
                    if (MapScripts.Current != Opening) armed = true;
                    else if (armed && MapScripts.Busy && Wanted)
                    {
                        armed = false;
                        step = Step.Opening;
                        ended = -1;
                        Note("the opening's last scene runs");
                    }
                    break;
                case Step.Opening:
                    if (HelpOpen()) { step = Step.Help; Note("its controls tutorial is open"); }
                    else if (MapScripts.Busy) ended = -1;
                    else if (ended < 0) ended = Time.realtimeSinceStartup;
                    else if (Time.realtimeSinceStartup - ended > NoHelpAfter) { step = Step.Ready; Note("the scene ended without its controls tutorial"); }
                    break;
                case Step.Help:
                    if (!HelpOpen()) { step = Step.Ready; Note("the controls tutorial closed"); }
                    break;
                case Step.Ready:
                    if (MapScripts.Busy || HelpOpen()) break;
                    step = Step.Idle;
                    if (!Wanted) { Note("no guide in this seed"); break; }
                    if (MapScripts.MapId != OpeningMap) { Note($"not shown: on map {MapScripts.MapId}, its script is in map {OpeningMap}'s list"); break; }
                    Start();
                    break;
            }
        }

        // runs the guide's script now (the harness's bcguide; the opening's flow above)
        internal static string Start()
        {
            var why = MapScripts.Start(Script);
            if (why != null) { Note("not shown: " + why); return "error: " + why; }
            Started++;
            Note($"shown ({BcSeeds.Active?.GuideMessages} messages)");
            return $"guide started: {BcSeeds.Active?.GuideMessages} messages";
        }

        static void Note(string what)
        {
            Last = what;
            Plugin.L.LogInfo("[bc] guide: " + what);
        }

        internal static string State() => $"guide {step}: {Last}" + (HelpOpen() ? "; field help open" : "");
    }
}
