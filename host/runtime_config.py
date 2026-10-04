"""Machine-local settings; never put generated config in a release archive."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
CONFIG_PATH = Path(os.environ.get('AGENT_MATRIX_CONFIG', LOCAL / 'config.json'))
VERSION = '0.1.1'


def load_config():
    data = {'serial_number': None, 'http_port': 8765}
    if CONFIG_PATH.exists():
        user = json.loads(CONFIG_PATH.read_text(encoding='utf-8-sig'))
        if not isinstance(user, dict):
            raise ValueError('Configuration must be a JSON object')
        data.update(user)
    port = data['http_port']
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('http_port must be an integer from 1024 to 65535')
    serial = data['serial_number']
    if serial is not None and (not isinstance(serial, str) or not serial or len(serial) > 128):
        raise ValueError('serial_number must be null or a nonempty USB serial number')
    return data


def bridge_url():
    return 'http://127.0.0.1:{}'.format(load_config()['http_port'])
