"""Verify persisted native mGBA LCD transitions; not semantic gameplay proof."""
import csv
import hashlib
import re
import sys
from pathlib import Path

EXPECTED = ("05-authored-rocket-facing.png", "24-facing-a-natural-encounter.png")
HEX = re.compile(r"[0-9a-f]{64}\Z")


def validate(directory, outcome):
    if outcome not in ("standard", "victory", "defeat"):
        raise ValueError("unsupported natural replay outcome")
    with (directory / "lcd-transition-manifest.csv").open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["capture", "colors", "sha256"]:
            raise ValueError("invalid LCD manifest schema")
        rows = list(reader)
    terminal = ("25-natural-cancelled.png" if outcome == "standard"
                else f"25-natural-{outcome}-acknowledged.png")
    if len(rows) != 4 or [row["capture"] for row in rows[:3]] != [*EXPECTED, terminal]:
        raise ValueError("LCD transitions missing or out of order")
    if not re.fullmatch(r"26-natural-resumed-(right|left|up|down)\.png", rows[3]["capture"]):
        raise ValueError("missing native field-resumption frame")
    hashes = []
    for row in rows:
        if None in row or set(row) != {"capture", "colors", "sha256"}:
            raise ValueError("malformed LCD manifest row")
        if not row["colors"].isascii() or not row["colors"].isdecimal():
            raise ValueError("noncanonical LCD colour count")
        if not 8 <= int(row["colors"]) <= 38400:
            raise ValueError("blank or invalid LCD colour count")
        if not HEX.fullmatch(row["sha256"]):
            raise ValueError("invalid LCD digest")
        actual = hashlib.sha256((directory / row["capture"]).read_bytes()).hexdigest()
        if actual != row["sha256"]:
            raise ValueError("LCD frame digest mismatch")
        hashes.append(actual)
    if any(a == b for a, b in zip(hashes, hashes[1:])):
        raise ValueError("identical adjacent LCD frames")
    marker = (directory / "NATIVE_AUTHORED_REPLAY_ACCEPTED.txt").read_text(encoding="utf-8")
    if f"{outcome} resolution" not in marker or "field movement" not in marker:
        raise ValueError("missing scenario-specific native replay marker")
    return len(rows)


if __name__ == "__main__":
    try:
        print(f"Validated {validate(Path(sys.argv[1]), sys.argv[2])} persisted LCD frames")
    except (IndexError, OSError, ValueError) as exc:
        raise SystemExit(f"FAIL: native LCD evidence: {exc}")
