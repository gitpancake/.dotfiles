#!/usr/bin/env python3
"""Animated ASCII matrix digital rain — falling green glyph streams.

Optionally reactive to a shared state file at $ART_STATE_FILE
(default: ~/.local/share/art/state.json). When present, palette,
intensity, burst, and an optional scrolling message are applied live.
All running matrix.py instances reading the same state stay in sync.
"""

import curses
import json
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
STATE_POLL_FRAMES = 10  # ~0.5s @ 20fps; mtime check only, cheap

# Half-width katakana + digits + a few latin = canonical matrix glyph pool
GLYPHS_UNICODE = (
    "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜｦﾝ"
    "0123456789"
    "Z:・.=*+-<>¦"
)
GLYPHS_ASCII = "0123456789ABCDEF:.*+-<>|/\\"


def _palettes():
    """Built lazily so curses constants are available."""
    return {
        "green":   (curses.COLOR_WHITE, curses.COLOR_GREEN,   curses.COLOR_GREEN,   curses.COLOR_BLUE),
        "amber":   (curses.COLOR_WHITE, curses.COLOR_YELLOW,  curses.COLOR_YELLOW,  curses.COLOR_RED),
        "magenta": (curses.COLOR_WHITE, curses.COLOR_MAGENTA, curses.COLOR_MAGENTA, curses.COLOR_BLUE),
        "cyan":    (curses.COLOR_WHITE, curses.COLOR_CYAN,    curses.COLOR_CYAN,    curses.COLOR_BLUE),
        "red":     (curses.COLOR_WHITE, curses.COLOR_RED,     curses.COLOR_RED,     curses.COLOR_YELLOW),
    }


DEFAULT_PALETTE = "green"


class Drop:
    """Single falling rain stream in one column."""
    def __init__(self, col, height):
        self.col = col
        self.height = height
        self.reset(initial=True)

    def reset(self, initial=False):
        self.length = random.randint(6, 18)
        self.speed = random.uniform(0.4, 1.4)  # rows per frame
        self.head = -random.randint(0, self.height) if initial else -random.randint(0, 6)
        self.chars = [random.randrange(1 << 30) for _ in range(self.length)]
        self.alive = True

    def step(self, speed_mult=1.0):
        self.head += self.speed * speed_mult
        if self.head - self.length > self.height:
            self.alive = False


class StateReader:
    """Polls JSON state file. Burst decays exponentially from burst_ts so
    a single commit produces a visible wave that fades over ~5s without
    requiring the watcher to keep writing.
    """

    BURST_HALFLIFE_S = 2.5

    def __init__(self, path):
        self.path = path
        self.last_mtime = 0.0
        self.palette = DEFAULT_PALETTE
        self.intensity = 1.0
        self.burst_ts = 0.0
        self.message = ""
        self.recent = []
        self._dirty = True

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
        if new_palette not in _palettes():
            new_palette = DEFAULT_PALETTE
        if new_palette != self.palette:
            self.palette = new_palette
            self._dirty = True

        self.intensity = float(data.get("intensity", 1.0))
        self.burst_ts = float(data.get("burst_ts", 0.0))
        self.message = str(data.get("message", ""))[:500]
        self.recent = data.get("recent", [])[:8]

    def burst_factor(self):
        if self.burst_ts <= 0:
            return 1.0
        age = time.time() - self.burst_ts
        if age < 0 or age > 30:
            return 1.0
        return 1.0 + 1.5 * (0.5 ** (age / self.BURST_HALFLIFE_S))

    def consume_dirty(self):
        d = self._dirty
        self._dirty = False
        return d


class MatrixRenderer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.frame = 0
        self.use_unicode = True
        self.drops = []
        self.last_width = 0
        self.last_height = 0
        self.state = StateReader(STATE_PATH)
        self.message_offset = 0

        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(0)

        self.has_color = curses.has_colors()
        if self.has_color:
            curses.start_color()
            curses.use_default_colors()
        self._apply_palette()
        self._check_unicode()
        self._update_size()
        self._populate()

    def _apply_palette(self):
        if not self.has_color:
            return
        head, bright, mid, tail = _palettes()[self.state.palette]
        curses.init_pair(1, head, -1)
        curses.init_pair(2, bright, -1)
        curses.init_pair(3, mid, -1)
        curses.init_pair(4, tail, -1)

    def _check_unicode(self):
        try:
            "ｱ".encode(self.stdscr.encoding if hasattr(self.stdscr, "encoding") else "utf-8")
        except (UnicodeEncodeError, LookupError):
            self.use_unicode = False

    def _glyph(self, seed):
        pool = GLYPHS_UNICODE if self.use_unicode else GLYPHS_ASCII
        return pool[seed % len(pool)]

    def _update_size(self):
        self.height, self.width = self.stdscr.getmaxyx()

    def _populate(self):
        self.drops = [Drop(c, self.height) for c in range(self.width)]

    def _color(self, pair_num, bold=False):
        if not self.has_color:
            return curses.A_BOLD if bold else curses.A_NORMAL
        attr = curses.color_pair(pair_num)
        if bold:
            attr |= curses.A_BOLD
        return attr

    def _safe_addstr(self, y, x, ch, attr=0):
        if 0 <= y < self.height and 0 <= x < self.width:
            try:
                self.stdscr.addstr(y, x, ch, attr)
            except curses.error:
                pass

    def _mutate_chars(self, drop, mutation_rate):
        for i in range(drop.length):
            if random.random() < mutation_rate:
                drop.chars[i] = random.randrange(1 << 30)

    def _draw_drop(self, drop):
        head_y = int(drop.head)
        for i in range(drop.length):
            y = head_y - i
            if y < 0 or y >= self.height:
                continue
            ch = self._glyph(drop.chars[i])
            if i == 0:
                attr = self._color(1, bold=True)
            elif i < 2:
                attr = self._color(2, bold=True)
            elif i < drop.length * 0.6:
                attr = self._color(2)
            elif i < drop.length * 0.85:
                attr = self._color(3) | curses.A_DIM
            else:
                attr = self._color(4) | curses.A_DIM
            self._safe_addstr(y, drop.col, ch, attr)

    def _draw_message(self):
        msg = self.state.message
        if not msg or self.height < 3 or self.width < 10:
            return
        padded = msg + "   ·   "
        offset = self.message_offset % len(padded)
        doubled = padded + padded
        slice_ = doubled[offset:offset + self.width]
        y = self.height - 1
        attr = self._color(1, bold=True) | curses.A_REVERSE
        for x, ch in enumerate(slice_[: self.width - 1]):
            self._safe_addstr(y, x, ch, attr)
        self.message_offset += 1

    def draw_frame(self):
        if self.frame % STATE_POLL_FRAMES == 0:
            self.state.poll()
            if self.state.consume_dirty():
                self._apply_palette()

        self.stdscr.erase()
        self._update_size()

        if self.width != self.last_width or self.height != self.last_height:
            self.last_width = self.width
            self.last_height = self.height
            self._populate()

        if self.height < 5 or self.width < 5:
            try:
                self.stdscr.addstr(0, 0, "Terminal too small")
            except curses.error:
                pass
            return

        speed_mult = self.state.burst_factor()
        intensity = max(0.2, min(3.0, self.state.intensity * speed_mult))
        respawn_rate = 0.04 * intensity
        mutation_rate = 0.05 * intensity

        for drop in self.drops:
            if not drop.alive:
                if random.random() < respawn_rate:
                    drop.reset()
                continue
            self._mutate_chars(drop, mutation_rate)
            drop.step(speed_mult)
            self._draw_drop(drop)

        self._draw_message()
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
        renderer = MatrixRenderer(stdscr)
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
