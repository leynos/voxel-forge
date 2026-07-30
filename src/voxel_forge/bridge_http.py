"""HTTP side of the editor bridge.

Serves the bridge's small JSON API (``GET /health``, ``GET /scene``,
``POST /scene``). Mutable bridge state is reached through the
:mod:`voxel_forge.bridge` module object so tests that replace
``bridge.store`` or ``bridge._async_broadcast`` observe the substitution.
"""

from __future__ import annotations

import json
import typing as typ

if typ.TYPE_CHECKING:
    import asyncio

from voxel_forge import bridge
from voxel_forge.model import VoxelScene

MAX_HTTP_BODY_BYTES = 10_000_000
_STATUS_OK = b"HTTP/1.1 200 OK\r\n"
_STATUS_NO_CONTENT = b"HTTP/1.1 204 No Content\r\n"
_STATUS_BAD_REQUEST = b"HTTP/1.1 400 Bad Request\r\n"
_STATUS_FORBIDDEN = b"HTTP/1.1 403 Forbidden\r\n"
_STATUS_TOO_LARGE = b"HTTP/1.1 413 Content Too Large\r\n"
_JSON_CONTENT_TYPE = b"Content-Type: application/json\r\n"
_CORS_METHODS = b"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"


class _HttpRequest(typ.NamedTuple):
    """The parts of an HTTP request head that the bridge acts upon."""

    method: str
    path: str
    content_length: int
    origin: str | None


def _parse_request_head(header_text: str) -> _HttpRequest:
    """Pull the method, path, body length and origin out of a request head."""
    lines = header_text.split("\r\n")
    first = lines[0] if lines else ""
    method = first.split(" ")[0] if first else "GET"
    path = first.split(" ")[1] if " " in first else "/"
    content_length = 0
    origin: str | None = None
    for line in lines[1:]:
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
        elif line.lower().startswith("origin:"):
            origin = line.split(":", 1)[1].strip()
    return _HttpRequest(method, path, content_length, origin)


def _cors_headers(origin: str | None) -> bytes:
    """Return the CORS headers granted to ``origin``."""
    headers = _CORS_METHODS
    if origin in bridge.allowed_origins():
        headers += f"Access-Control-Allow-Origin: {origin}\r\nVary: Origin\r\n".encode()
    return headers


async def _close_connection(writer: asyncio.StreamWriter) -> None:
    """Flush and close one client connection."""
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def _write_response(
    writer: asyncio.StreamWriter, status: bytes, headers: bytes, body: bytes
) -> None:
    """Write one JSON response and close the connection."""
    writer.write(
        status
        + headers
        + _JSON_CONTENT_TYPE
        + f"Content-Length: {len(body)}\r\n\r\n".encode()
        + body
    )
    await _close_connection(writer)


async def _handle_scene_post(payload: str) -> tuple[bytes, bytes]:
    """Replace the active scene from a JSON body and broadcast the result."""
    try:
        scene = VoxelScene.from_dict(json.loads(payload))
        bridge.store._scenes[scene.name] = scene
        bridge.store._current = scene.name
        await bridge._async_broadcast({
            "type": "scene_update",
            "scene": scene.to_dict(),
        })
        body = json.dumps({
            "ok": True,
            "name": scene.name,
            "blocks": scene.block_count(),
        }).encode()
    except Exception as exc:  # ruff: ignore[blind-except]  # any bad payload answers 400
        return _STATUS_BAD_REQUEST, json.dumps({"error": str(exc)}).encode()
    return _STATUS_OK, body


def _current_scene_body() -> bytes:
    """Return the active scene as JSON, or an error document when there is none."""
    name = bridge.store._current
    if not name or name not in bridge.store._scenes:
        return json.dumps({"error": "no active scene"}).encode()
    return json.dumps(bridge.store._scenes[name].to_dict(), ensure_ascii=False).encode()


async def _route_request(request: _HttpRequest, payload: str) -> tuple[bytes, bytes]:
    """Dispatch one request, returning its status line and response body."""
    match (request.method, request.path):
        case ("POST", "/scene"):
            return await _handle_scene_post(payload)
        case ("GET", "/health"):
            health = {"ok": True, "editor_clients": len(bridge._clients)}
            return _STATUS_OK, json.dumps(health).encode()
        case ("GET", "/scene"):
            return _STATUS_OK, _current_scene_body()
        case _:
            endpoints = {"endpoints": ["GET /health", "GET /scene", "POST /scene"]}
            return _STATUS_OK, json.dumps(endpoints).encode()


async def _http_handler(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Serve the bridge's small HTTP API on one connection."""
    header_bytes = await reader.readuntil(b"\r\n\r\n")
    request = _parse_request_head(header_bytes.decode("utf-8", errors="ignore"))
    cors = _cors_headers(request.origin)

    if request.origin is not None and request.origin not in bridge.allowed_origins():
        body = json.dumps({"error": "origin is not allowed"}).encode()
        await _write_response(writer, _STATUS_FORBIDDEN, b"", body)
        return

    if request.content_length < 0 or request.content_length > MAX_HTTP_BODY_BYTES:
        body = json.dumps({"error": "request body is too large"}).encode()
        await _write_response(writer, _STATUS_TOO_LARGE, cors, body)
        return

    payload_bytes = (
        await reader.readexactly(request.content_length)
        if request.content_length
        else b""
    )
    payload = payload_bytes.decode("utf-8")

    if request.method == "OPTIONS":
        writer.write(_STATUS_NO_CONTENT + cors + b"\r\n")
        await _close_connection(writer)
        return

    status, body = await _route_request(request, payload)
    await _write_response(writer, status, cors, body)
