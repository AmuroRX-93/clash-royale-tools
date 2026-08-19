#!/usr/bin/env python3
"""
Shared Clash Royale API helpers (token loading, SSL, GET).

Centralizes the API base URL, token loading and the HTTP client so app.py,
fetch.py and auto_fetch.py all behave identically.

API base URL resolution (in order):
  1. CR_API_BASE env var, if set.
  2. Default: the RoyaleAPI proxy (https://proxy.royaleapi.dev/v1).

The RoyaleAPI proxy lets you whitelist a single fixed IP (45.79.218.79) on the
official developer portal instead of your own (often dynamic) outbound IP. This
is what makes cloud hosting (Koyeb, etc.) work without a static egress IP.

To hit the official API directly instead (e.g. from a whitelisted machine):
    export CR_API_BASE=https://api.clashroyale.com/v1
"""
import json
import os
import ssl
import urllib.request
import urllib.parse
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_API_BASE = "https://proxy.royaleapi.dev/v1"
OFFICIAL_API_BASE = "https://api.clashroyale.com/v1"

# RoyaleAPI proxy fixed IP -- whitelist THIS on developer.clashroyale.com.
PROXY_WHITELIST_IP = "45.79.218.79"


def api_base():
    return (os.environ.get("CR_API_BASE") or DEFAULT_API_BASE).rstrip("/")


def make_ssl_context():
    """SSL context with a working CA bundle (fixes python.org macOS cert issue)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


SSL_CONTEXT = make_ssl_context()


def load_token():
    """Load API token from env var or a .env file next to this module."""
    token = os.environ.get("CR_API_TOKEN")
    if token:
        return token.strip()
    env_path = os.path.join(HERE, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                if key.strip() == "CR_API_TOKEN":
                    return val.strip().strip('"').strip("'")
    return None


def normalize_tag(tag):
    """Normalize a player tag: uppercase, ensure leading '#'."""
    tag = (tag or "").strip().upper()
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag


def api_get(path, token):
    """GET a path (e.g. 'players/%23TAG') from the API, returning parsed JSON."""
    url = f"{api_base()}/{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=25, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))
