#!/usr/bin/env python3
"""Animated ASCII bass visualizer — Ourman-inspired 140 BPM deep-dubstep wub.

A throbbing sub-bass orb pulses on the beat, radiating bass rings outward,
under an oriental lattice overlay, over a tribal-rhythm spectrum analyzer.
Tuned to 140 BPM — the tempo of the deep dubstep / 140 scene Ourman works in.
"""

import curses
import math
import time
import random
import sys

DEFAULT_BPM = 140             # the 140 scene's tempo; override with `art ourman <bpm>`
MIN_BPM, MAX_BPM = 20, 300
TARGET_FPS = 30
FRAME_TIME = 1.0 / TARGET_FPS

# Density ramp: glyphs from faint to heavy, used to shade by bass intensity
RAMP = " ·:░▒▓█"
ORB_CHARS = "▁▂▃▄▅▆▇█"
LATTICE = ["╱", "╲", "◇", "·"]   # oriental lattice motif
SPECTRUM_CHARS = "▁▂▃▄▅▆▇█"

# Fallback ASCII if terminal doesn't support unicode
FALLBACK = {
    "·": ".", "░": ".", "▒": "+", "▓": "#", "█": "#",
    "▁": ".", "▂": ":", "▃": "-", "▄": "=", "▅": "+", "▆": "*", "▇": "#",
    "╱": "/", "╲": "\\", "◇": "o",
}


class BassRenderer:
    def __init__(self, stdscr, bpm=DEFAULT_BPM):
        self.stdscr = stdscr
        self.bpm = bpm
        self.beat_time = 60.0 / bpm    # seconds per beat
        self.frame = 0
        self.start = time.monotonic()
        self.rings = []          # active bass rings: list of [radius, energy]
        self.spectrum = []       # per-column tribal-rhythm bar heights
        self.spectrum_vel = []
        self.last_beat = -1
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
        # Deep dubstep palette: bass magenta core, cyan rings, blue lattice
        curses.init_pair(1, curses.COLOR_MAGENTA, -1)   # bass orb core
        curses.init_pair(2, curses.COLOR_CYAN, -1)      # radiating bass rings
        curses.init_pair(3, curses.COLOR_BLUE, -1)      # oriental lattice
        curses.init_pair(4, curses.COLOR_GREEN, -1)     # tribal spectrum
        curses.init_pair(5, curses.COLOR_WHITE, -1)     # beat flash

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
        cols = max(1, self.width // 2)
        if len(self.spectrum) != cols:
            self.spectrum = [0.0] * cols
            self.spectrum_vel = [0.0] * cols

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

    def _beat_phase(self):
        """Returns (beat_index, phase 0..1 through current beat)."""
        elapsed = time.monotonic() - self.start
        beat_index = int(elapsed / self.beat_time)
        phase = (elapsed % self.beat_time) / self.beat_time
        return beat_index, phase

    def _on_beat(self, beat_index):
        """Fire a new bass ring + kick the spectrum. Every 4th beat = heavy drop."""
        heavy = beat_index % 4 == 0
        energy = 1.0 if heavy else 0.6
        self.rings.append([0.0, energy])
        # Tribal kick: random columns jump on the beat, harder on the drop
        kicks = max(1, len(self.spectrum) // (3 if heavy else 6))
        for _ in range(kicks):
            c = random.randint(0, len(self.spectrum) - 1)
            self.spectrum_vel[c] += (1.4 if heavy else 0.8) * random.uniform(0.6, 1.0)

    def _draw_bass_orb(self, phase, heavy_beat):
        """Sub-bass orb at center — wubs bigger right after the kick, decays through the beat."""
        cy, cx = self.height // 2, self.width // 2
        # Envelope: punch on beat (phase~0), exponential decay
        env = math.exp(-3.5 * phase)
        # LFO wub on top of the envelope — the signature dubstep growl
        wub = 0.5 + 0.5 * math.sin(self.frame * 0.6)
        intensity = env * (0.7 + 0.3 * wub)
        base_r = min(self.height, self.width // 2) * 0.32
        radius = base_r * (0.55 + 0.65 * intensity)

        for y in range(self.height):
            for x in range(0, self.width):
                dx = (x - cx) * 0.5      # aspect correction (chars ~2x tall)
                dy = (y - cy)
                dist = math.hypot(dx, dy)
                if dist > radius:
                    continue
                fill = 1.0 - (dist / radius)
                level = fill * intensity
                idx = int(level * (len(ORB_CHARS) - 1))
                if idx <= 0:
                    continue
                ch = self._ch(ORB_CHARS[idx])
                pair = 5 if (heavy_beat and idx >= len(ORB_CHARS) - 2) else 1
                self._safe_addstr(y, x, ch, self._color(pair, bold=idx > 3))

    def _draw_rings(self):
        """Concentric bass rings expanding outward from the orb."""
        cy, cx = self.height // 2, self.width // 2
        max_r = math.hypot(self.width // 2, self.height // 2) + 4
        attr_dim = self._color(2)
        attr_bold = self._color(2, bold=True)
        survivors = []
        for ring in self.rings:
            radius, energy = ring
            radius += 1.4              # expansion speed
            energy *= 0.94             # decay
            if radius < max_r and energy > 0.06:
                survivors.append([radius, energy])
            attr = attr_bold if energy > 0.5 else attr_dim
            ch = self._ch("░" if energy < 0.4 else "▒")
            steps = max(16, int(radius * 3))
            for i in range(steps):
                ang = 2 * math.pi * i / steps
                x = int(cx + math.cos(ang) * radius * 2)   # *2 undoes aspect squish
                y = int(cy + math.sin(ang) * radius)
                self._safe_addstr(y, x, ch, attr)
        self.rings = survivors[-12:]   # cap concurrent rings

    def _draw_lattice(self, phase):
        """Sparse oriental lattice overlay — drifts, brightens faintly on the beat."""
        attr = self._color(3, bold=phase < 0.15)
        spacing = 6
        off = (self.frame // 4) % spacing
        for y in range(0, self.height, 3):
            for x in range((y + off) % spacing, self.width, spacing):
                ch = LATTICE[(x + y + self.frame // 8) % len(LATTICE)]
                self._safe_addstr(y, x, self._ch(ch), attr)

    def _draw_spectrum(self):
        """Tribal-rhythm spectrum analyzer pinned to the bottom rows."""
        base_y = self.height - 1
        for i in range(len(self.spectrum)):
            # spring toward 0 with the velocity kicks from the beat
            self.spectrum_vel[i] -= self.spectrum[i] * 0.12
            self.spectrum_vel[i] *= 0.82
            self.spectrum[i] += self.spectrum_vel[i]
            if self.spectrum[i] < 0:
                self.spectrum[i] = 0.0
            h = min(int(self.spectrum[i] * 8), 8)
            x = i * 2
            for j in range(h):
                frac = (self.spectrum[i] * 8 - j)
                cidx = min(int(frac), len(SPECTRUM_CHARS) - 1)
                if cidx <= 0:
                    continue
                ch = self._ch(SPECTRUM_CHARS[cidx])
                y = base_y - j
                self._safe_addstr(y, x, ch, self._color(4, bold=j > 4))

    def _draw_hud(self, beat_index):
        bar = beat_index % 4 + 1
        label = f"OURMAN · {self.bpm} BPM · 1/{bar}  [q]uit"
        attr = self._color(5, bold=True)
        self._safe_addstr(0, max(0, (self.width - len(label)) // 2), label, attr)

    def draw_frame(self):
        self.stdscr.erase()
        self._update_size()

        if self.height < 10 or self.width < 24:
            try:
                self.stdscr.addstr(0, 0, "Terminal too small")
            except curses.error:
                pass
            return

        beat_index, phase = self._beat_phase()
        if beat_index != self.last_beat:
            self._on_beat(beat_index)
            self.last_beat = beat_index
        heavy_beat = beat_index % 4 == 0 and phase < 0.12

        self._draw_lattice(phase)
        self._draw_rings()
        self._draw_bass_orb(phase, heavy_beat)
        self._draw_spectrum()
        self._draw_hud(beat_index)

        self.stdscr.refresh()

    def run(self):
        try:
            while True:
                t0 = time.monotonic()
                key = self.stdscr.getch()
                if key in (ord('q'), ord('Q'), 27):   # q, Q, or ESC
                    break
                self.draw_frame()
                self.frame += 1
                elapsed = time.monotonic() - t0
                sleep_time = FRAME_TIME - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except KeyboardInterrupt:
            pass


def parse_bpm(argv):
    """First positional arg sets BPM (clamped to [MIN_BPM, MAX_BPM]). Non-numeric → default."""
    for arg in argv:
        if arg in ("-h", "--help"):
            print(f"usage: ourman [BPM]   (default {DEFAULT_BPM}, range {MIN_BPM}-{MAX_BPM})")
            raise SystemExit(0)
        try:
            return max(MIN_BPM, min(MAX_BPM, int(float(arg))))
        except ValueError:
            continue
    return DEFAULT_BPM


def main(stdscr):
    BassRenderer(stdscr, parse_bpm(sys.argv[1:])).run()


def run_no_altscreen():
    """Run curses on the main screen buffer to preserve scrollback and copy/paste."""
    bpm = parse_bpm(sys.argv[1:])
    stdscr = curses.initscr()
    sys.stdout.write('\033[?1049l')
    sys.stdout.flush()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    try:
        BassRenderer(stdscr, bpm).run()
    finally:
        stdscr.keypad(False)
        curses.echo()
        curses.nocbreak()
        curses.endwin()
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()


if __name__ == "__main__":
    run_no_altscreen()
