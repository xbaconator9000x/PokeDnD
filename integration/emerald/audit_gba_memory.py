#!/usr/bin/env python3
"""Audit native GBA ELF memory allocation without publishing the ROM.

Reads GNU arm-none-eabi-readelf section headers and nm symbol sizes.
The section audit measures linked virtual memory, not peak heap/stack,
runtime VRAM/OAM, or hardware performance; those need separate probes.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

REGIONS = {
    "EWRAM": (0x02000000, 0x02040000),
    "IWRAM": (0x03000000, 0x03008000),
    "VRAM": (0x06000000, 0x06018000),
    "OAM": (0x07000000, 0x07000400),
}
SECTION = re.compile(
    r"^\s*\[\s*\d+\]\s+(\S+)\s+\S+\s+([0-9a-fA-F]+)\s+"
    r"[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+\S+\s+(\S+)"
)
# Runtime allocator counters must survive linking as addressable EWRAM words.
# Their existence does not establish that the counters were sampled in mGBA.
REQUIRED_HEAP_COUNTERS = (
    "gPokeDnDHeapCurrent", "gPokeDnDHeapPeak",
    "gPokeDnDHeapFailures", "gPokeDnDHeapCapacity", "gPokeDnDHeapEpoch",
)
REQUIRED_STACK_COUNTERS = (
    "gPokeDnDStackSamplePeak", "gPokeDnDStackSampleCount",
    "gPokeDnDStackSampleInvalid", "gPokeDnDStackSampleMinFree",
    "gPokeDnDIrqStackCapacity", "gPokeDnDIrqStackBoundsInvalid",
)
SYMBOL = re.compile(r"^([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([A-Za-z])\s+(\S+)$")


def measure_sections(output):
    intervals = {name: [] for name in REGIONS}
    violations = []
    for line in output.splitlines():
        match = SECTION.match(line)
        if not match:
            continue
        name, address, size, flags = match.groups()
        start, size = int(address, 16), int(size, 16)
        if "A" not in flags or not size:
            continue
        end = start + size
        for region, (low, high) in REGIONS.items():
            if low <= start < high or low < end <= high or (start < low and end > high):
                if start < low or end > high:
                    violations.append(f"{name} exceeds {region}: {start:#x}..{end:#x}")
                else:
                    intervals[region].append((start, end, name))
    totals = {}
    for region, spans in intervals.items():
        spans.sort()
        total = 0
        last_end = None
        for start, end, name in spans:
            if last_end is not None and start < last_end:
                violations.append(f"{region} overlapping allocated section: {name}")
            total += end - start
            last_end = max(last_end or 0, end)
        totals[region] = {"linked_bytes": total, "capacity_bytes": REGIONS[region][1] - REGIONS[region][0],
                          "sections": [{"name": name, "start": start, "bytes": end-start}
                                       for start, end, name in spans]}
    return totals, violations


def measure_symbols(output):
    symbols = []
    for line in output.splitlines():
        match = SYMBOL.match(line.strip())
        if not match:
            continue
        address, size, kind, name = match.groups()
        address, size = int(address, 16), int(size, 16)
        if not size or not (name.startswith(("gPokeDnD", "PokeDnD_", "d20_"))
                            or name in ("sBattle", "sProjection", "sUnits")
                            or name.startswith(("sFrozenByD20", "sFrozenLocalId"))):
            continue
        for region, (low, high) in REGIONS.items():
            if low <= address < high:
                symbols.append({"name": name, "region": region, "address": address,
                                "bytes": size, "type": kind})
                break
    return sorted(symbols, key=lambda s: (s["region"], s["address"], s["name"]))


def audit(section_text, symbol_text):
    regions, violations = measure_sections(section_text)
    symbols = measure_symbols(symbol_text)
    if not any(s["name"] == "sBattle" for s in symbols):
        violations.append("native sBattle EWRAM symbol missing")
    if not any(s["name"] == "gPokeDnDDiagnosticState" for s in symbols):
        violations.append("native diagnostic register missing")
    by_name = {}
    for symbol in symbols:
        by_name.setdefault(symbol["name"], []).append(symbol)
    for name in REQUIRED_HEAP_COUNTERS + REQUIRED_STACK_COUNTERS:
        matches = by_name.get(name, [])
        if len(matches) != 1:
            violations.append(f"required native resource counter {name}: expected one, found {len(matches)}")
        elif matches[0]["region"] != "EWRAM" or matches[0]["bytes"] != 4:
            violations.append(f"required native resource counter {name}: expected one 4-byte EWRAM word")
    return {"regions": regions, "pokednd_ram_symbols": symbols,
            "pokednd_ram_symbol_bytes": sum(s["bytes"] for s in symbols),
            "limitations": "Linked section allocation only; excludes runtime heap/stack peaks, sprite/OAM and VRAM use.",
            "violations": violations, "pass": not violations}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("elf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sections = subprocess.check_output(["arm-none-eabi-readelf", "-SW", str(args.elf)], text=True)
    symbols = subprocess.check_output(["arm-none-eabi-nm", "-S", "--defined-only", str(args.elf)], text=True)
    report = audit(sections, symbols)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for name, region in report["regions"].items():
        print(f"{name}: {region['linked_bytes']}/{region['capacity_bytes']} linked bytes")
    print(f"PokéDND named RAM symbols: {report['pokednd_ram_symbol_bytes']} bytes")
    for issue in report["violations"]:
        print("FAIL:", issue)
    if report["violations"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
