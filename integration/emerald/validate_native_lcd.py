"""Verify persisted native mGBA LCD transitions; not semantic gameplay proof."""
import csv
import hashlib
import re
import struct
import zlib
import sys
from pathlib import Path

EXPECTED = ("05-authored-rocket-facing.png", "24-facing-a-natural-encounter.png")
HEX = re.compile(r"[0-9a-f]{64}\Z")


def verify_png(data):
    """Require a structurally valid, complete 240x160 PNG, not arbitrary hashed bytes."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid PNG signature")
    offset = 8
    seen_ihdr = False
    seen_idat = False
    seen_iend = False
    idat_parts = []
    depth = color = None
    while offset < len(data):
        if len(data) - offset < 12:
            raise ValueError("truncated PNG chunk")
        size = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + size
        if end > len(data):
            raise ValueError("truncated PNG payload")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        crc = struct.unpack_from(">I", data, offset + 8 + size)[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError("PNG chunk CRC mismatch")
        if not seen_ihdr:
            if kind != b"IHDR" or size != 13:
                raise ValueError("missing PNG IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if (width, height) != (240, 160) or depth not in (8, 16) or color not in (0, 2, 3, 4, 6) or compression or filtering or interlace:
                raise ValueError("invalid native LCD PNG dimensions or format")
            seen_ihdr = True
        elif kind == b"IHDR":
            raise ValueError("duplicate PNG IHDR")
        if kind == b"IDAT":
            seen_idat = True
            idat_parts.append(payload)
        if kind == b"IEND":
            if size or not seen_idat or end != len(data):
                raise ValueError("invalid PNG ending")
            seen_iend = True
            break
        offset = end
    if not seen_iend:
        raise ValueError("missing PNG IEND")

    # CRC-verified chunks alone do not prove a decodable screenshot.
    # Bound inflation to the exact GBA LCD scanline footprint.
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    stride = (240 * channels * depth + 7) // 8
    expected = 160 * (stride + 1)
    inflater = zlib.decompressobj()
    try:
        pixels = inflater.decompress(b"".join(idat_parts), expected + 1)
        pixels += inflater.flush(expected + 1 - len(pixels))
    except zlib.error as exc:
        raise ValueError("invalid PNG pixel stream") from exc
    if (len(pixels) != expected or not inflater.eof or
            inflater.unused_data or inflater.unconsumed_tail):
        raise ValueError("invalid PNG decoded pixel length or trailing data")
    if any(pixels[y * (stride + 1)] > 4 for y in range(160)):
        raise ValueError("invalid PNG scanline filter")



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
        data = (directory / row["capture"]).read_bytes()
        verify_png(data)
        actual = hashlib.sha256(data).hexdigest()
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
