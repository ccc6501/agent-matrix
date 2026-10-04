import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import manage
import board_port
from types import SimpleNamespace


class InstallTests(unittest.TestCase):
    def test_install_uninstall_preserves_other_hooks_and_later_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'release with spaces';root.mkdir()
            home=Path(tmp)/'home';path=home/'.claude/settings.json'
            original={'theme':'dark','hooks':{'Stop':[{'hooks':[{'type':'command','command':'existing'}]}]}}
            manage.atomic(path,manage.json_bytes(original))
            agents=['codex','claude','opencode','cline']
            manage.install(root,home,agents,Path(sys.executable))
            first=path.read_bytes()
            manage.install(root,home,agents,Path(sys.executable))
            self.assertEqual(first,path.read_bytes())
            data=manage.read_object(path);data['newPreference']=True
            data['hooks']['Stop'].append({'hooks':[{'type':'command','command':'added-later'}]})
            manage.atomic(path,manage.json_bytes(data))
            manage.uninstall(root)
            after=manage.read_object(path)
            self.assertTrue(after['newPreference']);self.assertEqual(after['theme'],'dark')
            self.assertEqual(len(after['hooks']['Stop']),2)
            self.assertFalse((home/'.cline/plugins/agent-matrix.ts').exists())
            self.assertFalse((home/'.config/opencode/plugins/agent-matrix.ts').exists())
            manage.install(root,home,agents,Path(sys.executable));manage.uninstall(root)

    def test_conflicting_plugin_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'release';root.mkdir();home=Path(tmp)/'home'
            path=home/'.cline/plugins/agent-matrix.ts';manage.atomic(path,b'// someone else')
            with self.assertRaises(ValueError):
                manage.install(root,home,['codex','cline'],Path(sys.executable))
            self.assertFalse((home/'.codex/hooks.json').exists())
            self.assertEqual(path.read_bytes(),b'// someone else')

    def test_apply_failure_restores_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=root/'a';b=root/'b';a.write_bytes(b'old')
            real=manage.atomic
            def fail(path,data):
                if path==b:raise OSError('simulated full disk')
                real(path,data)
            with patch.object(manage,'atomic',side_effect=fail),self.assertRaises(OSError):
                manage.commit_plan(root,{a:b'new',b:b'new'}, {})
            self.assertEqual(a.read_bytes(),b'old');self.assertFalse(b.exists())

    def test_modified_plugin_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'release';root.mkdir();home=Path(tmp)/'home'
            manage.install(root,home,['cline'],Path(sys.executable))
            target=home/'.cline/plugins/agent-matrix.ts';target.write_text('// edited')
            manage.uninstall(root)
            self.assertEqual(target.read_text(),'// edited')

    def test_ambiguous_boards_do_not_choose_first(self):
        ports=[SimpleNamespace(device='COM1',serial_number='one'),SimpleNamespace(device='COM2',serial_number='two')]
        with patch.object(board_port,'candidates',return_value=ports):
            with self.assertRaises(board_port.serial.SerialException):board_port.find_port()
            self.assertEqual(board_port.find_port('two'),'COM2')

    @unittest.skipUnless(os.name=='nt','Windows hook shell')
    def test_codex_hook_preserves_stdin_and_awkward_paths(self):
        with tempfile.TemporaryDirectory(prefix="matrix $ & ' ") as tmp:
            root=Path(tmp);(root/'host').mkdir()
            (root/'host/agent_hook.py').write_text('import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())')
            command=manage.hook_group('codex','Stop',Path(sys.executable),root)['hooks'][0]['command']
            result=subprocess.run(command.split(),input=b'{"hook_event_name":"Stop"}',capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),b'{"hook_event_name":"Stop"}')


if __name__=='__main__':unittest.main()
