# External research reference: Pokémon 5e

This document is a **pointer to external resources**, not a vendored copy of any rules, files, code, data, Pokémon sprites, assets, compendiums, or a claim that PokéDND implements them.

## Sources

- [Pokémon 5e website](https://poke5e.app/) — community tabletop Pokémon / D&D reference.
- [Pokémon 5e Core Rules](https://poke5e.app/rules/core-rules) — trainer play, Pokémon progression, catching, healing, combat and related systems. Select the **2024** edition on the website.
- [Pokémon 5e Combat](https://poke5e.app/rules/combat) — original trainer-command/initiative rules. **Reference, not the agreed PokéDND rule.**
- [Pokémon 5e status conditions](https://poke5e.app/rules/status-conditions) — candidate status conversions to evaluate, not adopted.
- [Pokémon 5e change log](https://poke5e.app/version-history) — the web rules are maintained and can evolve over time.
- [Foundry Pokémon 5e module](https://github.com/MissingGlitch/pokemon5e-foundry-module) — third-party digital rules/module implementation to study for architecture and dataset format.
- [Foundry module LICENSE](https://github.com/MissingGlitch/pokemon5e-foundry-module/blob/main/LICENSE) — the repository declares MIT for its covered software, but that does not imply permission to redistribute Pokémon or D&D material from elsewhere.
- [D&D SRD 5.2.1](https://www.dndbeyond.com/srd) — core D&D 2024-derived open rules reference, separate from Pokémon 5e.

## Foundry module: inspected technical inventory (14 November 2026)

**Primary technical source:** [MissingGlitch/pokemon5e-foundry-module](https://github.com/MissingGlitch/pokemon5e-foundry-module), version **0.13.0** in its inspected [module manifest](https://github.com/MissingGlitch/pokemon5e-foundry-module/blob/main/module.json). It requires Foundry VTT and the Foundry `dnd5e` system; it is **not** a native GBA runtime or an integration dependency.

The manifest identifies six compendium packs:

| Location | Foundry content type | Candidate PokéDND research |
| --- | --- | --- |
| `packs/pokedex_bestiary` | Pokémon Actor documents | D20 ability scores, HP, AC, movement, traits |
| `packs/pokemon_moves` | Move Items | Attack/save formulas, types, damage scaling, ranges, PP |
| `packs/pokemon_features` | Feature Items | Abilities, type mechanics and conditions |
| `packs/trainers` | Trainer Items | Human class and subclass concepts |
| `packs/items_and_consumables` | Item documents | Held items, capture tools and equipment |
| `packs/rules` | Journal entries | Rules, terminology and comparisons |

Its [README](https://github.com/MissingGlitch/pokemon5e-foundry-module/blob/main/README.md) **claims** over 1,000 prepared Pokémon and over 800 moves. These counts were not independently enumerated. The compendiums are stored as **LevelDB files** (`.ldb`, `MANIFEST` and `CURRENT`), not plain JSON. To inspect them at scale we'd need a separate read-only LevelDB/Foundry export process.

Useful inspected source code:

- [addPokemonSystemProperties.js](https://github.com/MissingGlitch/pokemon5e-foundry-module/blob/main/esmodules/addPokemonSystemProperties.js) extends Foundry `DND5E` damage-type and condition configuration with Pokémon-specific identifiers.
- [inputUpdateMoves.js](https://github.com/MissingGlitch/pokemon5e-foundry-module/blob/main/esmodules/html_inputs/inputUpdateMoves.js) identifies Pokémon moves as Foundry `weapon` Items with `system.type.value === "pokemon"` and updates their damage scaling / STAB.
- [inputMoveManager.js](https://github.com/MissingGlitch/pokemon5e-foundry-module/blob/main/esmodules/html_inputs/inputMoveManager.js) is a promising user-interface reference for learned move management, but not yet deeply audited.
- [inputEvolvePokemon.js](https://github.com/MissingGlitch/pokemon5e-foundry-module/blob/main/esmodules/html_inputs/inputEvolvePokemon.js) explicitly labels its evolution button **"NOT IMPLEMENTED YET"**. Do not assume the feature works simply because the README lists evolution-related capabilities.

### Proposed reuse workflow (not yet implemented)

1. Read a small sample of Actor and Move Item schemas externally, noting version and provenance; do not commit raw databases or copyrighted content.
2. Draft an original schema mapping into memory-efficient GBA tables: species → six ability scores/HP/AC/speed/traits; move → attack ability/action economy/range/dice/save/PP/type.
3. Keep **our** agreed trainer-initiative and command rules: each Pokémon shares its owner's initiative, an Action or Bonus Action commands one Pokémon, and an uncommanded Pokémon Dodges.
4. Build independent D20 regressions for representative Pokémon/moves before expanding coverage.

**Licence boundary:** the repository's [MIT licence](https://github.com/MissingGlitch/pokemon5e-foundry-module/blob/main/LICENSE) applies to covered software; it is **not** a blanket permission to redistribute Pokémon artwork, unrelated D&D text, Pokédex data or the embedded compendiums. The README's fair-use disclaimer is not a redistribution licence. No third-party module files, database dumps or assets are included in PokéDND.

## The distinction that matters

The external Pokémon 5e combat rules use **individual Pokémon initiative rolls** with specific trainer-command allowances. PokéDND **does not** intend to copy those mechanics wholesale.

Our proposed alternative, recorded in [Trainer initiative and commands](../design/trainer-initiative-and-commands.md):

- Each Pokémon acts within its **owning human trainer's initiative**.
- A trainer spends an **Action or Bonus Action** to command a Pokémon.
- If no command is issued, a deployed Pokémon takes **Dodge** (rather than making an autonomous attack).
- The player retains full tactical control over what each commanded Pokémon does.
- Each human may have up to two Pokémon on their roster; the party may contain up to three humans.

The current portable engine and GBA experiments still give Pokémon separate initiative; **this is an agreed design change for future implementation, not a completed feature**.

## Research backlog (not copied implementation)

Evaluate species-specific STR/DEX/CON/INT/WIS/CHA conversions, move attack abilities and ranges, DCs, level scaling, PP, type interactions, status duration, trainer class paths and Pokémon progression. Each candidate feature requires an independent balance decision, an original implementation and appropriate licensing review.

**Public repository policy:** only original PokéDND source and notes plus links to references. No ROM binaries, Shattered private assets, Pokémon 5e data dumps, private saves, secrets, or proprietary compendiums.
