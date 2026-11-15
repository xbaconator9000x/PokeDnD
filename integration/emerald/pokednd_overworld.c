/*
 * PokeDnD tactical overworld hook for pinned pokeemerald-expansion.
 * Original homebrew integration code. No ROM bytes or new art assets.
 *
 * L+R+START on the field triggers a one-human/one-Pikachu/one-Rocket encounter.
 * In combat the human and Pokemon share one initiative. A human deploys with
 * A, commands via L=Action or R=Bonus Action, or attacks via START.
 * A commanded Pokemon uses A=Thunderbolt or R=Quick Attack. B selects human
 * again, then ends the trainer turn. Uncommanded Pokemon Dodges automatically.
 * SELECT cancels without changing the map or save.
 *
 * This is a debug encounter, not a replacement for normal Pokemon battles.
 */
#include "global.h"
#include "d20.h"
#include "d20_field.h"
#include "pokednd_hud.h"
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
/* Explicit optional debug variants: hold UP or DOWN with L+R+START.
 * These create low-HP *starting positions*, not scripted wins/losses.
 * Damage, accuracy and battle outcome still run through the D20 engine. */
#define D20_SCENARIO_STANDARD 0
#define D20_SCENARIO_VICTORY 1
#define D20_SCENARIO_DEFEAT 2

/* Exported native probe: 0=idle, 1=started, 2=deployed, 3=turn,
 * 4=cancelled, 5=completed. Never interpret screenshots as this state. */
EWRAM_DATA volatile u32 gPokeDnDDiagnosticState;
/* Sticky milestones: 0=start, 1=deploy, 2=turn, 3=cancel, 4=finish,
 * 5=trainer-command, 6=Pokemon attack, 7=uncommanded Dodge. Unlike the last-state register, intermediate
 * transitions remain inspectable after the replay has moved on. */
EWRAM_DATA volatile u32 gPokeDnDMilestones;
/* Nonzero rejection codes make a vanilla-only replay actionable:
 * 1 field controls locked, 2 projection/spawn, 3 world coordinate,
 * 4 Rocket ID collision, 5 Pikachu ID collision, 6 sprite allocation,
 * 7 initiative start. A successful activation clears this value. */
EWRAM_DATA volatile u32 gPokeDnDStartFailure;
/* Incremented only when the native field input hook actually sees the chord.
 * A zero value distinguishes input/hook failures from encounter rejection. */
EWRAM_DATA volatile u32 gPokeDnDTriggerCount;
/* Increment only after native Emerald accepts a new D-pad input following
 * D20 cancellation AND the player's true map tile subsequently changes.
 * A frame difference or key injection alone must not pass this check. */
EWRAM_DATA volatile u32 gPokeDnDPostCancelMoves;
/* Actual result is written only by the core's D20Result transition.
 * Acknowledgements occur only after a distinct confirmation input. */
EWRAM_DATA volatile u32 gPokeDnDLastOutcome;
EWRAM_DATA volatile u32 gPokeDnDLastHumanHp;
EWRAM_DATA volatile u32 gPokeDnDLastEnemyHp;
EWRAM_DATA volatile u32 gPokeDnDOutcomeAcks;
static EWRAM_DATA bool8 sResultShown;
static EWRAM_DATA bool8 sWatchPostCancelMove;
static EWRAM_DATA bool8 sSawPostCancelDpad;
static EWRAM_DATA u8 sPostCancelMapGroup;
static EWRAM_DATA u8 sPostCancelMapNum;
static EWRAM_DATA s16 sPostCancelX;
static EWRAM_DATA s16 sPostCancelY;
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
    /* Combat may end after a warp has reset the BG0 window heap. */
    if (sMapGroup == gSaveBlock1Ptr->location.mapGroup &&
        sMapNum == gSaveBlock1Ptr->location.mapNum)
        PokeDnD_HudClose();
    else
        PokeDnD_HudAbandon();
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
        gPokeDnDMilestones |= 2u;
        PokeDnD_HudMessage(COMPOUND_STRING("PIKACHU DEPLOYED"));
        return true;
    }
    return false;
}
static bool StartCombat(u8 scenario)
{
    struct MapPosition player;
    int wx, wy;
    /* Avoid scripts, link rooms, active movement and accidental re-entry. */
    if (sActive)
        return false;
    sWatchPostCancelMove = FALSE;
    sSawPostCancelDpad = FALSE;
    gPokeDnDPostCancelMoves = 0;
    gPokeDnDDiagnosticState = 0;
    gPokeDnDMilestones = 0;
    gPokeDnDStartFailure = 0;
    gPokeDnDLastOutcome = FIGHTING;
    gPokeDnDLastHumanHp = 0;
    gPokeDnDLastEnemyHp = 0;
    sResultShown = FALSE;
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
    if (scenario == D20_SCENARIO_VICTORY) {
        /* One real legal attack must still land to win. Natural 1 misses. */
        sBattle.units[sUnits.enemy].hp = 1;
        sBattle.units[sUnits.enemy].max_hp = 1;
        sBattle.units[sUnits.enemy].ac = 2;
    } else if (scenario == D20_SCENARIO_DEFEAT) {
        /* Real enemy AI must reach the vulnerable trainer and hit. */
        sBattle.units[sUnits.human].hp = 1;
        sBattle.units[sUnits.human].max_hp = 1;
        sBattle.units[sUnits.human].ac = 2;
        sBattle.units[sUnits.enemy].stats[STR] = 18;
    }
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
    gPokeDnDMilestones |= 1u;
    FreezeSurroundingActors();
    if (!PokeDnD_HudOpen(&sBattle, sUnits.human, sUnits.pokemon,
                        sUnits.enemy)) {
        CleanupCombat(FALSE);
        gPokeDnDDiagnosticState = 0;
        gPokeDnDMilestones = 0;
        gPokeDnDStartFailure = 8; /* BG0 HUD allocation unavailable. */
        return false;
    }
    return true;
}
static void DisplayBattleResult(void)
{
    if (sResultShown || sBattle.outcome == FIGHTING)
        return;
    sResultShown = TRUE;
    /* Neither game-over case is faked by this adapter. */
    gPokeDnDLastOutcome = sBattle.outcome;
    gPokeDnDLastHumanHp = sBattle.units[sUnits.human].hp;
    gPokeDnDLastEnemyHp = sBattle.units[sUnits.enemy].hp;
    PokeDnD_HudMessage(sBattle.outcome == ALLIES_WIN
                           ? COMPOUND_STRING("VICTORY - A CONTINUE")
                           : COMPOUND_STRING("DEFEAT - A CONTINUE"));
    PokeDnD_HudRedraw(&sBattle);
}
static void ArmFieldReturnProbe(void)
{
    struct MapPosition position;
    GetPlayerPosition(&position);
    sPostCancelX = position.x;
    sPostCancelY = position.y;
    sPostCancelMapGroup = gSaveBlock1Ptr->location.mapGroup;
    sPostCancelMapNum = gSaveBlock1Ptr->location.mapNum;
    sSawPostCancelDpad = FALSE;
    sWatchPostCancelMove = TRUE;
    gPokeDnDPostCancelMoves = 0;
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
                                  enemy->x + stepX[best], enemy->y + stepY[best])) {
            MoveVisual(sUnits.enemy);
            PokeDnD_HudMessage(COMPOUND_STRING("ROCKET ADVANCES"));
        }
    }
    if (DistanceTo(sUnits.enemy,target) == 1) {
        D20Attack result = d20_attack(&sBattle,sUnits.enemy,target,TACKLE);
        if (result.legal)
            PokeDnD_HudAttack(COMPOUND_STRING("ROCKET TACKLE"), result);
    }
    if (sBattle.outcome == FIGHTING)
        (void)d20_next(&sBattle);
}
static void RunEnemyPhases(void)
{
    bool8 tookTurn = FALSE;
    for (int i = 0; i < 6 && sBattle.outcome == FIGHTING &&
                        d20_current(&sBattle) == sUnits.enemy; i++) {
        tookTurn = TRUE;
        EnemyPhase();
    }
    if (tookTurn)
        PokeDnD_HudRedraw(&sBattle);
}
static void MoveSelected(u16 newKeys)
{
    int id = d20_actor(&sBattle), x, y;
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
        /* Observe the *real* engine's player tile after normal field input
         * has been restored. Require a new D-pad press first; changing map,
         * stepping during rollback or an idle camera animation cannot pass. */
        if (sWatchPostCancelMove) {
            if (sPostCancelMapGroup != gSaveBlock1Ptr->location.mapGroup ||
                sPostCancelMapNum != gSaveBlock1Ptr->location.mapNum) {
                sWatchPostCancelMove = FALSE;
            } else if (!ArePlayerFieldControlsLocked()) {
                struct MapPosition position;
                if (newKeys & (DPAD_UP | DPAD_DOWN | DPAD_LEFT | DPAD_RIGHT))
                    sSawPostCancelDpad = TRUE;
                GetPlayerPosition(&position);
                if (sSawPostCancelDpad &&
                    (position.x != sPostCancelX || position.y != sPostCancelY)) {
                    gPokeDnDPostCancelMoves++;
                    sWatchPostCancelMove = FALSE;
                }
            }
        }
        if ((newKeys & START_BUTTON) && (heldKeys & D20_DEBUG_CHORD) == D20_DEBUG_CHORD) {
            u8 scenario = D20_SCENARIO_STANDARD;
            if (heldKeys & DPAD_UP)
                scenario = D20_SCENARIO_VICTORY;
            else if (heldKeys & DPAD_DOWN)
                scenario = D20_SCENARIO_DEFEAT;
            gPokeDnDTriggerCount++;
            return StartCombat(scenario);
        }
        return FALSE;
    }
    /* Always yield to Emerald if the map changed unexpectedly. */
    if (sMapGroup != gSaveBlock1Ptr->location.mapGroup ||
        sMapNum != gSaveBlock1Ptr->location.mapNum) {
        CleanupCombat(FALSE);
        return FALSE;
    }
    /* A result remains on screen until a separate A/START/B press.
     * A KO caused by an input on this frame cannot auto-dismiss itself. */
    if (sResultShown) {
        if (newKeys & (A_BUTTON | B_BUTTON | START_BUTTON)) {
            CleanupCombat(TRUE);
            ArmFieldReturnProbe();
            gPokeDnDOutcomeAcks++;
            gPokeDnDDiagnosticState = 5;
            gPokeDnDMilestones |= 16u;
        }
        return TRUE;
    }
    if (sBattle.outcome != FIGHTING) {
        DisplayBattleResult();
        return TRUE;
    }
    if (newKeys & SELECT_BUTTON) {
        CleanupCombat(TRUE);
        ArmFieldReturnProbe();
        gPokeDnDDiagnosticState = 4;
        gPokeDnDMilestones |= 8u;
        return TRUE;
    }
    RunEnemyPhases();
    if (sBattle.outcome != FIGHTING) {
        DisplayBattleResult();
        return TRUE;
    }
    id = d20_actor(&sBattle);
    if (d20_current(&sBattle) == sUnits.human &&
        (id == sUnits.human || id == sUnits.pokemon)) {
        MoveSelected(newKeys);
        if (id == sUnits.human) {
            /* A is deployment. Both command types pay the trainer budget. */
            if ((newKeys & A_BUTTON) && !sBattle.units[sUnits.pokemon].deployed)
                (void)SpawnPikachu();
            if ((newKeys & L_BUTTON) &&
                d20_command(&sBattle,sUnits.human,sUnits.pokemon,false)) {
                gPokeDnDMilestones |= 32u;
                PokeDnD_HudMessage(COMPOUND_STRING("PIKA ACTION COMMAND"));
            }
            if ((newKeys & R_BUTTON) &&
                d20_command(&sBattle,sUnits.human,sUnits.pokemon,true)) {
                gPokeDnDMilestones |= 32u;
                PokeDnD_HudMessage(COMPOUND_STRING("PIKA BONUS COMMAND"));
            }
            if (newKeys & START_BUTTON) {
                D20Attack result = d20_attack(&sBattle,sUnits.human,sUnits.enemy,TACKLE);
                PokeDnD_HudAttack(COMPOUND_STRING("HUMAN TACKLE"), result);
            }
        } else {
            D20Attack result = {0};
            if (newKeys & A_BUTTON)
                result = d20_attack(&sBattle,id,sUnits.enemy,THUNDERBOLT);
            else if (newKeys & R_BUTTON)
                result = d20_attack(&sBattle,id,sUnits.enemy,QUICK_ATTACK);
            if (newKeys & (A_BUTTON | R_BUTTON))
                PokeDnD_HudAttack((newKeys & A_BUTTON)
                                    ? COMPOUND_STRING("PIKA THUNDERBOLT")
                                    : COMPOUND_STRING("PIKA QUICK ATTACK"), result);
            if (result.legal)
                gPokeDnDMilestones |= 64u;
        }
        if ((newKeys & B_BUTTON) && sBattle.outcome == FIGHTING) {
            if (id == sUnits.pokemon) {
                if (d20_select(&sBattle,sUnits.human))
                    PokeDnD_HudMessage(COMPOUND_STRING("HUMAN SELECTED"));
            } else if (d20_next(&sBattle)) {
                gPokeDnDDiagnosticState = 3;
                gPokeDnDMilestones |= 4u;
                PokeDnD_HudMessage(COMPOUND_STRING("INITIATIVE ADVANCES"));
                if (sBattle.units[sUnits.pokemon].deployed &&
                    sBattle.units[sUnits.pokemon].dodging)
                    gPokeDnDMilestones |= 128u;
            }
        }
    }
    if (sBattle.outcome == FIGHTING)
        RunEnemyPhases();
    if (sBattle.outcome != FIGHTING)
        DisplayBattleResult();
    else if (newKeys)
        PokeDnD_HudRedraw(&sBattle);
    return TRUE; /* Suppress normal field movement and normal Pokémon battles. */
}
