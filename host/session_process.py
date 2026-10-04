"""Associate Claude session IDs with local process identities, never window titles."""
import json
import os
from pathlib import Path

import psutil

SESSION_DIR = Path.home() / ".claude" / "sessions"


def plugin_owner(agent, pid):
    """Bind local plugin metadata to a verified agent process and birth time."""
    if agent not in ("opencode", "cline"):
        return None
    try:
        process = psutil.Process(int(pid))
        chain = [process] + process.parents()
        names = ({"opencode.exe", "opencode-cli.exe"} if agent == "opencode"
                 else {"cline-app.exe", "code-sidecar.exe", "cline.exe"})
        matches = [p for p in chain if p.name().lower() in names]
        # Watch the desktop root when present; sandbox children may be evicted
        # while idle, which does not mean the user's session has closed.
        owner = next((p for p in matches if p.name().lower() in
                      ("cline-app.exe", "opencode.exe")), None)
        owner = owner or (matches[0] if matches else None)
        return {"pid": owner.pid, "created": owner.create_time()} if owner else None
    except (ValueError, TypeError, psutil.Error, OSError):
        return None


def claude_owner(session_id):
    """Read only Claude's session registration metadata (not chat transcripts)."""
    try:
        paths = list(SESSION_DIR.glob("*.json"))
    except OSError:
        return None
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("sessionId") != session_id:
                continue
            domain = data.get("pidDomain", "")
            if os.name != "nt" or domain.lower() != "win32:" + os.environ.get("COMPUTERNAME", "").lower():
                continue  # Never interpret a remote host's PID as a local process.
            pid = int(data["pid"])
            # Windows FILETIME -> Unix timestamp. Birth time prevents PID-reuse bugs.
            created = int(data["procStart"]) / 10_000_000 - 11_644_473_600
            if pid > 0 and created > 0:
                return {"pid": pid, "created": created}
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue  # An atomic rewrite or unavailable record is not proof of exit.
    return None


def owner_alive(owner):
    """True = same process; False = exited/reused PID; None = cannot inspect."""
    try:
        process = psutil.Process(owner["pid"])
        if abs(process.create_time() - owner["created"]) > 0.02:
            return False
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except (psutil.AccessDenied, OSError):
        return None
