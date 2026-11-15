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
key s
sleep 2; snap 16-trainer-bonus-command-attempt
key x
sleep 2; snap 17-commanded-thunderbolt-attempt
key z
sleep 2; snap 17b-return-to-trainer
key z
sleep 2; snap 17c-end-shared-initiative
key BackSpace
sleep 2; snap 18-cancel-attempt
# Preserve the exact ROM identity and reproducible input sequence alongside frames.
# A replay of a stale ROM cannot establish acceptance of the current source HEAD.
sha256sum "$ROM" | awk '{print $1}' > "$OUT/rom-sha256.txt"
cat > "$OUT/input-sequence.txt" <<'EOF'
Emulator: mGBA SDL; key mapping: BackSpace=SELECT, a=L, s=R,
Return=START, x=A, z=B, arrow keys=D-pad.
Entry attempts: L+R+START at frames 06 and 13.
Actions: A deployment, B ends trainer turn, R commands via Bonus Action,
A uses commanded Thunderbolt, B returns to trainer, B ends shared turn,
SELECT cancellation. Commands on a scripted title screen are not proof.
No gameplay acceptance is inferred from these inputs.
EOF
# Require an explicitly supplied emulator memory snapshot for gameplay acceptance.
# A linked ELF or a screenshot alone is not a runtime observation.
# Expected CSV columns: trigger_count,start_failure,milestones (integer or 0x hex).
# Milestones bit 0=start, bit 1=deploy, bit 2=turn.
if [ -n "${POKEDND_RUNTIME_PROBE:-}" ]; then
  python3 - "${POKEDND_RUNTIME_PROBE}" "$OUT" <<'PY'
import csv, pathlib, sys
source, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
with source.open(newline="") as handle:
    rows = list(csv.DictReader(handle))
required = {"trigger_count", "start_failure", "milestones"}
if not rows or not required.issubset(rows[0]):
    raise SystemExit("FAIL: missing runtime probe rows or columns")
observed = []
for row in rows:
    trigger, failure, bits = (int(row[k], 0) for k in
                              ("trigger_count", "start_failure", "milestones"))
    if min(trigger, failure, bits) < 0:
        raise SystemExit("FAIL: negative runtime probe value")
    observed.append((trigger, failure, bits))
passed = any(t > 0 and f == 0 and (m & 7) == 7 for t, f, m in observed)
(out / "runtime-probe-verdict.txt").write_text(
    ("PASS" if passed else "FAIL") +
    ": observed native trigger, admission, deployment and turn milestones\\n"
)
if not passed:
    raise SystemExit("FAIL: runtime probe does not establish tactical gameplay")
PY
fi
# A caller may supply an exact-head linked ELF to identify debugger probe
# addresses. This does NOT claim those variables were read from the emulator.
if [ -n "${POKEDND_ELF:-}" ]; then
  test -f "$POKEDND_ELF" || { echo "Missing POKEDND_ELF" >&2; exit 1; }
  NM="${POKEDND_NM:-arm-none-eabi-nm}"
  "$NM" -n "$POKEDND_ELF" > "$OUT/linked-symbols.txt"
  for symbol in gPokeDnDTriggerCount gPokeDnDStartFailure gPokeDnDDiagnosticState gPokeDnDMilestones; do
    if ! awk -v s="$symbol" '$3 == s {found=1} END {exit !found}' "$OUT/linked-symbols.txt"; then
      echo "Missing linked combat probe symbol: $symbol" >&2
      exit 1
    fi
  done
  awk '$3 ~ /^gPokeDnD(TriggerCount|StartFailure|DiagnosticState|Milestones)$/ {print}' \
    "$OUT/linked-symbols.txt" > "$OUT/probe-addresses.txt"
fi
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
First read gPokeDnDTriggerCount: zero means the field hook never saw the chord.
If positive, read gPokeDnDStartFailure to diagnose admission rejection.
Before accepting combat, read native gPokeDnDDiagnosticState from emulated
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
