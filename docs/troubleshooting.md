# Troubleshooting

Run `.venv\Scripts\python.exe tools\doctor.py` first.

| Symptom | Check |
|---|---|
| No CIRCUITPY drive or USB port | Use a data cable, then follow the exact board's CircuitPython installer. |
| Multiple matrices found | Run setup and choose the intended USB serial number. |
| Dashboard says another bridge uses the port | Close the older bridge before launching this copy. Do not run a serial monitor simultaneously. |
| Board offline | Wait for a firmware reload, check the selected board, and verify all three application files are on CIRCUITPY. |
| Python/module error | Rerun setup; use `.venv\Scripts\python.exe`, not a different Python installation. |
| New app stays off | Restart it, begin a new local session, and review Codex hooks if prompted. See the experimental adapter limitations. |
| Purple broken-link symbol | The board has not heard from the bridge for six seconds. This full-matrix symbol is different from Cline's purple border. |
| Success stays after closing a window | The process may still be alive. Checks fade after 30 seconds; ended sessions or adapter disconnects clear independently. |
| Color channels swapped | Test orange and green using the demo. Change `PIXEL_ORDER` between `RGB` and `GRB` in CIRCUITPY's `board_config.py`; tested hardware requires RGB. |
| Symbols sideways | Use Rotate to find the orientation, then save ROTATION in `board_config.py`. |
| Cline briefly says needs input before a tool | Its permission indicator is inferred; a slow pre-tool hook can trigger it. |

The browser mirror is an approximation of the board's animation phase and
brightness, not a camera feed. It goes dark when status data is unavailable.

For a different HTTP port, edit `.local/config.json`, stop the bridge, and restart
the bridge and agent apps. The browser, Python hooks, and newly loaded plugins use
that configuration. `AGENT_MATRIX_CONFIG` can select a different config file for
development. `AGENT_MATRIX_PYTHON` overrides plugin bridge-autostart Python.

To debug a bridge without a console, stop that bridge and run
`.venv\Scripts\python.exe host\bridge.py` in PowerShell. Logs live in `.local/`
and rotate at about 1 MB. Never attach agent settings, `.local/backups`, or chat
transcripts to a public issue.
