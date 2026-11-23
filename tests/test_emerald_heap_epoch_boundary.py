"""Regression for allocator accounting before the first InitHeap epoch."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "emerald_apply_heap_epoch", ROOT / "integration/emerald/apply.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HeapEpochBoundaryTests(unittest.TestCase):
    def test_allocation_and_free_reject_uninitialized_epoch(self):
        anchors = [
            "static u32 sHeapSize;",
            "// Alignment\n    if (size & 3)",
            "return pos->data;",
            "if (pos->next == head)\n            return NULL;",
            "block->allocated = FALSE;\n\n        // If",
            "sHeapSize = heapSize;",
        ]
        source = "\n".join(anchors)
        instrumented = MODULE.instrument_heap(source)
        guard = "gPokeDnDHeapEpoch == 0 ||"
        self.assertEqual(instrumented.count(guard), 3)  # allocation entry, success path, free
        self.assertIn("gPokeDnDHeapEpoch == 0xFFFFFFFFu ||", instrumented)

    def test_initial_heap_epoch_zero_remains_valid(self):
        source = "\n".join([
            "static u32 sHeapSize;", "// Alignment\n    if (size & 3)",
            "return pos->data;",
            "if (pos->next == head)\n            return NULL;",
            "block->allocated = FALSE;\n\n        // If",
            "sHeapSize = heapSize;",
        ])
        instrumented = MODULE.instrument_heap(source)
        init = instrumented.split("sHeapSize = heapSize;", 1)[1]
        self.assertNotIn("gPokeDnDHeapEpoch == 0 ||", init)
        self.assertIn("gPokeDnDHeapEpoch++;", init)


if __name__ == "__main__":
    unittest.main()
