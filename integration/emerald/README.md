# Emerald engine bridge: POC-02

Upstream source baseline: rh-hideout/pokeemerald-expansion at
4da9230cf7c1f1d7b0d47b45783b202666fffece (13 November 2026).

Implemented: source-level portable metatile coordinate projection for a
12x10 tactical encounter, a caller-supplied collision query, no-encounter
fail-closed checks, and human/Pikachu/opponent party ID mapping.

The pending Emerald hook will wrap live GetPlayerPosition and
MapGridGetCollisionAt, preserve overworld object events and sprite rendering,
intercept a deliberate debug key chord, and switch to tactical control in place.
The current adapter is not yet connected to Emerald, and tests are host-side.

No Nintendo ROM data, proprietary assets, Shattered graphics, or saves should
be committed here. The SRD 5.2.1 rules are a design reference, not a licence
for Pokemon assets.
