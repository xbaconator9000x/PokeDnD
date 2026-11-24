"""Source regression for native stack probes at high-risk combat phases.

The probes are read-only and do not claim whole-program high-water coverage.
"""
from pathlib import Path
import re
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "integration/emerald/pokednd_overworld.c"


class NativeCombatStackSamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text()

    def test_combat_phases_sample_before_side_effects(self):
        for signature in (
            "static void StartImpact(int target, D20Attack attack)",
            "static void DisplayBattleResult(void)",
            "static void MoveSelected(u16 newKeys)",
        ):
            with self.subTest(signature=signature):
                body = self.source.split(signature + "\n{", 1)[1].split("\n}", 1)[0]
                self.assertRegex(body, r"^\s*#ifdef POKEDND_NATIVE_REPLAY_ROCKET\s+"
                                 r"/\*[^*]*\*/\s+PokeDnD_SampleSystemStack\(\);"
                                 r"\s+#endif")
                self.assertLess(body.index("PokeDnD_SampleSystemStack();"),
                                body.index("    if ") if "    if " in body else len(body))

    def test_no_stack_paint_or_memset_in_sampler(self):
        sampler = self.source.split("static void PokeDnD_SampleSystemStack(void)", 1)[1].split(
            "#endif /* POKEDND_NATIVE_REPLAY_ROCKET */", 1)[0]
        self.assertIn('mov %0, sp', sampler)
        self.assertNotRegex(sampler, r"memset\s*\(|\*\s*\(\s*(?:volatile\s+)?u(?:8|16|32)\s*\*")
        self.assertIn("sp - low < 256u", sampler)
        self.assertIn("gPokeDnDStackSampleInvalid = 1", sampler)

    def test_probes_are_replay_only(self):
        for signature in (
            "static void StartImpact(int target, D20Attack attack)",
            "static void DisplayBattleResult(void)",
            "static void MoveSelected(u16 newKeys)",
        ):
            body = self.source.split(signature + "\n{", 1)[1].split("\n}", 1)[0]
            self.assertEqual(body.count("PokeDnD_SampleSystemStack();"), 1)
            self.assertEqual(body.count("#ifdef POKEDND_NATIVE_REPLAY_ROCKET"), 1)


if __name__ == "__main__":
    unittest.main()
