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
