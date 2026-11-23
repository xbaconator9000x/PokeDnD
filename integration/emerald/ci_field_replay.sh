#!/usr/bin/env bash
# Real mGBA/Xvfb field proof diagnostic, genuine LCD frames only.
set -euo pipefail
ROM="${1:?Usage: ci_field_replay.sh <ROM.gba> <evidence-directory>}"
OUT="${2:?Output directory required}"
mkdir -p "$OUT"
export SDL_VIDEODRIVER=x11 SDL_AUDIODRIVER=dummy
mgba -g "$ROM" >"$OUT/mgba.log" 2>&1 &
EMU=$!
PROBE_PID=""
trap 'if [ -n "$PROBE_PID" ]; then kill "$PROBE_PID" 2>/dev/null || true; fi; kill -9 "$EMU" 2>/dev/null || true' EXIT
WINDOW=""
for i in $(seq 1 20); do
  if ! kill -0 "$EMU" 2>/dev/null; then cat "$OUT/mgba.log"; exit 1; fi
  WINDOW=$(xdotool search --onlyvisible --name "mGBA" 2>/dev/null | sed -n '1p' || true)
  if [ -n "$WINDOW" ]; then break; fi
  sleep 1
done
test -n "$WINDOW" || { echo "No mGBA SDL window"; exit 1; }
xdotool windowfocus "$WINDOW" || true
# Unlike ELF address extraction or screenshots, these are actual GBA bus reads
# while the same mGBA process is running. Require a working debugger or fail.
POKEDND_ELF="${POKEDND_ELF:?Exact-head linked Emerald ELF required for live EWRAM sampling}"
python3 integration/emerald/mgba_ewram_probe.py serve \
  --elf "$POKEDND_ELF" --out "$OUT" >"$OUT/ewram-probe.log" 2>&1 &
PROBE_PID=$!
for i in $(seq 1 80); do
  if [ -f "$OUT/ewram-probe-ready.txt" ]; then break; fi
  if ! kill -0 "$PROBE_PID" 2>/dev/null; then
    echo "Native EWRAM probe failed during startup" >&2
    tail -n 12 "$OUT/ewram-probe.log" >&2
    exit 1
  fi
  sleep 0.25
done
test -f "$OUT/ewram-probe-ready.txt" || {
  echo "Timed out connecting to mGBA GDB stub" >&2
  tail -n 12 "$OUT/ewram-probe.log" >&2
  exit 1
}
sample() {
  python3 integration/emerald/mgba_ewram_probe.py sample --out "$OUT" --label "$1"
}
POKEDND_RUNTIME_PROBE="$OUT/runtime-probe-standard.csv"
# The GDB collector always writes runtime-probe.csv; preserve the first
# encounter after it finishes before validating sequential session resets.
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
# The quickstart hook only handles SELECT in Task_TitleScreenPhase3.
# A single press can land during a cinematic/title task transition. Retry
# across a bounded window, retaining distinct frames for visual diagnosis.
# Do not press A/START here: that would enter the ordinary new-game intro.
for attempt in 1 2 3 4; do
  key BackSpace
  sleep 3
  snap "03-title-select-attempt-$attempt"
done
sleep 2; snap 03-after-title-select
sleep 10; snap 04-world-candidate
# Run the authored encounter in a separate cold emulator session.
# No debug battle, dynamic allocation chord, or inherited reset state.
if [ "${3:-debug}" = "natural" ]; then
  sample natural-baseline
  key Down
  sleep 1; snap 05-authored-rocket-facing
  scenario="${POKEDND_NATURAL_SCENARIO:-standard}"
  case "$scenario" in
    standard) key x ;;
    victory|defeat)
      # L/R do not turn or step the Emerald player before facing-A.
      # Direction+A previously raced the native field movement callback.
      modifier=a
      if [ "$scenario" = defeat ]; then modifier=s; fi
      xdotool keydown --window "$WINDOW" "$modifier"
      sleep 0.25
      key x
      xdotool keyup --window "$WINDOW" "$modifier"
      ;;
    *) echo "Invalid natural replay scenario: $scenario" >&2; exit 2 ;;
  esac
sleep 2; snap 24-facing-a-natural-encounter
sample natural-start
python3 - "$OUT/runtime-probe.csv" <<'CHECKNATIVE'
import csv, sys
with open(sys.argv[1], newline="") as handle:
    row = list(csv.DictReader(handle))[-1]
if (int(row["natural_encounter_count"]) != 1 or
    int(row["last_natural_local_id"]) != 5 or
    int(row["diagnostic_state"]) != 1 or
    int(row["start_failure"]) != 0):
    raise SystemExit(
        "FAIL: authored Rocket facing-A admission "
        f"encounters={row['natural_encounter_count']} "
        f"local_id={row['last_natural_local_id']} "
        f"state={row['diagnostic_state']} "
        f"start_failure={row['start_failure']} "
        f"field_locks={row.get('replay_natural_lock_observations', 'not-probed')}"
    )
print("PASS: live mGBA facing-A activated existing native Rocket object event")
CHECKNATIVE
if [ "$scenario" != standard ]; then
  # Unlike the retreat scenario, these must resolve through real attack/AI
  # turns, preserve the original NPC, acknowledge the result and move.
  last_outcome() {
    python3 - "$OUT/runtime-probe.csv" <<'NATOUT'
import csv,sys
with open(sys.argv[1],newline="") as f:
    print(list(csv.DictReader(f))[-1]["last_outcome"])
NATOUT
  }
  if [ "$scenario" = victory ]; then
    key x; key z; key s
    for attempt in 1 2 3 4 5; do
      key x
      sleep 1
      snap "25-natural-victory-hit-$attempt"
      sample "natural-victory-hit-$attempt"
      if [ "$(last_outcome)" = 1 ]; then break; fi
      key z; key z; key s
    done
    test "$(last_outcome)" = 1 || { echo "FAIL: natural Rocket victory did not resolve"; exit 1; }
  else
    for attempt in $(seq 1 12); do
      key z
      sleep 1
      snap "25-natural-defeat-turn-$attempt"
      sample "natural-defeat-turn-$attempt"
      if [ "$(last_outcome)" = 2 ]; then break; fi
    done
    test "$(last_outcome)" = 2 || { echo "FAIL: natural Rocket defeat did not resolve"; exit 1; }
  fi
  key x
  sleep 1
  snap "25-natural-$scenario-acknowledged"
  sample "natural-$scenario-acknowledged"
  python3 - "$OUT/runtime-probe.csv" "$scenario" <<'NATTERMINAL'
import csv,sys
with open(sys.argv[1],newline="") as f:
    row=list(csv.DictReader(f))[-1]
expected=1 if sys.argv[2]=="victory" else 2
if (int(row["last_outcome"]) != expected or
    int(row["diagnostic_state"]) != 5 or
    int(row["natural_cleanup_status"]) != 1 or
    int(row["natural_encounter_count"]) != 1 or
    int(row["outcome_acks"]) < 1):
    raise SystemExit("FAIL: native natural encounter terminal cleanup/ack")
print("PASS: natural Rocket terminal outcome, acknowledgement and NPC restoration")
NATTERMINAL
else
key BackSpace
sleep 1; snap 25-natural-cancelled
sample natural-cancelled
python3 - "$OUT/runtime-probe.csv" <<'CHECKNATIVECANCEL'
import csv, sys
with open(sys.argv[1], newline="") as handle:
    row = list(csv.DictReader(handle))[-1]
if int(row["diagnostic_state"]) != 4 or int(row["natural_encounter_count"]) != 1:
    raise SystemExit("FAIL: natural encounter cancellation did not preserve attribution")
if int(row["natural_cleanup_status"]) != 1:
    raise SystemExit("FAIL: original Rocket NPC identity was not preserved on cleanup")
print("PASS: native Rocket encounter cancelled without resetting attribution")
CHECKNATIVECANCEL
fi
# The restored Rocket may occupy the tile to the right. Try ordinary
# directions and stop on the first observed real movement.
for direction in Right Left Up Down; do
  key "$direction"
  sleep 2
  note="natural-resumed-${direction,,}"
  snap "26-$note"
  sample "$note"
  if python3 - "$OUT/runtime-probe.csv" <<'CHECKMOVE'
import csv, sys
with open(sys.argv[1], newline="") as handle:
    row = list(csv.DictReader(handle))[-1]
raise SystemExit(0 if int(row["post_cancel_moves"]) >= 1 else 1)
CHECKMOVE
  then break; fi
done
python3 - "$OUT/runtime-probe.csv" <<'CHECKNATIVERESUME'
import csv, sys
with open(sys.argv[1], newline="") as handle:
    row = list(csv.DictReader(handle))[-1]
if int(row["post_cancel_moves"]) < 1:
    raise SystemExit("FAIL: native Rocket encounter did not restore field movement")
print("PASS: native facing-A Rocket encounter restored real field movement")
CHECKNATIVERESUME
  # Independently reject blank or frozen native LCD evidence before admitting
  # the authored encounter. Compare decoded pixels, not PNG metadata.
  lcd_check() {
    local frame="$1" colors
    test -s "$frame" || return 1
    colors=$(identify -format '%k' "$frame") || return 1
    test "$colors" -ge 8
  }
  lcd_distinct() {
    local left="$1" right="$2" a b
    a=$(convert "$left" -alpha off -resize 240x160! -depth 8 rgb:- | sha256sum) || return 1
    b=$(convert "$right" -alpha off -resize 240x160! -depth 8 rgb:- | sha256sum) || return 1
    test "$a" != "$b"
  }
  # Exercise failure paths with synthetic images; never retain them as evidence.
  lcd_fixture=$(mktemp -d)
  convert -size 240x160 xc:white "$lcd_fixture/blank.png"
  convert -size 240x160 gradient:black-white "$lcd_fixture/gradient.png"
  if lcd_check "$lcd_fixture/blank.png" ||
     lcd_distinct "$lcd_fixture/gradient.png" "$lcd_fixture/gradient.png" ||
     ! lcd_check "$lcd_fixture/gradient.png" ||
     ! lcd_distinct "$lcd_fixture/blank.png" "$lcd_fixture/gradient.png"; then
    rm -rf "$lcd_fixture"
    echo "FAIL: LCD gate regression self-test" >&2
    exit 1
  fi
  rm -rf "$lcd_fixture"
  entry="$OUT/24-facing-a-natural-encounter.png"
  before="$OUT/05-authored-rocket-facing.png"
  if [ "$scenario" = standard ]; then
    terminal="$OUT/25-natural-cancelled.png"
  else
    terminal="$OUT/25-natural-$scenario-acknowledged.png"
  fi
  resumed="$OUT/26-$note.png"
  for frame in "$before" "$entry" "$terminal" "$resumed"; do
    lcd_check "$frame" || { echo "FAIL: missing or blank LCD $frame" >&2; exit 1; }
  done
  lcd_distinct "$before" "$entry" &&
  lcd_distinct "$entry" "$terminal" &&
  lcd_distinct "$terminal" "$resumed" || {
    echo "FAIL: frozen LCD across native encounter transitions" >&2; exit 1;
  }
  {
    printf 'capture,colors,sha256\n'
    for frame in "$before" "$entry" "$terminal" "$resumed"; do
      printf '%s,%s,%s\n' "$(basename "$frame")" "$(identify -format %k "$frame")" "$(sha256sum "$frame" | cut -d' ' -f1)"
    done
  } > "$OUT/lcd-transition-manifest.csv"
  printf '%s\\n' "PASS: nonblank distinct native LCD entry, cleanup and movement; semantic visual review remains separate" > "$OUT/lcd-transition-verdict.txt"
  sha256sum "$ROM" | awk '{print $1}' > "$OUT/rom-sha256.txt"
  printf '%s\n' "PASS: authored Oldale NPC, ordinary A, ${scenario} resolution and field movement" > "$OUT/NATIVE_AUTHORED_REPLAY_ACCEPTED.txt"
  exit 0
fi
# Discover where the native flow reaches after quickstart. Capture evidence.
for k in Left Left Down Down Right Down; do
  key "$k"; sleep 1
done
sleep 2; snap 05-after-movement
sample baseline
# Debug-only replay must never claim a natural Rocket encounter. Check the
# *live* mGBA EWRAM values before and after the full debug sequence.
assert_no_natural_encounter() {
  python3 - "$OUT/runtime-probe.csv" <<'CHECKNATURAL'
import csv, sys
with open(sys.argv[1], newline="") as handle:
    rows = list(csv.DictReader(handle))
if not rows:
    raise SystemExit("FAIL: missing native encounter telemetry")
for row in rows:
    if int(row["natural_encounter_count"]) != 0 or int(row["last_natural_local_id"]) != 0:
        raise SystemExit("FAIL: debug replay incorrectly recorded a natural NPC encounter")
print("PASS: debug replay has no false natural Rocket encounter attribution")
CHECKNATURAL
}
assert_no_natural_encounter
# mGBA SDL default: L=A, R=S, START=Return, Pokémon A=X, B=Z.
xdotool keydown --window "$WINDOW" a
xdotool keydown --window "$WINDOW" s
key Return
xdotool keyup --window "$WINDOW" s
xdotool keyup --window "$WINDOW" a
sleep 2; snap 06-after-combat-chord
sample started
key x
sleep 2; snap 07-after-a-deployment
sample deployed
key z
sleep 2; snap 08-after-b-turn
sample turn
# Replay a single real encounter: do not spam A/dialogue or retrigger a
# second fight. Those formerly set the attack bit before its sample and
# produced a misleading pass with no accountable attack input.
key s
sleep 2; snap 09-commanded-pikachu
sample commanded
key x
sleep 2; snap 10-pikachu-thunderbolt
sample attacked
key z
sleep 2; snap 11-trainer-reselected
# Trainer retains their Action after commanding Pikachu via Bonus Action.
# Real L-held + newly pressed START must Dash for 6 extra five-foot tiles.
xdotool keydown --window "$WINDOW" a
key Return
xdotool keyup --window "$WINDOW" a
sleep 2; snap 11b-native-trainer-dash
sample dashed
python3 - "$OUT/runtime-probe.csv" <<'CHECKDASH'
import csv, sys
with open(sys.argv[1], newline="") as handle:
    rows = list(csv.DictReader(handle))
row = rows[-1]
if row["label"] != "dashed" or int(row["dash_count"]) != 1 or int(row["last_dash_movement"]) != 12:
    raise SystemExit("FAIL: live mGBA Dash did not grant six additional movement tiles")
if int(row["start_failure"]) != 0:
    raise SystemExit("FAIL: Dash replay triggered encounter admission failure")
print("PASS: native Dash consumed trainer Action and granted 12 movement tiles")
CHECKDASH
key z
sleep 2; snap 12-shared-turn-ended
key BackSpace
sleep 2; snap 13-combat-cancelled
sample cancelled
# After cancel, real overworld movement must be available again.
key Right
sleep 2; snap 14-normal-field-movement
sample resumed
# Preserve the proven standard encounter separately: sticky milestones reset
# legitimately on every *new* battle, so validate that original session alone.
cp "$OUT/runtime-probe.csv" "$OUT/runtime-probe-standard.csv"

# Native win/loss scenarios keep the same authentic collision, sprites,
# initiative, hit rolls, HP damage and outcome transitions. Only initial
# health/AC differ, selected via UP/DOWN held on the debug chord.
chord_with_direction() {
  local direction="$1"
  xdotool keydown --window "$WINDOW" a
  xdotool keydown --window "$WINDOW" s
  xdotool keydown --window "$WINDOW" "$direction"
  key Return
  xdotool keyup --window "$WINDOW" "$direction"
  xdotool keyup --window "$WINDOW" s
  xdotool keyup --window "$WINDOW" a
}
last_outcome() {
  python3 - "$OUT/runtime-probe.csv" <<'CHECKOUTCOME'
import csv,sys
with open(sys.argv[1],newline='') as f:
    rows=list(csv.DictReader(f))
print(rows[-1]['last_outcome'])
CHECKOUTCOME
}
chord_with_direction Up
sleep 2; snap 15-victory-debug-entry
sample victory-start
if [ "$(last_outcome)" != "0" ]; then echo "Victory debug entry failed" >&2; exit 1; fi
key x
sleep 1
key z
sleep 1
key s
sleep 1
for attempt in 1 2 3 4 5; do
  key x
  # Capture the genuine post-hit LCD *before* the 32-frame impact ends.
  # This is not independently proof of a hit; the native counters below are.
  snap "15b-victory-attack-impact-$attempt"
  sleep 1
  sample "victory-attack-$attempt"
  if [ "$(last_outcome)" = 1 ]; then break; fi
  # A missed attack is still a legal D20 roll. Advance shared initiative,
  # command the Pokemon on its next ready trainer turn and retry.
  key z
  key z
  key s
done
test "$(last_outcome)" = 1 || { echo "Native Rocket victory never resolved" >&2; exit 1; }
sleep 1; snap 16-victory-result
sample victory-result
key x
sleep 1; snap 17-victory-confirmed
sample victory-confirmed
# A restored field may face a wall or NPC. Exercise ordinary directional
# input before the single canonical acceptance sample. Never infer movement
# from LCD changes alone.
resume_field() {
  local label="$1" frame="$2" direction
  for direction in Right Left Up Down; do
    key "$direction"
    sleep 1
  done
  snap "$frame"
  sample "$label"
}
resume_field victory-resumed 18-victory-returned-field

chord_with_direction Down
sleep 2; snap 19-defeat-debug-entry
sample defeat-start
test "$(last_outcome)" = 0 || { echo "Native defeat entry failed" >&2; exit 1; }
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
  key z
  snap "19b-defeat-turn-impact-$attempt"
  sleep 1
  sample "defeat-turn-$attempt"
  if [ "$(last_outcome)" = 2 ]; then break; fi
done
test "$(last_outcome)" = 2 || { echo "Native trainer defeat never resolved" >&2; exit 1; }
sleep 1; snap 20-defeat-result
sample defeat-result
key x
sleep 1; snap 21-defeat-confirmed
sample defeat-confirmed
resume_field defeat-resumed 22-defeat-returned-field
python3 integration/emerald/validate_outcome_replay.py "$OUT/runtime-probe.csv" "$OUT"
assert_no_natural_encounter
# After the defeat replay, exercise ordinary Emerald D-pad input before
# creating a fixture, preserving a separate LCD/probe checkpoint. This is
# a diagnostic precondition, NOT proof of a tile transition or unlocked
# field controls; the fixture admission check remains authoritative.
sample pre-fixture-movement-baseline
key Left
sleep 2
key Right
sleep 2
snap 22a-pre-fixture-field-movement
sample pre-fixture-field-movement
python3 - "$OUT/runtime-probe.csv" <<'CHECKFIELD'
import csv, sys
with open(sys.argv[1], newline="") as handle:
    rows = list(csv.DictReader(handle))
baseline, current = rows[-2:]
if int(current["trigger_count"]) < 3:
    raise SystemExit("FAIL: pre-fixture recovery lost native battle history")
if int(current["diagnostic_state"]) not in (4, 5):
    raise SystemExit("FAIL: pre-fixture field unexpectedly entered combat")
print("PASS: retained battle history and idle D20 state before Rocket fixture")
CHECKFIELD
# Preserve the exact ROM identity and reproducible input sequence alongside frames.
# A replay of a stale ROM cannot establish acceptance of the current source HEAD.
sha256sum "$ROM" | awk '{print $1}' > "$OUT/rom-sha256.txt"
cat > "$OUT/input-sequence.txt" <<'EOF'
Emulator: mGBA SDL; key mapping: BackSpace=SELECT, a=L, s=R,
Return=START, x=A, z=B, arrow keys=D-pad.
One field encounter: L+R+START at frame 06. After Pikachu attacks,\nB reselects the trainer; hold L and press START to Dash, verified by\nlive mGBA EWRAM dash_count=1 and last_dash_movement=12.
A deploys Pikachu, B advances the shared initiative, R commands via a
trainer Bonus Action, A attempts Thunderbolt, B reselects trainer, B ends
the shared turn, SELECT cancels, Right checks ordinary field movement.
Then UP+L+R+START starts a low-HP Rocket victory scenario. A still
requires a real D20 hit and engine outcome, with B/R turn/command retries
only on actual misses. A confirms the result; Right restores field input.
DOWN+L+R+START starts a vulnerable-trainer defeat scenario. B advances
real Rocket AI turns; engine damage must KO the human. A confirms defeat;
Right must restore native Emerald movement. Both endings have real EWRAM
result/HP/acknowledgement/readback and distinct LCD frames. Successful hits
also require verified native sprite-offset frames and an early LCD capture.
No gameplay acceptance is inferred from screenshots or inputs alone.
EOF
# Require actual live memory observations from the same mGBA process.
# Expected CSV: trigger_count,start_failure,milestones,diagnostic_state,post_cancel_moves.
# Diagnostic screenshots are NEVER a substitute for this trace.
# Milestones bit 0=start, bit 1=deploy, bit 2=turn.
if [ ! -s "$POKEDND_RUNTIME_PROBE" ]; then
  echo "FAIL: missing live EWRAM trace" >&2
  exit 1
fi
if [ -n "${POKEDND_RUNTIME_PROBE:-}" ]; then
  python3 - "${POKEDND_RUNTIME_PROBE}" "$OUT" <<'PY'
import csv, pathlib, sys
source, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
with source.open(newline="") as handle:
    rows = list(csv.DictReader(handle))
required = {"trigger_count", "start_failure", "milestones", "diagnostic_state", "post_cancel_moves"}
if not rows or not required.issubset(rows[0]):
    raise SystemExit("FAIL: missing runtime probe rows or columns")
observed = []
for row in rows:
    trigger, failure, bits, state, moves = (int(row[k], 0) for k in
        ("trigger_count", "start_failure", "milestones", "diagnostic_state", "post_cancel_moves"))
    if min(trigger, failure, bits, state, moves) < 0:
        raise SystemExit("FAIL: negative runtime probe value")
    observed.append((trigger, failure, bits, state, moves))
# A single synthetic or stale all-bits-set row is not a replay trace.
# Require sequential emulator observations of activation, deployment and turn.
# Trigger counts must never decrease and milestone bits must be monotonic.
if len(observed) < 8:
    raise SystemExit("FAIL: require baseline, combat actions, cancellation and field-step samples")
if observed[0][1] != 0:
    raise SystemExit("FAIL: runtime admission failure observed")
for previous, current in zip(observed, observed[1:]):
    if current[4] < previous[4]:
        raise SystemExit("FAIL: native post-cancel movement counter regressed")
    if current[0] < previous[0]:
        raise SystemExit("FAIL: runtime trigger count regressed")
    if current[0] > previous[0] + 1:
        raise SystemExit("FAIL: missing trigger attempts in runtime trace")
    if current[1] != 0:
        raise SystemExit("FAIL: runtime admission failure observed")
    if current[3] not in (0, 1, 2, 3, 4, 5):
        raise SystemExit("FAIL: invalid native diagnostic state")
    if (current[2] & previous[2]) != previous[2]:
        raise SystemExit("FAIL: runtime milestones regressed")
# A valid encounter must have a clean pre-trigger baseline, then distinct
# observations of start, deployment and turn for the same trigger attempt.
# Reject failure codes at any point during the accepted attempt.
passed = False
for i in range(len(observed) - 8):
    baseline, started, deployed, turned, commanded, attacked, dashed, cancelled, resumed = observed[i:i + 9]
    attempt = started[0]
    if (baseline[0] + 1 == attempt and baseline[1] == 0
            and baseline[2] == 0 and baseline[3] == 0
            and all(row[0] == attempt and row[1] == 0
                    for row in (started, deployed, turned, commanded, attacked, dashed, cancelled, resumed))
            and started[3] == 1 and deployed[3] == 2 and turned[3] == 3
            and commanded[3] == 3 and attacked[3] == 3
            and dashed[3] == 3 and cancelled[3] == 4 and resumed[3] == 4
            and all(row[4] == 0 for row in (baseline, started, deployed,
                    turned, commanded, attacked, dashed, cancelled))
            and resumed[4] == 1
            and (started[2] & 255) == 1
            and (deployed[2] & 255) == 3
            and (turned[2] & 255) == 135
            and (commanded[2] & 255) == 167
            and (attacked[2] & 255) == 231
            and (dashed[2] & 255) == 231
            and (cancelled[2] & 255) == 239
            and (resumed[2] & 255) == 239):
        passed = True
        break
(out / "runtime-probe-verdict.txt").write_text(
    ("PASS" if passed else "FAIL") +
    ": live mGBA EWRAM proves encounter, deployment, turn, command, attack, cancellation and native overworld step\n"
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
  for symbol in gPokeDnDTriggerCount gPokeDnDStartFailure gPokeDnDDiagnosticState gPokeDnDMilestones gPokeDnDPostCancelMoves; do
    if ! awk -v s="$symbol" '$3 == s {found=1} END {exit !found}' "$OUT/linked-symbols.txt"; then
      echo "Missing linked combat probe symbol: $symbol" >&2
      exit 1
    fi
  done
  awk '$3 ~ /^gPokeDnD(TriggerCount|StartFailure|DiagnosticState|Milestones|PostCancelMoves)$/ {print}' \
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
cat > "$OUT/NATIVE_DEBUG_REPLAY_ACCEPTED.txt" <<'EOF'
This run passed live mGBA EWRAM validation for the debug-triggered
PokéDND encounters: deployment, paid command, D20 attack, normal
cancellation, separate victory and defeat with observed terminal HP,
native impact frames, result acknowledgements, and field steps.
The linked ROM was built from the pinned Emerald source in this run.
These checks do NOT establish natural NPC/wild encounter activation,
full map navigation, persistence, or a complete playable RPG.
See runtime-probe-verdict.txt, outcome-verdict.txt, runtime-probe.csv
and the genuine mGBA LCD captures for the underlying evidence.
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
