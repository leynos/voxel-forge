"""Start a fresh bridge with every documented fixed listener port unavailable."""

from __future__ import annotations

import json
import socket
import urllib.request

from voxel_forge import bridge


def main() -> None:
    """Occupy fixed ports, start a fresh bridge, and publish the observed result."""
    occupied: list[socket.socket] = []
    try:
        for port in (8765, 8766, 5173):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                sock.close()
            else:
                sock.listen(1)
                occupied.append(sock)
        assert occupied, "the fixture must hold at least one of the fixed ports"
        ws_port, http_port = bridge.start_bridge_background()
        with urllib.request.urlopen(  # fixed loopback URL scheme
            f"http://127.0.0.1:{http_port}/health", timeout=10
        ) as response:
            health = json.loads(response.read())
        print(
            json.dumps({
                "occupied": len(occupied),
                "ws_port": ws_port,
                "http_port": http_port,
                "health": health,
            })
        )
    finally:
        for sock in occupied:
            sock.close()


if __name__ == "__main__":
    main()
