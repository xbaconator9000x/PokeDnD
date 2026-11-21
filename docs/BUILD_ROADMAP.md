# Ordered build roadmap — GBA first, DS ready

**Status:** planned milestones, not completed work. Governed by [core architecture](CORE_ARCHITECTURE.md). These are twelve **substantial implementation PR scopes**, not twelve empty pull requests. Work is sequential and may be split only when tests/acceptance justify it. Current draft PR #2 remains the active GBA integration branch; do not merge unaccepted work.

**Automation policy:** pick the first unchecked milestone; implement meaningful code + tests; open/update a draft PR only after actual changes exist; run source/build tests and relevant genuine mGBA input/LCD tests; post exact SHA and evidence; mark complete only after acceptance. If blocked, report concrete blocker and continue safe independent work without falsely ticking the milestone. Never auto-merge to main, never publish ROMs/saves/secrets/assets, never equate compile with playability. DS is a future adapter, not a second parallel implementation yet.

- [ ] **01. Native Emerald vertical slice** — Repair genuine mGBA Rocket encounter activation; input-driven turn loop, victory/defeat/retreat, NPC restoration and LCD evidence. Preserve pinned upstream.\n  - Acceptance: reviewed code and regression tests; native hardware/emulator proof wherever gameplay is involved; documented resource limits and blockers.
- [ ] **02. Portable rules API and platform isolation** — Remove Emerald and Pokémon assumptions from C99 core; stable platform adapter API, deterministic RNG and reproducible state tests.\n  - Acceptance: reviewed code and regression tests; native hardware/emulator proof wherever gameplay is involved; documented resource limits and blockers.
- [ ] **03. 2024 SRD action economy and conditions** — Actions, bonus actions, reactions, movement, advantage/disadvantage, cover, conditions, concentration hooks and SRD provenance tests.\n  - Acceptance: reviewed code and regression tests; native hardware/emulator proof wherever gameplay is involved; documented resource limits and blockers.
- [ ] **04. Data-driven actor, class and encounter definitions** — Versioned schema/compiler, validated character templates, enemy templates, encounters, stat blocks and extension hooks.\n  - Acceptance: reviewed code and regression tests; native hardware/emulator proof wherever gameplay is involved; documented resource limits and blockers.
- [ ] **05. Pokémon-free Fighter vs Goblin** — Playable Emerald overworld combat with Pokémon module disabled; class features, equipment, initiative, AI and return to map.\n  - Acceptance: reviewed code and regression tests; native hardware/emulator proof wherever gameplay is involved; documented resource limits and blockers.
- [ ] **06. Native GBA tactical interface** — 240x160 tile/sprite-budgeted UI, targeting cursor, movement/attack range, turn order, action menus, combat log and controls.\n  - Acceptance: reviewed code and regression tests; native hardware/emulator proof wherever gameplay is involved; documented resource limits and blockers.
- [ ] **07. D&D 2024 character progression** — SRD classes/subclasses where licensed, skills, proficiency, feats, level-up, equipment and character sheets via extensible data.\n  - Acceptance: reviewed code and regression tests; native hardware/emulator proof wherever gameplay is involved; documented resource limits and blockers.
- [ ] **08. Spellcasting and effect engine** — Spell slots, targeting, saves, areas, duration, concentration, status and reusable effect definitions with resource-budget tests.\n  - Acceptance: reviewed code and regression tests; native hardware/emulator proof wherever gameplay is involved; documented resource limits and blockers.
- [ ] **09. Pokémon 5e 2024 optional module** — Source-verified rules for Pokémon actors, moves, bonds, capture, trainer mechanics, progression; independent enable/disable and licensing provenance.\n  - Acceptance: reviewed code and regression tests; native hardware/emulator proof wherever gameplay is involved; documented resource limits and blockers.
- [ ] **10. Mixed-party tactical encounters** — Traditional D&D, Pokémon-only and hybrid scenarios using same initiative/turn scheduler; configurable party limits, save/restore.\n  - Acceptance: reviewed code and regression tests; native hardware/emulator proof wherever gameplay is involved; documented resource limits and blockers.
- [ ] **11. Campaign creator pipeline and persistence** — Creator schemas, compiler, maps/events/quests/encounters, stable save format, migration, sample campaign, reproducible builds.\n  - Acceptance: reviewed code and regression tests; native hardware/emulator proof wherever gameplay is involved; documented resource limits and blockers.
- [ ] **12. GBA acceptance and DS handoff** — End-to-end native mGBA campaign playtest, artifacts, performance budgets, creator docs, stable shared contracts and DS adapter interface/spec.\n  - Acceptance: reviewed code and regression tests; native hardware/emulator proof wherever gameplay is involved; documented resource limits and blockers.

## Cross-cutting gates

- Core C99 compiles independently of Emerald, DS, and Pokémon content.
- Pokémon-off campaigns must have no mandatory Pokémon species, party, capture, command or graphics dependencies.
- SRD 5.2.1 and Pokémon 5e 2024 rule provenance are tracked separately; experimental rules are labeled.
- All campaign content is versioned, validated and platform-neutral; adapters own graphics/input/save transport.
- GBA adapter honors 240×160 LCD and GBA memory/VRAM/OAM budgets; DS adapter may exploit dual screens later.
- Native mGBA evidence must demonstrate actual controls, combat state transitions, NPC preservation and return to overworld.
- Do not mark a milestone complete solely because GitHub Actions is green; inspect the scope of each test.

## GitHub delivery queue

Each numbered scope should become a tracked issue and a substantial PR **when implementation starts**. Keep PR #2 open/draft until its native vertical slice is accepted. Do not create speculative empty branches or PRs. Later PRs can stack on tested predecessors without merging prematurely; preserve exact base/head relationships.
