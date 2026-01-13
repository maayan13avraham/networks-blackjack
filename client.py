
import socket
from protocol import (
    unpack_offer, pack_request, OFFER_UDP_PORT, get_preferred_ip, recv_exact,
    unpack_payload_server, pack_payload_client,
    DECISION_HIT, DECISION_STAND,
    RES_NOT_OVER, RES_WIN, RES_LOSS, RES_TIE
)


TEAM_NAME = "NoSocketsJustCards_v2"

# Maps card ranks (1-13) to Blackjack game values: Ace=11, Face cards=10
def card_points(rank: int) -> int:
    if rank == 1:
        return 11
    if rank >= 11:
        return 10
    return rank

# Calculates total hand value
# automatically adjusting Aces from 11 to 1 if the sum exceeds 21
def hand_value(ranks: list[int]) -> int:
    total = sum(card_points(r) for r in ranks)
    aces = sum(1 for r in ranks if r == 1)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

# convert numeric result codes to readable strings for the UI
def result_text(code: int) -> str:
    return {
        RES_NOT_OVER: "NOT_OVER",
        RES_TIE: "TIE",
        RES_LOSS: "LOSS",
        RES_WIN: "WIN",
    }.get(code, f"UNKNOWN({code})")

# Validates user input to ensure it is a number between 1 and 255
def ask_rounds() -> int:
    while True:
        rounds_str = input("How many rounds do you want to play? (1-255): ").strip()
        try:
            n = int(rounds_str)
            if 1 <= n <= 255:
                return n
        except ValueError:
            pass
        print("Invalid number. Try again.")

def play_session(server_ip: str, tcp_port: int, num_rounds: int):
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Initial connection timeout
    tcp.settimeout(3.0)
    try:
        tcp.connect((server_ip, tcp_port))

        # Prevents blocking indefinitely if the server hangs
        tcp.settimeout(8.0)

        try:
            # Send binary Request message over TCP
            tcp.sendall(pack_request(num_rounds, TEAM_NAME))

            # Basic server acknowledgment
            resp = tcp.recv(64)
            print(f"[TCP] Server response: {resp!r}")

            wins = losses = ties = 0

            for round_i in range(1, num_rounds + 1):
                print(f"\n=== Round {round_i}/{num_rounds} ===")

                player_ranks: list[int] = []
                dealer_ranks: list[int] = []

                # INITIAL DEAL: Receive 2 player cards face-up
                for i in range(2):
                    msg = recv_exact(tcp, 9)
                    result, rank, suit = unpack_payload_server(msg)
                    if result != RES_NOT_OVER:
                        print("Round ended unexpectedly:", result_text(result))
                        break
                    player_ranks.append(rank)
                    print(f"Player card {i+1}: rank={rank}, suit={suit} | total={hand_value(player_ranks)}")

                # INITIAL DEAL: Receive dealer's first visible card
                msg = recv_exact(tcp, 9)
                result, rank, suit = unpack_payload_server(msg)
                if result != RES_NOT_OVER:
                    print("Round ended unexpectedly:", result_text(result))
                    # consume round end and continue
                    if result == RES_WIN:
                        wins += 1
                    elif result == RES_LOSS:
                        losses += 1
                    else:
                        ties += 1
                    continue

                dealer_ranks.append(rank)
                print(f"Dealer shows: rank={rank}, suit={suit} | visible_total={hand_value(dealer_ranks)}")

                # PLAYER TURN: Loop until player Stands or Busts
                while True:
                    total = hand_value(player_ranks)
                    # Local check for player bust
                    if total > 21:
                        print("Player BUST (local). Waiting for server result...")
                        msg = recv_exact(tcp, 9)
                        end_res, _, _ = unpack_payload_server(msg)
                        print("Round finished:", result_text(end_res))
                        if end_res == RES_WIN:
                            wins += 1
                        elif end_res == RES_LOSS:
                            losses += 1
                        else:
                            ties += 1
                        break

                    choice = input("Hit or Stand? [h/s]: ").strip().lower()
                    if choice not in ['h', 's']:
                        print("Invalid input, please type 'h' or 's'")
                        continue
                    # Send "Hittt"
                    if choice.startswith("h"):
                        tcp.sendall(pack_payload_client(DECISION_HIT))

                        msg = recv_exact(tcp, 9)
                        res, rank, suit = unpack_payload_server(msg)

                        if res == RES_NOT_OVER:
                            player_ranks.append(rank)
                            total = hand_value(player_ranks)
                            print(f"Player got: rank={rank}, suit={suit} | total={total}")
                            # Check for bust after Hit
                            if total > 21:
                                # After bust, server sends final result
                                msg = recv_exact(tcp, 9)
                                end_res, _, _ = unpack_payload_server(msg)
                                print("Round finished:", result_text(end_res))
                                if end_res == RES_WIN:
                                    wins += 1
                                elif end_res == RES_LOSS:
                                    losses += 1
                                else:
                                    ties += 1
                                break

                            continue

                        # If server ended round immediately
                        print("Round finished:", result_text(res))
                        if res == RES_WIN:
                            wins += 1
                        elif res == RES_LOSS:
                            losses += 1
                        else:
                            ties += 1
                        break

                    else:
                        # Stand
                        tcp.sendall(pack_payload_client(DECISION_STAND))

                        #Dealer turn - Dealer hits until total >= 17
                        while True:
                            msg = recv_exact(tcp, 9)
                            res, rank, suit = unpack_payload_server(msg)

                            if res == RES_NOT_OVER:
                                dealer_ranks.append(rank)
                                print(f"Dealer got/revealed: rank={rank}, suit={suit} | dealer_total={hand_value(dealer_ranks)}")
                                continue
                            # Handle round result (Win/Loss/Tie)
                            print(f"Final dealer total = {hand_value(dealer_ranks)}")
                            print("Round finished:", result_text(res))
                            if res == RES_WIN:
                                wins += 1
                            elif res == RES_LOSS:
                                losses += 1
                            else:
                                ties += 1
                            break

                        break
            # Print session statistics and return to offer listening
            played = wins + losses + ties
            win_rate = (wins / played) if played else 0.0
            print(f"\nFinished playing {played} rounds, win rate: {win_rate:.2%}")
            print(f"Stats: wins={wins}, losses={losses}, ties={ties}")

        except socket.timeout:
            print("[TCP] Timeout: no response from server. Closing session and returning to offers...")
            return
    # Close connection immediately after session
    finally:
        try:
            tcp.close()
        except OSError:
            pass

def main():
    #Client initialization and offer discovery
    print("Client started, listening for offer requests...")
    PREFERRED_IP = get_preferred_ip()
    print("My preferred IP:", PREFERRED_IP)

    #Listen for UDP offers on the hardcoded port 13122
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    # Allows multiple clients on the same machine
    try:
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except OSError:
        pass

    try:
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except (AttributeError, OSError):
        pass

    udp.bind(("", OFFER_UDP_PORT))

    while True:
        # Unpack and validate UDP offer from server
        try:
            data, addr = udp.recvfrom(4096)
            sender_ip = addr[0]
            # Prompt user for rounds before connecting
            try:
                tcp_port, server_name = unpack_offer(data)

            # Ignore corrupted or malformed packets
            except ValueError:
                continue

            print(f"Received offer from {sender_ip} (server_name={server_name}, tcp_port={tcp_port})")
            #Get user input and start game session
            num_rounds = ask_rounds()
            play_session(sender_ip, tcp_port, num_rounds)
            # Immediately return to listening for offers after session ends
            print("Back to listening for offers...\n")

        except KeyboardInterrupt:
            print("\nClient stopped.")
            break

    udp.close()


if __name__ == "__main__":
    main()
