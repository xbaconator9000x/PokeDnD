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
#include "sprite.h"
#include "script.h"
#include "constants/event_objects.h"
#include "constants/event_object_movement.h"

#ifdef POKEDND_NATIVE_REPLAY_ROCKET
/* Read-only stack sampling: linker symbols are emitted by instrument_stack.
 * This is the deepest SP observed at the field callback, NOT a whole-program
 * high-water mark. Never paint a live stack or claim unsampled frames. */
extern u8 __pokednd_stack_low[];
extern u8 __pokednd_stack_top[];
/* IRQ capacity is linker-grounded, but IRQ usage remains unmeasured.
 * Never switch CPU modes or paint a live IRQ stack from field code. */
extern u8 __pokednd_irq_low[];
extern u8 __pokednd_irq_top[];
EWRAM_DATA volatile u32 gPokeDnDIrqStackCapacity;
EWRAM_DATA volatile u32 gPokeDnDIrqStackBoundsInvalid;
static void PokeDnD_CheckIrqStackBounds(void)
{
    u32 low = (u32)__pokednd_irq_low;
    u32 top = (u32)__pokednd_irq_top;
    /* A changed pinned layout must invalidate native resource evidence. */
    if (low >= top || (low & 3u) || (top & 3u) ||
        top - low != 352u || low != (u32)__pokednd_stack_top)
    {
        gPokeDnDIrqStackBoundsInvalid = 1u;
        gPokeDnDIrqStackCapacity = 0u;
        return;
    }
    if (gPokeDnDIrqStackBoundsInvalid)
        return;
    if (gPokeDnDIrqStackCapacity != 0u &&
        gPokeDnDIrqStackCapacity != top - low)
    {
        gPokeDnDIrqStackBoundsInvalid = 1u;
        gPokeDnDIrqStackCapacity = 0u;
        return;
    }
    gPokeDnDIrqStackCapacity = top - low;
}

EWRAM_DATA volatile u32 gPokeDnDStackSamplePeak;
EWRAM_DATA volatile u32 gPokeDnDStackSampleCount;
EWRAM_DATA volatile u32 gPokeDnDStackSampleInvalid;
/* Minimum unused stack space at sampled field callbacks. This is not an IRQ
 * measurement or an unsampled whole-program high-water mark. */
EWRAM_DATA volatile u32 gPokeDnDStackSampleMinFree;
static void PokeDnD_SampleSystemStack(void)
{
    PokeDnD_CheckIrqStackBounds();
    u32 sp;
    u32 low = (u32)__pokednd_stack_low;
    u32 top = (u32)__pokednd_stack_top;
    u32 depth;
    __asm__ volatile ("mov %0, sp" : "=r" (sp));
    /* The ARM system stack is word-aligned. Reject impossible bounds,
     * misaligned samples, poisoned counters and inconsistent prior peaks.
     * Never repair invalid evidence by clamping it to a plausible value. */
    if (low >= top || (low & 3u) || (top & 3u) ||
        sp < low || sp > top || (sp & 3u) ||
        gPokeDnDStackSampleCount == 0xFFFFFFFFu ||
        /* Reserve 256 bytes for transient frames below the observed SP.
         * A sample crossing this guard poisons the replay immediately;
         * host-side validation must not be the first line of defence. */
        top - low < 1024u ||
        sp - low < 256u ||
        gPokeDnDStackSamplePeak > top - low - 256u ||
        (gPokeDnDStackSampleCount == 0u &&
         (gPokeDnDStackSamplePeak != 0u || gPokeDnDStackSampleMinFree != 0u)) ||
        /* Reject corrupted prior extrema BEFORE updating either value.
         * Otherwise a later deeper sample could accidentally conceal a
         * damaged minimum-free counter and launder invalid replay data. */
        (gPokeDnDStackSampleCount != 0u &&
         (gPokeDnDStackSampleMinFree < 256u ||
          gPokeDnDStackSampleMinFree > top - low ||
          gPokeDnDStackSampleMinFree != top - low - gPokeDnDStackSamplePeak)))
    {
        gPokeDnDStackSampleInvalid = 1;
        return;
    }
    if (gPokeDnDStackSampleInvalid)
        return;
    depth = (u32)(top - sp);
    if (gPokeDnDStackSampleCount == 0u ||
        sp - low < gPokeDnDStackSampleMinFree)
        gPokeDnDStackSampleMinFree = sp - low;
    if (depth > gPokeDnDStackSamplePeak)
        gPokeDnDStackSamplePeak = depth;
    /* The two sampled extrema must describe the same downward-growing stack. */
    if (gPokeDnDStackSampleMinFree != top - low - gPokeDnDStackSamplePeak)
    {
        gPokeDnDStackSampleInvalid = 1;
        return;
    }
    gPokeDnDStackSampleCount++;
}

#endif /* POKEDND_NATIVE_REPLAY_ROCKET */

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
/* Distinguish genuine facing-A NPC encounters from the debug chord.
 * Count accepted encounters only, not rejected inputs or nearby actors. */
EWRAM_DATA volatile u32 gPokeDnDNaturalEncounterCount;
EWRAM_DATA volatile u32 gPokeDnDLastNaturalLocalId;
/* Native lifecycle evidence: original Rocket survives cleanup on its map,
 * retaining its local ID, graphics and original tile. 1=preserved,
 * 2=identity lost, 3=map changed (not safe to inspect recycled slots). */
EWRAM_DATA volatile u32 gPokeDnDNaturalCleanupStatus;
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
/* Native display-only hit reaction evidence; never substitute for damage. */
EWRAM_DATA volatile u32 gPokeDnDImpactStarts;
EWRAM_DATA volatile u32 gPokeDnDImpactFrames;
/* Native evidence: count successful Dash actions and resulting tile budget. */
EWRAM_DATA volatile u32 gPokeDnDDashCount;
EWRAM_DATA volatile u32 gPokeDnDLastDashMovement;
static EWRAM_DATA u8 sImpactObjectId;
static EWRAM_DATA u8 sImpactSpriteId;
static EWRAM_DATA u8 sImpactLocalId;
static EWRAM_DATA u8 sImpactMapGroup;
static EWRAM_DATA u8 sImpactMapNum;
static EWRAM_DATA u8 sImpactRemaining;
static EWRAM_DATA bool8 sImpactCritical;
static EWRAM_DATA s16 sImpactBaseX2;
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
static EWRAM_DATA bool8 sRocketIsExisting;
static EWRAM_DATA u8 sRocketOriginalLocalId;
static EWRAM_DATA s16 sRocketOriginalX;
static EWRAM_DATA s16 sRocketOriginalY;
static EWRAM_DATA u8 sPikachuObjectId;
static EWRAM_DATA u8 sActive;
static EWRAM_DATA u8 sMapGroup;
static EWRAM_DATA u8 sMapNum;
static EWRAM_DATA u8 sElevation;
static EWRAM_DATA s16 sEntryX;
static EWRAM_DATA s16 sEntryY;
static EWRAM_DATA bool8 sFrozenByD20[OBJECT_EVENTS_COUNT];
static EWRAM_DATA u8 sFrozenLocalId[OBJECT_EVENTS_COUNT];

/* A lightweight physical shake of the *existing* Emerald actor sprite.
 * Verify both the object-event identity and its sprite binding every frame,
 * since map warps and unrelated scripts can recycle either slot. */
static struct Sprite *GetImpactSprite(void)
{
    struct ObjectEvent *obj;
    if (!sImpactRemaining || sImpactObjectId >= OBJECT_EVENTS_COUNT)
        return NULL;
    obj = &gObjectEvents[sImpactObjectId];
    if (!obj->active || obj->localId != sImpactLocalId ||
        obj->mapGroup != sImpactMapGroup ||
        obj->mapNum != sImpactMapNum ||
        obj->spriteId != sImpactSpriteId ||
        sImpactSpriteId >= MAX_SPRITES || !gSprites[sImpactSpriteId].inUse)
        return NULL;
    return &gSprites[sImpactSpriteId];
}
static void EndImpact(void)
{
    struct Sprite *sprite = GetImpactSprite();
    if (sprite)
        sprite->x2 = sImpactBaseX2;
    sImpactRemaining = 0;
}
static void TickImpact(void)
{
    /* 32 native frames, 8-frame oscillation, with no extra assets or DMA. */
    static const s8 sOffsets[] = { 0, 1, 3, 1, 0, -1, -3, -1 };
    struct Sprite *sprite = GetImpactSprite();
    s16 offset;
    if (!sImpactRemaining)
        return;
    if (!sprite) {
        sImpactRemaining = 0;
        return;
    }
    offset = sOffsets[(32 - sImpactRemaining) % ARRAY_COUNT(sOffsets)];
    if (sImpactCritical)
        offset *= 2;
    sprite->x2 = sImpactBaseX2 + offset;
    if (offset)
        gPokeDnDImpactFrames++;
    if (--sImpactRemaining == 0)
        sprite->x2 = sImpactBaseX2;
}
static void StartImpact(int target, D20Attack attack)
{
#ifdef POKEDND_NATIVE_REPLAY_ROCKET
    /* Observe the live system SP at this combat phase; never write stack memory. */
    PokeDnD_SampleSystemStack();
#endif
    struct ObjectEvent *obj;
    u8 objectId;
    if (!attack.legal || !attack.hit || attack.damage <= 0)
        return;
    EndImpact();
    if (target == sUnits.human)
        objectId = gPlayerAvatar.objectEventId;
    else if (target == sUnits.pokemon)
        objectId = sPikachuObjectId;
    else if (target == sUnits.enemy)
        objectId = sRocketObjectId;
    else
        return;
    if (objectId >= OBJECT_EVENTS_COUNT)
        return;
    obj = &gObjectEvents[objectId];
    if (!obj->active || obj->spriteId >= MAX_SPRITES ||
        !gSprites[obj->spriteId].inUse ||
        obj->mapGroup != sMapGroup || obj->mapNum != sMapNum)
        return;
    sImpactObjectId = objectId;
    sImpactSpriteId = obj->spriteId;
    sImpactLocalId = obj->localId;
    sImpactMapGroup = obj->mapGroup;
    sImpactMapNum = obj->mapNum;
    sImpactBaseX2 = gSprites[obj->spriteId].x2;
    sImpactCritical = attack.crit;
    sImpactRemaining = 32;
    gPokeDnDImpactStarts++;
}
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
#ifdef POKEDND_NATIVE_REPLAY_ROCKET
    /* Capture live SP at this nested gameplay boundary; read-only sampling. */
    PokeDnD_SampleSystemStack();
#endif
    EndImpact();
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
    /* A natural encounter borrows the original NPC. Restore its tile and
     * preserve the actor, scripts and local ID; only debug sprites are ours. */
    if (sRocketIsExisting && sActive &&
        sMapGroup == gSaveBlock1Ptr->location.mapGroup &&
        sMapNum == gSaveBlock1Ptr->location.mapNum &&
        sRocketObjectId < OBJECT_EVENTS_COUNT &&
        gObjectEvents[sRocketObjectId].active &&
        gObjectEvents[sRocketObjectId].graphicsId == OBJ_EVENT_GFX_ROCKET_M &&
        gObjectEvents[sRocketObjectId].localId == sRocketOriginalLocalId &&
        gObjectEvents[sRocketObjectId].mapGroup == sMapGroup &&
        gObjectEvents[sRocketObjectId].mapNum == sMapNum)
        MoveObjectEventToMapCoords(&gObjectEvents[sRocketObjectId],
                                   sRocketOriginalX, sRocketOriginalY);
    /* Sample after restoration: the live probe must prove that the original
     * actor is still present on its starting tile, not merely that its slot
     * was occupied before cleanup. */
    if (sRocketIsExisting && sActive) {
        if (sMapGroup != gSaveBlock1Ptr->location.mapGroup ||
            sMapNum != gSaveBlock1Ptr->location.mapNum)
            gPokeDnDNaturalCleanupStatus = 3;
        else if (sRocketObjectId >= OBJECT_EVENTS_COUNT ||
                 !gObjectEvents[sRocketObjectId].active ||
                 gObjectEvents[sRocketObjectId].graphicsId != OBJ_EVENT_GFX_ROCKET_M ||
                 gObjectEvents[sRocketObjectId].localId != sRocketOriginalLocalId ||
                 gObjectEvents[sRocketObjectId].mapGroup != sMapGroup ||
                 gObjectEvents[sRocketObjectId].mapNum != sMapNum ||
                 gObjectEvents[sRocketObjectId].currentCoords.x != sRocketOriginalX ||
                 gObjectEvents[sRocketObjectId].currentCoords.y != sRocketOriginalY)
            gPokeDnDNaturalCleanupStatus = 2;
        else
            gPokeDnDNaturalCleanupStatus = 1;
    }
    /* Object-event slots can be recycled after an unexpected map warp.
     * Never destroy a real map NPC merely because it reused our old slot. */
    if (!sRocketIsExisting && sRocketObjectId < OBJECT_EVENTS_COUNT &&
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
    sRocketIsExisting = FALSE;
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
#ifdef POKEDND_NATIVE_REPLAY_ROCKET
    /* Capture live SP at this nested gameplay boundary; read-only sampling. */
    PokeDnD_SampleSystemStack();
#endif
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
static bool StartCombat(u8 scenario, u8 existingRocketId)
{
#ifdef POKEDND_NATIVE_REPLAY_ROCKET
    /* Capture live SP at this nested gameplay boundary; read-only sampling. */
    PokeDnD_SampleSystemStack();
#endif
    struct MapPosition player;
    int wx, wy;
    /* Avoid scripts, link rooms, active movement and accidental re-entry. */
    if (sActive)
        return false;
    /* A natural encounter must still refer to the same live Rocket on the
     * player's map. Never read a stale/recycled object slot. */
    if (existingRocketId < OBJECT_EVENTS_COUNT) {
        const struct ObjectEvent *rocket = &gObjectEvents[existingRocketId];
        if (!rocket->active || rocket->isPlayer || rocket->invisible ||
            rocket->graphicsId != OBJ_EVENT_GFX_ROCKET_M ||
            rocket->mapGroup != gSaveBlock1Ptr->location.mapGroup ||
            rocket->mapNum != gSaveBlock1Ptr->location.mapNum)
            return false;
    }
    sWatchPostCancelMove = FALSE;
    sSawPostCancelDpad = FALSE;
    gPokeDnDPostCancelMoves = 0;
    gPokeDnDDiagnosticState = 0;
    gPokeDnDMilestones = 0;
    gPokeDnDStartFailure = 0;
    gPokeDnDLastOutcome = FIGHTING;
    gPokeDnDImpactStarts = 0;
    gPokeDnDImpactFrames = 0;
    gPokeDnDDashCount = 0;
    gPokeDnDLastDashMovement = 0;
    sImpactRemaining = 0;
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
        !(existingRocketId < OBJECT_EVENTS_COUNT
          ? d20_field_spawn_existing(&sBattle, &sProjection, &sUnits,
              gObjectEvents[existingRocketId].currentCoords.x,
              gObjectEvents[existingRocketId].currentCoords.y)
          : d20_field_spawn_demo(&sBattle,&sProjection,&sUnits))) {
        gPokeDnDStartFailure = 2;
        return false;
    }
    if (!d20_field_to_world(&sProjection,sBattle.units[sUnits.enemy].x,
                           sBattle.units[sUnits.enemy].y,&wx,&wy)) {
        gPokeDnDStartFailure = 3;
        return false;
    }
    /* Fail closed if the world has a conflicting reserved local ID. */
    if (existingRocketId == OBJECT_EVENTS_COUNT &&
        !TryGetObjectEventIdByLocalIdAndMap(D20_ROCKET_LOCAL_ID,
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
    sRocketIsExisting = existingRocketId < OBJECT_EVENTS_COUNT;
    if (sRocketIsExisting)
        gPokeDnDNaturalCleanupStatus = 0;
    if (sRocketIsExisting) {
        sRocketObjectId = existingRocketId;
        sRocketOriginalLocalId = gObjectEvents[existingRocketId].localId;
        sRocketOriginalX = gObjectEvents[existingRocketId].currentCoords.x;
        sRocketOriginalY = gObjectEvents[existingRocketId].currentCoords.y;
    } else {
        sRocketObjectId = SpawnSpecialObjectEventParameterized(
            OBJ_EVENT_GFX_ROCKET_M, MOVEMENT_TYPE_NONE,
            D20_ROCKET_LOCAL_ID, wx, wy, sElevation);
    }
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
        if (!sRocketIsExisting && sRocketObjectId < OBJECT_EVENTS_COUNT &&
            gObjectEvents[sRocketObjectId].active &&
            gObjectEvents[sRocketObjectId].localId == D20_ROCKET_LOCAL_ID &&
            gObjectEvents[sRocketObjectId].mapGroup == sMapGroup &&
            gObjectEvents[sRocketObjectId].mapNum == sMapNum)
            RemoveObjectEvent(&gObjectEvents[sRocketObjectId]);
        sRocketObjectId = OBJECT_EVENTS_COUNT;
        sRocketIsExisting = FALSE;
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
#ifdef POKEDND_NATIVE_REPLAY_ROCKET
    /* Observe the live system SP at this combat phase; never write stack memory. */
    PokeDnD_SampleSystemStack();
#endif
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
        if (result.legal) {
            PokeDnD_HudAttack(COMPOUND_STRING("ROCKET TACKLE"), result);
            StartImpact(target, result);
        }
    }
    if (sBattle.outcome == FIGHTING)
        (void)d20_next(&sBattle);
}
static void RunEnemyPhases(void)
{
#ifdef POKEDND_NATIVE_REPLAY_ROCKET
    /* Capture live SP at this nested gameplay boundary; read-only sampling. */
    PokeDnD_SampleSystemStack();
#endif
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
#ifdef POKEDND_NATIVE_REPLAY_ROCKET
    /* Observe the live system SP at this combat phase; never write stack memory. */
    PokeDnD_SampleSystemStack();
#endif
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
/* Native field interaction prototype: pressing A next to an existing
 * Rocket actor opens the tactical encounter without the debug chord.
 * Only the original map actor is inspected; spawned debug actors are excluded.
 * A failed admission yields to the normal Emerald interaction. */
#ifdef POKEDND_NATIVE_REPLAY_ROCKET
/* CI-only: R+SELECT creates a native fixture without START/menu ambiguity.
 * L+R+SELECT+START is a GBA soft-reset chord and must never be sent by CI.
 * Create the object on the tile the player faces.
 * The fixture uses upstream Emerald graphics and normal A interaction; it
 * is never compiled into the normal integration or committed as ROM data. */
/* CI-only diagnostics: 0=not attempted, 1=controls locked, 2=invalid facing,
 * 3=blocked tile, 4=occupied tile, 5=allocation/identity conflict, 6=verified spawn, 7=wrong placement.
 * Capture the genuine control lock both at fixture admission and at the
 * ordinary facing-A interaction. No bypass is allowed: a locked field
 * cannot be counted as a successful native encounter. */
EWRAM_DATA volatile u32 gPokeDnDReplayFixtureStatus;
EWRAM_DATA volatile u32 gPokeDnDReplayLockObservations;
EWRAM_DATA volatile u32 gPokeDnDReplayNaturalLockObservations;
EWRAM_DATA volatile u32 gPokeDnDReplayFixtureAttemptCount;
static bool8 SpawnReplayRocket(u16 newKeys, u16 heldKeys)
{
    struct MapPosition player;
    s16 x, y;
    u8 facing;
    if (!(newKeys & SELECT_BUTTON) || !(heldKeys & R_BUTTON) ||
        (heldKeys & (L_BUTTON | START_BUTTON)))
        return FALSE;
    gPokeDnDReplayFixtureAttemptCount++;
    if (ArePlayerFieldControlsLocked()) {
        gPokeDnDReplayLockObservations++;
        gPokeDnDReplayFixtureStatus = 1;
        return TRUE;
    }
    GetPlayerPosition(&player);
    x = player.x;
    y = player.y;
    facing = GetPlayerFacingDirection();
    if (facing == DIR_NORTH) y--;
    else if (facing == DIR_SOUTH) y++;
    else if (facing == DIR_WEST) x--;
    else if (facing == DIR_EAST) x++;
    else {
        gPokeDnDReplayFixtureStatus = 2;
        return TRUE;
    }
    if (!AreCoordsInsidePlayerMap(x, y) || MapGridGetCollisionAt(x, y)) {
        gPokeDnDReplayFixtureStatus = 3;
        return TRUE;
    }
    for (int i = 0; i < OBJECT_EVENTS_COUNT; i++) {
        const struct ObjectEvent *obj = &gObjectEvents[i];
        if (obj->active && obj->mapGroup == gSaveBlock1Ptr->location.mapGroup &&
            obj->mapNum == gSaveBlock1Ptr->location.mapNum &&
            obj->currentCoords.x == x && obj->currentCoords.y == y) {
            gPokeDnDReplayFixtureStatus = 4;
            return TRUE;
        }
    }
    /* Never allocate a second actor with the same map-local identity.
     * A failed or repeated fixture request must not corrupt the object table. */
    u8 fixtureId;
    if (!TryGetObjectEventIdByLocalIdAndMap(230,
            gSaveBlock1Ptr->location.mapNum,
            gSaveBlock1Ptr->location.mapGroup, &fixtureId)) {
        gPokeDnDReplayFixtureStatus = 5;
        return TRUE;
    }
    fixtureId = SpawnSpecialObjectEventParameterized(OBJ_EVENT_GFX_ROCKET_M,
            MOVEMENT_TYPE_NONE, 230, x, y, player.elevation);
    if (fixtureId >= OBJECT_EVENTS_COUNT) {
        gPokeDnDReplayFixtureStatus = 5;
        return TRUE;
    }
    /* Allocation alone is not acceptance: verify the actual native actor
     * occupies the facing tile and belongs to this map and elevation. */
    const struct ObjectEvent *fixture = &gObjectEvents[fixtureId];
    if (!fixture->active || fixture->localId != 230 ||
        fixture->graphicsId != OBJ_EVENT_GFX_ROCKET_M ||
        fixture->mapNum != gSaveBlock1Ptr->location.mapNum ||
        fixture->mapGroup != gSaveBlock1Ptr->location.mapGroup ||
        fixture->currentElevation != player.elevation ||
        fixture->currentCoords.x != x || fixture->currentCoords.y != y) {
        RemoveObjectEvent(&gObjectEvents[fixtureId]);
        gPokeDnDReplayFixtureStatus = 7;
        return TRUE;
    }
    gPokeDnDReplayFixtureStatus = 6;
    return TRUE;
}
#endif
static bool8 TryRocketFieldEncounter(u16 newKeys)
{
    struct MapPosition player;
    s16 targetX, targetY;
    u8 facing;
    if (!(newKeys & A_BUTTON))
        return FALSE;
    if (ArePlayerFieldControlsLocked()) {
#ifdef POKEDND_NATIVE_REPLAY_ROCKET
        gPokeDnDReplayNaturalLockObservations++;
#endif
        return FALSE;
    }
    GetPlayerPosition(&player);
    targetX = player.x;
    targetY = player.y;
    facing = GetPlayerFacingDirection();
    if (facing == DIR_NORTH) targetY--;
    else if (facing == DIR_SOUTH) targetY++;
    else if (facing == DIR_WEST) targetX--;
    else if (facing == DIR_EAST) targetX++;
    else return FALSE;
    for (int i = 0; i < OBJECT_EVENTS_COUNT; i++) {
        const struct ObjectEvent *obj = &gObjectEvents[i];
        if (!obj->active || obj->isPlayer ||
            obj->graphicsId != OBJ_EVENT_GFX_ROCKET_M ||
            obj->localId == D20_ROCKET_LOCAL_ID ||
            obj->mapGroup != gSaveBlock1Ptr->location.mapGroup ||
            obj->mapNum != gSaveBlock1Ptr->location.mapNum ||
            /* Never hijack a scripted/frozen actor or an NPC on another
             * elevation. Emerald must retain its ordinary interaction. */
            obj->frozen || obj->invisible ||
            obj->currentElevation != player.elevation ||
            /* Moving actors may leave this tile before the engine processes
             * A. Let Emerald handle them rather than starting a fight with
             * an actor already walking away. */
            obj->heldMovementActive || obj->singleMovementActive ||
            obj->currentCoords.x != targetX ||
            obj->currentCoords.y != targetY)
            continue;
        /* StartCombat may allocate sprites and freeze actors. Capture the
         * source NPC identity before those allocations can reuse slots. */
        const u8 localId = obj->localId;
        /* Replay-only L+A / R+A select terminal test scenarios without
         * sending directional movement to Emerald's field controller.
         * The production encounter always uses standard statistics. */
        u8 scenario = D20_SCENARIO_STANDARD;
#ifdef POKEDND_NATIVE_REPLAY_ROCKET
        if ((gMain.heldKeys & (L_BUTTON | R_BUTTON)) == L_BUTTON)
            scenario = D20_SCENARIO_VICTORY;
        else if ((gMain.heldKeys & (L_BUTTON | R_BUTTON)) == R_BUTTON)
            scenario = D20_SCENARIO_DEFEAT;
#endif
        if (StartCombat(scenario, i)) {
            gPokeDnDTriggerCount++;
            gPokeDnDNaturalEncounterCount++;
            gPokeDnDLastNaturalLocalId = localId;
            return TRUE;
        }
        return FALSE;
    }
    return FALSE;
}
bool8 PokeDnD_HandleOverworldInput(u16 newKeys, u16 heldKeys)
{
    int id;
#ifdef POKEDND_NATIVE_REPLAY_ROCKET
    PokeDnD_SampleSystemStack();
#endif
    if (!sActive) {
#ifdef POKEDND_NATIVE_REPLAY_ROCKET
        if (SpawnReplayRocket(newKeys, heldKeys))
            return TRUE;
#endif
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
            /* A rejected debug encounter must not leak START to Emerald.\n             * Otherwise the same chord unexpectedly opens the field menu,\n             * obscuring the native admission error and consuming input. */
            (void)StartCombat(scenario, OBJECT_EVENTS_COUNT);
            return TRUE;
        }
        if (TryRocketFieldEncounter(newKeys))
            return TRUE;
        return FALSE;
    }
    /* Always yield to Emerald if the map changed unexpectedly. */
    if (sMapGroup != gSaveBlock1Ptr->location.mapGroup ||
        sMapNum != gSaveBlock1Ptr->location.mapNum) {
        CleanupCombat(FALSE);
        return FALSE;
    }
    /* Field callback runs every native frame, even with no new keypress. */
    TickImpact();
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
            /* L+START spends the trainer Action to Dash, doubling the
             * remaining tile budget without resetting already-used steps. */
            if ((newKeys & START_BUTTON) && (heldKeys & L_BUTTON)) {
                if (d20_dash(&sBattle, id)) {
                    gPokeDnDDashCount++;
                    gPokeDnDLastDashMovement = sBattle.units[id].movement;
                    PokeDnD_HudMessage(COMPOUND_STRING("DASH +SPEED TILES"));
                }
            } else {
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
                StartImpact(sUnits.enemy, result);
            }
            }
        } else {
            D20Attack result = {0};
            /* A commanded Pokemon spends its own Action to Dash, not the
             * trainer's already-paid command resource. */
            if ((newKeys & START_BUTTON) && (heldKeys & L_BUTTON)) {
                if (d20_dash(&sBattle, id)) {
                    gPokeDnDDashCount++;
                    gPokeDnDLastDashMovement = sBattle.units[id].movement;
                    PokeDnD_HudMessage(COMPOUND_STRING("PIKA DASH +SPEED"));
                }
            } else {
                if (newKeys & A_BUTTON)
                    result = d20_attack(&sBattle,id,sUnits.enemy,THUNDERBOLT);
                else if (newKeys & R_BUTTON)
                    result = d20_attack(&sBattle,id,sUnits.enemy,QUICK_ATTACK);
                if (newKeys & (A_BUTTON | R_BUTTON))
                    PokeDnD_HudAttack((newKeys & A_BUTTON)
                                        ? COMPOUND_STRING("PIKA THUNDERBOLT")
                                        : COMPOUND_STRING("PIKA QUICK ATTACK"), result);
                if (result.legal) {
                    gPokeDnDMilestones |= 64u;
                    StartImpact(sUnits.enemy, result);
                }
            }
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
