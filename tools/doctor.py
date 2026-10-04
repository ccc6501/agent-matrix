"""Read-only checks. Never opens the serial port held by a running bridge."""
import importlib.metadata
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'host'))


def main():
    issues = 0
    print('Agent Matrix installation check')
    print('Python:', sys.version.split()[0])
    for package in ('pyserial', 'psutil'):
        try:
            print(package + ':', importlib.metadata.version(package))
        except importlib.metadata.PackageNotFoundError:
            print(package + ': MISSING; run setup.ps1')
            issues += 1
    if issues:
        return 1
    from runtime_config import bridge_url, load_config, VERSION
    from board_port import find_port
    try:
        config = load_config()
        port = find_port(config['serial_number'])
        print('USB board:', port or 'NOT FOUND; connect the board and install CircuitPython')
        issues += not bool(port)
        with urllib.request.urlopen(bridge_url() + '/api/status', timeout=2) as r:
            data = json.load(r)
        if data.get('app') != 'agent-matrix' or data.get('version') != VERSION:
            print('Bridge: another or older service is using this port. Stop it before launching this copy.')
            issues += 1
        else:
            print('Bridge:', data['version'], 'connected' if data['board']['connected'] else data['board']['error'])
            issues += not data['board']['connected']
            for agent, rows in data['sessions'].items():
                print(agent + ':', str(len(rows)) + ' live session(s)')
    except (OSError, ValueError) as exc:
        print('Connection/config:', str(exc))
        print('Launch with .venv\\Scripts\\pythonw.exe host\\launch.py')
        issues += 1
    manifest = ROOT / '.local/install.json'
    if manifest.exists():
        installed = json.loads(manifest.read_text(encoding='utf-8'))
        print('Installed adapters:', ', '.join(installed['agents']) or 'none (manual mode)')
        from manage import read_object, digest
        for hook in installed['hooks']:
            try:
                groups = read_object(Path(hook['path'])).get('hooks', {}).get(hook['event'], [])
                if hook['group'] not in groups:
                    print('Missing/edited hook:', hook['event'], Path(hook['path']).name)
                    issues += 1
            except (ValueError, OSError):
                issues += 1
        for item in installed['files']:
            file = Path(item['path'])
            if not file.exists() or digest(file.read_bytes()) != item['sha256']:
                print('Missing/edited installed file:', file.name)
                issues += 1
    else:
        print('No install manifest. Run setup.ps1 to register adapters.')
    print('Codex hooks require native trust review. OpenCode/Cline need a new runtime after installation.')
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
