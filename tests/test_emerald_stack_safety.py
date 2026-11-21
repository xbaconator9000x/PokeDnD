"""Safety regression: never paint a live GBA system/IRQ stack."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "integration/emerald/apply.py"
spec = importlib.util.spec_from_file_location("adapter_stack", path)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

STARTUP = """sp_sys: .word IWRAM_END - 0x1c0
sp_irq: .word IWRAM_END - 0x60
\tbl InitializeWorkingMemory
"""
LINKER = """SECTIONS
{
    /* BEGIN ROM DATA */
}
"""


class StackSafetyTests(unittest.TestCase):
    def test_linker_bounds_without_writing_active_stack(self):
        startup, linker = adapter.instrument_stack(STARTUP, LINKER)
        self.assertEqual(startup, STARTUP)
        self.assertIn("__pokednd_stack_low = ALIGN(ADDR(.iwram.bss)", linker)
        self.assertIn("__pokednd_stack_top = ORIGIN(IWRAM)", linker)
        self.assertIn("__pokednd_irq_top = ORIGIN(IWRAM)", linker)
        self.assertIn('ASSERT(__pokednd_stack_top - __pokednd_stack_low >= 1024', linker)
        self.assertNotIn("strlo", startup)
        self.assertNotIn("0xA55A3CC3", startup)

    def test_reapplication_fails_closed(self):
        startup, linker = adapter.instrument_stack(STARTUP, LINKER)
        with self.assertRaises(RuntimeError):
            adapter.instrument_stack(startup, linker)

    def test_unknown_stack_top_fails_closed(self):
        with self.assertRaises(RuntimeError):
            adapter.instrument_stack(STARTUP.replace("0x1c0", "0x1b0"), LINKER)

    def test_missing_linker_anchor_fails_closed(self):
        with self.assertRaises(RuntimeError):
            adapter.instrument_stack(STARTUP, "SECTIONS {}")


if __name__ == "__main__":
    unittest.main()
