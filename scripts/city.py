#!/usr/bin/env python3
"""Animated ASCII night city skyline with twinkling stars and lit windows."""

import curses
import math
import time
import random
import sys

TARGET_FPS = 15
FRAME_TIME = 1.0 / TARGET_FPS

# Building block characters
WALL = "█"
WINDOW_LIT = "▪"
WINDOW_DARK = " "
ROOF_FLAT = "▄"
ANTENNA = "│"
ANTENNA_TIP = "◇"
GROUND = "▀"

# Sky characters
STAR_BRIGHT = "✦"
STAR_DIM = "·"
STAR_OFF = " "
MOON_BODY = "◯"

FALLBACK = {
    "█": "#", "▪": "o", "▄": "_", "▀": "=",
    "│": "|", "◇": "*", "✦": "*", "·": ".", "◯": "O",
}


class Building:
    """A single building in the skyline."""
    def __init__(self, x, width, height, has_antenna=False):
        self.x = x
        self.width = width
        self.height = height
        self.has_antenna = has_antenna
        self.windows = {}  # (row, col) -> is_lit
        self._generate_windows()

    def _generate_windows(self):
        for row in range(1, self.height - 1):
            for col in range(1, self.width - 1, 2):
                self.windows[(row, col)] = random.random() < 0.6


class Star:
    """A star in the night sky."""
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.phase = random.uniform(0, math.tau)
        self.speed = random.uniform(0.8, 2.5)
        self.brightness = 0.0  # 0.0 = off, 0.5 = dim, 1.0 = bright


class CityRenderer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.frame = 0
        self.t = 0.0
        self.buildings = []
        self.stars = []
        self.use_unicode = True
        self.shooting_star = None
        self.last_width = 0
        self.last_height = 0

        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(0)

        self._setup_colors()
        self._check_unicode()
        self._update_size()
        self._generate_city()
        self._generate_stars()

    def _setup_colors(self):
        if not curses.has_colors():
            self.has_color = False
            return
        self.has_color = True
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE, -1)    # bright stars
        curses.init_pair(2, curses.COLOR_BLUE, -1)     # dim stars / night sky
        curses.init_pair(3, curses.COLOR_YELLOW, -1)   # lit windows
        curses.init_pair(4, curses.COLOR_CYAN, -1)     # building outlines
        curses.init_pair(5, curses.COLOR_MAGENTA, -1)  # moon / accents
        curses.init_pair(6, curses.COLOR_RED, -1)      # antenna tips

    def _check_unicode(self):
        try:
            "█".encode(self.stdscr.encoding if hasattr(self.stdscr, 'encoding') else 'utf-8')
        except (UnicodeEncodeError, LookupError):
            self.use_unicode = False

    def _ch(self, c):
        if self.use_unicode:
            return c
        return FALLBACK.get(c, c)

    def _update_size(self):
        self.height, self.width = self.stdscr.getmaxyx()

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

    def _generate_city(self):
        self.buildings = []
        if self.width < 20 or self.height < 10:
            return

        skyline_base = int(self.height * 0.65)
        x = 0
        while x < self.width:
            w = random.randint(4, max(5, self.width // 8))
            h = random.randint(int(self.height * 0.15), int(self.height * 0.55))
            has_antenna = random.random() < 0.3
            b = Building(x, w, h, has_antenna)
            self.buildings.append(b)
            x += w + random.randint(0, 2)

        self.skyline_base = skyline_base

    def _generate_stars(self):
        self.stars = []
        if self.width < 10 or self.height < 5:
            return

        sky_height = int(self.height * 0.6)
        count = max(10, (self.width * sky_height) // 40)
        for _ in range(count):
            sx = random.randint(0, self.width - 1)
            sy = random.randint(0, sky_height)
            self.stars.append(Star(sx, sy))

    def _twinkle_star(self, star):
        """Update star brightness using a sine wave with per-star phase offset.

        Each star smoothly oscillates between off (0) and bright (1) based on
        its own phase and speed, creating a serene, realistic twinkling effect.
        """
        # TODO: implement twinkling — set star.brightness (0.0 to 1.0)
        # Available state: self.t (elapsed time), star.phase, star.speed
        # Approaches to consider:
        #   - Pure sine wave: smooth, dreamy     → (sin(t * speed + phase) + 1) / 2
        #   - Sine + random jitter: more organic → add small random perturbation
        #   - Threshold sine: stars "pop" on/off → round the sine to 0 or 1
        star.brightness = (math.sin(self.t * star.speed + star.phase) + 1.0) / 2.0

    def _draw_stars(self):
        for star in self.stars:
            self._twinkle_star(star)
            if star.brightness > 0.7:
                ch = self._ch(STAR_BRIGHT)
                attr = self._color(1, bold=True)
            elif star.brightness > 0.3:
                ch = self._ch(STAR_DIM)
                attr = self._color(2)
            else:
                continue
            self._safe_addstr(star.y, star.x, ch, attr)

    def _draw_moon(self):
        mx = int(self.width * 0.8)
        my = int(self.height * 0.1)
        attr = self._color(5, bold=True)
        self._safe_addstr(my, mx, self._ch(MOON_BODY), attr)
        # Glow around moon
        glow_attr = self._color(5)
        for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            self._safe_addstr(my + dy, mx + dx, self._ch(STAR_DIM), glow_attr)

    def _draw_buildings(self):
        base = self.skyline_base
        outline_attr = self._color(4)
        window_attr = self._color(3, bold=True)
        dark_attr = self._color(4)
        antenna_attr = self._color(4)
        tip_attr = self._color(6, bold=True)

        for b in self.buildings:
            top = base - b.height
            # Antenna
            if b.has_antenna:
                ax = b.x + b.width // 2
                for ay in range(max(0, top - 3), top):
                    self._safe_addstr(ay, ax, self._ch(ANTENNA), antenna_attr)
                # Blinking tip
                if self.frame % 30 < 15:
                    self._safe_addstr(max(0, top - 4), ax, self._ch(ANTENNA_TIP), tip_attr)

            # Roof
            for x in range(b.x, b.x + b.width):
                self._safe_addstr(top, x, self._ch(ROOF_FLAT), outline_attr)

            # Walls and windows
            for row in range(1, b.height):
                y = top + row
                # Left and right edges
                self._safe_addstr(y, b.x, self._ch(WALL), outline_attr)
                self._safe_addstr(y, b.x + b.width - 1, self._ch(WALL), outline_attr)
                # Windows
                for col in range(1, b.width - 1):
                    if (row, col) in b.windows:
                        is_lit = b.windows[(row, col)]
                        # Random window flicker
                        if random.random() < 0.003:
                            b.windows[(row, col)] = not is_lit
                            is_lit = not is_lit
                        if is_lit:
                            self._safe_addstr(y, b.x + col, self._ch(WINDOW_LIT), window_attr)
                        else:
                            self._safe_addstr(y, b.x + col, " ", dark_attr)
                    else:
                        self._safe_addstr(y, b.x + col, self._ch(WALL), outline_attr)

    def _draw_ground(self):
        attr = self._color(4)
        ch = self._ch(GROUND)
        for x in range(self.width - 1):
            self._safe_addstr(self.skyline_base + 1, x, ch, attr)

    def _draw_shooting_star(self):
        # Random chance to spawn
        if self.shooting_star is None and random.random() < 0.005:
            self.shooting_star = {
                'x': random.randint(0, self.width // 2),
                'y': random.randint(0, int(self.height * 0.3)),
                'dx': random.uniform(1.5, 3.0),
                'dy': random.uniform(0.3, 1.0),
                'life': random.randint(8, 15),
            }

        if self.shooting_star is not None:
            s = self.shooting_star
            attr = self._color(1, bold=True)
            trail_attr = self._color(2)

            # Draw trail
            for i in range(3):
                tx = int(s['x'] - s['dx'] * (i + 1))
                ty = int(s['y'] - s['dy'] * (i + 1))
                ch = self._ch(STAR_DIM) if i > 0 else "─"
                self._safe_addstr(ty, tx, ch, trail_attr)

            # Draw head
            self._safe_addstr(int(s['y']), int(s['x']), self._ch(STAR_BRIGHT), attr)

            s['x'] += s['dx']
            s['y'] += s['dy']
            s['life'] -= 1
            if s['life'] <= 0 or s['x'] >= self.width or s['y'] >= self.height:
                self.shooting_star = None

    def draw_frame(self):
        self.stdscr.erase()
        self._update_size()

        # Regenerate on resize
        if self.width != self.last_width or self.height != self.last_height:
            self.last_width = self.width
            self.last_height = self.height
            self._generate_city()
            self._generate_stars()

        if self.height < 10 or self.width < 20:
            try:
                self.stdscr.addstr(0, 0, "Terminal too small")
            except curses.error:
                pass
            return

        self._draw_stars()
        self._draw_moon()
        self._draw_shooting_star()
        self._draw_buildings()
        self._draw_ground()

        self.stdscr.refresh()

    def run(self):
        try:
            while True:
                t0 = time.monotonic()

                key = self.stdscr.getch()
                if key in (ord('q'), ord('Q'), 27):
                    break

                self.draw_frame()
                self.frame += 1
                self.t += FRAME_TIME

                elapsed = time.monotonic() - t0
                sleep_time = FRAME_TIME - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except KeyboardInterrupt:
            pass


def run_no_altscreen():
    """Run curses on the main screen buffer to preserve scrollback."""
    stdscr = curses.initscr()
    sys.stdout.write('\033[?1049l')
    sys.stdout.flush()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    try:
        renderer = CityRenderer(stdscr)
        renderer.run()
    finally:
        stdscr.keypad(False)
        curses.echo()
        curses.nocbreak()
        curses.endwin()
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()


if __name__ == "__main__":
    run_no_altscreen()
