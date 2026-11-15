"""Regression for fragmented TCP reads of the GDB packet checksum."""
import socket
import threading
import unittest

from integration.emerald.mgba_ewram_probe import RemoteGDB


class FragmentedSocket:
    def __init__(self, fragments):
        self.fragments = list(fragments)
        self.sent = []

    def settimeout(self, timeout):
        pass

    def recv(self, count):
        if not self.fragments:
            return b""
        chunk = self.fragments.pop(0)
        assert len(chunk) <= count
        return chunk

    def sendall(self, data):
        self.sent.append(data)


class ChecksumTests(unittest.TestCase):
    def test_fragmented_checksum_is_accepted(self):
        sock = FragmentedSocket([b"$", b"S", b"0", b"5", b"#", b"b", b"8"])
        self.assertEqual(RemoteGDB(sock).response(), "S05")
        self.assertEqual(sock.sent, [b"+"])

    def test_truncated_checksum_fails_closed(self):
        sock = FragmentedSocket([b"$", b"S", b"0", b"5", b"#", b"b"])
        with self.assertRaises(ConnectionError):
            RemoteGDB(sock).response()
        self.assertEqual(sock.sent, [])


if __name__ == "__main__":
    unittest.main()
