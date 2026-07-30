"""Readiness checks covering the bridge, server, and export surfaces."""

from __future__ import annotations

import asyncio
import contextlib
import json
import struct
import sys
import typing as typ
from pathlib import Path
from types import SimpleNamespace

import pytest

from voxel_forge import bridge, server
from voxel_forge.model import SceneStore, VoxelScene
from voxel_forge.vox_io import export_vox, import_vox

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def exchange_http(request: bytes) -> bytes:
    """Exchange one raw HTTP request with the bridge's HTTP listener."""

    async def exchange() -> bytes:
        http_server = await asyncio.start_server(bridge._http_handler, "127.0.0.1", 0)
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
    """Return the top-level chunks of a VOX payload, keyed by chunk id."""
    assert data[:4] == b"VOX ", "the payload must open with the VOX magic"
    assert data[8:12] == b"MAIN", "the first chunk must be MAIN"
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


def test_broadcast_submits_to_bridge_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The broadcast helper must submit work to the bridge's own loop."""
    submitted: list[tuple[cabc.Coroutine[object, object, object], object]] = []
    bridge_loop = object()
    monkeypatch.setattr(bridge, "_bridge_loop", bridge_loop)

    def capture(
        coroutine: cabc.Coroutine[object, object, object], loop: object
    ) -> None:
        submitted.append((coroutine, loop))
        coroutine.close()

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", capture)

    bridge._broadcast({"type": "scene_update"})

    assert len(submitted) == 1, "the broadcast must be submitted exactly once"
    assert submitted[0][1] is bridge_loop, "submission must target the bridge loop"


def test_editor_remove_updates_server_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    """An editor removal must delete the voxel and re-broadcast the scene."""
    store = SceneStore()
    scene = store.create("editor")
    scene.place(1, 2, 3, "1")
    monkeypatch.setattr(bridge, "store", store)
    broadcasts: list[dict[str, typ.Any]] = []

    async def capture(  # ruff: ignore[unused-async]  # Must be awaitable to replace the hook.
        payload: dict[str, typ.Any],
    ) -> None:
        broadcasts.append(payload)

    monkeypatch.setattr(bridge, "_async_broadcast", capture)

    class WebSocket:
        def __init__(self) -> None:
            self.messages = iter([
                '{"type":"editor_remove","scene_name":"editor","layer_index":0,"x":1,"y":2,"z":3}'
            ])

        def __aiter__(self) -> typ.Self:
            return self

        async def __anext__(self) -> str:
            try:
                return next(self.messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def send(self, _message: str) -> None:
            return None

    asyncio.run(bridge._ws_handler(WebSocket()))

    assert scene.block_count() == 0, "the removed voxel must leave the scene"
    assert broadcasts[-1]["scene"]["name"] == "editor", "the update must name the scene"


def test_http_bridge_rejects_non_local_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The HTTP bridge must refuse requests from a non-local origin."""
    store = SceneStore()
    monkeypatch.setattr(bridge, "store", store)
    payload = b'{"name":"hostile"}'
    request = (
        b"POST /scene HTTP/1.1\r\n"
        b"Host: 127.0.0.1:8766\r\n"
        b"Origin: https://example.invalid\r\n"
        + f"Content-Length: {len(payload)}\r\n\r\n".encode()
        + payload
    )

    response = exchange_http(request)

    assert response.startswith(b"HTTP/1.1 403 Forbidden"), "a foreign origin must fail"
    assert store.list_active() == [], "the refused post must not create a scene"


def test_bridge_diagnostic_uses_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bridge diagnostics must go to stderr so stdout stays protocol-only."""

    class DummyServer:
        async def __aenter__(self) -> typ.Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

    async def make_server(  # ruff: ignore[unused-async]  # Must be awaitable like the real API.
        *_args: object, **_kwargs: object
    ) -> DummyServer:
        return DummyServer()

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(serve=make_server))
    monkeypatch.setattr(asyncio, "start_server", make_server)

    async def run_until_started() -> None:
        task = asyncio.create_task(bridge._run_servers())
        await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(run_until_started())
    captured = capsys.readouterr()

    assert not captured.out, "the bridge must leave stdout free for the protocol"
    assert "VoxelForge bridge:" in captured.err, "diagnostics must go to stderr"


def test_desktop_entry_point_degrades_without_pyside6(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without the `desktop` extra, `voxel-forge` must explain, not traceback."""
    monkeypatch.setitem(sys.modules, "PySide6", None)
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", None)
    monkeypatch.delitem(sys.modules, "voxel_forge.desktop.app", raising=False)
    from voxel_forge.desktop import launch

    exit_code = launch.main()
    captured = capsys.readouterr()

    assert exit_code == 1, "a missing desktop extra must exit non-zero"
    assert "desktop" in captured.err, "the message must name the missing extra"
    assert "uv" in captured.err, "the message must show how to install the extra"
    assert "Traceback" not in captured.err, "the failure must not show a traceback"


def test_desktop_entry_point_reraises_unrelated_import_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrelated ImportError must propagate rather than be swallowed."""
    monkeypatch.setitem(sys.modules, "voxel_forge.export_roblox", None)
    monkeypatch.delitem(sys.modules, "voxel_forge.desktop.app", raising=False)
    from voxel_forge.desktop import launch

    with pytest.raises(ImportError, match="export_roblox"):
        launch.main()


def test_runtime_dependencies_are_bounded_below_next_major() -> None:
    """A fresh resolution (``uv tool install``) must not select a breaking major."""
    import tomllib

    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    for requirement in pyproject["project"]["dependencies"]:
        assert "<" in requirement, f"dependency {requirement!r} has no upper bound"


def test_mcp_entry_point_supports_help(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`voxel-forge-mcp --help` must succeed without starting the server."""
    monkeypatch.setattr(sys, "argv", ["voxel-forge-mcp", "--help"])

    with pytest.raises(SystemExit) as excinfo:
        server.main()

    assert excinfo.value.code == 0, "--help must exit successfully"
    assert "VoxelForge" in capsys.readouterr().out, "help must name the tool"


def test_readme_documents_cross_platform_installation() -> None:
    """The README must be followable on Linux without translation."""
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "uv tool install" in readme, "the README must document uv installation"
    assert "voxel-forge-mcp" in readme, "the README must name the MCP entry point"
    assert "C:\\Users" not in readme, (
        "README must not rely on user-specific absolute paths"
    )


def test_windows_mcp_launcher_uses_installed_entrypoint() -> None:
    """The Windows launcher must call the installed entry point."""
    launcher = Path("run-mcp.bat").read_text(encoding="utf-8")

    assert "uv run voxel-forge-mcp" in launcher, "uv must launch the entry point"
    assert "python src/voxel_forge/server.py" not in launcher, "no path may remain"


def test_scene_name_cannot_escape_scene_directory(scene_directory: Path) -> None:
    """A traversing scene name must be refused before anything is written."""
    scene = VoxelScene("../outside")

    with pytest.raises(ValueError, match="scene name"):
        scene.save()

    assert not (scene_directory.parent / "outside.json").exists(), "nothing may escape"


def test_unicode_scene_name_round_trips(scene_directory: Path) -> None:
    """A non-ASCII scene name must survive a save and load cycle."""
    scene = VoxelScene("บ้าน เล็ก")
    scene.place(1, 2, 3, "2")

    saved_path = scene.save()
    loaded = VoxelScene.load(scene.name)

    assert saved_path.parent == scene_directory, "the scene must be saved in place"
    assert loaded.to_dict() == scene.to_dict(), "the scene must survive a round trip"


@pytest.mark.parametrize("name", ["", ".", "..", "bad/name", "bad\\name", "CON"])
def test_scene_store_rejects_unsafe_names(name: str) -> None:
    """The store must refuse names that are unsafe as file names."""
    store = SceneStore()

    with pytest.raises(ValueError, match="scene name"):
        store.create(name)


def test_from_dict_rejects_invalid_active_layer() -> None:
    """An out-of-range active layer must be rejected on deserialisation."""
    data = VoxelScene("valid").to_dict()
    data["active_layer"] = -1

    with pytest.raises(ValueError, match="active_layer"):
        VoxelScene.from_dict(data)


def test_from_dict_rejects_invalid_palette_channel() -> None:
    """An out-of-range palette channel must be rejected on deserialisation."""
    data = VoxelScene("valid").to_dict()
    data["palette"] = {"1": [256, 0, 0]}

    with pytest.raises(ValueError, match="palette"):
        VoxelScene.from_dict(data)


def test_place_rejects_unknown_colour_without_mutating_scene() -> None:
    """An unknown colour must be refused and leave the scene untouched."""
    scene = VoxelScene("valid")

    with pytest.raises(ValueError, match="colour"):
        scene.place(0, 0, 0, "not-a-colour")

    assert scene.block_count() == 0, "the rejected voxel must not be stored"


@pytest.fixture
def empty_server_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the server module an empty scene store and an inert bridge."""
    monkeypatch.setattr(server, "store", server.SceneStore())
    monkeypatch.setattr(server, "_sync_bridge", lambda _scene: None)


def test_fill_box_rejects_more_than_limit_without_mutation(
    empty_server_store: None,
) -> None:
    """An oversized box fill must be refused before any voxel is placed."""
    server.store.create("bounded")

    with pytest.raises(ValueError, match="100,000"):
        server.voxelforge_fill_box(0, 100_000, 0, 0, 0, 0)

    assert server.store.get().block_count() == 0, "the scene must stay untouched"


def test_place_many_rejects_more_than_limit_without_mutation(
    empty_server_store: None,
) -> None:
    """An oversized batch place must be refused before any voxel lands."""
    server.store.create("bounded")
    blocks = [[index, 0, 0, "1"] for index in range(100_001)]

    with pytest.raises(ValueError, match="100,000"):
        server.voxelforge_place_many(json.dumps(blocks))

    assert server.store.get().block_count() == 0, "the scene must stay untouched"


def test_basic_agent_scene_workflow(
    empty_server_store: None, scene_directory: Path
) -> None:
    """The core agent tools must create, edit, save, and reload a scene."""
    assert "basic" in server.voxelforge_create_scene("basic"), "the scene must exist"
    assert "วาง" in server.voxelforge_place_block(0, 0, 0, "2"), "placing must work"
    assert "เติม" in server.voxelforge_fill_box(1, 2, 0, 0, 0, 0, "3"), (
        "filling must be confirmed"
    )
    assert server.store.get().block_count() == 3, "three voxels must be present"
    assert "บันทึก" in server.voxelforge_save(), "the save must be confirmed"

    server.store = server.SceneStore()
    assert "โหลด" in server.voxelforge_load("basic"), "the load must be confirmed"
    assert server.store.get().block_count() == 3, "the saved voxels must return"


def test_export_contains_required_chunks_in_order(tmp_path: Path) -> None:
    """A VOX export must carry SIZE, XYZI, and RGBA chunks in that order."""
    scene = VoxelScene("chunks")
    scene.place(2, 3, 4, "2")
    path = export_vox(scene, tmp_path / "chunks.vox")
    data = path.read_bytes()

    assert data.index(b"SIZE") < data.index(b"XYZI") < data.index(b"RGBA"), (
        "the chunks must appear in the order the format requires"
    )
    chunks = child_chunks(data)
    assert struct.unpack("<III", chunks[b"SIZE"]) == (1, 1, 1), (
        "the model must be trimmed to its occupied extent"
    )
    assert struct.unpack_from("<I", chunks[b"XYZI"])[0] == 1, "one voxel must be listed"


@pytest.mark.parametrize("hex_colour", ["#123456", "#000000"])
def test_export_preserves_hex_colour_through_round_trip(
    tmp_path: Path, hex_colour: str
) -> None:
    """A hex colour must survive an export and import round trip."""
    scene = VoxelScene("colour")
    scene.place(0, 0, 0, hex_colour)

    loaded = import_vox(export_vox(scene, tmp_path / "colour.vox"))
    colour_key = loaded.layer.blocks[0, 0, 0]

    assert loaded.resolve_color(colour_key) == scene.resolve_color(hex_colour), (
        "the colour must be preserved exactly"
    )


def test_export_rejects_unrepresentable_dimension(tmp_path: Path) -> None:
    """A scene wider than the VOX format allows must be refused."""
    scene = VoxelScene("wide")
    scene.place(0, 0, 0, "1")
    scene.place(256, 0, 0, "1")

    with pytest.raises(ValueError, match="256"):
        export_vox(scene, tmp_path / "wide.vox")
