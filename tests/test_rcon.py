"""
Unit tests for the RCON protocol client (isrt/rcon.py).

All tests use mock sockets so no live server is required.
"""

import socket
import struct
import threading
from unittest.mock import MagicMock, patch

import pytest

from isrt.rcon import (
    AUTH_FAILURE_ID,
    PACKET_TYPE_AUTH,
    PACKET_TYPE_AUTH_RESPONSE,
    PACKET_TYPE_COMMAND,
    PACKET_TYPE_RESPONSE,
    AuthenticationError,
    ConnectionError,
    RCONClient,
    RCONError,
    RCONPacket,
)

# ---------------------------------------------------------------------------
# RCONPacket encode / decode
# ---------------------------------------------------------------------------


class TestRCONPacket:
    def test_encode_decode_roundtrip(self):
        packet = RCONPacket(42, PACKET_TYPE_COMMAND, "AdminListPlayers")
        encoded = packet.encode()
        decoded = RCONPacket.decode(encoded)
        assert decoded.id == 42
        assert decoded.type == PACKET_TYPE_COMMAND
        assert decoded.body == "AdminListPlayers"

    def test_encode_empty_body(self):
        packet = RCONPacket(1, PACKET_TYPE_RESPONSE, "")
        encoded = packet.encode()
        decoded = RCONPacket.decode(encoded)
        assert decoded.body == ""

    def test_encode_unicode_body(self):
        body = "Héllo Wörld"
        packet = RCONPacket(7, PACKET_TYPE_COMMAND, body)
        decoded = RCONPacket.decode(packet.encode())
        assert decoded.body == body

    def test_encode_size_field(self):
        """Size field must equal len(id) + len(type) + len(body+NUL) + len(NUL)."""
        body = "test"
        packet = RCONPacket(1, PACKET_TYPE_COMMAND, body)
        encoded = packet.encode()
        size = struct.unpack("<i", encoded[:4])[0]
        # 4 (id) + 4 (type) + len(body) + 1 (body NUL) + 1 (trailing NUL)
        assert size == 4 + 4 + len(body.encode()) + 2

    def test_decode_too_short_raises(self):
        with pytest.raises(RCONError):
            RCONPacket.decode(b"\x00" * 5)

    def test_decode_incomplete_raises(self):
        """Passing fewer bytes than size field promises should raise."""
        size_bytes = struct.pack("<i", 100)
        with pytest.raises(RCONError):
            RCONPacket.decode(size_bytes + b"\x00" * 4)


# ---------------------------------------------------------------------------
# Helpers for building raw server packets
# ---------------------------------------------------------------------------


def _make_raw_packet(packet_id: int, packet_type: int, body: str) -> bytes:
    return RCONPacket(packet_id, packet_type, body).encode()


def _make_socket_with_data(*packets: bytes):
    """Return a MagicMock socket whose recv returns the given packet bytes."""
    data = b"".join(packets)
    index = [0]

    def fake_recv(n):
        chunk = data[index[0] : index[0] + n]
        index[0] += n
        return chunk

    sock = MagicMock(spec=socket.socket)
    sock.recv.side_effect = fake_recv
    return sock


# ---------------------------------------------------------------------------
# RCONClient authentication
# ---------------------------------------------------------------------------


class TestRCONClientAuthentication:
    def _auth_success_socket(self, request_id: int):
        """Socket that returns a successful auth response for *request_id*."""
        # Server sends empty RESPONSE_VALUE then AUTH_RESPONSE
        empty = _make_raw_packet(request_id, PACKET_TYPE_RESPONSE, "")
        auth_ok = _make_raw_packet(request_id, PACKET_TYPE_AUTH_RESPONSE, "")
        return _make_socket_with_data(empty, auth_ok)

    def _auth_fail_socket(self, request_id: int):
        """Socket that returns a failed auth response."""
        empty = _make_raw_packet(request_id, PACKET_TYPE_RESPONSE, "")
        auth_fail = _make_raw_packet(AUTH_FAILURE_ID, PACKET_TYPE_AUTH_RESPONSE, "")
        return _make_socket_with_data(empty, auth_fail)

    def test_successful_authentication(self):
        client = RCONClient("127.0.0.1", 27015, "correct")
        client._socket = self._auth_success_socket(1)
        client.authenticate()  # Should not raise

    def test_failed_authentication_raises(self):
        client = RCONClient("127.0.0.1", 27015, "wrong")
        client._socket = self._auth_fail_socket(1)
        with pytest.raises(AuthenticationError):
            client.authenticate()

    def test_auth_without_connection_raises(self):
        client = RCONClient("127.0.0.1", 27015, "pw")
        with pytest.raises(ConnectionError):
            client.authenticate()


# ---------------------------------------------------------------------------
# RCONClient.execute
# ---------------------------------------------------------------------------


class TestRCONClientExecute:
    def _execute_socket(self, cmd_id: int, end_id: int, response_body: str):
        """
        Build a mock socket that responds to:
          1. cmd_id  -> response with *response_body*
          2. end_id  -> empty response (signals end)
        """
        resp = _make_raw_packet(cmd_id, PACKET_TYPE_RESPONSE, response_body)
        end = _make_raw_packet(end_id, PACKET_TYPE_RESPONSE, "")
        return _make_socket_with_data(resp, end)

    def test_execute_returns_response(self):
        client = RCONClient("127.0.0.1", 27015, "pw")
        # Request IDs start at 0 and _next_id increments before returning
        # First call → id=1 (cmd), second call → id=2 (end marker)
        client._socket = self._execute_socket(1, 2, "Player1\nPlayer2")
        result = client.execute("AdminListPlayers")
        assert result == "Player1\nPlayer2"

    def test_execute_empty_response(self):
        client = RCONClient("127.0.0.1", 27015, "pw")
        client._socket = self._execute_socket(1, 2, "")
        result = client.execute("AdminRestartLevel")
        assert result == ""

    def test_execute_without_connection_raises(self):
        client = RCONClient("127.0.0.1", 27015, "pw")
        with pytest.raises(ConnectionError):
            client.execute("AdminListPlayers")

    def test_execute_multipart_response(self):
        """Multiple response packets for the same command are concatenated."""
        client = RCONClient("127.0.0.1", 27015, "pw")
        part1 = _make_raw_packet(1, PACKET_TYPE_RESPONSE, "Hello ")
        part2 = _make_raw_packet(1, PACKET_TYPE_RESPONSE, "World")
        end = _make_raw_packet(2, PACKET_TYPE_RESPONSE, "")
        client._socket = _make_socket_with_data(part1, part2, end)
        result = client.execute("SomeLongCommand")
        assert result == "Hello World"


# ---------------------------------------------------------------------------
# RCONClient connect / disconnect
# ---------------------------------------------------------------------------


class TestRCONClientConnection:
    def test_connect_sets_socket(self):
        client = RCONClient("127.0.0.1", 27015, "pw")
        mock_sock = MagicMock()
        with patch("socket.socket", return_value=mock_sock):
            client.connect()
        assert client.connected
        mock_sock.connect.assert_called_once_with(("127.0.0.1", 27015))

    def test_connect_failure_raises(self):
        client = RCONClient("127.0.0.1", 27015, "pw")
        with patch("socket.socket") as mock_socket_cls:
            mock_sock = mock_socket_cls.return_value
            mock_sock.connect.side_effect = OSError("refused")
            with pytest.raises(ConnectionError):
                client.connect()

    def test_disconnect_clears_socket(self):
        client = RCONClient("127.0.0.1", 27015, "pw")
        client._socket = MagicMock()
        client.disconnect()
        assert not client.connected

    def test_context_manager_connects_and_disconnects(self):
        client = RCONClient("127.0.0.1", 27015, "pw")
        mock_sock = MagicMock()
        # Provide auth response data for __enter__
        request_id = 1
        empty = _make_raw_packet(request_id, PACKET_TYPE_RESPONSE, "")
        auth_ok = _make_raw_packet(request_id, PACKET_TYPE_AUTH_RESPONSE, "")
        data = empty + auth_ok
        index = [0]

        def fake_recv(n):
            chunk = data[index[0] : index[0] + n]
            index[0] += n
            return chunk

        mock_sock.recv.side_effect = fake_recv

        with patch("socket.socket", return_value=mock_sock):
            with client:
                assert client.connected
        assert not client.connected
