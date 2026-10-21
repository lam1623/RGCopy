"""WebSocket that streams queue changes to the UI."""

from __future__ import annotations

import asyncio
import contextlib

from starlette.websockets import WebSocket, WebSocketDisconnect

from .auth import is_authenticated, origin_allowed
from .context import AppContext


async def events_ws(websocket: WebSocket) -> None:
    ctx: AppContext = websocket.app.state.ctx
    if not origin_allowed(websocket):
        await websocket.close(code=4403)
        return
    if not is_authenticated(websocket):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    manager = ctx.manager
    queue = manager.subscribe()

    async def sender() -> None:
        await websocket.send_json(manager.snapshot())
        while True:
            event = await queue.get()
            await websocket.send_json(manager.snapshot() if event["type"] == "resync" else event)

    async def receiver() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return

    tasks = {asyncio.create_task(sender()), asyncio.create_task(receiver())}
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            with contextlib.suppress(WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
                task.result()
    finally:
        for task in tasks:
            task.cancel()
        manager.unsubscribe(queue)
