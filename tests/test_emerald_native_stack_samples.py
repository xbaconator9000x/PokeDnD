"""Native sampled stack acceptance: never equate sampled SP with painted high-water."""
import importlib.util
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("resources", ROOT / "integration/emerald/validate_runtime_resources.py")
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)


class NativeStackSamplesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def trace(self, lines):
        (self.path / "runtime-stack-samples.csv").write_text(
            "label,low,top,peak,samples,invalid\n" + lines)

    def test_valid_monotone_native_samples(self):
        self.trace("start,50360320,50363968,128,4,0\nturn,50360320,50363968,256,12,0\n")
        report = resources.validate_stack_samples(self.path, ["start", "turn"])
        self.assertEqual(report["system_stack_peak_sampled_bytes"], 256)
        self.assertEqual(report["system_stack_sample_count"], 12)

    def test_poison_and_over_budget_rejected(self):
        for peak, count, invalid in ((128, 4, 1), (3456, 4, 0), (128, 0, 0),
                                     (128, 4294967295, 0)):
            with self.subTest(peak=peak, count=count, invalid=invalid):
                self.trace(f"start,50360320,50363968,{peak},{count},{invalid}\n")
                with self.assertRaises(ValueError):
                    resources.validate_stack_samples(self.path, ["start"])

    def test_regression_or_wrong_checkpoint_rejected(self):
        self.trace("start,50360320,50363968,256,12,0\nturn,50360320,50363968,128,13,0\n")
        with self.assertRaises(ValueError):
            resources.validate_stack_samples(self.path, ["start", "turn"])
        with self.assertRaises(ValueError):
            resources.validate_stack_samples(self.path, ["start", "other"])

    def test_missing_or_legacy_watermark_is_not_stack_evidence(self):
        (self.path / "runtime-watermark.csv").write_text(
            "label,low,top,used,untouched\nstart,50360320,50363968,128,3520\n")
        with self.assertRaises(FileNotFoundError):
            resources.validate_stack_samples(self.path, ["start"])


if __name__ == "__main__":
    unittest.main()
