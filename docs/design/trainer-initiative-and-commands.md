# Trainer-linked initiative and commands — proposed PokéDND rules

Status: **implemented in the portable D20 core and integrated into both GBA input adapters; current exact-head emulator verification pending.** Source of direction: user design discussion, November 2026. These mechanics supersede the original separate-Pokémon-initiative POC approach when the next combat refactor is undertaken.

## Turns and initiative

- Each human trainer rolls initiative normally using D&D 2024/5.5e initiative rules.
- Their deployed Pokémon **share that trainer's initiative**. They do not roll separate initiatives or insert their own initiative slots.
- Within the trainer's turn, the player chooses the order in which the trainer acts and the commanded Pokémon resolve their actions, respecting action expenditure. Think of each human and their deployed Pokémon as one *initiative group*, not as autonomous Pokémon turns.
- Each human may bring up to two Pokémon. With three humans the intended maximum friendly composition remains three humans + six Pokémon.
- Trainer subclasses might later change command costs or tactics, but no exception is adopted for this first iteration.

## Command economy

- A trainer can spend their **Action OR Bonus Action** to issue a command to one of their deployed Pokémon.
- A command authorizes the designated Pokémon to take its chosen action, such as a move, after the relevant trainer resource has been spent. The Pokémon's attack is **not** an additional free trainer attack.
- An Action command and a Bonus Action command can direct two different Pokémon during the same trainer turn (one Pokémon per command). This matches the intended maximum roster of two Pokémon per human, and makes both trainer resources tactically meaningful.
- A Pokémon that is already deployed but **receives no command during the trainer's turn takes the Dodge action by default**, rather than picking an autonomous damaging action.
- Full party control is retained: the player chooses the Pokémon's move, target and eligible positioning when it has a command. Command selection is not AI automation.
- Pokémon reactions and movement, the effect of incapacitated trainers, and class-specific command improvements require later specification. Do not silently invent them.

## Deployment versus command

The previously chosen POC rule remains a starting point: **sending out a Pokémon spends the trainer's Action** to place it into the overworld on an adjacent passable tile. The current prototype delays the new Pokémon's first action until a later round. Whether an already-available Bonus Action may command a Pokémon deployed this turn is a separate balance question; the conservative prototype keeps the no-immediate-action deployment restriction.

## Quick example

A Ranger and two Pokémon act on initiative 14. The Ranger spends a Bonus Action to command Pikachu to use Thunderbolt, then an Action to command Ivysaur to use Vine Whip. Both Pokémon are directly controlled during the Ranger's initiative group, using their own attack abilities and move effects. If the Ranger instead attacks with their Action and commands only Pikachu as a Bonus Action, Ivysaur Dodges.

## Implementation and verification status

1. Preserve the tested portable C99 D20 core and stand-alone GBA POC as a baseline.
2. **Implemented in source:** Pokémon no longer enter initiative as independent entries. Trainer-owned selection and paid commands enforce Action/Bonus Action exhaustion, one command per Pokémon per trainer turn, automatic Dodge, no free action on deployment, and disadvantage for attacks targeting a Dodging Pokémon. Regression tests cover these behaviours.
3. **Implemented in source:** the standalone GBA and Emerald hook both support Action/Bonus commands, switching from the commanded Pokémon back to trainer, and an attack. The GBA demo displays a Dodge marker and an action-ready/used indicator; richer native Emerald turn HUDs remain future work.
4. **Testing underway:** host GCC/Clang/sanitizers, devkitARM GBA/Emerald builds, and real mGBA deployment→Bonus Action command→attack-state pixel verification. A genuine two-Pokémon-per-trainer emulator battle and all-native Emerald field combat remain outstanding.

## Related reference

[External Pokémon 5e reference](../research/pokemon-5e.md). The external rules are a research source, **not** authority for our action economy or an implementation dependency.
