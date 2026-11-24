"""Source regression for native read-only stack samples at real encounter boundaries.

This does not assert a whole-program high-water mark or IRQ coverage.
"""
import re
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "integration/emerald/pokednd_overworld.c"


class NativeNestedStackSamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_nested_gameplay_boundaries_sample_sp(self):
        for signature in (
            "static void CleanupCombat(bool8 restorePlayer)",
            "static bool SpawnPikachu(void)",
            "static bool StartCombat(u8 scenario, u8 existingRocketId)",
            "static void RunEnemyPhases(void)",
        ):
            with self.subTest(signature=signature):
                pattern = (re.escape(signature) +
                           r"\s*\{\s*#ifdef POKEDND_NATIVE_REPLAY_ROCKET\s*"
                           r"/\*[^*]*\*/\s*PokeDnD_SampleSystemStack\(\);\s*#endif")
                self.assertRegex(self.source, pattern)

    def test_samples_are_read_only_and_guarded(self):
        body = self.source.split("static void PokeDnD_SampleSystemStack(void)", 1)[1].split(
            "#endif /* POKEDND_NATIVE_REPLAY_ROCKET */", 1)[0]
        self.assertIn('mov %0, sp', body)
        self.assertIn("sp - low < 256u", body)
        self.assertIn("gPokeDnDStackSampleInvalid = 1", body)
        self.assertNotRegex(body, r"\b(?:memset|CpuFill|DmaFill)\s*\(")

    def test_no_whole_program_watermark_claim(self):
        self.assertIn("NOT a whole-program", self.source)


if __name__ == "__main__":
    unittest.main()
