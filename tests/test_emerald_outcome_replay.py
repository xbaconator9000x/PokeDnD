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
    # Native impact samples are reset on encounter entry, then a real
    # landed hit produces a positive sprite-offset frame count.
    active_hit = label.startswith(("victory-attack-", "defeat-turn-")) or (
        label.startswith(("victory-", "defeat-")) and
        not label.endswith("-start"))
    return dict(label=label, trigger_count=str(attempt), start_failure="0",
                milestones=str(bits), diagnostic_state=str(state),
                post_cancel_moves=str(moves), last_outcome=str(result),
                last_human_hp=str(human), last_enemy_hp=str(enemy),
                outcome_acks=str(ack),
                impact_starts=str(1 if active_hit else 0),
                impact_frames=str(20 if active_hit else 0))


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
    def test_native_scenario_modifiers_do_not_move_player(self):
        actor = (ROOT / "integration/emerald/pokednd_overworld.c").read_text()
        replay = (ROOT / "integration/emerald/ci_field_replay.sh").read_text()
        natural = actor.split("static bool8 TryRocketFieldEncounter", 1)[1].split(
            "bool8 PokeDnD_HandleOverworldInput", 1)[0]
        self.assertIn("(gMain.heldKeys & (L_BUTTON | R_BUTTON)) == L_BUTTON", natural)
        self.assertIn("(gMain.heldKeys & (L_BUTTON | R_BUTTON)) == R_BUTTON", natural)
        self.assertNotIn("gMain.heldKeys & DPAD_UP", natural)
        self.assertNotIn("gMain.heldKeys & DPAD_DOWN", natural)
        interaction = replay.split('if [ "${3:-debug}" = "natural" ]; then', 1)[1].split(
            "sample natural-start", 1)[0]
        self.assertIn('modifier=a', interaction)
        self.assertIn('if [ "$scenario" = defeat ]; then modifier=s; fi', interaction)
        self.assertNotIn('direction=Up', interaction)
        self.assertNotIn('direction=Down', interaction)

    def test_real_ordered_victory_and_defeat_accepted(self):
        self.assertTrue(outcomes.validate(good_trace()).startswith("PASS"))

    def test_missing_actual_sprite_animation_rejected(self):
        rows = good_trace()
        rows[2]["impact_frames"] = "0"
        self.assertRaisesRegex(ValueError, "sprite hit reaction", outcomes.validate, rows)
        rows = good_trace()
        rows[7]["impact_starts"] = "0"
        self.assertRaisesRegex(ValueError, "sprite hit reaction", outcomes.validate, rows)

    def test_impact_must_not_precede_attack(self):
        rows = good_trace()
        rows[0]["impact_starts"] = "1"
        self.assertRaisesRegex(ValueError, "before an attack", outcomes.validate, rows)

    def test_terminal_damage_must_be_observed_at_input_checkpoint(self):
        rows = good_trace()
        rows[1]["last_outcome"] = "0"
        rows[1]["last_enemy_hp"] = "1"
        self.assertRaisesRegex(ValueError, "terminal damage at input checkpoint",
                               outcomes.validate, rows)
        rows = good_trace()
        rows[6]["last_outcome"] = "0"
        rows[6]["last_human_hp"] = "1"
        self.assertRaisesRegex(ValueError, "terminal damage at input checkpoint",
                               outcomes.validate, rows)

    def test_intermediate_conflicting_outcome_rejected(self):
        rows = good_trace()
        rows[1]["last_outcome"] = "2"
        self.assertRaisesRegex(ValueError, "terminal damage at input checkpoint",
                               outcomes.validate, rows)

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
        self.assertRaisesRegex(ValueError, "intermediate milestones regressed",
                               outcomes.validate, rows)
        rows = good_trace()
        rows.pop(6)
        self.assertRaisesRegex(ValueError, "enemy turn checkpoint",
                               outcomes.validate, rows)

    def test_result_cannot_erase_observed_attack(self):
        rows = good_trace()
        rows[2]["milestones"] = "39"
        self.assertRaisesRegex(ValueError, "intermediate milestones regressed",
                               outcomes.validate, rows)

    def test_checkpoint_order_and_duplicates(self):
        rows = good_trace()
        rows[1], rows[5] = rows[5], rows[1]
        self.assertRaisesRegex(ValueError, "out of order", outcomes.validate, rows)
        rows = good_trace()
        rows.insert(1, rows[0].copy())
        self.assertRaisesRegex(ValueError, "exactly one checkpoint",
                               outcomes.validate, rows)

    def test_fake_intermediate_checkpoint_rejected(self):
        rows = good_trace()
        rows[1]["milestones"] = "3"
        self.assertRaisesRegex(ValueError, "observed native attack/turn",
                               outcomes.validate, rows)

    def test_intermediate_from_other_encounter_rejected(self):
        rows = good_trace()
        rows[6]["trigger_count"] = "2"
        self.assertRaisesRegex(ValueError, "wrong encounter",
                               outcomes.validate, rows)

    def test_intermediate_early_ack_rejected(self):
        rows = good_trace()
        rows[1]["outcome_acks"] = "1"
        self.assertRaisesRegex(ValueError, "before confirmation",
                               outcomes.validate, rows)

    def test_intermediate_regression_rejected(self):
        rows = good_trace()
        rows[1]["milestones"] = "0"
        self.assertRaisesRegex(ValueError, "regressed",
                               outcomes.validate, rows)

    def test_attack_checkpoint_after_result_rejected(self):
        rows = good_trace()
        rows.insert(3, rows.pop(1))
        self.assertRaisesRegex(ValueError, "outside encounter",
                               outcomes.validate, rows)

    def test_enemy_turn_before_defeat_start_rejected(self):
        rows = good_trace()
        rows.insert(5, rows.pop(6))
        self.assertRaisesRegex(ValueError, "outside encounter",
                               outcomes.validate, rows)

    def test_unknown_native_checkpoint_rejected(self):
        rows = good_trace()
        rows.insert(2, dict(rows[1], label="victory-forged"))
        self.assertRaisesRegex(ValueError, "unexpected native outcome checkpoint",
                               outcomes.validate, rows)

    def test_complete_live_csv_with_standard_encounter_accepted(self):
        standard = [sample(label, 1, 0, 0, 0, 0, 0, 0, 0) for label in
                    ("baseline", "started", "deployed", "turn", "commanded",
                     "attacked", "cancelled", "resumed")]
        self.assertTrue(outcomes.validate(standard + good_trace()).startswith("PASS"))

    def test_standard_prefix_malformed_register_fails_closed(self):
        labels = ("baseline", "started", "deployed", "turn", "commanded",
                  "attacked", "cancelled", "resumed")
        for index, value in ((0, "not-a-number"), (4, "-1"),
                             (7, "4294967296")):
            with self.subTest(index=index, value=value):
                standard = [sample(label, 1, 0, 0, 0, 0, 0, 0, 0)
                            for label in labels]
                standard[index]["last_enemy_hp"] = value
                self.assertRaisesRegex(
                    ValueError, "standard native register",
                    outcomes.validate, standard + good_trace())

    def test_standard_prefix_valid_hex_registers_accepted(self):
        labels = ("baseline", "started", "deployed", "turn", "commanded",
                  "attacked", "cancelled", "resumed")
        standard = [sample(label, 1, 0, 0, 0, 0, 0, 0, 0)
                    for label in labels]
        standard[2]["milestones"] = "0x3"
        self.assertTrue(outcomes.validate(standard + good_trace()).startswith("PASS"))

    def test_misplaced_standard_checkpoint_rejected(self):
        rows = good_trace()
        rows.insert(1, sample("baseline", 1, 0, 0, 0, 0, 0, 0, 0))
        self.assertRaisesRegex(ValueError, "out of order", outcomes.validate, rows)

    def test_duplicate_native_input_checkpoint_rejected(self):
        rows = good_trace()
        rows.insert(2, rows[1].copy())
        self.assertRaisesRegex(ValueError, "duplicate native input checkpoints",
                               outcomes.validate, rows)

    def test_skipped_native_input_ordinal_rejected(self):
        rows = good_trace()
        rows[1]["label"] = "victory-attack-2"
        self.assertRaisesRegex(ValueError, "noncontiguous", outcomes.validate, rows)
        rows = good_trace()
        rows[6]["label"] = "defeat-turn-0"
        self.assertRaisesRegex(ValueError, "noncontiguous", outcomes.validate, rows)

    def test_late_checkpoint_missing_register_rejected(self):
        rows = good_trace()
        rows[8].pop("last_enemy_hp")
        self.assertRaisesRegex(ValueError, "sample 8", outcomes.validate, rows)

    def test_blank_or_malformed_native_register_rejected(self):
        for value in ("", "  ", "not-a-number", None):
            with self.subTest(value=value):
                rows = good_trace()
                rows[6]["last_human_hp"] = value
                self.assertRaisesRegex(ValueError, "native (outcome or HP registers|register)",
                                       outcomes.validate, rows)

    def test_outcome_register_overflow_rejected_at_every_phase(self):
        # GDB samples are unsigned 32-bit EWRAM words. Python integers do not
        # overflow, so an impossible trace must not satisfy combat acceptance.
        for index in range(len(good_trace())):
            for column in outcomes.REQUIRED[1:]:
                with self.subTest(index=index, column=column):
                    rows = good_trace()
                    rows[index][column] = "0x100000000"
                    self.assertRaisesRegex(
                        ValueError, "out-of-range native EWRAM register",
                        outcomes.validate, rows)

    def test_outcome_negative_register_rejected(self):
        rows = good_trace()
        rows[7]["impact_frames"] = "-1"
        self.assertRaisesRegex(
            ValueError, "out-of-range native EWRAM register",
            outcomes.validate, rows)

    def test_missing_register_rejected(self):
        rows = good_trace()
        rows[0].pop("last_outcome")
        self.assertRaisesRegex(ValueError, "missing native outcome",
                               outcomes.validate, rows)


if __name__ == "__main__":
    unittest.main()
