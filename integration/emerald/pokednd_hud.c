/*
 * Small GBA-native combat HUD for the prototype's live Emerald overworld.
 * Uses existing Emerald font/window tiles. No ROM art or external assets.
 */
#include "global.h"
#include "d20.h"
#include "menu.h"
#include "pokednd_hud.h"
#include "string_util.h"
#include "text.h"
#include "window.h"

/* BG0 tile pool 0x40..0xe7, disjoint from Emerald's persistent dialogue
 * window at 0x194. This overlay exists only with field input owned by D20. */
static const struct WindowTemplate sHudWindow = {
    .bg = 0,
    .tilemapLeft = 1,
    .tilemapTop = 0,
    .width = 28,
    .height = 6,
    .paletteNum = 15,
    .baseBlock = 0x40
};
static const u8 sHudColors[] = {
    TEXT_COLOR_DARK_GRAY, TEXT_COLOR_WHITE, TEXT_COLOR_LIGHT_GRAY
};
static const u8 sTxtRound[]     = _("D20 R");
static const u8 sTxtTurn[]      = _("   TURN ");
static const u8 sTxtMove[]      = _(" MV");
static const u8 sTxtHuman[]     = _("HUMAN");
static const u8 sTxtPokemon[]   = _("PIKACHU");
static const u8 sTxtRocket[]    = _("ROCKET");
static const u8 sTxtH[]         = _("H ");
static const u8 sTxtP[]         = _("  P ");
static const u8 sTxtR[]         = _("  R ");
static const u8 sTxtSlash[]     = _("/");
static const u8 sTxtStowed[]    = _("STOWED");
static const u8 sTxtDeploy[]    = _("A:DEPLOY L+START:DASH B:END");
static const u8 sTxtTrainer[]   = _("R:CMD L+START:DASH B:END");
static const u8 sTxtPokemonAct[]= _("A:BOLT R:QUICK L+START:DASH");
static const u8 sTxtEnemyTurn[] = _("ENEMY TURN");
static const u8 sTxtFinish[]    = _("A/B: RETURN TO FIELD");
static const u8 sTxtBegin[]     = _("ROCKET ENCOUNTER");
static const u8 sTxtRoll[]      = _(" d20:");
static const u8 sTxtHit[]       = _(" HIT ");
static const u8 sTxtCrit[]      = _(" CRIT ");
static const u8 sTxtMiss[]      = _(" MISSED");
static const u8 sTxtIllegal[]   = _(" NOT READY");

static EWRAM_DATA bool8 sHudOpen;
static EWRAM_DATA u8 sHudWindowId;
static EWRAM_DATA s8 sHumanId;
static EWRAM_DATA s8 sPokemonId;
static EWRAM_DATA s8 sEnemyId;
static EWRAM_DATA u8 sHudMessage[48];

/* Render a complete line synchronously: ephemeral stack text is never kept
 * by a deferred printer, avoiding stale pointers on the next field frame. */
static void PrintLine(const u8 *str, u8 y)
{
    AddTextPrinterParameterized4(sHudWindowId, FONT_SMALL, 2, y, 0, 0,
                                 sHudColors, TEXT_SKIP_DRAW, str);
}

static void AppendNumber(u8 *dest, int number)
{
    u8 digits[12];
    if (number < 0)
        number = 0;
    ConvertIntToDecimalStringN(digits, number, STR_CONV_MODE_LEFT_ALIGN, 4);
    StringAppend(dest, digits);
}

static void AppendHp(u8 *dest, const D20Unit *unit)
{
    AppendNumber(dest, unit->hp);
    StringAppend(dest, sTxtSlash);
    AppendNumber(dest, unit->max_hp);
}

void PokeDnD_HudRedraw(const D20Battle *battle)
{
    u8 line[76];
    const D20Unit *human;
    const D20Unit *pokemon;
    const D20Unit *rocket;
    int actor;
    if (!sHudOpen || battle == NULL)
        return;
    if (sHumanId < 0 || sPokemonId < 0 || sEnemyId < 0 ||
        sHumanId >= battle->count || sPokemonId >= battle->count ||
        sEnemyId >= battle->count)
        return;

    human = &battle->units[sHumanId];
    pokemon = &battle->units[sPokemonId];
    rocket = &battle->units[sEnemyId];
    actor = d20_actor(battle);

    FillWindowPixelBuffer(sHudWindowId, PIXEL_FILL(TEXT_COLOR_DARK_GRAY));
    StringCopy(line, sTxtRound);
    AppendNumber(line, battle->round);
    StringAppend(line, sTxtTurn);
    if (d20_current(battle) == sEnemyId)
        StringAppend(line, sTxtRocket);
    else if (actor == sPokemonId)
        StringAppend(line, sTxtPokemon);
    else
        StringAppend(line, sTxtHuman);
    if (actor >= 0 && actor < battle->count) {
        StringAppend(line, sTxtMove);
        AppendNumber(line, battle->units[actor].movement);
    }
    PrintLine(line, 0);

    StringCopy(line, sTxtH);
    AppendHp(line, human);
    StringAppend(line, sTxtP);
    if (pokemon->deployed)
        AppendHp(line, pokemon);
    else
        StringAppend(line, sTxtStowed);
    StringAppend(line, sTxtR);
    AppendHp(line, rocket);
    PrintLine(line, 12);

    if (battle->outcome != FIGHTING)
        PrintLine(sTxtFinish, 24);
    else if (d20_current(battle) == sEnemyId)
        PrintLine(sTxtEnemyTurn, 24);
    else if (actor == sPokemonId)
        PrintLine(sTxtPokemonAct, 24);
    else if (!pokemon->deployed)
        PrintLine(sTxtDeploy, 24);
    else
        PrintLine(sTxtTrainer, 24);
    PrintLine(sHudMessage, 36);
    CopyWindowToVram(sHudWindowId, COPYWIN_GFX);
}

void PokeDnD_HudMessage(const u8 *message)
{
    if (sHudOpen && message != NULL)
        StringCopy(sHudMessage, message);
}

void PokeDnD_HudAttack(const u8 *move, D20Attack attack)
{
    if (!sHudOpen || move == NULL)
        return;
    StringCopy(sHudMessage, move);
    if (!attack.legal) {
        StringAppend(sHudMessage, sTxtIllegal);
        return;
    }
    /* Show the actual natural d20 roll, not an invented animation result. */
    StringAppend(sHudMessage, sTxtRoll);
    AppendNumber(sHudMessage, attack.natural);
    if (!attack.hit) {
        StringAppend(sHudMessage, sTxtMiss);
    } else {
        StringAppend(sHudMessage, attack.crit ? sTxtCrit : sTxtHit);
        AppendNumber(sHudMessage, attack.damage);
    }
}

bool8 PokeDnD_HudOpen(const D20Battle *battle, int human, int pokemon, int enemy)
{
    u32 id;
    if (sHudOpen || battle == NULL)
        return FALSE;
    sHudWindowId = WINDOW_NONE;
    id = AddWindow(&sHudWindow);
    if (id == WINDOW_NONE)
        return FALSE;
    sHudWindowId = id;
    sHumanId = human;
    sPokemonId = pokemon;
    sEnemyId = enemy;
    sHudOpen = TRUE;
    StringCopy(sHudMessage, sTxtBegin);
    PutWindowTilemap(sHudWindowId);
    PokeDnD_HudRedraw(battle);
    CopyWindowToVram(sHudWindowId, COPYWIN_FULL);
    return TRUE;
}

void PokeDnD_HudClose(void)
{
    if (!sHudOpen)
        return;
    ClearWindowTilemap(sHudWindowId);
    CopyWindowToVram(sHudWindowId, COPYWIN_MAP);
    RemoveWindow(sHudWindowId);
    PokeDnD_HudAbandon();
}

/* A map reload can reset the whole BG0/window heap. Never call RemoveWindow
 * on an old index after the engine has replaced that heap. */
void PokeDnD_HudAbandon(void)
{
    sHudWindowId = WINDOW_NONE;
    sHudOpen = FALSE;
}
