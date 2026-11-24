"""Regression: persisted native resource verdicts cannot invent acceptance fields."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "resource_verdict", ROOT / "integration/emerald/validate_runtime_resources.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

INPUTS = ("runtime-probe.csv", "runtime-oam.csv", "runtime-stack.csv",
          "runtime-heap.csv", "runtime-stack-samples.csv", "runtime-video.csv")


class VerdictIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.hashes = {}
        for name in INPUTS:
            data = ("fixture:" + name).encode()
            (self.directory / name).write_bytes(data)
            self.hashes[name] = hashlib.sha256(data).hexdigest()
        self.measurements = {"heap_peak_bytes": 64, "limitations": "sampled only"}
        self.verdict = dict(self.measurements,
                            vblank_acceptance="not_measured",
                            stack_acceptance="sampled_only_not_high_water",
                            irq_stack_acceptance="not_measured",
                            evidence_sha256=self.hashes)

    def write(self):
        (self.directory / "runtime-resource-verdict.json").write_text(
            json.dumps(self.verdict))

    def test_exact_verdict_verifies(self):
        self.write()
        with patch.object(MODULE, "validate", return_value=self.measurements):
            self.assertEqual(MODULE.verify_verdict(self.directory), self.verdict)

    def test_forged_gameplay_acceptance_is_rejected(self):
        self.verdict["native_gameplay_accepted"] = True
        self.write()
        with patch.object(MODULE, "validate", return_value=self.measurements):
            with self.assertRaisesRegex(ValueError, "unvalidated fields"):
                MODULE.verify_verdict(self.directory)

    def test_missing_measurement_is_rejected(self):
        del self.verdict["heap_peak_bytes"]
        self.write()
        with patch.object(MODULE, "validate", return_value=self.measurements):
            with self.assertRaisesRegex(ValueError, "unvalidated fields"):
                MODULE.verify_verdict(self.directory)

    def test_duplicate_top_level_claim_is_rejected(self):
        self.write()
        path = self.directory / "runtime-resource-verdict.json"
        original = path.read_text()
        path.write_text(original.replace('"heap_peak_bytes": 64',
                                         '"heap_peak_bytes": 64, "heap_peak_bytes": 64'))
        with patch.object(MODULE, "validate", return_value=self.measurements):
            with self.assertRaisesRegex(ValueError, "duplicate resource verdict JSON key"):
                MODULE.verify_verdict(self.directory)

    def test_duplicate_nested_digest_is_rejected(self):
        self.write()
        path = self.directory / "runtime-resource-verdict.json"
        original = path.read_text()
        key = '"runtime-probe.csv":'
        path.write_text(original.replace(key, key + ' "forged", ' + key))
        with patch.object(MODULE, "validate", return_value=self.measurements):
            with self.assertRaisesRegex(ValueError, "duplicate resource verdict JSON key"):
                MODULE.verify_verdict(self.directory)

    def test_boolean_cannot_impersonate_numeric_measurement(self):
        self.measurements["heap_peak_bytes"] = 1
        self.verdict["heap_peak_bytes"] = True
        self.write()
        with patch.object(MODULE, "validate", return_value=self.measurements):
            with self.assertRaisesRegex(ValueError, "stale or inconsistent"):
                MODULE.verify_verdict(self.directory)

    def test_nonfinite_numeric_claims_fail_before_measurement_validation(self):
        self.write()
        path = self.directory / "runtime-resource-verdict.json"
        original = path.read_text()
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                path.write_text(original.replace('"heap_peak_bytes": 64',
                                                 '"heap_peak_bytes": ' + constant))
                with patch.object(MODULE, "validate", return_value=self.measurements):
                    with self.assertRaisesRegex(ValueError, "non-finite resource verdict"):
                        MODULE.verify_verdict(self.directory)

    def test_cli_verify_rejects_modified_input(self):
        self.write()
        (self.directory / "runtime-heap.csv").write_text("tampered")
        with patch.object(MODULE, "validate", return_value=self.measurements):
            with self.assertRaisesRegex(ValueError, "stale or modified"):
                MODULE.main([str(self.directory), "--verify"])

    def test_cli_verify_does_not_rewrite_verdict(self):
        self.write()
        before = (self.directory / "runtime-resource-verdict.json").read_bytes()
        with patch.object(MODULE, "validate", return_value=self.measurements):
            MODULE.main([str(self.directory), "--verify"])
        self.assertEqual(before, (self.directory / "runtime-resource-verdict.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
