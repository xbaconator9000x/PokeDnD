#include "d20.h"
#include <string.h>
uint8_t d20_speed_tiles(unsigned int feet)
{
    unsigned int tiles = feet / D20_FEET_PER_TILE;
    return (uint8_t)(tiles > 255u ? 255u : tiles);
}
static int ab(int x) { return x < 0 ? -x : x; }
static bool inside(int x, int y) { return x >= 0 && y >= 0 && x < D20_W && y < D20_H; }
static bool occupied(const D20Battle *b, int x, int y, int except)
{
    for (int i = 0; i < b->count; i++) {
        const D20Unit *u = &b->units[i];
        if (i != except && u->deployed && u->hp > 0 && u->x == x && u->y == y) return true;
    }
    return false;
}
static bool free_tile(const D20Battle *b, int x, int y, int except)
{ return inside(x, y) && b->map[y][x] != '#' && !occupied(b, x, y, except); }
void d20_init(D20Battle *b, uint32_t seed)
{
    memset(b, 0, sizeof(*b));
    b->cursor = -1; b->selected = -1; b->rng = seed ? seed : 0xC0FFEEu;
    for (int y = 0; y < D20_H; y++) for (int x = 0; x < D20_W; x++) b->map[y][x] = '.';
}
int d20_mod(int s) { return s >= 10 ? (s - 10) / 2 : -((11 - s) / 2); }
int d20_roll(D20Battle *b, int sides)
{
    if (!b || sides < 1) return 0;
    b->rng ^= b->rng << 13; b->rng ^= b->rng >> 17; b->rng ^= b->rng << 5;
    return (int)(b->rng % (uint32_t)sides) + 1;
}
int d20_add(D20Battle *b, D20Role role, int owner, int x, int y, bool deployed)
{
    int humans = 0, owned = 0, id;
    D20Unit *u;
    if (!b || b->started || b->count >= D20_MAX || !inside(x, y)) return -1;
    for (int i = 0; i < b->count; i++) {
        humans += b->units[i].role == HUMAN;
        owned += b->units[i].role == POKEMON && b->units[i].owner == owner;
    }
    if (role == HUMAN && (!deployed || owner != -1 || humans >= 3)) return -1;
    if (role == POKEMON && (deployed || owner < 0 || owner >= b->count ||
                            b->units[owner].role != HUMAN || owned >= 2)) return -1;
    if (role == ENEMY && (!deployed || owner != -1)) return -1;
    if (role > ENEMY || (deployed && !free_tile(b, x, y, -1))) return -1;
    id = b->count++; u = &b->units[id]; memset(u, 0, sizeof(*u));
    u->x = (int8_t)x; u->y = (int8_t)y; u->owner = (int8_t)owner;
    u->role = (uint8_t)role; u->team = role == ENEMY ? 1 : 0; u->deployed = deployed;
    u->hp = u->max_hp = role == HUMAN ? 24 : 18;
    u->ac = role == ENEMY ? 12 : 13; u->speed = d20_speed_tiles(30); u->proficiency = 2; u->ready_round = 1;
    for (int a = 0; a < ABILITIES; a++) u->stats[a] = 10;
    return id;
}
bool d20_wall(D20Battle *b, int x, int y, bool blocked)
{
    if (!b || !inside(x, y) || (blocked && occupied(b, x, y, -1))) return false;
    b->map[y][x] = blocked ? '#' : '.'; return true;
}
static void insert_turn(D20Battle *b, int id)
{
    int p = 0;
    D20Unit *u = &b->units[id];
    while (p < b->order_count) {
        D20Unit *o = &b->units[b->order[p]];
        if (u->initiative > o->initiative ||
           (u->initiative == o->initiative && d20_mod(u->stats[DEX]) > d20_mod(o->stats[DEX]))) break;
        p++;
    }
    for (int j = b->order_count; j > p; j--) b->order[j] = b->order[j - 1];
    b->order[p] = (int8_t)id; b->order_count++;
    if (p <= b->cursor) b->cursor++;
}
bool d20_start(D20Battle *b)
{
    int allies = 0, foes = 0;
    if (!b || b->started) return false;
    for (int i = 0; i < b->count; i++) if (b->units[i].deployed && b->units[i].hp > 0) {
        if (b->units[i].team) foes++; else allies++;
    }
    if (!allies || !foes) return false;
    /* d20_next increments the round when wrapping from cursor -1 to 0.
     * Start at zero so the first initiative turn belongs to round one. */
    b->round = 0; b->cursor = -1; b->started = 1;
    for (int i = 0; i < b->count; i++) if (b->units[i].deployed && b->units[i].hp > 0 && b->units[i].role != POKEMON) {
        D20Unit *u = &b->units[i];
        u->initiative = (int16_t)(d20_roll(b, 20) + d20_mod(u->stats[DEX]));
        insert_turn(b, i);
    }
    return d20_next(b);
}
int d20_current(const D20Battle *b)
{
    if (!b || !b->started || b->outcome != FIGHTING || b->cursor < 0 ||
        b->cursor >= b->order_count) return -1;
    return b->order[b->cursor];
}
int d20_actor(const D20Battle *b)
{
    if (d20_current(b) < 0) return -1;
    return b->selected;
}
bool d20_select(D20Battle *b, int actor)
{
    int owner = d20_current(b);
    if (owner < 0 || actor < 0 || actor >= b->count) return false;
    if (actor == owner) { b->selected = (int8_t)owner; return true; }
    D20Unit *p = &b->units[actor];
    if (b->units[owner].role != HUMAN || p->role != POKEMON ||
        p->owner != owner || !p->deployed || p->hp <= 0 ||
        p->ready_round > b->round || !p->commanded) return false;
    b->selected = (int8_t)actor;
    return true;
}
bool d20_command(D20Battle *b, int owner, int pokemon, bool spendBonus)
{
    D20Unit *h, *p;
    if (!b || owner < 0 || owner >= b->count ||
        d20_current(b) != owner || pokemon < 0 || pokemon >= b->count) return false;
    h = &b->units[owner]; p = &b->units[pokemon];
    if (h->role != HUMAN || h->hp <= 0 || p->role != POKEMON ||
        p->owner != owner || !p->deployed || p->hp <= 0 ||
        p->ready_round > b->round || p->commanded ||
        (spendBonus ? !h->bonus : !h->action)) return false;
    if (spendBonus) h->bonus = 0; else h->action = 0;
    p->commanded = 1;
    p->dodging = 0;
    p->action = p->asleep ? 0 : 1;
    p->movement = p->asleep ? 0 : p->speed;
    p->asleep = 0;
    b->selected = (int8_t)pokemon;
    return true;
}
bool d20_next(D20Battle *b)
{
    if (!b || !b->started || b->outcome != FIGHTING || !b->order_count) return false;
    for (int tries = 0; tries < D20_MAX * 3; tries++) {
        D20Unit *u;
        b->cursor++;
        if (b->cursor >= b->order_count) { b->cursor = 0; b->round++; }
        u = &b->units[b->order[b->cursor]];
        if (!u->deployed || u->hp <= 0 || u->ready_round > b->round) continue;
        u->action = u->asleep ? 0 : 1;
        u->bonus = u->asleep ? 0 : 1;
        u->reaction = u->asleep ? 0 : 1;
        u->movement = u->asleep ? 0 : u->speed;
        u->asleep = 0; /* One missed turn: prototype, not full 2024 condition. */
        b->selected = b->order[b->cursor];
        if (u->role == HUMAN) {
            for (int i = 0; i < b->count; i++) {
                D20Unit *p = &b->units[i];
                if (p->role != POKEMON || p->owner != b->selected ||
                    !p->deployed || p->hp <= 0) continue;
                p->commanded = 0;
                p->action = 0;
                p->movement = 0;
                p->dodging = 1; /* Default Dodge until a valid command. */
            }
        }
        return true;
    }
    return false;
}
bool d20_deploy(D20Battle *b, int owner, int pokemon, int x, int y)
{
    D20Unit *h, *p;
    if (!b || owner < 0 || owner >= b->count ||
        d20_current(b) != owner || d20_actor(b) != owner ||
        pokemon < 0 || pokemon >= b->count) return false;
    h = &b->units[owner]; p = &b->units[pokemon];
    if (h->role != HUMAN || h->hp <= 0 || !h->action || p->role != POKEMON || p->owner != owner ||
        p->deployed || p->hp <= 0 || ab(x-h->x) + ab(y-h->y) != 1 ||
        !free_tile(b, x, y, -1)) return false;
    h->action = 0; p->deployed = 1; p->x = (int8_t)x; p->y = (int8_t)y;
    p->ready_round = b->round + 1; /* No immediate attack after deployment. */
    p->initiative = h->initiative; /* Share the trainer initiative, no slot. */
    p->commanded = 0; p->dodging = 1;
    return true;
}
bool d20_dash(D20Battle *b, int actor)
{
    D20Unit *u;
    if (!b || actor < 0 || actor >= b->count || d20_actor(b) != actor)
        return false;
    u = &b->units[actor];
    if (!u->deployed || u->hp <= 0 || !u->action ||
        (unsigned int)u->movement + u->speed > 255u)
        return false;
    u->action = 0;
    u->movement = (uint8_t)(u->movement + u->speed);
    return true;
}
bool d20_walk(D20Battle *b, int actor, int x, int y)
{
    int distances[D20_W * D20_H], queue[D20_W * D20_H], head = 0, tail = 0, goal;
    const int dx[] = {1, -1, 0, 0}, dy[] = {0, 0, 1, -1};
    D20Unit *u;
    if (!b || actor < 0 || actor >= b->count ||
        d20_actor(b) != actor || !inside(x, y)) return false;
    u = &b->units[actor];
    if (!u->movement || !free_tile(b, x, y, actor) || (u->x == x && u->y == y)) return false;
    for (int i = 0; i < D20_W * D20_H; i++) distances[i] = -1;
    goal = y * D20_W + x;
    queue[tail++] = u->y * D20_W + u->x;
    distances[queue[0]] = 0;
    while (head < tail && distances[goal] == -1) {
        int v = queue[head++], vx = v % D20_W, vy = v / D20_W;
        for (int j = 0; j < 4; j++) {
            int nx = vx + dx[j], ny = vy + dy[j], next;
            if (!free_tile(b, nx, ny, actor)) continue;
            next = ny * D20_W + nx;
            if (distances[next] >= 0) continue;
            distances[next] = distances[v] + 1;
            queue[tail++] = next;
        }
    }
    if (distances[goal] < 1 || distances[goal] > u->movement) return false;
    u->movement = (uint8_t)(u->movement - distances[goal]);
    u->x = (int8_t)x; u->y = (int8_t)y; return true;
}
bool d20_los(const D20Battle *b, int x0, int y0, int x1, int y1)
{
    int dx, dy, sx, sy, err;
    if (!b || !inside(x0, y0) || !inside(x1, y1)) return false;
    dx = ab(x1-x0); dy = ab(y1-y0); sx = x0 < x1 ? 1 : -1; sy = y0 < y1 ? 1 : -1;
    err = dx - dy;
    while (x0 != x1 || y0 != y1) {
        int twice = 2 * err;
        int previousX = x0, previousY = y0;
        if (twice > -dy) { err -= dy; x0 += sx; }
        if (twice < dx) { err += dx; y0 += sy; }
        /* Avoid seeing diagonally through a fully closed wall corner.
         * A single adjacent wall still allows visibility; cover can be
         * modelled separately once 5.5e cover rules are implemented. */
        if (previousX != x0 && previousY != y0 &&
            b->map[previousY][x0] == '#' &&
            b->map[y0][previousX] == '#') return false;
        if ((x0 != x1 || y0 != y1) && b->map[y0][x0] == '#') return false;
    }
    return true;
}
static void resolve_victory(D20Battle *b)
{
    bool allies = false, foes = false;
    for (int i = 0; i < b->count; i++) if (b->units[i].deployed && b->units[i].hp > 0) {
        if (b->units[i].team) foes = true;
        else if (b->units[i].role == HUMAN) allies = true;
    }
    if (!foes) b->outcome = ALLIES_WIN;
    else if (!allies) b->outcome = ENEMIES_WIN;
}
D20Attack d20_attack(D20Battle *b, int actor, int target, D20Move move)
{
    D20Attack result = {0, 0, 0, 0, 0, 0, 0};
    D20Unit *a, *t;
    int range, roll, damage = 0, dice, sides;
    D20Stat stat;
    if (!b || actor < 0 || actor >= b->count ||
        d20_actor(b) != actor || target < 0 || target >= b->count ||
        move > SLEEP_POWDER) return result;
    a = &b->units[actor]; t = &b->units[target];
    if (!a->action || a->hp <= 0 || !t->deployed || t->hp <= 0 || a->team == t->team) return result;
    range = move == THUNDERBOLT ? 5 : move == SLEEP_POWDER ? 4 : 1;
    if (ab(a->x-t->x) + ab(a->y-t->y) > range || !d20_los(b, a->x, a->y, t->x, t->y)) return result;
    a->action = 0; result.legal = true;
    roll = d20_roll(b, 20);
    /* Dodge imposes disadvantage on attacks, not on CON saving throws. */
    if (move != SLEEP_POWDER && t->dodging) {
        result.second_roll = d20_roll(b, 20);
        if (result.second_roll < roll) roll = result.second_roll;
    }
    result.natural = roll;
    if (move == SLEEP_POWDER) {
        int dc = 8 + a->proficiency + d20_mod(a->stats[WIS]);
        result.total = roll + d20_mod(t->stats[CON]);
        result.hit = result.total < dc; /* CON saving throw. */
        if (result.hit) t->asleep = 1;
        return result;
    }
    stat = move == THUNDERBOLT ? CHA : move == QUICK_ATTACK ? DEX : STR;
    result.total = roll + a->proficiency + d20_mod(a->stats[stat]);
    result.crit = roll == 20;
    result.hit = result.crit || (roll != 1 && result.total >= t->ac);
    if (!result.hit) return result;
    dice = move == THUNDERBOLT ? 2 : 1;
    sides = move == THUNDERBOLT ? 8 : 6;
    for (int i = 0; i < dice * (result.crit ? 2 : 1); i++) damage += d20_roll(b, sides);
    if (move != THUNDERBOLT) damage += d20_mod(a->stats[stat]);
    if (damage < 0) damage = 0;
    if (damage > t->hp) damage = t->hp;
    t->hp = (int16_t)(t->hp - damage); result.damage = damage;
    resolve_victory(b); return result;
}
