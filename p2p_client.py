"""WebRTC client using the relay only for signaling and fallback messages."""

import asyncio
import json
import os
from urllib.parse import urlsplit

DEFAULT_STUN_SERVERS = (
    "stun:stun.l.google.com:19302",
    "stun:stun.cloudflare.com:3478",
)
ICE_CONNECTION_TIMEOUT_SECONDS = 45


def _stun_server_urls():
    configured = [
        server.strip()
        for server in os.environ.get("CONNECT_STUN_SERVERS", "").split(",")
        if server.strip()
    ]
    return configured or list(DEFAULT_STUN_SERVERS)


def run_p2p(
    relay_url, room_code, turn_server=None, turn_username=None, turn_password=None
):
    asyncio.run(_run_p2p(relay_url, room_code, turn_server, turn_username, turn_password))


async def _run_p2p(relay_url, room_code, turn_server, turn_username, turn_password):
    import websockets
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc import RTCConfiguration, RTCIceServer
    from aiortc.exceptions import (
        InternalError,
        InvalidAccessError,
        InvalidStateError,
        OperationError,
    )

    parsed_url = urlsplit(relay_url)
    scheme = {"http": "ws", "https": "wss"}.get(parsed_url.scheme, parsed_url.scheme)
    if scheme not in ("ws", "wss") or not parsed_url.netloc:
        raise ValueError("--p2p-relay musi być poprawnym adresem http(s) lub ws(s)")
    if turn_server and not (turn_username and turn_password):
        raise ValueError("Serwer TURN wymaga nazwy użytkownika i hasła")

    path = parsed_url.path.rstrip("/") + f"/p2p/{room_code}"
    endpoint = parsed_url._replace(scheme=scheme, path=path).geturl()
    ice_servers = [RTCIceServer(urls=server) for server in _stun_server_urls()]
    if turn_server:
        ice_servers.append(
            RTCIceServer(
                urls=turn_server,
                username=turn_username,
                credential=turn_password,
            )
        )

    configuration = RTCConfiguration(iceServers=ice_servers)
    try:
        signaling_connection = await websockets.connect(endpoint, max_size=262144)
    except websockets.exceptions.WebSocketException as error:
        raise ConnectionError(
            f"Nie udało się połączyć z serwerem sygnalizacyjnym: {error}"
        ) from error

    async with signaling_connection as signaling:
        pc = RTCPeerConnection(configuration)
        channel_ready = asyncio.Event()
        fallback = asyncio.Event()
        shutting_down = asyncio.Event()
        send_lock = asyncio.Lock()
        data_channel = None
        connection_timeout = None

        async def send_signal(message):
            async with send_lock:
                await signaling.send(json.dumps(message))

        async def wait_for_direct_connection():
            try:
                await asyncio.wait_for(
                    channel_ready.wait(), timeout=ICE_CONNECTION_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                use_fallback(
                    "Nie udało się zestawić kanału WebRTC w "
                    f"{ICE_CONNECTION_TIMEOUT_SECONDS} s."
                )

        async def notify_fallback():
            try:
                await send_signal({"type": "fallback"})
            except websockets.exceptions.WebSocketException as error:
                print(f"\nNie udało się zgłosić trybu relay: {error}")

        def use_fallback(reason):
            if fallback.is_set() or shutting_down.is_set():
                return
            fallback.set()
            print(
                f"\n{reason} Wiadomości będą przekazywane przez serwer. "
                "Bezpośrednie P2P przez CGNAT może wymagać TURN."
            )
            asyncio.create_task(notify_fallback())

        def attach_channel(channel):
            nonlocal data_channel
            data_channel = channel

            @channel.on("open")
            def on_open():
                if channel_ready.is_set():
                    return
                channel_ready.set()
                print("\nKanał WebRTC aktywny.\n> ", end="", flush=True)

            @channel.on("message")
            def on_message(message):
                if isinstance(message, str):
                    print(f"\n[peer] {message}\n> ", end="", flush=True)

            @channel.on("close")
            def on_close():
                if not fallback.is_set():
                    use_fallback()

            if channel.readyState == "open":
                on_open()

        @pc.on("datachannel")
        def on_datachannel(channel):
            attach_channel(channel)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"\nStan połączenia WebRTC: {pc.connectionState}")
            if pc.connectionState == "failed":
                use_fallback("WebRTC zgłosił błąd zestawiania połączenia.")

        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            print(f"\nStan ICE: {pc.iceConnectionState}")
            if pc.iceConnectionState == "failed":
                use_fallback("Negocjacja ICE nie znalazła osiągalnej trasy P2P.")

        async def receive_signals():
            nonlocal connection_timeout
            try:
                async for raw_message in signaling:
                    event = json.loads(raw_message)
                    event_type = event.get("type")
                    try:
                        if event_type == "ready":
                            if connection_timeout is None:
                                connection_timeout = asyncio.create_task(
                                    wait_for_direct_connection()
                                )
                            if event.get("initiator"):
                                attach_channel(pc.createDataChannel("chat"))
                                offer = await pc.createOffer()
                                await pc.setLocalDescription(offer)
                                await send_signal(
                                    {
                                        "type": "offer",
                                        "sdp": pc.localDescription.sdp,
                                    }
                                )
                        elif event_type == "signal":
                            description = event["data"]
                            if description.get("type") == "offer":
                                await pc.setRemoteDescription(
                                    RTCSessionDescription(
                                        sdp=description["sdp"], type="offer"
                                    )
                                )
                                answer = await pc.createAnswer()
                                await pc.setLocalDescription(answer)
                                await send_signal(
                                    {
                                        "type": "answer",
                                        "sdp": pc.localDescription.sdp,
                                    }
                                )
                            elif description.get("type") == "answer":
                                await pc.setRemoteDescription(
                                    RTCSessionDescription(
                                        sdp=description["sdp"], type="answer"
                                    )
                                )
                        elif event_type == "fallback":
                            fallback.set()
                            print("\nPeer używa połączenia przez serwer.")
                        elif event_type == "data":
                            print(f"\n[peer] {event['text']}\n> ", end="", flush=True)
                        elif event_type in ("status", "error"):
                            print(
                                f"\n{event['message']}\n> ", end="", flush=True
                            )
                    except (
                        InternalError,
                        InvalidAccessError,
                        InvalidStateError,
                        OperationError,
                        KeyError,
                        ValueError,
                        RuntimeError,
                    ) as error:
                        print(f"\nNegocjacja WebRTC nie powiodła się: {error}")
                        use_fallback()
            except (
                OSError,
                ValueError,
                KeyError,
                websockets.exceptions.WebSocketException,
            ) as error:
                print(f"\nPołączenie sygnalizacyjne zostało przerwane: {error}")
            finally:
                shutting_down.set()
                if connection_timeout:
                    connection_timeout.cancel()
                await pc.close()

        receiver = asyncio.create_task(receive_signals())
        print(
            f"Połączono z serwerem sygnalizacyjnym w pokoju {room_code}. "
            "Czekam na peer..."
        )
        try:
            while not receiver.done():
                try:
                    message = await asyncio.to_thread(input, "> ")
                except EOFError:
                    break
                if message.strip() == "/quit":
                    break
                if not message:
                    continue
                if not fallback.is_set() and not channel_ready.is_set():
                    opened = asyncio.create_task(channel_ready.wait())
                    relayed = asyncio.create_task(fallback.wait())
                    done, pending = await asyncio.wait(
                        (opened, relayed),
                        timeout=60,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    if not done:
                        print("\nPołączenie nie jest jeszcze gotowe; spróbuj ponownie.")
                        continue
                if fallback.is_set():
                    await send_signal({"type": "data", "text": message})
                elif data_channel and data_channel.readyState == "open":
                    data_channel.send(message)
        finally:
            shutting_down.set()
            receiver.cancel()
            try:
                await receiver
            except asyncio.CancelledError:
                pass
            await pc.close()
