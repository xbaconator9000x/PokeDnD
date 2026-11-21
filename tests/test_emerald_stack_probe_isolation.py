"""Regression: normal Emerald adapter must not reference replay-only linker symbols."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integration/emerald/pokednd_overworld.c"
PATCHER = ROOT / "integration/emerald/apply.py"


class StackProbeBuildIsolationTests(unittest.TestCase):
    def test_linker_symbols_and_sampler_are_replay_only(self):
        source = SOURCE.read_text(encoding="utf-8")
        begin = source.index("#ifdef POKEDND_NATIVE_REPLAY_ROCKET\n/* Read-only stack sampling")
        end = source.index("#endif /* POKEDND_NATIVE_REPLAY_ROCKET */", begin)
        probe = source[begin:end]
        self.assertIn("extern u8 __pokednd_stack_low[];", probe)
        self.assertIn("extern u8 __pokednd_stack_top[];", probe)
        self.assertIn('mov %0, sp', probe)
        self.assertNotIn("= 0xA5", probe)
        call = source.index("    PokeDnD_SampleSystemStack();")
        self.assertEqual(source[:call].splitlines()[-1],
                         "#ifdef POKEDND_NATIVE_REPLAY_ROCKET")
        self.assertEqual(source[call:].splitlines()[1], "#endif")

    def test_replay_flag_and_linker_patching_are_coupled(self):
        patcher = PATCHER.read_text(encoding="utf-8")
        self.assertIn('stack_modified, linker_modified = instrument_stack(', patcher)
        self.assertIn('if field_replay:\n        stack_target.write_text(stack_modified)', patcher)
        self.assertIn('"#define POKEDND_NATIVE_REPLAY_ROCKET 1\\n"', patcher)
        self.assertIn('if field_replay:\n        # Replay-only source flag.', patcher)


if __name__ == "__main__":
    unittest.main()
