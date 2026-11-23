"""Mutation tests for persisted native LCD replay provenance."""
import csv
import hashlib
import importlib.util
import tempfile
import struct
import zlib
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "integration/emerald/validate_native_lcd.py"
spec = importlib.util.spec_from_file_location("validate_native_lcd", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
validate = module.validate


def png_chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def png_frame(index):
    # Small valid native-size RGB image; distinct frames without proprietary assets.
    pixel = bytes((index, 0, 0))
    scanlines = (b"\x00" + pixel * 240) * 160
    ihdr = struct.pack(">IIBBBBB", 240, 160, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr)
            + png_chunk(b"IDAT", zlib.compress(scanlines))
            + png_chunk(b"IEND", b""))


class NativeLCDTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.names = ["05-authored-rocket-facing.png",
                      "24-facing-a-natural-encounter.png",
                      "25-natural-victory-acknowledged.png",
                      "26-natural-resumed-left.png"]
        with (self.root / "lcd-transition-manifest.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("capture", "colors", "sha256"))
            for i, name in enumerate(self.names):
                data = png_frame(i + 1)
                (self.root / name).write_bytes(data)
                writer.writerow((name, 12 + i, hashlib.sha256(data).hexdigest()))
        (self.root / "NATIVE_AUTHORED_REPLAY_ACCEPTED.txt").write_text(
            "PASS: authored Oldale NPC, ordinary A, victory resolution and field movement")

    def test_valid_manifest(self):
        self.assertEqual(validate(self.root, "victory"), 4)

    def test_tampered_lcd_fails(self):
        (self.root / self.names[1]).write_bytes(b"altered")
        with self.assertRaisesRegex(ValueError, "PNG signature"):
            validate(self.root, "victory")

    def test_wrong_scenario_fails(self):
        with self.assertRaises(ValueError):
            validate(self.root, "defeat")

    def test_missing_native_marker_fails(self):
        (self.root / "NATIVE_AUTHORED_REPLAY_ACCEPTED.txt").unlink()
        with self.assertRaises(FileNotFoundError):
            validate(self.root, "victory")

    def test_duplicate_transition_fails(self):
        manifest = self.root / "lcd-transition-manifest.csv"
        lines = manifest.read_text().splitlines()
        lines[2] = lines[1]
        manifest.write_text("\n".join(lines) + "\n")
        with self.assertRaises(ValueError):
            validate(self.root, "victory")

    def test_arbitrary_bytes_with_matching_digest_fail(self):
        name = self.names[0]
        data = b"not a PNG"
        (self.root / name).write_bytes(data)
        manifest = self.root / "lcd-transition-manifest.csv"
        lines = manifest.read_text().splitlines()
        lines[1] = f"{name},12,{hashlib.sha256(data).hexdigest()}"
        manifest.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(ValueError, "PNG signature"):
            validate(self.root, "victory")

    def test_wrong_lcd_dimensions_fail(self):
        name = self.names[0]
        data = bytearray(png_frame(1))
        data[16:20] = struct.pack(">I", 239)
        data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]) & 0xffffffff)
        data = bytes(data)
        (self.root / name).write_bytes(data)
        manifest = self.root / "lcd-transition-manifest.csv"
        lines = manifest.read_text().splitlines()
        lines[1] = f"{name},12,{hashlib.sha256(data).hexdigest()}"
        manifest.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(ValueError, "dimensions"):
            validate(self.root, "victory")
