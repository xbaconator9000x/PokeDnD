"""Native heap entry guard regressions for pinned upstream allocator patching."""
import unittest
from integration.emerald.apply import instrument_heap

ANCHORS = "\n".join((
    "static u32 sHeapSize;",
    "// Alignment\n    if (size & 3)",
    "return pos->data;",
    "if (pos->next == head)\n            return NULL;",
    "block->allocated = FALSE;\n\n        // If",
    "sHeapSize = heapSize;",
))


class NativeHeapEntryGuardTests(unittest.TestCase):
    def setUp(self):
        self.source = instrument_heap(ANCHORS)
        self.entry = self.source.split("static u32 sHeapSize;", 1)[1].split(
            "// Alignment", 1)[0]

    def test_poison_and_uninitialized_epoch_return_before_traversal(self):
        for condition in (
            "gPokeDnDHeapEpoch == 0 ||",
            "gPokeDnDHeapEpoch == 0xFFFFFFFFu ||",
            "gPokeDnDHeapCurrent == 0xFFFFFFFFu ||",
            "gPokeDnDHeapPeak == 0xFFFFFFFFu ||",
            "gPokeDnDHeapFailures == 0xFFFFFFFFu ||",
            "gPokeDnDHeapCapacity == 0",
        ):
            with self.subTest(condition=condition):
                self.assertIn(condition, self.entry)
        self.assertLess(self.entry.index("return NULL;"),
                        self.entry.index("Reject alignment overflow"))

    def test_entry_rejects_inconsistent_live_counters(self):
        for condition in (
            "gPokeDnDHeapCurrent > gPokeDnDHeapPeak ||",
            "gPokeDnDHeapPeak > gPokeDnDHeapCapacity)",
        ):
            with self.subTest(condition=condition):
                self.assertIn(condition, self.entry)
        self.assertLess(self.entry.index("gPokeDnDHeapCurrent > gPokeDnDHeapPeak"),
                        self.entry.index("return NULL;"))

    def test_failure_counter_saturation_poison_is_terminal(self):
        self.assertIn("if (gPokeDnDHeapFailures == 0xFFFFFFFEu)", self.entry)
        saturated = self.entry.split(
            "if (gPokeDnDHeapFailures == 0xFFFFFFFEu)", 1)[1]
        for poison in (
            "gPokeDnDHeapCurrent = 0xFFFFFFFFu;",
            "gPokeDnDHeapPeak = 0xFFFFFFFFu;",
            "gPokeDnDHeapFailures = 0xFFFFFFFFu;",
            "gPokeDnDHeapEpoch = 0xFFFFFFFFu;",
        ):
            self.assertIn(poison, saturated)
        self.assertLess(saturated.index("gPokeDnDHeapEpoch = 0xFFFFFFFFu;"),
                        saturated.index("return NULL;"))

    def test_invalid_epoch_is_terminal_not_reset_by_allocation(self):
        self.assertIn("gPokeDnDHeapEpoch = 0xFFFFFFFFu;", self.entry)
        self.assertIn("gPokeDnDHeapFailures = 0xFFFFFFFFu;", self.entry)
        self.assertNotIn("gPokeDnDHeapEpoch++", self.entry)

    def test_pinned_allocator_anchor_mismatch_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "allocator anchor mismatch"):
            instrument_heap(ANCHORS.replace("// Alignment", "// Changed upstream"))


if __name__ == "__main__":
    unittest.main()
