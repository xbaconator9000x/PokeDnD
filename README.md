# PokéDND 🎲

**Core mission:** a reusable, creator-oriented D&D 5e (2024 / SRD 5.2.1) tactical RPG framework for Pokémon-derived overworld engines. **Pokémon mechanics are optional.** Creators can build conventional D&D campaigns with no Pokémon, Pokémon 5e (2024) campaigns, or hybrid adventures.

**Fundamental architecture:** [Core architecture and GBA-first / DS-ready contract](docs/CORE_ARCHITECTURE.md). The shared portable C99 rules and campaign data must remain independent of both Pokémon-specific rules and Emerald internals. Finish the GBA/pokeemerald-expansion playable proof first; design adapter boundaries for a future Nintendo DS/Gen 4 port without splitting current development effort.

**Current implementation status:** existing Rocket/Pikachu encounters, trainer-group initiative, command costs, and 3-human/2-Pokémon limits are experimental prototype mechanics, **not universal framework rules or verified Pokémon 5e (2024) defaults**. Native mGBA acceptance is still pending.

## Design

- Gen III-style world, with turn-based battles **on the overworld map**.
- Up to 3 humans, each commanding up to 2 Pokémon with **full direct party control**. **Now implemented in the portable engine:** Pokémon share their trainer's initiative and require an Action or Bonus Action command; uncommanded Pokémon Dodge. Native GBA/Emerald gameplay acceptance for this revision is still being tested.
- Sending out a Pokémon costs one human Action.
- D20 initiative and attacks, AC, proficiency, movement, six ability scores, and saving throws.
- Species-specific attack ability mapping: e.g. Pikachu's Thunderbolt uses CHA.

## External research and battle design

- [Pokémon 5e (2024) research references](docs/research/pokemon-5e.md) — official site, community combat conversion and Foundry module links; no copied third-party files.
- [Trainer-linked initiative and command economy](docs/design/trainer-initiative-and-commands.md) — **proposed PokéDND rule**: a human's Pokémon use their trainer's initiative; Action or Bonus Action to command; uncommanded Pokémon Dodge.

The original separate-initiative POC-01 remains in Git history. The active POC-03 source now implements trainer-group initiative, explicit Pokémon commands and a basic Dodge defence; see [POC-03 implementation and verification](docs/POC-03.md).

## What actually exists

**POC-01:** a portable C99 tactical rules module with deterministic dice, initiative, turn ordering, three-plus-six party limits, deployment, tile-based BFS movement, blocking terrain, line of sight, four sample attacks/saving throws and automated tests.

**Native GBA progress:** a separate, original Mode 3 top-down battlefield ROM now cross-compiles with devkitARM and has successfully booted in actual mGBA with a 240×160 LCD capture. This is a minimalist hardware demonstration, **not yet integrated into Emerald**; the A-button Pokémon deployment is independently verified by native mGBA key injection and before/after LCD captures. Complete movement, attack and enemy-turn gameplay remain unverified in the emulator. The host demo illustrates the same rules logic. Run host tests with:

    make test
    make demo

With devkitARM installed, build the standalone ROM using `make -C gba`. See [GBA demo controls](gba/README.md). Actual GBA boot evidence is in the `PokeDnD GBA hardware demo build` GitHub Actions artifacts.

## POC-03 rules and controls

A trainer's Action or Bonus Action can authorise one deployed Pokémon to act on the trainer's initiative; a Pokémon cannot be commanded twice in the same trainer turn. When uncommanded, it Dodges and incoming attacks roll with disadvantage. Pokémon deployment still consumes a human Action and cannot produce a free attack immediately. Both the standalone GBA and Emerald input adapters now expose the command action; their **current exact-head emulator acceptance is not yet established**. [Read the command contract](docs/design/trainer-initiative-and-commands.md).

## Next acceptance milestone

**POC-02:** pin pokeemerald-expansion, build a GBA ROM, run the same rules in actual Emerald overworld combat (human → Action deploy Pikachu → individual turns → grunt defeated → resume same map), and verify with mGBA gameplay/screenshots. See [POC notes](docs/POC-01.md).

## Licensing and separation

- [D&D SRD 5.2.1](https://www.dndbeyond.com/srd) (CC BY 4.0) is the rules reference.
- Deployment timing, Pokémon attack stats, damage dice and one-turn Sleep Powder are **homebrew**, not official 2024 D&D rules.
- Pokémon rights and sprites are not covered by the SRD licence. No proprietary ROM bytes, Shattered assets, saves or private keys are included here.
- Keep the project separate from Shattered and XGBA, importing only assets with appropriate permissions and provenance.
- Do not claim host tests demonstrate playable GBA or emulator acceptance.
