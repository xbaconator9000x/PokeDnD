#ifndef POKEDND_D20_FIELD_H
#define POKEDND_D20_FIELD_H
#include "d20.h"

typedef bool (*D20Blocked)(int worldX, int worldY, void *ctx);
typedef struct {
    int originX, originY;
    int centerX, centerY;
} D20FieldProjection;
typedef struct {
    int human, pokemon, enemy;
} D20FieldEncounter;

/* Metatile conversion and collision projection; independent of rendering. */
bool d20_field_project(D20Battle *b, D20FieldProjection *p,
                       int worldX, int worldY, D20Blocked blocked, void *ctx);
bool d20_field_to_world(const D20FieldProjection *p, int x, int y, int *wx, int *wy);
bool d20_field_to_local(const D20FieldProjection *p, int wx, int wy, int *x, int *y);
bool d20_field_spawn_demo(D20Battle *b, const D20FieldProjection *p,
                          D20FieldEncounter *ids);
#endif
