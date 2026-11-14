#include "d20_field.h"
#include <assert.h>
#include <stdio.h>

static int checks;
#define CHECK(x) do { checks++; assert(x); } while (0)
typedef struct {int minx,maxx,miny,maxy,wallx,wally,calls;} FakeMap;
static bool blocked(int x,int y,void *context)
{
    FakeMap *f=(FakeMap *)context;
    f->calls++;
    return x<f->minx||x>f->maxx||y<f->miny||y>f->maxy||(x==f->wallx&&y==f->wally);
}
static FakeMap open_map(void)
{
    FakeMap f={0,100,0,100,-999,-999,0};
    return f;
}
static void test_world_projection(void)
{
    D20Battle b; D20FieldProjection p;
    FakeMap f=open_map(); int wx,wy,x,y;
    f.wallx=42;f.wally=25;
    d20_init(&b,1);
    CHECK(d20_field_project(&b,&p,40,25,blocked,&f));
    CHECK(f.calls==D20_W*D20_H);
    CHECK(p.originX==35&&p.originY==21);
    CHECK(b.map[4][7]=='#');
    CHECK(d20_field_to_world(&p,5,4,&wx,&wy));
    CHECK(wx==40&&wy==25);
    CHECK(d20_field_to_local(&p,wx,wy,&x,&y));
    CHECK(x==5&&y==4);
    CHECK(!d20_field_to_local(&p,99,99,&x,&y));
    CHECK(!d20_field_to_world(&p,-1,4,&wx,&wy));
    CHECK(!d20_field_project(&b,&p,40,25,NULL,&f));
}
static void test_boundaries_and_fail_closed(void)
{
    D20Battle b; D20FieldProjection p; FakeMap f=open_map();
    d20_init(&b,2); f.maxx=7;f.maxy=7;
    CHECK(d20_field_project(&b,&p,2,2,blocked,&f));
    CHECK(b.map[0][0]=='#');
    f=open_map();f.wallx=40;f.wally=25;
    CHECK(!d20_field_project(&b,&p,40,25,blocked,&f));
    CHECK(b.map[4][5]=='#');
}
static void test_encounter(void)
{
    D20Battle b; D20FieldProjection p; D20FieldEncounter e;FakeMap f=open_map();
    d20_init(&b,2026);
    CHECK(d20_field_project(&b,&p,40,25,blocked,&f));
    CHECK(d20_field_spawn_demo(&b,&p,&e));
    CHECK(e.human==0&&e.pokemon==1&&e.enemy==2);
    CHECK(!b.units[e.pokemon].deployed && b.units[e.pokemon].owner==e.human);
    CHECK(b.units[e.enemy].team==1);
    CHECK(d20_los(&b,b.units[e.human].x,b.units[e.human].y,
                     b.units[e.enemy].x,b.units[e.enemy].y));
    CHECK(d20_start(&b));
    CHECK(!d20_field_spawn_demo(&b,&p,&e));
    CHECK(!d20_field_project(&b,&p,40,25,blocked,&f));
}
static void test_trapped(void)
{
    D20Battle b;D20FieldProjection p;D20FieldEncounter e;FakeMap f=open_map();
    d20_init(&b,9);
    f.minx=f.maxx=40;f.miny=f.maxy=25;
    CHECK(d20_field_project(&b,&p,40,25,blocked,&f));
    CHECK(!d20_field_spawn_demo(&b,&p,&e));
    CHECK(b.count==0);
}
int main(void)
{
    test_world_projection();test_boundaries_and_fail_closed();
    test_encounter();test_trapped();
    printf("PASS: overworld map adapter (%d assertions, 4 scenarios)\n",checks);
    return 0;
}
