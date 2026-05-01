#!/usr/bin/env python3
"""Animated ASCII matrix digital rain — falling green glyph streams."""

import curses
import random
import sys
import time

TARGET_FPS = 20
FRAME_TIME = 1.0 / TARGET_FPS

# Half-width katakana + digits + a few latin = canonical matrix glyph pool
GLYPHS_UNICODE = (
    "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜｦﾝ"
    "0123456789"
    "Z:・.=*+-<>¦"
)
GLYPHS_ASCII = "0123456789ABCDEF:.*+-<>|/\\"


class Drop:
    """Single falling rain stream in one column."""
    def __init__(self, col, height):
        self.col = col
        self.height = height
        self.reset(initial=True)

    def reset(self, initial=False):
        self.length = random.randint(6, 18)
        self.speed = random.uniform(0.4, 1.4)  # rows per frame
        # Initial stagger so streams don't all start at top simultaneously
        self.head = -random.randint(0, self.height) if initial else -random.randint(0, 6)
        self.chars = [random.randrange(1 << 30) for _ in range(self.length)]
        self.alive = True

    def step(self):
        self.head += self.speed
        if self.head - self.length > self.height:
            self.alive = False


class MatrixRenderer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.frame = 0
        self.use_unicode = True
        self.drops = []
        self.last_width = 0
        self.last_height = 0

        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(0)

        self._setup_colors()
        self._check_unicode()
        self._update_size()
        self._populate()

    def _setup_colors(self):
        self.has_color = curses.has_colors()
        if not self.has_color:
            return
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE, -1)   # head
        curses.init_pair(2, curses.COLOR_GREEN, -1)   # bright trail
        curses.init_pair(3, curses.COLOR_GREEN, -1)   # mid trail (dim via attr)
        curses.init_pair(4, curses.COLOR_BLUE, -1)    # tail fade

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

    def _mutate_chars(self, drop):
        """Randomly flip glyphs in the trail to create the shimmer effect.

        Each glyph in the drop's trail can mutate to a new random value
        between frames. Mutation rate controls the visual feel.
        """
        # TODO: implement glyph mutation — modify drop.chars in place
        # Available: drop.chars (list of int seeds), drop.length
        # Approaches to consider:
        #   - Uniform low rate    → each char ~3% chance per frame, calm shimmer
        #   - Head-biased         → head mutates often, tail rarely (info "decays")
        #   - Burst               → 0% most frames, occasional full reroll, glitchy
        for i in range(drop.length):
            if random.random() < 0.05:
                drop.chars[i] = random.randrange(1 << 30)

    def _draw_drop(self, drop):
        head_y = int(drop.head)
        for i in range(drop.length):
            y = head_y - i
            if y < 0 or y >= self.height:
                continue
            ch = self._glyph(drop.chars[i])
            if i == 0:
                attr = self._color(1, bold=True)              # white head
            elif i < 2:
                attr = self._color(2, bold=True)              # bright green
            elif i < drop.length * 0.6:
                attr = self._color(2)                         # green
            elif i < drop.length * 0.85:
                attr = self._color(3) | curses.A_DIM          # dim green
            else:
                attr = self._color(4) | curses.A_DIM          # blue fade
            self._safe_addstr(y, drop.col, ch, attr)

    def draw_frame(self):
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

        for drop in self.drops:
            if not drop.alive:
                if random.random() < 0.04:
                    drop.reset()
                continue
            self._mutate_chars(drop)
            drop.step()
            self._draw_drop(drop)

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
