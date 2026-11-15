"""Executable regression tests for native Emerald endgame trace validation."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "integration/emerald/validate_outcome_replay.py"
SPEC = importlib.util.spec_from_file_location("native_outcomes", PATH)
outcomes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(outcomes)


def sample(label, attempt, bits, state, moves, result, human, enemy, ack):
    return dict(label=label, trigger_count=str(attempt), start_failure="0",
                milestones=str(bits), diagnostic_state=str(state),
                post_cancel_moves=str(moves), last_outcome=str(result),
                last_human_hp=str(human), last_enemy_hp=str(enemy),
                outcome_acks=str(ack))


def good_trace():
    return [
        sample("victory-start", 2, 1, 1, 0, 0, 0, 0, 0),
        sample("victory-attack-1", 2, 103, 3, 0, 1, 24, 0, 0),
        sample("victory-result", 2, 103, 3, 0, 1, 24, 0, 0),
        sample("victory-confirmed", 2, 119, 5, 0, 1, 24, 0, 1),
        sample("victory-resumed", 2, 119, 5, 1, 1, 24, 0, 1),
        sample("defeat-start", 3, 1, 1, 0, 0, 0, 0, 1),
        sample("defeat-turn-1", 3, 5, 3, 0, 2, 0, 16, 1),
        sample("defeat-result", 3, 5, 3, 0, 2, 0, 16, 1),
        sample("defeat-confirmed", 3, 21, 5, 0, 2, 0, 16, 2),
        sample("defeat-resumed", 3, 21, 5, 1, 2, 0, 16, 2),
    ]


class OutcomeReplayTests(unittest.TestCase):
    def test_real_ordered_victory_and_defeat_accepted(self):
        self.assertTrue(outcomes.validate(good_trace()).startswith("PASS"))

    def test_missing_damage_rejected(self):
        rows = good_trace()
        rows[2]["last_enemy_hp"] = "1"
        self.assertRaisesRegex(ValueError, "did not defeat Rocket",
                               outcomes.validate, rows)

    def test_defeat_requires_actual_human_ko(self):
        rows = good_trace()
        rows[7]["last_human_hp"] = "1"
        self.assertRaisesRegex(ValueError, "did not KO human",
                               outcomes.validate, rows)

    def test_no_early_autoclose(self):
        rows = good_trace()
        rows[2]["diagnostic_state"] = "5"
        self.assertRaisesRegex(ValueError, "already dismissed",
                               outcomes.validate, rows)

    def test_separate_result_confirmation(self):
        rows = good_trace()
        rows[3]["outcome_acks"] = "0"
        self.assertRaisesRegex(ValueError, "confirmed outcome",
                               outcomes.validate, rows)

    def test_no_premature_or_missing_post_result_movement(self):
        rows = good_trace()
        rows[3]["post_cancel_moves"] = "1"
        self.assertRaisesRegex(ValueError, "premature field step",
                               outcomes.validate, rows)
        rows = good_trace()
        rows[9]["post_cancel_moves"] = "0"
        self.assertRaisesRegex(ValueError, "real map-tile step",
                               outcomes.validate, rows)

    def test_distinct_native_encounters_required(self):
        rows = good_trace()
        rows[5]["trigger_count"] = "2"
        self.assertRaisesRegex(ValueError, "wrong native encounter count",
                               outcomes.validate, rows)

    def test_no_fake_attack_or_enemy_turn(self):
        rows = good_trace()
        rows[2]["milestones"] = "39"
        self.assertRaisesRegex(ValueError, "legal Pokémon attack",
                               outcomes.validate, rows)
        rows = good_trace()
        rows.pop(6)
        self.assertRaisesRegex(ValueError, "enemy turn checkpoint",
                               outcomes.validate, rows)

    def test_checkpoint_order_and_duplicates(self):
        rows = good_trace()
        rows[1], rows[5] = rows[5], rows[1]
        self.assertRaisesRegex(ValueError, "out of order", outcomes.validate, rows)
        rows = good_trace()
        rows.insert(1, rows[0].copy())
        self.assertRaisesRegex(ValueError, "exactly one checkpoint",
                               outcomes.validate, rows)

    def test_missing_register_rejected(self):
        rows = good_trace()
        rows[0].pop("last_outcome")
        self.assertRaisesRegex(ValueError, "missing native outcome",
                               outcomes.validate, rows)


if __name__ == "__main__":
    unittest.main()
