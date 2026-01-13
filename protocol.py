# =========================
# protocol.py
# =========================
# This module defines the binary protocol used between client and server:
# - Offer messages (UDP)
# - Request messages (TCP)
# - Game payload messages (TCP)
# All messages start with a magic cookie for validation.

import struct
import socket

# =========================
# Network utilities
# =========================
def get_preferred_ip() -> str:
    """
       Returns the preferred local IP address by opening a dummy UDP connection.
       Used to determine the interface used for outgoing traffic.
       """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


# =========================
# Common constants
# =========================

MAGIC_COOKIE = 0xabcddcba  # Protocol identifier (4 bytes)

MSG_TYPE_OFFER = 0x2     # Server -> Client (UDP)
MSG_TYPE_REQUEST = 0x3     # Client -> Server (TCP)
MSG_TYPE_PAYLOAD = 0x4     # Game payload (TCP)

OFFER_UDP_PORT = 13122     # UDP port used for broadcasting offers


# =========================
# Offer message (Server -> Client, UDP)
# =========================
# Format:
# magic cookie (4 bytes, big-endian)
# message type (1 byte) = 0x2
# server TCP port (2 bytes, big-endian)
# server name (32 bytes, fixed-length)
OFFER_STRUCT = struct.Struct("!IBH32s")  # I=4, B=1, H=2, 32s=32

def encode_fixed_name(name: str, size: int = 32) -> bytes:
    """
      Encodes a string into a fixed-length byte field.
      - If shorter than size: pad with null bytes (0x00)
      - If longer than size: truncate
      """
    b = name.encode("utf-8", errors="ignore")
    if len(b) >= size:
        return b[:size]
    return b + b"\x00" * (size - len(b))


def decode_fixed_name(raw: bytes) -> str:
    """
       Decodes a fixed-length byte field into a string,
       stripping trailing null bytes.
       """
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")


def pack_offer(server_tcp_port: int, server_name: str) -> bytes:
    """
        Packs an offer message according to the protocol specification.
        """
    if not (0 <= server_tcp_port <= 65535):
        raise ValueError("server_tcp_port must be in 0..65535")
    name_bytes = encode_fixed_name(server_name, 32)
    return OFFER_STRUCT.pack(MAGIC_COOKIE, MSG_TYPE_OFFER, server_tcp_port, name_bytes)


def unpack_offer(data: bytes):
    """
       Unpacks an offer message.
       Returns: (server_tcp_port, server_name)
       """
    if len(data) != OFFER_STRUCT.size:
        raise ValueError(f"Bad offer length: {len(data)} != {OFFER_STRUCT.size}")
    cookie, mtype, port, name_raw = OFFER_STRUCT.unpack(data)
    if cookie != MAGIC_COOKIE:
        raise ValueError("Bad magic cookie")
    if mtype != MSG_TYPE_OFFER:
        raise ValueError("Not an offer packet")
    return port, decode_fixed_name(name_raw)

# =========================
# Request message (Client -> Server, TCP)
# =========================
# Format:
# magic cookie (4 bytes)
# message type (1 byte) = 0x3
# number of rounds (1 byte)
# client name (32 bytes, fixed-length)
REQUEST_STRUCT = struct.Struct("!IBB32s")  # I=4, B=1, B=1, 32s=32


def pack_request(num_rounds: int, client_name: str) -> bytes:
    """
        Packs a request message sent by the client.
        """
    if not (1 <= num_rounds <= 255):
        raise ValueError("num_rounds must be in 1..255")
    name_bytes = encode_fixed_name(client_name, 32)
    return REQUEST_STRUCT.pack(MAGIC_COOKIE, MSG_TYPE_REQUEST, num_rounds, name_bytes)


def unpack_request(data: bytes):
    """
    Unpacks a request message.
    Returns: (num_rounds, client_name)
    """
    if len(data) != REQUEST_STRUCT.size:
        raise ValueError(f"Bad request length: {len(data)} != {REQUEST_STRUCT.size}")
    cookie, mtype, num_rounds, name_raw = REQUEST_STRUCT.unpack(data)
    if cookie != MAGIC_COOKIE:
        raise ValueError("Bad magic cookie")
    if mtype != MSG_TYPE_REQUEST:
        raise ValueError("Not a request packet")
    if num_rounds == 0:
        raise ValueError("num_rounds cannot be 0")
    return num_rounds, decode_fixed_name(name_raw)




# =========================
# Game payload messages (TCP)
# =========================

# Client decision is exactly 5 bytes (ASCII) per spec
DECISION_HIT = b"Hittt"
DECISION_STAND = b"Stand"

# Round results (server -> client)
RES_NOT_OVER = 0x0
RES_TIE = 0x1
RES_LOSS = 0x2
RES_WIN = 0x3

# Client -> Server payload
# Format:
# magic cookie (4 bytes)
# message type (1 byte) = 0x4
# decision (5 bytes)
PAYLOAD_CLIENT_STRUCT = struct.Struct("!IB5s")  # 4+1+5 = 10 bytes

# Server -> Client payload
# Format:
# magic cookie (4 bytes)
# message type (1 byte) = 0x4
# result (1 byte)
# card rank (2 bytes)
# card suit (1 byte)
PAYLOAD_SERVER_STRUCT = struct.Struct("!IBBHB")  # 4+1+1+2+1 = 9 bytes


def pack_payload_client(decision: bytes) -> bytes:
    """
    Packs a client decision payload.
    Decision must be either b'Hittt' or b'Stand'.
    """
    if decision not in (DECISION_HIT, DECISION_STAND):
        raise ValueError("decision must be b'Hittt' or b'Stand'")
    return PAYLOAD_CLIENT_STRUCT.pack(MAGIC_COOKIE, MSG_TYPE_PAYLOAD, decision)


def unpack_payload_client(data: bytes) -> bytes:
    """
    Unpacks a client payload.
    Returns the decision bytes.
    """
    if len(data) != PAYLOAD_CLIENT_STRUCT.size:
        raise ValueError(f"Bad client payload length: {len(data)} != {PAYLOAD_CLIENT_STRUCT.size}")
    cookie, mtype, decision = PAYLOAD_CLIENT_STRUCT.unpack(data)
    if cookie != MAGIC_COOKIE:
        raise ValueError("Bad magic cookie")
    if mtype != MSG_TYPE_PAYLOAD:
        raise ValueError("Not a payload packet")
    if decision not in (DECISION_HIT, DECISION_STAND):
        raise ValueError("Bad decision")
    return decision


def pack_payload_server(result: int, rank: int, suit: int) -> bytes:
    """
    Packs a server payload message.
    result: 0..3
    rank:   1..13 (A=1, J=11, Q=12, K=13)
    suit:   0..3  (H/D/C/S)
    """
    if not (0 <= result <= 3):
        raise ValueError("result must be 0..3")
    if not (1 <= rank <= 13):
        raise ValueError("rank must be 1..13")
    if not (0 <= suit <= 3):
        raise ValueError("suit must be 0..3")
    return PAYLOAD_SERVER_STRUCT.pack(MAGIC_COOKIE, MSG_TYPE_PAYLOAD, result, rank, suit)


def unpack_payload_server(data: bytes):
    """
    Unpacks a server payload.
    Returns: (result, rank, suit)
    """
    if len(data) != PAYLOAD_SERVER_STRUCT.size:
        raise ValueError(f"Bad server payload length: {len(data)} != {PAYLOAD_SERVER_STRUCT.size}")
    cookie, mtype, result, rank, suit = PAYLOAD_SERVER_STRUCT.unpack(data)
    if cookie != MAGIC_COOKIE:
        raise ValueError("Bad magic cookie")
    if mtype != MSG_TYPE_PAYLOAD:
        raise ValueError("Not a payload packet")
    return result, rank, suit

# =========================
# Socket helpers
# =========================
def recv_exact(sock: socket.socket, n: int) -> bytes:
    """
        Receives exactly n bytes from a TCP socket.
        Raises an error if the connection closes early.
        """
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Socket closed while reading")
        data += chunk
    return data
