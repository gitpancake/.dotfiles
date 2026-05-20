#!/usr/bin/env python3
"""granola-tix-review — fetch today's Granola docs + transcripts, ask Opus to
suggest ticket changes against ~/.claude/tickets, interactive review.

Persistent state under ~/.granola-tix/ (gitignored, outside dotfiles):
  feedback.md          append-only decision log (informs future runs)
  style.md             distilled preference doc (regenerated each run)
  runs/<utc>.jsonl     raw suggestions + decisions per run
  last-prompt.md       last Opus prompt (debugging)
  last-suggestions.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

GRANOLA_SUPABASE = Path.home() / "Library/Application Support/Granola/supabase.json"
TIX_ROOT = Path.home() / ".claude/tickets"
STATE_DIR = Path.home() / ".granola-tix"
FEEDBACK_PATH = STATE_DIR / "feedback.md"
STYLE_PATH = STATE_DIR / "style.md"
RUNS_DIR = STATE_DIR / "runs"
CLIENT_VERSION = "7.220.0"
OPUS_MODEL = "claude-opus-4-7"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

AREAS = ("integrations", "platform", "ops", "tooling", "spikes")


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def granola_post(path: str, body: dict, access: str) -> dict | list:
    headers = {
        "Authorization": f"Bearer {access}",
        "Content-Type": "application/json",
        "X-Client-Version": CLIENT_VERSION,
        "X-Granola-Platform": "darwin",
        "X-Granola-Time-Zone": os.environ.get("TZ", "America/New_York"),
        "Accept-Encoding": "gzip",
    }
    req = urllib.request.Request(
        f"https://api.granola.ai{path}",
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    r = urllib.request.urlopen(req, timeout=45)
    raw = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def refresh_access_token() -> str:
    if not GRANOLA_SUPABASE.exists():
        die(f"Granola creds not found at {GRANOLA_SUPABASE} — is Granola installed?")
    sb = json.load(GRANOLA_SUPABASE.open())
    tok = json.loads(sb["workos_tokens"])
    out = granola_post(
        "/v1/refresh-access-token",
        {"refresh_token": tok["refresh_token"]},
        tok["access_token"],
    )
    if not isinstance(out, dict) or "access_token" not in out:
        die(f"refresh-access-token returned unexpected payload: {str(out)[:200]}")
    return out["access_token"]


def fetch_recent_docs(access: str, days: int = 1) -> list[dict]:
    if days < 1:
        days = 1
    now = datetime.now().astimezone()
    midnight_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = (midnight_local - timedelta(days=days - 1)).astimezone(timezone.utc)
    out: list[dict] = []
    offset = 0
    while True:
        page = granola_post(
            "/v2/get-documents", {"limit": 50, "offset": offset}, access
        )
        docs = page.get("docs") if isinstance(page, dict) else None
        if not docs:
            break
        stop = False
        for d in docs:
            created = d.get("created_at")
            if not created:
                continue
            ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if ts < cutoff:
                stop = True
                break
            out.append(d)
        if stop or len(docs) < 50:
            break
        offset += 50
    return out


def fetch_transcript(doc_id: str, access: str) -> str:
    try:
        t = granola_post(
            "/v1/get-document-transcript", {"document_id": doc_id}, access
        )
    except urllib.error.HTTPError as e:
        return f"<transcript unavailable: HTTP {e.code}>"
    except Exception as e:
        return f"<transcript fetch failed: {e}>"
    if not isinstance(t, list):
        return ""
    lines: list[str] = []
    for u in t:
        if not u.get("is_final"):
            continue
        spk = (
            u.get("detected_speaker_name")
            or ("me" if u.get("source") == "microphone" else u.get("source") or "?")
        )
        text = (u.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{spk}] {text}")
    return "\n".join(lines)


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def index_tickets() -> list[dict]:
    items: list[dict] = []
    if not TIX_ROOT.exists():
        return items
    for path in TIX_ROOT.rglob("*.md"):
        name = path.name
        if name.startswith("_TEMPLATE") or name.startswith("_THIN") or name == "README.md":
            continue
        rel = path.relative_to(TIX_ROOT)
        try:
            txt = path.read_text(errors="ignore")
        except Exception:
            continue
        status = ""
        title = path.stem
        body = txt
        m = FRONTMATTER_RE.match(txt)
        if m:
            fm = m.group(1)
            body = txt[m.end():]
            for line in fm.splitlines():
                line = line.strip()
                if line.startswith("status:"):
                    status = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"').strip("'")
        summary = ""
        for ln in body.splitlines():
            ln_s = ln.strip()
            if ln_s and not ln_s.startswith("#") and not ln_s.startswith("```"):
                summary = ln_s[:160]
                break
        slug = str(rel.with_suffix(""))
        items.append(
            {"slug": slug, "title": title, "status": status, "summary": summary}
        )
    return items


def load_style() -> str:
    return STYLE_PATH.read_text() if STYLE_PATH.exists() else ""


def build_prompt(docs_with_tx: list[tuple[dict, str]], tix: list[dict], style: str, days: int = 1) -> str:
    parts: list[str] = []
    window = "today's" if days <= 1 else f"the last {days} days' of"
    parts.append(
        f"# Role\nYou audit {window} meeting transcripts against the engineer's "
        "local ticket DB and propose discrete, well-scoped changes.\n"
    )
    if style.strip():
        parts.append("# Learned preferences (from past runs — respect these)\n" + style.strip() + "\n")
    parts.append("# Ticket DB contract\n")
    parts.append(
        f"- Slugs are descriptive kebab-case, never IDs/numbers. Areas: {', '.join(AREAS)}.\n"
        "- New tickets are *one unit of change* with crisp acceptance criteria.\n"
        "- Edits propose a concrete addition to an existing ticket's local notes — not a rewrite.\n"
        "- Skip generic boilerplate. If a transcript is small talk only, return empty arrays.\n"
    )
    parts.append("# Existing tickets\n")
    if not tix:
        parts.append("(none)")
    else:
        for t in tix:
            parts.append(f"- {t['slug']} [{t['status'] or 'no-status'}] :: {t['title']} — {t['summary']}")
    parts.append(f"\n# Meetings ({'today' if days <= 1 else f'last {days} days'})\n")
    for d, tx in docs_with_tx:
        parts.append(
            f"## {d.get('title') or '(untitled)'}  [{d.get('id')}]  @ {d.get('created_at')}"
        )
        cal = d.get("google_calendar_event")
        if isinstance(cal, dict):
            attendees = [a.get("email") for a in (cal.get("attendees") or []) if a.get("email")]
            if attendees:
                parts.append(f"attendees: {', '.join(attendees)}")
        if d.get("summary"):
            parts.append(f"granola summary: {d['summary']}")
        if d.get("notes_markdown"):
            parts.append("notes:\n" + d["notes_markdown"])
        parts.append("transcript:\n" + (tx or "<no transcript>"))
        parts.append("")
    parts.append(
        "# Output\n"
        "Return ONLY a JSON object matching this shape:\n"
        '{\n'
        '  "new_tickets":[{"slug":"area/kebab-slug","title":"...","area":"<one of areas>","why":"1-2 sentences citing the meeting","acceptance":["...","..."]}],\n'
        '  "edits":[{"slug":"area/existing-slug","change":"concrete addition (1-2 sentences)","why":"..."}],\n'
        '  "redundant":[{"slug":"area/existing-slug","reason":"..."}]\n'
        '}\n'
        "Empty arrays are fine. Do not invent ticket slugs that already exist in the list above for new_tickets — propose those as edits instead.\n"
    )
    return "\n".join(parts)


def call_opus(prompt: str, model: str = OPUS_MODEL) -> dict:
    cmd = [
        "claude", "-p",
        "--model", model,
        "--output-format", "json",
        "--disable-slash-commands",
        "--append-system-prompt",
        "You are a JSON-only ticket triage agent. Reply with one JSON object, no prose, no code fences.",
    ]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        die(f"claude failed (exit {r.returncode}): {r.stderr[:800]}")
    try:
        wrap = json.loads(r.stdout)
    except json.JSONDecodeError:
        die(f"claude returned non-JSON wrapper: {r.stdout[:300]}")
    if isinstance(wrap, dict) and wrap.get("is_error"):
        die(f"claude error: {wrap.get('result','')[:500]}")
    result = wrap.get("result") if isinstance(wrap, dict) else wrap
    if isinstance(result, dict):
        return result
    text = result or ""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        die(f"could not parse Opus JSON. raw:\n{text[:600]}")
    return {}


def render_new_ticket(item: dict) -> str:
    accept = "\n".join(f"- [ ] {a}" for a in item.get("acceptance", []) or [])
    today = datetime.now().date().isoformat()
    title = item.get("title", "").replace('"', '\\"')
    why = (item.get("why") or "").strip()
    return (
        f'---\n'
        f'title: "{title}"\n'
        f'status: draft\n'
        f'created: {today}\n'
        f'source: granola-tix-review\n'
        f'---\n\n'
        f'{why}\n\n'
        f'## Acceptance\n{accept or "- [ ] TBD"}\n'
    )


def prompt_choice(label: str) -> tuple[str, str | None]:
    while True:
        try:
            c = input(f"  {label} [a]ccept [s]kip [e]dit-note [q]uit > ").strip().lower()
        except EOFError:
            return "q", None
        if c in ("a", "s", "q"):
            return c, None
        if c == "e":
            try:
                note = input("    note > ").strip()
            except EOFError:
                note = ""
            return "a", note or None


def interactive_review(suggestions: dict, dry_run: bool) -> list[dict]:
    decisions: list[dict] = []

    new_items = suggestions.get("new_tickets") or []
    print(f"\n== NEW TICKETS ({len(new_items)}) ==")
    for n in new_items:
        area = n.get("area") or "spikes"
        slug = n.get("slug") or ""
        if "/" not in slug:
            slug = f"{area}/{slug}"
        title = n.get("title", "")
        print(f"\n+ {slug}")
        print(f"  title: {title}")
        print(f"  why:   {n.get('why','')}")
        for a in n.get("acceptance", []) or []:
            print(f"   • {a}")
        if dry_run:
            decisions.append({"kind": "new", "slug": slug, "action": "dry-run", "item": n})
            continue
        c, note = prompt_choice(">")
        if c == "q":
            return decisions
        if c == "a":
            target = TIX_ROOT / f"{slug}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                print(f"  ! {target} exists — skipping write")
                decisions.append({"kind": "new", "slug": slug, "action": "exists", "note": note, "item": n})
            else:
                target.write_text(render_new_ticket(n))
                print(f"  wrote {target}")
                decisions.append({"kind": "new", "slug": slug, "action": "accept", "note": note, "item": n})
        else:
            decisions.append({"kind": "new", "slug": slug, "action": "skip", "item": n})

    edit_items = suggestions.get("edits") or []
    print(f"\n== EDITS ({len(edit_items)}) ==")
    for e in edit_items:
        slug = e.get("slug", "")
        print(f"\n~ {slug}")
        print(f"  change: {e.get('change','')}")
        print(f"  why:    {e.get('why','')}")
        if dry_run:
            decisions.append({"kind": "edit", "slug": slug, "action": "dry-run", "item": e})
            continue
        c, note = prompt_choice(">")
        if c == "q":
            return decisions
        if c == "a":
            target = TIX_ROOT / f"{slug}.md"
            if not target.exists():
                print(f"  ! {target} not found — skipping")
                decisions.append({"kind": "edit", "slug": slug, "action": "miss", "item": e})
                continue
            stamp = datetime.now().date().isoformat()
            existing = target.read_text()
            sep = "" if existing.endswith("\n") else "\n"
            target.write_text(
                existing + sep
                + f"\n<!-- {stamp} granola-tix-review -->\n"
                + f"- {e.get('change','').strip()}\n"
            )
            print(f"  appended to {target}")
            decisions.append({"kind": "edit", "slug": slug, "action": "accept", "note": note, "item": e})
        else:
            decisions.append({"kind": "edit", "slug": slug, "action": "skip", "item": e})

    redundant_items = suggestions.get("redundant") or []
    print(f"\n== MAYBE REDUNDANT ({len(redundant_items)}) ==")
    for r in redundant_items:
        slug = r.get("slug", "")
        print(f"\n? {slug}: {r.get('reason','')}")
        if dry_run:
            decisions.append({"kind": "redundant", "slug": slug, "action": "dry-run", "item": r})
            continue
        c, note = prompt_choice(">")
        if c == "q":
            return decisions
        decisions.append({
            "kind": "redundant", "slug": slug,
            "action": "accept" if c == "a" else "skip",
            "note": note, "item": r,
        })
    return decisions


def write_runs(decisions: list[dict]) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    p = RUNS_DIR / f"{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    with p.open("w") as fh:
        for d in decisions:
            fh.write(json.dumps(d) + "\n")
    return p


def append_feedback(decisions: list[dict]) -> None:
    if not decisions:
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_PATH.open("a") as fh:
        fh.write(f"\n## {datetime.now().isoformat(timespec='seconds')}\n")
        for d in decisions:
            it = d.get("item") or {}
            label = it.get("slug") or it.get("title") or ""
            fh.write(f"- [{d['kind']}/{d['action']}] {label}")
            if d.get("note"):
                fh.write(f" — note: {d['note']}")
            fh.write("\n")


def regenerate_style() -> None:
    if not FEEDBACK_PATH.exists():
        return
    body = FEEDBACK_PATH.read_text()
    if len(body) < 200:
        return
    prompt = (
        "Distill these accept/skip/edit decisions into a terse preference doc "
        "(<400 words, bullet points) for a ticket-suggestion assistant. Capture: "
        "what kinds of suggestions the user accepts, what they reject, recurring "
        "edit-notes, slug/area patterns, scope preferences. Output only the doc.\n\n"
        + body[-20000:]
    )
    try:
        r = subprocess.run(
            ["claude", "-p", "--model", HAIKU_MODEL,
             "--output-format", "json", "--disable-slash-commands"],
            input=prompt, capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0:
            return
        wrap = json.loads(r.stdout)
        text = (wrap.get("result") or "").strip() if isinstance(wrap, dict) else ""
        if text:
            STYLE_PATH.write_text(text + "\n")
    except Exception:
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Suggest ticket changes from today's Granola transcripts.")
    ap.add_argument("--dry-run", action="store_true", help="print suggestions, no writes/prompts")
    ap.add_argument("--cache", help="path to cached suggestions JSON (skips Granola + Opus)")
    ap.add_argument("--no-transcripts", action="store_true", help="skip transcript fetch (use notes only)")
    ap.add_argument("--model", default=OPUS_MODEL, help=f"Claude model (default {OPUS_MODEL})")
    ap.add_argument("--history", type=int, default=1, metavar="N",
                    help="include last N days (default 1 = today only; 2 = today+yesterday, ...)")
    args = ap.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    if args.cache:
        suggestions = json.load(open(args.cache))
    else:
        print("→ refreshing Granola token")
        access = refresh_access_token()
        days = max(1, args.history)
        span = "today" if days == 1 else f"last {days} days"
        print(f"→ fetching docs ({span})")
        docs = fetch_recent_docs(access, days=days)
        print(f"  {len(docs)} doc(s)")
        if not docs:
            print(f"nothing for {span}, exiting.")
            return
        dwt: list[tuple[dict, str]] = []
        for d in docs:
            title = d.get("title") or "(untitled)"
            if args.no_transcripts:
                dwt.append((d, ""))
                continue
            print(f"  · {title} — fetching transcript")
            tx = fetch_transcript(d["id"], access) if d.get("id") else ""
            dwt.append((d, tx))
        print("→ indexing local tickets")
        tix = index_tickets()
        print(f"  {len(tix)} ticket(s)")
        style = load_style()
        prompt = build_prompt(dwt, tix, style, days=days)
        (STATE_DIR / "last-prompt.md").write_text(prompt)
        approx_tokens = len(prompt) // 4
        print(f"→ asking {args.model} (~{approx_tokens:,} prompt tokens)")
        suggestions = call_opus(prompt, model=args.model)
        (STATE_DIR / "last-suggestions.json").write_text(json.dumps(suggestions, indent=2))

    n_new = len(suggestions.get("new_tickets") or [])
    n_edit = len(suggestions.get("edits") or [])
    n_red = len(suggestions.get("redundant") or [])
    print(f"\nsuggestions: {n_new} new · {n_edit} edits · {n_red} redundant")

    if args.dry_run:
        print(json.dumps(suggestions, indent=2))
        return

    if n_new == n_edit == n_red == 0:
        print("nothing to review.")
        return

    decisions = interactive_review(suggestions, dry_run=False)
    runs_path = write_runs(decisions)
    append_feedback(decisions)
    print(f"\n→ run log: {runs_path}")
    print("→ regenerating preference doc")
    regenerate_style()
    print("done.")


if __name__ == "__main__":
    main()
