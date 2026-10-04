"""Local bridge for the agent status light.

Owns the board's serial port (only one program can open it at a time) and serves:
  GET  /                 the mirror web app (web/matrix.html)
  GET  /api/status       board link, displayed agent states, and tracked sessions
  POST /api/session      from agent hooks: {"agent","session","state","ts","cwd","event"}
  POST /api/state        manual override: {"agent": "codex|claude|opencode|cline|all", "state": "working|..."}

Run:  python host/bridge.py            then open http://localhost:8765/
(Agent hooks start it automatically if it isn't running.)

Each agent's most urgent session drives its matrix symbol. The board chooses which
agent to show, keeps its identity border, and detects a missed bridge heartbeat.
"""
import argparse
import json
import math
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import serial
from serial.tools import list_ports
from runtime_config import CONFIG_PATH, VERSION, load_config
from board_port import find_port
from session_process import claude_owner, owner_alive, plugin_owner
from cline_desktop import ClineDesktop

ESPRESSIF_VID = 0x303A
MATRIX_PID = 0x826E
AGENTS = ("codex", "claude", "opencode", "cline")
STATES = ("working", "needs_input", "completed", "error", "idle", "off", "disconnected")
SESSION_STATES = ("working", "needs_input", "completed", "error", "idle", "ended")
PRIORITY = ("error", "needs_input", "working", "completed", "idle")  # most urgent first
# A session that stops reporting decays to idle: covers interrupts, crashes, and
# permission prompts dismissed without a follow-up event.
STALE_S = {"working": 15 * 60, "needs_input": 60 * 60, "completed": 30, "error": 30 * 60}
PROCESS_POLL_S = 2.0
PLUGIN_LEASE_S = 20.0
FORGET_S = 6 * 3600
MANUAL_HOLD_S = 60
HEARTBEAT_S = 6
POLL_S = 0.25
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class Board:
    """Serial link to the light. All port access goes through one lock."""

    def __init__(self, port=None):
        self.forced_port = port
        self.serial_number = load_config()["serial_number"]
        self.ser = None
        self.lock = threading.Lock()
        self.on_reconnect = None
        self.status = {"connected": False, "port": None, "version": None, "error": "not connected yet",
                       "agents": {a: None for a in AGENTS}, "updated": None,
                       "display": None}

    def _find_port(self):
        return find_port(self.serial_number, self.forced_port)

    def _open(self):
        port = self._find_port()
        if not port:
            raise serial.SerialException("configured ESP32-S3-Matrix not found")
        self.ser = serial.Serial(port, 115200, timeout=0.3)
        self.status["port"] = port
        if self._cmd("ping") != "pong agent-matrix-v3":
            raise serial.SerialException("port did not identify as agent-matrix-v3")
        self._cmd("heartbeat {}".format(HEARTBEAT_S))
        if self.on_reconnect:
            self.on_reconnect()

    def _cmd(self, line):
        self.ser.reset_input_buffer()
        self.ser.write((line + "\n").encode())
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:  # skip echoes / stray console output
            got = self.ser.readline().decode(errors="replace").strip()
            if got.startswith(("ok", "err", "pong")):
                return got
        raise serial.SerialException("no reply to {!r} - is code.py running?".format(line))

    def command(self, line):
        with self.lock:
            try:
                if self.ser is None:
                    self._open()
                reply = self._cmd(line)
                self._apply_status(self._cmd("status"))
                return reply
            except (serial.SerialException, OSError) as e:
                self._drop(e)
                raise

    def _apply_status(self, reply):
        fields = dict(kv.split("=", 1) for kv in reply.split()[1:] if "=" in kv)
        if not reply.startswith("ok ") or fields.get("version") != "agent-matrix-v3":
            raise serial.SerialException("invalid matrix status reply")
        if any(fields.get(a) not in STATES for a in AGENTS):
            raise serial.SerialException("missing agent state in matrix reply")
        try:
            display = {"agent": fields["shown"], "state": fields["display_state"],
                       "phase": float(fields["phase"]), "demo_s": int(fields["demo"]),
                       "rotation": int(fields["rotation"]), "brightness": float(fields["brightness"])}
        except (KeyError, ValueError) as exc:
            raise serial.SerialException("invalid display metadata") from exc
        self.status.update(connected=True, error=None, version=fields.get("version"),
                           updated=time.time(), display=display,
                           agents={a: fields.get(a) for a in AGENTS})

    def _drop(self, err):
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.status.update(connected=False, error=str(err), display=None,
                           agents={a: None for a in AGENTS})


class Sessions:
    """Per-session states reported by agent hooks, folded into one state per agent."""

    def __init__(self, owner_lookup=claude_owner, owner_check=owner_alive):
        self.lock = threading.Lock()
        self.by_agent = {a: {} for a in AGENTS}
        self.owner_lookup, self.owner_check = owner_lookup, owner_check
        self.last_process_check = -float("inf")

    def update(self, agent, sid, state, ts, cwd="", event="", pid=None):
        with self.lock:
            sessions = self.by_agent[agent]
            if sid not in sessions and len(sessions) >= 512:
                expired = [key for key, value in sessions.items() if time.time() - value['ts'] > FORGET_S]
                for key in expired:
                    del sessions[key]
                if len(sessions) >= 512:
                    raise ValueError('Session limit reached')
            cur = sessions.get(sid)
            if cur and ts < cur["ts"]:
                return False  # async hooks can land out of order; keep the newer report
            sessions[sid] = {"state": state, "ts": ts, "cwd": cwd or (cur or {}).get("cwd", ""),
                             "event": event, "seen": time.time(),
                             "owner": (plugin_owner(agent, pid) if pid else None) or
                                      (None if event == "SessionStart" else (cur or {}).get("owner"))}
            return True

    def reap_closed(self, now, monotonic_now=None):
        """Only confirmed process exits end sessions; permission errors do not."""
        mono = time.monotonic() if monotonic_now is None else monotonic_now
        with self.lock:
            if mono - self.last_process_check < PROCESS_POLL_S:
                return
            self.last_process_check = mono
            for agent, sid, session in [(a, sid, s) for a in AGENTS
                                        for sid, s in self.by_agent[a].items()]:
                if session["state"] == "ended":
                    continue
                if agent in ("opencode", "cline") and now - session.get("seen", now) > PLUGIN_LEASE_S:
                    session.update(state="ended", ts=now, event="PluginDisconnected")
                    continue
                if agent == "claude" and session.get("owner") is None:
                    session["owner"] = self.owner_lookup(sid)
                owner = session.get("owner")
                if owner and self.owner_check(owner) is False:
                    session.update(state="ended", ts=now, event="ProcessExit")

    @staticmethod
    def _effective(s, now):
        limit = STALE_S.get(s["state"])
        return "idle" if limit and now - s["ts"] > limit else s["state"]

    def aggregate(self, agent, now):
        with self.lock:
            sessions = self.by_agent[agent]
            for sid in [k for k, s in sessions.items() if now - s["ts"] > FORGET_S]:
                del sessions[sid]
            states = {self._effective(s, now) for s in sessions.values() if s["state"] != "ended"}
        return next((p for p in PRIORITY if p in states), "off")

    def snapshot(self, now):
        with self.lock:
            return {agent: sorted(
                ({"id": sid[:8], "label": os.path.basename(s["cwd"].rstrip("\\/")) or "session",
                  "state": self._effective(s, now), "event": s["event"], "age_s": int(now - s["ts"])}
                 for sid, s in sessions.items() if s["state"] != "ended"),
                key=lambda r: (PRIORITY.index(r["state"]) if r["state"] in PRIORITY else 99, r["age_s"]))
                for agent, sessions in self.by_agent.items()}


class Driver:
    """Pushes each agent's aggregate state to the board when it changes."""

    def __init__(self, board, sessions):
        self.board, self.sessions = board, sessions
        self.pushed = {}
        self.manual_until = {a: 0.0 for a in AGENTS}
        self.lock = threading.RLock()
        self.wake = threading.Event()
        board.on_reconnect = self.pushed.clear  # board may have rebooted: re-send everything

    def set_manual(self, agent, state):
        with self.lock:
            reply = self.board.command("{} {}".format(agent, state))
            if reply.startswith("ok"):
                self.manual(agent)
            return reply

    def manual(self, agent):
        for a in (AGENTS if agent == "all" else (agent,)):
            self.manual_until[a] = time.time() + MANUAL_HOLD_S
            self.pushed.pop(a, None)

    def tick(self):
        with self.lock:
            self._tick()

    def _tick(self):
        now = time.time()
        self.sessions.reap_closed(now)
        try:
            for agent in AGENTS:
                if now < self.manual_until[agent]:
                    continue
                want = self.sessions.aggregate(agent, now)
                if self.pushed.get(agent) != want:
                    if self.board.command("{} {}".format(agent, want)).startswith("ok"):
                        self.pushed[agent] = want
            self.board.command("status")
        except (serial.SerialException, OSError):
            pass  # board.status already records the error; retry next tick


class Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second process bind a port that's already
    # listening, which would defeat the duplicate-bridge guard in main().
    allow_reuse_address = False
    daemon_threads = True


def make_handler(board, sessions, driver):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def _local_request(self):
            port = self.server.server_address[1]
            hosts = ('127.0.0.1:{}'.format(port), 'localhost:{}'.format(port))
            if self.headers.get('Host', '').lower() not in hosts:
                self._json(403, {'error': 'Local host header required'})
                return False
            origin = self.headers.get('Origin')
            if origin is not None and origin not in tuple('http://' + h for h in hosts):
                self._json(403, {'error': 'Cross-origin requests are not supported'})
                return False
            return True

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('Transfer encoding is not supported')
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('Content-Type must be application/json')
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= 16384:
                raise ValueError('Request must contain 1..16384 bytes')
            data = json.loads(self.rfile.read(n))
            if not isinstance(data, dict):
                raise ValueError('Body must be a JSON object')
            return data

        def _snapshot(self):
            now = time.time()
            return {"bridge": "ok", "app": "agent-matrix", "version": VERSION,
                    "board": {k: board.status[k] for k in ("connected", "port", "version", "error", "updated")},
                    "agents": board.status["agents"],
                    "display": board.status["display"],
                    "sessions": sessions.snapshot(now),
                    "manual_s": {a: max(0, int(driver.manual_until[a] - now)) for a in AGENTS}}

        def do_GET(self):
            if not self._local_request():
                return
            if self.path in ("/", "/index.html"):
                body = (WEB_DIR / "matrix.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/status":
                self._json(200, self._snapshot())
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._local_request():
                return
            try:
                data = self._body()
            except (ValueError, OSError) as exc:
                return self._json(400, {"error": str(exc)})
            if self.path == "/api/session":
                return self._session(data)
            if self.path == "/api/state":
                return self._manual(data)
            if self.path == "/api/display":
                return self._display(data)
            return self._json(404, {"error": "not found"})

        def _session(self, d):
            agent, st, sid = d.get("agent"), d.get("state"), d.get("session")
            if agent not in AGENTS or st not in SESSION_STATES or not isinstance(sid, str) or not 1 <= len(sid) <= 256:
                return self._json(400, {"error": "need agent {}, state {}, session".format(AGENTS, SESSION_STATES)})
            try:
                ts = d.get('ts', time.time())
                if isinstance(ts, bool) or not isinstance(ts, (int, float)):
                    raise ValueError('Timestamp must be a number')
                if not math.isfinite(ts) or not 0 < ts <= time.time() + 60:
                    raise ValueError('Timestamp must be finite, positive, and not in the future')
                cwd, event, pid = d.get('cwd', ''), d.get('event', ''), d.get('pid')
                if not isinstance(cwd, str) or len(cwd) > 4096 or not isinstance(event, str) or len(event) > 128:
                    raise ValueError('Invalid cwd or event')
                if pid is not None and (type(pid) is not int or not 0 < pid <= 2**32-1):
                    raise ValueError('Invalid process ID')
                applied = sessions.update(agent, sid, st, ts, cwd, event, pid)
            except (TypeError, ValueError, OverflowError):
                return self._json(400, {'error': 'Invalid session metadata or session limit reached'})
            driver.wake.set()
            return self._json(200, {"ok": True, "applied": applied})

        def _manual(self, d):
            agent, st = str(d.get("agent", "")).lower(), str(d.get("state", "")).lower()
            if agent not in AGENTS + ("all",) or st not in STATES:
                return self._json(400, {"error": "agent must be one of {} and state one of {}".format(AGENTS + ("all",), STATES)})
            try:
                reply = driver.set_manual(agent, st)
            except (serial.SerialException, OSError) as e:
                return self._json(503, dict(self._snapshot(), error=str(e)))
            code = 200 if reply.startswith("ok") else 502
            return self._json(code, dict(self._snapshot(), reply=reply))

        def _display(self, d):
            command = d.get("command")
            value = d.get("value")
            if command == "demo" and type(value) is int and 0 <= value <= 120:
                line = "demo " + str(value)
            elif command == "rotate" and type(value) is int and value in (0, 90, 180, 270):
                line = "rotate " + str(value)
            else:
                return self._json(400, {"error": "expected demo 0..120 or rotate 0/90/180/270"})
            try:
                reply = board.command(line)
            except (serial.SerialException, OSError) as exc:
                return self._json(503, {"error": str(exc)})
            return self._json(200 if reply.startswith("ok") else 502,
                              dict(self._snapshot(), reply=reply))

        def log_message(self, fmt, *args):  # keep the console readable; status polls are noisy
            # pythonw has no stderr. Logging must not break a successful POST.
            if sys.stderr is not None and "/api/status" not in (args[0] if args else ""):
                super().log_message(fmt, *args)

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="serial port (default: auto-detect the ESP32)")
    ap.add_argument("--http", type=int, default=load_config()["http_port"])
    a = ap.parse_args()

    board, sessions = Board(a.port), Sessions()
    driver = Driver(board, sessions)
    # Bind before touching the serial port so a duplicate bridge exits without
    # stealing the port from the one already running.
    try:
        server = Server(("127.0.0.1", a.http), make_handler(board, sessions, driver))
    except OSError:
        raise SystemExit("Port {} is busy - is another bridge already running?".format(a.http))

    def poller():
        while True:
            driver.tick()
            driver.wake.wait(POLL_S)
            driver.wake.clear()

    if load_config().get('cline_desktop', False):
        threading.Thread(target=ClineDesktop(sessions.update).run, daemon=True).start()
    threading.Thread(target=poller, daemon=True).start()
    print("Agent light bridge on http://localhost:{}/  (Ctrl+C to stop)".format(a.http))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
