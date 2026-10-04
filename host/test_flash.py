from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import flash


class FlashTests(unittest.TestCase):
    def test_wrong_board_is_not_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            drive=Path(tmp)/'drive';drive.mkdir();(drive/'code.py').write_text('keep')
            (drive/'boot_out.txt').write_text('a different CircuitPython board')
            with self.assertRaises(ValueError):flash.deploy(drive,Path(tmp)/'backups')
            self.assertEqual((drive/'code.py').read_text(),'keep')
            self.assertFalse((drive/'matrix_display.py').exists())

    def test_existing_calibration_and_application_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            drive=Path(tmp)/'drive';drive.mkdir()
            (drive/'boot_out.txt').write_text('Board ID:waveshare_esp32_s3_matrix')
            (drive/'code.py').write_text('old application')
            (drive/'board_config.py').write_text('ROTATION = 90')
            backups=Path(tmp)/'backups';flash.deploy(drive,backups)
            self.assertEqual((drive/'board_config.py').read_text(),'ROTATION = 90')
            self.assertIn('agent-matrix-v3',(drive/'code.py').read_text())
            saved=next(backups.iterdir())
            self.assertEqual((saved/'code.py').read_text(),'old application')


if __name__=='__main__':unittest.main()
