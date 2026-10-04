"""Copy application files to an identified CircuitPython matrix with a backup."""
import argparse
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]


def deploy(drive, backup_root):
    drive = drive.resolve()
    boot = drive / 'boot_out.txt'
    if not boot.exists() or 'waveshare_esp32_s3_matrix' not in boot.read_text(errors='replace').lower():
        raise ValueError('Not an identified Waveshare ESP32-S3-Matrix CircuitPython drive.')
    backup = backup_root / time.strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True, exist_ok=False)
    for name in ('matrix_display.py', 'board_config.py', 'code.py'):
        target = drive / name
        if target.exists():
            shutil.copy2(target, backup / name)
        # Keep calibrated settings on an existing Agent Matrix installation.
        if name == 'board_config.py' and target.exists():
            continue
        shutil.copy2(ROOT / 'firmware/matrix' / name, target)
    print('Application copied; CircuitPython will reload. Existing board_config.py retained.')
    print('Previous application files backed up to', backup)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--drive', required=True, type=Path, help='CircuitPython drive root, for example E:/')
    args = ap.parse_args()
    try:
        deploy(args.drive, ROOT / '.local/firmware-backups')
    except (OSError, ValueError) as exc:
        ap.exit(1, str(exc) + '\n')
