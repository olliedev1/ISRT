"""
Source RCON protocol client for Insurgency Sandstorm.

Implements the Source RCON Protocol as documented at:
https://developer.valvesoftware.com/wiki/Source_RCON_Protocol
"""

import socket
import struct
import time
from typing import Optional

# Packet types
PACKET_TYPE_RESPONSE = 0
PACKET_TYPE_AUTH_RESPONSE = 2
PACKET_TYPE_COMMAND = 2
PACKET_TYPE_AUTH = 3

# Special request ID used to signal auth failure
AUTH_FAILURE_ID = -1

# Maximum size for a single packet body (Source RCON spec)
MAX_PACKET_SIZE = 4096

# Maximum request ID value (signed 32-bit integer)
MAX_REQUEST_ID = 0x7FFFFFFF

# End-of-response marker used for multi-packet detection
_END_MARKER_BODY = "ISRT_END_OF_RESPONSE"


class RCONError(Exception):
    """Base exception for RCON errors."""


class AuthenticationError(RCONError):
    """Raised when RCON authentication fails."""


class ConnectionError(RCONError):
    """Raised when the connection to the server fails."""


class RCONPacket:
    """Represents a single Source RCON packet."""

    def __init__(self, packet_id: int, packet_type: int, body: str = ""):
        self.id = packet_id
        self.type = packet_type
        self.body = body

    def encode(self) -> bytes:
        """Encode the packet to bytes for transmission."""
        body_bytes = self.body.encode("utf-8") + b"\x00\x00"
        payload = struct.pack("<ii", self.id, self.type) + body_bytes
        return struct.pack("<i", len(payload)) + payload

    @classmethod
    def decode(cls, data: bytes) -> "RCONPacket":
        """Decode a packet from raw bytes (including the 4-byte size prefix)."""
        if len(data) < 14:
            raise RCONError("Packet data too short to decode")
        size = struct.unpack("<i", data[:4])[0]
        if len(data) < 4 + size:
            raise RCONError("Incomplete packet data")
        packet_id = struct.unpack("<i", data[4:8])[0]
        packet_type = struct.unpack("<i", data[8:12])[0]
        # Body is everything between header and the two trailing null bytes
        body_end = 4 + size - 2
        body = data[12:body_end].decode("utf-8", errors="replace")
        return cls(packet_id, packet_type, body)


class RCONClient:
    """
    RCON client for Insurgency Sandstorm (Source RCON protocol).

    Usage::

        with RCONClient("192.168.1.1", 27015, "my_password") as client:
            response = client.execute("AdminListPlayers")
            print(response)
    """

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._request_id = 0

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open a TCP connection to the RCON server."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))
            self._socket = sock
        except OSError as exc:
            raise ConnectionError(
                f"Could not connect to {self.host}:{self.port}: {exc}"
            ) from exc

    def authenticate(self) -> None:
        """
        Send authentication packet and verify the server accepted the password.

        Raises:
            AuthenticationError: if the server rejects the password.
            ConnectionError: if not connected.
        """
        self._ensure_connected()
        packet_id = self._next_id()
        auth_packet = RCONPacket(packet_id, PACKET_TYPE_AUTH, self.password)
        self._send(auth_packet)

        # The server sends an empty SERVERDATA_RESPONSE_VALUE packet first,
        # then the AUTH_RESPONSE packet.
        response = self._recv_packet()
        # Some server implementations omit the first empty packet; handle both.
        if response.type == PACKET_TYPE_RESPONSE:
            response = self._recv_packet()

        if response.id == AUTH_FAILURE_ID or response.id != packet_id:
            raise AuthenticationError("RCON authentication failed – check password")

    def disconnect(self) -> None:
        """Close the connection to the RCON server."""
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            finally:
                self._socket = None

    @property
    def connected(self) -> bool:
        """Return True if the socket is open."""
        return self._socket is not None

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def execute(self, command: str) -> str:
        """
        Send a command to the RCON server and return the response string.

        For commands that produce large output the server may send multiple
        packets.  This method reassembles them before returning.

        Args:
            command: The RCON command to execute.

        Returns:
            The server response as a string.
        """
        self._ensure_connected()
        cmd_id = self._next_id()
        self._send(RCONPacket(cmd_id, PACKET_TYPE_COMMAND, command))

        # Send a dummy follow-up packet so we know when the real response ends.
        end_id = self._next_id()
        self._send(RCONPacket(end_id, PACKET_TYPE_COMMAND, _END_MARKER_BODY))

        parts = []
        while True:
            packet = self._recv_packet()
            if packet.id == end_id:
                # We've consumed all response packets for our command.
                break
            if packet.id == cmd_id and packet.type == PACKET_TYPE_RESPONSE:
                parts.append(packet.body)

        return "".join(parts)

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "RCONClient":
        self.connect()
        self.authenticate()
        return self

    def __exit__(self, *_args) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._request_id = (self._request_id % MAX_REQUEST_ID) + 1
        return self._request_id

    def _ensure_connected(self) -> None:
        if self._socket is None:
            raise ConnectionError("Not connected – call connect() first")

    def _send(self, packet: RCONPacket) -> None:
        assert self._socket is not None
        try:
            self._socket.sendall(packet.encode())
        except OSError as exc:
            self._socket = None
            raise ConnectionError(f"Send failed: {exc}") from exc

    def _recv_exact(self, n: int) -> bytes:
        """Read exactly *n* bytes from the socket."""
        assert self._socket is not None
        buf = b""
        while len(buf) < n:
            try:
                chunk = self._socket.recv(n - len(buf))
            except OSError as exc:
                self._socket = None
                raise ConnectionError(f"Receive failed: {exc}") from exc
            if not chunk:
                self._socket = None
                raise ConnectionError("Server closed the connection")
            buf += chunk
        return buf

    def _recv_packet(self) -> RCONPacket:
        """Read one complete packet from the socket."""
        size_data = self._recv_exact(4)
        size = struct.unpack("<i", size_data)[0]
        if size < 10 or size > MAX_PACKET_SIZE:
            raise RCONError(f"Invalid packet size: {size}")
        payload = self._recv_exact(size)
        return RCONPacket.decode(size_data + payload)
