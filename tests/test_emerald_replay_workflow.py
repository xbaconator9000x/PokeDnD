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
        self.assertEqual(text.count("ci_field_replay.sh"), 4)
        self.assertIn('"$ROM" evidence/debug', text)
        self.assertIn('"$ROM" evidence/natural natural', text)
        self.assertIn('test "$debug_status" = 0 && test "$natural_status" = 0 && test "$victory_status" = 0 && test "$defeat_status" = 0', text)
        self.assertIn("POKEDND_NATURAL_SCENARIO=victory", text)
        self.assertIn("POKEDND_NATURAL_SCENARIO=defeat", text)
        self.assertIn("evidence/natural-victory natural", text)
        self.assertIn("evidence/natural-defeat natural", text)
        self.assertEqual(text.count("actions/upload-artifact@"), 1)

    def test_authored_encounter_runs_before_debug_inputs(self):
        script = (ROOT / "integration/emerald/ci_field_replay.sh").read_text()
        natural = script.split('if [ "${3:-debug}" = "natural" ]; then', 1)[1].split("# Discover where the native flow reaches after quickstart.", 1)[0]
        self.assertIn("key Down", natural)
        self.assertIn("key x", natural)
        self.assertIn('int(row["last_natural_local_id"]) != 5', natural)
        self.assertIn("natural_cleanup_status", natural)
        self.assertIn("post_cancel_moves", natural)
        self.assertIn('if [ "$scenario" != standard ]; then', natural)
        self.assertIn('if [ "$scenario" = victory ]; then', natural)
        self.assertIn('if [ "$(last_outcome)" = 2 ]; then break; fi', natural)
        self.assertIn('if int(row["post_cancel_moves"]) < 1:', natural)
        self.assertIn('exit 0', natural)
        self.assertIn("NATTERMINAL", natural)
        self.assertIn("natural_cleanup_status", natural)
        self.assertIn("outcome_acks", natural)
        self.assertIn("natural-resumed-", natural)
        self.assertNotIn("fixture-retry", natural)
        self.assertIn('xdotool keydown --window "$WINDOW" "$direction"', natural)
        self.assertIn('xdotool keyup --window "$WINDOW" "$direction"', natural)
        self.assertIn("NATIVE_AUTHORED_REPLAY_ACCEPTED.txt", natural)

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

    def test_rejected_debug_chord_is_consumed(self):
        source = (ROOT / "integration/emerald/pokednd_overworld.c").read_text()
        self.assertIn("(void)StartCombat(scenario, OBJECT_EVENTS_COUNT);", source)
        self.assertIn("gPokeDnDTriggerCount++;", source)
        self.assertNotIn("return StartCombat(scenario);", source)
        self.assertIn("return TRUE;", source.split("(void)StartCombat(scenario, OBJECT_EVENTS_COUNT);", 1)[1].split("return FALSE;", 1)[0])

    def test_rocket_field_interaction_is_native_and_safe(self):
        source = (ROOT / "integration/emerald/pokednd_overworld.c").read_text()
        self.assertIn("TryRocketFieldEncounter(newKeys)", source)
        self.assertIn("obj->graphicsId != OBJ_EVENT_GFX_ROCKET_M", source)
        self.assertIn("obj->localId == D20_ROCKET_LOCAL_ID", source)
        # Only the object in the facing tile may intercept the A interaction.
        # Side/rear Rockets must fall through to Emerald field handling.
        self.assertIn("facing = GetPlayerFacingDirection();", source)
        for direction in ("DIR_NORTH", "DIR_SOUTH", "DIR_WEST", "DIR_EAST"):
            self.assertIn("facing == " + direction, source)
        self.assertIn("obj->currentCoords.x != targetX", source)
        self.assertIn("obj->currentCoords.y != targetY", source)
        self.assertNotIn("AbsCoord(obj->currentCoords.x - player.x)", source)
        self.assertIn("u8 scenario = D20_SCENARIO_STANDARD;", source)
        self.assertIn("if (StartCombat(scenario, i))", source)
        self.assertIn("#ifdef POKEDND_NATIVE_REPLAY_ROCKET", source)
        self.assertIn("gMain.heldKeys & DPAD_UP", source)
        self.assertIn("gMain.heldKeys & DPAD_DOWN", source)
        self.assertIn("return FALSE;\n    }\n    return FALSE;\n}\nbool8 PokeDnD_HandleOverworldInput", source)

    def test_upstream_pin_matches_native_build(self):
        self.assertIn(PIN, INTEGRATION.read_text())


if __name__ == "__main__":
    unittest.main()
