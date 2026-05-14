#!/usr/bin/env python3
"""tix — terminal ticket explorer for ~/.claude/tickets.

Keyboard-driven, Linear-like TUI over the local ticket briefs. The list
view groups tickets by their on-disk folder; Enter opens the full
markdown in glow's pager. Zero deps beyond the stdlib + glow on PATH.
"""
import curses
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TICKETS_DIR = Path(os.environ.get("TICKETS_DIR", Path.home() / ".claude" / "tickets"))

# Linear workspace slug — used to derive a ticket URL from its `linear:` id.
# Set LINEAR_WORKSPACE in the environment; unset → no derived URL.
LINEAR_WORKSPACE = os.environ.get("LINEAR_WORKSPACE", "")

# Files under TICKETS_DIR that are not tickets — skipped by the loader.
META_FILES = {"README.md", "_TEMPLATE.md", "_EPIC-TEMPLATE.md", "_CHILD-TEMPLATE.md"}

# status label -> (icon, color name, sort rank). Lowercase keys are the current
# schema (~/.claude/tickets/README.md); title-case keys are legacy (pre-migration).
STATUS_META = {
    "active":      ("◐", "inprogress", 0),
    "open":        ("○", "todo", 1),
    "draft":       ("◌", "backlog", 2),
    "done":        ("●", "done", 3),
    "In Progress": ("◐", "inprogress", 0),
    "In Review":   ("◑", "inreview", 1),
    "Todo":        ("○", "todo", 2),
    "Backlog":     ("○", "backlog", 3),
    "Done":        ("●", "done", 4),
    "Canceled":    ("✕", "muted", 5),
    "Cancelled":   ("✕", "muted", 5),
}
DEFAULT_STATUS_META = ("·", "muted", 9)
FILTER_ORDER = ["active", "open", "draft", "done",
                "In Progress", "In Review", "Todo", "Backlog"]


def parse_frontmatter(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    fm = {}
    if not text.startswith("---"):
        return fm
    end = text.find("\n---", 3)
    if end == -1:
        return fm
    for line in text[3:end].splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
            val = val[1:-1]
        fm[key] = val
    return fm


def clean_title(title, ticket_id):
    title = re.sub(r"^\[[A-Za-z]+-\d+\]\s*", "", title.strip())
    return title or ticket_id


class Ticket:
    def __init__(self, path):
        fm = parse_frontmatter(path)
        self.path = path
        self.is_epic = path.name == "_epic.md"
        # Legacy = pre-migration schema: carried `id:`, no `linear:`/`area:`.
        self.legacy = "id" in fm and "linear" not in fm and "area" not in fm
        # An _epic.md represents its folder; everything else is its own slug.
        self.slug = path.parent.name if self.is_epic else path.stem
        self.linear = fm.get("linear", "").strip()
        # Display identifier: Linear id if synced, else the slug (legacy: `id:`).
        self.id = self.linear or fm.get("id") or self.slug
        self.epic = fm.get("epic", "") or fm.get("parent", "")
        self.area = fm.get("area", "")
        self.status = fm.get("status", "").strip() or ("open" if self.is_epic else "")
        # URL is derived from `linear:` when LINEAR_WORKSPACE is set; a legacy
        # stored `url:` is the fallback.
        self.url = (f"https://linear.app/{LINEAR_WORKSPACE}/issue/{self.linear}"
                    if self.linear and LINEAR_WORKSPACE else fm.get("url", ""))
        self.title = clean_title(fm.get("title", self.slug), self.slug)
        self.group = path.parent.name

    @property
    def meta(self):
        if self.is_epic:
            return ("▸", "accent", -1)
        return STATUS_META.get(self.status, DEFAULT_STATUS_META)


def load_tickets():
    tickets = []
    if TICKETS_DIR.is_dir():
        for path in sorted(TICKETS_DIR.rglob("*.md")):
            if path.name in META_FILES:
                continue
            # Skip other _*.md meta files, but keep _epic.md (the epic PRD).
            if path.name.startswith("_") and path.name != "_epic.md":
                continue
            try:
                tickets.append(Ticket(path))
            except Exception:
                continue
    return tickets


def group_sort_key(name):
    # underscore groups (_loose etc.) sink to the bottom
    return (name.startswith("_"), name.lower())


class App:
    def __init__(self):
        self.tickets = load_tickets()
        self.collapsed = set()
        self.filter_idx = 0
        self.query = ""
        self.search_mode = False
        self.sel = 0
        self.top = 0
        self.colors = {}
        self.rebuild()

    # ---- data ---------------------------------------------------------
    def rebuild(self):
        by_group = {}
        for t in self.tickets:
            by_group.setdefault(t.group, []).append(t)
        for g in by_group:
            by_group[g].sort(key=lambda t: (t.meta[2], t.id))
        self.by_group = by_group
        self.groups = sorted(by_group, key=group_sort_key)
        present = [s for s in FILTER_ORDER if any(t.status == s for t in self.tickets)]
        self.filters = ["All"] + present
        if self.filter_idx >= len(self.filters):
            self.filter_idx = 0
        self.rebuild_rows()

    def passes(self, t):
        f = self.filters[self.filter_idx]
        if f != "All" and t.status != f:
            return False
        if self.query:
            q = self.query.lower()
            hay = (t.id + " " + t.title + " " + t.group + " " + t.area).lower()
            if q not in hay:
                return False
        return True

    def rebuild_rows(self):
        rows = []
        for g in self.groups:
            visible = [t for t in self.by_group[g] if self.passes(t)]
            if not visible:
                continue
            rows.append({"type": "group", "group": g,
                         "count": len(visible), "total": len(self.by_group[g])})
            if g not in self.collapsed:
                for t in visible:
                    rows.append({"type": "ticket", "ticket": t})
        self.rows = rows
        if self.sel >= len(rows):
            self.sel = max(0, len(rows) - 1)

    # ---- colors -------------------------------------------------------
    def init_colors(self):
        if not curses.has_colors():
            return
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass
        spec = {
            "inprogress": curses.COLOR_YELLOW,
            "inreview": curses.COLOR_MAGENTA,
            "todo": curses.COLOR_CYAN,
            "backlog": curses.COLOR_BLUE,
            "done": curses.COLOR_GREEN,
            "muted": curses.COLOR_WHITE,
            "group": curses.COLOR_WHITE,
            "accent": curses.COLOR_CYAN,
        }
        for i, (name, fg) in enumerate(spec.items(), start=1):
            try:
                curses.init_pair(i, fg, -1)
            except curses.error:
                curses.init_pair(i, fg, curses.COLOR_BLACK)
            self.colors[name] = curses.color_pair(i)

    def attr(self, name, extra=0):
        return self.colors.get(name, 0) | extra

    # ---- rendering ----------------------------------------------------
    @staticmethod
    def _put(win, y, x, text, attr=0, maxx=None):
        if y < 0:
            return
        h, w = win.getmaxyx()
        if y >= h or x >= w:
            return
        limit = w if maxx is None else min(w, maxx)
        text = text[: max(0, limit - x)]
        if not text:
            return
        try:
            win.addstr(y, x, text, attr)
        except curses.error:
            pass

    def draw(self, stdscr):
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        self.draw_header(stdscr, w)
        body_h = max(0, h - 2)
        self.clamp_viewport(body_h)
        for i in range(body_h):
            idx = self.top + i
            if idx >= len(self.rows):
                break
            self.draw_row(stdscr, 1 + i, w, idx, self.rows[idx])
        self.draw_footer(stdscr, h, w)
        stdscr.refresh()

    def draw_header(self, stdscr, w):
        x = 0
        self._put(stdscr, 0, x, " tix ", self.attr("accent", curses.A_REVERSE | curses.A_BOLD))
        x += 6
        for i, f in enumerate(self.filters):
            label = f" {f} "
            if i == self.filter_idx:
                self._put(stdscr, 0, x, label, curses.A_REVERSE | curses.A_BOLD)
            else:
                self._put(stdscr, 0, x, label, curses.A_DIM)
            x += len(label) + 1
        matched = sum(1 for t in self.tickets if self.passes(t))
        total = len(self.tickets)
        summary = f"{matched}/{total} tickets"
        self._put(stdscr, 0, max(x, w - len(summary) - 1), summary, self.attr("accent"))

    def draw_row(self, stdscr, y, w, idx, row):
        selected = idx == self.sel
        if row["type"] == "group":
            arrow = "▶" if row["group"] in self.collapsed else "▼"
            text = f"{arrow} {row['group']}"
            count = f"({row['count']}/{row['total']})"
            attr = curses.A_BOLD | (curses.A_REVERSE if selected else 0)
            if selected:
                self._put(stdscr, y, 0, " " * (w - 1), curses.A_REVERSE)
            self._put(stdscr, y, 0, text, attr)
            self._put(stdscr, y, max(0, w - len(count) - 1), count,
                      attr if selected else self.attr("muted", curses.A_DIM))
            return

        t = row["ticket"]
        icon, color, _ = t.meta
        status = t.status
        # Legacy tickets get a `~` marker; slugs are wider than Linear ids.
        disp_id = (t.id + "~") if t.legacy else t.id
        id_col = f"{disp_id[:16]:<16}"
        if selected:
            self._put(stdscr, y, 0, " " * (w - 1), curses.A_REVERSE)
            base = curses.A_REVERSE
            self._put(stdscr, y, 2, icon, base | curses.A_BOLD)
            self._put(stdscr, y, 4, id_col, base | curses.A_BOLD)
            title_x = 4 + len(id_col) + 1
            avail = w - title_x - len(status) - 2
            self._put(stdscr, y, title_x, t.title[: max(0, avail)], base)
            self._put(stdscr, y, max(title_x, w - len(status) - 1), status, base | curses.A_DIM)
        else:
            self._put(stdscr, y, 2, icon, self.attr(color, curses.A_BOLD))
            self._put(stdscr, y, 4, id_col, curses.A_DIM)
            title_x = 4 + len(id_col) + 1
            avail = w - title_x - len(status) - 2
            self._put(stdscr, y, title_x, t.title[: max(0, avail)])
            self._put(stdscr, y, max(title_x, w - len(status) - 1), status,
                      self.attr(color))

    def draw_footer(self, stdscr, h, w):
        y = h - 1
        if self.search_mode:
            prompt = f"/{self.query}"
            self._put(stdscr, y, 0, " " * (w - 1), curses.A_REVERSE)
            self._put(stdscr, y, 0, prompt, curses.A_REVERSE)
            try:
                stdscr.move(y, min(len(prompt), w - 1))
            except curses.error:
                pass
            return
        hints = ("↑↓ move  ⏎ open  space fold  tab filter  "
                 "/ search  o url  r reload  q quit")
        if self.query:
            hints = f"filter:/{self.query}   " + hints
        self._put(stdscr, y, 0, hints, self.attr("muted", curses.A_DIM))

    # ---- viewport -----------------------------------------------------
    def clamp_viewport(self, body_h):
        if body_h <= 0:
            return
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + body_h:
            self.top = self.sel - body_h + 1
        self.top = max(0, min(self.top, max(0, len(self.rows) - body_h)))

    def move(self, delta, body_h):
        if not self.rows:
            return
        self.sel = max(0, min(len(self.rows) - 1, self.sel + delta))

    # ---- actions ------------------------------------------------------
    def current(self):
        if 0 <= self.sel < len(self.rows):
            return self.rows[self.sel]
        return None

    def toggle_group(self, name):
        if name in self.collapsed:
            self.collapsed.discard(name)
        else:
            self.collapsed.add(name)
        self.rebuild_rows()

    def toggle_all(self):
        if len(self.collapsed) < len(self.groups):
            self.collapsed = set(self.groups)
        else:
            self.collapsed.clear()
        self.rebuild_rows()

    def open_ticket(self, stdscr, ticket):
        pager = shutil.which("glow")
        cmd = [pager, "-p", str(ticket.path)] if pager else \
              [os.environ.get("PAGER", "less"), str(ticket.path)]
        curses.def_prog_mode()
        curses.endwin()
        try:
            subprocess.run(cmd)
        except Exception:
            pass
        curses.reset_prog_mode()
        stdscr.refresh()

    def open_url(self, ticket):
        if not ticket.url:
            return
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        if not shutil.which(opener):
            return
        try:
            subprocess.Popen([opener, ticket.url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def reload(self):
        self.tickets = load_tickets()
        self.rebuild()

    # ---- main loop ----------------------------------------------------
    def run(self, stdscr):
        curses.curs_set(0)
        stdscr.keypad(True)
        self.init_colors()
        while True:
            h, _ = stdscr.getmaxyx()
            body_h = max(1, h - 2)
            curses.curs_set(1 if self.search_mode else 0)
            self.draw(stdscr)
            ch = stdscr.getch()
            if self.search_mode:
                self.handle_search_key(ch)
                continue
            if ch in (ord("q"), 27):
                return
            elif ch in (curses.KEY_DOWN, ord("j")):
                self.move(1, body_h)
            elif ch in (curses.KEY_UP, ord("k")):
                self.move(-1, body_h)
            elif ch == curses.KEY_NPAGE or ch == 4:  # PgDn / Ctrl-D
                self.move(body_h // 2 if ch == 4 else body_h, body_h)
            elif ch == curses.KEY_PPAGE or ch == 21:  # PgUp / Ctrl-U
                self.move(-(body_h // 2) if ch == 21 else -body_h, body_h)
            elif ch == ord("g"):
                self.sel = 0
            elif ch == ord("G"):
                self.sel = max(0, len(self.rows) - 1)
            elif ch in (curses.KEY_ENTER, 10, 13, curses.KEY_RIGHT, ord("l")):
                self.activate(stdscr)
            elif ch == ord(" "):
                row = self.current()
                if row:
                    name = row["group"] if row["type"] == "group" else row["ticket"].group
                    self.toggle_group(name)
            elif ch in (curses.KEY_LEFT, ord("h")):
                row = self.current()
                if row and row["type"] == "ticket":
                    self.toggle_group(row["ticket"].group)
                elif row and row["type"] == "group" and row["group"] not in self.collapsed:
                    self.toggle_group(row["group"])
            elif ch == ord("\t"):
                self.filter_idx = (self.filter_idx + 1) % len(self.filters)
                self.rebuild_rows()
            elif ch == curses.KEY_BTAB:
                self.filter_idx = (self.filter_idx - 1) % len(self.filters)
                self.rebuild_rows()
            elif ord("1") <= ch <= ord("9"):
                i = ch - ord("1")
                if i < len(self.filters):
                    self.filter_idx = i
                    self.rebuild_rows()
            elif ch == ord("/"):
                self.search_mode = True
            elif ch == ord("o"):
                row = self.current()
                if row and row["type"] == "ticket":
                    self.open_url(row["ticket"])
            elif ch == ord("r"):
                self.reload()
            elif ch in (ord("C"), ord("z")):
                self.toggle_all()

    def activate(self, stdscr):
        row = self.current()
        if not row:
            return
        if row["type"] == "group":
            self.toggle_group(row["group"])
        else:
            self.open_ticket(stdscr, row["ticket"])

    def handle_search_key(self, ch):
        if ch in (27,):  # ESC — cancel
            self.search_mode = False
            self.query = ""
            self.rebuild_rows()
        elif ch in (curses.KEY_ENTER, 10, 13):  # commit
            self.search_mode = False
            self.rebuild_rows()
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            self.query = self.query[:-1]
            self.rebuild_rows()
        elif 32 <= ch < 127:
            self.query += chr(ch)
            self.rebuild_rows()


def main():
    if not TICKETS_DIR.is_dir():
        print(f"tix: no ticket directory at {TICKETS_DIR}", file=sys.stderr)
        return 1
    app = App()
    if not app.tickets:
        print(f"tix: no tickets found under {TICKETS_DIR}", file=sys.stderr)
        return 1
    curses.wrapper(app.run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
