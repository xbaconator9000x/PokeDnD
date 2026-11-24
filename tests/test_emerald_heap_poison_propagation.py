"""Regression for fail-closed native heap accounting across allocation epochs."""
import unittest

from integration.emerald.apply import instrument_heap


class HeapPoisonPropagationTests(unittest.TestCase):
    def test_poisoned_failure_counter_blocks_successful_alloc_and_free(self):
        # These checks must precede the respective accounting updates.
        import inspect
        source = inspect.getsource(instrument_heap)
        alloc = source.split('u32 occupied = pos->size + sizeof(struct MemBlock);', 1)[1].split('return pos->data;', 1)[0]
        free = source.split('u32 occupied = block->size + sizeof(struct MemBlock);', 1)[1].split('block->allocated = FALSE;', 1)[0]
        self.assertIn('gPokeDnDHeapFailures == 0xFFFFFFFFu', alloc)
        self.assertIn('gPokeDnDHeapFailures == 0xFFFFFFFFu', free)
        self.assertLess(alloc.index('gPokeDnDHeapFailures == 0xFFFFFFFFu'),
                        alloc.index('gPokeDnDHeapCurrent += occupied;'))
        self.assertLess(free.index('gPokeDnDHeapFailures == 0xFFFFFFFFu'),
                        free.index('gPokeDnDHeapCurrent -= occupied;'))

    def test_reset_rejects_impossible_prior_peak(self):
        import inspect
        source = inspect.getsource(instrument_heap)
        reset = source.split('sHeapSize = heapSize;', 1)[1]
        guards = reset.split('gPokeDnDHeapCurrent = 0xFFFFFFFFu;', 1)[0]
        self.assertIn('gPokeDnDHeapPeak > gPokeDnDHeapCapacity', guards)
        self.assertIn('gPokeDnDHeapPeak < gPokeDnDHeapCurrent', guards)
        self.assertIn('gPokeDnDHeapFailures == 0xFFFFFFFFu', guards)
        self.assertIn('gPokeDnDHeapEpoch == 0xFFFFFFFFu', guards)


if __name__ == "__main__":
    unittest.main()
