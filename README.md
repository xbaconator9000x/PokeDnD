# PokéDND 🎲

**Experimental project:** a Pokémon-inspired, top-down tactical CRPG grounded in the revised 2024 D&D 5e rules (SRD 5.2.1).

## Design

- Gen III-style world, with turn-based battles **on the overworld map**.
- Up to 3 humans, each commanding up to 2 Pokémon with **full direct party control**. **Planned rule:** Pokémon share their human trainer's initiative, require an Action or Bonus Action command, and otherwise take Dodge. This is not yet implemented in the current engine.
- Sending out a Pokémon costs one human Action.
- D20 initiative and attacks, AC, proficiency, movement, six ability scores, and saving throws.
- Species-specific attack ability mapping: e.g. Pikachu's Thunderbolt uses CHA.

## External research and battle design

- [Pokémon 5e (2024) research references](docs/research/pokemon-5e.md) — official site, community combat conversion and Foundry module links; no copied third-party files.
- [Trainer-linked initiative and command economy](docs/design/trainer-initiative-and-commands.md) — **proposed PokéDND rule**: a human's Pokémon use their trainer's initiative; Action or Bonus Action to command; uncommanded Pokémon Dodge.

The current POC's independent Pokémon initiative is an earlier implementation to migrate, **not** the final design.

## What actually exists

**POC-01:** a portable C99 tactical rules module with deterministic dice, initiative, turn ordering, three-plus-six party limits, deployment, tile-based BFS movement, blocking terrain, line of sight, four sample attacks/saving throws and automated tests.

**Native GBA progress:** a separate, original Mode 3 top-down battlefield ROM now cross-compiles with devkitARM and has successfully booted in actual mGBA with a 240×160 LCD capture. This is a minimalist hardware demonstration, **not yet integrated into Emerald**; the A-button Pokémon deployment is independently verified by native mGBA key injection and before/after LCD captures. Complete movement, attack and enemy-turn gameplay remain unverified in the emulator. The host demo illustrates the same rules logic. Run host tests with:

    make test
    make demo

With devkitARM installed, build the standalone ROM using `make -C gba`. See [GBA demo controls](gba/README.md). Actual GBA boot evidence is in the `PokeDnD GBA hardware demo build` GitHub Actions artifacts.

## Next acceptance milestone

**POC-02:** pin pokeemerald-expansion, build a GBA ROM, run the same rules in actual Emerald overworld combat (human → Action deploy Pikachu → individual turns → grunt defeated → resume same map), and verify with mGBA gameplay/screenshots. See [POC notes](docs/POC-01.md).

## Licensing and separation

- [D&D SRD 5.2.1](https://www.dndbeyond.com/srd) (CC BY 4.0) is the rules reference.
- Deployment timing, Pokémon attack stats, damage dice and one-turn Sleep Powder are **homebrew**, not official 2024 D&D rules.
- Pokémon rights and sprites are not covered by the SRD licence. No proprietary ROM bytes, Shattered assets, saves or private keys are included here.
- Keep the project separate from Shattered and XGBA, importing only assets with appropriate permissions and provenance.
- Do not claim host tests demonstrate playable GBA or emulator acceptance.
