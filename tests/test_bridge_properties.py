"""Generated properties for bridge boundaries and process supervision."""

from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from voxel_forge import bridge, orchestration
from voxel_forge.bridge_http import _parse_request_head
from voxel_forge.orchestration import _parse_listening_port


@given(st.lists(st.integers(min_value=1, max_value=65535), max_size=40))
def test_editor_origin_registry_tracks_generated_port_sets(ports: list[int]) -> None:
    """Every registered port has both hosts and revocation preserves 5173."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(bridge, "_editor_origin_ports", {5173})

        for port in ports:
            bridge.register_editor_origin(port)

        registered_ports = {5173, *ports}
        expected_origins = {
            f"http://{host}:{port}"
            for port in registered_ports
            for host in ("127.0.0.1", "localhost")
        }
        assert bridge.allowed_origins() == expected_origins, (
            "each registered port must produce both supported host origins"
        )

        for port in ports:
            bridge.unregister_editor_origin(port)

        assert bridge.allowed_origins() == {
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        }, "revoking generated ports must preserve the standalone editor origin"


@given(st.integers(min_value=0, max_value=2**63 - 1))
def test_http_content_length_round_trips_nonnegative_integers(
    content_length: int,
) -> None:
    """The request parser preserves every nonnegative integer length."""
    request = _parse_request_head(
        f"POST /scene HTTP/1.1\r\nContent-Length: {content_length}\r\n\r\n"
    )

    assert request.method == "POST", "preserve the parsed request method"
    assert request.path == "/scene", "preserve the parsed request path"
    assert request.content_length == content_length, (
        "preserve every nonnegative content length"
    )


@given(st.integers(min_value=-(2**63), max_value=-1))
def test_http_content_length_rejects_generated_negative_integers(
    content_length: int,
) -> None:
    """Negative request lengths never enter body-reading logic."""
    with pytest.raises(ValueError, match="non-negative"):
        _parse_request_head(
            f"POST /scene HTTP/1.1\r\nContent-Length: {content_length}\r\n\r\n"
        )


@given(st.integers(min_value=1, max_value=65535))
def test_listening_event_parser_round_trips_generated_ports(port: int) -> None:
    """Valid Bun readiness events preserve every usable bound port."""
    event = json.dumps({"event": "listening", "port": port})

    assert _parse_listening_port(event) == port, (
        "preserve the port reported by a valid readiness event"
    )


class _ProcessState:
    """Minimal process double exposing the lifecycle used by supervision."""

    def __init__(self, pid: int) -> None:
        """Start the process in the live state expected before supervision."""
        self.pid = pid
        self.is_running = True

    def poll(self) -> int | None:
        """Return the same live-or-exited signal as ``Popen.poll``."""
        return None if self.is_running else 0


@given(
    st.lists(
        st.tuples(st.integers(min_value=0, max_value=7), st.booleans()),
        max_size=60,
    )
)
def test_supervision_registry_matches_generated_process_lifecycles(
    operations: list[tuple[int, bool]],
) -> None:
    """Every supervision pass registers live handles and prunes exited ones."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(orchestration, "_supervised", {})
        processes = {pid: _ProcessState(pid) for pid in range(8)}
        observed: set[int] = set()

        for pid, should_exit in operations:
            process = processes[pid]
            if should_exit:
                process.is_running = False
            observed.add(pid)

            orchestration.supervise(process)

            expected = {
                known_pid for known_pid in observed if processes[known_pid].is_running
            }
            assert set(orchestration._supervised) == expected, (
                "supervision must retain live children and prune exited children"
            )
