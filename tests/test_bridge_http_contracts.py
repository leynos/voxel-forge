"""Successful HTTP bridge routes and their loopback CORS contract."""

from __future__ import annotations

import asyncio
import json
import typing as typ

from readiness_helpers import exchange_http

from voxel_forge import bridge
from voxel_forge.model import SceneStore

if typ.TYPE_CHECKING:
    import pytest

_EDITOR_ORIGIN = "http://localhost:5173"


def _response_body(response: bytes) -> bytes:
    """Return the bytes after the HTTP response header terminator."""
    return response.split(b"\r\n\r\n", maxsplit=1)[1]


def _assert_successful_json_response(
    response: bytes,
    expected_body: dict[str, object],
    route_name: str,
) -> None:
    """Check a successful JSON route and its registered-origin response."""
    headers = response.split(b"\r\n\r\n", maxsplit=1)[0]

    assert response.startswith(b"HTTP/1.1 200 OK"), f"{route_name} must succeed"
    assert f"Access-Control-Allow-Origin: {_EDITOR_ORIGIN}".encode() in headers, (
        f"{route_name} must allow the registered editor origin"
    )
    assert json.loads(_response_body(response)) == expected_body, (
        f"{route_name} must return its expected JSON payload"
    )


def test_health_route_reports_bridge_status_with_allowed_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health responses expose status and CORS only for a registered editor."""
    monkeypatch.setattr(bridge, "_clients", set())
    monkeypatch.setattr(bridge, "_editor_origin_ports", {5173})

    response = exchange_http(
        f"GET /health HTTP/1.1\r\nOrigin: {_EDITOR_ORIGIN}\r\n\r\n".encode()
    )
    _assert_successful_json_response(
        response,
        {"ok": True, "editor_clients": 0},
        "health route",
    )


def test_scene_route_returns_the_current_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The HTTP scene route serializes the active scene from the shared store."""
    store = SceneStore()
    current = store.create("current")
    monkeypatch.setattr(bridge, "store", store)

    response = exchange_http(b"GET /scene HTTP/1.1\r\n\r\n")

    assert response.startswith(b"HTTP/1.1 200 OK"), "scene lookup must succeed"
    assert json.loads(_response_body(response)) == current.to_dict(), (
        "the route must return the active scene snapshot"
    )


def test_scene_post_registers_and_broadcasts_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid scene post updates the registry and broadcasts the same snapshot."""
    store = SceneStore()
    posted = SceneStore().create("posted")
    broadcasts: list[dict[str, object]] = []

    async def record_broadcast(payload: dict[str, object]) -> None:
        """Capture the scene event sent to connected editors."""
        await asyncio.sleep(0)
        broadcasts.append(payload)

    monkeypatch.setattr(bridge, "store", store)
    monkeypatch.setattr(bridge, "_editor_origin_ports", {5173})
    monkeypatch.setattr(bridge, "_async_broadcast", record_broadcast)
    body = json.dumps(posted.to_dict()).encode()
    request = (
        f"POST /scene HTTP/1.1\r\nOrigin: {_EDITOR_ORIGIN}\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    ).encode() + body

    response = exchange_http(request)
    _assert_successful_json_response(
        response,
        {"ok": True, "name": "posted", "blocks": 0},
        "scene write",
    )
    assert store.get().to_dict() == posted.to_dict(), "store the posted scene"
    assert broadcasts == [{"type": "scene_update", "scene": posted.to_dict()}], (
        "broadcast the same scene snapshot to connected editors"
    )


def test_options_route_returns_preflight_cors_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allowed preflight requests receive the methods and origin headers."""
    monkeypatch.setattr(bridge, "_editor_origin_ports", {5173})
    request = (
        f"OPTIONS /scene HTTP/1.1\r\nOrigin: {_EDITOR_ORIGIN}\r\n"
        "Access-Control-Request-Method: POST\r\n\r\n"
    ).encode()

    response = exchange_http(request)
    headers, body = response.split(b"\r\n\r\n", maxsplit=1)

    assert response.startswith(b"HTTP/1.1 204 No Content"), (
        "preflight must return no content"
    )
    assert b"Access-Control-Allow-Methods: GET, POST, OPTIONS" in headers, (
        "preflight must list supported bridge methods"
    )
    assert f"Access-Control-Allow-Origin: {_EDITOR_ORIGIN}".encode() in headers, (
        "preflight must allow the registered editor origin"
    )
    assert body == b"", "preflight response must have no body"
