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
sleep 14; snap 02b-interactive-title
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
echo "Diagnostic captures complete; visual interpretation needed for gameplay claim."
