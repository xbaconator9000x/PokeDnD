"""Fail closed on missing or inconsistent live resource checkpoint traces."""
import csv
import json
import sys
from pathlib import Path


def rows(path):
    with path.open(newline="") as handle:
        result = list(csv.DictReader(handle))
    labels = [row["label"] for row in result]
    if not labels or len(set(labels)) != len(labels):
        raise ValueError(f"{path.name}: empty or duplicate checkpoints")
    return result


def validate(directory):
    state = rows(directory / "runtime-probe.csv")
    oam = rows(directory / "runtime-oam.csv")
    stack = rows(directory / "runtime-stack.csv")
    labels = [row["label"] for row in state]
    if any([row["label"] for row in trace] != labels for trace in (oam, stack)):
        raise ValueError("resource checkpoint sequence differs from gameplay trace")
    occupancy = []
    pointers = []
    for sprite, frame in zip(oam, stack):
        count, mode, enabled = (int(sprite[k]) for k in
                                ("enabled_oam_entries", "display_mode", "obj_enabled"))
        sp, offset = (int(frame[k]) for k in ("sp", "bytes_above_iwram_base"))
        if not (0 <= count <= 128 and 0 <= mode <= 5 and enabled in (0, 1)):
            raise ValueError("invalid hardware OAM or display state")
        if not (0x03000000 <= sp <= 0x03008000 and sp % 4 == 0
                and offset == sp - 0x03000000):
            raise ValueError("invalid IWRAM stack checkpoint")
        occupancy.append(count)
        pointers.append(sp)
    return {"checkpoints": len(labels), "max_sampled_oam_entries": max(occupancy),
            "min_sampled_sp": min(pointers), "max_sampled_sp": max(pointers),
            "limitations": "Checkpoint observations only; not heap or stack high-water."}


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    report = validate(directory)
    (directory / "runtime-resource-verdict.json").write_text(
        json.dumps(report, indent=2) + "\n")
    print("PASS: resource checkpoint integrity")
