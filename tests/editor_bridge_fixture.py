"""Serve an isolated in-memory bridge for the rendered editor regression.

The Node browser test starts this helper, reads its ephemeral ports from stdout,
and terminates only this child when finished. No scene files are created.
"""

import asyncio
import json
import sys

from websockets.asyncio.server import serve

from voxel_forge import bridge
from voxel_forge.model import SceneStore


async def main(editor_origin: str) -> None:
    """Run real bridge handlers with a lower voxel and an empty active layer.

    Parameters
    ----------
    editor_origin : str
        Origin of the test-owned static server, allowed for HTTP and WebSocket.

    Examples
    --------
    Run ``uv run python tests/editor_bridge_fixture.py http://127.0.0.1:5173``
    to print the allocated ports and keep serving until the child is stopped.
    """
    shared = SceneStore()
    scene = shared.create("browser-regression")
    scene.place(0, 0, 0, "2")
    scene.add_layer("Active upper")
    scene.active_layer = 1
    bridge.use_store(shared)
    bridge.ALLOWED_EDITOR_ORIGINS = frozenset({editor_origin})
    bridge._bridge_loop = asyncio.get_running_loop()
    http = await asyncio.start_server(bridge._http_handler, "127.0.0.1", 0)
    async with (
        http,
        serve(
            bridge._ws_handler, "127.0.0.1", 0, origins=[None, editor_origin]
        ) as websocket,
    ):
        ports = {
            "http": http.sockets[0].getsockname()[1],
            "ws": websocket.sockets[0].getsockname()[1],
        }
        print(json.dumps(ports), flush=True)
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
