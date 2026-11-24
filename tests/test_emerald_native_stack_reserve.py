"""Source-level safety regression for replay-only native SP sampling.

The sampler reads the active SP; it must never paint an in-use stack.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integration/emerald/pokednd_overworld.c"


class NativeStackReserveTests(unittest.TestCase):
    def test_linker_bounded_sampler_fails_closed_at_low_water(self):
        source = SOURCE.read_text(encoding="utf-8")
        start = source.index("static void PokeDnD_SampleSystemStack(void)")
        end = source.index("#endif /* POKEDND_NATIVE_REPLAY_ROCKET */", start)
        sampler = source[start:end]
        self.assertIn('mov %0, sp', sampler)
        self.assertIn("sp < low || sp > top", sampler)
        self.assertIn("top - low < 1024u", sampler)
        self.assertIn("sp - low < 256u", sampler)
        self.assertIn("gPokeDnDStackSamplePeak > top - low - 256u", sampler)
        self.assertLess(sampler.index("sp < low || sp > top"),
                        sampler.index("sp - low < 256u"))
        self.assertLess(sampler.index("top - low < 1024u"),
                        sampler.index("gPokeDnDStackSamplePeak > top - low - 256u"))
        self.assertIn("gPokeDnDStackSampleInvalid = 1;", sampler)
        self.assertNotIn("strlo", sampler)
        self.assertNotIn("0xA5", sampler)

    def test_sampled_depth_is_not_claimed_as_full_high_water(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("NOT a whole-program", source)
        self.assertIn("depth = (u32)(top - sp);", source)


if __name__ == "__main__":
    unittest.main()
