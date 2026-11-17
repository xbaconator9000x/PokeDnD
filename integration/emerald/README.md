# POC-02 — actual Emerald overworld tactical hook (experimental)

Independent of Pokémon: Shattered. The 2024 D&D 5e SRD 5.2.1 is the
rules starting point, not a complete Pokémon×D&D implementation.

## Exact upstream baseline

- https://github.com/rh-hideout/pokeemerald-expansion
- Pinned commit: `4da9230cf7c1f1d7b0d47b45783b202666fffece`
- `apply.py` refuses a mismatching SHA, overwritten destination file, or changed
  overworld callback source anchor. The upstream source is fetched into
  ephemeral GitHub Actions build storage, never vendored here.

## Implemented inside native Emerald

The portable C99 rules engine is compiled into actual Emerald and called by
`CB1_Overworld` before regular field input:

- Debug entry: hold L + R and press START while field controls are unlocked
  and a valid encounter area exists.
- Map projection: the 12×10 combat grid samples real Emerald metatile
  collision, existing object events and map boundaries.
- Independent human / stowed Pikachu / Rocket test combatants, using existing
  `OBJ_EVENT_GFX_ROCKET_M` and `OBJ_EVENT_GFX_PIKACHU` sprites.
- Trainer-shared initiative, movement and basic attacks. Human spends an Action
  or Bonus Action to command Pikachu; an uncommanded Pokémon automatically Dodges
  and attack rolls against it have disadvantage. Pikachu deployment costs the
  human's Action only after its sprite has successfully spawned.
- Simple enemy turn; normal overworld input resumes after the encounter.
- Existing NPCs are temporarily frozen and individually restored afterward.
- SELECT cancellation restores the player's original tile; temporary sprites
  are deleted only when their object local ID and original map identity match.

## Prototype controls

| Game Boy button | In combat |
| --- | --- |
| D-pad | Move active friendly unit on the grid |
| A | Human deploys Pikachu / Pikachu uses Thunderbolt |
| L | Human spends Action to command Pikachu |
| R | Human spends Bonus Action to command Pikachu; selected Pikachu uses Quick Attack |
| START | Human uses Tackle (Action) |
| B | Switch from selected Pikachu to trainer; trainer ends shared turn |
| SELECT | Cancel and return player to original tile |

**Unimplemented:** dedicated turn HUD, cover mechanics, complex AI, actual
class/subclass progression, six deployed Pokémon, type chart, full 5.5e spell
conditions and concentration, animations, quest outcomes, XP, saving and
gameplay persistence. The native tactical inputs now have real mGBA memory
evidence, but the graphical combat presentation and a polished playable loop
still require work.

## Reproducible evidence

Host GCC/Clang/sanitizer and portable map projection tests run through
`make test`. Native CI fetches the pinned upstream, adds the source-only
integration, cross-compiles and checks actual linked ARM ELF symbols, then
boots the ROM in mGBA.

`integration/emerald/ci_field_replay.sh` captures genuine mGBA SDL frames
from an **exact-HEAD source build**, not a stale ROM artifact. Emerald's native
SELECT quickstart normally skips Birch's introduction but still starts inside
the moving truck; repeatedly pressing SELECT cannot bypass that map script.
Only the replay workflow uses `apply.py upstream --field-replay`, which
fail-closed patches the exact pinned `WarpToTruck` source to spawn outdoors
at Oldale Town (10, 12), clear of scripted trigger coordinates and NPCs.
Normal adapter builds preserve Emerald's original new-game warp.

The replay workflow runs Python regressions for the default/replay boots
and a mock GDB remote peer, then connects directly to the **running mGBA
debugger stub** (`mgba -g`) and reads the exact ARM-linked EWRAM variables.
A real, exact-head mGBA run at commit `d5c5df86521e6570f79d0c5fecc77a3914e64458`
passed 4/4 workflows and returned the following ordered live samples:

| Input checkpoint | Trigger | Failure | Sticky bits | Native state |
| --- | ---: | ---: | ---: | ---: |
| Field baseline | 0 | 0 | 0 | 0 |
| L+R+START encounter | 1 | 0 | 1 | 1 |
| A deploy Pikachu | 1 | 0 | 3 | 2 |
| B advance turn | 1 | 0 | 135 | 3 |
| SELECT cancel | 1 | 0 | 239 | 4 |

The sticky bits at cancellation also confirm a trainer command, legal Pokémon
attack and automatic Dodge were processed. The subsequent fail-closed replay
checks now require distinct live samples for command and attack before
cancellation; these stronger checks must pass at their own exact HEAD.
Evidence: https://github.com/xbaconator9000x/PokeDnD/actions/runs/43707170926

Later exact-head native replay acceptance at commit `1accaf7eebb7b56d5587ff6c4a43d3e0147b03c5` passed all four workflows, including input-driven debug, natural Rocket retreat, victory and defeat. The native outcome validator requires separate attack/turn checkpoints, HP-based terminal damage, result acknowledgement, sprite hit-reaction counters, cleanup and one subsequent overworld movement step. Evidence: https://github.com/xbaconator9000x/PokeDnD/actions/runs/44098534974

**Acceptance boundary:** GitHub reports native input/EWRAM validation success, but the uploaded LCD frames have not yet been independently inspected. The replay-only Oldale warp and victory/defeat modifiers are test fixtures, not default production gameplay. Resource-budget measurements and SRD versus homebrew rules provenance remain to be documented before roadmap issue #3 can be checked off. A passing validator or compilation is not a substitute for reviewing native LCD images.

No private ROM bytes, Shattered assets, saves, keys or copyrighted sprite
assets are committed here. Build artifacts are held privately for seven days.

## GBA linked-memory budget (new acceptance gate)

The native integration workflow now runs `tests/test_emerald_gba_memory.py` and
`integration/emerald/audit_gba_memory.py` against the **actual pinned-upstream
ARM ELF**. Its JSON evidence reports allocated EWRAM (256 KiB), IWRAM (32 KiB),
VRAM (96 KiB) and OAM (1 KiB) section ranges, overlapping/overflowing allocations,
and the sizes of named PokéDND RAM objects including `sBattle`. The audit fails
closed if core combat or diagnostic symbols are absent. The JSON is source-derived
build metadata, not proprietary ROM content.

**Not yet measured:** peak stack/heap concurrency, dynamic sprite/OAM allocation,
VRAM runtime ownership, VBlank timing, and gameplay performance. Linked ELF
allocation alone cannot establish those runtime budgets; native mGBA acceptance
and actual LCD review remain independent gates.

**Rules provenance:** trainer-group initiative, paid Pokémon commands, automatic
Dodge, species statistics and current encounter balance are experimental
PokéDND prototype rules, **not** asserted to be D&D 2024 SRD 5.2.1 or
source-verified Pokémon 5e (2024) mechanics. The C99 core must remain usable
without Pokémon content; future optional-module rules require independent
source/licence verification before being labelled canonical.
