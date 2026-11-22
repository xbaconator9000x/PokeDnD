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
        # Every invocation must be inside its own replay-only preprocessor
        # guard. Comments between the guard and call are permitted, but
        # executable statements or a missing #endif are not.
        import re
        calls = list(re.finditer(r"(?m)^    PokeDnD_SampleSystemStack\(\);$", source))
        self.assertGreaterEqual(len(calls), 1)
        guarded = re.compile(
            r"(?m)^#ifdef POKEDND_NATIVE_REPLAY_ROCKET\n"
            r"(?:[ \t]*/\*[^\n]*\*/\n|[ \t]*//[^\n]*\n|[ \t]*\n)*"
            r"    PokeDnD_SampleSystemStack\(\);\n#endif$"
        )
        matches = list(guarded.finditer(source))
        self.assertEqual(len(matches), len(calls),
                         "Every native stack sample must have its own replay-only guard")
        # Mutation check: removing any replay guard must make the count fail.
        # This prevents an incorrectly escaped regex from silently passing.
        unguarded = source.replace(
            "#ifdef POKEDND_NATIVE_REPLAY_ROCKET\n"
            "    /* Observe the live system SP at this combat phase; never write stack memory. */\n",
            "    /* Observe the live system SP at this combat phase; never write stack memory. */\n",
            1,
        )
        self.assertNotEqual(len(list(guarded.finditer(unguarded))), len(calls))

    def test_stack_probe_fails_closed_on_corrupt_samples(self):
        source = SOURCE.read_text(encoding="utf-8")
        start = source.index("static void PokeDnD_SampleSystemStack(void)")
        end = source.index("#endif /* POKEDND_NATIVE_REPLAY_ROCKET */", start)
        probe = source[start:end]
        for guard in (
            "low >= top", "(low & 3u)", "(top & 3u)",
            "sp < low", "sp > top", "(sp & 3u)",
            "gPokeDnDStackSampleCount == 0xFFFFFFFFu",
            "gPokeDnDStackSamplePeak > top - low",
            "gPokeDnDStackSampleCount == 0u && gPokeDnDStackSamplePeak != 0u",
        ):
            self.assertIn(guard, probe)
        self.assertLess(probe.index("gPokeDnDStackSampleInvalid = 1;"),
                        probe.index("gPokeDnDStackSampleCount++;"))
        self.assertIn("if (gPokeDnDStackSampleInvalid)\n        return;", probe)
        self.assertLess(probe.index("if (gPokeDnDStackSampleInvalid)"),
                        probe.index("gPokeDnDStackSampleCount++;"))
        self.assertLess(probe.index("sp < low"),
                        probe.index("gPokeDnDStackSamplePeak = depth;"))
        self.assertNotIn("memset(", probe)
        self.assertNotIn("0xA5", probe)

    def test_replay_flag_and_linker_patching_are_coupled(self):
        patcher = PATCHER.read_text(encoding="utf-8")
        self.assertIn('stack_modified, linker_modified = instrument_stack(', patcher)
        self.assertIn('if field_replay:\n        stack_target.write_text(stack_modified)', patcher)
        self.assertIn('"#define POKEDND_NATIVE_REPLAY_ROCKET 1\\n"', patcher)
        self.assertIn('if field_replay:\n        # Replay-only source flag.', patcher)


if __name__ == "__main__":
    unittest.main()
