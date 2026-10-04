"""Read-only fallback for Cline Desktop builds whose SDK plugins cannot load.

Queries select status metadata inside SQLite; prompts, tool arguments/results,
messages, provider settings and credentials are never returned to the bridge.
The event DB is an internal Cline interface: unsupported schemas fail quietly.
"""
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import psutil

EVENTS = ('run.started', 'run.completed', 'run.failed', 'run.cancelled',
          'tool.started', 'tool.finished', 'capability.requested',
          'capability.resolved', 'capability.failed', 'session.detached',
          'approval.requested', 'approval.resolved')
QUESTIONS = {'ask_question', 'ask_followup_question', 'plan_mode_respond'}
WAITS = {'tool_executor.askQuestion'}


def desktop_pid():
    for p in psutil.process_iter(['name']):
        if (p.info['name'] or '').lower() == 'cline-app.exe':
            return p.pid
    return None


@contextmanager
def connect(path):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.1)
    try:
        db.execute('PRAGMA query_only=ON')
        yield db
    finally:
        db.close()


class ClineDesktop:
    def __init__(self, report, directory=None, find_pid=desktop_pid):
        self.report = report
        self.directory = directory or Path.home() / '.cline/data/db'
        self.find_pid = find_pid
        self.cursor = None
        self.tracked = {}
        self.pid = None
        self.last_emit = 0
        self.last_error = None

    def end_all(self, now):
        for sid, item in self.tracked.items():
            self.report('cline', 'desktop:' + sid, 'ended', now, item['cwd'], 'DesktopClosed', self.pid)
        self.tracked.clear()
        self.cursor = None

    def apply(self, row, metadata, now):
        _, sid, event, stamp, tool, key, capability, reason, participants = row
        if sid not in metadata:
            return
        if sid not in self.tracked:
            if event != 'run.started':
                return
            # Bound memory, just as the bridge bounds plugin sessions.
            if len(self.tracked) >= 256:
                return
            self.tracked[sid] = {'state': 'working', 'ts': stamp / 1000,
                                 'cwd': metadata[sid], 'waits': set(), 'event': event}
        item = self.tracked[sid]
        state = item['state']
        if event == 'run.started':
            item['waits'].clear()
            state = 'working'
        elif event in ('run.completed', 'run.failed', 'run.cancelled'):
            item['waits'].clear()
            state = ('idle' if reason in ('aborted', 'cancelled', 'canceled') or event == 'run.cancelled'
                     else 'error' if event == 'run.failed' else 'completed')
        elif event == 'session.detached' and participants == 0:
            self.report('cline', 'desktop:' + sid, 'ended', now, item['cwd'], event, self.pid)
            del self.tracked[sid]
            return
        elif state in ('working', 'needs_input'):
            if event == 'tool.started' and tool in QUESTIONS:
                item['waits'].add('tool:' + str(key))
            elif event == 'tool.finished':
                item['waits'].discard('tool:' + str(key))
            elif event == 'approval.requested':
                item['waits'].add('approval:' + str(key))
            elif event == 'approval.resolved':
                item['waits'].discard('approval:' + str(key))
            elif event == 'capability.requested' and capability in WAITS:
                item['waits'].add('cap:' + str(key))
            elif event in ('capability.resolved', 'capability.failed'):
                item['waits'].discard('cap:' + str(key))
            state = 'needs_input' if item['waits'] else 'working'
        item.update(state=state, ts=min(stamp / 1000, now), event=event)

    def poll(self, now=None):
        now = time.time() if now is None else now
        try:
            pid = self.find_pid()
            if pid != self.pid:
                self.end_all(now)
                self.pid = pid
            if not pid:
                return
            event_path = self.directory / 'hub-events-hub-production.db'
            session_path = self.directory / 'sessions.db'
            if not event_path.exists() or not session_path.exists():
                return
            with connect(event_path) as db:
                high = db.execute('SELECT coalesce(max(sequence), 0) FROM hub_events').fetchone()[0]
                if self.cursor is None or high < self.cursor:
                    # Never replay historical successes/errors when starting the bridge.
                    self.cursor = high
                with connect(session_path) as sessions:
                    metadata = dict(sessions.execute(
                        "SELECT session_id, coalesce(cwd, '') FROM sessions WHERE source='desktop' AND ended_at IS NULL"))
                rows = db.execute('''SELECT sequence, session_id, event, created_at,
                    json_extract(envelope_json, '$.payload.toolName'),
                    coalesce(json_extract(envelope_json, '$.payload.approvalId'),
                             json_extract(envelope_json, '$.payload.toolCallId'),
                             json_extract(envelope_json, '$.payload.requestId')),
                    json_extract(envelope_json, '$.payload.capabilityName'),
                    json_extract(envelope_json, '$.payload.reason'),
                    json_array_length(envelope_json, '$.payload.session.participants')
                    FROM hub_events WHERE sequence > ? AND sequence <= ? AND event IN ('''
                    + ','.join('?' for _ in EVENTS) + ') ORDER BY sequence LIMIT 2048',
                    (self.cursor, high, *EVENTS)).fetchall()
                for row in rows:
                    self.apply(row, metadata, now)
                self.cursor = rows[-1][0] if len(rows) == 2048 else high
            for sid in list(self.tracked):
                if sid not in metadata:
                    item = self.tracked.pop(sid)
                    self.report('cline', 'desktop:' + sid, 'ended', now, item['cwd'], 'SessionClosed', pid)
            if rows or now - self.last_emit >= 5:
                for sid, item in self.tracked.items():
                    stamp = now if item['state'] in ('working', 'needs_input', 'idle') else item['ts']
                    self.report('cline', 'desktop:' + sid, item['state'], stamp, item['cwd'], item['event'], pid)
                self.last_emit = now
            self.last_error = None
        except (sqlite3.Error, OSError, ValueError, TypeError, psutil.Error) as exc:
            # No heartbeat on read failure: the bridge's normal lease expires.
            self.last_error = type(exc).__name__

    def run(self):
        while True:
            self.poll()
            time.sleep(0.5)
