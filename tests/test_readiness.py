"""Executable contract for the readiness gates.

Each test here pins one behaviour that "basic agent-driven voxel scene creation"
depends on: the MCP launcher, bridge scheduling and origin checks, editor
removal round-trips, scene-name and payload validation, resource bounds,
persistence, and the raw structure of exported MagicaVoxel files.

Run the whole module with ``uv run pytest -q``. Tests that touch persistence
request the ``scene_directory`` fixture from ``conftest.py`` so no real
``~/.voxel-forge`` directory is read or written. Assertions carry messages
because a readiness failure should name the broken contract directly.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import json
import struct
import sys
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from voxel_forge import bridge, scene_store, server
from voxel_forge.model import SceneStore, VoxelScene
from voxel_forge.vox_io import export_vox, import_vox

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def exchange_http(request: bytes) -> bytes:
    """Send one raw HTTP request to a throwaway bridge server and return the response."""

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


def test_broadcast_submits_to_bridge_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    submitted: list[tuple[Any, Any]] = []
    bridge_loop = object()
    monkeypatch.setattr(bridge, "_bridge_loop", bridge_loop)

    def capture(coroutine: Any, loop: Any) -> concurrent.futures.Future[None]:
        submitted.append((coroutine, loop))
        coroutine.close()
        future: concurrent.futures.Future[None] = concurrent.futures.Future()
        future.set_result(None)
        return future

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", capture)

    bridge._broadcast({"type": "scene_update"})

    assert len(submitted) == 1, "a broadcast must schedule exactly one coroutine"
    assert submitted[0][1] is bridge_loop, "the coroutine must be scheduled on the bridge loop"


def test_broadcast_before_loop_is_ready_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "_bridge_loop", None)
    scheduled: list[Any] = []
    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", lambda c, _loop: scheduled.append(c))

    bridge._broadcast({"type": "scene_update"})

    assert scheduled == [], "a broadcast before the bridge loop starts must not be scheduled"


def test_editor_remove_updates_server_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SceneStore()
    scene = store.create("editor")
    scene.place(1, 2, 3, "1")
    monkeypatch.setattr(bridge, "store", store)
    broadcasts: list[dict[str, Any]] = []

    async def capture(payload: dict[str, Any]) -> None:
        broadcasts.append(payload)

    monkeypatch.setattr(bridge, "_async_broadcast", capture)

    class WebSocket:
        def __init__(self) -> None:
            self.messages: Iterator[str] = iter(
                ['{"type":"editor_remove","scene_name":"editor","layer_index":0,"x":1,"y":2,"z":3}']
            )

        def __aiter__(self) -> AsyncIterator[str]:
            return self

        async def __anext__(self) -> str:
            try:
                return next(self.messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def send(self, _message: str) -> None:
            return None

    asyncio.run(bridge._ws_handler(WebSocket()))

    assert scene.block_count() == 0, "an editor removal must delete the voxel from the scene"
    assert broadcasts[-1]["scene"]["name"] == "editor", "a removal must broadcast the updated scene"


def test_editor_remove_targets_the_clicked_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SceneStore()
    scene = store.create("layered")
    scene.add_layer("upper")
    scene.active_layer = 1
    scene.place(4, 0, 0, "1", layer_index=0)
    monkeypatch.setattr(bridge, "store", store)
    broadcasts: list[dict[str, Any]] = []

    async def capture(payload: dict[str, Any]) -> None:
        broadcasts.append(payload)

    monkeypatch.setattr(bridge, "_async_broadcast", capture)

    class WebSocket:
        def __init__(self) -> None:
            self.messages: Iterator[str] = iter(
                ['{"type":"editor_remove","scene_name":"layered","layer_index":0,"x":4,"y":0,"z":0}']
            )

        def __aiter__(self) -> AsyncIterator[str]:
            return self

        async def __anext__(self) -> str:
            try:
                return next(self.messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def send(self, _message: str) -> None:
            return None

    asyncio.run(bridge._ws_handler(WebSocket()))

    assert scene.layers[0].blocks == {}, "the removal must delete from the layer the editor sent"
    assert scene.layers[1].blocks == {}, "the active layer must not be touched by a lower-layer removal"


def test_editor_remove_falls_back_when_layer_is_wrong(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SceneStore()
    scene = store.create("layered")
    scene.add_layer("upper")
    scene.active_layer = 1
    scene.place(4, 0, 0, "1", layer_index=0)
    monkeypatch.setattr(bridge, "store", store)

    async def capture(_payload: dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(bridge, "_async_broadcast", capture)

    class WebSocket:
        def __init__(self) -> None:
            self.messages: Iterator[str] = iter(
                ['{"type":"editor_remove","scene_name":"layered","layer_index":1,"x":4,"y":0,"z":0}']
            )

        def __aiter__(self) -> AsyncIterator[str]:
            return self

        async def __anext__(self) -> str:
            try:
                return next(self.messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def send(self, _message: str) -> None:
            return None

    asyncio.run(bridge._ws_handler(WebSocket()))

    assert scene.block_count() == 0, "a removal must not be silently dropped when the layer is stale"


def test_http_bridge_rejects_non_local_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SceneStore()
    monkeypatch.setattr(bridge, "store", store)
    payload = b'{"name":"hostile"}'
    request = (
        b"POST /scene HTTP/1.1\r\n"
        b"Host: 127.0.0.1:8766\r\n"
        b"Origin: https://example.invalid\r\n" + f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload
    )

    response = exchange_http(request)

    assert response.startswith(b"HTTP/1.1 403 Forbidden"), "a non-local origin must be refused"
    assert store.list_active() == [], "a refused request must not create a scene"


def test_http_bridge_rejects_oversized_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "store", SceneStore())
    request = b"POST /scene HTTP/1.1\r\nHost: 127.0.0.1:8766\r\nContent-Length: 10000001\r\n\r\n"

    response = exchange_http(request)

    assert response.startswith(b"HTTP/1.1 413"), "a body over MAX_HTTP_BODY_BYTES must be refused"


def test_bridge_diagnostic_uses_stderr(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    class DummyServer:
        async def __aenter__(self) -> DummyServer:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

    async def make_server(*_args: Any, **_kwargs: Any) -> DummyServer:
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

    assert captured.out == "", "the bridge must not write to stdout, which carries MCP protocol data"
    assert "VoxelForge bridge:" in captured.err, "the bridge must announce its ports on stderr"


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

    assert exit_code == 1
    assert "desktop" in captured.err
    assert "uv" in captured.err
    assert "Traceback" not in captured.err


def test_desktop_entry_point_reraises_unrelated_import_errors(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_readme_documents_cross_platform_installation() -> None:
    """The README must be followable on Linux without translation."""
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "uv tool install" in readme
    assert "voxel-forge-mcp" in readme
    assert "C:\\Users" not in readme, "README must not rely on user-specific absolute paths"


def test_windows_mcp_launcher_uses_installed_entrypoint() -> None:
    launcher = (REPOSITORY_ROOT / "run-mcp.bat").read_text(encoding="utf-8")

    assert "uv run voxel-forge-mcp" in launcher, "the launcher must call the installed console script"
    assert "python src/voxel_forge/server.py" not in launcher, "the launcher must not run a source file directly"
    assert "|| exit /b 1" in launcher, "a failed locked sync must abort the launcher"
    assert launcher.rstrip().endswith("exit /b %errorlevel%"), (
        "the launcher must return the exit status of the MCP server"
    )


def test_scene_name_cannot_escape_scene_directory(scene_directory: Path) -> None:
    scene = VoxelScene("../outside")

    with pytest.raises(ValueError, match="scene name"):
        scene_store.save_scene(scene)

    assert not (scene_directory.parent / "outside.json").exists(), "an unsafe name must not write outside the directory"


def test_unicode_scene_name_round_trips(scene_directory: Path) -> None:
    scene = VoxelScene("บ้าน เล็ก")
    scene.place(1, 2, 3, "2")

    saved_path = scene_store.save_scene(scene)
    loaded = scene_store.load_scene(scene.name)

    assert saved_path.parent == scene_directory, "a saved scene must stay inside the scenes directory"
    assert loaded.to_dict() == scene.to_dict(), "a saved scene must reload unchanged"


def test_list_saved_scenes_reports_saved_names(scene_directory: Path) -> None:
    scene_store.save_scene(VoxelScene("beta"))
    scene_store.save_scene(VoxelScene("alpha"))

    assert scene_store.list_saved_scenes() == ["alpha", "beta"], "saved scenes must be listed sorted by name"


def test_list_saved_scenes_leaves_an_absent_store_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    absent = tmp_path / "never-created"
    monkeypatch.setattr(scene_store, "scenes_dir", lambda: absent)

    listed = scene_store.list_saved_scenes()

    assert listed == [], "an absent store must list as empty rather than failing"
    assert not absent.exists(), "listing must not create the scene directory as a side effect"


def test_broadcast_failure_is_reported_on_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(bridge, "_bridge_loop", object())

    def failed(coroutine: Any, _loop: Any) -> concurrent.futures.Future[None]:
        coroutine.close()
        future: concurrent.futures.Future[None] = concurrent.futures.Future()
        future.set_exception(RuntimeError("editor socket went away"))
        return future

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", failed)

    bridge._broadcast({"type": "scene_update", "scene": {"name": "hidden-payload"}})

    captured = capsys.readouterr()
    assert captured.out == "", "a broadcast failure must not write to protocol-carrying stdout"
    assert "broadcast failed" in captured.err, "an unexpected broadcast failure must be reported"
    assert "hidden-payload" not in captured.err, "diagnostics must not echo the broadcast payload"


def test_editor_place_and_mcp_place_interleave_without_losing_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic interleaving: an editor edit lands between two MCP edits.

    The MCP tool surface and the editor bridge must share one lock, or an
    editor edit can slip into the middle of an MCP read-modify-snapshot
    sequence. The editor's placement is driven from a second thread while the
    main thread holds the lock, so the test fails if the two sides do not
    synchronize on the same store.
    """
    shared = SceneStore()
    scene = shared.create("shared")
    monkeypatch.setattr(bridge, "store", shared)
    observed: list[dict[str, Any]] = []

    async def capture(payload: dict[str, Any]) -> None:
        observed.append(payload)

    monkeypatch.setattr(bridge, "_async_broadcast", capture)

    class WebSocket:
        def __init__(self) -> None:
            self.messages: Iterator[str] = iter(
                ['{"type":"editor_place","scene_name":"shared","layer_index":0,"x":9,"y":0,"z":0,"color":"2"}']
            )

        def __aiter__(self) -> AsyncIterator[str]:
            return self

        async def __anext__(self) -> str:
            try:
                return next(self.messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def send(self, _message: str) -> None:
            return None

    # _block_coordinate runs between the scene lookup and the mutation. Pausing
    # the editor there lets the main thread test whether the handler still owns
    # the shared lock at that instant: a handler that holds the lock across the
    # whole read-modify-snapshot sequence refuses the main thread's non-blocking
    # acquire, while one that only locked the lookup leaves the lock free.
    at_parse = threading.Event()
    proceed = threading.Event()

    def hooked_coordinate(_message: dict[str, Any]) -> tuple[int, int, int]:
        at_parse.set()
        assert proceed.wait(timeout=5), "the main thread must release the editor hook"
        return 9, 0, 0

    monkeypatch.setattr(bridge, "_block_coordinate", hooked_coordinate)

    def editor_edit() -> None:
        asyncio.run(bridge._ws_handler(WebSocket()))

    scene.place(0, 0, 0, "1")
    thread = threading.Thread(target=editor_edit)
    thread.start()
    assert at_parse.wait(timeout=5), "the editor thread must reach the coordinate parse"
    handler_holds_lock = not shared.lock.acquire(blocking=False)
    if not handler_holds_lock:
        shared.lock.release()
    proceed.set()
    thread.join(timeout=5)
    assert not thread.is_alive(), "the editor thread must finish"

    assert handler_holds_lock, "the editor must hold the shared lock across the mutation, not only the lookup"
    assert scene.block_count() == 2, "an editor placement must land alongside the MCP placement"
    assert observed and observed[-1]["scene"]["layers"][0]["blocks"] == [[0, 0, 0, "1"], [9, 0, 0, "2"]], (
        "the editor must broadcast the merged state"
    )


@pytest.mark.parametrize("name", ["", ".", "..", "bad/name", "bad\\name", "CON", "CON.txt", "lpt1.scene", "trailing."])
def test_scene_store_rejects_unsafe_names(name: str) -> None:
    store = SceneStore()

    with pytest.raises(ValueError, match="scene name"):
        store.create(name)


def test_store_select_requires_a_registered_scene() -> None:
    store = SceneStore()
    store.create("original")
    store.create("second")

    selected = store.select("original")

    assert selected is store.get(), "select must make the named scene current"
    with pytest.raises(KeyError, match="not loaded in this session"):
        store.select("never-created")


def test_register_makes_a_scene_current() -> None:
    store = SceneStore()

    registered = store.register(VoxelScene("adopted"))

    assert store.get() is registered, "register must adopt the scene and make it current"


def test_from_dict_rejects_invalid_active_layer() -> None:
    data = VoxelScene("valid").to_dict()
    data["active_layer"] = -1

    with pytest.raises(ValueError, match="active_layer"):
        VoxelScene.from_dict(data)


def test_from_dict_rejects_invalid_palette_channel() -> None:
    data = VoxelScene("valid").to_dict()
    data["palette"] = {"1": [256, 0, 0]}

    with pytest.raises(ValueError, match="palette"):
        VoxelScene.from_dict(data)


@pytest.mark.parametrize("channel", [1.9, True, "1"])
def test_from_dict_rejects_coercible_rgb_channels(channel: Any) -> None:
    data = VoxelScene("valid").to_dict()
    data["palette"] = {"1": [channel, 0, 0]}

    with pytest.raises(ValueError, match="palette"):
        VoxelScene.from_dict(data)


@pytest.mark.parametrize("name", [None, ["a"], {"a": 1}, 7])
def test_from_dict_rejects_non_text_scene_name(name: Any) -> None:
    data = VoxelScene("valid").to_dict()
    data["name"] = name

    with pytest.raises(ValueError, match="scene name"):
        VoxelScene.from_dict(data)


def test_place_rejects_unknown_colour_without_mutating_scene() -> None:
    scene = VoxelScene("valid")

    with pytest.raises(ValueError, match="colour"):
        scene.place(0, 0, 0, "not-a-colour")

    assert scene.block_count() == 0, "a rejected placement must not mutate the scene"


@pytest.fixture
def empty_server_store(monkeypatch: pytest.MonkeyPatch) -> SceneStore:
    """Replace the module-level scene registry and bridge sync for one test."""
    replacement = SceneStore()
    monkeypatch.setattr(server, "store", replacement)
    monkeypatch.setattr(server, "_sync_bridge", lambda _scene: None)
    return replacement


def test_fill_box_rejects_more_than_limit_without_mutation(empty_server_store: SceneStore) -> None:
    empty_server_store.create("bounded")

    with pytest.raises(ValueError, match="100,000"):
        server.voxelforge_fill_box(0, 100_000, 0, 0, 0, 0)

    assert empty_server_store.get().block_count() == 0, "a rejected fill_box must not mutate the scene"


def test_place_many_rejects_more_than_limit_without_mutation(empty_server_store: SceneStore) -> None:
    empty_server_store.create("bounded")
    blocks = [[index, 0, 0, "1"] for index in range(100_001)]

    with pytest.raises(ValueError, match="100,000"):
        server.voxelforge_place_many(json.dumps(blocks))

    assert empty_server_store.get().block_count() == 0, "a rejected place_many must not mutate the scene"


def test_place_many_rejects_oversized_payload_before_decoding(empty_server_store: SceneStore) -> None:
    empty_server_store.create("bounded")
    oversized = "[" + ("0," * server.MAX_BLOCKS_JSON_CHARS)

    with pytest.raises(ValueError, match="at most"):
        server.voxelforge_place_many(oversized)

    assert empty_server_store.get().block_count() == 0, "an oversized payload must be rejected without mutation"


def test_basic_agent_scene_workflow(
    empty_server_store: SceneStore,
    monkeypatch: pytest.MonkeyPatch,
    scene_directory: Path,
) -> None:
    assert "basic" in server.voxelforge_create_scene("basic"), "create_scene must name the new scene"
    assert "วาง" in server.voxelforge_place_block(0, 0, 0, "2"), "place_block must confirm the placement"
    assert "เติม" in server.voxelforge_fill_box(1, 2, 0, 0, 0, 0, "3"), "fill_box must confirm the fill"
    assert empty_server_store.get().block_count() == 3, "place_block and fill_box must each add their voxels"
    assert "บันทึก" in server.voxelforge_save(), "save must confirm the file it wrote"

    monkeypatch.setattr(server, "store", SceneStore())
    assert "โหลด" in server.voxelforge_load("basic"), "load must confirm the scene it read"
    assert server.store.get().block_count() == 3, "a reloaded scene must keep its voxels"


def test_export_contains_required_chunks_in_order(tmp_path: Path) -> None:
    scene = VoxelScene("chunks")
    scene.place(2, 3, 4, "2")
    path = export_vox(scene, tmp_path / "chunks.vox")
    data = path.read_bytes()

    assert data.index(b"SIZE") < data.index(b"XYZI") < data.index(b"RGBA"), (
        "VOX children must be written SIZE, then XYZI, then RGBA"
    )
    chunks = child_chunks(data)
    assert struct.unpack("<III", chunks[b"SIZE"]) == (1, 1, 1), "SIZE must span the visible bounding box"
    assert struct.unpack_from("<I", chunks[b"XYZI"])[0] == 1, "XYZI must hold one voxel per visible block"


@pytest.mark.parametrize("hex_colour", ["#123456", "#000000"])
def test_export_preserves_hex_colour_through_round_trip(tmp_path: Path, hex_colour: str) -> None:
    scene = VoxelScene("colour")
    scene.place(0, 0, 0, hex_colour)

    loaded = import_vox(export_vox(scene, tmp_path / "colour.vox"))
    colour_key = loaded.layer.blocks[(0, 0, 0)]

    assert loaded.resolve_color(colour_key) == scene.resolve_color(hex_colour), (
        "an exported colour must survive a round trip through the palette"
    )


def test_export_rejects_unrepresentable_dimension(tmp_path: Path) -> None:
    scene = VoxelScene("wide")
    scene.place(0, 0, 0, "1")
    scene.place(256, 0, 0, "1")

    with pytest.raises(ValueError, match="256"):
        export_vox(scene, tmp_path / "wide.vox")


def test_export_rejects_overlapping_visible_layers(tmp_path: Path) -> None:
    scene = VoxelScene("overlap")
    scene.place(0, 0, 0, "1")
    scene.add_layer("upper")
    scene.place(0, 0, 0, "2", layer_index=1)

    with pytest.raises(ValueError, match="overlap"):
        export_vox(scene, tmp_path / "overlap.vox")
