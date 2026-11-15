#!/usr/bin/env python3
"""Apply the PokeDnD overworld input hook to an *external* pinned upstream checkout.

No vendor code or Pokémon assets are committed to the PokeDnD repository.
Refuse unknown revisions; exact source anchors are required.
"""
from pathlib import Path
import argparse
import subprocess
import shutil

PIN = "4da9230cf7c1f1d7b0d47b45783b202666fffece"
SOURCE = Path(__file__).resolve().parents[2]

def install(upstream: Path, *, check_only: bool = False, field_replay: bool = False):
    upstream = upstream.resolve()
    sha = subprocess.check_output(["git", "-C", str(upstream),
                                   "rev-parse", "HEAD"], text=True).strip()
    if sha != PIN:
        raise RuntimeError(f"Upstream SHA {sha} is not pinned SHA {PIN}")
    target = upstream / "src/overworld.c"
    content = target.read_text(encoding="utf-8")
    anchor = """void CB1_Overworld(void)
{
    if (gMain.callback2 == CB2_Overworld)
        DoCB1_Overworld(gMain.newKeys, gMain.heldKeys);
}"""
    modified = """void CB1_Overworld(void)
{
    if (gMain.callback2 == CB2_Overworld)
    {
        if (!PokeDnD_HandleOverworldInput(gMain.newKeys, gMain.heldKeys))
            DoCB1_Overworld(gMain.newKeys, gMain.heldKeys);
    }
}"""
    include_anchor = '#include "global.h"\n'
    include_replacement = include_anchor + '#include "pokednd_overworld.h"\n'
    if content.count(anchor) != 1 or content.count(include_anchor) != 1:
        raise RuntimeError("Emerald overworld callback/include mismatch; refusing partial patch")
    target_files = {
        upstream / "include/d20.h": SOURCE / "include/d20.h",
        upstream / "include/d20_field.h": SOURCE / "include/d20_field.h",
        upstream / "include/pokednd_overworld.h": SOURCE / "integration/emerald/pokednd_overworld.h",
        upstream / "include/pokednd_hud.h": SOURCE / "integration/emerald/pokednd_hud.h",
        upstream / "src/pokednd_hud.c": SOURCE / "integration/emerald/pokednd_hud.c",
        upstream / "src/d20.c": SOURCE / "src/d20.c",
        upstream / "src/d20_field.c": SOURCE / "src/d20_field.c",
        upstream / "src/pokednd_overworld.c": SOURCE / "integration/emerald/pokednd_overworld.c",
    }
    for dest, origin in target_files.items():
        if not origin.is_file():
            raise RuntimeError(f"Missing own integration source: {origin}")
        if dest.exists():
            raise RuntimeError(f"Destination exists; refusing overwrite: {dest}")
    # Native upstream quickstart skips Birch's introduction but starts in the
    # moving truck. For automated combat replay only, use a deterministic
    # outdoor spawn clear of Oldale's warps, trigger tiles and fixed NPCs.
    # Normal integration deliberately retains the original truck start.
    replay_target = upstream / "src/new_game.c"
    replay_original = None
    replay_modified = None
    if field_replay:
        if not replay_target.is_file():
            raise RuntimeError("Missing pinned upstream new-game source")
        replay_original = replay_target.read_text(encoding="utf-8")
        original_warp = ("SetWarpDestination(MAP_GROUP(MAP_INSIDE_OF_TRUCK), "
                         "MAP_NUM(MAP_INSIDE_OF_TRUCK), WARP_ID_NONE, -1, -1);")
        replay_warp = ("SetWarpDestination(MAP_GROUP(MAP_OLDALE_TOWN), "
                       "MAP_NUM(MAP_OLDALE_TOWN), WARP_ID_NONE, 10, 12);")
        if replay_original.count(original_warp) != 1:
            raise RuntimeError("Pinned truck start changed; refusing replay field warp")
        replay_modified = replay_original.replace(original_warp, replay_warp, 1)
    if check_only:
        print("PASS: upstream SHA, hook anchors and replay warp verified")
        return
    if field_replay:
        replay_target.write_text(replay_modified, encoding="utf-8")
    target.write_text(content.replace(include_anchor, include_replacement, 1)
                              .replace(anchor, modified, 1), encoding="utf-8")
    for dest, origin in target_files.items():
        shutil.copy2(origin, dest)
    print("PASS: installed PokeDnD source adapter in pinned Emerald checkout")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--field-replay", action="store_true",
                        help="CI-only: start outdoors in Oldale Town instead of the moving truck")
    args = parser.parse_args()
    install(args.upstream, check_only=args.check_only,
            field_replay=args.field_replay)
