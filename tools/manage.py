"""Install only selected integrations; retain unrelated settings on uninstall."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'host'))
from agent_hook import EVENTS
from board_port import candidates
from runtime_config import load_config


def json_bytes(data):
    return (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def read_object(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('Expected JSON object: ' + str(path))
    return data


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.agent-matrix.tmp')
    temp.write_bytes(data)
    temp.replace(path)


def hook_group(agent, event, python, root):
    script = root / 'host' / 'agent_hook.py'
    if agent == 'claude':
        hook = {'type':'command', 'command':str(python), 'args':[str(script), agent]}
    else:
        # Encoded PowerShell avoids shell interpolation of spaces, $, &, quotes,
        # and non-ASCII install paths. Stdin remains the native hook payload.
        import base64
        quoted = lambda value: "'" + str(value).replace("'", "''") + "'"
        code = '& {} {} {}'.format(quoted(python), quoted(script), quoted(agent))
        command = 'powershell.exe -NoProfile -NonInteractive -EncodedCommand ' + base64.b64encode(code.encode('utf-16le')).decode('ascii')
        hook = {'type':'command', 'command':command, 'commandWindows':command}
    hook['timeout'] = 3 if event in ('SessionEnd', 'Interrupt') else 5
    if event != 'SessionEnd':
        hook['async'] = True
    group = {'hooks':[hook]}
    if event == 'PreToolUse':
        group['matcher'] = 'AskUserQuestion|ExitPlanMode'
    return group


def integration_plan(root, home, agents, python, codex_home=None, opencode_home=None):
    """Pure planning: validate everything before modifying any user settings."""
    changes, hooks, files = {}, [], []
    codex_home = codex_home or home / '.codex'
    opencode_home = opencode_home or home / '.config/opencode'
    for agent in agents:
        if agent in ('codex', 'claude'):
            path = codex_home / 'hooks.json' if agent == 'codex' else home / '.claude/settings.json'
            data = read_object(path)
            bag = data.setdefault('hooks', {})
            if not isinstance(bag, dict):
                raise ValueError('Invalid existing hooks: ' + str(path))
            for event in EVENTS[agent]:
                entries = bag.setdefault(event, [])
                if not isinstance(entries, list):
                    raise ValueError('Invalid existing event: ' + event)
                group = hook_group(agent, event, python, root)
                if group in entries:
                    raise ValueError('Hook already exists without an install manifest; inspect ' + str(path))
                entries.append(group)
                hooks.append({'path':str(path), 'event':event, 'group':group})
            changes[path] = json_bytes(data)
        else:
            folder = opencode_home / 'plugins' if agent == 'opencode' else home / '.cline/plugins'
            path = folder / 'agent-matrix.ts'
            if path.exists():
                raise ValueError('Refusing to replace existing plugin: ' + str(path))
            body = ('// Installed by Agent Matrix. Remove with tools/manage.py uninstall.\n'
                    'export { default } from ' + json.dumps((root / 'integrations' / (agent + '.js')).as_uri()) + ';\n').encode()
            changes[path] = body
            files.append({'path':str(path), 'sha256':digest(body)})
    return changes, hooks, files


def commit_plan(root, changes, manifest):
    """Back up originals and roll back only our writes if applying a plan fails."""
    originals = {p:p.read_bytes() if p.exists() else None for p in changes}
    backup = root / '.local/backups' / time.strftime('%Y%m%d-%H%M%S')
    for index, (path, original) in enumerate(originals.items()):
        if original is not None:
            backup.mkdir(parents=True, exist_ok=True)
            (backup / (str(index) + '-' + path.name)).write_bytes(original)
    written = []
    try:
        for path, data in changes.items():
            current = path.read_bytes() if path.exists() else None
            if current != originals[path]:
                raise RuntimeError('File changed during installation: ' + str(path))
            atomic(path, data)
            written.append(path)
        atomic(root / '.local/install.json', json_bytes(manifest))
    except Exception:
        for path in reversed(written):
            if path.read_bytes() != changes[path]:
                continue
            if originals[path] is None:
                path.unlink()
            else:
                atomic(path, originals[path])
        raise


def install(root, home, agents, python, serial_number=None, http_port=8765, codex_home=None, opencode_home=None):
    manifest_path = root / '.local/install.json'
    if manifest_path.exists():
        previous = read_object(manifest_path)
        if previous.get('agents') == agents and previous.get('python') == str(python):
            config_path = root / '.local/config.json'
            config = read_object(config_path)
            config.update(serial_number=serial_number, http_port=http_port, python=str(python), cline_desktop='cline' in agents)
            atomic(config_path, json_bytes(config))
            print('Already installed. Run doctor to check it, or uninstall before changing agents.')
            return previous
        raise ValueError('Already installed with different options. Uninstall before changing agents.')
    changes, hooks, files = integration_plan(root, home, agents, python, codex_home, opencode_home)
    config_path = root / '.local/config.json'
    config = read_object(config_path)
    config.update(serial_number=serial_number, http_port=http_port, python=str(python), cline_desktop='cline' in agents)
    changes[config_path] = json_bytes(config)
    manifest = {'agents':agents, 'python':str(python), 'hooks':hooks, 'files':files}
    commit_plan(root, changes, manifest)
    return manifest


def uninstall(root):
    path = root / '.local/install.json'
    if not path.exists():
        print('No installation manifest; nothing removed.')
        return
    manifest = read_object(path)
    plans = {}
    for item in manifest.get('hooks', []):
        target = Path(item['path'])
        if not target.exists():
            continue
        data = plans.setdefault(target, read_object(target))
        bag = data.get('hooks', {})
        entries = bag.get(item['event'], [])
        # Remove only the exact entry we installed, including nested groups.
        if item['group'] in entries:
            entries.remove(item['group'])
            if not entries:
                bag.pop(item['event'], None)
        else:
            print('Hook was edited or removed; left current settings alone:', item['event'])
    for target, data in plans.items():
        atomic(target, json_bytes(data))
    for item in manifest.get('files', []):
        target = Path(item['path'])
        if target.exists() and digest(target.read_bytes()) == item['sha256']:
            target.unlink()
        elif target.exists():
            print('Modified file preserved:', target)
    config_path = root / '.local/config.json'
    config = read_object(config_path)
    config['cline_desktop'] = False
    atomic(config_path, json_bytes(config))
    path.replace(path.with_name('last-uninstall.json'))
    print('Removed matching integrations. Local config, backups, and source files retained.')


def shortcut(root, python):
    # Use Windows' actual Desktop folder (including OneDrive redirection).
    script = root / 'tools/shortcut.ps1'
    result = subprocess.run(['powershell.exe','-NoProfile','-File',str(script),'-Root',str(root),'-Python',str(python)],
                            capture_output=True, text=True, check=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    target = Path(result.stdout.strip().splitlines()[-1])
    manifest_path = root / '.local/install.json'
    data = read_object(manifest_path)
    data['files'].append({'path':str(target), 'sha256':digest(target.read_bytes())})
    atomic(manifest_path, json_bytes(data))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['install','uninstall'])
    ap.add_argument('--agents', help='Comma-separated codex,claude,opencode,cline; or none')
    ap.add_argument('--no-shortcut', action='store_true')
    ap.add_argument('--skip-board', action='store_true')
    a = ap.parse_args()
    if a.command == 'uninstall':
        uninstall(ROOT)
        return
    if os.name != 'nt':
        raise ValueError('Desktop installation currently supports Windows only.')
    choice = a.agents if a.agents is not None else input('Agents (codex,claude,opencode,cline), comma-separated, or none: ')
    agents = list(dict.fromkeys(v.strip().lower() for v in choice.split(',') if v.strip()))
    if agents == ['none']:
        agents = []
    elif not agents or any(v not in ('codex','claude','opencode','cline') for v in agents):
        raise ValueError('Choose agent names or none.')
    serial_number = load_config()['serial_number']
    if not a.skip_board:
        boards = candidates()
        if len(boards) == 1:
            serial_number = boards[0].serial_number
        elif len(boards) > 1:
            for i, b in enumerate(boards, 1):
                print(i, b.device, b.serial_number)
            index = int(input('Board number: ')) - 1
            if not 0 <= index < len(boards):
                raise ValueError('Invalid board number')
            serial_number = boards[index].serial_number
        else:
            print('No CircuitPython matrix detected; complete flashing, then run setup again.')
    code_home = Path(os.environ['CODEX_HOME']) if os.environ.get('CODEX_HOME') else None
    open_home = Path(os.environ['XDG_CONFIG_HOME']) / 'opencode' if os.environ.get('XDG_CONFIG_HOME') else None
    manifest = install(ROOT, Path.home(), agents, Path(sys.executable), serial_number,
                       load_config()['http_port'], code_home, open_home)
    if not a.no_shortcut and not any(v['path'].endswith('.lnk') for v in manifest['files']):
        try:
            shortcut(ROOT, Path(sys.executable).with_name('pythonw.exe'))
        except subprocess.CalledProcessError:
            print('Shortcut not created (an existing shortcut is preserved). Use host/launch.py.')
    print('Setup complete. Restart selected apps. Review/trust Codex hooks when prompted.')
    print('Launch: .venv\\Scripts\\pythonw.exe host\\launch.py')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print('Setup:', str(exc), file=sys.stderr)
        sys.exit(1)
