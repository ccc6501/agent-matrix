"""Pure display logic for Agent Matrix; usable by CircuitPython and desktop tests."""
import math

AGENTS = ("codex", "claude", "opencode", "cline")
STATES = ("working", "needs_input", "completed", "error", "idle", "off", "disconnected")
IDENTITY = {"codex": (0, 90, 255), "claude": (255, 100, 0), "opencode": (255, 255, 255), "cline": (180, 40, 255)}
COLORS = {"working": (190, 210, 255), "needs_input": (255, 200, 0),
          "completed": (0, 255, 40), "error": (255, 0, 0), "idle": (45, 45, 45)}
GLYPHS = {
    "working": ("001100", "010010", "100001", "100001", "010010", "001100"),
    "needs_input": ("001100", "001100", "001100", "001100", "000000", "001100"),
    "completed": ("000000", "000001", "000010", "100100", "011000", "000000"),
    "error": ("100001", "010010", "001100", "001100", "010010", "100001"),
    "idle": ("000000", "000000", "011110", "000000", "000000", "000000"),
}
BROKEN = ("00100100", "00100100", "01111110", "01000010",
          "00000000", "01000010", "00111100", "00011000")
OFF = (0, 0, 0)


def scale(color, k):
    return tuple(int(v * k) for v in color)


def choose(states, phase):
    if "disconnected" in states.values():
        return "link", "disconnected"
    active = [a for a in AGENTS if states.get(a, "off") != "off"]
    if not active:
        return "none", "off"
    urgent = [a for a in active if states[a] in ("needs_input", "error")]
    # All urgent agents remain visible; one urgent agent holds the display.
    choices = urgent or [a for a in active if states[a] != "idle"] or active
    agent = choices[int(phase / 3) % len(choices)]
    return agent, states[agent]


def render(agent, state, phase):
    frame = [OFF] * 64
    if state == "disconnected":
        color = scale((140, 0, 255), 0.65 + 0.35 * math.cos(phase * 2))
        for y, row in enumerate(BROKEN):
            for x, bit in enumerate(row):
                if bit == "1":
                    frame[y * 8 + x] = color
        return frame
    if state == "off":
        return frame
    border = scale(IDENTITY[agent], 0.5 if state != "idle" else 0.2)
    for y in range(8):
        for x in range(8):
            if x in (0, 7) or y in (0, 7):
                frame[y * 8 + x] = border
    for y, row in enumerate(GLYPHS[state]):
        for x, bit in enumerate(row):
            if bit != "1":
                continue
            k = 1.0
            if state == "needs_input":
                k = 1.0 if phase % 1 < 0.5 else 0.12
            elif state == "working":
                angle = math.atan2(y - 2.5, x - 2.5) % (2 * math.pi)
                delta = (phase * 4 - angle) % (2 * math.pi)
                k = 0.18 + 0.82 * max(0, 1 - delta / 2.8)
            frame[(y + 1) * 8 + x + 1] = scale(COLORS[state], k)
    return frame


def physical_index(x, y, rotation=0):
    # Waveshare Font demo: TOP + RIGHT + COLUMNS + PROGRESSIVE, GRB.
    for _ in range((rotation // 90) % 4):
        x, y = 7 - y, x
    return (7 - x) * 8 + y
