# PokéDND 🎲

**Experimental project:** a Pokémon-inspired, top-down tactical CRPG grounded in the revised 2024 D&D 5e rules (SRD 5.2.1).

## Design

- Gen III-style world, with turn-based battles **on the overworld map**.
- Up to 3 humans, each commanding up to 2 Pokémon; independent party control.
- Sending out a Pokémon costs one human Action.
- D20 initiative and attacks, AC, proficiency, movement, six ability scores, and saving throws.
- Species-specific attack ability mapping: e.g. Pikachu's Thunderbolt uses CHA.

## What actually exists

**POC-01:** a portable C99 tactical rules module with deterministic dice, initiative, turn ordering, three-plus-six party limits, deployment, tile-based BFS movement, blocking terrain, line of sight, four sample attacks/saving throws and automated tests.

This is **not yet a playable .gba ROM**. Its host-side demo illustrates core logic only. Run locally with GCC or Clang:

    make test
    make demo

## Next acceptance milestone

**POC-02:** pin pokeemerald-expansion, build a GBA ROM, run the same rules in actual Emerald overworld combat (human → Action deploy Pikachu → individual turns → grunt defeated → resume same map), and verify with mGBA gameplay/screenshots. See [POC notes](docs/POC-01.md).

## Licensing and separation

- [D&D SRD 5.2.1](https://www.dndbeyond.com/srd) (CC BY 4.0) is the rules reference.
- Deployment timing, Pokémon attack stats, damage dice and one-turn Sleep Powder are **homebrew**, not official 2024 D&D rules.
- Pokémon rights and sprites are not covered by the SRD licence. No proprietary ROM bytes, Shattered assets, saves or private keys are included here.
- Keep the project separate from Shattered and XGBA, importing only assets with appropriate permissions and provenance.
- Do not claim host tests demonstrate playable GBA or emulator acceptance.
