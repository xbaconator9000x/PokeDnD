#include "d20_field.h"

static int abs_int(int n) { return n < 0 ? -n : n; }
bool d20_field_to_world(const D20FieldProjection *p, int x, int y, int *wx, int *wy)
{
    if (!p || !wx || !wy || x < 0 || x >= D20_W || y < 0 || y >= D20_H) return false;
    *wx = p->originX + x; *wy = p->originY + y;
    return true;
}
bool d20_field_to_local(const D20FieldProjection *p, int wx, int wy, int *x, int *y)
{
    int lx, ly;
    if (!p || !x || !y) return false;
    lx = wx - p->originX; ly = wy - p->originY;
    if (lx < 0 || ly < 0 || lx >= D20_W || ly >= D20_H) return false;
    *x = lx; *y = ly;
    return true;
}
bool d20_field_project(D20Battle *b, D20FieldProjection *p,
                       int worldX, int worldY, D20Blocked blocked, void *ctx)
{
    if (!b || !p || !blocked || b->started || b->count) return false;
    p->centerX = 5; p->centerY = 4;
    p->originX = worldX - p->centerX;
    p->originY = worldY - p->centerY;
    for (int y = 0; y < D20_H; y++)
        for (int x = 0; x < D20_W; x++)
            b->map[y][x] = blocked(p->originX + x, p->originY + y, ctx) ? '#' : '.';
    return b->map[p->centerY][p->centerX] == '.';
}
bool d20_field_spawn_demo(D20Battle *b, const D20FieldProjection *p,
                          D20FieldEncounter *ids)
{
    int ex = -1, ey = -1;
    if (!b || !p || !ids || b->started || b->count ||
        p->centerX < 0 || p->centerX >= D20_W ||
        p->centerY < 0 || p->centerY >= D20_H ||
        b->map[p->centerY][p->centerX] != '.') return false;
    for (int distance = 3; distance <= 5 && ex < 0; distance++) {
        for (int y = 0; y < D20_H && ex < 0; y++)
            for (int x = D20_W - 1; x >= 0; x--) {
                if (abs_int(x-p->centerX) + abs_int(y-p->centerY) != distance ||
                    b->map[y][x] == '#' ||
                    !d20_los(b,p->centerX,p->centerY,x,y)) continue;
                ex = x; ey = y; break;
            }
    }
    if (ex < 0) return false;
    ids->human = d20_add(b, HUMAN, -1, p->centerX, p->centerY, true);
    if (ids->human < 0) return false;
    ids->pokemon = d20_add(b, POKEMON, ids->human,p->centerX,p->centerY,false);
    ids->enemy = d20_add(b, ENEMY, -1, ex,ey,true);
    return ids->pokemon >= 0 && ids->enemy >= 0;
}
