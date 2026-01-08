# client.py
import socket
from protocol import unpack_offer, pack_request, OFFER_UDP_PORT, get_preferred_ip

TEAM_NAME = "NoSocketsJustCards_v2"

def main():
    print("Client started, listening for offer requests...")

    PREFERRED_IP = get_preferred_ip()
    print("My preferred IP:", PREFERRED_IP)

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
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
        try:
            data, addr = udp.recvfrom(4096)
            sender_ip = addr[0]
            try:
                tcp_port, server_name = unpack_offer(data)
                if server_name != TEAM_NAME:
                    continue

                print("DEBUG offer from:", sender_ip)
                if sender_ip != PREFERRED_IP:
                    continue

            except ValueError:
                continue

            print(f"Received offer from {sender_ip} (server_name={server_name}, tcp_port={tcp_port})")

            # --- ask user rounds ---
            rounds_str = input("How many rounds do you want to play? (1-255): ").strip()
            try:
                num_rounds = int(rounds_str)
                if not (1 <= num_rounds <= 255):
                    raise ValueError
            except ValueError:

                print("Invalid number of rounds. Going back to listening...")
                continue

            # --- TCP connect ---

            tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp.settimeout(3.0)

            try:

                tcp.connect((sender_ip, tcp_port))
                req = pack_request(num_rounds, TEAM_NAME)
                tcp.sendall(req)

                resp = tcp.recv(64)
                print(f"[TCP] Server response: {resp!r}")

            except Exception as e:

                print(f"[TCP] Connection failed: {e}")

            finally:

                tcp.close()
            print("Back to listening for offers...\n")

        except KeyboardInterrupt:

            print("\nClient stopped.")
            break

    udp.close()


if __name__ == "__main__":
    main()
