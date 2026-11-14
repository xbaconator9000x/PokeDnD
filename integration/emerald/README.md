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
- Initiative, movement and basic attacks. Pikachu deployment costs the human's
  Action only after its sprite has successfully spawned.
- Simple enemy turn; normal overworld input resumes after the encounter.
- Existing NPCs are temporarily frozen and individually restored afterward.
- SELECT cancellation restores the player's original tile; temporary sprites
  are deleted only when their object local ID and original map identity match.

## Prototype controls

| Game Boy button | In combat |
| --- | --- |
| D-pad | Move active friendly unit on the grid |
| A | Human deploys Pikachu / Pikachu uses Thunderbolt |
| L | Human uses Tackle |
| R | Pikachu uses Quick Attack |
| B | End current friendly turn |
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

`integration/emerald/ci_field_replay.sh` captures startup/title/quickstart/
field candidate frames on a real mGBA SDL frontend. The standalone replay
workflow uses previously built private run `43583355204` for rapid
diagnostics, not always the latest exact HEAD. Title/splash/Birch intro
screenshots are **not** gameplay acceptance.

Required next proof: trigger the Rocket encounter on a live Emerald map,
send out Pikachu, act with both combatants, resolve an attack, cancel or win,
and resume field movement, all captured by native emulator inputs.

No private ROM bytes, Shattered assets, saves, keys or copyrighted sprite
assets are committed here. Build artifacts are held privately for seven days.
