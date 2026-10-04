"""Run with python -m unittest discover -s host -p test_matrix.py."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware" / "matrix"))
import matrix_display as display
import bridge


class MatrixTests(unittest.TestCase):
    def test_four_agent_rotation_and_colors(self):
        states = {a: "working" for a in display.AGENTS}
        self.assertEqual([display.choose(states, t)[0] for t in (0, 3, 6, 9)], list(display.AGENTS))
        self.assertEqual(display.IDENTITY["opencode"], (255, 255, 255))
        self.assertEqual(display.IDENTITY["cline"], (180, 40, 255))
        states["cline"] = "needs_input"
        self.assertEqual(display.choose(states, 0), ("cline", "needs_input"))

    def test_borders_and_interior(self):
        for agent in display.AGENTS:
            for state in display.GLYPHS:
                frame = display.render(agent, state, 0.2)
                self.assertEqual(len(frame), 64)
                expected = display.scale(display.IDENTITY[agent], 0.2 if state == "idle" else 0.5)
                for y in range(8):
                    for x in range(8):
                        if x in (0, 7) or y in (0, 7):
                            self.assertEqual(frame[y * 8 + x], expected)
        self.assertEqual(display.render("none", "off", 0), [(0, 0, 0)] * 64)

    def test_motion_never_changes_identity(self):
        for state in ("working", "needs_input"):
            a = display.render("claude", state, 0.1)
            b = display.render("claude", state, 0.7)
            self.assertNotEqual(a, b)
            self.assertEqual(a[:8], b[:8])

    def test_rotation_is_bijective(self):
        for rotation in (0, 90, 180, 270):
            indices = [display.physical_index(x, y, rotation) for y in range(8) for x in range(8)]
            self.assertEqual(sorted(indices), list(range(64)))
        self.assertEqual(display.physical_index(7, 0), 0)
        self.assertEqual(display.physical_index(0, 7), 63)

    def test_attention_and_alternation(self):
        states = {"codex": "working", "claude": "completed"}
        self.assertEqual(display.choose(states, 0), ("codex", "working"))
        self.assertEqual(display.choose(states, 3.1), ("claude", "completed"))
        states["claude"] = "needs_input"
        for t in (0, 3, 6, 9):
            self.assertEqual(display.choose(states, t), ("claude", "needs_input"))
        states["codex"] = "error"
        self.assertEqual(display.choose(states, 0), ("codex", "error"))
        self.assertEqual(display.choose(states, 3), ("claude", "needs_input"))
        self.assertEqual(display.choose({"codex": "off", "claude": "off"}, 0), ("none", "off"))
        self.assertEqual(display.choose({"codex": "working", "claude": "disconnected"}, 0), ("link", "disconnected"))

    def test_only_configured_matrix_is_selected(self):
        board = bridge.Board()
        board.serial_number = 'selected-test-board'
        ports = [SimpleNamespace(vid=0x303A, pid=0x81B4, serial_number="zero", device="COM12"),
                 SimpleNamespace(vid=0x303A, pid=0x826E, serial_number="other", device="COM8"),
                 SimpleNamespace(vid=0x303A, pid=0x826E, serial_number=board.serial_number, device="COM7")]
        with patch.object(bridge.list_ports, "comports", return_value=ports):
            self.assertEqual(board._find_port(), "COM7")
        with patch.object(bridge.list_ports, "comports", return_value=ports[:2]):
            self.assertIsNone(board._find_port())

    def test_bad_status_is_not_connected(self):
        board = bridge.Board()
        for reply in ("err unknown", "ok version=agent-light-v1", "ok version=agent-matrix-v2"):
            with self.assertRaises(bridge.serial.SerialException):
                board._apply_status(reply)
        self.assertFalse(board.status["connected"])

    def test_hidden_bridge_can_log_without_stderr(self):
        handler = bridge.make_handler(None, None, None)
        with patch.object(bridge.sys, "stderr", None):
            handler.log_message(None, "%s", "POST /api/display HTTP/1.1")


if __name__ == "__main__":
    unittest.main()
