#include "d20.h"
#include <assert.h>
#include <stdio.h>

static int assertions;
#define CHECK(x) do { assertions++; assert(x); } while (0)

static int seek(D20Battle *b, int owner)
{
    for (int i = 0; i < 100; i++) {
        if (d20_current(b) == owner) return 1;
        if (!d20_next(b)) return 0;
    }
    return 0;
}
static int next_time(D20Battle *b, int owner)
{
    return d20_next(b) && seek(b, owner);
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
    D20Battle a,b;
    CHECK(d20_mod(1)==-5);
    CHECK(d20_mod(9)==-1);
    CHECK(d20_mod(10)==0);
    CHECK(d20_mod(11)==0);
    CHECK(d20_mod(20)==5);
    d20_init(&a,777);d20_init(&b,777);
    for(int i=0;i<100;i++) {
        int n=d20_roll(&a,20);
        CHECK(n>=1 && n<=20 && n==d20_roll(&b,20));
    }
    CHECK(d20_roll(&a,0)==0);
    CHECK(d20_actor(&a)==-1);
}
static void test_party_limits(void)
{
    D20Battle b;int h[3];
    d20_init(&b,1);
    for(int i=0;i<3;i++) {
        h[i]=d20_add(&b,HUMAN,-1,i,0,true);
        CHECK(h[i]>=0);
    }
    CHECK(d20_add(&b,HUMAN,-1,3,0,true)==-1);
    CHECK(d20_add(&b,POKEMON,99,4,0,false)==-1);
    CHECK(d20_add(&b,POKEMON,h[0],0,0,false)>=0);
    CHECK(d20_add(&b,POKEMON,h[0],0,0,false)>=0);
    CHECK(d20_add(&b,POKEMON,h[0],0,0,false)==-1);
    CHECK(d20_add(&b,ENEMY,-1,0,0,true)==-1);
    CHECK(!d20_start(&b));
}
static void test_initiative_deploy_and_command(void)
{
    D20Battle b;int h,p,e;
    setup(&b,&h,&p,&e);
    CHECK(b.order_count==2);
    CHECK(seek(&b,h));
    CHECK(d20_actor(&b)==h);
    CHECK(!d20_deploy(&b,h,p,5,4));
    CHECK(!d20_deploy(&b,h,e,2,4));
    CHECK(!d20_command(&b,h,p,true));  /* Pokémon still in its ball. */
    CHECK(d20_deploy(&b,h,p,2,4));
    CHECK(b.units[h].action==0);
    CHECK(b.units[p].deployed && b.units[p].dodging);
    CHECK(b.units[p].initiative==b.units[h].initiative);
    CHECK(b.order_count==2);           /* One shared initiative, no extra slot. */
    CHECK(b.units[p].ready_round==b.round+1);
    CHECK(!d20_command(&b,h,p,true));  /* Deployment turn has no free attack. */
    CHECK(!d20_deploy(&b,h,p,1,3));
    CHECK(next_time(&b,h));
    CHECK(b.round>=b.units[p].ready_round);
    CHECK(b.units[p].dodging && !b.units[p].commanded);
    CHECK(!d20_select(&b,p));          /* Must pay a command cost first. */
    CHECK(d20_command(&b,h,p,true));
    CHECK(b.units[h].bonus==0 && b.units[h].action==1);
    CHECK(b.units[p].commanded && !b.units[p].dodging);
    CHECK(d20_actor(&b)==p && d20_current(&b)==h);
    CHECK(b.units[p].movement==6);
    CHECK(!d20_command(&b,h,p,false)); /* Never command same Pokémon twice. */
    CHECK(d20_select(&b,h));
    CHECK(d20_actor(&b)==h);
    CHECK(d20_select(&b,p));
    CHECK(!d20_select(&b,e));          /* Enemy not selectable by trainer. */
}
static void test_path_and_blockers(void)
{
    D20Battle b;int h,p,e;
    setup(&b,&h,&p,&e);
    CHECK(seek(&b,h));
    CHECK(d20_wall(&b,2,4,true));
    CHECK(!d20_walk(&b,h,2,4));
    CHECK(!d20_walk(&b,h,5,4));
    CHECK(d20_walk(&b,h,1,6));
    CHECK(b.units[h].movement==4);
    CHECK(!d20_walk(&b,h,6,6));
    CHECK(d20_walk(&b,h,2,6));
    CHECK(b.units[h].movement==3);
    CHECK(!d20_wall(&b,2,6,true));
    CHECK(!d20_walk(&b,h,2,6));
}
static void test_los_and_closed_corner(void)
{
    D20Battle b;
    d20_init(&b,42);
    CHECK(d20_los(&b,1,1,5,1));
    CHECK(d20_wall(&b,3,1,true));
    CHECK(!d20_los(&b,1,1,5,1));
    CHECK(d20_los(&b,1,1,1,5));
    CHECK(!d20_los(&b,-1,1,1,5));
    CHECK(d20_wall(&b,2,1,true));
    CHECK(d20_wall(&b,1,2,true));
    CHECK(!d20_los(&b,1,1,2,2));
    CHECK(!d20_los(&b,2,2,1,1));
    CHECK(d20_wall(&b,1,2,false));
    CHECK(d20_los(&b,1,1,2,2));
}
static void test_human_attack_consumes_action(void)
{
    D20Battle b;int h,p,e,hp;
    D20Attack r;
    setup(&b,&h,&p,&e);
    CHECK(seek(&b,h));
    CHECK(!d20_attack(&b,h,e,TACKLE).legal);
    CHECK(b.units[h].action==1);
    CHECK(d20_walk(&b,h,4,4));
    hp=b.units[e].hp;
    r=d20_attack(&b,h,e,TACKLE);
    CHECK(r.legal && r.natural>=1 && r.natural<=20);
    CHECK(b.units[e].hp<=hp);
    CHECK(!d20_attack(&b,h,e,TACKLE).legal);
    CHECK(!d20_deploy(&b,h,p,4,3));
}
static void test_pikachu_cha_move_and_switch_back(void)
{
    D20Battle b;int h,p,e;
    D20Attack r;
    setup(&b,&h,&p,&e);
    CHECK(seek(&b,h));
    CHECK(d20_deploy(&b,h,p,2,4));
    CHECK(next_time(&b,h));
    CHECK(d20_command(&b,h,p,true));
    r=d20_attack(&b,p,e,THUNDERBOLT);
    CHECK(r.legal);
    CHECK(r.total==r.natural+b.units[p].proficiency+d20_mod(b.units[p].stats[CHA]));
    CHECK(!d20_attack(&b,p,e,THUNDERBOLT).legal);
    CHECK(d20_select(&b,h));
    CHECK(b.units[h].action==1);
    CHECK(!d20_attack(&b,p,e,THUNDERBOLT).legal); /* Different selection. */
    CHECK(!d20_command(&b,h,p,false));
}
static void test_wall_prevents_thunderbolt(void)
{
    D20Battle b;int h,p,e;
    setup(&b,&h,&p,&e);
    CHECK(d20_wall(&b,3,4,true));
    CHECK(seek(&b,h));
    CHECK(d20_deploy(&b,h,p,2,4));
    CHECK(next_time(&b,h));
    CHECK(d20_command(&b,h,p,true));
    CHECK(!d20_attack(&b,p,e,THUNDERBOLT).legal);
    CHECK(b.units[p].action==1);
}
static void test_two_pokemon_two_resources(void)
{
    D20Battle b;int h,p1,p2,e;D20Attack r;
    d20_init(&b,2026);
    h=d20_add(&b,HUMAN,-1,1,4,true);
    p1=d20_add(&b,POKEMON,h,1,4,false);
    p2=d20_add(&b,POKEMON,h,1,4,false);
    e=d20_add(&b,ENEMY,-1,5,4,true);
    CHECK(h==0&&p1==1&&p2==2&&e==3);
    b.units[e].hp=b.units[e].max_hp=300;
    b.units[p1].stats[CHA]=18;b.units[p2].stats[CHA]=16;
    CHECK(d20_start(&b));
    CHECK(seek(&b,h));
    CHECK(d20_deploy(&b,h,p1,2,4));
    CHECK(next_time(&b,h));
    CHECK(d20_deploy(&b,h,p2,1,5));
    CHECK(next_time(&b,h));
    CHECK(b.order_count==2);
    CHECK(b.units[p1].dodging&&b.units[p2].dodging);
    CHECK(d20_command(&b,h,p1,true));
    r=d20_attack(&b,p1,e,THUNDERBOLT);CHECK(r.legal);
    CHECK(d20_command(&b,h,p2,false));
    CHECK(b.units[h].action==0&&b.units[h].bonus==0);
    CHECK(d20_actor(&b)==p2);
    r=d20_attack(&b,p2,e,THUNDERBOLT);CHECK(r.legal);
    CHECK(!d20_command(&b,h,p1,false));
    CHECK(!d20_command(&b,h,p2,true));
    CHECK(d20_select(&b,h));
    CHECK(!d20_attack(&b,h,e,TACKLE).legal);
    CHECK(next_time(&b,h));
    CHECK(b.units[p1].dodging&&b.units[p2].dodging);
    CHECK(!b.units[p1].commanded&&!b.units[p2].commanded);
}
static void test_dodge_grants_attack_disadvantage(void)
{
    D20Battle b;int h,p,e;D20Attack r;
    setup(&b,&h,&p,&e);
    CHECK(seek(&b,h));
    CHECK(d20_deploy(&b,h,p,2,4));
    CHECK(b.units[p].dodging);
    CHECK(seek(&b,e));
    r=d20_attack(&b,e,p,THUNDERBOLT);
    CHECK(r.legal);
    CHECK(r.second_roll>=1&&r.second_roll<=20);
    CHECK(r.natural>=1&&r.natural<=r.second_roll);
    CHECK(seek(&b,h));
    CHECK(d20_command(&b,h,p,true));
    CHECK(!b.units[p].dodging);
    CHECK(seek(&b,e));
    r=d20_attack(&b,e,p,THUNDERBOLT);
    CHECK(r.legal&&r.second_roll==0);
}
static void test_uncommanded_dodge_and_invalid_owner(void)
{
    D20Battle b;int h,p,e;
    setup(&b,&h,&p,&e);
    CHECK(seek(&b,h));
    CHECK(d20_deploy(&b,h,p,2,4));
    CHECK(next_time(&b,h));
    CHECK(!d20_command(&b,e,p,true));
    CHECK(!d20_command(&b,h,e,true));
    CHECK(!d20_command(&b,h,p,false) || b.units[p].commanded);
    CHECK(next_time(&b,h));
    CHECK(b.units[p].dodging && !b.units[p].commanded);
    CHECK(!d20_walk(&b,p,3,4));
    CHECK(!d20_attack(&b,p,e,THUNDERBOLT).legal);
}
static void test_first_round_and_deployment_cooldown(void)
{
    D20Battle b;
    int h, p, e;
    d20_init(&b, 20261115);
    h = d20_add(&b, HUMAN, -1, 1, 4, true);
    p = d20_add(&b, POKEMON, h, 1, 4, false);
    e = d20_add(&b, ENEMY, -1, 5, 4, true);
    CHECK(h >= 0 && p >= 0 && e >= 0);
    CHECK(d20_start(&b));
    CHECK(b.round == 1); /* First actor must not start in round two. */
    CHECK(seek(&b, h));
    CHECK(b.round == 1);
    CHECK(d20_deploy(&b, h, p, 2, 4));
    CHECK(b.units[p].ready_round == 2);
    CHECK(!d20_command(&b, h, p, true));
    CHECK(next_time(&b, h));
    CHECK(b.round == 2);
    CHECK(d20_command(&b, h, p, true));
}
static void test_invalid_actor_ids_fail_closed(void)
{
    D20Battle b;
    int h, p, e;
    d20_init(&b, 2026);
    h = d20_add(&b, HUMAN, -1, 1, 4, true);
    p = d20_add(&b, POKEMON, h, 1, 4, false);
    e = d20_add(&b, ENEMY, -1, 5, 4, true);
    CHECK(h == 0 && p == 1 && e == 2);
    /* Before initiative, current and selected are both -1.
     * Never interpret that sentinel as a valid caller index. */
    CHECK(!d20_walk(&b, -1, 2, 4));
    CHECK(!d20_attack(&b, -1, e, TACKLE).legal);
    CHECK(!d20_command(&b, -1, p, true));
    CHECK(!d20_deploy(&b, -1, p, 2, 4));
    CHECK(!d20_walk(&b, b.count, 2, 4));
    CHECK(!d20_attack(&b, b.count, e, TACKLE).legal);
    CHECK(d20_start(&b));
    CHECK(seek(&b, h));
    CHECK(!d20_walk(&b, -1, 2, 4));
    CHECK(!d20_attack(&b, -1, e, TACKLE).legal);
    CHECK(!d20_command(&b, -1, p, true));
    CHECK(!d20_deploy(&b, -1, p, 2, 4));
    CHECK(!d20_attack(&b, b.count, e, TACKLE).legal);
    CHECK(b.units[h].action == 1);
}
static void test_real_victory_requires_a_landed_attack(void)
{
    D20Battle b; int h,p,e; D20Attack r = {0}; bool won = false;
    setup(&b,&h,&p,&e);
    b.units[e].hp = b.units[e].max_hp = 1;
    b.units[e].ac = 2; /* Low-HP DEBUG encounter, not forced combat result. */
    CHECK(seek(&b,h));
    CHECK(d20_walk(&b,h,4,4));
    for (int turn=0;turn<8;turn++) {
        r=d20_attack(&b,h,e,TACKLE);
        CHECK(r.legal);
        if (r.hit) { won=true; break; }
        CHECK(b.outcome==FIGHTING && b.units[e].hp==1);
        CHECK(next_time(&b,h));
    }
    CHECK(won && b.outcome==ALLIES_WIN);
    CHECK(r.damage==1 && b.units[e].hp==0);
    CHECK(b.units[h].hp>0);
    CHECK(d20_current(&b)==-1);
    CHECK(!d20_next(&b));
    CHECK(!d20_attack(&b,h,e,TACKLE).legal);
}
static void test_real_defeat_requires_enemy_knockout(void)
{
    D20Battle b; int h,p,e; D20Attack r = {0}; bool lost = false;
    setup(&b,&h,&p,&e);
    b.units[h].hp = b.units[h].max_hp = 1;
    b.units[h].ac = 2;
    b.units[e].stats[STR] = 18;
    CHECK(seek(&b,e));
    CHECK(d20_walk(&b,e,2,4));
    for (int turn=0;turn<8;turn++) {
        r=d20_attack(&b,e,h,TACKLE);
        CHECK(r.legal);
        if (r.hit) { lost=true; break; }
        CHECK(b.outcome==FIGHTING && b.units[h].hp==1);
        CHECK(next_time(&b,e));
    }
    CHECK(lost && b.outcome==ENEMIES_WIN);
    CHECK(r.damage==1 && b.units[h].hp==0);
    CHECK(b.units[e].hp>0);
    CHECK(!d20_next(&b));
    CHECK(!d20_attack(&b,e,h,TACKLE).legal);
}
int main(void)
{
    test_ability_and_dice();
    test_party_limits();
    test_initiative_deploy_and_command();
    test_path_and_blockers();
    test_los_and_closed_corner();
    test_human_attack_consumes_action();
    test_pikachu_cha_move_and_switch_back();
    test_wall_prevents_thunderbolt();
    test_two_pokemon_two_resources();
    test_dodge_grants_attack_disadvantage();
    test_uncommanded_dodge_and_invalid_owner();
    test_invalid_actor_ids_fail_closed();
    test_first_round_and_deployment_cooldown();
    test_real_victory_requires_a_landed_attack();
    test_real_defeat_requires_enemy_knockout();
    printf("PASS: PokeDnD trainer-initiative D20 core (%d assertions, 13 scenarios)\n", assertions);
    return 0;
}
