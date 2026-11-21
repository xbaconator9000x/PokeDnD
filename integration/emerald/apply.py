#!/usr/bin/env python3
"""Apply the PokeDnD overworld input hook to an *external* pinned upstream checkout.

No vendor code or Pokémon assets are committed to the PokeDnD repository.
Refuse unknown revisions; exact source anchors are required.
"""
from pathlib import Path
import argparse
import subprocess
import shutil
import json

PIN = "4da9230cf7c1f1d7b0d47b45783b202666fffece"
SOURCE = Path(__file__).resolve().parents[2]



def instrument_stack(startup, linker):
    """Paint only unused system stack at boot, before any IRQ or C call."""
    anchor = "\tbl InitializeWorkingMemory\n"
    boundary = "    /* BEGIN ROM DATA */"
    if startup.count(anchor) != 1 or linker.count(boundary) != 1:
        raise RuntimeError("Pinned stack startup/linker anchor mismatch")
    if ("sp_sys: .word IWRAM_END - 0x1c0" not in startup
            or "sp_irq: .word IWRAM_END - 0x60" not in startup):
        raise RuntimeError("Pinned system stack top changed")
    startup = startup.replace(anchor, anchor + """
\tldr r0, =__pokednd_stack_low
\tldr r1, =__pokednd_stack_top
\tldr r2, =0xA55A3CC3
1:
\tcmp r0, r1
\tstrlo r2, [r0], #4
\tblo 1b
\tldr r0, =__pokednd_irq_low
\tldr r1, =__pokednd_irq_top
2:
\tcmp r0, r1
\tstrlo r2, [r0], #4
\tblo 2b
""".replace("\\t", "\t"), 1)
    linker = linker.replace(boundary, """
    __pokednd_stack_low = ALIGN(ADDR(.iwram.bss) + SIZEOF(.iwram.bss), 4);
    __pokednd_stack_top = ORIGIN(IWRAM) + LENGTH(IWRAM) - 0x1c0;
    __pokednd_irq_low = __pokednd_stack_top;
    __pokednd_irq_top = ORIGIN(IWRAM) + LENGTH(IWRAM) - 0x60;
    ASSERT(__pokednd_irq_top - __pokednd_irq_low == 352, "IRQ stack layout changed")
    ASSERT(__pokednd_stack_top - __pokednd_stack_low >= 1024, "Insufficient system stack")
""" + boundary, 1)
    return startup, linker


def instrument_heap(source):
    """Count actual occupied bytes, including allocated block headers."""
    edits = [
        ("static u32 sHeapSize;", """static u32 sHeapSize;
EWRAM_DATA volatile u32 gPokeDnDHeapCurrent = 0;
EWRAM_DATA volatile u32 gPokeDnDHeapPeak = 0;
EWRAM_DATA volatile u32 gPokeDnDHeapFailures = 0;
EWRAM_DATA volatile u32 gPokeDnDHeapCapacity = 0;
EWRAM_DATA volatile u32 gPokeDnDHeapEpoch = 0;"""),
        ("return pos->data;", """/* Account for the allocator's actual block span, including header.
                 * Saturate on corruption rather than wrap into a false low peak. */
                {
                    u32 occupied = pos->size + sizeof(struct MemBlock);
                    if (occupied < pos->size ||
                        occupied > gPokeDnDHeapCapacity ||
                        gPokeDnDHeapCurrent > gPokeDnDHeapCapacity - occupied)
                    {
                        gPokeDnDHeapCurrent = 0xFFFFFFFFu;
                        gPokeDnDHeapPeak = 0xFFFFFFFFu;
                    }
                    else
                    {
                        gPokeDnDHeapCurrent += occupied;
                        if (gPokeDnDHeapCurrent > gPokeDnDHeapPeak)
                            gPokeDnDHeapPeak = gPokeDnDHeapCurrent;
                    }
                }
                return pos->data;"""),
        ("if (pos->next == head)\n            return NULL;", """if (pos->next == head)
        {
            if (gPokeDnDHeapFailures != 0xFFFFFFFFu)
                gPokeDnDHeapFailures++;
            return NULL;
        }"""),
        ("block->allocated = FALSE;\n\n        // If", """/* Preserve the invalid sentinel across subsequent frees. */
        {
            u32 occupied = block->size + sizeof(struct MemBlock);
            if (occupied < block->size ||
                gPokeDnDHeapCurrent == 0xFFFFFFFFu ||
                occupied > gPokeDnDHeapCurrent)
            {
                gPokeDnDHeapCurrent = 0xFFFFFFFFu;
                gPokeDnDHeapPeak = 0xFFFFFFFFu;
            }
            else
                gPokeDnDHeapCurrent -= occupied;
        }
        block->allocated = FALSE;

        // If"""),
        ("sHeapSize = heapSize;", """sHeapSize = heapSize;
    /* An invalid epoch or counter is terminal for this replay.  A later
     * InitHeap must not launder an earlier allocation-accounting failure
     * into apparently valid evidence.  Only a fresh boot clears globals. */
    if (heapSize == 0 || gPokeDnDHeapEpoch == 0xFFFFFFFFu ||
        gPokeDnDHeapCurrent == 0xFFFFFFFFu ||
        gPokeDnDHeapPeak == 0xFFFFFFFFu ||
        gPokeDnDHeapFailures == 0xFFFFFFFFu)
    {
        gPokeDnDHeapCurrent = 0xFFFFFFFFu;
        gPokeDnDHeapPeak = 0xFFFFFFFFu;
        gPokeDnDHeapFailures = 0xFFFFFFFFu;
        gPokeDnDHeapEpoch = 0xFFFFFFFFu;
        gPokeDnDHeapCapacity = heapSize;
    }
    else
    {
        gPokeDnDHeapCurrent = 0;
        gPokeDnDHeapPeak = 0;
        gPokeDnDHeapFailures = 0;
        gPokeDnDHeapCapacity = heapSize;
        gPokeDnDHeapEpoch++;
    }"""),
    ]
    for old, new in edits:
        if source.count(old) != 1:
            raise RuntimeError("Pinned allocator anchor mismatch: " + old)
        source = source.replace(old, new, 1)
    return source


def authored_replay_map(original: str) -> str:
    """Append one map-authored opponent; never change existing map IDs/events."""
    data = json.loads(original)
    if data.get("id") != "MAP_OLDALE_TOWN":
        raise RuntimeError("Unexpected replay map identity")
    objects = data["object_events"]
    if len(objects) != 4:
        raise RuntimeError("Pinned Oldale object count changed")
    x, y = 10, 13
    for kind in ("object_events", "warp_events", "coord_events", "bg_events"):
        if any(e.get("x") == x and e.get("y") == y for e in data[kind]):
            raise RuntimeError("Replay opponent location conflicts with existing map event")
    objects.append({
        "graphics_id": "OBJ_EVENT_GFX_ROCKET_M", "x": x, "y": y,
        "elevation": 3, "movement_type": "MOVEMENT_TYPE_FACE_UP",
        "movement_range_x": 0, "movement_range_y": 0,
        "trainer_type": "TRAINER_TYPE_NONE", "trainer_sight_or_berry_tree_id": "0",
        "script": "0", "flag": "0",
    })
    return json.dumps(data, indent=2) + "\n"


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
    replay_map = upstream / "data/maps/OldaleTown/map.json"
    if field_replay:
        map_modified = authored_replay_map(replay_map.read_text(encoding="utf-8"))
    if field_replay:
        heap_target = upstream / "src/malloc.c"
        heap_modified = instrument_heap(heap_target.read_text(encoding="utf-8"))
        stack_target = upstream / "src/crt0.s"
        linker_target = upstream / "ld_script_modern.ld"
        stack_modified, linker_modified = instrument_stack(stack_target.read_text(), linker_target.read_text())
    if check_only:
        print("PASS: upstream SHA, hook anchors and replay warp verified")
        return
    if field_replay:
        stack_target.write_text(stack_modified)
        linker_target.write_text(linker_modified)
        heap_target.write_text(heap_modified, encoding="utf-8")
        replay_target.write_text(replay_modified, encoding="utf-8")
        replay_map.write_text(map_modified, encoding="utf-8")
    target.write_text(content.replace(include_anchor, include_replacement, 1)
                              .replace(anchor, modified, 1), encoding="utf-8")
    for dest, origin in target_files.items():
        shutil.copy2(origin, dest)
    if field_replay:
        # Replay-only source flag. The ordinary adapter never injects an NPC.
        # This is a test fixture using the upstream's own Rocket graphics.
        actor = upstream / "src/pokednd_overworld.c"
        actor.write_text("#define POKEDND_NATIVE_REPLAY_ROCKET 1\n" +
                         actor.read_text(encoding="utf-8"), encoding="utf-8")
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
