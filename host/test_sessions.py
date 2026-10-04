import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import psutil
import bridge
import session_process


class SessionTests(unittest.TestCase):
    def test_plugin_disappearing_clears_without_killing_other_agents(self):
        sessions = bridge.Sessions()
        with patch.object(bridge.time, "time", return_value=100):
            sessions.update("cline", "one", "needs_input", 100)
            sessions.update("codex", "two", "working", 100)
        sessions.reap_closed(121, 0)
        self.assertEqual(sessions.aggregate("cline", 121), "off")
        self.assertEqual(sessions.aggregate("codex", 121), "working")

    def test_plugin_heartbeat_keeps_completion_time_and_closed_sessions_off(self):
        for agent in ("opencode", "cline"):
            sessions = bridge.Sessions(owner_check=lambda owner: False)
            with patch.object(bridge, "plugin_owner", return_value={"pid": 123, "created": 42}):
                sessions.update(agent, "one", "completed", 100, pid=123)
                sessions.update(agent, "one", "completed", 100, pid=123)
            self.assertEqual(sessions.aggregate(agent, 131), "idle")
            sessions.reap_closed(132, 0)
            self.assertEqual(sessions.aggregate(agent, 132), "off")
            self.assertFalse(sessions.update(agent, "one", "completed", 100))

    def sessions(self, check=lambda owner: True):
        return bridge.Sessions(lambda sid: {"pid": 123, "created": 42}, check)

    def test_completion_expires_after_thirty_seconds(self):
        sessions = self.sessions()
        sessions.update("claude", "one", "completed", 100)
        self.assertEqual(sessions.aggregate("claude", 129), "completed")
        self.assertEqual(sessions.aggregate("claude", 131), "idle")

    def test_no_sessions_and_explicit_end_are_off(self):
        sessions = self.sessions()
        self.assertEqual(sessions.aggregate("claude", 100), "off")
        sessions.update("claude", "one", "working", 100)
        sessions.update("claude", "one", "ended", 101, event="SessionEnd")
        self.assertEqual(sessions.aggregate("claude", 101), "off")
        self.assertEqual(sessions.snapshot(101)["claude"], [])
        self.assertFalse(sessions.update("claude", "one", "completed", 100.5))

    def test_one_closed_session_does_not_clear_other_agents_or_sessions(self):
        sessions = bridge.Sessions(lambda sid: {"pid": sid}, lambda o: o["pid"] != "closed")
        sessions.update("claude", "closed", "error", 100)
        sessions.update("claude", "open", "working", 100)
        sessions.update("codex", "codex", "working", 100)
        sessions.reap_closed(101, 0)
        self.assertEqual(sessions.aggregate("claude", 101), "working")
        self.assertEqual(sessions.aggregate("codex", 101), "working")
        self.assertEqual(len(sessions.snapshot(101)["claude"]), 1)
        self.assertEqual(sessions.by_agent["claude"]["closed"]["event"], "ProcessExit")

    def test_unknown_process_does_not_end_active_work(self):
        sessions = self.sessions(lambda o: None)
        sessions.update("claude", "one", "needs_input", 100)
        sessions.reap_closed(101, 0)
        self.assertEqual(sessions.aggregate("claude", 101), "needs_input")

    def test_resumed_session_gets_new_identity(self):
        sessions = self.sessions(lambda o: False)
        sessions.update("claude", "one", "working", 100)
        sessions.reap_closed(101, 0)
        self.assertEqual(sessions.aggregate("claude", 101), "off")
        sessions.owner_check = lambda o: True
        sessions.update("claude", "one", "idle", 102, event="SessionStart")
        sessions.reap_closed(103, 3)
        self.assertEqual(sessions.aggregate("claude", 103), "idle")

    def test_real_process_exit_and_pid_reuse(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.8)"],
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            owner = {"pid": child.pid, "created": psutil.Process(child.pid).create_time()}
            self.assertTrue(session_process.owner_alive(owner))
            self.assertFalse(session_process.owner_alive(dict(owner, created=owner["created"] - 10)))
            sessions = bridge.Sessions(lambda sid: owner, session_process.owner_alive)
            sessions.update("claude", "child", "completed", time.time())
            sessions.reap_closed(time.time(), 0)
            self.assertEqual(sessions.aggregate("claude", time.time()), "completed")
            child.wait(timeout=5)
            sessions.reap_closed(time.time(), 3)
            self.assertEqual(sessions.aggregate("claude", time.time()), "off")
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)

    def test_session_registry_exact_match_and_bad_data(self):
        scratch = Path.cwd() / "work"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory)
            (root / "bad.json").write_text("[]")
            (root / "partial.json").write_text("{")
            (root / "one.json").write_text(json.dumps({
                "sessionId": "exact", "pid": 55, "procStart": "134355518111525146",
                "pidDomain": "win32:" + os.environ.get("COMPUTERNAME", "").lower()}))
            with patch.object(session_process, "SESSION_DIR", root):
                self.assertIsNone(session_process.claude_owner("unrelated"))
                if os.name == "nt":
                    self.assertEqual(session_process.claude_owner("exact")["pid"], 55)


if __name__ == "__main__":
    unittest.main()
