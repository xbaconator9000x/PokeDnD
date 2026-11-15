"""Source-only regression: the replay must build this exact revision, not an old ROM."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/emerald-field-replay.yml"
INTEGRATION = ROOT / ".github/workflows/emerald-integration.yml"
PIN = "4da9230cf7c1f1d7b0d47b45783b202666fffece"


class ReplayWorkflowTests(unittest.TestCase):
    def test_exact_head_source_and_hook(self):
        text = WORKFLOW.read_text()
        self.assertIn("actions/checkout@v4", text)
        self.assertIn("integration/emerald/apply.py upstream --field-replay", text)
        self.assertIn("MAP_OLDALE_TOWN", text)
        self.assertIn("make -C upstream -j4 all", text)
        self.assertIn("PokeDnD_HandleOverworldInput", text)
        self.assertIn(PIN, text)
        self.assertIn("ci_field_replay.sh", text)

    def test_no_stale_rom_or_duplicate_replay(self):
        text = WORKFLOW.read_text()
        self.assertNotIn("download-artifact@", text)
        self.assertNotIn("run-id:", text)
        self.assertNotIn("find rom ", text)
        self.assertEqual(text.count("ci_field_replay.sh"), 1)
        self.assertEqual(text.count("actions/upload-artifact@"), 1)

    def test_replay_runs_on_integration_changes(self):
        text = WORKFLOW.read_text()
        self.assertIn('"integration/emerald/**"', text)
        self.assertIn('"src/d20*"', text)
        self.assertIn('"include/d20*"', text)

    def test_runtime_probe_requires_ordered_transitions(self):
        script = (ROOT / "integration/emerald/ci_field_replay.sh").read_text()
        self.assertIn("len(observed) < 8", script)
        self.assertIn("post_cancel_moves", script)
        self.assertIn("resumed[4] == 1", script)
        self.assertIn("gPokeDnDPostCancelMoves", script)
        self.assertIn("runtime trigger count regressed", script)
        self.assertIn("runtime milestones regressed", script)
        self.assertIn("started[3] == 1 and deployed[3] == 2 and turned[3] == 3", script)
        self.assertIn("(started[2] & 255) == 1", script)
        self.assertIn("(deployed[2] & 255) == 3", script)
        self.assertIn("(turned[2] & 255) == 135", script)
        self.assertIn("(commanded[2] & 255) == 167", script)
        self.assertIn("(attacked[2] & 255) == 231", script)
        self.assertIn("(cancelled[2] & 255) == 239", script)
        self.assertNotIn("passed = any(t > 0 and f == 0 and (m & 7) == 7", script)

    def test_debug_replay_evidence_only_after_live_validation(self):
        script = (ROOT / "integration/emerald/ci_field_replay.sh").read_text()
        verdict = script.index("python3 integration/emerald/validate_outcome_replay.py")
        standard = script.index('"runtime-probe-verdict.txt").write_text(')
        evidence = script.index("NATIVE_DEBUG_REPLAY_ACCEPTED.txt")
        self.assertLess(verdict, evidence)
        self.assertLess(standard, evidence)
        self.assertNotIn("ACCEPTANCE_NOT_VERIFIED.txt", script)
        self.assertIn("do NOT establish natural NPC/wild encounter activation", script)

    def test_upstream_pin_matches_native_build(self):
        self.assertIn(PIN, INTEGRATION.read_text())


if __name__ == "__main__":
    unittest.main()
