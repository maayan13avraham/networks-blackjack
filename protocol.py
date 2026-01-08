# protocol.py
import struct
import socket
def get_preferred_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

MAGIC_COOKIE = 0xabcddcba
MSG_TYPE_OFFER = 0x2

OFFER_UDP_PORT = 13122

# Offer format:
# magic cookie (4 bytes, big-endian) | msg type (1 byte) | server tcp port (2 bytes, big-endian) | server name (32 bytes)
OFFER_STRUCT = struct.Struct("!IBH32s")  # I=4, B=1, H=2, 32s=32


def encode_fixed_name(name: str, size: int = 32) -> bytes:
    b = name.encode("utf-8", errors="ignore")
    if len(b) >= size:
        return b[:size]
    return b + b"\x00" * (size - len(b))


def decode_fixed_name(raw: bytes) -> str:
    # strip trailing nulls
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")


def pack_offer(server_tcp_port: int, server_name: str) -> bytes:
    if not (0 <= server_tcp_port <= 65535):
        raise ValueError("server_tcp_port must be in 0..65535")
    name_bytes = encode_fixed_name(server_name, 32)
    return OFFER_STRUCT.pack(MAGIC_COOKIE, MSG_TYPE_OFFER, server_tcp_port, name_bytes)


def unpack_offer(data: bytes):
    """Returns (server_tcp_port, server_name) or raises ValueError."""
    if len(data) != OFFER_STRUCT.size:
        raise ValueError(f"Bad offer length: {len(data)} != {OFFER_STRUCT.size}")
    cookie, mtype, port, name_raw = OFFER_STRUCT.unpack(data)
    if cookie != MAGIC_COOKIE:
        raise ValueError("Bad magic cookie")
    if mtype != MSG_TYPE_OFFER:
        raise ValueError("Not an offer packet")
    return port, decode_fixed_name(name_raw)

MSG_TYPE_REQUEST = 0x3





# Request format:
# magic (4) | type (1) | num_rounds (1) | client name (32)
REQUEST_STRUCT = struct.Struct("!IBB32s")  # I=4, B=1, B=1, 32s=32


def pack_request(num_rounds: int, client_name: str) -> bytes:
    if not (1 <= num_rounds <= 255):
        raise ValueError("num_rounds must be in 1..255")
    name_bytes = encode_fixed_name(client_name, 32)
    return REQUEST_STRUCT.pack(MAGIC_COOKIE, MSG_TYPE_REQUEST, num_rounds, name_bytes)


def unpack_request(data: bytes):
    """Returns (num_rounds, client_name) or raises ValueError."""
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


# -------------------- Payload (Stage 3) --------------------

MSG_TYPE_PAYLOAD = 0x4

# Client decision is exactly 5 bytes (ASCII) per spec
DECISION_HIT = b"Hittt"
DECISION_STAND = b"Stand"

# Round results (server -> client)
RES_NOT_OVER = 0x0
RES_TIE = 0x1
RES_LOSS = 0x2
RES_WIN = 0x3

# Client->Server payload: magic(4) | type(1) | decision(5)
PAYLOAD_CLIENT_STRUCT = struct.Struct("!IB5s")  # 4+1+5=10

# Server->Client payload: magic(4) | type(1) | result(1) | rank(2) | suit(1)
PAYLOAD_SERVER_STRUCT = struct.Struct("!IBBHB")  # 4+1+1+2+1=9


def pack_payload_client(decision: bytes) -> bytes:
    """decision must be b'Hittt' or b'Stand'."""
    if decision not in (DECISION_HIT, DECISION_STAND):
        raise ValueError("decision must be b'Hittt' or b'Stand'")
    return PAYLOAD_CLIENT_STRUCT.pack(MAGIC_COOKIE, MSG_TYPE_PAYLOAD, decision)


def unpack_payload_client(data: bytes) -> bytes:
    """Returns decision bytes (b'Hittt' or b'Stand')."""
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
    result: 0..3
    rank: 1..13  (A=1, J=11, Q=12, K=13)
    suit: 0..3   (H/D/C/S)
    """
    if not (0 <= result <= 3):
        raise ValueError("result must be 0..3")
    if not (1 <= rank <= 13):
        raise ValueError("rank must be 1..13")
    if not (0 <= suit <= 3):
        raise ValueError("suit must be 0..3")
    return PAYLOAD_SERVER_STRUCT.pack(MAGIC_COOKIE, MSG_TYPE_PAYLOAD, result, rank, suit)


def unpack_payload_server(data: bytes):
    """Returns (result, rank, suit)."""
    if len(data) != PAYLOAD_SERVER_STRUCT.size:
        raise ValueError(f"Bad server payload length: {len(data)} != {PAYLOAD_SERVER_STRUCT.size}")
    cookie, mtype, result, rank, suit = PAYLOAD_SERVER_STRUCT.unpack(data)
    if cookie != MAGIC_COOKIE:
        raise ValueError("Bad magic cookie")
    if mtype != MSG_TYPE_PAYLOAD:
        raise ValueError("Not a payload packet")
    return result, rank, suit


def recv_exact(sock: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Socket closed while reading")
        data += chunk
    return data
