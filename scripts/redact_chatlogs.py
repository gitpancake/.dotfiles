#!/usr/bin/env python3
"""Redact sensitive data from Claude chatlog files in-place."""
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.home() / ".claude" / "projects"
EXTS = {".jsonl", ".json", ".md", ".txt"}

# Each entry: (name, pattern, replacement)
# Patterns ordered most-specific first.
PATTERNS = [
    # Anthropic
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "[REDACTED:anthropic_key]"),
    # OpenAI
    ("openai_key", re.compile(r"sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}"), "[REDACTED:openai_key]"),
    # GitHub
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "[REDACTED:github_pat]"),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), "[REDACTED:github_token]"),
    # Slack
    ("slack_token", re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}"), "[REDACTED:slack_token]"),
    # Stripe
    ("stripe_key", re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{20,}"), "[REDACTED:stripe_key]"),
    # AWS
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED:aws_access_key]"),
    # Sendgrid
    ("sendgrid_key", re.compile(r"\bSG\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}"), "[REDACTED:sendgrid_key]"),
    # Twilio
    ("twilio_sid", re.compile(r"\bAC[a-f0-9]{32}\b"), "[REDACTED:twilio_sid]"),
    # Google API key
    ("google_api_key", re.compile(r"\bAIza[A-Za-z0-9_\-]{30,}"), "[REDACTED:google_api_key]"),
    # JWT (3 base64url segments)
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "[REDACTED:jwt]"),
    # PEM private keys (multi-line block — need DOTALL)
    ("private_key_pem", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL), "[REDACTED:private_key_pem]"),
    # Escaped PEM (in JSON: \n form)
    ("private_key_pem_escaped", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:\\n|[^\"]){10,}?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED:private_key_pem]"),
    # SSH private key
    ("ssh_private_key", re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----.*?-----END OPENSSH PRIVATE KEY-----", re.DOTALL), "[REDACTED:ssh_private_key]"),
    # DB URLs with creds
    ("db_url", re.compile(r"\b(postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|rediss|amqp|amqps)://[^:\s/@\"']+:[^@\s\"']+@[^\s\"'<>]+"), r"\1://[REDACTED:db_creds]@host"),
    # Generic http(s) basic-auth URL
    ("http_basic_auth_url", re.compile(r"\bhttps?://[^:\s/@\"']+:[^@\s\"']+@[^\s\"'<>]+"), "[REDACTED:basic_auth_url]"),
    # Bearer tokens
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.=]{20,}"), "Bearer [REDACTED:token]"),
    # Authorization headers
    ("authorization_header", re.compile(r"(?i)(authorization[\"']?\s*:\s*[\"']?)(basic|bearer|token)\s+[A-Za-z0-9_\-\.=:]{10,}"), r"\1\2 [REDACTED:auth]"),
    # Generic token / key / secret / password assignments — JSON-ish
    ("kv_secret", re.compile(r"(?i)([\"']?(?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret[_-]?key|private[_-]?key|password|passwd|pwd|auth[_-]?token)[\"']?\s*[:=]\s*[\"'])[^\"'\s][^\"']{6,}([\"'])"), r"\1[REDACTED:secret]\2"),
    # Env-style assignments (no quotes): API_KEY=value, PASSWORD=value
    ("env_secret", re.compile(r"(?im)^([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|DSN|URL|URI)[A-Z0-9_]*)\s*=\s*([^\s\"'#][^\s\"'#]{6,})"), r"\1=[REDACTED:env]"),
    # Firebase service account "private_key" JSON field (raw escaped)
    ("firebase_private_key", re.compile(r"(\"private_key\"\s*:\s*\")[^\"]+(\")"), r"\1[REDACTED:firebase_private_key]\2"),
    # Generic high-entropy hex (64+ chars) likely keys — conservative
    ("hex_secret_64", re.compile(r"\b[a-f0-9]{64,}\b"), "[REDACTED:hex_secret]"),
]


def process_file(path: Path, counts: Counter) -> bool:
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
    files_changed = 0
    files_scanned = 0
    for dirpath, _, filenames in os.walk(ROOT):
        for fn in filenames:
            if not any(fn.endswith(e) for e in EXTS):
                continue
            files_scanned += 1
            p = Path(dirpath) / fn
            if process_file(p, counts):
                files_changed += 1
            if files_scanned % 500 == 0:
                print(f"... scanned {files_scanned}, changed {files_changed}", file=sys.stderr)

    print(f"\nDone. Scanned {files_scanned} files. Modified {files_changed}.")
    print("Redactions by type:")
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<30} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
