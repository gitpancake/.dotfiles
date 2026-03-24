#!/usr/bin/env python3
"""Animated ASCII hologram — rotating 3D wireframe cube with holographic effects."""

import curses
import math
import time
import random
import sys

# Cube geometry: 8 vertices, 12 edges
VERTICES = [
    (-1, -1, -1), ( 1, -1, -1), ( 1,  1, -1), (-1,  1, -1),
    (-1, -1,  1), ( 1, -1,  1), ( 1,  1,  1), (-1,  1,  1),
]
EDGES = [
    (0, 1), (1, 2), (2, 3), (3, 0),  # back face
    (4, 5), (5, 6), (6, 7), (7, 4),  # front face
    (0, 4), (1, 5), (2, 6), (3, 7),  # connectors
]

TARGET_FPS = 30
FRAME_TIME = 1.0 / TARGET_FPS

# Line characters by slope direction
CHAR_HORIZONTAL = "─"
CHAR_VERTICAL = "│"
CHAR_DIAG_POS = "╲"
CHAR_DIAG_NEG = "╱"
CHAR_VERTEX = "◆"
CHAR_DOT = "·"

GLITCH_CHARS = list("░▒▓│─╱╲·*+")
SCANLINE_CHAR = "═"

# Fallback ASCII if terminal doesn't support unicode
FALLBACK = {
    "─": "-", "│": "|", "╲": "\\", "╱": "/", "◆": "*",
    "·": ".", "░": ".", "▒": "+", "▓": "#", "═": "=",
}


class HologramRenderer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.angle_x = 0.0
        self.angle_y = 0.0
        self.frame = 0
        self.scanline_y = 0
        self.glitch_rows = {}  # row -> (shift, frames_left)
        self.scatter = []  # background dots
        self.scatter_age = 0
        self.use_unicode = True

        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(0)

        self._setup_colors()
        self._check_unicode()
        self._update_size()

    def _setup_colors(self):
        if not curses.has_colors():
            self.has_color = False
            return
        self.has_color = True
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)     # primary wireframe
        curses.init_pair(2, curses.COLOR_GREEN, -1)     # scan line
        curses.init_pair(3, curses.COLOR_BLUE, -1)      # background scatter
        curses.init_pair(4, curses.COLOR_WHITE, -1)     # glitch highlight

    def _check_unicode(self):
        try:
            "─".encode(self.stdscr.encoding if hasattr(self.stdscr, 'encoding') else 'utf-8')
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

    def rotate_vertex(self, x, y, z):
        ax, ay = self.angle_x, self.angle_y
        cos_y, sin_y = math.cos(ay), math.sin(ay)
        cos_x, sin_x = math.cos(ax), math.sin(ax)
        # Rotate around Y
        x2 = x * cos_y - z * sin_y
        z2 = x * sin_y + z * cos_y
        # Rotate around X
        y2 = y * cos_x - z2 * sin_x
        z3 = y * sin_x + z2 * cos_x
        return x2, y2, z3

    def project(self, x, y, z):
        fov = 4.0
        scale = fov / (fov + z)
        # Aspect correction: terminal chars are ~2x tall as wide
        sx = int(self.width / 2 + x * scale * self.width * 0.25)
        sy = int(self.height / 2 + y * scale * self.height * 0.25)
        return sx, sy

    def bresenham(self, x0, y0, x1, y1):
        points = []
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            points.append((x0, y0))
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy
        return points

    def line_char(self, dx, dy):
        if dx == 0 and dy == 0:
            return self._ch(CHAR_VERTEX)
        angle = math.atan2(dy, dx)
        deg = abs(math.degrees(angle))
        if deg < 22.5 or deg > 157.5:
            return self._ch(CHAR_HORIZONTAL)
        elif 67.5 < deg < 112.5:
            return self._ch(CHAR_VERTICAL)
        elif angle > 0:
            return self._ch(CHAR_DIAG_POS)
        else:
            return self._ch(CHAR_DIAG_NEG)

    def _edge_color_pair(self):
        cycle = [1, 2, 3]
        return cycle[self.frame // 60 % 3]

    def _generate_scatter(self):
        self.scatter = []
        count = max(1, (self.width * self.height) // 200)
        for _ in range(count):
            sx = random.randint(0, self.width - 1)
            sy = random.randint(0, self.height - 1)
            ch = random.choice([self._ch("·"), self._ch("░")])
            self.scatter.append((sy, sx, ch))
        self.scatter_age = 0

    def _draw_scatter(self):
        if self.scatter_age >= 30 or not self.scatter:
            self._generate_scatter()
        self.scatter_age += 1
        attr = self._color(3)
        for sy, sx, ch in self.scatter:
            self._safe_addstr(sy, sx, ch, attr)

    def _draw_wireframe(self):
        color_pair = self._edge_color_pair()
        attr = self._color(color_pair, bold=True)

        # Rotate and project all vertices
        projected = []
        for vx, vy, vz in VERTICES:
            rx, ry, rz = self.rotate_vertex(vx, vy, vz)
            sx, sy = self.project(rx, ry, rz)
            projected.append((sx, sy))

        # Draw edges
        for i, j in EDGES:
            x0, y0 = projected[i]
            x1, y1 = projected[j]
            dx = x1 - x0
            dy = y1 - y0
            ch = self.line_char(dx, dy)
            points = self.bresenham(x0, y0, x1, y1)
            for idx, (px, py) in enumerate(points):
                # Intensity gradient: brighter near vertices
                dist_ratio = idx / max(len(points) - 1, 1)
                near_vertex = dist_ratio < 0.15 or dist_ratio > 0.85
                if near_vertex:
                    self._safe_addstr(py, px, ch, self._color(1, bold=True))
                else:
                    self._safe_addstr(py, px, ch, attr)

        # Draw vertices on top
        vertex_attr = self._color(1, bold=True)
        for sx, sy in projected:
            self._safe_addstr(sy, sx, self._ch(CHAR_VERTEX), vertex_attr)

    def _draw_scanline(self):
        self.scanline_y = (self.scanline_y + 1) % self.height
        attr = self._color(2, bold=True)
        ch = self._ch(SCANLINE_CHAR)
        # Draw the scan line across full width with some transparency
        for x in range(0, self.width - 1, 2):
            self._safe_addstr(self.scanline_y, x, ch, attr)
        # Dim lines adjacent to scan line
        dim_attr = self._color(2)
        for dy in [-1, 1]:
            row = self.scanline_y + dy
            if 0 <= row < self.height:
                for x in range(0, self.width - 1, 4):
                    self._safe_addstr(row, x, self._ch("─"), dim_attr)

    def _apply_glitch(self):
        # Chance to add new glitch rows
        if random.random() < 0.05:
            num_rows = random.randint(1, 3)
            for _ in range(num_rows):
                row = random.randint(0, self.height - 1)
                shift = random.choice([-3, -2, -1, 1, 2, 3])
                self.glitch_rows[row] = (shift, random.randint(2, 4))

        # Render active glitches
        expired = []
        attr = self._color(4, bold=True)
        for row, (shift, frames_left) in self.glitch_rows.items():
            if frames_left <= 0:
                expired.append(row)
                continue
            self.glitch_rows[row] = (shift, frames_left - 1)
            # Fill the shifted gap with glitch characters
            if shift > 0:
                for x in range(min(shift, self.width)):
                    ch = random.choice(GLITCH_CHARS)
                    self._safe_addstr(row, x, self._ch(ch), attr)
            else:
                for x in range(max(0, self.width + shift), self.width):
                    ch = random.choice(GLITCH_CHARS)
                    self._safe_addstr(row, x, self._ch(ch), attr)
        for row in expired:
            del self.glitch_rows[row]

    def draw_frame(self):
        self.stdscr.erase()
        self._update_size()

        if self.height < 10 or self.width < 20:
            msg = "Terminal too small"
            try:
                self.stdscr.addstr(0, 0, msg)
            except curses.error:
                pass
            return

        self._draw_scatter()
        self._draw_wireframe()
        self._draw_scanline()
        self._apply_glitch()

        self.stdscr.refresh()

    def run(self):
        try:
            while True:
                t0 = time.monotonic()

                key = self.stdscr.getch()
                if key in (ord('q'), ord('Q'), 27):  # q, Q, or ESC
                    break

                self.draw_frame()

                self.angle_y += 0.03
                self.angle_x += 0.015
                self.frame += 1

                elapsed = time.monotonic() - t0
                sleep_time = FRAME_TIME - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except KeyboardInterrupt:
            pass


def main(stdscr):
    renderer = HologramRenderer(stdscr)
    renderer.run()


def run_no_altscreen():
    """Run curses on the main screen buffer to preserve scrollback and copy/paste."""
    stdscr = curses.initscr()
    # Immediately leave alternate screen buffer so we render on the main screen
    sys.stdout.write('\033[?1049l')
    sys.stdout.flush()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    try:
        renderer = HologramRenderer(stdscr)
        renderer.run()
    finally:
        stdscr.keypad(False)
        curses.echo()
        curses.nocbreak()
        curses.endwin()
        # Clear the screen area the animation used, leave cursor at bottom
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()


if __name__ == "__main__":
    run_no_altscreen()
