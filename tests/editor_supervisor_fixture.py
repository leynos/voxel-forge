"""Keep a supervised editor alive until the test kills this Python parent."""

import json
import threading

from voxel_forge.orchestration import (
    EditorPorts,
    start_editor_process,
    supervise,
)

process, port = start_editor_process(EditorPorts(bridge_ws=1, bridge_http=2))
supervise(process)
print(json.dumps({"pid": process.pid, "port": port}), flush=True)
threading.Event().wait()
