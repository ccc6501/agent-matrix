"""Select only the intended Waveshare matrix; never guess between two boards."""
import serial
from serial.tools import list_ports

ESPRESSIF_VID = 0x303A
MATRIX_PID = 0x826E


def candidates():
    return [p for p in list_ports.comports() if p.vid == ESPRESSIF_VID and p.pid == MATRIX_PID]


def find_port(serial_number=None, port=None):
    if port:
        return port
    matches = [p for p in candidates() if not serial_number or p.serial_number == serial_number]
    if len(matches) > 1:
        raise serial.SerialException('Multiple matrices found. Run setup and select a USB serial number.')
    return matches[0].device if matches else None
