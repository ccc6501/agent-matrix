import json
from contextlib import contextmanager
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cline_desktop import ClineDesktop, connect


@contextmanager
def writable(path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


class ClineDesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.events = self.folder / 'hub-events-hub-production.db'
        with writable(self.events) as db:
            db.execute('CREATE TABLE hub_events(sequence INTEGER PRIMARY KEY, session_id TEXT, event TEXT, created_at INTEGER, envelope_json TEXT)')
        with writable(self.folder / 'sessions.db') as db:
            db.execute('CREATE TABLE sessions(session_id TEXT, source TEXT, ended_at TEXT, cwd TEXT)')
            db.executemany('INSERT INTO sessions VALUES(?,?,NULL,?)', [('s', 'desktop', '/project'), ('cli', 'cli', '/other')])
        self.rows = []
        self.pid = 123
        self.now = 1000
        self.reader = ClineDesktop(lambda *row: self.rows.append(row), self.folder, lambda: self.pid)
        self.reader.poll(self.now)

    def emit(self, event, payload=None, sid='s'):
        self.now += 1
        payload = dict(payload or {}, text='PRIVATE TRANSCRIPT SENTINEL')
        with writable(self.events) as db:
            db.execute('INSERT INTO hub_events(session_id,event,created_at,envelope_json) VALUES(?,?,?,?)',
                       (sid, event, self.now * 1000, json.dumps({'payload': payload})))
        self.reader.poll(self.now)

    def state(self):
        return self.rows[-1][2]

    def test_real_desktop_question_sequence_and_completion_expiry(self):
        self.emit('run.started')
        self.assertEqual(self.state(), 'working')
        self.emit('tool.started', {'toolName': 'run_commands', 'toolCallId': 'a'})
        self.assertEqual(self.state(), 'working')
        self.emit('tool.started', {'toolName': 'ask_question', 'toolCallId': 'q'})
        self.emit('capability.requested', {'capabilityName': 'tool_executor.askQuestion', 'requestId': 'cap'})
        self.assertEqual(self.state(), 'needs_input')
        self.emit('capability.resolved', {'requestId': 'cap'})
        self.assertEqual(self.state(), 'needs_input')
        self.emit('tool.finished', {'toolCallId': 'q'})
        self.assertEqual(self.state(), 'working')
        self.emit('run.completed', {'reason': 'completed'})
        self.assertEqual(self.state(), 'completed')
        stamp = self.rows[-1][3]
        self.reader.poll(self.now + 40)
        self.assertEqual(self.rows[-1][3], stamp)
        self.assertNotIn('PRIVATE TRANSCRIPT', repr(self.rows))

    def test_concurrent_approvals_and_questions(self):
        self.emit('run.started')
        self.emit('approval.requested', {'approvalId': 'a', 'toolCallId': 'tool'})
        self.emit('approval.requested', {'approvalId': 'b', 'toolCallId': 'tool2'})
        self.emit('approval.resolved', {'approvalId': 'a'})
        self.assertEqual(self.state(), 'needs_input')
        self.emit('approval.resolved', {'approvalId': 'b'})
        self.assertEqual(self.state(), 'working')

    def test_fail_cancel_restart(self):
        self.emit('run.started')
        self.emit('run.failed', {'reason': 'error'})
        self.assertEqual(self.state(), 'error')
        self.emit('run.started')
        self.emit('run.completed', {'reason': 'aborted'})
        self.assertEqual(self.state(), 'idle')
        self.emit('run.started')
        self.assertEqual(self.state(), 'working')

    def test_close_and_process_exit(self):
        self.emit('run.started')
        self.emit('session.detached', {'session': {'participants': ['remaining']}})
        self.assertEqual(self.state(), 'working')
        self.emit('session.detached', {'session': {'participants': []}})
        self.assertEqual(self.state(), 'ended')
        self.emit('run.started')
        self.pid = None
        self.reader.poll(self.now + 1)
        self.assertEqual(self.state(), 'ended')
        self.assertFalse(self.reader.tracked)

    def test_start_does_not_replay_history_or_track_cli(self):
        self.emit('run.started', sid='cli')
        self.assertFalse(self.rows)
        self.emit('run.started')
        self.emit('run.completed')
        rows = []
        reader = ClineDesktop(lambda *r: rows.append(r), self.folder, lambda: self.pid)
        reader.poll(self.now)
        self.assertFalse(rows)

    def test_unknown_schema_stops_heartbeat_without_breaking_bridge(self):
        self.emit('run.started')
        count = len(self.rows)
        with writable(self.events) as db:
            db.execute('DROP TABLE hub_events')
        self.reader.poll(self.now + 30)
        self.assertEqual(len(self.rows), count)
        self.assertEqual(self.reader.last_error, 'OperationalError')

    def test_database_is_read_only(self):
        with connect(self.events) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM hub_events')


if __name__ == '__main__':
    unittest.main()
