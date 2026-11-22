"""Linker-bound stack safety regressions for the pinned Emerald adapter.

These tests do not claim a high-water measurement: they verify the generated
linker contract without writing into either live ARM stack.
"""
import unittest

from integration.emerald.apply import instrument_stack


STARTUP = "sp_sys: .word IWRAM_END - 0x1c0\nsp_irq: .word IWRAM_END - 0x60\n"
LINKER = "SECTIONS\n{\n    /* BEGIN ROM DATA */\n}\n"


class NativeStackLinkerBoundsTests(unittest.TestCase):
    def test_system_and_irq_ranges_are_linker_checked(self):
        original_startup, generated = instrument_stack(STARTUP, LINKER)
        self.assertEqual(original_startup, STARTUP)
        required = (
            "__pokednd_stack_low >= ORIGIN(IWRAM)",
            "__pokednd_stack_low < __pokednd_stack_top",
            "(__pokednd_stack_low & 3) == 0",
            "(__pokednd_stack_top & 3) == 0",
            "__pokednd_irq_low == __pokednd_stack_top",
            "__pokednd_irq_top <= ORIGIN(IWRAM) + LENGTH(IWRAM)",
            "(__pokednd_irq_top & 3) == 0",
            "__pokednd_irq_top - __pokednd_irq_low == 352",
            "__pokednd_stack_top - __pokednd_stack_low >= 1024",
        )
        for expression in required:
            with self.subTest(expression=expression):
                self.assertIn("ASSERT(" + expression, generated)

    def test_rejects_upstream_stack_layout_drift(self):
        with self.assertRaisesRegex(RuntimeError, "stack tops changed"):
            instrument_stack(STARTUP.replace("0x1c0", "0x200"), LINKER)

    def test_rejects_duplicate_linker_anchor(self):
        with self.assertRaisesRegex(RuntimeError, "linker anchor mismatch"):
            instrument_stack(STARTUP, LINKER + "    /* BEGIN ROM DATA */")

    def test_rejects_repeated_instrumentation(self):
        _, generated = instrument_stack(STARTUP, LINKER)
        with self.assertRaisesRegex(RuntimeError, "already installed"):
            instrument_stack(STARTUP, generated)

    def test_does_not_write_or_paint_live_stack(self):
        startup, generated = instrument_stack(STARTUP, LINKER)
        self.assertEqual(startup, STARTUP)
        self.assertNotIn("memset", generated)
        self.assertNotIn("0xA5", generated)


if __name__ == "__main__":
    unittest.main()
