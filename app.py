#!/usr/bin/env python3
"""
Clash Royale local dashboard - backend.

A zero-dependency local web app (Python standard library only). It serves a
single-page frontend and proxies the official Clash Royale API so the browser
can fetch fresh data on demand.

Run:
    python3 app.py            # serves on http://127.0.0.1:8787
    python3 app.py 9000       # custom port

The API token is read from CR_API_TOKEN env var or a .env file next to this
script. The token is IP-locked; requests go out from THIS machine's Python
outbound IP, which must be on the token's allowed-IP list at
https://developer.clashroyale.com
"""
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import store
import crapi
from crapi import api_get, load_token, normalize_tag

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = int(os.environ.get("PORT", "8787"))
BIND_HOST = os.environ.get("HOST", "0.0.0.0")
DEFAULT_TAG = "#20GQJGRJ0J"

# Interval (seconds) for the built-in background auto-fetch. 0 disables it.
# Replaces the macOS launchd job so archiving keeps running on any host.
AUTO_FETCH_INTERVAL = int(os.environ.get("AUTO_FETCH_INTERVAL", str(3600)))

# Tracked accounts (tag -> display name), shown as quick-switch buttons in the UI.
# Keep this in sync with DEFAULT_TAGS in auto_fetch.py.
TRACKED_ACCOUNTS = [
    {"tag": "#20GQJGRJ0J", "name": "Sȼøɍȼħfɍøsŧ (主号)"},
    {"tag": "#89RYQJRGL", "name": "Nɨǥħŧȼøɍɇ✨晚神"},
    {"tag": "#U929YPC28", "name": "384637"},
    {"tag": "#C0YGVC8RV", "name": "Leslie✨晚神"},
    {"tag": "#QCJY99PLG", "name": "塔米饭"},
    {"tag": "#2V2UVU8L", "name": "神奇糕仔吃米饭"},
    {"tag": "#YUQYJV08", "name": "RamboOo"},
    {"tag": "#CPGRQ8VQV", "name": "!¡osama™️!¡"},
    {"tag": "#8QQ29J9Q8", "name": "Arain"},
    {"tag": "#UYPLJJ0JU", "name": "✨Endlessイナバ❤️3M"},
    {"tag": "#V2LUQ8880", "name": "Zzr"},
]


def make_ssl_context():
    # kept for backward-compat imports; real client lives in crapi.
    return crapi.SSL_CONTEXT


def summarize_battlelog(battles):
    """Turn raw battle log into a compact summary the frontend can render."""
    wins = losses = draws = 0
    opp_cards = Counter()
    rows = []
    modes = Counter()
    for b in battles:
        team = b.get("team", [{}])[0]
        opp = b.get("opponent", [{}])[0]
        tc = team.get("crowns", 0)
        oc = opp.get("crowns", 0)
        if tc > oc:
            result = "win"; wins += 1
        elif tc < oc:
            result = "loss"; losses += 1
        else:
            result = "draw"; draws += 1
        gm = b.get("gameMode", {}).get("name", "")
        modes[gm] += 1
        for c in opp.get("cards", []):
            opp_cards[c.get("name")] += 1
        rows.append({
            "time": b.get("battleTime", "")[:15],
            "mode": gm,
            "type": b.get("type", ""),
            "myCrowns": tc,
            "oppCrowns": oc,
            "result": result,
            "oppName": opp.get("name", "?"),
            "oppTag": opp.get("tag", ""),
            "oppCards": [store._card_brief(c, i) for i, c in enumerate(opp.get("cards", []))],
            "myCards": [store._card_brief(c, i) for i, c in enumerate(team.get("cards", []))],
            "myTowers": [store._tower_brief(c) for c in team.get("supportCards", [])],
            "oppTowers": [store._tower_brief(c) for c in opp.get("supportCards", [])],
            "myPlayers": [store._player_brief(pl) for pl in b.get("team", [])],
            "oppPlayers": [store._player_brief(pl) for pl in b.get("opponent", [])],
        })
    total = wins + losses
    return {
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "winRate": round(wins / total * 100, 1) if total else 0,
        "modes": modes.most_common(),
        "topOpponentCards": opp_cards.most_common(15),
        "battles": rows,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "CRDash/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[app] " + (fmt % args) + "\n")

    def _send_json(self, obj, status=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            self.send_error(404, "Not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route in ("/", "/index.html"):
            return self._send_file(os.path.join(HERE, "index.html"), "text/html; charset=utf-8")

        if route == "/api/config":
            return self._send_json({
                "defaultTag": DEFAULT_TAG,
                "hasToken": bool(load_token()),
                "accounts": TRACKED_ACCOUNTS,
            })

        if route == "/api/sample":
            # Offline/demo data from a local snapshot (no network). Useful when
            # the outbound IP isn't whitelisted or there's no connectivity.
            sample_path = os.path.join(HERE, "sample.json")
            try:
                with open(sample_path, encoding="utf-8") as f:
                    return self._send_json(json.load(f))
            except FileNotFoundError:
                return self._send_json({"error": "no_sample", "message": "sample.json not found"}, 404)

        if route == "/api/player":
            qs = urllib.parse.parse_qs(parsed.query)
            raw_tag = qs.get("tag", [DEFAULT_TAG])[0]
            token = load_token()
            if not token:
                return self._send_json({"error": "no_token", "message": "No CR_API_TOKEN in .env"}, 500)
            tag = normalize_tag(raw_tag)
            enc = urllib.parse.quote(tag)
            result = {"tag": tag}
            try:
                result["player"] = api_get(f"players/{enc}", token)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                try:
                    body = json.loads(body)
                except Exception:
                    pass
                return self._send_json({"error": "http_error", "status": e.code, "body": body}, 502)
            except Exception as e:
                return self._send_json({"error": "fetch_failed", "message": str(e)}, 502)
            # Resolve equipped forms (EVO/HERO) on the current deck so the frontend
            # never has to guess -- same rule as everywhere else.
            try:
                p = result["player"]
                if isinstance(p.get("currentDeck"), list):
                    p["currentDeck"] = [store._card_brief(c, i) for i, c in enumerate(p["currentDeck"])]
                if isinstance(p.get("currentDeckSupportCards"), list):
                    p["currentDeckSupportCards"] = [store._tower_brief(c) for c in p["currentDeckSupportCards"]]
            except Exception:
                pass
            # battle log + chests are best-effort
            raw_battles = None
            try:
                raw_battles = api_get(f"players/{enc}/battlelog", token)
                result["battlelog"] = summarize_battlelog(raw_battles)
            except Exception as e:
                result["battlelogError"] = str(e)
            try:
                result["chests"] = api_get(f"players/{enc}/upcomingchests", token)
            except Exception as e:
                result["chestsError"] = str(e)

            # Archive to local DB (accumulate history beyond the API's ~25 cap).
            try:
                from datetime import datetime, timezone
                now_iso = datetime.now(timezone.utc).isoformat()
                new_count = store.archive_battles(tag, raw_battles or [])
                store.archive_snapshot(tag, result["player"], now_iso)
                result["archived"] = {"newBattles": new_count}
            except Exception as e:
                result["archiveError"] = str(e)

            return self._send_json(result)

        if route == "/api/history":
            qs = urllib.parse.parse_qs(parsed.query)
            raw_tag = qs.get("tag", [DEFAULT_TAG])[0]
            tag = normalize_tag(raw_tag)
            try:
                return self._send_json(store.get_history(tag))
            except Exception as e:
                return self._send_json({"error": "history_failed", "message": str(e)}, 500)

        if route in ("/health", "/healthz", "/api/health"):
            return self._send_json({"ok": True})

        self.send_error(404, "Not found")


def _bg_fetch_once():
    """Fetch + archive every tracked account once. Used by the scheduler."""
    token = load_token()
    if not token:
        print("[autofetch] no token; skipping")
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    total_new = 0
    for acc in TRACKED_ACCOUNTS:
        tag = normalize_tag(acc["tag"])
        enc = urllib.parse.quote(tag)
        try:
            player = api_get(f"players/{enc}", token)
            try:
                battles = api_get(f"players/{enc}/battlelog", token)
            except Exception:
                battles = []
            total_new += store.archive_battles(tag, battles or [])
            store.archive_snapshot(tag, player, now_iso)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:160]
            print(f"[autofetch] {tag}: HTTP {e.code} {body}")
        except Exception as e:
            print(f"[autofetch] {tag}: {e}")
    print(f"[autofetch] done · {total_new} new battle(s) archived")


def _scheduler_loop():
    """Background thread: run _bg_fetch_once() every AUTO_FETCH_INTERVAL seconds."""
    # Small initial delay so the web server is up first.
    time.sleep(10)
    while True:
        try:
            _bg_fetch_once()
        except Exception as e:
            print(f"[autofetch] loop error: {e}")
        time.sleep(AUTO_FETCH_INTERVAL)


def main():
    store.init_db()
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    if AUTO_FETCH_INTERVAL > 0:
        t = threading.Thread(target=_scheduler_loop, daemon=True)
        t.start()
        print(f"Auto-fetch scheduler on: every {AUTO_FETCH_INTERVAL}s for {len(TRACKED_ACCOUNTS)} accounts")

    server = ThreadingHTTPServer((BIND_HOST, port), Handler)
    shown_host = "127.0.0.1" if BIND_HOST in ("0.0.0.0", "") else BIND_HOST
    print(f"Clash Royale dashboard running at http://{shown_host}:{port} (bound {BIND_HOST})")
    print(f"API base: {crapi.api_base()}")
    print(f"Default player: {DEFAULT_TAG}")
    if not load_token():
        print("WARNING: no token found - set CR_API_TOKEN env var (or .env).")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
        server.shutdown()


if __name__ == "__main__":
    main()
