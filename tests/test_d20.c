#include "d20.h"
#include <assert.h>
#include <stdio.h>

static int assertions;
#define CHECK(x) do { assertions++; assert(x); } while (0)

static int seek(D20Battle *b, int id)
{
    for (int k = 0; k < 80; k++) {
        if (d20_current(b) == id) return 1;
        if (!d20_next(b)) return 0;
    }
    return 0;
}
static void setup(D20Battle *b, int *h, int *p, int *e)
{
    d20_init(b, 12345);
    *h = d20_add(b, HUMAN, -1, 1, 4, true);
    *p = d20_add(b, POKEMON, *h, 1, 4, false);
    *e = d20_add(b, ENEMY, -1, 5, 4, true);
    CHECK(*h == 0 && *p == 1 && *e == 2);
    b->units[*h].stats[DEX] = 14;
    b->units[*p].stats[CHA] = 18;
    b->units[*p].stats[DEX] = 16;
    CHECK(d20_start(b));
}
static void test_ability_and_dice(void)
{
    D20Battle a, b;
    CHECK(d20_mod(1) == -5);
    CHECK(d20_mod(9) == -1);
    CHECK(d20_mod(10) == 0);
    CHECK(d20_mod(11) == 0);
    CHECK(d20_mod(20) == 5);
    d20_init(&a, 777); d20_init(&b, 777);
    for (int k = 0; k < 100; k++) {
        int r = d20_roll(&a, 20);
        CHECK(r >= 1 && r <= 20 && r == d20_roll(&b, 20));
    }
    CHECK(d20_roll(&a, 0) == 0);
}
static void test_party_limits(void)
{
    D20Battle b;
    int h[3];
    d20_init(&b, 1);
    for (int i = 0; i < 3; i++) {
        h[i] = d20_add(&b, HUMAN, -1, i, 0, true);
        CHECK(h[i] >= 0);
    }
    CHECK(d20_add(&b, HUMAN, -1, 3, 0, true) == -1);
    CHECK(d20_add(&b, POKEMON, 999, 4, 0, false) == -1);
    CHECK(d20_add(&b, POKEMON, h[0], 0, 0, false) >= 0);
    CHECK(d20_add(&b, POKEMON, h[0], 0, 0, false) >= 0);
    CHECK(d20_add(&b, POKEMON, h[0], 0, 0, false) == -1);
    CHECK(d20_add(&b, ENEMY, -1, 0, 0, true) == -1);
    CHECK(!d20_start(&b)); /* No enemies on the field. */
}
static void test_turn_and_deploy(void)
{
    D20Battle b;
    int h, p, e;
    setup(&b, &h, &p, &e);
    CHECK(b.order_count == 2);
    CHECK(seek(&b, h));
    CHECK(!d20_deploy(&b, h, p, 5, 4));
    CHECK(!d20_deploy(&b, h, e, 2, 4));
    CHECK(b.units[h].action == 1);
    CHECK(d20_deploy(&b, h, p, 2, 4));
    CHECK(b.units[h].action == 0);
    CHECK(b.units[p].deployed && b.order_count == 3);
    CHECK(b.units[p].ready_round == b.round + 1);
    CHECK(!d20_deploy(&b, h, p, 1, 3));
    CHECK(seek(&b, p));
    CHECK(b.round >= b.units[p].ready_round);
    CHECK(b.units[p].action == 1);
    CHECK(b.units[p].movement == 6);
}
static void test_path_and_blockers(void)
{
    D20Battle b;
    int h, p, e;
    setup(&b, &h, &p, &e);
    CHECK(seek(&b, h));
    CHECK(d20_wall(&b, 2, 4, true));
    CHECK(!d20_walk(&b, h, 2, 4));
    CHECK(!d20_walk(&b, h, 5, 4)); /* Occupied by enemy. */
    CHECK(d20_walk(&b, h, 1, 6));
    CHECK(b.units[h].movement == 4);
    CHECK(!d20_walk(&b, h, 6, 6)); /* Five tiles exceeds remaining four. */
    CHECK(d20_walk(&b, h, 2, 6));
    CHECK(b.units[h].movement == 3);
    CHECK(!d20_wall(&b, 2, 6, true));
    CHECK(!d20_walk(&b, h, 2, 6));
}
static void test_los(void)
{
    D20Battle b;
    d20_init(&b, 42);
    CHECK(d20_los(&b, 1, 1, 5, 1));
    CHECK(d20_wall(&b, 3, 1, true));
    CHECK(!d20_los(&b, 1, 1, 5, 1));
    CHECK(d20_los(&b, 1, 1, 1, 5));
    CHECK(!d20_los(&b, -1, 1, 1, 5));
    CHECK(d20_wall(&b, 2, 1, true));
    CHECK(d20_wall(&b, 1, 2, true));
    CHECK(!d20_los(&b, 1, 1, 2, 2)); /* Closed wall corner. */
    CHECK(!d20_los(&b, 2, 2, 1, 1)); /* Symmetric corner blocking. */
    CHECK(d20_wall(&b, 1, 2, false));
    CHECK(d20_los(&b, 1, 1, 2, 2)); /* One wall is not full occlusion. */
}
static void test_attack_action(void)
{
    D20Battle b;
    int h, p, e, hp;
    D20Attack r;
    setup(&b, &h, &p, &e);
    CHECK(seek(&b, h));
    CHECK(!d20_attack(&b, h, e, TACKLE).legal);
    CHECK(b.units[h].action == 1);
    CHECK(d20_walk(&b, h, 4, 4));
    hp = b.units[e].hp;
    r = d20_attack(&b, h, e, TACKLE);
    CHECK(r.legal && r.natural >= 1 && r.natural <= 20);
    CHECK(b.units[e].hp <= hp);
    CHECK(!d20_attack(&b, h, e, TACKLE).legal);
    CHECK(!d20_deploy(&b, h, p, 4, 3)); /* Both cost an Action. */
}
static void test_pikachu_cha_attack(void)
{
    D20Battle b;
    int h, p, e;
    D20Attack r;
    setup(&b, &h, &p, &e);
    CHECK(seek(&b, h));
    CHECK(d20_deploy(&b, h, p, 2, 4));
    CHECK(seek(&b, p));
    r = d20_attack(&b, p, e, THUNDERBOLT);
    CHECK(r.legal);
    CHECK(r.total == r.natural + b.units[p].proficiency + d20_mod(b.units[p].stats[CHA]));
    CHECK(!d20_attack(&b, p, e, THUNDERBOLT).legal);
}
static void test_wall_stops_spell(void)
{
    D20Battle b;
    int h, p, e;
    setup(&b, &h, &p, &e);
    CHECK(d20_wall(&b, 3, 4, true));
    CHECK(seek(&b, h));
    CHECK(d20_deploy(&b, h, p, 2, 4));
    CHECK(seek(&b, p));
    CHECK(!d20_attack(&b, p, e, THUNDERBOLT).legal);
    CHECK(b.units[p].action == 1);
}
int main(void)
{
    test_ability_and_dice();
    test_party_limits();
    test_turn_and_deploy();
    test_path_and_blockers();
    test_los();
    test_attack_action();
    test_pikachu_cha_attack();
    test_wall_stops_spell();
    printf("PASS: PokeDnD portable D20 core (%d assertions, 8 scenarios)\n", assertions);
    return 0;
}
