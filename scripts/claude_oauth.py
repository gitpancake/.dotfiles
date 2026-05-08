"""Claude Code OAuth helper.

Reads the OAuth tokens stored by Claude Code in the macOS keychain
(service "Claude Code-credentials"), refreshes them when expired, and
exposes a `call_messages()` helper that POSTs to the Anthropic Messages
API using the OAuth bearer flow.

Falls back to ANTHROPIC_API_KEY env var if the keychain entry is
missing or refresh fails.

Tokens are persisted back to the keychain after a successful refresh so
other Claude Code processes pick up the new value.
"""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request

KEYCHAIN_SERVICE = "Claude Code-credentials"
ANTHROPIC_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_REFRESH_URL = "https://console.anthropic.com/v1/oauth/token"
MESSAGES_URL = "https://api.anthropic.com/v1/messages"
OAUTH_BETA_HEADER = "oauth-2025-04-20"
ANTHROPIC_VERSION = "2023-06-01"

CLAUDE_CODE_SYSTEM_PREFIX = (
    "You are Claude Code, Anthropic's official CLI for Claude."
)

REFRESH_LEEWAY_S = 60


def _keychain_account():
    return os.environ.get("USER") or os.environ.get("LOGNAME") or ""


def _keychain_read():
    """Return the parsed credentials dict, or None if missing."""
    try:
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-s", KEYCHAIN_SERVICE,
                "-a", _keychain_account(),
                "-w",
            ],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _keychain_write(creds):
    """Atomically replace the keychain entry with the given dict."""
    try:
        subprocess.run(
            [
                "security", "add-generic-password",
                "-U",
                "-s", KEYCHAIN_SERVICE,
                "-a", _keychain_account(),
                "-w", json.dumps(creds),
            ],
            capture_output=True, check=False, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _refresh(refresh_token):
    body = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": ANTHROPIC_OAUTH_CLIENT_ID,
    }).encode()
    req = urllib.request.Request(
        OAUTH_REFRESH_URL,
        data=body,
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError):
        return None


def get_access_token():
    """Return a fresh access token, refreshing if necessary.

    Returns None if no Claude Code OAuth credentials are present or
    refresh failed. Callers should fall back to ANTHROPIC_API_KEY.
    """
    creds = _keychain_read()
    if not creds:
        return None
    oauth = creds.get("claudeAiOauth")
    if not oauth:
        return None

    expires_at = float(oauth.get("expiresAt", 0)) / 1000.0  # ms → s
    now = time.time()

    if expires_at - now > REFRESH_LEEWAY_S:
        return oauth.get("accessToken")

    refresh_token = oauth.get("refreshToken")
    if not refresh_token:
        return oauth.get("accessToken")

    refreshed = _refresh(refresh_token)
    if not refreshed or "access_token" not in refreshed:
        # Refresh failed — return the (possibly stale) token and let the
        # API call surface the auth error if needed.
        return oauth.get("accessToken")

    new_oauth = dict(oauth)
    new_oauth["accessToken"] = refreshed["access_token"]
    if "refresh_token" in refreshed:
        new_oauth["refreshToken"] = refreshed["refresh_token"]
    if "expires_in" in refreshed:
        new_oauth["expiresAt"] = int(
            (now + float(refreshed["expires_in"])) * 1000
        )
    creds["claudeAiOauth"] = new_oauth
    _keychain_write(creds)
    return new_oauth["accessToken"]


def call_messages(model, messages, system=None, max_tokens=256, timeout=20):
    """POST to /v1/messages using OAuth bearer (or ANTHROPIC_API_KEY fallback).

    Returns the parsed response dict, or None on transport / decode
    errors. The caller is responsible for extracting `content[0].text`.

    OAuth path requires the system prompt to start with the Claude Code
    identifier — we prepend it transparently.
    """
    token = get_access_token()
    use_oauth = bool(token)
    if not use_oauth:
        token = os.environ.get("ANTHROPIC_API_KEY")
        if not token:
            return None

    if use_oauth:
        prefix = CLAUDE_CODE_SYSTEM_PREFIX
        full_system = f"{prefix}\n\n{system}" if system else prefix
        headers = {
            "Authorization": f"Bearer {token}",
            "anthropic-beta": OAUTH_BETA_HEADER,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
    else:
        full_system = system
        headers = {
            "x-api-key": token,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if full_system:
        payload["system"] = full_system

    req = urllib.request.Request(
        MESSAGES_URL,
        data=json.dumps(payload).encode(),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read())
            err["__http_status"] = e.code
            return err
        except (json.JSONDecodeError, OSError):
            return None
    except (urllib.error.URLError, json.JSONDecodeError):
        return None


def extract_text(response):
    """Pull the first text block out of a Messages API response."""
    if not isinstance(response, dict):
        return ""
    content = response.get("content")
    if not isinstance(content, list) or not content:
        return ""
    block = content[0]
    if not isinstance(block, dict):
        return ""
    return block.get("text", "") or ""


if __name__ == "__main__":
    # Quick smoke test: prints "ok" + auth path used.
    tok = get_access_token()
    if tok:
        print(f"oauth token loaded ({len(tok)} chars)")
    elif os.environ.get("ANTHROPIC_API_KEY"):
        print("falling back to ANTHROPIC_API_KEY")
    else:
        print("no auth available")
