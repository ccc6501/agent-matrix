"""Desktop entry point: reuse/start the hidden bridge, then open its web controls."""
import ctypes
import json
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from agent_hook import BRIDGE, log, start_bridge


def ready():
    try:
        with urllib.request.urlopen(BRIDGE + "/api/status", timeout=0.75) as response:
            data = json.load(response)
        return data.get("app") == "agent-matrix" and data.get("bridge") == "ok" and "board" in data and "agents" in data
    except (OSError, urllib.error.URLError, ValueError, AttributeError):
        return False


def main():
    if not ready():
        start_bridge()
        deadline = time.monotonic() + 10
        while not ready():
            if time.monotonic() >= deadline:
                raise RuntimeError("The status bridge did not start. Another application may be using the configured port.")
            time.sleep(0.25)
    if "--no-browser" not in sys.argv:
        if not webbrowser.open(BRIDGE + "/", new=2):
            raise RuntimeError("The bridge is running. Open http://127.0.0.1:8765/ in your browser.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("desktop launcher: " + str(exc))
        if "--no-browser" in sys.argv:
            raise
        ctypes.windll.user32.MessageBoxW(None, str(exc), "Agent Matrix", 0x10)
        sys.exit(1)
