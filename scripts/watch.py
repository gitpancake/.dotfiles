#!/usr/bin/env python3
"""Ambient zen renderer reactive to commit-watcher state.

A sparse, breathing field of soft glyphs in a gruvbox palette. Glyphs
brighten then fade in place rather than falling. Spawn density is
modulated by a slow sine wave (~6s breath cadence) and by recent
commit activity from the shared state file.

Reads $ART_STATE_FILE (default ~/.local/share/art/state.json) for
palette, intensity, burst, and a recent-commit log. Multiple watch
panes reading the same state stay in sync.
"""

import curses
import json
import math
import os
import random
import sys
import time

TARGET_FPS = 20
FRAME_TIME = 1.0 / TARGET_FPS

STATE_PATH = os.environ.get(
    "ART_STATE_FILE",
    os.path.expanduser("~/.local/share/art/state.json"),
)
STATE_POLL_FRAMES = 10  # ~0.5s @ 20fps; mtime-only check, cheap

BREATH_PERIOD_S = 6.0       # resting breath cadence
DENSITY_BASELINE = 0.045    # fraction of cells active at breath peak, baseline intensity
MAX_AGE = 22                # frames a cell stays visible before retirement
LOG_MAX_ROWS = 6
LOG_SCROLL_EVERY_FRAMES = 8

# Gruvbox 256-color indices. Mapped to nearest 8-color when terminal lacks 256.
GRUVBOX_256 = {
    "ghost":       236,  # bg0_s — barely visible against bg
    "fade":        239,  # bg2
    "mid":         243,  # bg4
    "warm":        245,  # gray
    "soft":        248,  # fg3
    "cream":       250,  # fg2
    "bright":      223,  # fg1 warm cream — used for head
    "aqua":         72,  # neutral_aqua
    "aqua_bright": 108,  # bright_aqua
    "yellow":      172,  # neutral_yellow
    "magenta":     132,  # neutral_purple
    "blue":         66,  # neutral_blue
    "red":         124,  # neutral_red
}

GRUVBOX_8 = {
    "ghost":       curses.COLOR_BLACK,
    "fade":        curses.COLOR_BLACK,
    "mid":         curses.COLOR_BLACK,
    "warm":        curses.COLOR_WHITE,
    "soft":        curses.COLOR_WHITE,
    "cream":       curses.COLOR_WHITE,
    "bright":      curses.COLOR_WHITE,
    "aqua":        curses.COLOR_CYAN,
    "aqua_bright": curses.COLOR_GREEN,
    "yellow":      curses.COLOR_YELLOW,
    "magenta":     curses.COLOR_MAGENTA,
    "blue":        curses.COLOR_BLUE,
    "red":         curses.COLOR_RED,
}

# State palette → (head accent, body accent). Heads punch slightly brighter
# than bodies so commit pulses register as a visible flash without being
# loud.
ACCENT_FROM_STATE = {
    "green":   ("aqua_bright", "aqua"),
    "amber":   ("yellow",      "yellow"),
    "magenta": ("magenta",     "magenta"),
    "cyan":    ("aqua_bright", "blue"),
    "red":     ("red",         "red"),
}
DEFAULT_PALETTE = "green"

# Soft, narrow-width glyph pool. No falling-rain feel. Mostly punctuation,
# braille dots, faint bullets.
GLYPHS_UNICODE = (
    "·••◦◦∙"
    "⠀⠁⠂⠄⠈⠐⠠⡀⢀⠃⠅⠆⠊⠌⠐⠈"
    ".,'`:;~"
    "*+-"
)
GLYPHS_ASCII = ".,'`:;*+-~"


class StateReader:
    """Polls JSON state file. Burst decays exponentially from burst_ts so
    a single commit produces a visible pulse that fades over a few seconds
    without the watcher needing to keep writing.
    """

    BURST_HALFLIFE_S = 2.5

    def __init__(self, path):
        self.path = path
        self.last_mtime = 0.0
        self.palette = DEFAULT_PALETTE
        self.intensity = 1.0
        self.burst_ts = 0.0
        self.recent = []

    def poll(self):
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return
        if mtime == self.last_mtime:
            return
        self.last_mtime = mtime
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        new_palette = data.get("palette", DEFAULT_PALETTE)
        if new_palette not in ACCENT_FROM_STATE:
            new_palette = DEFAULT_PALETTE
        self.palette = new_palette
        self.intensity = float(data.get("intensity", 1.0))
        self.burst_ts = float(data.get("burst_ts", 0.0))
        self.recent = data.get("recent", [])[:LOG_MAX_ROWS]

    def burst_factor(self):
        if self.burst_ts <= 0:
            return 1.0
        age = time.time() - self.burst_ts
        if age < 0 or age > 30:
            return 1.0
        return 1.0 + 1.2 * (0.5 ** (age / self.BURST_HALFLIFE_S))


class WatchRenderer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.frame = 0
        self.cells = {}            # (y, x) -> [age, glyph_char, accent_pair_idx]
        self.vignette = {}         # (y, x) -> int boost (adds to effective age)
        self.color_pairs = {}      # color_key -> curses pair number
        self.state = StateReader(STATE_PATH)
        self.last_w = 0
        self.last_h = 0
        self.use_unicode = True
        self.start_t = time.monotonic()
        self.message_offset = 0

        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(0)

        self.has_color = curses.has_colors()
        self.color_count = curses.COLORS if self.has_color else 0
        if self.has_color:
            curses.start_color()
            curses.use_default_colors()
            self._init_colors()
        self._check_unicode()
        self._update_size()

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _init_colors(self):
        """Allocate one color pair per gruvbox key. 256-color terms get the
        full muted palette; 8-color terms fall back to the closest base
        color and lean on A_DIM for the fade band.
        """
        palette = GRUVBOX_256 if self.color_count >= 256 else GRUVBOX_8
        for i, (key, color_idx) in enumerate(palette.items(), start=1):
            try:
                curses.init_pair(i, color_idx, -1)
                self.color_pairs[key] = i
            except curses.error:
                # init_pair can fail on terminals that lie about their
                # color count; fall back to default white.
                curses.init_pair(i, curses.COLOR_WHITE, -1)
                self.color_pairs[key] = i

    def _check_unicode(self):
        try:
            "·".encode(self.stdscr.encoding if hasattr(self.stdscr, "encoding") else "utf-8")
        except (UnicodeEncodeError, LookupError):
            self.use_unicode = False

    def _update_size(self):
        h, w = self.stdscr.getmaxyx()
        if h == self.last_h and w == self.last_w:
            return
        self.last_h, self.last_w = h, w
        self.height, self.width = h, w
        self._build_vignette()
        # Window resize: existing cells may be off-grid; drop them rather
        # than risk addstr errors, and let the breath repopulate.
        self.cells = {k: v for k, v in self.cells.items()
                      if 0 <= k[0] < h and 0 <= k[1] < w}

    def _build_vignette(self):
        """Precompute a small age-boost per cell based on distance from
        center. Cells near the edges fade through the gradient one step
        faster, producing a soft radial vignette without any background
        fill cost.
        """
        self.vignette = {}
        if self.height < 2 or self.width < 2:
            return
        cy, cx = self.height / 2.0, self.width / 2.0
        # Char cells are roughly 2:1 tall:wide; scale y so the vignette
        # reads circular, not vertically squashed.
        max_dist = math.hypot(cx, cy * 2.0)
        if max_dist == 0:
            return
        for y in range(self.height):
            for x in range(self.width):
                d = math.hypot(x - cx, (y - cy) * 2.0) / max_dist
                if d < 0.45:
                    boost = 0
                elif d < 0.70:
                    boost = 1
                elif d < 0.88:
                    boost = 2
                else:
                    boost = 3
                self.vignette[(y, x)] = boost

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _glyph(self):
        pool = GLYPHS_UNICODE if self.use_unicode else GLYPHS_ASCII
        return pool[random.randrange(len(pool))]

    def _color_key_for_age(self, age, head_key, body_key):
        """Map an effective age (cell age + vignette boost) onto the
        gruvbox gradient. Heads use the state's accent; older cells fall
        through neutral grays.
        """
        if age <= 0:
            return head_key
        if age <= 1:
            return body_key
        if age <= 3:
            return "cream"
        if age <= 6:
            return "soft"
        if age <= 10:
            return "warm"
        if age <= 14:
            return "mid"
        if age <= 18:
            return "fade"
        return "ghost"

    def _attr_for(self, color_key):
        if not self.has_color:
            return curses.A_DIM if color_key in ("fade", "ghost", "mid") else curses.A_NORMAL
        pair = self.color_pairs.get(color_key, 0)
        attr = curses.color_pair(pair)
        if self.color_count < 256 and color_key in ("fade", "ghost", "mid"):
            attr |= curses.A_DIM
        if color_key in ("bright", "aqua_bright"):
            attr |= curses.A_BOLD
        return attr

    def _safe_addstr(self, y, x, ch, attr=0):
        if 0 <= y < self.height and 0 <= x < self.width - 1:
            try:
                self.stdscr.addstr(y, x, ch, attr)
            except curses.error:
                pass

    def _breath_factor(self):
        """[0.35, 1.0] sine wave on BREATH_PERIOD_S. Modulates spawn
        probability so the field gently inhales and exhales.
        """
        phase = (time.monotonic() - self.start_t) / BREATH_PERIOD_S
        return 0.35 + 0.65 * (math.sin(phase * 2.0 * math.pi) + 1.0) / 2.0

    def _spawn(self, count, head_key, body_key):
        """Add up to `count` new cells at random unoccupied positions.
        Limits attempts to avoid pathological loops on a saturated grid.
        """
        if count <= 0 or self.height < 2 or self.width < 2:
            return
        log_reserved = min(LOG_MAX_ROWS, self.height // 3) if self.state.recent else 0
        usable_h = max(1, self.height - log_reserved)
        attempts = 0
        spawned = 0
        max_attempts = count * 4
        while spawned < count and attempts < max_attempts:
            attempts += 1
            y = random.randrange(usable_h)
            x = random.randrange(self.width - 1)
            if (y, x) in self.cells:
                continue
            self.cells[(y, x)] = [0, self._glyph(), (head_key, body_key)]
            spawned += 1

    def _draw_cells(self):
        """Tick and draw. Cells age once per frame; expired cells are
        retired. Draws each cell's glyph at the gradient color matching
        its effective age (own age + vignette boost).
        """
        retired = []
        for pos, cell in self.cells.items():
            cell[0] += 1
            age = cell[0]
            if age >= MAX_AGE:
                retired.append(pos)
                continue
            y, x = pos
            boost = self.vignette.get(pos, 0)
            head_key, body_key = cell[2]
            color_key = self._color_key_for_age(age + boost, head_key, body_key)
            self._safe_addstr(y, x, cell[1], self._attr_for(color_key))
        for pos in retired:
            del self.cells[pos]

    def _draw_log_stack(self):
        """Bottom-anchored, soft-toned commit log. Newest at the bottom.
        Long lines scroll horizontally with a per-row stagger so the
        stack doesn't move in lockstep.
        """
        recent = self.state.recent
        if not recent or self.height < 6 or self.width < 16:
            return
        if self.frame % LOG_SCROLL_EVERY_FRAMES == 0:
            self.message_offset += 1

        max_rows = min(len(recent), LOG_MAX_ROWS, max(1, self.height // 3))
        for i in range(max_rows):
            entry = recent[i]
            sha = str(entry.get("sha", ""))[:8]
            subject = str(entry.get("subject", ""))
            line = f"{sha}  {subject}" if sha else subject
            if not line:
                continue

            y = self.height - 1 - i
            usable = self.width - 1
            attr = self._attr_for("cream" if i == 0 else "soft" if i < 2 else "warm")

            if len(line) <= usable:
                text = line
            else:
                padded = line + "   ·   "
                offset = (self.message_offset + i * 7) % len(padded)
                doubled = padded + padded
                text = doubled[offset:offset + usable]
            for x, ch in enumerate(text[:usable]):
                self._safe_addstr(y, x, ch, attr)

    def draw_frame(self):
        if self.frame % STATE_POLL_FRAMES == 0:
            self.state.poll()

        self.stdscr.erase()
        self._update_size()

        if self.height < 5 or self.width < 5:
            try:
                self.stdscr.addstr(0, 0, "Terminal too small")
            except curses.error:
                pass
            return

        head_key, body_key = ACCENT_FROM_STATE.get(
            self.state.palette, ACCENT_FROM_STATE[DEFAULT_PALETTE],
        )
        burst = self.state.burst_factor()
        intensity = max(0.5, min(3.0, self.state.intensity * burst))
        breath = self._breath_factor()
        target_density = DENSITY_BASELINE * intensity * breath
        usable_cells = self.width * self.height
        target_count = int(target_density * usable_cells)
        # Spawn at most a small fraction of the deficit per frame so growth
        # is gradual; prevents jarring pop-in when intensity jumps.
        deficit = max(0, target_count - len(self.cells))
        spawns = min(deficit, max(1, target_count // 12))
        self._spawn(spawns, head_key, body_key)
        self._draw_cells()
        self._draw_log_stack()
        self.stdscr.refresh()

    def run(self):
        try:
            while True:
                t0 = time.monotonic()
                key = self.stdscr.getch()
                if key in (ord("q"), ord("Q"), 27):
                    break
                self.draw_frame()
                self.frame += 1
                elapsed = time.monotonic() - t0
                sleep_time = FRAME_TIME - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except KeyboardInterrupt:
            pass


def run_no_altscreen():
    """Run curses on the main screen buffer to preserve scrollback."""
    stdscr = curses.initscr()
    sys.stdout.write("\033[?1049l")
    sys.stdout.flush()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    try:
        renderer = WatchRenderer(stdscr)
        renderer.run()
    finally:
        stdscr.keypad(False)
        curses.echo()
        curses.nocbreak()
        curses.endwin()
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


if __name__ == "__main__":
    run_no_altscreen()
