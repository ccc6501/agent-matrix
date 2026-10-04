"""Agent hook -> status light bridge.

Called by Claude Code and Codex hooks with the hook payload (JSON) on stdin:
    python agent_hook.py claude
    python agent_hook.py codex

Maps the hook event to a light state and reports it to the bridge, starting the bridge
in the background if it isn't running. It must never get in the agent's way: it prints
nothing (some hook events feed stdout back to the model), swallows every error, and
always exits 0.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from runtime_config import LOCAL, bridge_url

BRIDGE = bridge_url()
BRIDGE_SCRIPT = Path(__file__).resolve().parent / "bridge.py"
LOG = LOCAL / "agent_hook.log"

# hook_event_name -> state. Events not listed are ignored.
EVENTS = {
    "claude": {
        "SessionStart": "idle",
        "UserPromptSubmit": "working",
        "PreToolUse": "needs_input",        # settings only route AskUserQuestion / ExitPlanMode here
        "PermissionRequest": "needs_input",
        "Elicitation": "needs_input",
        "ElicitationResult": "working",
        "PostToolUse": "working",           # also clears needs_input once a prompt is answered
        "PostToolUseFailure": "working",
        "Stop": "completed",
        "StopFailure": "error",
        "SessionEnd": "ended",
    },
    "codex": {
        "SessionStart": "idle",
        "UserPromptSubmit": "working",
        "PermissionRequest": "needs_input",
        "PostToolUse": "working",
        "Stop": "completed",
        "Interrupt": "idle",
        "SessionEnd": "ended",
    },
}


def post(payload, timeout):
    req = urllib.request.Request(BRIDGE + "/api/session", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=timeout).read()


def start_bridge():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw if pythonw.exists() else sys.executable)
    flags = 0
    if os.name == "nt":
        # Detach fully so the bridge outlives this hook (and the agent's job object if allowed).
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              close_fds=True, cwd=str(BRIDGE_SCRIPT.parent))
    try:
        subprocess.Popen([exe, str(BRIDGE_SCRIPT)], creationflags=(flags | 0x01000000) if os.name == "nt" else 0, **kw)  # BREAKAWAY_FROM_JOB
    except OSError:
        subprocess.Popen([exe, str(BRIDGE_SCRIPT)], creationflags=flags, **kw)


def log(msg):
    try:
        LOCAL.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > 1024 * 1024:
            LOG.replace(LOG.with_suffix(".previous.log"))
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("{} {}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def main():
    ts = time.time()  # taken first: async hooks may finish out of order, the bridge keeps the newest
    agent = sys.argv[1] if len(sys.argv) > 1 else ""
    raw = sys.stdin.buffer.read() if sys.stdin else b""
    try:
        # utf-8-sig: Windows shells may prepend a BOM when piping to a native program
        data = json.loads(raw.decode("utf-8-sig", "replace").strip() or "{}")
    except ValueError:
        log("{}: invalid hook JSON (payload omitted)".format(agent))
        data = {}
    if not isinstance(data, dict):
        return
    event = data.get("hook_event_name", "")
    if agent == "--forward":
        # Local plugin fallback: only status metadata reaches the bridge.
        if data.get("agent") not in ("opencode", "cline"):
            return
        if data.get("state") not in ("working", "needs_input", "completed", "error", "idle", "ended"):
            return
        payload = {k: data[k] for k in ("agent", "session", "state", "ts", "cwd", "event", "pid") if k in data}
        try:
            post(payload, timeout=1)
        except (urllib.error.URLError, OSError):
            if payload["state"] == "ended":
                return
            start_bridge()
            for _ in range(10):
                time.sleep(0.3)
                try:
                    post(payload, timeout=1)
                    break
                except (urllib.error.URLError, OSError):
                    pass
        return
    state = EVENTS.get(agent, {}).get(event)
    if not state:
        return
    payload = {"agent": agent, "session": data.get("session_id") or "unknown", "state": state,
               "ts": ts, "cwd": data.get("cwd", ""), "event": event}
    try:
        post(payload, timeout=1)
        return
    except (urllib.error.URLError, OSError):
        pass
    if event == "SessionEnd":
        # A busy/reconnecting bridge should not lose the only explicit close event.
        # Stay within the 3-second hook budget; never start a bridge just to end.
        for _ in range(3):
            time.sleep(0.1)
            try:
                post(payload, timeout=0.25)
                return
            except (urllib.error.URLError, OSError):
                pass
        log("SessionEnd could not reach bridge for " + agent)
        return
    try:
        start_bridge()
        for _ in range(10):
            time.sleep(0.3)
            try:
                post(payload, timeout=1)
                return
            except (urllib.error.URLError, OSError):
                continue
        log("bridge did not come up for {} {}".format(agent, event))
    except Exception as e:
        log("start_bridge failed: " + type(e).__name__)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never let a status light break an agent session
        log("hook error: " + type(e).__name__)
    sys.exit(0)
