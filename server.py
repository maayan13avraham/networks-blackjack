# =========================
# server.py
# =========================
# Blackjack game server for the networking hackathon.
# Responsibilities:
# - Broadcast UDP offer messages
# - Accept TCP client connections
# - Run multiple blackjack rounds per client
# - Handle multiple clients concurrently using threads
# - Use timeouts to avoid hanging connections
import socket
import threading
import time
from typing import List, Tuple

from protocol import (
    pack_offer, unpack_request, OFFER_UDP_PORT,
    pack_payload_server, recv_exact, unpack_payload_client,
    DECISION_HIT, DECISION_STAND,
    RES_NOT_OVER, RES_WIN, RES_LOSS, RES_TIE
)
import random

TEAM_NAME = "NoSocketsJustCards_v2"

# =========================
# Blackjack utility functions
# =========================
def card_points(rank: int) -> int:
    """
        Returns the blackjack value of a card rank.
        Ace counts as 11 initially.
        Face cards count as 10.
        """
    if rank == 1:
        return 11
    if rank >= 11:
        return 10
    return rank

def hand_value(ranks: List[int]) -> int:
    """
        Computes the blackjack value of a hand,
        adjusting Aces from 11 to 1 if needed.
        """
    total = sum(card_points(r) for r in ranks)
    aces = sum(1 for r in ranks if r == 1)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def fresh_deck() -> List[Tuple[int, int]]:
    """
        Creates and shuffles a fresh standard deck.
        Each card is (rank, suit).
        """
    deck = [(rank, suit) for suit in range(4) for rank in range(1, 14)]
    random.shuffle(deck)
    return deck

def draw_from_deck(deck: List[Tuple[int, int]]) -> Tuple[int, int]:
    """
        Draws one card from the deck.
        Deck is guaranteed non-empty for this assignment.
        """
    return deck.pop()

# =========================
# Network utilities
# =========================
def get_local_ip() -> str:
    """
        Returns the local IP address used for outgoing connections.
        """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        s.close()

# =========================
# Game helpers
# =========================
def send_final_result(conn: socket.socket, result_code: int):
    """
        Sends the final round result to the client.
        Protocol requires a valid card, so a dummy card is sent.
        """
    conn.sendall(pack_payload_server(result_code, 1, 0))

# =========================
# Single round logic
# =========================
def play_one_round(conn: socket.socket) -> int:
    """
    Plays a single blackjack round with the client.
    Returns:
        RES_WIN, RES_LOSS, or RES_TIE
    """
    deck = fresh_deck()

    player_cards: List[Tuple[int, int]] = []
    dealer_cards: List[Tuple[int, int]] = []

    # ---- Initial deal: player gets 2 cards ----
    for _ in range(2):
        r, s = draw_from_deck(deck)
        player_cards.append((r, s))
        conn.sendall(pack_payload_server(RES_NOT_OVER, r, s))

    # ---- Dealer upcard ----
    up_r, up_s = draw_from_deck(deck)
    dealer_cards.append((up_r, up_s))
    conn.sendall(pack_payload_server(RES_NOT_OVER, up_r, up_s))  # dealer upcard

    # ---- Dealer hidden card ----
    hidden_r, hidden_s = draw_from_deck(deck)
    dealer_cards.append((hidden_r, hidden_s))  # not sent yet

    # ---- Player turn ----
    while True:
        p_total = hand_value([r for (r, _) in player_cards])
        if p_total > 21:
            # Player busts -> immediate loss
            send_final_result(conn, RES_LOSS)
            return RES_LOSS

        decision = unpack_payload_client(recv_exact(conn, 10))

        if decision == DECISION_STAND:
            break

        if decision == DECISION_HIT:
            r, s = draw_from_deck(deck)
            player_cards.append((r, s))
            conn.sendall(pack_payload_server(RES_NOT_OVER, r, s))
            # loop continues; bust handled at top

    # ---- Dealer turn ----
    # Reveal hidden card
    conn.sendall(pack_payload_server(RES_NOT_OVER, hidden_r, hidden_s))

    # Dealer hits until total >= 17
    while True:
        d_total = hand_value([r for (r, _) in dealer_cards])
        if d_total >= 17:
            break
        r, s = draw_from_deck(deck)
        dealer_cards.append((r, s))
        conn.sendall(pack_payload_server(RES_NOT_OVER, r, s))

    # ---- Decide outcome ----
    p_total = hand_value([r for (r, _) in player_cards])
    d_total = hand_value([r for (r, _) in dealer_cards])

    if d_total > 21:
        send_final_result(conn, RES_WIN)
        return RES_WIN
    if p_total > d_total:
        send_final_result(conn, RES_WIN)
        return RES_WIN
    if p_total < d_total:
        send_final_result(conn, RES_LOSS)
        return RES_LOSS

    send_final_result(conn, RES_TIE)
    return RES_TIE

# =========================
# Client handler (per thread)
# =========================
def handle_client(conn: socket.socket, addr):
    """
        Handles a single TCP client connection.
        Runs in its own thread.
        """
    try:
        # Prevent hanging forever if client disappears
        conn.settimeout(10.0)

        # Receive request message
        req = recv_exact(conn, 38)
        num_rounds, client_name = unpack_request(req)
        print(f"[TCP] Client {client_name} from {addr[0]}:{addr[1]} requested {num_rounds} rounds")

        # Optional ACK
        conn.sendall(b"OK")

        wins = losses = ties = 0

        for i in range(num_rounds):
            result = play_one_round(conn)
            if result == RES_WIN:
                wins += 1
            elif result == RES_LOSS:
                losses += 1
            else:
                ties += 1

        print(f"[TCP] Finished with {client_name}: wins={wins}, losses={losses}, ties={ties}")

    except socket.timeout:
        print(f"[TCP] Timeout with {addr}: client not responding. Closing connection.")

    except Exception as e:
        print(f"[TCP] Error with {addr}: {e}")
    finally:
        try:
            conn.close()
        except OSError:
            pass


# =========================
# Server main loop
# =========================
def main():
    print("### RUNNING SERVER.PY STAGE 2 ###")

    ip = get_local_ip()
    WIFI_IP = ip

    print(f"Server started, listening on IP address {ip}")

    # ---- TCP socket (for game sessions) ----
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.bind((WIFI_IP, 0))

    tcp.listen()
    server_tcp_port = tcp.getsockname()[1]

    print(f"Server started, listening on IP address {ip} (TCP port {server_tcp_port})")

    # ---- UDP socket (for offers) ----
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    udp.bind((WIFI_IP, 0))
    offer = pack_offer(server_tcp_port, TEAM_NAME)
    dest = ("255.255.255.255", OFFER_UDP_PORT)

    last_offer_time = 0.0
    while True:
        try:
            # Broadcast offer once per second
            now = time.time()
            if now - last_offer_time >= 1.0:
                udp.sendto(offer, dest)
                print(f"[UDP] Sent offer (tcp_port={server_tcp_port}, name={TEAM_NAME})")
                last_offer_time = now

            # Accept TCP connections without blocking
            tcp.settimeout(0.2)
            try:
                conn, addr = tcp.accept()
                t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                t.start()
            except socket.timeout:
                pass

        except KeyboardInterrupt:
            print("\nServer stopped.")
            break
        except OSError as e:
            print(f"Server error: {e}")

    udp.close()
    tcp.close()


if __name__ == "__main__":
    main()
