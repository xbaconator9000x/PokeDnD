"""Regression tests for replay-only Emerald field boot.

These fixtures contain original test text only; no Pokémon ROM or game assets.
"""
from test_emerald_heap import FIXTURE
import json
import importlib.util
from pathlib import Path
import tempfile
from unittest import TestCase, main, mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pokednd_emerald_apply", ROOT / "integration/emerald/apply.py"
)
apply = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apply)

OVERWORLD = '''#include "global.h"

void CB1_Overworld(void)
{
    if (gMain.callback2 == CB2_Overworld)
        DoCB1_Overworld(gMain.newKeys, gMain.heldKeys);
}
'''
TRUCK = ("SetWarpDestination(MAP_GROUP(MAP_INSIDE_OF_TRUCK), "
         "MAP_NUM(MAP_INSIDE_OF_TRUCK), WARP_ID_NONE, -1, -1);")


class EmeraldFieldBootTests(TestCase):
    def make_upstream(self, path: Path, warp: str = TRUCK):
        (path / "src").mkdir()
        (path / "include").mkdir()
        map_dir = path / "data/maps/OldaleTown"
        map_dir.mkdir(parents=True)
        (map_dir / "map.json").write_text(json.dumps({
            "id": "MAP_OLDALE_TOWN", "object_events": [{"x": i, "y": 1} for i in range(4)],
            "warp_events": [], "coord_events": [], "bg_events": []}))
        (path / "src/overworld.c").write_text(OVERWORLD)
        (path / "src/malloc.c").write_text(FIXTURE)
        (path / "src/crt0.s").write_text("\tbl InitializeWorkingMemory\nsp_sys: .word IWRAM_END - 0x1c0\nsp_irq: .word IWRAM_END - 0x60\n")
        (path / "ld_script_modern.ld").write_text("    /* BEGIN ROM DATA */")
        (path / "src/new_game.c").write_text(
            "static void WarpToTruck(void)\n"
            "{\n"
            "    if (IS_FRLG)\n"
            "        SetWarpDestination(MAP_GROUP(MAP_PALLET_TOWN_PLAYERS_HOUSE_2F), "
            "MAP_NUM(MAP_PALLET_TOWN_PLAYERS_HOUSE_2F), WARP_ID_NONE, 6, 6);\n"
            "    else\n"
            "        " + warp + "\n"
            "    WarpIntoMap();\n"
            "}\n"
        )

    def install(self, path: Path, **kwargs):
        with mock.patch.object(apply.subprocess, "check_output",
                               return_value=apply.PIN + "\n"):
            apply.install(path, **kwargs)

    def test_stack_bounds_and_boot_order(self):
        startup = "\tbl InitializeWorkingMemory\nsp_sys: .word IWRAM_END - 0x1c0\nsp_irq: .word IWRAM_END - 0x60\n"
        patched, linker = apply.instrument_stack(startup, "    /* BEGIN ROM DATA */")
        self.assertIn("strlo r2, [r0], #4", patched)
        self.assertLess(patched.index("bl InitializeWorkingMemory"), patched.index("strlo"))
        self.assertIn("SIZEOF(.iwram.bss)", linker)
        self.assertIn(">= 1024", linker)
        with self.assertRaises(RuntimeError):
            apply.instrument_stack(startup.replace("0x1c0", "0x200"), "    /* BEGIN ROM DATA */")

    def test_normal_build_preserves_vanilla_truck(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_upstream(root)
            original = (root / "src/new_game.c").read_text()
            self.install(root)
            self.assertEqual((root / "src/new_game.c").read_text(), original)
            self.assertIn("PokeDnD_HandleOverworldInput",
                          (root / "src/overworld.c").read_text())
            self.assertTrue((root / "src/pokednd_overworld.c").is_file())

    def test_replay_boot_goes_to_outdoor_oldale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_upstream(root)
            self.install(root, field_replay=True)
            modified = (root / "src/new_game.c").read_text()
            self.assertIn("MAP_GROUP(MAP_OLDALE_TOWN)", modified)
            self.assertIn("MAP_NUM(MAP_OLDALE_TOWN)", modified)
            self.assertIn("WARP_ID_NONE, 10, 12", modified)
            self.assertNotIn(TRUCK, modified)
            self.assertIn("gPokeDnDHeapPeak", (root / "src/malloc.c").read_text())
            self.assertIn("PokeDnD_HandleOverworldInput",
                          (root / "src/overworld.c").read_text())

    def test_authored_fixture_preserves_original_events_and_normal_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_upstream(root)
            path = root / "data/maps/OldaleTown/map.json"
            original = path.read_text()
            data = json.loads(apply.authored_replay_map(original))
            self.assertEqual(data["object_events"][:4], json.loads(original)["object_events"])
            self.assertEqual(len(data["object_events"]), 5)
            self.assertEqual(data["object_events"][4]["graphics_id"], "OBJ_EVENT_GFX_ROCKET_M")
            self.install(root)
            self.assertEqual(path.read_text(), original)

    def test_authored_fixture_rejects_conflicting_event(self):
        data = {"id": "MAP_OLDALE_TOWN", "object_events": [{"x": i, "y": 1} for i in range(4)],
                "warp_events": [{"x": 10, "y": 13}], "coord_events": [], "bg_events": []}
        with self.assertRaisesRegex(RuntimeError, "conflicts"):
            apply.authored_replay_map(json.dumps(data))

    def test_unknown_start_warp_fails_closed_without_partial_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_upstream(root, warp="UnexpectedWarp();")
            with self.assertRaisesRegex(RuntimeError, "truck start changed"):
                self.install(root, field_replay=True)
            self.assertEqual((root / "src/overworld.c").read_text(), OVERWORLD)
            self.assertFalse((root / "src/pokednd_overworld.c").exists())

    def test_natural_rocket_encounter_respects_native_actor_state(self):
        """Source contract: ordinary A interactions must not hijack busy NPCs."""
        source = (ROOT / "integration/emerald/pokednd_overworld.c").read_text()
        start = source.index("static bool8 TryRocketFieldEncounter(")
        end = source.index("bool8 PokeDnD_HandleOverworldInput(", start)
        handler = source[start:end]
        for required in (
            "GetPlayerFacingDirection()",
            "obj->currentCoords.x != targetX",
            "obj->currentCoords.y != targetY",
            "obj->frozen",
            "obj->invisible",
            "obj->currentElevation != player.elevation",
            "obj->heldMovementActive",
            "obj->singleMovementActive",
            "obj->mapGroup != gSaveBlock1Ptr->location.mapGroup",
            "obj->mapNum != gSaveBlock1Ptr->location.mapNum",
        ):
            with self.subTest(guard=required):
                self.assertIn(required, handler)
        # Scenario selection is replay-only; the ordinary build must retain
        # standard difficulty and all actor-state guards must precede combat.
        self.assertLess(handler.index("obj->singleMovementActive"),
                        handler.index("StartCombat(scenario, i)"))
        self.assertIn("u8 scenario = D20_SCENARIO_STANDARD;", handler)
        self.assertIn("#ifdef POKEDND_NATIVE_REPLAY_ROCKET", handler)
        self.assertIn("scenario = D20_SCENARIO_VICTORY;", handler)
        self.assertIn("scenario = D20_SCENARIO_DEFEAT;", handler)
        self.assertNotIn("AbsCoord(", handler)
        self.assertIn("gPokeDnDNaturalEncounterCount++", handler)
        self.assertIn("gPokeDnDLastNaturalLocalId = localId", handler)
        self.assertIn("StartCombat(scenario, i)", handler)

    def test_check_only_does_not_mutate_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_upstream(root)
            self.install(root, field_replay=True, check_only=True)
            self.assertIn(TRUCK, (root / "src/new_game.c").read_text())
            self.assertEqual((root / "src/malloc.c").read_text(), FIXTURE)
            self.assertEqual((root / "src/overworld.c").read_text(), OVERWORLD)


if __name__ == "__main__":
    main()
