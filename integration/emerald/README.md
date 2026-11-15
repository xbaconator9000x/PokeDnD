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
gameplay persistence. Visual gameplay on a live Emerald field has not yet
been accepted.

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

The replay workflow runs Python regression tests for the default and replay
boot paths, rejects changed source anchors, and retains diagnostic captures.
**Screenshots, a successful source build or a green mGBA replay do not
establish tactical gameplay acceptance** without live EWRAM transitions.

Required next proof: trigger the Rocket encounter on a live Emerald map,
send out Pikachu, act with both combatants, resolve an attack, cancel or win,
and resume field movement, all captured by native emulator inputs.

No private ROM bytes, Shattered assets, saves, keys or copyrighted sprite
assets are committed here. Build artifacts are held privately for seven days.
