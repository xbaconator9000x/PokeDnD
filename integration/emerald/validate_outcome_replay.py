#!/usr/bin/env python3
"""Fail-closed native Emerald victory/defeat acceptance for a live GDB CSV.

This is only authoritative when the input CSV comes from the replay's real
mGBA debugger socket. Synthetic rows are used only for validator unit tests.
"""
import argparse
import csv
from pathlib import Path


REQUIRED = (
    "label", "trigger_count", "start_failure", "milestones",
    "diagnostic_state", "post_cancel_moves", "last_outcome",
    "last_human_hp", "last_enemy_hp", "outcome_acks",
    "impact_starts", "impact_frames",
)


def validate(rows):
    if not rows:
        raise ValueError("no live EWRAM samples")
    if set(REQUIRED) - set(rows[0]):
        raise ValueError("missing native outcome or HP registers")
    standard_labels = ("baseline", "started", "deployed", "turn",
                       "commanded", "attacked", "dashed", "cancelled", "resumed")
    # The live debugger CSV contains the preceding standard encounter too.
    # Accept only its known, ordered labels and exclude it from the outcome
    # checkpoint validator; unknown labels still fail closed.
    labels_all = [row["label"] for row in rows]
    legacy_labels = tuple(label for label in standard_labels if label != "dashed")
    standard = [label for label in labels_all if label in standard_labels]
    if standard:
        if (tuple(standard) not in (standard_labels, legacy_labels) or
                labels_all[:len(standard)] != standard):
            raise ValueError("standard native encounter checkpoints out of order")
        rows = rows[len(standard):]
    parsed = []
    for row in rows:
        sample = {"label": row["label"]}
        for column in REQUIRED[1:]:
            sample[column] = int(row[column], 0)
            if sample[column] < 0:
                raise ValueError("negative EWRAM value")
        parsed.append(sample)

    def checkpoint(name):
        found = [r for r in parsed if r["label"] == name]
        if len(found) != 1:
            raise ValueError("expected exactly one checkpoint: " + name)
        return found[0]

    vstart = checkpoint("victory-start")
    vresult = checkpoint("victory-result")
    vconfirm = checkpoint("victory-confirmed")
    vresume = checkpoint("victory-resumed")
    dstart = checkpoint("defeat-start")
    dresult = checkpoint("defeat-result")
    dconfirm = checkpoint("defeat-confirmed")
    dresume = checkpoint("defeat-resumed")
    labels = [r["label"] for r in parsed]
    # Reject unaccounted samples and checkpoints outside their own encounter.
    # A correct name alone must never make a stale debugger row admissible.
    allowed = set(("victory-start", "victory-result", "victory-confirmed",
                   "victory-resumed", "defeat-start", "defeat-result",
                   "defeat-confirmed", "defeat-resumed"))
    for label in labels:
        if label not in allowed and not (label.startswith("victory-attack-")
                                         or label.startswith("defeat-turn-")):
            raise ValueError("unexpected native outcome checkpoint: " + label)
    sequence = ["victory-start", "victory-result", "victory-confirmed",
                "victory-resumed", "defeat-start", "defeat-result",
                "defeat-confirmed", "defeat-resumed"]
    if [labels.index(n) for n in sequence] != sorted(labels.index(n) for n in sequence):
        raise ValueError("native outcome events out of order")
    for i, label in enumerate(labels):
        if label.startswith("victory-attack-") and not (labels.index("victory-start") < i < labels.index("victory-result")):
            raise ValueError("victory attack checkpoint outside encounter")
        if label.startswith("defeat-turn-") and not (labels.index("defeat-start") < i < labels.index("defeat-result")):
            raise ValueError("defeat turn checkpoint outside encounter")
    if not any(r["label"].startswith("victory-attack-") and
               labels.index("victory-start") < i < labels.index("victory-result")
               for i, r in enumerate(parsed)):
        raise ValueError("victory lacks actual input/attack checkpoint")
    if not any(r["label"].startswith("defeat-turn-") and
               labels.index("defeat-start") < i < labels.index("defeat-result")
               for i, r in enumerate(parsed)):
        raise ValueError("defeat lacks genuine enemy turn checkpoint")

    # Intermediate checkpoints must be genuine samples from the same native
    # encounter, not merely correctly named rows. In particular, reject
    # outcome bits that were already present at encounter entry.
    for prefix, attempt, marker, required_bit in (
        ("victory", 2, "victory-attack-", 64),
        ("defeat", 3, "defeat-turn-", 4),
    ):
        start_index = labels.index(prefix + "-start")
        result_index = labels.index(prefix + "-result")
        intermediates = [
            r for r in parsed[start_index + 1:result_index]
            if r["label"].startswith(marker)
        ]
        if not intermediates:
            raise ValueError(prefix + " lacks intermediate native samples")
        if parsed[start_index]["milestones"] & required_bit:
            raise ValueError(prefix + " inherited combat milestone before input")
        previous_bits = parsed[start_index]["milestones"]
        for row in intermediates + [parsed[result_index]]:
            if row["trigger_count"] != attempt or row["start_failure"]:
                raise ValueError(prefix + " intermediate sample belongs to wrong encounter")
            if row["milestones"] & previous_bits != previous_bits:
                raise ValueError(prefix + " intermediate milestones regressed")
            if row["outcome_acks"] != (0 if prefix == "victory" else 1):
                raise ValueError(prefix + " result acknowledged before confirmation")
            if row["post_cancel_moves"]:
                raise ValueError(prefix + " moved before field restoration")
            previous_bits = row["milestones"]
        if not any(row["milestones"] & required_bit for row in intermediates):
            raise ValueError(prefix + " lacks observed native attack/turn milestone")
        # The terminal KO must be visible at an actual input/initiative
        # checkpoint, not appear for the first time in a fabricated result row.
        terminal = 1 if prefix == "victory" else 2
        ko_register = "last_enemy_hp" if prefix == "victory" else "last_human_hp"
        survivor = "last_human_hp" if prefix == "victory" else "last_enemy_hp"
        if not any(row["last_outcome"] == terminal and row[ko_register] == 0
                   and row[survivor] > 0 and row["impact_frames"] > 0
                   and row["impact_starts"] > 0 for row in intermediates):
            raise ValueError(prefix + " lacks observed native terminal damage at input checkpoint")
        if any(row["last_outcome"] not in (0, terminal) for row in intermediates):
            raise ValueError(prefix + " intermediate has conflicting outcome")

    for name, start, result, confirm, resume, attempt, outcome, acks in (
        ("victory", vstart, vresult, vconfirm, vresume, 2, 1, 0),
        ("defeat", dstart, dresult, dconfirm, dresume, 3, 2, 1),
    ):
        if any(row["start_failure"] for row in (start, result, confirm, resume)):
            raise ValueError(name + " has native admission failure")
        if any(row["trigger_count"] != attempt for row in (start, result, confirm, resume)):
            raise ValueError(name + " has wrong native encounter count")
        if start["last_outcome"] != 0 or start["diagnostic_state"] != 1:
            raise ValueError(name + " did not start a new live fight")
        if start["outcome_acks"] != acks:
            raise ValueError(name + " inherited unexpected result acknowledgement")
        if start["impact_starts"] or start["impact_frames"]:
            raise ValueError(name + " inherited impact animation before an attack")
        if result["last_outcome"] != outcome or result["outcome_acks"] != acks:
            raise ValueError(name + " lacks unacknowledged native result")
        if result["impact_starts"] < 1 or result["impact_frames"] < 1:
            raise ValueError(name + " lacks native sprite hit reaction frames")
        if result["diagnostic_state"] not in (1, 2, 3):
            raise ValueError(name + " result screen was already dismissed")
        if confirm["last_outcome"] != outcome or confirm["diagnostic_state"] != 5:
            raise ValueError(name + " did not complete native battle cleanup")
        if confirm["outcome_acks"] != acks + 1 or not confirm["milestones"] & 16:
            raise ValueError(name + " lacks separate confirmed outcome")
        if any(row["post_cancel_moves"] != 0 for row in (start, result, confirm)):
            raise ValueError(name + " counted a premature field step")
        if resume["last_outcome"] != outcome or resume["diagnostic_state"] != 5:
            raise ValueError(name + " lost result after resuming")
        if resume["outcome_acks"] != acks + 1 or resume["post_cancel_moves"] != 1:
            raise ValueError(name + " did not resume with a real map-tile step")

    if vresult["last_enemy_hp"] != 0 or vresult["last_human_hp"] < 1:
        raise ValueError("victory did not defeat Rocket while human survived")
    if dresult["last_human_hp"] != 0 or dresult["last_enemy_hp"] < 1:
        raise ValueError("defeat did not KO human while Rocket survived")
    if not vresult["milestones"] & 64:
        raise ValueError("victory did not include a legal Pokémon attack")
    if not dresult["milestones"] & 4:
        raise ValueError("defeat did not progress real initiative")
    return "PASS: mGBA D20 win/loss + real HP damage + confirmed cleanup + both normal field steps"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    with args.trace.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    try:
        verdict = validate(rows)
    except (ValueError, KeyError) as error:
        verdict = "FAIL: " + str(error)
        args.evidence.joinpath("outcome-verdict.txt").write_text(verdict + "\n")
        raise SystemExit(verdict)
    args.evidence.joinpath("outcome-verdict.txt").write_text(verdict + "\n")
    print(verdict)


if __name__ == "__main__":
    main()
