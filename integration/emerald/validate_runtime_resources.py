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


def validate_heap(directory, labels):
    heap = rows(directory / "runtime-heap.csv")
    if [row["label"] for row in heap] != labels:
        raise ValueError("heap checkpoint sequence differs from gameplay trace")
    previous = None
    for row in heap:
        current, peak, failures, capacity, epoch = (
            int(row[k]) for k in ("current", "peak", "failures", "capacity", "epoch"))
        if not (0 <= current <= peak <= capacity <= 0x40000
                and capacity > 0 and epoch > 0 and failures == 0):
            raise ValueError("invalid heap accounting or allocation failure")
        if previous and (epoch != previous[4] or capacity != previous[3]
                         or peak < previous[1]):
            raise ValueError("heap reset or peak regression during replay")
        previous = current, peak, failures, capacity, epoch
    if previous[1] == 0:
        raise ValueError("no observed native heap allocations")
    return {"heap_peak_bytes": previous[1], "heap_capacity_bytes": previous[3],
            "heap_remaining_at_peak": previous[3] - previous[1]}


def validate_watermark(directory, labels):
    trace = rows(directory / "runtime-watermark.csv")
    if [row["label"] for row in trace] != labels:
        raise ValueError("stack watermark checkpoint sequence mismatch")
    bounds = None
    peak = 0
    for row in trace:
        low, top, used, untouched = (int(row[k]) for k in
                                     ("low", "top", "used", "untouched"))
        if not (0x03000000 <= low <= top - 1024
                and top == 0x03007E40 and low % 4 == 0
                and used % 4 == 0 and untouched % 4 == 0
                and used >= 0 and untouched >= 256
                and used + untouched == top - low):
            raise ValueError("system stack watermark exceeds safe budget")
        if bounds is not None and bounds != (low, top):
            raise ValueError("system stack bounds changed")
        bounds = low, top
        peak = max(peak, used)
    if peak == 0:
        raise ValueError("no native system stack writes observed")
    return {"system_stack_peak_written_bytes": peak,
            "system_stack_capacity_bytes": bounds[1] - bounds[0],
            "system_stack_min_untouched_bytes": bounds[1] - bounds[0] - peak}


def validate_irq(directory, labels):
    trace = rows(directory / "runtime-irq.csv")
    if [row["label"] for row in trace] != labels:
        raise ValueError("IRQ checkpoint sequence mismatch")
    peak = 0
    for row in trace:
        low, top, used, untouched = (int(row[k]) for k in ("low", "top", "used", "untouched"))
        if not ((low, top) == (0x03007E40, 0x03007FA0)
                and used >= 0 and untouched >= 32
                and used % 4 == 0 and untouched % 4 == 0
                and used + untouched == 352):
            raise ValueError("IRQ stack watermark exceeds safe budget")
        peak = max(peak, used)
    if peak == 0:
        raise ValueError("no native IRQ stack writes observed")
    return {"irq_stack_peak_written_bytes": peak,
            "irq_stack_capacity_bytes": 352,
            "irq_stack_min_untouched_bytes": 352 - peak}


def validate(directory, require_heap=False, require_watermark=False, require_irq=False):
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
    report = {"checkpoints": len(labels), "max_sampled_oam_entries": max(occupancy),
            "min_sampled_sp": min(pointers), "max_sampled_sp": max(pointers),
            "limitations": "OAM and stack are checkpoint samples; stack high-water remains unmeasured."}
    if require_heap:
        report.update(validate_heap(directory, labels))
    if require_watermark:
        report.update(validate_watermark(directory, labels))
        report['limitations'] = 'System stack watermark measures overwritten words, not unwritten reservations; IRQ stack and OAM remain checkpoint observations.'
    if require_irq:
        report.update(validate_irq(directory, labels))
        report["limitations"] = "Stack watermarks measure overwritten words, not unwritten reservations; OAM is sampled."
    return report


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    report = validate(directory, require_heap=True, require_watermark=True, require_irq=True)
    (directory / "runtime-resource-verdict.json").write_text(
        json.dumps(report, indent=2) + "\n")
    print("PASS: resource checkpoint integrity")
