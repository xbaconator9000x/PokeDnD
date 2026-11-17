#ifndef POKEDND_D20_H
#define POKEDND_D20_H
#include <stdbool.h>
#include <stdint.h>
#define D20_W 12
#define D20_H 10
#define D20_MAX 20
typedef enum { STR, DEX, CON, INT, WIS, CHA, ABILITIES } D20Stat;
typedef enum { HUMAN, POKEMON, ENEMY } D20Role;
typedef enum { TACKLE, QUICK_ATTACK, THUNDERBOLT, SLEEP_POWDER } D20Move;
typedef enum { FIGHTING, ALLIES_WIN, ENEMIES_WIN } D20Result;
typedef struct {
    int8_t x, y, owner;
    uint8_t role, team, stats[ABILITIES], speed, proficiency;
    int16_t hp, max_hp, ac, initiative;
    uint8_t deployed, asleep, action, bonus, reaction, movement;
    uint16_t ready_round;
} D20Unit;
typedef struct {
    char map[D20_H][D20_W];
    D20Unit units[D20_MAX];
    int8_t order[D20_MAX], cursor;
    uint8_t count, order_count, started, outcome;
    uint16_t round;
    uint32_t rng;
} D20Battle;
typedef struct {
    bool legal, hit, crit;
    int natural, total, damage;
} D20Attack;
void d20_init(D20Battle *b, uint32_t seed);
int d20_add(D20Battle *b, D20Role role, int owner, int x, int y, bool deployed);
bool d20_wall(D20Battle *b, int x, int y, bool blocked);
int d20_mod(int ability_score);
int d20_roll(D20Battle *b, int sides);
bool d20_start(D20Battle *b);
int d20_current(const D20Battle *b);
bool d20_next(D20Battle *b);
bool d20_deploy(D20Battle *b, int owner, int pokemon, int x, int y);
bool d20_walk(D20Battle *b, int actor, int x, int y);
bool d20_los(const D20Battle *b, int x0, int y0, int x1, int y1);
D20Attack d20_attack(D20Battle *b, int actor, int target, D20Move move);
#endif
