#!/usr/bin/env bash
# Real mGBA/Xvfb field proof diagnostic, genuine LCD frames only.
set -euo pipefail
ROM="${1:?Usage: ci_field_replay.sh <ROM.gba> <evidence-directory>}"
OUT="${2:?Output directory required}"
mkdir -p "$OUT"
export SDL_VIDEODRIVER=x11 SDL_AUDIODRIVER=dummy
mgba "$ROM" >"$OUT/mgba.log" 2>&1 &
EMU=$!
trap 'kill -9 "$EMU" 2>/dev/null || true' EXIT
WINDOW=""
for i in $(seq 1 20); do
  if ! kill -0 "$EMU" 2>/dev/null; then cat "$OUT/mgba.log"; exit 1; fi
  WINDOW=$(xdotool search --onlyvisible --name "mGBA" 2>/dev/null | sed -n '1p' || true)
  if [ -n "$WINDOW" ]; then break; fi
  sleep 1
done
test -n "$WINDOW" || { echo "No mGBA SDL window"; exit 1; }
xdotool windowfocus "$WINDOW" || true
snap() {
  local name="$1"
  timeout 6s xwd -silent -id "$WINDOW" | convert xwd:- "$OUT/$name.png"
  printf '%-32s colors=%s\n' "$name" "$(identify -format %k "$OUT/$name.png")"
}
key() {
  xdotool keydown --window "$WINDOW" "$1"
  sleep 0.25
  xdotool keyup --window "$WINDOW" "$1"
}
sleep 10; snap 01-startup
sleep 12; snap 02-title-animation
# Emerald title animation is still in progress after ~22 seconds.
# Pressing SELECT before Task_TitleScreenPhase3 is active is ignored.
sleep 14; snap 02b-title-cinematic
# The rider cinematic still runs at ~36 s; the press-start title appears
# only after roughly 45 s. Wait until the SELECT New Game HUD is shown.
sleep 16; snap 02c-title-ready
# pokeemerald-expansion quickstart: SELECT on interactive title skips naming.
key BackSpace
sleep 8; snap 03-after-title-select
sleep 10; snap 04-world-candidate
# Discover where the native flow reaches after quickstart. Capture evidence.
for k in Left Left Down Down Right Down; do
  key "$k"; sleep 1
done
sleep 2; snap 05-after-movement
# mGBA SDL default: L=A, R=S, START=Return, Pokémon A=X, B=Z.
xdotool keydown --window "$WINDOW" a
xdotool keydown --window "$WINDOW" s
key Return
xdotool keyup --window "$WINDOW" s
xdotool keyup --window "$WINDOW" a
sleep 2; snap 06-after-combat-chord
key x
sleep 2; snap 07-after-a-deployment
key z
sleep 2; snap 08-after-b-turn
# The previous test often reached a transitional mostly-black frame.
# Continue recording instead of misreporting it as either success or failure.
sleep 15; snap 09-transition-plus-15
sleep 15; snap 10-transition-plus-30
for i in $(seq 1 16); do
  key x
  sleep 1
  if [ $((i % 4)) -eq 0 ]; then snap "11-dialogue-advance-$i"; fi
done
sleep 5; snap 12-final-field-candidate
# A second attempt after dialogue advancement is necessary: the initial chord
# may have been sent while the title/new-game script still owned input.
# Record each input phase separately so a reviewer can distinguish title,
# field, encounter activation, deployment, turns and cancellation.
xdotool keydown --window "$WINDOW" a
xdotool keydown --window "$WINDOW" s
key Return
xdotool keyup --window "$WINDOW" s
xdotool keyup --window "$WINDOW" a
sleep 3; snap 13-late-encounter-chord
key x
sleep 2; snap 14-deploy-attempt
key z
sleep 2; snap 15-end-human-turn
key x
sleep 2; snap 16-pokemon-action-attempt
key z
sleep 2; snap 17-end-pokemon-turn
key BackSpace
sleep 2; snap 18-cancel-attempt
# Diagnostic screenshots are not acceptance evidence. Record image changes
# around the encounter attempt and refuse to label a static replay playable.
# The native gPokeDnDDiagnosticState must be read by a debugger/mGBA probe
# before any workflow can assert encounter/deployment/turn acceptance.
{
  printf 'capture,colors,sha256\n'
  for frame in "$OUT"/*.png; do
    printf '%s,%s,%s\n' "$(basename "$frame")" \
      "$(identify -format %k "$frame")" \
      "$(sha256sum "$frame" | cut -d' ' -f1)"
  done
} > "$OUT/frame-manifest.csv"
cat > "$OUT/ACCEPTANCE_NOT_VERIFIED.txt" <<'EOF'
This artifact contains genuine mGBA display captures, NOT verified tactical gameplay.
A green workflow means the emulator and capture harness ran successfully.
First read gPokeDnDTriggerCount: zero means the field hook never saw the chord.\nIf positive, read gPokeDnDStartFailure to diagnose admission rejection.\nBefore accepting combat, read native gPokeDnDDiagnosticState from emulated
EWRAM and verify ordered transitions: 1 encounter, 2 deployment, 3 turn,
4 cancellation (or 5 completion). Do not infer these from filenames or PNGs.
EOF
# Produce a compact, chronological animation exclusively from genuine emulator
# window captures. This is diagnostic evidence, NOT proof of a playable battle.
# Natural filename sorting preserves 02b/02c and numbered dialogue frames.
mapfile -t frames < <(find "$OUT" -maxdepth 1 -name '*.png' -type f | LC_ALL=C sort -V)
if [ "${#frames[@]}" -lt 8 ]; then
  echo "Insufficient real emulator frames for diagnostic GIF" >&2
  exit 1
fi
convert -limit memory 128MiB -limit map 256MiB \
  -delay 110 "${frames[@]}" -resize 480x320 -layers Optimize \
  -loop 0 "$OUT/emerald-real-mgba-diagnostic.gif"
test -s "$OUT/emerald-real-mgba-diagnostic.gif"
identify -format 'Diagnostic GIF: %n frames, %wx%h pixels\n' \
  "$OUT/emerald-real-mgba-diagnostic.gif" | head -n 1
echo "Real mGBA diagnostic GIF generated; combat playability is NOT asserted."
