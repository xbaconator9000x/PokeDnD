# Core architecture and cross-platform contract

**Status: fundamental project direction.** This document governs new work in PokéDND. Changes to this direction require an explicit design decision; existing prototype behaviour is not automatically canonical.

## Product definition

PokéDND is a reusable, creator-oriented **D&D 5e 2024 / SRD 5.2.1 tactical RPG framework** targeting Pokémon-derived overworld engines. It must support **ordinary D&D campaigns with no Pokémon content at all**, Pokémon 5e (2024) campaigns, hybrid campaigns, and creator-defined rules/content. The Pokémon game engine is a platform host, not a mandatory game mechanic.

## Layer boundaries

1. **Portable rules core (C99):** deterministic dice/RNG interface, actor statistics, ability checks, saves, initiative, action economy, movement, combat, conditions, class/feature hooks, spell/effect hooks, encounter state and serialization. No Emerald globals, Pokémon species, graphics, audio, platform input, or DS APIs in core code.
2. **Optional rules/content modules:** SRD-compatible 2024 fantasy content; Pokémon 5e (2024) species, moves, capture, bonds, evolution and trainer mechanics; campaign-specific additions. Trainer is not a substitute for a human D&D class. Module enablement is explicit and Pokémon-off must be supported.
3. **Creator data pipeline:** platform-neutral, versioned definitions for actors, classes, encounters, actions, maps/events and campaigns, validated and compiled into bounded runtime representations. Do not hardcode Rocket, Pikachu, three humans, two Pokémon, or one particular initiative/command interpretation into shared APIs.
4. **Platform adapters:** GBA/pokeemerald-expansion first, DS/Gen 4 later. Adapter owns input mapping, UI, map/NPC integration, sprites, sound, platform memory and save transport. Neither platform's types leak into the portable core.
5. **Platform capabilities:** memory/VRAM/OAM budgets, viewport and interaction constraints are adapter-declared. DS may show a second-screen touch action bar; GBA uses native 240×160-compatible menus. Gameplay rules are shared; presentation and bounded content capacity can differ.

## Rules fidelity and provenance

- Base rules target D&D 2024 SRD 5.2.1; do not label non-SRD Player's Handbook material as SRD.
- Pokémon-specific rules target Pokémon 5e (2024) as a separate optional module. Verify individual rules against source material before coding. Foundry implementations are secondary implementation references, not automatic authority.
- Track rule provenance and intentional homebrew deviations. Existing trainer-group initiative, command costs, Dodge defaults, stat conversions and party caps are **prototype choices pending source verification**, not fundamental universal D&D or Pokémon 5e rules.
- Respect third-party licensing. Do not commit unlicensed book text, compendia, proprietary game assets, original ROMs, saves or keys.

## Development sequencing

**Priority 1: finish the existing GBA vertical slice** on draft PR #2 and the pinned pokeemerald-expansion upstream. Prove a real native mGBA input-driven encounter: initiate from overworld, resolve turns/movement/actions, win or lose, clean up and resume control. Preserve genuine screenshots, test logs and exact-head acceptance evidence. Compilation/host tests alone do not prove playability.

**Priority 2: reusable GBA framework.** Replace hardcoded actors/encounters with data-driven definitions. Demonstrate *Fighter versus Goblin* with Pokémon module disabled and a separate Pokémon 5e encounter with the module enabled, both on actual Emerald overworld maps.

**Priority 3: creator-facing packaging.** Provide schemas, compiler/validation, examples, documented extension points, save compatibility and build/test instructions.

**Priority 4: DS adapter.** Reuse the C99 rules, compiled campaign content and portable tests. Prototype native DS gameplay and dual-screen/touch UI, then evaluate Gen 4 ROM integration with real builds and emulator acceptance. DS design must influence interface boundaries now, but must not divert primary effort before GBA gameplay is proven.

## Acceptance and non-goals

- Portable-core tests must run without Emerald or Pokémon dependencies.
- A no-Pokémon campaign must build and play without Pokémon-specific actor or command assumptions.
- Both GBA and DS use the same versioned rules/data contracts; platform-dependent presentation remains separate.
- No automatic merges of draft PRs; no claim of mGBA/DS gameplay acceptance without genuine native input/LCD evidence.
- No scope mixing with Shattered, XGBA or other projects.
- Do not restart the current GBA implementation merely to redesign abstractions. Refactor incrementally behind tested interfaces.
