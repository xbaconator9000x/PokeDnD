"""Host regressions for real native GBA ELF memory budget audit."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "integration/emerald/audit_gba_memory.py"
spec = importlib.util.spec_from_file_location("gba_memory", path)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def section(name, addr, size, flags="WA"):
    return f"  [ 4] {name} NOBITS {addr:08x} 001000 {size:06x} 00 {flags} 0 0 4"


SYMBOLS = """02000100 00000400 b sBattle
02000500 00000004 B gPokeDnDDiagnosticState
02000600 00000020 b sProjection
02000700 00000020 b sUnits
03000100 00000004 T unrelated
""" + "\n".join(
    f"{0x02000800 + 8 * i:08x} 00000004 B {name}"
    for i, name in enumerate(audit.REQUIRED_HEAP_COUNTERS)
) + "\n"


class GbaMemoryAuditTests(unittest.TestCase):
    def test_exact_linked_ewram_and_iwram_allocation(self):
        sections = "\n".join((section(".ewram", 0x02000000, 0x2000),
                              section(".iwram", 0x03000000, 0x1000),
                              section(".text", 0x08000000, 0x4000, "AX")))
        result = audit.audit(sections, SYMBOLS)
        self.assertTrue(result["pass"], result["violations"])
        self.assertEqual(result["regions"]["EWRAM"]["linked_bytes"], 8192)
        self.assertEqual(result["regions"]["IWRAM"]["linked_bytes"], 4096)
        self.assertEqual(result["pokednd_ram_symbol_bytes"], 0x444 + 4 * len(audit.REQUIRED_HEAP_COUNTERS))

    def test_overflow_fails_closed(self):
        sections = section(".ewram", 0x0203ff00, 0x200)
        result = audit.audit(sections, SYMBOLS)
        self.assertFalse(result["pass"])
        self.assertIn("exceeds EWRAM", " ".join(result["violations"]))

    def test_overlapping_sections_fail_closed(self):
        sections = "\n".join((section(".ewram", 0x02000000, 0x1000),
                              section(".extra", 0x02000800, 0x1000)))
        result = audit.audit(sections, SYMBOLS)
        self.assertFalse(result["pass"])
        self.assertIn("overlapping", " ".join(result["violations"]))

    def test_non_allocated_sections_do_not_count(self):
        sections = section(".debug_info", 0x02000000, 0x20000, "MS")
        result = audit.audit(sections, SYMBOLS)
        self.assertTrue(result["pass"])
        self.assertEqual(result["regions"]["EWRAM"]["linked_bytes"], 0)

    def test_required_native_symbols_missing_fails_closed(self):
        result = audit.audit(section(".ewram", 0x02000000, 0x1000), "")
        self.assertFalse(result["pass"])
        self.assertEqual(len(result["violations"]), 2 + len(audit.REQUIRED_HEAP_COUNTERS))

    def test_section_at_end_of_region_is_not_ram(self):
        regions, errors = audit.measure_sections(section(".other", 0x02040000, 0x100))
        self.assertFalse(errors)
        self.assertEqual(regions["EWRAM"]["linked_bytes"], 0)

    def test_boundary_exact_fit_accepted(self):
        regions, errors = audit.measure_sections(section(".ewram", 0x02000000, 0x40000))
        self.assertFalse(errors)
        self.assertEqual(regions["EWRAM"]["linked_bytes"], 0x40000)


if __name__ == "__main__":
    unittest.main()
