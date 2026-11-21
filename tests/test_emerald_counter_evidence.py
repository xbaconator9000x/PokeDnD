"""Regression tests for fail-closed native counter evidence schemas."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "integration/emerald/validate_runtime_resources.py"
spec = importlib.util.spec_from_file_location("native_resources", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CounterEvidenceTests(unittest.TestCase):
    def write(self, root, name, header, values):
        (root / name).write_text(header + "\n" + values + "\n")

    def test_heap_canonical_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write(root, "runtime-heap.csv",
                       "label,current,peak,failures,capacity,epoch",
                       "boot,128,128,0,8192,1\nfield,0,256,0,8192,1")
            report = module.validate_heap(root, ["boot", "field"])
            self.assertEqual(report["heap_peak_bytes"], 256)

    def test_heap_rejects_ignored_column_and_signed_counter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            header = "label,current,peak,failures,capacity,epoch"
            valid = "boot,128,128,0,8192,1"
            for altered_header, altered_values in [
                (header + ",untrusted", valid + ",1"),
                (header, "boot,+128,128,0,8192,1"),
                (header, "boot, 128,128,0,8192,1"),
            ]:
                with self.subTest(altered_header=altered_header, values=altered_values):
                    self.write(root, "runtime-heap.csv", altered_header, altered_values)
                    with self.assertRaises(ValueError):
                        module.validate_heap(root, ["boot"])

    def test_vblank_rejects_extra_columns_and_noncanonical_ticks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            header = "label,elapsed_ticks,peak_ticks,budget_ticks,epoch"
            self.write(root, "runtime-vblank.csv", header, "boot,12,20,100,1")
            self.assertEqual(module.validate_vblank(root, ["boot"])["vblank_peak_timer_ticks"], 20)
            for altered_header, values in [
                (header + ",untrusted", "boot,12,20,100,1,1"),
                (header, "boot,+12,20,100,1"),
            ]:
                with self.subTest(values=values):
                    self.write(root, "runtime-vblank.csv", altered_header, values)
                    with self.assertRaises(ValueError):
                        module.validate_vblank(root, ["boot"])


    def test_stack_watermarks_reject_extra_columns_and_noncanonical_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # The system stack lower bound must be aligned and leave >=256 bytes.
            system_low = 0x03007E40 - 2048
            cases = (
                ("runtime-watermark.csv", module.validate_watermark,
                 f"boot,{system_low},50363968,256,1792"),
                ("runtime-irq.csv", module.validate_irq,
                 "boot,50363968,50364320,64,288"),
            )
            header = "label,low,top,used,untouched"
            for filename, validator, valid in cases:
                with self.subTest(filename=filename):
                    self.write(root, filename, header, valid)
                    self.assertTrue(validator(root, ["boot"]))
                    self.write(root, filename, header + ",ignored", valid + ",1")
                    with self.assertRaises(ValueError):
                        validator(root, ["boot"])
                    self.write(root, filename, header, valid.replace(",64,", ",+64,").replace(",256,", ",+256,"))
                    with self.assertRaises(ValueError):
                        validator(root, ["boot"])


if __name__ == "__main__":
    unittest.main()
