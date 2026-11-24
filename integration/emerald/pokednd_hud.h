#ifndef POKEDND_EMERALD_HUD_H
#define POKEDND_EMERALD_HUD_H

#include "d20.h"

/* Field-only display: no new Pokémon assets, menus or persistent state. */
bool8 PokeDnD_HudOpen(const D20Battle *battle, int human, int pokemon, int enemy);
void PokeDnD_HudRedraw(const D20Battle *battle);
void PokeDnD_HudMessage(const u8 *message);
void PokeDnD_HudAttack(const u8 *move, D20Attack attack);
void PokeDnD_HudClose(void);
void PokeDnD_HudAbandon(void);

#endif // POKEDND_EMERALD_HUD_H
