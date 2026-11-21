#ifndef POKEDND_D20_H
#define POKEDND_D20_H
#include <stdbool.h>
#include <stdint.h>
#define D20_W 12
#define D20_H 10
#define D20_MAX 20
/* Tactical scale: one orthogonal map tile is five feet. */
#define D20_FEET_PER_TILE 5
typedef enum { STR, DEX, CON, INT, WIS, CHA, ABILITIES } D20Stat;
typedef enum { HUMAN, POKEMON, ENEMY } D20Role;
typedef enum { TACKLE, QUICK_ATTACK, THUNDERBOLT, SLEEP_POWDER } D20Move;
typedef enum { FIGHTING, ALLIES_WIN, ENEMIES_WIN } D20Result;
typedef struct {
    int8_t x, y, owner;
    uint8_t role, team, stats[ABILITIES], speed, proficiency;
    int16_t hp, max_hp, ac, initiative;
    uint8_t deployed, asleep, action, bonus, reaction, movement;
    uint8_t commanded, dodging; /* Pokemon: commanded once per trainer turn, else Dodge */
    uint16_t ready_round;
} D20Unit;
typedef struct {
    char map[D20_H][D20_W];
    D20Unit units[D20_MAX];
    int8_t order[D20_MAX], cursor;
    int8_t selected; /* human/enemy turn owner, or commanded Pokemon */
    uint8_t count, order_count, started, outcome;
    uint8_t max_trainers, max_pokemon_per_trainer; /* Campaign policy, not fixed rules. */
    uint16_t round;
    uint32_t rng;
} D20Battle;
typedef struct {
    bool legal, hit, crit;
    int natural, total, damage;
    int second_roll; /* 0 normally; the second d20 when Dodge imposed disadvantage */
} D20Attack;
/* Creator-defined actor template. No species or copyrighted rules data embedded. */
typedef struct {
    uint8_t stats[ABILITIES];
    uint8_t speed_feet, proficiency;
    int16_t hp, ac;
} D20ActorTemplate;
/* Only before combat. Invalid templates leave the actor unchanged. */
bool d20_apply_template(D20Battle *b, int actor, const D20ActorTemplate *template_data);
void d20_init(D20Battle *b, uint32_t seed);
/* Set before adding actors; limits are validated against the current roster. */
bool d20_party_limits(D20Battle *b, unsigned int trainers, unsigned int pokemon_per_trainer);
int d20_add(D20Battle *b, D20Role role, int owner, int x, int y, bool deployed);
bool d20_wall(D20Battle *b, int x, int y, bool blocked);
int d20_mod(int ability_score);
int d20_roll(D20Battle *b, int sides);
bool d20_start(D20Battle *b);
int d20_current(const D20Battle *b);
int d20_actor(const D20Battle *b);
bool d20_select(D20Battle *b, int actor);
bool d20_command(D20Battle *b, int owner, int pokemon, bool spendBonus);
bool d20_next(D20Battle *b);
bool d20_deploy(D20Battle *b, int owner, int pokemon, int x, int y);
/* Convert a speed in feet to whole traversable tiles (round down). */
uint8_t d20_speed_tiles(unsigned int feet);
bool d20_dash(D20Battle *b, int actor);
bool d20_walk(D20Battle *b, int actor, int x, int y);
bool d20_los(const D20Battle *b, int x0, int y0, int x1, int y1);
D20Attack d20_attack(D20Battle *b, int actor, int target, D20Move move);
#endif
