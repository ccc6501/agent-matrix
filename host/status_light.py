"""PC-side control for the USB agent status light.

Usage:
  python status_light.py ports                      list candidate serial ports
  python status_light.py ping
  python status_light.py codex working              set one agent (codex | claude | opencode | cline | all)
  python status_light.py demo                       cycle every state on all four agents
  python status_light.py <cmd> --port COM7         force a port (direct serial only)

If the bridge (host/bridge.py) is running it owns the serial port, so commands are
sent through it automatically; otherwise they go straight over the console port
(close any serial monitor first).

States: working, needs_input, completed, error, idle, off, disconnected
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import serial
from serial.tools import list_ports

ESPRESSIF_VID = 0x303A
STATES = ("working", "needs_input", "completed", "error", "idle", "off", "disconnected")
from runtime_config import bridge_url, load_config
from board_port import find_port as select_port

BRIDGE = bridge_url()


def find_port():
    """The board's CircuitPython console port (commands share it with the REPL)."""
    port = select_port(load_config()["serial_number"])
    if not port:
        sys.exit("Matrix not found. Connect it and run tools/doctor.py.")
    return port


class SerialLink:
    def __init__(self, port):
        self.ser = serial.Serial(port, 115200, timeout=0.5)

    def send(self, line):
        self.ser.reset_input_buffer()
        self.ser.write((line + "\n").encode())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:  # skip echoes / stray console output
            got = self.ser.readline().decode(errors="replace").strip()
            if got.startswith(("ok", "err", "pong")):
                return got
        return ""

    def close(self):
        self.ser.close()


class BridgeLink:
    """Maps the serial text protocol onto the bridge's HTTP API."""

    @staticmethod
    def available():
        try:
            urllib.request.urlopen(BRIDGE + "/api/status", timeout=0.5).read()
            return True
        except (urllib.error.URLError, OSError):
            return False

    def _call(self, path, body=None):
        req = urllib.request.Request(BRIDGE + path, method="POST" if body else "GET",
                                     data=json.dumps(body).encode() if body else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read() or b"{}")

    def send(self, line):
        parts = line.split()
        if parts and parts[0] in ("demo", "rotate"):
            value = int(parts[1]) if len(parts) > 1 else 72
            d = self._call("/api/display", {"command": parts[0], "value": value})
            return d.get("reply") or "err " + str(d.get("error"))
        if len(parts) == 2 and parts[1] in STATES:
            d = self._call("/api/state", {"agent": parts[0], "state": parts[1]})
            return d.get("reply") or "err " + str(d.get("error"))
        if parts and parts[0] in ("ping", "status"):
            d = self._call("/api/status")
            b = d["board"]
            if not b["connected"]:
                return "err board offline: " + str(b["error"])
            return "ok " + " ".join(k + "=" + str(v) for k, v in d["agents"].items()) + " version=" + str(b["version"]) + " (via bridge)"
        return "err bridge supports agent states, demo, rotate, ping and status"

    def close(self):
        pass


def send(link, line):
    resp = link.send(line)
    print("> {:<24} < {}".format(line, resp or "(no reply)"))
    return resp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("args", nargs="+")
    ap.add_argument("--port")
    a = ap.parse_args()

    if a.args[0] == "ports":
        for p in list_ports.comports():
            print(p.device, hex(p.vid or 0), p.location, p.description)
        return

    link = BridgeLink() if not a.port and BridgeLink.available() else SerialLink(a.port or find_port())
    try:
        if a.args[0] == "demo":
            send(link, " ".join(a.args) if len(a.args) > 1 else "demo 72")
        else:
            send(link, " ".join(a.args))
    finally:
        link.close()


if __name__ == "__main__":
    main()
