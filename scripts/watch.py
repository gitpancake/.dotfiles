#!/usr/bin/env python3
"""Ambient zen renderer reactive to commit-watcher + audio-watcher state.

A sparse, breathing field of soft glyphs in a gruvbox palette. Glyphs
brighten then fade in place rather than falling. Spawn density is
modulated by a slow sine wave and by recent activity from two state
files:

  ~/.local/share/art/state.json  — commit/PR/branch events (commit-watcher)
  ~/.local/share/art/audio.json  — live-audio onsets + energy + tempo
                                   (audio-watcher capturing the
                                   BackgroundMusic loopback device)

The audio layer is bounded to "zen mode": beats add a small cluster
punch on the newest event's origin (no flashes), tempo only slows the
breath, energy widens clusters within a tight cap, and the audio_weight
knob (0..1, default 0.50) is the master mix between the audio layer and
the commit layer. Multiple watch panes reading the same state stay in
sync.
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
AUDIO_STATE_PATH = os.environ.get(
    "ART_AUDIO_STATE",
    os.path.expanduser("~/.local/share/art/audio.json"),
)
STATE_POLL_FRAMES = 10  # ~0.5s @ 20fps; mtime-only check, cheap

# Zen-mode caps on Spotify reactivity. The renderer enforces these even if
# the watcher writes higher audio_weight — beats stay as texture, not flash.
AUDIO_BEAT_BUDGET_BUMP = 2.5      # cells placed per beat at audio_weight=1.0
AUDIO_ENERGY_RATE_GAIN = 1.5      # rate_per_frame *= 1 + energy * gain * w
AUDIO_LOUD_SPREAD_GAIN = 0.80     # cluster spread *= 1 + loud_norm * gain * w
AUDIO_TEMPO_BREATH_BEATS = 8.0    # one breath = N beats when fully audio-driven
AUDIO_BEAT_DIRECT_PLACE = True    # also force-place cells on newest source per beat

BREATH_PERIOD_S = 180.0       # baseline breath at zero commits/hour (deep zen)
DENSITY_CAP = 0.030           # max fraction of cells alive at any moment
MAX_AGE = 240                 # frames a cell stays visible before retirement (12s @ 20fps)
BASE_SPAWNS_PER_SECOND = 4.0  # baseline spawn rate at zero commits/hour
LOG_MAX_ROWS = 30
LOG_SCROLL_EVERY_FRAMES = 8
SOURCE_HALFLIFE_S = 300.0     # constellation: events fade out over ~5 min
SOURCE_RING_LIMIT = 5         # how many recent events contribute spawns each frame

# Per-event-type visual profile. base_rate weights spawn share; spread_div
# controls cluster size (smaller div = bigger cluster); origin "edge" pins
# to the perimeter; start_age_pct >0 makes cells spawn already faded, used
# for branch_delete / pr_close to read as "subdued / wind-down" events.
EVENT_PROFILES = {
    "commit":        {"base_rate": 4.0, "spread_div": 5, "origin": "hash", "start_age_pct": 0.00},
    "branch_push":   {"base_rate": 2.5, "spread_div": 6, "origin": "hash", "start_age_pct": 0.00},
    "branch_create": {"base_rate": 2.0, "spread_div": 8, "origin": "edge", "start_age_pct": 0.00},
    "branch_delete": {"base_rate": 1.5, "spread_div": 6, "origin": "hash", "start_age_pct": 0.55},
    "pr_open":       {"base_rate": 3.5, "spread_div": 4, "origin": "hash", "start_age_pct": 0.00},
    "pr_close":      {"base_rate": 1.5, "spread_div": 6, "origin": "hash", "start_age_pct": 0.30},
    "pr_merge":      {"base_rate": 5.5, "spread_div": 3, "origin": "hash", "start_age_pct": 0.00},
    "pr_review":     {"base_rate": 1.0, "spread_div": 9, "origin": "hash", "start_age_pct": 0.00},
}
DEFAULT_EVENT_PROFILE = EVENT_PROFILES["commit"]


def cadence_from_rate(rate_1h):
    """Map last-hour commit count → (spawn_multiplier, breath_period_s).

    This is the taste knob. Default below is a gentle linear ramp clamped
    so an idle repo stays meditative and a storm never strobes. Tune to
    preference — try a log curve for softer high-end, or discrete tiers
    (idle / busy / storm) for more theatrical mood shifts.

    Recommended bounds: spawn_multiplier ∈ [0.5, 4.0], breath ∈ [20, 240].
    """
    spawn_multiplier = 1.0 + rate_1h / 4.0
    breath_period_s = BREATH_PERIOD_S / (1.0 + rate_1h / 3.0)
    spawn_multiplier = max(0.5, min(4.0, spawn_multiplier))
    breath_period_s = max(20.0, min(240.0, breath_period_s))
    return spawn_multiplier, breath_period_s

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

# Per-author tint variants. Author seed (hash of actor name) picks one of
# the variants for that palette, so different pushers get visibly distinct
# but on-palette shades. Each variant is a (head_key, body_key) pair.
PALETTE_VARIANTS = {
    "green":   [("aqua_bright", "aqua"),
                ("aqua_bright", "blue"),
                ("yellow",      "aqua")],
    "amber":   [("yellow",      "yellow"),
                ("bright",      "yellow"),
                ("yellow",      "warm")],
    "magenta": [("magenta",     "magenta"),
                ("magenta",     "red"),
                ("red",         "magenta")],
    "cyan":    [("aqua_bright", "blue"),
                ("aqua",        "blue"),
                ("aqua_bright", "aqua")],
    "red":     [("red",         "red"),
                ("red",         "magenta"),
                ("yellow",      "red")],
}

# Soft, narrow-width glyph pool. No falling-rain feel. Mostly punctuation,
# braille dots, faint bullets.
GLYPHS_UNICODE = (
    "·••◦◦∙"
    "⠀⠁⠂⠄⠈⠐⠠⡀⢀⠃⠅⠆⠊⠌⠐⠈"
    ".,'`:;~"
    "*+-"
)
GLYPHS_ASCII = ".,'`:;*+-~"

# Per-commit glyph "fingerprint" subsets. Picked by hashing sha[0:2] mod
# len, so the same commit always renders with the same character family —
# a visible signature distinct from neighbouring commits.
GLYPH_SUBSETS = (
    "·••◦◦∙",
    "⠀⠁⠂⠄⠈⠐⠠⡀⢀",
    "⠃⠅⠆⠊⠌⠐⠈",
    ".,'`:;~",
    "*+-",
    "·•⠁⠂.,",
    "⠄⠈⠐⠠*",
    "⠂⠄⠆⠊+-",
)


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
        self.palette_secondary = DEFAULT_PALETTE
        self.intensity = 1.0
        self.burst_ts = 0.0
        self.recent = []
        self.events = []
        self.sha = ""
        self.rate_1h = 0

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
        sec = data.get("palette_secondary", new_palette)
        if sec not in ACCENT_FROM_STATE:
            sec = new_palette
        self.palette_secondary = sec
        self.intensity = float(data.get("intensity", 1.0))
        self.burst_ts = float(data.get("burst_ts", 0.0))
        self.recent = data.get("recent", [])[:LOG_MAX_ROWS]
        events = data.get("events", []) or []
        if isinstance(events, list):
            self.events = events[:SOURCE_RING_LIMIT]
        else:
            self.events = []
        self.sha = str(data.get("sha", ""))
        try:
            self.rate_1h = max(0, int(data.get("rate_1h", 0)))
        except (TypeError, ValueError):
            self.rate_1h = 0

    def burst_factor(self):
        if self.burst_ts <= 0:
            return 1.0
        age = time.time() - self.burst_ts
        if age < 0 or age > 30:
            return 1.0
        return 1.0 + 1.2 * (0.5 ** (age / self.BURST_HALFLIFE_S))


class AudioReader:
    """Polls audio-watcher state. Beats are detected by edge-triggering
    on changes to `beat_ts`: each fresh value fires exactly one beat punch
    via consume_beat(). Energy and tempo are continuous floats sampled
    each frame; the audio-watcher writes immediately on every onset so
    end-to-end beat latency stays bounded by the renderer's per-frame
    poll (~50ms).
    """

    def __init__(self, path):
        self.path = path
        self.last_mtime = 0.0
        self.is_active = False
        self.energy = 0.0
        self.tempo = 0.0
        self.beat_ts = 0.0
        self.audio_weight = 0.0
        self.min_breath = 30.0
        self._last_seen_beat_ts = 0.0
        self._beat_pending = False

    def poll(self):
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return
        if mtime == self.last_mtime:
            return
        self.last_mtime = mtime
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        self.is_active = bool(data.get("is_active", False))
        self.energy = max(0.0, min(1.0, float(data.get("energy", 0) or 0)))
        self.tempo = float(data.get("tempo", 0) or 0)
        new_beat = float(data.get("beat_ts", 0) or 0)
        if new_beat > self._last_seen_beat_ts and new_beat > 0:
            self._beat_pending = True
            self._last_seen_beat_ts = new_beat
        self.beat_ts = new_beat
        self.audio_weight = max(0.0, min(1.0, float(data.get("audio_weight", 0.0) or 0.0)))
        self.min_breath = float(data.get("min_breath_period_s", 30.0) or 30.0)

    def consume_beat(self):
        if self._beat_pending:
            self._beat_pending = False
            return True
        return False


class WatchRenderer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.frame = 0
        self.cells = {}            # (y, x) -> [age, glyph_char, accent_pair_idx]
        self.vignette = {}         # (y, x) -> int boost (adds to effective age)
        self.color_pairs = {}      # color_key -> curses pair number
        self.state = StateReader(STATE_PATH)
        self.audio = AudioReader(AUDIO_STATE_PATH)
        self.last_w = 0
        self.last_h = 0
        self.use_unicode = True
        self.start_t = time.monotonic()
        self.message_offset = 0
        self.spawn_budget = 0.0
        # Breath uses a phase accumulator so the period can change mid-flight
        # (driven by rate_1h) without phase jumps in the sine wave.
        self.breath_phase = 0.0
        self._last_breath_t = self.start_t

        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(0)

        self.has_color = curses.has_colors()
        self.color_count = 0
        if self.has_color:
            curses.start_color()
            curses.use_default_colors()
            # COLORS is only populated after start_color(); guard with
            # getattr because some terminals expose it only conditionally.
            self.color_count = getattr(curses, "COLORS", 8)
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
                # Boost stored as fraction of MAX_AGE so it stays visible
                # at any MAX_AGE setting; outer ring jumps cells ~15% of
                # the way through the gradient.
                if d < 0.45:
                    boost = 0.0
                elif d < 0.70:
                    boost = 0.05
                elif d < 0.88:
                    boost = 0.10
                else:
                    boost = 0.15
                self.vignette[(y, x)] = boost

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _glyph(self):
        pool = GLYPHS_UNICODE if self.use_unicode else GLYPHS_ASCII
        return pool[random.randrange(len(pool))]

    def _color_key_for_pct(self, pct, head_key, body_key):
        """Map an age fraction (0..1, with vignette boost added) onto the
        gruvbox gradient. Heads use the state's accent; older cells fall
        through neutral grays. Percentage-based so the gradient holds
        shape at any MAX_AGE.
        """
        if pct <= 0.04:
            return head_key
        if pct <= 0.12:
            return body_key
        if pct <= 0.28:
            return "bright"
        if pct <= 0.48:
            return "cream"
        if pct <= 0.64:
            return "soft"
        if pct <= 0.78:
            return "warm"
        if pct <= 0.90:
            return "mid"
        return "fade"

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

    def _breath_factor(self, period_s):
        """[0.5, 1.0] sine wave with dynamic period. Integrates dt/period
        each frame so changes in `period_s` (driven by commit rate) don't
        snap the wave's phase.
        """
        now = time.monotonic()
        dt = now - self._last_breath_t
        self._last_breath_t = now
        self.breath_phase = (self.breath_phase + dt / max(0.1, period_s)) % 1.0
        return 0.5 + 0.5 * (math.sin(self.breath_phase * 2.0 * math.pi) + 1.0) / 2.0

    # ------------------------------------------------------------------
    # Multi-source spawn model: each recent event acts as a spawn source
    # with its own origin, cluster size, palette, glyph subset, and weight.
    # ------------------------------------------------------------------

    def _origin_for_event(self, ev, mode, usable_h):
        sha = str(ev.get("sha", "")) or str(ev.get("glyph_seed", ""))
        if not sha:
            return None
        try:
            yi = int(sha[0:8] or "0", 16) if len(sha) >= 8 else int(sha or "0", 16)
            xi = int(sha[8:16] or "0", 16) if len(sha) >= 16 else int((sha[::-1] or "0"), 16)
        except (ValueError, IndexError):
            return None
        if mode == "edge":
            # Pick perimeter side from the high byte; one axis pinned, the
            # other free. branch_create reads as a sparkle ringing the grid.
            edge = (yi >> 24) & 3
            if edge == 0:
                return 0, xi % max(1, self.width - 1)
            if edge == 1:
                return max(0, usable_h - 1), xi % max(1, self.width - 1)
            if edge == 2:
                return yi % usable_h, 0
            return yi % usable_h, max(0, self.width - 2)
        return yi % usable_h, xi % max(1, self.width - 1)

    def _glyph_subset_for(self, ev):
        if not self.use_unicode:
            return GLYPHS_ASCII
        seed = str(ev.get("glyph_seed", "")) or str(ev.get("sha", ""))[:2]
        if not seed:
            return GLYPHS_UNICODE
        try:
            return GLYPH_SUBSETS[int(seed, 16) % len(GLYPH_SUBSETS)]
        except ValueError:
            return GLYPHS_UNICODE

    def _tinted_accents(self, palette_key, author_seed):
        variants = PALETTE_VARIANTS.get(
            palette_key, [ACCENT_FROM_STATE.get(palette_key, ACCENT_FROM_STATE[DEFAULT_PALETTE])],
        )
        return variants[int(author_seed) % len(variants)]

    def _make_source(self, ev, idx, now, usable_h):
        """Build a spawn source dict from an event record. Returns None if
        the event is malformed or yields no usable origin.
        """
        ev_type = ev.get("type", "commit")
        profile = EVENT_PROFILES.get(ev_type, DEFAULT_EVENT_PROFILE)
        origin = self._origin_for_event(ev, profile["origin"], usable_h)
        if origin is None:
            return None
        try:
            ts = float(ev.get("ts", 0.0))
        except (TypeError, ValueError):
            ts = 0.0
        age_s = max(0.0, now - ts) if ts > 0 else 0.0
        # Newest event also gets the burst pulse on top of base weight.
        weight = profile["base_rate"] * (0.5 ** (age_s / SOURCE_HALFLIFE_S))
        if idx == 0:
            weight *= self.state.burst_factor()
        loc_delta = max(0, int(ev.get("loc_delta", 0) or 0))
        spread_factor = 1.0 + math.log1p(loc_delta) / 4.0
        base_div = profile["spread_div"]
        spread_y = max(1, int((usable_h / base_div) * spread_factor))
        spread_x = max(2, int((self.width / base_div) * spread_factor))
        palette = ev.get("palette", "green")
        if palette not in ACCENT_FROM_STATE:
            palette = DEFAULT_PALETTE
        author_seed = ev.get("author_seed", 0) or 0
        head_key, body_key = self._tinted_accents(palette, author_seed)
        sec_palette = self.state.palette_secondary if palette == self.state.palette else palette
        if sec_palette not in ACCENT_FROM_STATE:
            sec_palette = palette
        _, body_secondary = ACCENT_FROM_STATE[sec_palette]
        return {
            "type": ev_type,
            "origin": origin,
            "spread_y": spread_y,
            "spread_x": spread_x,
            "head_key": head_key,
            "body_key": body_key,
            "body_secondary_key": body_secondary,
            "glyph_subset": self._glyph_subset_for(ev),
            "weight": max(0.05, weight),
            "start_age_pct": profile["start_age_pct"],
            "palette_key": palette,
            "author_seed": int(author_seed),
        }

    def _legacy_source(self, usable_h):
        """Synthesize a single source from the legacy fields (sha, palette)
        for backwards compat with watcher versions that don't write events[].
        """
        palette = self.state.palette
        if palette not in ACCENT_FROM_STATE:
            palette = DEFAULT_PALETTE
        head_key, body_key = ACCENT_FROM_STATE[palette]
        sec = self.state.palette_secondary if self.state.palette_secondary in ACCENT_FROM_STATE else palette
        _, body_secondary = ACCENT_FROM_STATE[sec]
        sha = self.state.sha
        origin = None
        if sha:
            try:
                yi = int(sha[0:8], 16)
                xi = int(sha[8:16], 16)
                origin = (yi % usable_h, xi % max(1, self.width - 1))
            except (ValueError, IndexError):
                origin = None
        return {
            "type": "commit",
            "origin": origin,
            "spread_y": max(1, usable_h // 5),
            "spread_x": max(2, self.width // 5),
            "head_key": head_key,
            "body_key": body_key,
            "body_secondary_key": body_secondary,
            "glyph_subset": None,
            "weight": 4.0 * self.state.burst_factor(),
            "start_age_pct": 0.0,
            "palette_key": palette,
            "author_seed": 0,
        }

    def _build_sources(self, usable_h):
        if not self.state.events:
            return [self._legacy_source(usable_h)]
        now = time.time()
        sources = []
        for i, ev in enumerate(self.state.events[:SOURCE_RING_LIMIT]):
            s = self._make_source(ev, i, now, usable_h)
            if s:
                sources.append(s)
        if not sources:
            return [self._legacy_source(usable_h)]
        return sources

    def _spawn_one_from_source(self, source, usable_h):
        origin = source["origin"]
        if origin is not None and random.random() < 0.80:
            oy, ox = origin
            y = max(0, min(usable_h - 1, oy + int(random.gauss(0, source["spread_y"]))))
            x = max(0, min(self.width - 2, ox + int(random.gauss(0, source["spread_x"]))))
        else:
            y = random.randrange(usable_h)
            x = random.randrange(self.width - 1)
        if (y, x) in self.cells:
            return False
        body = source["body_key"]
        sec = source["body_secondary_key"]
        if sec and sec != body and random.random() < 0.30:
            body = sec
        glyphs = source["glyph_subset"] or (GLYPHS_UNICODE if self.use_unicode else GLYPHS_ASCII)
        glyph = glyphs[random.randrange(len(glyphs))]
        start_age = int(MAX_AGE * source["start_age_pct"])
        self.cells[(y, x)] = [start_age, glyph, (source["head_key"], body)]
        return True

    def _spawn_budget_step(self, spawns_due, sources, usable_h):
        if not sources or spawns_due <= 0:
            return
        cap = int(DENSITY_CAP * self.width * self.height)
        headroom = max(0, cap - len(self.cells))
        target = min(spawns_due, headroom)
        if target <= 0:
            return
        weights = [max(0.0, s["weight"]) for s in sources]
        total = sum(weights)
        if total <= 0:
            return
        cum = []
        running = 0.0
        for w in weights:
            running += w
            cum.append(running)
        placed = 0
        attempts = 0
        max_attempts = target * 4
        while placed < target and attempts < max_attempts:
            attempts += 1
            r = random.random() * total
            idx = len(cum) - 1
            for i, c in enumerate(cum):
                if r <= c:
                    idx = i
                    break
            if self._spawn_one_from_source(sources[idx], usable_h):
                placed += 1

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
            boost = self.vignette.get(pos, 0.0)
            head_key, body_key = cell[2]
            pct = min(1.0, age / MAX_AGE + boost)
            color_key = self._color_key_for_pct(pct, head_key, body_key)
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

    def _apply_audio_to_sources(self, sources, audio_w):
        """Per-frame audio overlay on sources. Energy widens cluster
        spread proportionally; bounded by audio_w + renderer-side cap so
        beats add texture rather than flash.
        """
        energy = self.audio.energy
        if energy <= 0:
            return
        spread_boost = 1.0 + energy * AUDIO_LOUD_SPREAD_GAIN * audio_w
        if spread_boost <= 1.001:
            return
        for s in sources:
            s["spread_y"] = max(1, int(s["spread_y"] * spread_boost))
            s["spread_x"] = max(2, int(s["spread_x"] * spread_boost))

    def draw_frame(self):
        if self.frame % STATE_POLL_FRAMES == 0:
            self.state.poll()
        # Audio polled every frame: mtime check is cheap and beats arrive
        # faster than the 0.5s commit-state poll cadence.
        self.audio.poll()

        self.stdscr.erase()
        self._update_size()

        if self.height < 5 or self.width < 5:
            try:
                self.stdscr.addstr(0, 0, "Terminal too small")
            except curses.error:
                pass
            return

        burst = self.state.burst_factor()
        intensity = max(0.5, min(3.0, self.state.intensity * burst))
        spawn_mult, breath_period = cadence_from_rate(self.state.rate_1h)

        audio_w = 0.0
        if self.audio.audio_weight > 0 and self.audio.is_active:
            audio_w = self.audio.audio_weight
            if self.audio.tempo > 20:
                # Tempo blend: stretch breath toward the song's pace, but
                # never below the configured zen floor (default 30s).
                audio_breath = max(
                    self.audio.min_breath,
                    60.0 / self.audio.tempo * AUDIO_TEMPO_BREATH_BEATS,
                )
                breath_period = breath_period * (1 - audio_w) + audio_breath * audio_w
            breath_period = max(self.audio.min_breath, breath_period)

        breath = self._breath_factor(breath_period)

        # Rate-limited spawning: float accumulator integrates a target
        # rate (spawns/second), independent of how many cells are alive
        # or have just retired. Sources (recent events) carve up that
        # budget by weight — newest event with active burst gets the
        # lion's share; older events still claim small ambient spawns at
        # their hash-derived spots, producing the constellation effect.
        rate_per_frame = (
            (BASE_SPAWNS_PER_SECOND / TARGET_FPS)
            * intensity * breath * spawn_mult
        )
        beat_fired = False
        if audio_w > 0:
            rate_per_frame *= 1.0 + self.audio.energy * AUDIO_ENERGY_RATE_GAIN * audio_w
            beat_fired = self.audio.consume_beat()

        self.spawn_budget += rate_per_frame
        spawns_due = int(self.spawn_budget)
        need_sources = spawns_due > 0 or (audio_w > 0 and beat_fired)
        if need_sources:
            log_reserved = min(LOG_MAX_ROWS, self.height // 3) if self.state.recent else 0
            usable_h = max(1, self.height - log_reserved)
            sources = self._build_sources(usable_h)
            if audio_w > 0:
                self._apply_audio_to_sources(sources, audio_w)

            # Beat punch: place cells directly on the newest source's
            # origin, bypassing the spawn-budget accumulator so each beat
            # produces a visible cluster bump regardless of how full the
            # field is. Density cap still respected.
            if AUDIO_BEAT_DIRECT_PLACE and beat_fired and sources:
                cap = int(DENSITY_CAP * self.width * self.height)
                headroom = max(0, cap - len(self.cells))
                n_punch = max(1, int(round(
                    AUDIO_BEAT_BUDGET_BUMP * audio_w * (1.0 + self.audio.energy)
                )))
                n_punch = min(n_punch, headroom)
                for _ in range(n_punch):
                    self._spawn_one_from_source(sources[0], usable_h)

            if spawns_due > 0:
                self.spawn_budget -= spawns_due
                self._spawn_budget_step(spawns_due, sources, usable_h)

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
