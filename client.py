# client.py
import socket
from protocol import unpack_offer, OFFER_UDP_PORT

def main():
    print("Client started, listening for offer requests...")

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
            except ValueError:
                continue

            print(f"Received offer from {sender_ip} (server_name={server_name}, tcp_port={tcp_port})")

        except KeyboardInterrupt:
            print("\nClient stopped.")
            break
        except OSError as e:
            print(f"UDP recv error: {e}")
            break

    udp.close()


if __name__ == "__main__":
    main()
