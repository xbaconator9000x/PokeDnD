"""Regression for native heap exhaustion failure-counter saturation.

The generated allocator must poison the replay immediately rather than
reporting a wrapped failure counter as valid telemetry.
"""
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


class HeapExhaustionSaturationTests(unittest.TestCase):
    def test_exhaustion_poison_precedes_return(self):
        patched = instrument_heap(ANCHORS)
        exhaustion = patched.split("if (pos->next == head)", 1)[1].split(
            "return NULL;", 1)[0]
        self.assertIn("gPokeDnDHeapFailures >= 0xFFFFFFFEu", exhaustion)
        for assignment in (
            "gPokeDnDHeapCurrent = 0xFFFFFFFFu;",
            "gPokeDnDHeapPeak = 0xFFFFFFFFu;",
            "gPokeDnDHeapFailures = 0xFFFFFFFFu;",
            "gPokeDnDHeapEpoch = 0xFFFFFFFFu;",
        ):
            with self.subTest(assignment=assignment):
                self.assertIn(assignment, exhaustion)
        self.assertIn("else\n                gPokeDnDHeapFailures++;", exhaustion)

    def test_upstream_exhaustion_anchor_is_mandatory(self):
        with self.assertRaisesRegex(RuntimeError, "allocator anchor mismatch"):
            instrument_heap(ANCHORS.replace("if (pos->next == head)",
                                            "if (pos->next != head)"))


if __name__ == "__main__":
    unittest.main()
