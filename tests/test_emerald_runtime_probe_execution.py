"""Execute the real replay probe validator against representative emulator traces.

These tests exercise the embedded validator rather than checking source strings.
They do not constitute emulator gameplay acceptance.
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "integration/emerald/ci_field_replay.sh"


def validator_source():
    source = SCRIPT.read_text()
    marker = 'python3 - "${POKEDND_RUNTIME_PROBE}" "$OUT" <<\'PY\'\n'
    if marker not in source:
        raise AssertionError("runtime validator heredoc missing")
    return source.split(marker, 1)[1].split("\nPY\n", 1)[0]


def run_trace(rows):
    rows = [(*row, {0: 0, 1: 1, 3: 2, 7: 3}.get(row[2], 0))
            if len(row) == 3 else row for row in rows]
    with tempfile.TemporaryDirectory() as temp:
        folder = pathlib.Path(temp)
        csv = folder / "trace.csv"
        csv.write_text("trigger_count,start_failure,milestones,diagnostic_state\n" + "".join(
            ",".join(str(value) for value in row) + "\n" for row in rows))
        result = subprocess.run(
            [sys.executable, "-c", validator_source(), str(csv), str(folder)],
            capture_output=True, text=True, check=False)
        verdict = folder / "runtime-probe-verdict.txt"
        return result.returncode, verdict.read_text() if verdict.exists() else ""


class RuntimeProbeExecutionTests(unittest.TestCase):
    def test_real_ordered_trace_passes(self):
        status, verdict = run_trace([(0, 0, 0, 0), (1, 0, 1, 1), (1, 0, 3, 2),
                                     (1, 0, 135, 3), (1, 0, 167, 3),
                                     (1, 0, 231, 3), (1, 0, 239, 4)])
        self.assertEqual(status, 0)
        self.assertTrue(verdict.startswith("PASS"))

    def test_missing_command_rejected(self):
        self.assertNotEqual(run_trace([(0, 0, 0, 0), (1, 0, 1, 1), (1, 0, 3, 2),
                                       (1, 0, 135, 3), (1, 0, 135, 3),
                                       (1, 0, 199, 3), (1, 0, 207, 4)])[0], 0)

    def test_missing_attack_rejected(self):
        self.assertNotEqual(run_trace([(0, 0, 0, 0), (1, 0, 1, 1), (1, 0, 3, 2),
                                       (1, 0, 135, 3), (1, 0, 167, 3),
                                       (1, 0, 167, 3), (1, 0, 175, 4)])[0], 0)

    def test_missing_cancel_rejected(self):
        self.assertNotEqual(run_trace([(0, 0, 0, 0), (1, 0, 1, 1), (1, 0, 3, 2),
                                       (1, 0, 135, 3), (1, 0, 167, 3),
                                       (1, 0, 231, 3), (1, 0, 231, 3)])[0], 0)

    def test_faked_attack_without_command_rejected(self):
        self.assertNotEqual(run_trace([(0, 0, 0, 0), (1, 0, 1, 1), (1, 0, 3, 2),
                                       (1, 0, 135, 3), (1, 0, 135, 3),
                                       (1, 0, 199, 3), (1, 0, 207, 4)])[0], 0)

    def test_wrong_native_state_rejected(self):
        self.assertNotEqual(run_trace([(0, 0, 0, 0), (1, 0, 1, 1),
                                       (1, 0, 3, 1), (1, 0, 7, 3)])[0], 0)

    def test_skipped_trigger_attempt_rejected(self):
        self.assertNotEqual(run_trace([(0, 0, 0, 0), (2, 0, 1, 1),
                                       (2, 0, 3, 2), (2, 0, 7, 3)])[0], 0)

    def test_hidden_skipped_attempt_rejected(self):
        self.assertNotEqual(run_trace([(0, 0, 0, 0), (1, 0, 1, 1),
                                       (1, 0, 3, 2), (1, 0, 7, 3),
                                       (4, 0, 7, 3)])[0], 0)

    def test_late_admission_failure_rejected(self):
        self.assertNotEqual(run_trace([(0, 0, 0, 0), (1, 0, 1, 1),
                                       (1, 0, 3, 2), (1, 0, 7, 3),
                                       (1, 2, 7, 3)])[0], 0)

    def test_invalid_native_state_rejected(self):
        self.assertNotEqual(run_trace([(0, 0, 0, 0), (1, 0, 1, 1),
                                       (1, 0, 3, 2), (1, 0, 7, 3),
                                       (1, 0, 7, 99)])[0], 0)

    def test_no_baseline_rejected(self):
        self.assertNotEqual(run_trace([(1, 0, 1), (1, 0, 3), (1, 0, 7)])[0], 0)

    def test_cross_attempt_milestones_rejected(self):
        self.assertNotEqual(run_trace([(0, 0, 0), (1, 0, 1),
                                       (2, 0, 3), (2, 0, 7)])[0], 0)

    def test_failed_attempt_rejected(self):
        self.assertNotEqual(run_trace([(0, 0, 0), (1, 0, 1),
                                       (1, 2, 3), (1, 0, 7)])[0], 0)

    def test_single_snapshot_rejected(self):
        self.assertNotEqual(run_trace([(1, 0, 7)])[0], 0)

    def test_no_trigger_rejected(self):
        self.assertNotEqual(run_trace([(0, 0, 1), (0, 0, 3), (0, 0, 7)])[0], 0)

    def test_admission_failure_rejected(self):
        self.assertNotEqual(run_trace([(1, 2, 1), (1, 2, 3), (1, 2, 7)])[0], 0)

    def test_missing_deployment_rejected(self):
        self.assertNotEqual(run_trace([(1, 0, 1), (1, 0, 1), (1, 0, 5)])[0], 0)

    def test_regressing_milestones_rejected(self):
        self.assertNotEqual(run_trace([(1, 0, 3), (1, 0, 1), (1, 0, 7)])[0], 0)

    def test_regressing_trigger_rejected(self):
        self.assertNotEqual(run_trace([(2, 0, 1), (1, 0, 3), (2, 0, 7)])[0], 0)

    def test_skipped_deployment_snapshot_rejected(self):
        self.assertNotEqual(run_trace([(1, 0, 1), (1, 0, 7), (1, 0, 7)])[0], 0)


if __name__ == "__main__":
    unittest.main()
