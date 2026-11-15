# POC-03 — trainer-owned initiative, paid Pokémon commands and Dodge

**Scope:** Original PokéDND 2024 D&D-inspired mechanics in the existing
portable C99 tactical core, the original homebrew GBA demonstrator, and the
native Emerald field-input adapter. This does not import any Foundry module
compendiums or proprietary Pokémon 5e dataset.

## Rules now implemented

- Roll initiative for each human trainer and opposing enemy only. Owned
  Pokémon share their trainer's initiative and do **not** insert new turn
  slots; the public d20_current() returns the owning trainer.
- The active, directly controlled character is separately exposed through
  d20_actor(). d20_select() may return from a commanded Pokémon to its
  trainer without exhausting a resource.
- d20_command(trainer, pokemon, spendBonus) consumes either exactly one
  trainer Action or Bonus Action, then gives the selected Pokémon exactly
  one Action and its own 6-tile movement allocation. The trainer may command
  at most two *different* owned Pokémon per turn using both resource types.
- When deployed without a command, each Pokémon automatically Dodges.
  Melee and ranged attack rolls against a Dodging Pokémon take the lower
  of two d20 rolls (disadvantage). The result records the second roll so
  host tests can verify this. The prototype's CON saving throw is unaffected.
- Sending out a Pokémon costs the human Action, requires a vacant adjacent
  tile, and cannot authorise an immediate free attack in that round. Failed
  placement or unauthorized command does not consume an Action/Bonus Action.
- A commanded Pokémon may move/act and return selection to its trainer
  during the same shared turn. Trainers keep any remaining resources.
- Each Pokémon automatically returns to uncommanded Dodge on the next
  trainer turn unless newly commanded.
- The allied side loses if all human trainers are down, even if deployed
  Pokémon remain present.

**2024 SRD limitations:** Dodge is currently implemented for attack-roll
disadvantage only; Dexterity save advantage, incapacity interactions,
readying actions, reactions, cover, concentration and full conditions are
not yet implemented. Pokémon move dice/types remain provisional homebrew.

## Available controls

| Input | Human selected | Commanded Pokémon selected |
| --- | --- | --- |
| D-pad | Move human | Move Pokémon |
| A | Deploy Pokémon (Action) | Thunderbolt (Action) |
| L | Command Pokémon using human Action | — |
| R | Command Pokémon using human Bonus Action | Quick Attack |
| START | Human Tackle | Return to trainer (homebrew GBA demo) |
| B | End shared trainer turn | Return to trainer |
| SELECT | Cancel Emerald encounter / reset GBA demo | Same |

**Native GBA debug demo:** upper-right green/red square indicates the
selected Pokémon has an attack Action ready/spent. The yellow Pokémon
shows a white D while Dodging. Real mGBA CI now attempts to verify
deployment, D disappearance on a paid command, and green→red Action change
after a Thunderbolt, using actual SDL key injection and LCD pixels.

**Emerald debug entry:** L+R+START while exploring a valid open area.
The Emerald hook retains the original map, NPCs, map collision and
D20 party state; its native milestones now include command/attack/Dodge
bits 5/6/7 respectively. Emerald field combat remains exploratory until
an actual field entry + combat input sequence is demonstrated in mGBA.

## Regression acceptance matrix

- Host C99 GCC and Clang: tests/test_d20.c covers ability modifiers,
  seedable dice, party limits, trainer initiative, deferred deployment,
  paid Action/Bonus commands, own Pokémon selection, once-per-turn commands,
  dual-Pokémon command budget, Dodge disadvantage, 12×10 BFS movement,
  wall/corner LOS, hit/crit and attack authorization.
- Host field projection: tests/test_d20_field.c verifies live-map collision,
  boundaries, unit ownership/placement and fail-closed encounter startup.
- Sanitizers: ASan/UBSan on the same host suite.
- Standalone native GBA: devkitARM compile plus true SDL mGBA replay
  (spawn→end turn→R command→A attack, visual markers recorded).
- Integrated Emerald: pinned upstream source build, linked ARM symbols,
  mGBA boot and field replay. A ROM that boots/title-captures without
  a demonstrable battle is **not** full gameplay acceptance.

These are acceptance requirements, not blanket pass claims.
Record exact PR head and GitHub run IDs separately as evidence matures.
The preceding standalone POC-01 code is preserved in Git history on
the project's earlier development commits and draft PR #1.

## Next vertical slice

1. Native mGBA exact-head demonstration of command + Dodge in the
   original standalone GBA prototype.
2. Native Emerald field encounter admission + Pikachu spawn + paid
   command + Thunderbolt + cancellation/field return, with real LCD
   captures and emulated memory probe values.
3. Extend an actual battle to three human teams / six Pokémon and
   richer AI without exceeding EWRAM, IWRAM, VRAM or OAM constraints.

**Sources:** [original trainer command specification](design/trainer-initiative-and-commands.md)
and [external Pokémon 5e research](research/pokemon-5e.md).
