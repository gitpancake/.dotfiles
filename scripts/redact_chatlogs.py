#!/usr/bin/env python3
"""Redact secrets in memory/ dirs, delete all other transcripts."""
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.home() / ".claude" / "projects"
EXTS = {".jsonl", ".json", ".md", ".txt"}

PATTERNS = [
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "[REDACTED:anthropic_key]"),
    ("openai_key", re.compile(r"sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}"), "[REDACTED:openai_key]"),
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "[REDACTED:github_pat]"),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), "[REDACTED:github_token]"),
    ("slack_token", re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}"), "[REDACTED:slack_token]"),
    ("stripe_key", re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{20,}"), "[REDACTED:stripe_key]"),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED:aws_access_key]"),
    ("sendgrid_key", re.compile(r"\bSG\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}"), "[REDACTED:sendgrid_key]"),
    ("twilio_sid", re.compile(r"\bAC[a-f0-9]{32}\b"), "[REDACTED:twilio_sid]"),
    ("google_api_key", re.compile(r"\bAIza[A-Za-z0-9_\-]{30,}"), "[REDACTED:google_api_key]"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "[REDACTED:jwt]"),
    ("private_key_pem", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL), "[REDACTED:private_key_pem]"),
    ("private_key_pem_escaped", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:\\n|[^\"]){10,}?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED:private_key_pem]"),
    ("ssh_private_key", re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----.*?-----END OPENSSH PRIVATE KEY-----", re.DOTALL), "[REDACTED:ssh_private_key]"),
    ("db_url", re.compile(r"\b(postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|rediss|amqp|amqps)://[^:\s/@\"']+:[^@\s\"']+@[^\s\"'<>]+"), r"\1://[REDACTED:db_creds]@host"),
    ("http_basic_auth_url", re.compile(r"\bhttps?://[^:\s/@\"']+:[^@\s\"']+@[^\s\"'<>]+"), "[REDACTED:basic_auth_url]"),
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.=]{20,}"), "Bearer [REDACTED:token]"),
    ("authorization_header", re.compile(r"(?i)(authorization[\"']?\s*:\s*[\"']?)(basic|bearer|token)\s+[A-Za-z0-9_\-\.=:]{10,}"), r"\1\2 [REDACTED:auth]"),
    ("kv_secret", re.compile(r"(?i)([\"']?(?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret[_-]?key|private[_-]?key|password|passwd|pwd|auth[_-]?token)[\"']?\s*[:=]\s*[\"'])[^\"'\s][^\"']{6,}([\"'])"), r"\1[REDACTED:secret]\2"),
    ("env_secret", re.compile(r"(?im)^([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|DSN|URL|URI)[A-Z0-9_]*)\s*=\s*([^\s\"'#][^\s\"'#]{6,})"), r"\1=[REDACTED:env]"),
    ("firebase_private_key", re.compile(r"(\"private_key\"\s*:\s*\")[^\"]+(\")"), r"\1[REDACTED:firebase_private_key]\2"),
    ("hex_secret_64", re.compile(r"\b[a-f0-9]{64,}\b"), "[REDACTED:hex_secret]"),
]


def in_memory_dir(path: Path) -> bool:
    return "memory" in path.relative_to(ROOT).parts


def redact_file(path: Path, counts: Counter) -> bool:
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False

    new_text = text
    file_changed = False
    for name, pattern, repl in PATTERNS:
        new_text2, n = pattern.subn(repl, new_text)
        if n:
            counts[name] += n
            new_text = new_text2
            file_changed = True

    if file_changed:
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(new_text, encoding="utf-8")
            os.replace(tmp, path)
        except OSError as e:
            print(f"WRITE FAIL {path}: {e}", file=sys.stderr)
            try:
                tmp.unlink()
            except OSError:
                pass
            return False
    return file_changed


def main() -> int:
    counts = Counter()
    files_redacted = 0
    files_deleted = 0
    files_scanned = 0
    bytes_freed = 0

    for dirpath, _, filenames in os.walk(ROOT):
        for fn in filenames:
            files_scanned += 1
            p = Path(dirpath) / fn
            if in_memory_dir(p):
                if any(fn.endswith(e) for e in EXTS):
                    if redact_file(p, counts):
                        files_redacted += 1
            else:
                try:
                    bytes_freed += p.stat().st_size
                    p.unlink()
                    files_deleted += 1
                except OSError as e:
                    print(f"DELETE FAIL {p}: {e}", file=sys.stderr)
            if files_scanned % 500 == 0:
                print(f"... scanned {files_scanned}, redacted {files_redacted}, deleted {files_deleted}", file=sys.stderr)

    # Prune empty dirs (bottom-up), but keep ROOT and memory/ trees
    for dirpath, dirnames, filenames in os.walk(ROOT, topdown=False):
        d = Path(dirpath)
        if d == ROOT:
            continue
        if in_memory_dir(d):
            continue
        try:
            if not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass

    print(f"\nDone. Scanned {files_scanned}.")
    print(f"  Memory files redacted: {files_redacted}")
    print(f"  Transcript files deleted: {files_deleted} ({bytes_freed / 1_000_000:.1f} MB)")
    print("Redactions by type:")
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<30} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
