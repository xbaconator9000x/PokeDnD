/* Original homebrew PokeDnD hardware test. No Pokemon ROM, tiles or sprites. */
#include "d20.h"
#include <stdint.h>
#define REG_DISPCNT (*(volatile uint16_t *)0x04000000)
#define REG_VCOUNT (*(volatile uint16_t *)0x04000006)
#define REG_KEYINPUT (*(volatile uint16_t *)0x04000130)
#define KEY_A 1
#define KEY_B 2
#define KEY_SELECT 4
#define KEY_START 8
#define KEY_RIGHT 16
#define KEY_LEFT 32
#define KEY_UP 64
#define KEY_DOWN 128
#define KEY_R 256
#define KEY_L 512
#define MODE3_BG2 0x0403
#define RGB(r,g,b) ((uint16_t)((r)|((g)<<5)|((b)<<10)))
#define SCREEN_W 240
#define SCREEN_H 160
#define MAP_X 48
#define MAP_Y 14
#define TILE 12
static volatile uint16_t *const screen = (volatile uint16_t *)0x06000000;
static D20Battle battle;
static int hero, pikachu, grunt;

static void fill(int x, int y, int w, int h, uint16_t color)
{
    for (int j = y; j < y + h; j++) {
        if (j < 0 || j >= SCREEN_H) continue;
        for (int i = x; i < x + w; i++) {
            if (i >= 0 && i < SCREEN_W) screen[j * SCREEN_W + i] = color;
        }
    }
}
static void glyph(int x, int y, char c, uint16_t color)
{
    /* 3x5 font for compact tactical UI. Each byte is a row of three pixels. */
    uint8_t rows[5] = {0,0,0,0,0};
    switch (c) {
        case 'A': { uint8_t a[5]={2,5,7,5,5}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'B': { uint8_t a[5]={6,5,6,5,6}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'C': { uint8_t a[5]={3,4,4,4,3}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'D': { uint8_t a[5]={6,5,5,5,6}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'E': { uint8_t a[5]={7,4,6,4,7}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'F': { uint8_t a[5]={7,4,6,4,4}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'G': { uint8_t a[5]={3,4,5,5,3}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'H': { uint8_t a[5]={5,5,7,5,5}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'I': { uint8_t a[5]={7,2,2,2,7}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'J': { uint8_t a[5]={1,1,1,5,2}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'K': { uint8_t a[5]={5,5,6,5,5}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'L': { uint8_t a[5]={4,4,4,4,7}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'M': { uint8_t a[5]={5,7,7,5,5}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'N': { uint8_t a[5]={5,7,7,7,5}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'O': { uint8_t a[5]={2,5,5,5,2}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'P': { uint8_t a[5]={6,5,6,4,4}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'Q': { uint8_t a[5]={2,5,5,7,3}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'R': { uint8_t a[5]={6,5,6,5,5}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'S': { uint8_t a[5]={3,4,2,1,6}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'T': { uint8_t a[5]={7,2,2,2,2}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'U': { uint8_t a[5]={5,5,5,5,7}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'V': { uint8_t a[5]={5,5,5,5,2}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'W': { uint8_t a[5]={5,5,7,7,5}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'X': { uint8_t a[5]={5,5,2,5,5}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'Y': { uint8_t a[5]={5,5,2,2,2}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case 'Z': { uint8_t a[5]={7,1,2,4,7}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case '0': { uint8_t a[5]={7,5,5,5,7}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case '1': { uint8_t a[5]={2,6,2,2,7}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case '2': { uint8_t a[5]={6,1,2,4,7}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case '3': { uint8_t a[5]={6,1,2,1,6}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case '4': { uint8_t a[5]={5,5,7,1,1}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case '5': { uint8_t a[5]={7,4,6,1,6}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case '6': { uint8_t a[5]={3,4,6,5,2}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case '7': { uint8_t a[5]={7,1,2,2,2}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case '8': { uint8_t a[5]={2,5,2,5,2}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case '9': { uint8_t a[5]={2,5,3,1,6}; for(int k=0;k<5;k++)rows[k]=a[k]; break; }
        case ':': rows[1]=2; rows[3]=2; break;
        case '!': rows[0]=2; rows[1]=2; rows[2]=2; rows[4]=2; break;
        case '/': rows[0]=1; rows[1]=1; rows[2]=2; rows[3]=4; rows[4]=4; break;
        case '-': rows[2]=7; break;
        default: break;
    }
    for (int j=0;j<5;j++) for(int i=0;i<3;i++)
        if ((rows[j] >> (2-i)) & 1) fill(x+i,y+j,1,1,color);
}
static void label(int x,int y,const char *s,uint16_t color)
{
    while (*s) { glyph(x,y,*s,color); x+=4; s++; }
}
static void draw(void)
{
    int actor = d20_current(&battle);
    fill(0,0,SCREEN_W,SCREEN_H,RGB(2,4,6));
    label(5,3,"POKEDND D20 GBA",RGB(31,29,20));
    for (int y=0;y<D20_H;y++) for(int x=0;x<D20_W;x++) {
        uint16_t grass = (x+y)%2 ? RGB(7,14,7) : RGB(9,16,8);
        int sx=MAP_X+x*TILE, sy=MAP_Y+y*TILE;
        if(battle.map[y][x]=='#') grass=RGB(13,11,10);
        fill(sx,sy,TILE-1,TILE-1,grass);
    }
    for(int i=0;i<battle.count;i++) {
        const D20Unit *u=&battle.units[i];
        int sx,sy;
        uint16_t color;
        if(!u->deployed||u->hp<=0)continue;
        sx=MAP_X+u->x*TILE; sy=MAP_Y+u->y*TILE;
        color=u->role==HUMAN?RGB(6,18,30):u->role==POKEMON?RGB(31,27,2):RGB(31,7,7);
        fill(sx+2,sy+2,7,8,color);
        glyph(sx+4,sy+3,u->role==HUMAN?'H':u->role==POKEMON?'P':'R',RGB(31,31,31));
        if(i==actor) {
            fill(sx,sy,TILE-1,1,RGB(31,31,31)); fill(sx,sy,1,TILE-1,RGB(31,31,31));
        }
    }
    fill(0,136,SCREEN_W,24,RGB(3,5,9));
    if(battle.outcome==ALLIES_WIN) label(6,139,"VICTORY SELECT RESET",RGB(28,31,15));
    else if(battle.outcome==ENEMIES_WIN) label(6,139,"DEFEAT SELECT RESET",RGB(31,12,12));
    else {
        label(6,138,actor==hero?"HUMAN":actor==pikachu?"PIKACHU":"ROCKET",RGB(29,27,20));
        label(98,138,"A ACT B END",RGB(29,27,20));
        label(6,148,"DPAD MOVE SELECT RESET",RGB(19,25,31));
        label(112,148,"L HIT R QUICK",RGB(19,25,31));
    }
    for(int i=0;i<3;i++) {
        const D20Unit *u=&battle.units[i];
        int barx=195, bary=17+i*10;
        fill(barx,bary,38,5,RGB(11,11,11));
        if(u->hp>0 && u->max_hp>0)
            fill(barx,bary,(u->hp*38)/u->max_hp,5,u->team?RGB(31,8,8):RGB(10,26,11));
        glyph(barx-7,bary,i==hero?'H':i==pikachu?'P':'R',RGB(31,31,31));
    }
}
static void reset(void)
{
    d20_init(&battle,2026);
    hero=d20_add(&battle,HUMAN,-1,1,4,true);
    pikachu=d20_add(&battle,POKEMON,hero,1,4,false);
    grunt=d20_add(&battle,ENEMY,-1,7,4,true);
    battle.units[hero].stats[DEX]=14;
    battle.units[pikachu].stats[DEX]=16;
    battle.units[pikachu].stats[CHA]=18;
    battle.units[grunt].hp=battle.units[grunt].max_hp=16;
    d20_wall(&battle,3,2,true);
    d20_wall(&battle,3,3,true);
    d20_wall(&battle,8,7,true);
    d20_start(&battle);
}
static void enemy_turn(void)
{
    D20Unit *r=&battle.units[grunt], *h=&battle.units[hero];
    int dist= (r->x>h->x?r->x-h->x:h->x-r->x)+(r->y>h->y?r->y-h->y:h->y-r->y);
    if(dist==1) (void)d20_attack(&battle,grunt,hero,TACKLE);
    else {
        int dx=r->x>h->x?-1:1;
        if(r->x!=h->x && !d20_walk(&battle,grunt,r->x+dx,r->y) && r->y!=h->y)
            (void)d20_walk(&battle,grunt,r->x,r->y+(r->y>h->y?-1:1));
        else if(r->x==h->x && r->y!=h->y)
            (void)d20_walk(&battle,grunt,r->x,r->y+(r->y>h->y?-1:1));
    }
    if(battle.outcome==FIGHTING) d20_next(&battle);
}
static void input(uint16_t keys)
{
    int who=d20_current(&battle);
    const D20Unit *u;
    int dx=0,dy=0;
    if(keys&KEY_SELECT) { reset(); return; }
    if(who<0) return;
    if(who==grunt) { enemy_turn(); return; }
    u=&battle.units[who];
    if(keys&KEY_RIGHT)dx=1;
    else if(keys&KEY_LEFT)dx=-1;
    else if(keys&KEY_UP)dy=-1;
    else if(keys&KEY_DOWN)dy=1;
    if(dx||dy) (void)d20_walk(&battle,who,u->x+dx,u->y+dy);
    if(keys&KEY_A) {
        if(who==hero) {
            if(!d20_deploy(&battle,hero,pikachu,u->x+1,u->y))
               (void)d20_deploy(&battle,hero,pikachu,u->x,u->y+1);
        } else (void)d20_attack(&battle,pikachu,grunt,THUNDERBOLT);
    }
    if((keys&KEY_L) && who==hero) (void)d20_attack(&battle,hero,grunt,TACKLE);
    if((keys&KEY_R) && who==pikachu) (void)d20_attack(&battle,pikachu,grunt,QUICK_ATTACK);
    if((keys&KEY_B) && battle.outcome==FIGHTING) d20_next(&battle);
}
int main(void)
{
    uint16_t previous=0;
    REG_DISPCNT=MODE3_BG2;
    reset();
    for(;;) {
        uint16_t keys;
        while(REG_VCOUNT>=160) { }
        while(REG_VCOUNT<160) { }
        keys=(uint16_t)(~REG_KEYINPUT)&0x03ff;
        if(d20_current(&battle)==grunt) input(0);
        else if(keys&~previous) input(keys&~previous);
        previous=keys;
        draw();
    }
}
