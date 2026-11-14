/*
 * PokeDnD tactical overworld hook for pinned pokeemerald-expansion.
 * Original homebrew integration code. No ROM bytes or new art assets.
 *
 * L+R+START on the field triggers a one-human/one-Pikachu/one-Rocket encounter.
 * During combat: D-pad moves the currently active ally; A sends out Pikachu
 * as the human's Action or Pikachu uses Thunderbolt; L performs a human Tackle;
 * R performs Pikachu Quick Attack; B ends a friendly turn;
 * SELECT cancels the encounter without modifying the map or save.
 *
 * This is a debug encounter, not a replacement for normal Pokemon battles.
 */
#include "global.h"
#include "d20.h"
#include "d20_field.h"
#include "event_object_movement.h"
#include "field_control_avatar.h"
#include "field_player_avatar.h"
#include "fieldmap.h"
#include "main.h"
#include "script.h"
#include "constants/event_objects.h"
#include "constants/event_object_movement.h"

/* These local IDs are reserved only while this debug fight is active. */
#define D20_ROCKET_LOCAL_ID 231
#define D20_PIKACHU_LOCAL_ID 232
#define D20_DEBUG_CHORD (L_BUTTON | R_BUTTON | START_BUTTON)

/* Exported native probe: 0=idle, 1=started, 2=deployed, 3=turn,
 * 4=cancelled, 5=completed. Never interpret screenshots as this state. */
EWRAM_DATA volatile u32 gPokeDnDDiagnosticState;
/* Nonzero rejection codes make a vanilla-only replay actionable:
 * 1 field controls locked, 2 projection/spawn, 3 world coordinate,
 * 4 Rocket ID collision, 5 Pikachu ID collision, 6 sprite allocation,
 * 7 initiative start. A successful activation clears this value. */
EWRAM_DATA volatile u32 gPokeDnDStartFailure;
/* Incremented only when the native field input hook actually sees the chord.
 * A zero value distinguishes input/hook failures from encounter rejection. */
EWRAM_DATA volatile u32 gPokeDnDTriggerCount;
static EWRAM_DATA D20Battle sBattle;
static EWRAM_DATA D20FieldProjection sProjection;
static EWRAM_DATA D20FieldEncounter sUnits;
static EWRAM_DATA u8 sRocketObjectId;
static EWRAM_DATA u8 sPikachuObjectId;
static EWRAM_DATA u8 sActive;
static EWRAM_DATA u8 sMapGroup;
static EWRAM_DATA u8 sMapNum;
static EWRAM_DATA u8 sElevation;
static EWRAM_DATA s16 sEntryX;
static EWRAM_DATA s16 sEntryY;
static EWRAM_DATA bool8 sFrozenByD20[OBJECT_EVENTS_COUNT];
static EWRAM_DATA u8 sFrozenLocalId[OBJECT_EVENTS_COUNT];

static int AbsCoord(int a) { return a < 0 ? -a : a; }
static int DistanceTo(int a, int b)
{
    D20Unit *u = &sBattle.units[a];
    D20Unit *v = &sBattle.units[b];
    return AbsCoord(u->x - v->x) + AbsCoord(u->y - v->y);
}
static bool D20MapBlocked(int wx, int wy, void *ctx)
{
    (void)ctx;
    if (!AreCoordsInsidePlayerMap(wx, wy) || MapGridGetCollisionAt(wx, wy))
        return true;
    /* Honour existing world actors, not only metatile passability. */
    for (int i = 0; i < OBJECT_EVENTS_COUNT; i++) {
        const struct ObjectEvent *obj = &gObjectEvents[i];
        if (obj->active && !obj->isPlayer &&
            obj->currentCoords.x == wx && obj->currentCoords.y == wy)
            return true;
    }
    return false;
}
static void FreezeSurroundingActors(void)
{
    for (int i = 0; i < OBJECT_EVENTS_COUNT; i++) {
        struct ObjectEvent *obj = &gObjectEvents[i];
        sFrozenByD20[i] = FALSE;
        if (!obj->active || i == gPlayerAvatar.objectEventId || obj->frozen)
            continue;
        /* FreezeObjectEvent returns FALSE only when it actually froze the NPC. */
        if (!FreezeObjectEvent(obj)) {
            sFrozenByD20[i] = TRUE;
            sFrozenLocalId[i] = obj->localId;
        }
    }
}
static void CleanupCombat(bool8 restorePlayer)
{
    /* Never unfreeze a pre-existing scripted actor, or an NPC slot reused
     * after a map warp. Only revert the freezes we personally installed. */
    if (sActive && sMapGroup == gSaveBlock1Ptr->location.mapGroup &&
        sMapNum == gSaveBlock1Ptr->location.mapNum) {
        for (int i = 0; i < OBJECT_EVENTS_COUNT; i++) {
            struct ObjectEvent *obj = &gObjectEvents[i];
            if (sFrozenByD20[i] && obj->active && obj->frozen &&
                obj->localId == sFrozenLocalId[i] && obj->mapGroup == sMapGroup &&
                obj->mapNum == sMapNum)
                UnfreezeObjectEvent(obj);
        }
    }
    /* Debug cancel is non-destructive. Never teleport across a map warp. */
    if (restorePlayer && sActive &&
        sMapGroup == gSaveBlock1Ptr->location.mapGroup &&
        sMapNum == gSaveBlock1Ptr->location.mapNum &&
        gPlayerAvatar.objectEventId < OBJECT_EVENTS_COUNT)
        MoveObjectEventToMapCoords(&gObjectEvents[gPlayerAvatar.objectEventId], sEntryX, sEntryY);
    /* Object-event slots can be recycled after an unexpected map warp.
     * Never destroy a real map NPC merely because it reused our old slot. */
    if (sRocketObjectId < OBJECT_EVENTS_COUNT &&
        gObjectEvents[sRocketObjectId].active &&
        gObjectEvents[sRocketObjectId].localId == D20_ROCKET_LOCAL_ID &&
        gObjectEvents[sRocketObjectId].mapNum == sMapNum &&
        gObjectEvents[sRocketObjectId].mapGroup == sMapGroup)
        RemoveObjectEvent(&gObjectEvents[sRocketObjectId]);
    if (sPikachuObjectId < OBJECT_EVENTS_COUNT &&
        gObjectEvents[sPikachuObjectId].active &&
        gObjectEvents[sPikachuObjectId].localId == D20_PIKACHU_LOCAL_ID &&
        gObjectEvents[sPikachuObjectId].mapNum == sMapNum &&
        gObjectEvents[sPikachuObjectId].mapGroup == sMapGroup)
        RemoveObjectEvent(&gObjectEvents[sPikachuObjectId]);
    sActive = FALSE;
    sRocketObjectId = OBJECT_EVENTS_COUNT;
    sPikachuObjectId = OBJECT_EVENTS_COUNT;
}
static void MoveVisual(int id)
{
    int wx, wy;
    D20Unit *unit;
    if (id < 0 || id >= sBattle.count) return;
    unit = &sBattle.units[id];
    if (!d20_field_to_world(&sProjection, unit->x, unit->y, &wx, &wy))
        return;
    if (id == sUnits.human) {
        MoveObjectEventToMapCoords(&gObjectEvents[gPlayerAvatar.objectEventId],wx,wy);
    } else if (id == sUnits.pokemon && sPikachuObjectId < OBJECT_EVENTS_COUNT &&
               gObjectEvents[sPikachuObjectId].active) {
        MoveObjectEventToMapCoords(&gObjectEvents[sPikachuObjectId],wx,wy);
    } else if (id == sUnits.enemy && sRocketObjectId < OBJECT_EVENTS_COUNT &&
               gObjectEvents[sRocketObjectId].active) {
        MoveObjectEventToMapCoords(&gObjectEvents[sRocketObjectId],wx,wy);
    }
}
static bool SpawnPikachu(void)
{
    int id = sUnits.pokemon, wx, wy;
    u8 spriteId;
    D20Unit *human = &sBattle.units[sUnits.human];
    /* Do not allocate overworld resources for an illegal action. */
    if (!human->action || sBattle.units[id].deployed || sBattle.units[id].hp <= 0)
        return false;
    const int dirX[] = {1,0,-1,0};
    const int dirY[] = {0,1,0,-1};
    for (int i = 0; i < 4; i++) {
        int x = human->x + dirX[i], y = human->y + dirY[i];
        if (x < 0 || x >= D20_W || y < 0 || y >= D20_H ||
            sBattle.map[y][x] == '#')
            continue;
        if (!d20_field_to_world(&sProjection,x,y,&wx,&wy))
            continue;
        /* Sprite allocation must succeed before the Action is committed. */
        spriteId = SpawnSpecialObjectEventParameterized(
            OBJ_EVENT_GFX_PIKACHU, MOVEMENT_TYPE_NONE,
            D20_PIKACHU_LOCAL_ID, wx, wy, sElevation);
        if (spriteId == OBJECT_EVENTS_COUNT)
            continue;
        if (!d20_deploy(&sBattle, sUnits.human, id, x, y)) {
            RemoveObjectEvent(&gObjectEvents[spriteId]);
            continue;
        }
        sPikachuObjectId = spriteId;
        gPokeDnDDiagnosticState = 2;
        return true;
    }
    return false;
}
static bool StartCombat(void)
{
    struct MapPosition player;
    int wx, wy;
    /* Avoid scripts, link rooms, active movement and accidental re-entry. */
    if (sActive)
        return false;
    gPokeDnDDiagnosticState = 0;
    gPokeDnDStartFailure = 0;
    if (ArePlayerFieldControlsLocked()) {
        gPokeDnDStartFailure = 1;
        return false;
    }
    GetPlayerPosition(&player);
    d20_init(&sBattle, 0x12345678u ^ (u32)(player.x * 7919 + player.y * 104729));
    if (!d20_field_project(&sBattle,&sProjection,player.x,player.y,
                           D20MapBlocked,NULL) ||
        !d20_field_spawn_demo(&sBattle,&sProjection,&sUnits)) {
        gPokeDnDStartFailure = 2;
        return false;
    }
    if (!d20_field_to_world(&sProjection,sBattle.units[sUnits.enemy].x,
                           sBattle.units[sUnits.enemy].y,&wx,&wy)) {
        gPokeDnDStartFailure = 3;
        return false;
    }
    /* Fail closed if the world has a conflicting reserved local ID. */
    if (!TryGetObjectEventIdByLocalIdAndMap(D20_ROCKET_LOCAL_ID,
            gSaveBlock1Ptr->location.mapNum,
            gSaveBlock1Ptr->location.mapGroup, &sRocketObjectId)) {
        gPokeDnDStartFailure = 4;
        return false;
    }
    if (!TryGetObjectEventIdByLocalIdAndMap(D20_PIKACHU_LOCAL_ID,
            gSaveBlock1Ptr->location.mapNum,
            gSaveBlock1Ptr->location.mapGroup, &sPikachuObjectId)) {
        gPokeDnDStartFailure = 5;
        return false;
    }
    sMapGroup = gSaveBlock1Ptr->location.mapGroup;
    sMapNum = gSaveBlock1Ptr->location.mapNum;
    sElevation = player.elevation;
    sEntryX = player.x;
    sEntryY = player.y;
    sRocketObjectId = SpawnSpecialObjectEventParameterized(
        OBJ_EVENT_GFX_ROCKET_M, MOVEMENT_TYPE_NONE,
        D20_ROCKET_LOCAL_ID, wx, wy, sElevation);
    sPikachuObjectId = OBJECT_EVENTS_COUNT;
    if (sRocketObjectId == OBJECT_EVENTS_COUNT) {
        gPokeDnDStartFailure = 6;
        return false;
    }
    sBattle.units[sUnits.human].stats[DEX] = 14;
    sBattle.units[sUnits.pokemon].stats[DEX] = 16;
    sBattle.units[sUnits.pokemon].stats[CHA] = 18;
    sBattle.units[sUnits.enemy].hp = 16;
    sBattle.units[sUnits.enemy].max_hp = 16;
    if (!d20_start(&sBattle)) {
        /* The encounter is not active yet: CleanupCombat cannot own this
         * sprite. Roll back the freshly allocated Rocket explicitly. */
        if (sRocketObjectId < OBJECT_EVENTS_COUNT &&
            gObjectEvents[sRocketObjectId].active &&
            gObjectEvents[sRocketObjectId].localId == D20_ROCKET_LOCAL_ID &&
            gObjectEvents[sRocketObjectId].mapGroup == sMapGroup &&
            gObjectEvents[sRocketObjectId].mapNum == sMapNum)
            RemoveObjectEvent(&gObjectEvents[sRocketObjectId]);
        sRocketObjectId = OBJECT_EVENTS_COUNT;
        gPokeDnDStartFailure = 7;
        return false;
    }
    sActive = TRUE;
    gPokeDnDDiagnosticState = 1;
    FreezeSurroundingActors();
    return true;
}
static void EnemyPhase(void)
{
    int target;
    if (d20_current(&sBattle) != sUnits.enemy) return;
    /* A defeated human is not a valid target. Keep pursuing a living
     * deployed ally rather than pathfinding towards an unconscious trainer. */
    target = -1;
    if (sBattle.units[sUnits.human].deployed &&
        sBattle.units[sUnits.human].hp > 0)
        target = sUnits.human;
    if (sBattle.units[sUnits.pokemon].deployed &&
        sBattle.units[sUnits.pokemon].hp > 0 &&
        (target < 0 ||
         DistanceTo(sUnits.enemy, sUnits.pokemon) < DistanceTo(sUnits.enemy, target)))
        target = sUnits.pokemon;
    if (target < 0) {
        /* The core normally resolves defeat on the finishing attack.
         * Avoid invalid indexing if an external script changes the party. */
        (void)d20_next(&sBattle);
        return;
    }
    if (DistanceTo(sUnits.enemy,target) > 1) {
        /* Breadth-first pursuit navigates around terrain rather than getting
         * trapped by a wall when no immediately closer tile is available.
         * Work on the bounded tactical grid, not the full Emerald map. */
        static const int stepX[4] = { 0, 1, 0, -1 };
        static const int stepY[4] = { -1, 0, 1, 0 };
        int distances[D20_H][D20_W];
        int queueX[D20_W * D20_H], queueY[D20_W * D20_H];
        int head = 0, tail = 0, best = -1;
        D20Unit *enemy = &sBattle.units[sUnits.enemy];
        D20Unit *victim = &sBattle.units[target];
        for (int y = 0; y < D20_H; y++)
            for (int x = 0; x < D20_W; x++)
                distances[y][x] = -1;
        distances[victim->y][victim->x] = 0;
        queueX[tail] = victim->x;
        queueY[tail++] = victim->y;
        while (head < tail) {
            int x = queueX[head], y = queueY[head++];
            for (int i = 0; i < 4; i++) {
                int nx = x + stepX[i], ny = y + stepY[i];
                bool occupied = false;
                if (nx < 0 || nx >= D20_W || ny < 0 || ny >= D20_H ||
                    sBattle.map[ny][nx] == '#' || distances[ny][nx] >= 0)
                    continue;
                for (int j = 0; j < sBattle.count; j++) {
                    D20Unit *other = &sBattle.units[j];
                    if (j != sUnits.enemy && j != target && other->deployed &&
                        other->hp > 0 && other->x == nx && other->y == ny) {
                        occupied = true;
                        break;
                    }
                }
                if (occupied) continue;
                distances[ny][nx] = distances[y][x] + 1;
                queueX[tail] = nx;
                queueY[tail++] = ny;
            }
        }
        /* A neighbour may increase Manhattan distance while still being the
         * first step of the shortest navigable route around a wall. */
        int bestDistance = D20_W * D20_H + 1;
        for (int i = 0; i < 4; i++) {
            int x = enemy->x + stepX[i], y = enemy->y + stepY[i];
            if (x < 0 || x >= D20_W || y < 0 || y >= D20_H ||
                distances[y][x] < 0 || distances[y][x] >= bestDistance)
                continue;
            bool occupied = false;
            for (int j = 0; j < sBattle.count; j++) {
                D20Unit *other = &sBattle.units[j];
                if (j != sUnits.enemy && other->deployed && other->hp > 0 &&
                    other->x == x && other->y == y) {
                    occupied = true;
                    break;
                }
            }
            if (!occupied) {
                bestDistance = distances[y][x];
                best = i;
            }
        }
        if (best >= 0 && d20_walk(&sBattle, sUnits.enemy,
                                  enemy->x + stepX[best], enemy->y + stepY[best]))
            MoveVisual(sUnits.enemy);
    }
    if (DistanceTo(sUnits.enemy,target) == 1)
        (void)d20_attack(&sBattle,sUnits.enemy,target,TACKLE);
    if (sBattle.outcome == FIGHTING)
        (void)d20_next(&sBattle);
}
static void RunEnemyPhases(void)
{
    for (int i = 0; i < 6 && sBattle.outcome == FIGHTING &&
                        d20_current(&sBattle) == sUnits.enemy; i++)
        EnemyPhase();
}
static void MoveSelected(u16 newKeys)
{
    int id = d20_current(&sBattle), x, y;
    D20Unit *unit;
    if (id < 0 || id == sUnits.enemy) return;
    unit = &sBattle.units[id];
    x = unit->x; y = unit->y;
    if (newKeys & DPAD_UP) y--;
    else if (newKeys & DPAD_DOWN) y++;
    else if (newKeys & DPAD_LEFT) x--;
    else if (newKeys & DPAD_RIGHT) x++;
    else return;
    if (d20_walk(&sBattle,id,x,y))
        MoveVisual(id);
}
bool8 PokeDnD_HandleOverworldInput(u16 newKeys, u16 heldKeys)
{
    int id;
    if (!sActive) {
        if ((newKeys & START_BUTTON) && (heldKeys & D20_DEBUG_CHORD) == D20_DEBUG_CHORD) {
            gPokeDnDTriggerCount++;
            return StartCombat();
        }
        return FALSE;
    }
    /* Always yield to Emerald if the map changed unexpectedly. */
    if (sMapGroup != gSaveBlock1Ptr->location.mapGroup ||
        sMapNum != gSaveBlock1Ptr->location.mapNum) {
        CleanupCombat(FALSE);
        return FALSE;
    }
    if (newKeys & SELECT_BUTTON) {
        CleanupCombat(TRUE);
        gPokeDnDDiagnosticState = 4;
        return TRUE;
    }
    RunEnemyPhases();
    if (sBattle.outcome != FIGHTING) {
        CleanupCombat(FALSE);
        gPokeDnDDiagnosticState = 5;
        return TRUE;
    }
    id = d20_current(&sBattle);
    if (id == sUnits.human || id == sUnits.pokemon) {
        MoveSelected(newKeys);
        if (newKeys & A_BUTTON) {
            if (id == sUnits.human) (void)SpawnPikachu();
            else (void)d20_attack(&sBattle,id,sUnits.enemy,THUNDERBOLT);
        }
        if ((newKeys & L_BUTTON) && id == sUnits.human)
            (void)d20_attack(&sBattle,id,sUnits.enemy,TACKLE);
        if ((newKeys & R_BUTTON) && id == sUnits.pokemon)
            (void)d20_attack(&sBattle,id,sUnits.enemy,QUICK_ATTACK);
        if ((newKeys & B_BUTTON) && sBattle.outcome == FIGHTING) {
            if (d20_next(&sBattle))
                gPokeDnDDiagnosticState = 3;
        }
    }
    if (sBattle.outcome != FIGHTING) {
        CleanupCombat(FALSE);
        gPokeDnDDiagnosticState = 5;
    }
    else
        RunEnemyPhases();
    return TRUE; /* Suppress normal field movement and normal Pokémon battles. */
}
