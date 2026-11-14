# POC-01: Pikachu Rolls Initiative

Goal: a tiny independent, reproducible tactical rules library written in **portable C99**, so we can test combat logic before bringing it inside the GBA overworld. No heap allocation, OS dependencies, Pokémon sprites or ROM bytes.

## Implemented core

1. Six 5.5e ability scores and floor-rounded modifiers.
2. Deterministic seedable d20 rolls, proficiency and DEX initiative.
3. Up to three friendly human party members with two registered Pokémon each.
4. Deploying a Pokémon uses a human Action and adjacent free tile; it joins sorted initiative and begins acting the next round (homebrew).
5. Separate per-unit Action, Bonus Action, Reaction and movement counters.
6. Orthogonal breadth-first search with occupied tiles and blocking walls.
7. Line of sight and attack range.
8. Tackle: STR melee 1d6+STR; Quick Attack: DEX melee 1d6+DEX; Thunderbolt: CHA ranged 2d8; Sleep Powder: WIS-based DC with CON save. These are provisional homebrew damage/ability interpretations.
9. Natural 1 misses; natural 20 critical hits double the damage dice; combat outcome tracking.

## Known limitations

The demonstration uses a synthetic 12×10 grid, **not an Emerald map**. Sleep status skips a turn, not a full 2024 Unconscious/Concentration model. Pokémon types, moves, AI, classes, save/load, rendering and GBA integration are not implemented.

## POC-01 acceptance

Run make test and make demo. CI builds GCC, Clang and sanitizer tests. These do **not** establish actual GBA hardware compatibility or in-game acceptance.

## POC-02 genuine-ROM acceptance contract

- Pin a known pokeemerald-expansion revision and ARM toolchain.
- Build a source-based GBA ROM with tactical overworld hooks.
- Initiate combat on a real Emerald map without transitioning to the classic battle screen.
- Spend a human Action deploying Pikachu; control both separately.
- Attack and defeat a grunt; return to free exploration on the same map.
- Run in native mGBA and collect genuine LCD captures, logs and memory observations.
- Test a cold restart and save checkpoint, then scale toward 3 human + 6 Pokémon under GBA memory/OAM pressure.
- Never upload copyrighted ROM bytes, private user assets or saves to public CI.

## Verified native GBA boot (POC-01 extension)

On the development branch, original GBA Mode 3 rendering and button handlers were added as `gba/main.c`. The portable C99 rules core is cross-compiled with devkitARM into a small standalone homebrew ROM; no Emerald assets are included. Exact-head GitHub workflow run 43579199593 successfully built the ROM, launched it in the real mGBA SDL frontend, captured a 240×160 LCD PNG (12 colours), and uploaded ROM plus screenshot/log artifacts. This **verifies boot and rendered output only**, not correctness of key inputs, complete combat interactions, persistence, or Emerald overworld integration.
