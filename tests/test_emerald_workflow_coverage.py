"""Prevent the native Emerald replay workflow from silently skipping new regressions."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/emerald-field-replay.yml"


class EmeraldWorkflowCoverageTests(unittest.TestCase):
    def test_all_emerald_regressions_are_discovered(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python3 -m unittest discover -s tests -p 'test_emerald_*.py' -v", workflow)
        self.assertEqual(workflow.count("python3 -m unittest discover"), 1)
        self.assertIn('      - "tests/test_emerald_*.py"', workflow)

    def test_tests_run_before_pinned_upstream_and_native_replay(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        tests = workflow.index("- name: Replay boot and workflow source regression tests")
        upstream = workflow.index("- name: Fetch exact pinned Emerald source")
        replay = workflow.index("- name: Replay real mGBA input and capture frames")
        self.assertLess(tests, upstream)
        self.assertLess(upstream, replay)


if __name__ == "__main__":
    unittest.main()
