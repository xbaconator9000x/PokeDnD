#!/usr/bin/env python3
"""Read native PokeDnD EWRAM symbols from a *running* mGBA GDB stub.

A GUI screenshot or a linked ELF is not a runtime memory observation.
Only run on a local CI-owned emulator; the debugger listens on loopback.
"""
import argparse
import csv
from pathlib import Path
import re
import socket
import subprocess
import time

NAMES = (
    "gPokeDnDTriggerCount",
    "gPokeDnDStartFailure",
    "gPokeDnDMilestones",
    "gPokeDnDDiagnosticState",
    "gPokeDnDPostCancelMoves",
    "gPokeDnDLastOutcome",
    "gPokeDnDLastHumanHp",
    "gPokeDnDLastEnemyHp",
    "gPokeDnDOutcomeAcks",
    "gPokeDnDImpactStarts",
    "gPokeDnDImpactFrames",
    "gPokeDnDDashCount",
    "gPokeDnDLastDashMovement",
    "gPokeDnDNaturalEncounterCount",
    "gPokeDnDLastNaturalLocalId",
    "gPokeDnDNaturalCleanupStatus",
    "gPokeDnDReplayFixtureStatus",
    "gPokeDnDReplayLockObservations",
    "gPokeDnDReplayNaturalLockObservations",
    "gPokeDnDReplayFixtureAttemptCount",
)
FIELDS = ("label", "trigger_count", "start_failure", "milestones",
          "diagnostic_state", "post_cancel_moves",
          "last_outcome", "last_human_hp", "last_enemy_hp",
          "outcome_acks", "impact_starts", "impact_frames",
          "dash_count", "last_dash_movement",
          "natural_encounter_count", "last_natural_local_id",
          "natural_cleanup_status",
          "replay_fixture_status",
          "replay_fixture_lock_count", "replay_natural_lock_count",
          "replay_fixture_attempt_count")


HEAP_NAMES = ("gPokeDnDHeapCurrent", "gPokeDnDHeapPeak",
              "gPokeDnDHeapFailures", "gPokeDnDHeapCapacity", "gPokeDnDHeapEpoch")


def symbol_addresses(elf: Path, nm: str = "arm-none-eabi-nm", names=NAMES):
    output = subprocess.check_output([nm, "-n", str(elf)], text=True)
    addresses = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] in names:
            address = int(parts[0], 16)
            if not 0x02000000 <= address <= 0x0203FFFC or address % 4:
                raise ValueError("probe symbol is not aligned GBA EWRAM: " + parts[2])
            addresses[parts[2]] = address
    missing = set(names) - set(addresses)
    if missing:
        raise ValueError("missing linked EWRAM probe symbols: " + ", ".join(sorted(missing)))
    return addresses


def stack_bounds(elf, nm):
    names = ("__pokednd_stack_low", "__pokednd_stack_top")
    found = {}
    for line in subprocess.check_output([nm, "-n", str(elf)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] in names:
            found[parts[2]] = int(parts[0], 16)
    low, top = (found.get(name, 0) for name in names)
    if not (0x03000000 <= low <= top - 1024
            and top == 0x03007E40 and low % 4 == 0):
        raise ValueError("invalid linked system stack bounds")
    return low, top


def watermark_usage(data):
    if not data or len(data) % 4:
        raise ValueError("invalid stack watermark length")
    marker = bytes.fromhex("c33c5aa5")
    untouched = 0
    while untouched < len(data) and data[untouched:untouched+4] == marker:
        untouched += 4
    return len(data) - untouched, untouched


class RemoteGDB:
    def __init__(self, sock):
        self.sock = sock
        self.sock.settimeout(8)

    def send(self, command):
        data = command.encode("ascii")
        checksum = sum(data) % 256
        self.sock.sendall(b"$" + data + b"#" + ("%02x" % checksum).encode("ascii"))

    def response(self):
        while True:
            first = self.sock.recv(1)
            if not first:
                raise ConnectionError("mGBA debugger closed")
            if first in (b"+", b"-"):
                if first == b"-":
                    raise ConnectionError("mGBA rejected GDB packet checksum")
                continue
            if first != b"$":
                continue
            data = bytearray()
            while True:
                char = self.sock.recv(1)
                if not char:
                    raise ConnectionError("mGBA closed in GDB response")
                if char == b"#":
                    break
                data.extend(char)
            checksum = bytearray()
            while len(checksum) < 2:
                fragment = self.sock.recv(2 - len(checksum))
                if not fragment:
                    raise ConnectionError("mGBA closed during GDB checksum")
                checksum.extend(fragment)
            expected = sum(data) % 256
            if checksum.lower() != ("%02x" % expected).encode("ascii"):
                self.sock.sendall(b"-")
                raise ValueError("invalid mGBA GDB packet checksum")
            self.sock.sendall(b"+")
            value = data.decode("ascii")
            if value.startswith("O") and len(value) > 1 and re.fullmatch("[0-9a-fA-F]+", value[1:]):
                continue  # Optional GDB console output before a response.
            return value

    def start(self):
        self.send("?")
        state = self.response()
        if not state.startswith(("S", "T")):
            raise ValueError("expected debugger stop reason, received " + state[:24])
        self.send("c")

    def read_bus(self, address, size):
        self.send("m%x,%x" % (address, size))
        value = self.response()
        if len(value) != size * 2 or not re.fullmatch("[0-9a-fA-F]+", value):
            raise ValueError("invalid resource bus read at %08x" % address)
        return bytes.fromhex(value)

    def stack_snapshot(self):
        # ARM GDB register packet begins with r0-r15, each little-endian u32.
        # This is instantaneous SP, not a stack high-water measurement.
        self.send("g")
        value = self.response()
        if len(value) < 128 or not re.fullmatch("[0-9a-fA-F]+", value) or len(value) % 2:
            raise ValueError("invalid ARM register packet")
        sp = int.from_bytes(bytes.fromhex(value[104:112]), "little")
        if not 0x03000000 <= sp <= 0x03008000 or sp % 4:
            raise ValueError("unaligned or out-of-IWRAM stack pointer: %08x" % sp)
        return sp, sp - 0x03000000

    def resource_snapshot(self):
        # Read hardware OAM, not the engine's shadow sprite array.
        oam = b"".join(self.read_bus(0x07000000 + offset, 64)
                       for offset in range(0, 1024, 64))
        enabled = sum((int.from_bytes(oam[i:i+2], "little") & 0x300) != 0x200
                      for i in range(0, 1024, 8))
        display = int.from_bytes(self.read_bus(0x04000000, 2), "little")
        return (enabled, display & 7, int(bool(display & 0x1000)))

    def snapshot(self, addresses, resources=False, bounds=None):
        self.sock.sendall(b"\x03")
        reason = self.response()
        if not reason.startswith(("S", "T")):
            raise ValueError("mGBA did not stop for EWRAM snapshot: " + reason[:24])
        values = {}
        try:
            for name in addresses:
                self.send("m%x,4" % addresses[name])
                value = self.response()
                if not re.fullmatch("[0-9a-fA-F]{8}", value):
                    raise ValueError("invalid four-byte EWRAM value for " + name + ": " + value[:24])
                values[name] = int.from_bytes(bytes.fromhex(value), "little")
            if resources:
                values["resources"] = self.resource_snapshot()
                values["stack"] = self.stack_snapshot()
                if bounds is not None:
                    low, top = bounds
                    data = b"".join(self.read_bus(addr, min(256, top-addr))
                                    for addr in range(low, top, 256))
                    values["watermark"] = (low, top, *watermark_usage(data))
        finally:
            self.send("c")
        return values


def connect_gdb(port, timeout=25):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=2)
        except OSError as error:
            last_error = error
            time.sleep(0.2)
    raise ConnectionError("mGBA -g debugger port unavailable") from last_error


def serve(elf, out, port, nm):
    out.mkdir(parents=True, exist_ok=True)
    addresses = symbol_addresses(elf, nm, NAMES + HEAP_NAMES)
    bounds = stack_bounds(elf, nm)
    socket_path = out / "ewram-probe.sock"
    csv_path = out / "runtime-probe.csv"
    ready_path = out / "ewram-probe-ready.txt"
    if socket_path.exists():
        socket_path.unlink()
    with connect_gdb(port) as remote, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        gdb = RemoteGDB(remote)
        gdb.start()
        server.bind(str(socket_path))
        server.listen(2)
        csv_path.write_text(",".join(FIELDS) + "\n")
        (out / "runtime-oam.csv").write_text("label,enabled_oam_entries,display_mode,obj_enabled\n")
        (out / "runtime-stack.csv").write_text("label,sp,bytes_above_iwram_base\n")
        (out / "runtime-heap.csv").write_text("label,current,peak,failures,capacity,epoch\n")
        (out / "runtime-watermark.csv").write_text("label,low,top,used,untouched\\n".replace("\\n", "\n"))
        ready_path.write_text("mGBA GDB connected and native EWRAM symbols validated\n")
        try:
            while True:
                with server.accept()[0] as client:
                    client.settimeout(12)
                    label = client.recv(128).decode("ascii").strip()
                    if label == "quit":
                        client.sendall(b"OK quit\n")
                        return
                    if not re.fullmatch("[a-z][a-z0-9_-]{0,40}", label):
                        client.sendall(b"ERROR invalid sample label\n")
                        continue
                    try:
                        values = gdb.snapshot(addresses, resources=True, bounds=bounds)
                        with (out / "runtime-oam.csv").open("a", newline="") as resource_file:
                            csv.writer(resource_file).writerow([label, *values["resources"]])
                        with (out / "runtime-stack.csv").open("a", newline="") as stack_file:
                            csv.writer(stack_file).writerow([label, *values["stack"]])
                        with (out / "runtime-heap.csv").open("a", newline="") as heap_file:
                            csv.writer(heap_file).writerow([label, *[values[name] for name in HEAP_NAMES]])
                        with (out / "runtime-watermark.csv").open("a", newline="") as watermark_file:
                            csv.writer(watermark_file).writerow([label, *values["watermark"]])
                        row = [label] + [values[name] for name in NAMES]
                        with csv_path.open("a", newline="") as file:
                            csv.writer(file).writerow(row)
                        client.sendall(("OK " + label + " " +
                                        " ".join(str(v) for v in row[1:]) + "\n").encode("ascii"))
                    except (ValueError, OSError, ConnectionError) as error:
                        client.sendall(("ERROR " + str(error) + "\n").encode("ascii"))
                        raise
        finally:
            ready_path.unlink(missing_ok=True)
            socket_path.unlink(missing_ok=True)


def sample(out, label):
    path = out / "ewram-probe.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(15)
        client.connect(str(path))
        client.sendall(label.encode("ascii"))
        reply = client.recv(1024).decode("ascii").strip()
    print(reply)
    if not reply.startswith("OK "):
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    srv = sub.add_parser("serve")
    srv.add_argument("--elf", type=Path, required=True)
    srv.add_argument("--out", type=Path, required=True)
    srv.add_argument("--port", type=int, default=2345)
    srv.add_argument("--nm", default="arm-none-eabi-nm")
    take = sub.add_parser("sample")
    take.add_argument("--out", type=Path, required=True)
    take.add_argument("--label", required=True)
    args = parser.parse_args()
    if args.action == "serve":
        serve(args.elf, args.out, args.port, args.nm)
    else:
        sample(args.out, args.label)


if __name__ == "__main__":
    main()
