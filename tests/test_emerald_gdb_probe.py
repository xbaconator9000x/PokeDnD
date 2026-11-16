"""Mock GDB remote peer verifies authentic four-byte EWRAM sampling mechanics.

No ROM, emulator, saves or Pokémon assets are used in these source tests.
"""
import importlib.util
from pathlib import Path
import socket
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pokednd_mgba_probe", ROOT / "integration/emerald/mgba_ewram_probe.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def packet(text):
    data = text.encode("ascii")
    return b"$" + data + b"#" + ("%02x" % (sum(data) & 0xff)).encode("ascii")


class FakeGDB:
    def __init__(self, sock, memory):
        self.sock = sock
        self.memory = memory
        self.commands = []
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        try:
            while True:
                prefix = self.sock.recv(1)
                if not prefix:
                    return
                if prefix == b"+":
                    continue
                if prefix == b"\x03":
                    self.sock.sendall(packet("S05"))
                    continue
                if prefix != b"$":
                    continue
                payload = bytearray()
                while True:
                    char = self.sock.recv(1)
                    if char == b"#":
                        break
                    if not char:
                        return
                    payload.extend(char)
                self.sock.recv(2)  # GDB checksum from client.
                command = payload.decode("ascii")
                self.commands.append(command)
                self.sock.sendall(b"+")
                if command == "?":
                    self.sock.sendall(packet("S05"))
                elif command.startswith("m"):
                    address, count = command[1:].split(",")
                    addr = int(address, 16)
                    length = int(count, 16)
                    self.sock.sendall(packet(self.memory[addr:addr + length].hex()))
                elif command == "c":
                    continue
                else:
                    self.sock.sendall(packet("E01"))
        except OSError:
            return

    def wait_for_continue(self):
        # The mock debugger runs on another thread: a sent packet is not
        # necessarily processed before snapshot() returns.
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if self.commands.count("c") >= 2:
                return
            time.sleep(0.005)
        raise AssertionError("mock GDB never resumed after snapshot")

    def close(self):
        self.sock.close()
        self.thread.join(timeout=2)


class GDBProbeTests(unittest.TestCase):
    def test_symbol_addresses_are_validated_in_gba_ewram(self):
        elf = Path("/unused.elf")
        values = [0x02000100 + i * 4 for i in range(len(probe.NAMES))]
        output = "".join(f"{addr:08x} B {name}\n"
                         for name, addr in zip(probe.NAMES, values))
        with mock.patch.object(probe.subprocess, "check_output", return_value=output):
            self.assertEqual(probe.symbol_addresses(elf), dict(zip(probe.NAMES, values)))
        with mock.patch.object(probe.subprocess, "check_output",
                               return_value=output.replace("02000108", "03000108")):
            with self.assertRaisesRegex(ValueError, "not aligned GBA EWRAM"):
                probe.symbol_addresses(elf)
        with mock.patch.object(probe.subprocess, "check_output",
                               return_value=output.splitlines()[0]):
            with self.assertRaisesRegex(ValueError, "missing linked"):
                probe.symbol_addresses(elf)

    def test_live_gdb_snapshot_reads_32_bit_values_and_resumes(self):
        a, b = socket.socketpair()
        memory = bytearray(0x300)
        addresses = dict(zip(probe.NAMES, (0x100 + i * 4 for i in range(len(probe.NAMES)))))
        # Keep fixture diagnostic fields in the mock protocol contract. A new
        # EWRAM probe field must be represented here rather than silently
        # passing an uninitialised zero from the fake memory buffer.
        expected_by_name = dict(zip(probe.NAMES, (
            1, 0, 3, 2, 1, 2, 0, 16, 1, 1, 30, 2, 12, 1, 7, 6, 0,
            4, 2, 1,  # fixture attempts, locked observations, last lock
        ), strict=True))
        expected = tuple(expected_by_name[name] for name in probe.NAMES)
        for index, number in enumerate(expected):
            memory[0x100 + index * 4:0x104 + index * 4] = number.to_bytes(4, "little")
        fake = FakeGDB(b, memory)
        fake.start()
        try:
            gdb = probe.RemoteGDB(a)
            gdb.start()
            observed = gdb.snapshot(addresses)
            fake.wait_for_continue()
            self.assertEqual(tuple(observed[key] for key in probe.NAMES), expected)
            self.assertEqual(fake.commands[0:2], ["?", "c"])
            self.assertEqual(fake.commands[-1], "c")
            self.assertEqual([cmd for cmd in fake.commands if cmd.startswith("m")],
                             [f"m{address:x},4" for address in addresses.values()])
        finally:
            a.close()
            fake.close()

    def test_gdb_rejects_malformed_memory_read(self):
        a, b = socket.socketpair()
        fake = FakeGDB(b, bytearray(0x40))
        fake.start()
        try:
            gdb = probe.RemoteGDB(a)
            gdb.start()
            with self.assertRaisesRegex(ValueError, "four-byte EWRAM"):
                gdb.snapshot(dict.fromkeys(probe.NAMES, 0x100))
            fake.wait_for_continue()
            self.assertEqual(fake.commands[-1], "c")
        finally:
            a.close()
            fake.close()


if __name__ == "__main__":
    unittest.main()
