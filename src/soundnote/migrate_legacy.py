"""One-time shutdown of the previous local service, before opening the GUI."""

import json
import os
from pathlib import Path
import signal
import urllib.error
import urllib.request


def stop_legacy(project):
    # Verify both application identity and workspace before stopping anything.
    # The new desktop app itself does not start an HTTP server.
    project = str(Path(project).resolve())
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8765/api/health", timeout=1) as response:
            info = json.load(response)
        if info.get("app") != "soundnote-local" or info.get("workspace") != project:
            return False
        pid = int(info["pid"])
        if pid <= 1 or pid == os.getpid():
            return False
        os.kill(pid, signal.SIGTERM)
        return True
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        return False
