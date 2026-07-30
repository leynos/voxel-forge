"""Contract tests for hosting the web editor as a supervised Bun process.

These cover roadmap step 1.2: the editor travels inside the wheel, is
resolvable from both checkout and installed layouts, and is served by Bun
on a discoverable port.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # tests spawn Bun with validated arguments and shell=False
import tomllib
import typing as typ
import urllib.request
from pathlib import Path

import pytest

from voxel_forge.editor_runtime import editor_entrypoint, editor_package_root

BUN = shutil.which("bun")
STARTUP_TIMEOUT_SECONDS = 30.0


def test_editor_entrypoint_resolves_in_checkout() -> None:
    """A repository checkout must resolve the Bun entry point."""
    entrypoint = editor_entrypoint()

    assert entrypoint.name == "serve.ts", "entry point must be the Bun server script"
    assert entrypoint.is_file(), "entry point must exist in a checkout"


def test_editor_package_root_contains_manifest_and_lockfile() -> None:
    """The resolved package root must carry package.json and bun.lock."""
    root = editor_package_root()

    assert (root / "package.json").is_file(), "package root must contain package.json"
    assert (root / "bun.lock").is_file(), "package root must contain the Bun lockfile"


def test_wheel_bundles_the_editor() -> None:
    """The wheel build must force-include the editor's runtime files."""
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"][
        "force-include"
    ]

    packaged = set(force_include.values())
    for required in (
        "voxel_forge/editor/index.html",
        "voxel_forge/editor/src",
        "voxel_forge/editor/serve.ts",
        "voxel_forge/editor/package.json",
        "voxel_forge/editor/bun.lock",
    ):
        assert required in packaged, f"wheel must bundle {required}"
    for source in force_include:
        assert Path(source).exists(), f"force-included source {source} must exist"


def _read_listening_port(process: subprocess.Popen[str]) -> int:
    """Read the structured listening event from the editor's stdout."""
    stdout = process.stdout
    assert stdout is not None, "editor stdout must be captured"
    line = stdout.readline()
    event = json.loads(line)
    assert event.get("event") == "listening", f"unexpected editor event: {event!r}"
    return int(event["port"])


@pytest.mark.skipif(BUN is None, reason="bun is not installed")
def test_bun_serves_the_editor_on_an_ephemeral_port() -> None:
    """Bun must bind an ephemeral port, report it, and serve the editor."""
    env = {
        "PATH": "/usr/bin:/bin",
        "VOXELFORGE_EDITOR_PORT": "0",
        "VOXELFORGE_BRIDGE_WS_PORT": "18765",
        "VOXELFORGE_BRIDGE_HTTP_PORT": "18766",
    }
    with subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]  # fixed executable and script path; shell=False
        [typ.cast("str", BUN), str(editor_entrypoint())],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=editor_package_root(),
    ) as process:
        try:
            port = _read_listening_port(process)

            with socket.create_connection(("127.0.0.1", port), timeout=5):
                pass
            with urllib.request.urlopen(  # fixed loopback URL scheme
                f"http://127.0.0.1:{port}/", timeout=10
            ) as response:
                page = response.read().decode("utf-8")
            with urllib.request.urlopen(  # fixed loopback URL scheme
                f"http://127.0.0.1:{port}/bridge.json", timeout=10
            ) as response:
                bridge = json.loads(response.read())

            assert "VoxelForge" in page, "served page must be the editor"
            assert bridge["wsUrl"].endswith(":18765"), (
                "bridge.json must republish the WebSocket port from the environment"
            )
            assert bridge["httpUrl"].endswith(":18766"), (
                "bridge.json must republish the HTTP port from the environment"
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
