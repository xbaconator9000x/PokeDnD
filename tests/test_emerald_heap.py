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
            "gPokeDnDHeapCurrent += occupied",
            "gPokeDnDHeapCurrent -= occupied",
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

    def test_accounting_fails_closed_on_overflow(self):
        result = adapter.instrument_heap(FIXTURE)
        self.assertIn("occupied < pos->size", result)
        self.assertIn("occupied > gPokeDnDHeapCapacity", result)
        self.assertIn("gPokeDnDHeapCurrent > gPokeDnDHeapCapacity - occupied", result)
        self.assertIn("gPokeDnDHeapCurrent = 0xFFFFFFFFu", result)
        self.assertIn("gPokeDnDHeapPeak = 0xFFFFFFFFu", result)

    def test_accounting_fails_closed_on_underflow(self):
        result = adapter.instrument_heap(FIXTURE)
        self.assertIn("occupied < block->size", result)
        self.assertIn("occupied > gPokeDnDHeapCurrent", result)
        self.assertIn("gPokeDnDHeapCurrent == 0xFFFFFFFFu", result)
        self.assertIn("gPokeDnDHeapCurrent -= occupied", result)

    def test_terminal_fault_survives_allocator_reinitialization(self):
        # The emitted native reset branch must test old counters before
        # zeroing them. A second InitHeap must never erase a corrupt epoch.
        result = adapter.instrument_heap(FIXTURE)
        reset = result.split("sHeapSize = heapSize;", 1)[1]
        fault = reset.index("gPokeDnDHeapCurrent == 0xFFFFFFFFu")
        clear = reset.index("gPokeDnDHeapCurrent = 0;")
        self.assertLess(fault, clear)
        self.assertIn("gPokeDnDHeapPeak == 0xFFFFFFFFu", reset[:clear])
        self.assertIn("gPokeDnDHeapFailures == 0xFFFFFFFFu", reset[:clear])
        self.assertIn("gPokeDnDHeapEpoch = 0xFFFFFFFFu;", reset[:clear])
        self.assertIn("gPokeDnDHeapEpoch++;", reset[clear:])

    def test_reset_rejects_live_allocations(self):
        # InitHeap must not erase a nonzero current allocation counter.
        result = adapter.instrument_heap(FIXTURE)
        reset = result.split("sHeapSize = heapSize;", 1)[1]
        guard = "gPokeDnDHeapCurrent != 0"
        self.assertIn(guard, reset)
        self.assertLess(reset.index(guard), reset.index("gPokeDnDHeapCurrent = 0;"))
        self.assertIn("gPokeDnDHeapCurrent = 0xFFFFFFFFu;", reset)

    def test_reset_rejects_zero_capacity_and_epoch_rollover(self):
        result = adapter.instrument_heap(FIXTURE)
        self.assertIn("heapSize == 0", result)
        self.assertIn("gPokeDnDHeapEpoch == 0xFFFFFFFFu", result)
        self.assertIn("gPokeDnDHeapEpoch = 0xFFFFFFFFu", result)
        self.assertIn("gPokeDnDHeapEpoch++;", result)
        self.assertIn("gPokeDnDHeapPeak = 0xFFFFFFFFu", result)

    def test_first_epoch_dirty_counters_rejected(self):
        result = adapter.instrument_heap(FIXTURE)
        reset = result.split("sHeapSize = heapSize;", 1)[1]
        self.assertIn("gPokeDnDHeapEpoch == 0 &&", reset)
        self.assertIn("gPokeDnDHeapPeak != 0 || gPokeDnDHeapFailures != 0", reset)
        self.assertLess(reset.index("gPokeDnDHeapCurrent != 0"), reset.index("gPokeDnDHeapCurrent = 0;"))
        self.assertIn("gPokeDnDHeapEpoch = 0xFFFFFFFFu;", reset)

    def test_double_free_and_corrupt_span_fail_closed(self):
        result = adapter.instrument_heap(FIXTURE)
        free = result.split("/* Preserve the invalid sentinel across subsequent frees. */", 1)[1]
        self.assertIn("block->magic != MALLOC_SYSTEM_ID", free)
        self.assertLess(free.index("block->magic != MALLOC_SYSTEM_ID"), free.index("gPokeDnDHeapCurrent -= occupied;"))
        self.assertIn("!block->allocated", free)
        self.assertIn("occupied > gPokeDnDHeapCapacity", free)
        self.assertLess(free.index("!block->allocated"), free.index("gPokeDnDHeapCurrent -= occupied;"))
        self.assertLess(free.index("occupied > gPokeDnDHeapCapacity"), free.index("gPokeDnDHeapCurrent -= occupied;"))
        self.assertIn("gPokeDnDHeapPeak = 0xFFFFFFFFu;", free)

    def test_allocated_header_integrity_precedes_accounting(self):
        # Upstream AllocInternal sets allocated and retains MALLOC_SYSTEM_ID.
        # Corrupted headers must poison the evidence before a peak is recorded.
        result = adapter.instrument_heap(FIXTURE)
        allocation = result.split("/* Account for the allocator's actual block span", 1)[1].split("return pos->data;", 1)[0]
        self.assertIn("pos->magic != MALLOC_SYSTEM_ID", allocation)
        self.assertIn("!pos->allocated", allocation)
        self.assertLess(allocation.index("pos->magic != MALLOC_SYSTEM_ID"), allocation.index("gPokeDnDHeapCurrent += occupied"))
        self.assertLess(allocation.index("!pos->allocated"), allocation.index("gPokeDnDHeapCurrent += occupied"))
        self.assertIn("gPokeDnDHeapCurrent = 0xFFFFFFFFu;", allocation)
        self.assertIn("gPokeDnDHeapPeak = 0xFFFFFFFFu;", allocation)
