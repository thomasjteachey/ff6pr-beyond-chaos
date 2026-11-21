using HarmonyLib;
using PrKit.Ff6;   // SnesAi: the kit's FF6 AI interpreter; SnesAiHost: the battle it runs in

namespace BeyondChaos.PR
{
    // Every monster runs its Beyond Chaos script the way the SNES runs it: the seed carries each monster's
    // SNES AI as BC left it (BC rewrites specials and some scripts: tools/port_ai.py snes_ai_data), and the
    // kit's interpreter (PrKit/Ff6/SnesAi*, written for Worlds Collide) runs it in the PR's battles.
    static class BcEnemyAi
    {
        sealed class Bc : SnesAiMod
        {
            public override SnesAiData Data => BcSeeds.Active?.SnesAi;
            public override bool Active => Plugin.BcMode && Data != null;
            public override string Tag => "bc";
            public override bool ScriptStatusEffects => false;   // as Worlds Collide: on once BC's fights are tested with them
        }

        public static void Patch(Harmony h) => SnesAiHost.Patch(h, new Bc());
        internal static void Update() => SnesAiHost.Update();
        internal static int Turns => SnesAiHost.Turns;
        internal static string LastTurn => SnesAiHost.LastTurn;
    }
}
