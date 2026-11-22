"""Fail closed on missing or inconsistent live resource checkpoint traces."""
import csv
import hashlib
import json
import sys
from pathlib import Path


def rows(path):
    with path.open(newline="") as handle:
        result = list(csv.DictReader(handle))
    # DictReader silently overwrites duplicate header names and places surplus
    # fields under the None key. Neither is valid native replay evidence.
    with path.open(newline="") as handle:
        headers = csv.reader(handle).__next__()
    if (not headers or headers[0] != "label" or len(headers) != len(set(headers))
            or any(not name for name in headers)):
        raise ValueError(f"{path.name}: malformed or duplicate CSV headers")
    if any(None in row or any(value is None or value == "" for value in row.values())
           for row in result):
        raise ValueError(f"{path.name}: incomplete or surplus checkpoint fields")
    labels = [row["label"] for row in result]
    if not labels or len(set(labels)) != len(labels):
        raise ValueError(f"{path.name}: empty or duplicate checkpoints")
    return result


def require_counter_columns(trace, expected, name):
    """Reject silently ignored columns in native counter evidence."""
    if not trace or set(trace[0]) != set(expected):
        raise ValueError(f"{name}: missing or unexpected counter columns")
    for row in trace:
        for field in expected:
            if field == "label":
                continue
            value = row[field]
            if not value.isascii() or not value.isdecimal():
                raise ValueError(f"{name}: noncanonical unsigned counter {field}")


def validate_heap(directory, labels):
    heap = rows(directory / "runtime-heap.csv")
    require_counter_columns(heap, ("label", "current", "peak", "failures",
                                   "capacity", "epoch"), "runtime-heap.csv")
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
    if previous[3] - previous[1] < 256:
        raise ValueError("heap reserve below 256 bytes")
    if previous[1] == 0:
        raise ValueError("no observed native heap allocations")
    return {"heap_peak_bytes": previous[1], "heap_capacity_bytes": previous[3],
            "heap_remaining_at_peak": previous[3] - previous[1]}


def validate_stack_samples(directory, labels):
    """Admit only linker-bounded native SP samples; never infer watermark writes."""
    trace = rows(directory / "runtime-stack-samples.csv")
    require_counter_columns(trace, ("label", "low", "top", "peak", "samples", "invalid"),
                            "runtime-stack-samples.csv")
    if [row["label"] for row in trace] != labels:
        raise ValueError("native stack sampler checkpoint sequence mismatch")
    previous_peak = previous_count = None
    bounds = None
    for row in trace:
        low, top, peak, count, invalid = (int(row[k]) for k in
            ("low", "top", "peak", "samples", "invalid"))
        if not (0x03000000 <= low <= top - 1024 and top == 0x03007E40
                and low % 4 == 0 and peak % 4 == 0
                and 0 < peak <= top - low - 256 and 0 < count < 0xFFFFFFFF
                and invalid == 0):
            raise ValueError("invalid or over-budget native stack sample")
        if bounds is not None and bounds != (low, top):
            raise ValueError("native stack sampler linker bounds changed")
        if previous_peak is not None and (peak < previous_peak or count < previous_count):
            raise ValueError("native stack sampler counters regressed")
        bounds = (low, top)
        previous_peak, previous_count = peak, count
    return {"system_stack_peak_sampled_bytes": previous_peak,
            "system_stack_sample_count": previous_count,
            "system_stack_capacity_bytes": bounds[1] - bounds[0],
            "system_stack_sampled_reserve_bytes": bounds[1] - bounds[0] - previous_peak}


def validate_watermark(directory, labels):
    trace = rows(directory / "runtime-watermark.csv")
    require_counter_columns(trace, ("label", "low", "top", "used", "untouched"),
                            "runtime-watermark.csv")
    if [row["label"] for row in trace] != labels:
        raise ValueError("stack watermark checkpoint sequence mismatch")
    bounds = None
    peak = 0
    previous_used = None
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
        if previous_used is not None and used < previous_used:
            raise ValueError("system stack watermark regressed between checkpoints")
        previous_used = used
        bounds = low, top
        peak = max(peak, used)
    if peak == 0:
        raise ValueError("no native system stack writes observed")
    return {"system_stack_peak_written_bytes": peak,
            "system_stack_capacity_bytes": bounds[1] - bounds[0],
            "system_stack_min_untouched_bytes": bounds[1] - bounds[0] - peak}


def validate_irq(directory, labels):
    trace = rows(directory / "runtime-irq.csv")
    require_counter_columns(trace, ("label", "low", "top", "used", "untouched"),
                            "runtime-irq.csv")
    if [row["label"] for row in trace] != labels:
        raise ValueError("IRQ checkpoint sequence mismatch")
    peak = 0
    previous_used = None
    for row in trace:
        low, top, used, untouched = (int(row[k]) for k in ("low", "top", "used", "untouched"))
        if not ((low, top) == (0x03007E40, 0x03007FA0)
                and used >= 0 and untouched >= 32
                and used % 4 == 0 and untouched % 4 == 0
                and used + untouched == 352):
            raise ValueError("IRQ stack watermark exceeds safe budget")
        if previous_used is not None and used < previous_used:
            raise ValueError("IRQ stack watermark regressed between checkpoints")
        previous_used = used
        peak = max(peak, used)
    if peak == 0:
        raise ValueError("no native IRQ stack writes observed")
    return {"irq_stack_peak_written_bytes": peak,
            "irq_stack_capacity_bytes": 352,
            "irq_stack_min_untouched_bytes": 352 - peak}


def validate_video(directory, labels, oam):
    trace = rows(directory / "runtime-video.csv")
    require_counter_columns(trace, ("label", "dispcnt", "dispstat", "vcount",
                                   "bg0cnt", "bg1cnt", "bg2cnt", "bg3cnt"),
                            "runtime-video.csv")
    if [row["label"] for row in trace] != labels:
        raise ValueError("video checkpoint sequence mismatch")
    layouts = []
    peak_screen_bytes = 0
    peak_char_bytes = 0
    peak_union_bytes = 0
    for row, sprite in zip(trace, oam):
        control, status, line, *backgrounds = (int(row[k]) for k in
            ("dispcnt", "dispstat", "vcount", "bg0cnt", "bg1cnt", "bg2cnt", "bg3cnt"))
        if not all(0 <= value <= 65535 for value in (control, status, *backgrounds)):
            raise ValueError("invalid video register width")
        if not 0 <= line < 228:
            raise ValueError("invalid GBA scanline")
        if control & 7 != int(sprite["display_mode"]) or bool(control & 0x1000) != bool(int(sprite["obj_enabled"])):
            raise ValueError("inconsistent display control snapshots")
        # This accounting models text BGs in mode 0 only. Modes 1-5 use
        # affine/bitmap layouts: silently treating their enabled backgrounds
        # as zero occupancy would falsely certify a resource budget.
        if control & 7 != 0:
            # Bitmap modes 3-5 consume framebuffer VRAM even when BG enable
            # bits are clear. Affine modes also need separate allocation rules.
            # Never certify an unmodelled mode as zero-byte occupancy.
            raise ValueError("unsupported GBA display mode for VRAM budget")
        # Text BG screen blocks occupy 2 KiB apiece. Character blocks
        # identify bases only; these are not allocator occupancy measurements.
        if control & 7 == 0:
            occupied = set()
            character = set()
            for index, bg in enumerate(backgrounds):
                if control & (0x100 << index):
                    base = (bg >> 8) & 31
                    blocks = (1, 2, 2, 4)[bg >> 14]
                    if base + blocks > 32:
                        raise ValueError("text BG screen map exceeds BG VRAM")
                    occupied.update(range(base, base + blocks))
                    char_base = ((bg >> 2) & 3) * 8
                    character.update(range(char_base, char_base + 8))
                    layouts.append({"bg": index, "screen_base": base,
                                    "screen_blocks": blocks, "char_base": (bg >> 2) & 3})
            peak_screen_bytes = max(peak_screen_bytes, len(occupied) * 2048)
            peak_char_bytes = max(peak_char_bytes, len(character) * 2048)
            peak_union_bytes = max(peak_union_bytes, len(character | occupied) * 2048)
    return {"peak_sampled_text_char_base_span_bytes": peak_char_bytes,
            "peak_sampled_text_base_union_bytes": peak_union_bytes,
            "peak_sampled_text_screen_bytes": peak_screen_bytes, "video_checkpoints": len(trace), "text_bg_layouts": layouts,
            "video_limitations": "Register snapshots only; character spans represent nominal 16 KiB base blocks, not actual tile usage or allocator ownership; no VBlank duration."}



def validate_vblank(directory, labels):
    """Validate measured VBlank timer deltas, not sampled DISPSTAT flags.

    This trace is admissible only when native instrumentation provides timer
    ticks around the actual VBlank work. A scanline sample is insufficient.
    """
    trace = rows(directory / "runtime-vblank.csv")
    require_counter_columns(trace, ("label", "elapsed_ticks", "peak_ticks",
                                    "budget_ticks", "epoch"), "runtime-vblank.csv")
    if [row["label"] for row in trace] != labels:
        raise ValueError("VBlank checkpoint sequence mismatch")
    peak = 0
    previous_peak = None
    for row in trace:
        ticks = int(row["elapsed_ticks"])
        high = int(row["peak_ticks"])
        budget = int(row["budget_ticks"])
        epoch = int(row["epoch"])
        if not (epoch > 0 and budget > 0 and 0 <= ticks <= high <= budget):
            raise ValueError("VBlank timer budget exceeded or invalid")
        if previous_peak is not None and (high < previous_peak[0]
                                          or epoch != previous_peak[1]
                                          or budget != previous_peak[2]):
            raise ValueError("VBlank timer epoch or high-water regression")
        previous_peak = (high, epoch, budget)
        peak = max(peak, high)
    if peak == 0:
        raise ValueError("no native VBlank timer activity measured")
    return {"vblank_peak_timer_ticks": peak,
            "vblank_timer_budget_ticks": previous_peak[2],
            "vblank_timer_remaining_ticks": previous_peak[2] - peak}


def validate(directory, require_heap=False, require_stack_samples=False, require_watermark=False, require_irq=False, require_video=False, require_vblank=False):
    state = rows(directory / "runtime-probe.csv")
    oam = rows(directory / "runtime-oam.csv")
    stack = rows(directory / "runtime-stack.csv")
    # Baseline traces are just as authoritative as optional resource traces.
    # Reject unexpected columns and malformed counters before interpreting
    # hardware snapshots; otherwise a changed collector schema can pass silently.
    # The live collector emits the complete native encounter register set.
    # A two-column "state" fixture must not masquerade as genuine replay.
    require_counter_columns(state, (
        "label", "trigger_count", "start_failure", "milestones",
        "diagnostic_state", "post_cancel_moves", "last_outcome",
        "last_human_hp", "last_enemy_hp", "outcome_acks",
        "impact_starts", "impact_frames", "dash_count", "last_dash_movement",
        "natural_encounter_count", "last_natural_local_id",
        "natural_cleanup_status", "replay_fixture_status",
        "replay_fixture_lock_count", "replay_natural_lock_count",
        "replay_fixture_attempt_count"), "runtime-probe.csv")
    require_counter_columns(oam, ("label", "enabled_oam_entries",
                                  "display_mode", "obj_enabled"), "runtime-oam.csv")
    require_counter_columns(stack, ("label", "sp", "bytes_above_iwram_base"),
                            "runtime-stack.csv")
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
    if require_stack_samples:
        report.update(validate_stack_samples(directory, labels))
        report["limitations"] = "Read-only system stack samples; unsampled call paths and IRQ high-water remain unknown."
    if require_watermark:
        report.update(validate_watermark(directory, labels))
        report['limitations'] = 'System stack watermark measures overwritten words, not unwritten reservations; IRQ stack and OAM remain checkpoint observations.'
    if require_irq:
        report.update(validate_irq(directory, labels))
        report["limitations"] = "Stack watermarks measure overwritten words, not unwritten reservations; OAM is sampled."
    if require_video:
        report.update(validate_video(directory, labels, oam))
    if require_vblank:
        report.update(validate_vblank(directory, labels))
    return report


def verify_verdict(directory):
    """Recheck a persisted verdict against every required replay input.

    A JSON verdict is not a transferable acceptance certificate: callers must
    verify its input digests and explicit measurement limitations before use.
    """
    verdict_path = directory / "runtime-resource-verdict.json"
    report = json.loads(verdict_path.read_text())
    expected = {
        "runtime-probe.csv", "runtime-oam.csv", "runtime-stack.csv",
        "runtime-heap.csv", "runtime-stack-samples.csv", "runtime-video.csv"
    }
    if report.get("vblank_acceptance") == "measured":
        expected.add("runtime-vblank.csv")
    elif report.get("vblank_acceptance") != "not_measured":
        raise ValueError("unrecognized VBlank acceptance status")
    if report.get("stack_acceptance") != "sampled_only_not_high_water" or (
            report.get("irq_stack_acceptance") != "not_measured"):
        raise ValueError("unrecognized stack measurement status")
    digests = report.get("evidence_sha256")
    if not isinstance(digests, dict) or set(digests) != expected:
        raise ValueError("verdict evidence manifest missing or incomplete")
    for name in sorted(expected):
        actual = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        if not isinstance(digests[name], str) or len(digests[name]) != 64 or (
                actual != digests[name]):
            raise ValueError(f"stale or modified resource evidence: {name}")
    # Hashes alone are insufficient: re-run every budget and schema check.
    verified = validate(directory, require_heap=True, require_stack_samples=True,
                        require_video=True, require_vblank="runtime-vblank.csv" in expected)
    for key, value in verified.items():
        if report.get(key) != value:
            raise ValueError(f"stale or inconsistent resource verdict: {key}")
    return report


def main(argv):
    if not argv or argv[1:].count("--require-vblank") > 1 or set(argv[1:]) - {"--require-vblank"}:
        raise SystemExit("usage: validate_runtime_resources.py DIR [--require-vblank]")
    directory = Path(argv[0])
    require_vblank = "--require-vblank" in argv[1:]
    # Never leave a successful verdict from an earlier replay when the current
    # trace is missing, malformed, or over budget. A failed run must fail closed.
    verdict_path = directory / "runtime-resource-verdict.json"
    verdict_path.unlink(missing_ok=True)
    report = validate(directory, require_heap=True, require_stack_samples=True,
                      require_watermark=False, require_irq=False, require_video=True,
                      require_vblank=require_vblank)
    report["vblank_acceptance"] = "measured" if require_vblank else "not_measured"
    report["stack_acceptance"] = "sampled_only_not_high_water"
    report["irq_stack_acceptance"] = "not_measured"
    # Bind the verdict to the exact replay inputs; do not mistake a stale
    # verdict for acceptance of subsequently replaced or edited CSV traces.
    evidence_names = ("runtime-probe.csv", "runtime-oam.csv", "runtime-stack.csv",
                      "runtime-heap.csv", "runtime-stack-samples.csv", "runtime-video.csv")
    if require_vblank:
        evidence_names += ("runtime-vblank.csv",)
    report["evidence_sha256"] = {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in evidence_names
    }
    verdict_path.write_text(
        json.dumps(report, indent=2) + "\n")
    print("PASS: resource checkpoint integrity")
    return report


if __name__ == "__main__":
    main(sys.argv[1:])
