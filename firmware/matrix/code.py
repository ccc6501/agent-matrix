"""Agent Matrix v3: four agent identity borders, 6x6 status symbols.

USB console protocol remains compatible with agent-light-v1.
Additional commands: demo [seconds], rotate 0|90|180|270, brightness 0..0.12.
Do not send Ctrl-C/Ctrl-D in normal operation; these control the Python REPL.
"""
import sys
import time
import board
import neopixel
import supervisor
from board_config import BRIGHTNESS, ROTATION, PIXEL_ORDER
from matrix_display import AGENTS, STATES, choose, render, physical_index

VERSION = "agent-matrix-v3"
brightness = min(0.12, max(0.0, BRIGHTNESS))
rotation = ROTATION if ROTATION in (0, 90, 180, 270) else 0
pixels = neopixel.NeoPixel(board.NEOPIXEL, 64, bpp=3,
                          pixel_order=getattr(neopixel, PIXEL_ORDER), brightness=brightness,
                          auto_write=False)
state = {a: "off" for a in AGENTS}
heartbeat_s = 6
last_rx = None
epoch = time.monotonic()
demo_start = 0.0
demo_until = 0.0
rx_buf = ""
overflow = False
DEMO_STATES = ("working", "needs_input", "completed", "error", "idle", "disconnected")
try:
    supervisor.status_bar.console = False
except AttributeError:
    pass


def display(now):
    if now < demo_until:
        phase = now - demo_start
        st = DEMO_STATES[int(phase / (3 * len(AGENTS))) % len(DEMO_STATES)]
        shown = AGENTS[int(phase / 3) % len(AGENTS)]
        return "link" if st == "disconnected" else shown, st, phase
    phase = now - epoch
    if last_rx is None or (heartbeat_s and now - last_rx > heartbeat_s):
        return "link", "disconnected", phase
    agent, st = choose(state, phase)
    return agent, st, phase


def reply(text):
    print(text)


def handle(line):
    global last_rx, heartbeat_s, epoch, demo_start, demo_until, rotation, brightness
    parts = line.strip().lower().split()
    if not parts:
        return
    now = time.monotonic()
    # Capture the pre-command timeout so a status probe can observe heartbeat loss.
    expired = last_rx is None or (heartbeat_s and now - last_rx > heartbeat_s)
    cmd = parts[0]
    if cmd == "ping" and len(parts) == 1:
        reply("pong " + VERSION)
    elif cmd == "status" and len(parts) == 1:
        agent, st, phase = display(now)
        effective = {a: "disconnected" if expired and now >= demo_until else state[a] for a in AGENTS}
        reply("ok " + " ".join(a + "=" + effective[a] for a in AGENTS) + " heartbeat={} version={} shown={} display_state={} phase={:.3f} demo={} rotation={} brightness={:.3f}".format(
            heartbeat_s, VERSION,
            agent, st, phase, max(0, int(demo_until - now)), rotation, brightness))
    elif cmd == "heartbeat" and len(parts) == 2:
        value = int(parts[1])
        if not 0 <= value <= 3600:
            raise ValueError("heartbeat must be 0..3600")
        heartbeat_s = value
        reply("ok heartbeat " + str(value))
    elif cmd in AGENTS + ("all",) and len(parts) == 2 and parts[1] in STATES:
        changed = False
        for agent in (AGENTS if cmd == "all" else (cmd,)):
            if state[agent] != parts[1]:
                state[agent] = parts[1]
                changed = True
        if changed:
            epoch = now
        reply("ok {} {}".format(cmd, parts[1]))
    elif cmd == "demo" and len(parts) in (1, 2):
        seconds = int(parts[1]) if len(parts) == 2 else 72
        if not 0 <= seconds <= 120:
            raise ValueError("demo must be 0..120 seconds")
        demo_start, demo_until = now, now + seconds
        reply("ok demo " + str(seconds))
    elif cmd == "rotate" and len(parts) == 2 and int(parts[1]) in (0, 90, 180, 270):
        rotation = int(parts[1])
        reply("ok rotate " + str(rotation))
    elif cmd == "brightness" and len(parts) == 2:
        value = float(parts[1])
        if not 0 <= value <= 0.12:
            raise ValueError("brightness must be 0..0.12")
        brightness = value
        pixels.brightness = value
        reply("ok brightness " + str(value))
    else:
        reply("err unknown: " + line[:40])
        return
    last_rx = now


print(VERSION + " ready | Waveshare ESP32-S3-Matrix, GPIO14, 64 " + PIXEL_ORDER + " pixels")
while True:
    # Bound input work per frame so bursts of serial traffic cannot freeze LEDs.
    for _ in range(256):
        if not supervisor.runtime.serial_bytes_available:
            break
        char = sys.stdin.read(1)
        if char in "\r\n":
            if overflow:
                reply("err line too long")
            elif rx_buf:
                try:
                    handle(rx_buf)
                except (ValueError, OverflowError) as exc:
                    reply("err " + str(exc)[:80])
            rx_buf, overflow = "", False
        elif not overflow:
            rx_buf += char
            if len(rx_buf) > 160:
                rx_buf, overflow = "", True
    agent, st, phase = display(time.monotonic())
    frame = render(agent, st, phase)
    for y in range(8):
        for x in range(8):
            pixels[physical_index(x, y, rotation)] = frame[y * 8 + x]
    pixels.show()
    time.sleep(0.025)
