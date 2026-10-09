#!/usr/bin/env python3
"""Prosty, bezpośredni czat TCP między dwoma uruchomionymi węzłami."""

import argparse
import socket
import socketserver
import threading


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
    return parser.parse_args()


def main():
    args = parse_args()
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
