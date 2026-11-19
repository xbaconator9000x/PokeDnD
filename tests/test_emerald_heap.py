import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("adapter", Path(__file__).resolve().parents[1] / "integration/emerald/apply.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

FIXTURE = """static u32 sHeapSize;
return pos->data;
if (pos->next == head)
            return NULL;
block->allocated = FALSE;

        // If
sHeapSize = heapSize;"""

class HeapInstrumentationTests(unittest.TestCase):
    def test_hooks(self):
        result = adapter.instrument_heap(FIXTURE)
        for expression in (
            "gPokeDnDHeapCurrent += pos->size + sizeof(struct MemBlock)",
            "gPokeDnDHeapCurrent -= block->size + sizeof(struct MemBlock)",
            "gPokeDnDHeapPeak = gPokeDnDHeapCurrent",
            "gPokeDnDHeapFailures++",
            "gPokeDnDHeapCapacity = heapSize",
            "gPokeDnDHeapEpoch++",
        ):
            self.assertIn(expression, result)

    def test_missing_anchor(self):
        with self.assertRaises(RuntimeError):
            adapter.instrument_heap(FIXTURE.replace("return pos->data;", ""))

    def test_duplicate_anchor(self):
        with self.assertRaises(RuntimeError):
            adapter.instrument_heap(FIXTURE + "\nreturn pos->data;")

    def test_reapply_rejected(self):
        with self.assertRaises(RuntimeError):
            adapter.instrument_heap(adapter.instrument_heap(FIXTURE))
