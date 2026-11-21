#include "d20.h"
#include <stdio.h>

static void board(const D20Battle *b)
{
    printf("\nRound %u  (H=Human, P=Pikachu, R=Rocket)\n", b->round);
    for (int y = 0; y < D20_H; y++) {
        for (int x = 0; x < D20_W; x++) {
            char cell = b->map[y][x];
            for (int i = 0; i < b->count; i++) {
                const D20Unit *u = &b->units[i];
                if (u->deployed && u->hp > 0 && u->x == x && u->y == y)
                    cell = u->role == HUMAN ? 'H' : u->role == POKEMON ? 'P' : 'R';
            }
            putchar(cell);
        }
        putchar('\n');
    }
}
static int seek(D20Battle *b, int id)
{
    for (int i = 0; i < 40; i++) {
        if (d20_current(b) == id) return 1;
        if (!d20_next(b)) break;
    }
    return 0;
}
int main(void)
{
    D20Battle b;
    int hero, pikachu, grunt;
    D20Attack hit;
    d20_init(&b, 2026);
    hero = d20_add(&b, HUMAN, -1, 1, 4, true);
    pikachu = d20_add(&b, POKEMON, hero, 1, 4, false);
    grunt = d20_add(&b, ENEMY, -1, 5, 4, true);
    b.units[hero].stats[DEX] = 14;
    b.units[pikachu].stats[CHA] = 18;
    b.units[pikachu].stats[DEX] = 16;
    d20_wall(&b, 4, 2, true);
    d20_start(&b);
    puts("POC-03 — Trainer-linked initiative and commands (host-side simulation)");
    board(&b);
    if (!seek(&b, hero) || !d20_deploy(&b, hero, pikachu, 2, 4)) return 1;
    puts("\nHuman spends Action: send out Pikachu!");
    board(&b);
    if (!d20_next(&b) || !seek(&b, hero) ||
        !d20_command(&b, hero, pikachu, true)) return 1;
    puts("Trainer spends Bonus Action: command Pikachu!");
    hit = d20_attack(&b, pikachu, grunt, THUNDERBOLT);
    if (!hit.legal) return 1;
    printf("\nPikachu Thunderbolt! d20=%d total=%d hit=%s damage=%d, grunt HP=%d\n",
           hit.natural, hit.total, hit.hit ? "yes" : "no", hit.damage, b.units[grunt].hp);
    board(&b);
    puts("\nRules engine demo only; NOT a playable GBA ROM or emulator capture.");
    return 0;
}
