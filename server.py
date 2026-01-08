# server.py
import socket
import threading
import time
from protocol import pack_offer, unpack_request, OFFER_UDP_PORT

TEAM_NAME = "NoSocketsJustCards_v2"



def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        s.close()

def handle_client(conn: socket.socket, addr):
    try:
        expected = 4 + 1 + 1 + 32  # 38
        data = b""
        while len(data) < expected:
            chunk = conn.recv(expected - len(data))
            if not chunk:
                raise ConnectionError("Client closed before sending full request")
            data += chunk

        num_rounds, client_name = unpack_request(data)
        print(f"[TCP] Client connected from {addr[0]}:{addr[1]} | name={client_name} | rounds={num_rounds}")

        conn.sendall(b"OK")
    except Exception as e:
        print(f"[TCP] Error with {addr}: {e}")
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    print("### RUNNING SERVER.PY STAGE 2 ###")

    ip = get_local_ip()
    WIFI_IP = ip

    print(f"Server started, listening on IP address {ip}")

    # ---- TCP socket ----
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.bind((WIFI_IP, 0))

    tcp.listen()
    server_tcp_port = tcp.getsockname()[1]

    print(f"Server started, listening on IP address {ip} (TCP port {server_tcp_port})")

    # ---- UDP broadcaster ----
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    udp.bind((WIFI_IP, 0))
    offer = pack_offer(server_tcp_port, TEAM_NAME)
    dest = ("255.255.255.255", OFFER_UDP_PORT)

    last_offer_time = 0.0
    while True:
        try:
            # 1) לשדר offer פעם בשנייה
            now = time.time()
            if now - last_offer_time >= 1.0:
                udp.sendto(offer, dest)
                print(f"[UDP] Sent offer (tcp_port={server_tcp_port}, name={TEAM_NAME})")
                last_offer_time = now

            # 2) לקבל TCP בלי להיתקע: נשים timeout קצר
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
