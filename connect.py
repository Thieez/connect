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
        print(f"\nPołączono z {address}. Możesz pisać.\n> ", end="", flush=True)
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
    if bool(args.relay) != bool(args.room):
        parser.error("--relay i --room muszą być podane razem")
    if args.relay and args.connect:
        parser.error("--relay nie może być używane razem z --connect")
    return args


def main():
    args = parse_args()
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


if __name__ == "__main__":
    main()
