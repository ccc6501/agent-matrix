# Install CircuitPython and the matrix application

1. Back up any application already on your board before replacing its runtime.
2. Open the [official CircuitPython page for Waveshare ESP32-S3-Matrix](https://circuitpython.org/board/waveshare_esp32_s3_matrix/).
   This project was tested with **10.3.1**, including its frozen `neopixel` library;
   no separate NeoPixel library download is needed for that build.
3. If your board has a working TinyUF2 bootloader, enter its UF2 bootloader mode
   and copy the matching `.uf2` onto the bootloader drive. Use the official page's
   bootloader/installer instructions if no UF2 drive appears. The page documents
   the minimum bootloader version for 4 MB ESP32-S3 boards. Do not flash an image
   intended for another ESP32-S3 board.
4. After installation, a **CIRCUITPY** drive should appear. Its `boot_out.txt`
   should identify `waveshare_esp32_s3_matrix`.
5. Run desktop setup, then `python tools/flash.py --drive E:/` using the setup
   virtual environment and your actual drive letter. The script copies
   `matrix_display.py`, `board_config.py`, and finally `code.py`. It checks the
   target identity before writing and backs up replaced application files.
6. The board reloads automatically. Launch the bridge and use the display demo.

`board_config.py` is preserved if already present. To change its calibration,
edit the file on CIRCUITPY explicitly. The dashboard's Rotate button is temporary;
the file's ROTATION value persists after reload. Leave USB CDC at its default
configuration; the serial console carries the display protocol.

The firmware uses the built-in matrix on GPIO14, a one-pixel identity border,
and a 6×6 status symbol. It does not use the IMU or Wi-Fi. See the
[Waveshare board documentation](https://docs.waveshare.com/ESP32-S3-Matrix) for
hardware and bootloader details.
