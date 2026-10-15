"""Shared helpers for the Python readiness contract tests.

This module provides temporary HTTP exchange, VOX chunk parsing, a finite
editor WebSocket, and a bounded non-blocking lock probe. Readiness test modules
import these helpers to exercise bridge and file-format contracts without
starting production services.
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import threading

from pathlib import Path

from voxel_forge import bridge_http

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def exchange_http(request: bytes) -> bytes:
    """Exchange a raw HTTP request with a temporary bridge server."""

    async def exchange() -> bytes:
        """Send the request through a temporary localhost bridge server."""
        http_server = await asyncio.start_server(
            bridge_http._http_handler, "127.0.0.1", 0
        )
        port = http_server.sockets[0].getsockname()[1]
        async with http_server:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(request)
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
        return response

    return asyncio.run(exchange())


def child_chunks(data: bytes) -> dict[bytes, bytes]:
    """Return the MAIN chunk's child chunks, keyed by chunk id."""
    assert data[:4] == b"VOX ", "exported file must start with the VOX magic"
    assert data[8:12] == b"MAIN", "the first chunk after the header must be MAIN"
    children_size = struct.unpack_from("<I", data, 16)[0]
    offset = 20
    end = offset + children_size
    chunks: dict[bytes, bytes] = {}
    while offset < end:
        chunk_id = data[offset : offset + 4]
        content_size, nested_size = struct.unpack_from("<II", data, offset + 4)
        content_start = offset + 12
        chunks[chunk_id] = data[content_start : content_start + content_size]
        offset = content_start + content_size + nested_size
    return chunks


class EditorSocket:
    """Finite editor message stream for routing and lock-ownership tests."""

    def __init__(self, messages: list[str]) -> None:
        """Store the messages to deliver; for example EditorSocket([]) is empty."""
        self.messages = iter(messages)

    def __aiter__(self) -> typ.Self:
        """Use this socket as its own asynchronous message iterator."""
        return self

    async def __anext__(self) -> str:
        """Read the next message, ending the stream when all are consumed."""
        try:
            return next(self.messages)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def send(self, _message: str) -> None:
        """Accept the initial snapshot without coupling a routing test to it."""
        return


@contextlib.contextmanager
def probe_lock(lock: threading.RLock) -> cabc.Iterator[bool]:
    """Bound a non-blocking lock probe, e.g. ``with probe_lock(lock) as available``.

    Release only a lock this thread acquired; another thread's ownership stays
    intact so a concurrency test can observe the mutation boundary.
    """
    has_acquired = False
    try:
        has_acquired = lock.acquire(blocking=False)
        yield has_acquired
    finally:
        if has_acquired:
            lock.release()
