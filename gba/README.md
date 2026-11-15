# Standalone GBA POC — not Pokémon Emerald

This module uses the **exact same portable tactical rules engine** as the GCC/Clang host simulation. It is a tiny original GBA Mode 3 top-down grid renderer with simple coloured unit blocks and no proprietary Pokémon sprites, maps, audio, or ROM content.

Build on devkitARM with make -C gba, or retrieve the unsigned/homebrew .gba from the **GBA hardware demo build** GitHub Actions artifact (after that workflow passes).

Controls:
- D-pad: move current friendly character through tiles (limited by its movement allowance).
- A: human deploys Pikachu (Action); Pikachu uses Thunderbolt (Action).
- L: while the human is selected, spend its **Action** to command deployed Pikachu.
- R: while the human is selected, spend its **Bonus Action** to command deployed Pikachu; while Pikachu is selected, use Quick Attack.
- START: while the human is selected, use Tackle (Action).
- B: while Pikachu is selected, return selection to the human; while the human is selected, end the shared trainer turn.
- SELECT: reset encounter.

Pokémon share trainer initiative rather than rolling separately. A command authorises a directly controlled Pokémon's action; without a command, it takes Dodge and incoming attacks roll with disadvantage. The HUD shows a D for Dodge and a top-right green/red action-use indicator when Pikachu is selected. The Rocket unit uses minimal scripted enemy movement and Tackle. No sophisticated AI, Pokémon type chart, class features or GBA save exists yet.

This can establish a **native GBA compilation** milestone, but a successful cross-compile alone does not prove the ROM boots correctly in mGBA or has been played. A real emulator session and LCD capture must verify playability. The ultimate POC is still **real Emerald overworld** tactical combat and seamless return to free exploration.
