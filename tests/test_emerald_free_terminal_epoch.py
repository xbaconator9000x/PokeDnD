"""Regression for terminal heap-accounting corruption at the Free boundary."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("emerald_apply", ROOT / "integration/emerald/apply.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HeapFreeTerminalTests(unittest.TestCase):
    def test_corrupt_free_poison_is_terminal(self):
        # Read the actual replacement installed at the pinned allocator anchor.
        source = (ROOT / "integration/emerald/apply.py").read_text()
        start = source.index('("block->allocated = FALSE;')
        end = source.index('("sHeapSize = heapSize;"', start)
        free_hook = source[start:end]
        terminal = free_hook.split("if (block->magic != MALLOC_SYSTEM_ID", 1)[1].split(
            "else\\n                gPokeDnDHeapCurrent -= occupied;", 1
        )[0]
        for field in ("Current", "Peak", "Failures", "Epoch"):
            self.assertIn("gPokeDnDHeap" + field + " = 0xFFFFFFFFu;", terminal)
        self.assertIn("occupied > gPokeDnDHeapCurrent", terminal)

    def test_init_does_not_launder_terminal_epoch(self):
        source = (ROOT / "integration/emerald/apply.py").read_text()
        self.assertIn("gPokeDnDHeapEpoch == 0xFFFFFFFFu", source)
        self.assertIn("gPokeDnDHeapEpoch = 0xFFFFFFFFu;", source)
        self.assertIn("Pinned allocator anchor mismatch", source)


if __name__ == "__main__":
    unittest.main()
