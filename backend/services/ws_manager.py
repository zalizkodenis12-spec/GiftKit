"""WebSocket connection manager for real-time terminal broadcasts."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket
from loguru import logger

from backend.database import utc_now_iso


class WSManager:
    """Manages active /ws/live WebSocket clients and broadcasts JSON events safely."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.debug(f"WS connected (active: {len(self._connections)})")

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
        logger.debug(f"WS disconnected (active: {len(self._connections)})")

    async def broadcast(self, event_type: str, data: Any) -> None:
        if not self._connections:
            return
        payload = {
            "type": event_type,
            "data": data,
            "timestamp": utc_now_iso(),
        }
        async with self._lock:
            targets = list(self._connections)

        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)


ws_manager = WSManager()
