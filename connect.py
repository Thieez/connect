#!/usr/bin/env python3
"""Prosty, bezpośredni czat TCP między dwoma uruchomionymi węzłami."""

import argparse
import json
import re
import socket
import socketserver
import threading
from urllib.parse import urlsplit


class PeerNode:
    def __init__(self):
        self.peers = set()
        self.lock = threading.Lock()

    def add_peer(self, connection, address, receive_in_thread=True):
        with self.lock:
            self.peers.add(connection)
        try:
            remote = connection.getpeername()
            local = connection.getsockname()
            print(
                f"\nTCP połączone: local={local[0]}:{local[1]} "
                f"peer={remote[0]}:{remote[1]}."
            )
        except OSError as error:
            print(f"\nNie udało się odczytać endpointu TCP dla {address}: {error}")
        print(f"Połączono z {address}. Możesz pisać.\n> ", end="", flush=True)
        if receive_in_thread:
            threading.Thread(
                target=self._receive, args=(connection, address), daemon=True
            ).start()

    def _receive(self, connection, address):
        try:
            with connection.makefile("r", encoding="utf-8") as stream:
                for message in stream:
                    print(f"\n[{address}] {message.rstrip()}\n> ", end="", flush=True)
        except (OSError, UnicodeError) as error:
            print(f"\nBłąd połączenia z {address}: {error}")
        finally:
            self.remove_peer(connection)
            print(f"\nRozłączono: {address}")

    def send(self, message):
        payload = (message + "\n").encode("utf-8")
        with self.lock:
            peers = list(self.peers)
        if not peers:
            print("\nBrak połączonych peerów.")
            return
        for peer in peers:
            try:
                peer.sendall(payload)
            except OSError as error:
                print(f"\nNie udało się wysłać wiadomości: {error}")
                self.remove_peer(peer)

    def remove_peer(self, connection):
        with self.lock:
            self.peers.discard(connection)
        try:
            connection.close()
        except OSError:
            pass


class PeerHandler(socketserver.BaseRequestHandler):
    def handle(self):
        address = self.client_address[0]
        self.server.node.add_peer(self.request, address, receive_in_thread=False)
        self.server.node._receive(self.request, address)


class PeerServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_relay(relay_url, room_code):
    import websocket

    parsed_url = urlsplit(relay_url)
    scheme = {"http": "ws", "https": "wss"}.get(parsed_url.scheme, parsed_url.scheme)
    if scheme not in ("ws", "wss") or not parsed_url.netloc:
        raise ValueError("--relay must be a valid http(s) or ws(s) URL")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", room_code):
        raise ValueError("--room must be 8-64 characters: letters, numbers, _ or -")
    path = parsed_url.path.rstrip("/") + f"/ws/{room_code}"
    relay_endpoint = parsed_url._replace(scheme=scheme, path=path).geturl()

    try:
        connection = websocket.create_connection(relay_endpoint, timeout=60)
    except websocket.WebSocketException as error:
        raise ConnectionError(f"Relay handshake failed: {error}") from error
    connection.settimeout(None)
    send_lock = threading.Lock()
    disconnected = threading.Event()

    def receive():
        try:
            while True:
                payload = connection.recv()
                if payload is None:
                    break
                event = json.loads(payload)
                if event["type"] == "message":
                    print(f"\n[peer] {event['text']}\n> ", end="", flush=True)
                elif event["type"] in ("status", "error"):
                    print(f"\n{event['message']}\n> ", end="", flush=True)
        except (OSError, ValueError, KeyError, websocket.WebSocketException) as error:
            if not disconnected.is_set():
                print(f"\nPołączenie z relay zostało przerwane: {error}")
        finally:
            disconnected.set()

    threading.Thread(target=receive, daemon=True).start()
    print(f"Połączono z relay w pokoju {room_code}. Wpisz /quit, aby zakończyć.")
    try:
        while not disconnected.is_set():
            try:
                message = input("> ")
            except EOFError:
                break
            if message.strip() == "/quit":
                break
            if message:
                try:
                    with send_lock:
                        connection.send(
                            message
                        )
                except websocket.WebSocketException as error:
                    print(f"\nNie udało się wysłać wiadomości: {error}")
                    break
    except KeyboardInterrupt:
        print("\nZamykanie połączenia.")
    finally:
        disconnected.set()
        connection.close()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Uruchom węzeł czatu P2P i opcjonalnie połącz się z adresem peera."
    )
    parser.add_argument(
        "--connect",
        metavar="ADRES",
        help="adres IP lub nazwa hosta drugiego urządzenia",
    )
    parser.add_argument(
        "--headscale",
        metavar="URL",
        help=(
            "użyj podanego serwera Tailscale/Headscale (domyślnie "
            "https://connect-headscale.onrender.com)"
        ),
    )
    parser.add_argument(
        "--no-headscale",
        action="store_true",
        help="wyłącz domyślne połączenie przez sieć Headscale",
    )
    parser.add_argument(
        "--relay",
        metavar="URL",
        help="adres serwera relay, np. https://connect-relay.onrender.com",
    )
    parser.add_argument(
        "--room",
        metavar="KOD",
        help="wspólny, prywatny kod pokoju relay (8-64 znaków)",
    )
    parser.add_argument(
        "--p2p-relay",
        metavar="URL",
        help="serwer sygnalizacyjny dla WebRTC, np. https://connect-relay.onrender.com",
    )
    parser.add_argument(
        "--turn-server",
        metavar="URL",
        help="opcjonalny serwer TURN, np. turn:turn.example.com:3478",
    )
    parser.add_argument("--turn-username", help="nazwa użytkownika serwera TURN")
    parser.add_argument("--turn-password", help="hasło serwera TURN")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="adres nasłuchiwania (domyślnie 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="port TCP dla obu węzłów (domyślnie 8765)",
    )
    args = parser.parse_args()
    if args.no_headscale and args.headscale:
        parser.error("--no-headscale nie może być używane razem z --headscale")
    if not args.no_headscale and not (args.relay or args.p2p_relay):
        from tailscale_client import DEFAULT_HEADSCALE_URL

        args.headscale = args.headscale or DEFAULT_HEADSCALE_URL
    if bool(args.relay or args.p2p_relay) != bool(args.room):
        parser.error("--relay lub --p2p-relay i --room muszą być podane razem")
    if args.headscale and (args.relay or args.p2p_relay):
        parser.error(
            "--headscale nie może być używane razem z --relay ani --p2p-relay"
        )
    if args.relay and args.connect:
        parser.error("--relay nie może być używane razem z --connect")
    if args.p2p_relay and (args.relay or args.connect):
        parser.error("--p2p-relay nie może być używane razem z --relay ani --connect")
    if args.p2p_relay and not args.room:
        parser.error("--p2p-relay wymaga podania --room")
    if any((args.turn_server, args.turn_username, args.turn_password)) and not all(
        (args.p2p_relay, args.turn_server, args.turn_username, args.turn_password)
    ):
        parser.error(
            "konfiguracja TURN wymaga --p2p-relay, --turn-server, "
            "--turn-username i --turn-password"
        )
    return args


def main():
    args = parse_args()
    if args.headscale:
        from tailscale_client import (
            allow_mesh_inbound,
            connect_to_headscale,
            start_mesh_diagnostics,
        )

        try:
            connect_to_headscale(args.headscale)
            allow_mesh_inbound(args.port)
            mesh_diagnostics = start_mesh_diagnostics(args.connect)
        except (OSError, ValueError, RuntimeError) as error:
            raise SystemExit(
                f"Nie udało się skonfigurować sieci Headscale: {error}"
            ) from error
    else:
        mesh_diagnostics = None

    if args.p2p_relay:
        from p2p_client import run_p2p

        try:
            run_p2p(
                args.p2p_relay,
                args.room,
                args.turn_server,
                args.turn_username,
                args.turn_password,
            )
        except (OSError, ValueError, RuntimeError) as error:
            raise SystemExit(
                f"Nie udało się uruchomić połączenia WebRTC: {error}"
            ) from error
        return
    if args.relay:
        try:
            run_relay(args.relay, args.room)
        except (OSError, ValueError) as error:
            raise SystemExit(f"Nie udało się połączyć z relay: {error}") from error
        return

    node = PeerNode()
    server = PeerServer((args.host, args.port), PeerHandler)
    server.node = node
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Węzeł nasłuchuje na {args.host}:{args.port}.")

    try:
        if args.connect:
            connection = socket.create_connection((args.connect, args.port), timeout=10)
            connection.settimeout(None)
            node.add_peer(connection, args.connect)
        print("Wpisz wiadomość i naciśnij Enter. Wpisz /quit, aby zakończyć.")
        while True:
            try:
                message = input("> ")
            except EOFError:
                break
            if message.strip() == "/quit":
                break
            if message:
                node.send(message)
    except KeyboardInterrupt:
        print("\nZamykanie węzła.")
    finally:
        with node.lock:
            peers = list(node.peers)
        for peer in peers:
            node.remove_peer(peer)
        server.shutdown()
        server.server_close()
        if mesh_diagnostics:
            mesh_diagnostics.stop()


if __name__ == "__main__":
    main()
