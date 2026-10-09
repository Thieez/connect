"""WebSocket relay for peers that cannot connect directly through NAT."""

import asyncio
import re

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="Connect Relay")
rooms: dict[str, set[WebSocket]] = {}
rooms_lock = asyncio.Lock()
ROOM_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


@app.get("/")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/{room_code}")
async def relay(websocket: WebSocket, room_code: str):
    if not ROOM_PATTERN.fullmatch(room_code):
        await websocket.close(code=1008, reason="Invalid room code")
        return

    await websocket.accept()
    async with rooms_lock:
        peers = rooms.setdefault(room_code, set())
        if len(peers) >= 2:
            await websocket.send_json(
                {"type": "error", "message": "Pokój jest już pełny."}
            )
            await websocket.close(code=1013, reason="Room is full")
            return
        peers.add(websocket)
        other_peers = peers - {websocket}

    try:
        if other_peers:
            await websocket.send_json({"type": "status", "message": "Peer połączony."})
            await send_to_peers(
                other_peers, {"type": "status", "message": "Peer dołączył."}
            )
        else:
            await websocket.send_json(
                {"type": "status", "message": "Czekam na drugiego peera..."}
            )

        while True:
            message = await websocket.receive_text()
            if len(message.encode("utf-8")) > 4096:
                await websocket.send_json(
                    {"type": "error", "message": "Wiadomość jest za długa (limit 4 KB)."}
                )
                continue
            async with rooms_lock:
                recipients = rooms.get(room_code, set()) - {websocket}
            await send_to_peers(
                recipients, {"type": "message", "text": message}
            )
    except WebSocketDisconnect:
        pass
    finally:
        async with rooms_lock:
            peers = rooms.get(room_code)
            if peers is not None:
                peers.discard(websocket)
                other_peers = set(peers)
                if not peers:
                    del rooms[room_code]
            else:
                other_peers = set()
        await send_to_peers(
            other_peers, {"type": "status", "message": "Peer się rozłączył."}
        )


async def send_to_peers(peers: set[WebSocket], message: dict[str, str]):
    for peer in peers:
        try:
            await peer.send_json(message)
        except (RuntimeError, WebSocketDisconnect):
            pass
