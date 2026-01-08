# server.py
import socket
import time
from protocol import pack_offer, OFFER_UDP_PORT

TEAM_NAME = "NoSocketsJustCards"
SERVER_TCP_PORT = 55555


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        s.close()


def main():
    ip = get_local_ip()
    print(f"Server started, listening on IP address {ip}")

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    offer = pack_offer(SERVER_TCP_PORT, TEAM_NAME)
    dest = ("255.255.255.255", OFFER_UDP_PORT)

    while True:
        try:
            udp.sendto(offer, dest)
            print(f"Sent offer (tcp_port={SERVER_TCP_PORT}, name={TEAM_NAME})")
            time.sleep(1.0)
        except KeyboardInterrupt:
            print("\nServer stopped.")
            break
        except OSError as e:
            print(f"UDP send error: {e}")
            time.sleep(1.0)

    udp.close()


if __name__ == "__main__":
    main()
