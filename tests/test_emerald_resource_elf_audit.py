"""Fail-closed native resource counter ELF audit regressions."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_gba_memory", ROOT / "integration/emerald/audit_gba_memory.py")
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


def symbol_table(*, missing=None, wrong_region=None, wrong_size=None, duplicate=None):
    names = ("sBattle", "gPokeDnDDiagnosticState") + (
        audit_module.REQUIRED_HEAP_COUNTERS + audit_module.REQUIRED_STACK_COUNTERS)
    lines = []
    for i, name in enumerate(names):
        if name == missing:
            continue
        addr = 0x03000000 if name == wrong_region else 0x02000000 + 8 * i
        size = 8 if name == wrong_size else 4
        lines.append(f"{addr:08x} {size:08x} B {name}")
        if name == duplicate:
            lines.append(f"{addr+4:08x} 00000004 B {name}")
    return "\n".join(lines)


class ResourceElfAuditTests(unittest.TestCase):
    def check(self, **kwargs):
        return audit_module.audit("", symbol_table(**kwargs), require_stack=True)

    def test_all_required_native_counters_present(self):
        result = self.check()
        self.assertTrue(result["pass"], result["violations"])

    def test_linked_ram_budget_exact_boundary_passes(self):
        section = "  [ 1] .ewram NOBITS 02000000 000100 000010 00 WA 0 0 4"
        result = audit_module.audit(section, symbol_table(), budgets={"EWRAM": 256})
        self.assertTrue(result["pass"], result["violations"])

    def test_linked_ram_budget_exceeded_fails(self):
        section = "  [ 1] .ewram NOBITS 02000000 000100 000010 00 WA 0 0 4"
        result = audit_module.audit(section, symbol_table(), budgets={"EWRAM": 255})
        self.assertFalse(result["pass"])
        self.assertIn("exceeds budget 255", " ".join(result["violations"]))

    def test_invalid_budget_rejected(self):
        for ceiling in (-1, True, "256"):
            with self.subTest(ceiling=ceiling):
                self.assertFalse(audit_module.audit(
                    "", symbol_table(), budgets={"EWRAM": ceiling})["pass"])

    def test_missing_heap_counter_fails(self):
        result = self.check(missing="gPokeDnDHeapFailures")
        self.assertFalse(result["pass"])
        self.assertIn("gPokeDnDHeapFailures", " ".join(result["violations"]))

    def test_non_replay_build_does_not_require_stack_counters(self):
        result = audit_module.audit("", symbol_table(missing="gPokeDnDIrqStackCapacity"))
        self.assertTrue(result["pass"], result["violations"])

    def test_missing_irq_counter_fails(self):
        self.assertFalse(self.check(missing="gPokeDnDIrqStackCapacity")["pass"])

    def test_wrong_memory_region_fails(self):
        self.assertFalse(self.check(wrong_region="gPokeDnDHeapPeak")["pass"])

    def test_wrong_size_fails(self):
        self.assertFalse(self.check(wrong_size="gPokeDnDStackSampleCount")["pass"])

    def test_duplicate_counter_fails(self):
        self.assertFalse(self.check(duplicate="gPokeDnDHeapEpoch")["pass"])


if __name__ == "__main__":
    unittest.main()
