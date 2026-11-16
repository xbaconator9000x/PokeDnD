"""Regression tests for replay-only Emerald field boot.

These fixtures contain original test text only; no Pokémon ROM or game assets.
"""
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
        (path / "src/overworld.c").write_text(OVERWORLD)
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
            self.assertIn("PokeDnD_HandleOverworldInput",
                          (root / "src/overworld.c").read_text())

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
        self.assertLess(handler.index("obj->singleMovementActive"),
                        handler.index("StartCombat(D20_SCENARIO_STANDARD)"))
        self.assertNotIn("AbsCoord(", handler)

    def test_check_only_does_not_mutate_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_upstream(root)
            self.install(root, field_replay=True, check_only=True)
            self.assertIn(TRUCK, (root / "src/new_game.c").read_text())
            self.assertEqual((root / "src/overworld.c").read_text(), OVERWORLD)


if __name__ == "__main__":
    main()
