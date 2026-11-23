"""Regression: replay-only preprocessor flag must not swallow the adapter source."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APPLY = ROOT / "integration" / "emerald" / "apply.py"


class ReplaySourceInjectionTests(unittest.TestCase):
    def test_replay_define_is_line_terminated(self):
        self.assertIn(r'actor.write_text("#define POKEDND_NATIVE_REPLAY_ROCKET 1\n" +', source)
        self.assertNotIn(r'actor.write_text("#define POKEDND_NATIVE_REPLAY_ROCKET 1\\n" +', source)

    def test_replay_define_materializes_separate_preprocessor_line(self):
        prefix = "#define POKEDND_NATIVE_REPLAY_ROCKET 1\n"
        body = '#include "global.h"\nint pokednd_probe(void) { return 1; }\n'
        result = prefix + body
        self.assertEqual(result.splitlines()[0], "#define POKEDND_NATIVE_REPLAY_ROCKET 1")
        self.assertEqual(result.splitlines()[1], '#include "global.h"')
        self.assertEqual(len(result.splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
