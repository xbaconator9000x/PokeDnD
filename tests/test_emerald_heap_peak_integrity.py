"""Regression contracts for native allocator peak-accounting corruption guards.

Tests inspect the generated pinned-upstream C rather than a mock allocator.
No ROM bytes or private game assets are required.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pokednd_emerald_heap_apply", ROOT / "integration/emerald/apply.py"
)
apply = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apply)

from test_emerald_heap import FIXTURE


class HeapPeakIntegrityTests(unittest.TestCase):
    def test_allocation_and_free_reject_corrupt_peak_before_counter_update(self):
        source = apply.instrument_heap(FIXTURE)
        self.assertEqual(source.count(
            "gPokeDnDHeapPeak < gPokeDnDHeapCurrent"), 2)
        self.assertEqual(source.count(
            "gPokeDnDHeapPeak > gPokeDnDHeapCapacity"), 2)
        alloc = source.index("u32 occupied = pos->size + sizeof(struct MemBlock);")
        alloc_end = source.index("return pos->data;", alloc)
        free = source.index("u32 occupied = block->size + sizeof(struct MemBlock);")
        free_end = source.index("block->allocated = FALSE;", free)
        for section, mutation in (
            (source[alloc:alloc_end], "gPokeDnDHeapCurrent += occupied;"),
            (source[free:free_end], "gPokeDnDHeapCurrent -= occupied;"),
        ):
            with self.subTest(mutation=mutation):
                self.assertLess(
                    section.index("gPokeDnDHeapPeak < gPokeDnDHeapCurrent"),
                    section.index(mutation))
                self.assertLess(
                    section.index("gPokeDnDHeapPeak > gPokeDnDHeapCapacity"),
                    section.index(mutation))
                self.assertIn("gPokeDnDHeapCurrent = 0xFFFFFFFFu;", section)
                self.assertIn("gPokeDnDHeapPeak = 0xFFFFFFFFu;", section)

    def test_rejects_unpinned_or_already_instrumented_allocator(self):
        patched = apply.instrument_heap(FIXTURE)
        with self.assertRaisesRegex(RuntimeError, "Pinned allocator anchor mismatch"):
            apply.instrument_heap(patched)


if __name__ == "__main__":
    unittest.main()
