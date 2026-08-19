#!/usr/bin/env python3
"""
Headless auto-fetcher for Clash Royale data.

Fetches player profile + battle log for each configured player tag and archives
everything into the local SQLite DB (store.py). Designed to be run on a schedule
(e.g. hourly via launchd) so battle history accumulates beyond the API's ~25-battle
window and trophy trend snapshots build up over time.

Usage:
    python3 auto_fetch.py                 # fetch the default tags below
    python3 auto_fetch.py 20GQJGRJ0J ...  # fetch specific tags

Reads CR_API_TOKEN from env or the .env file next to this script. The token is
IP-locked, so this must run from a machine whose outbound IP is whitelisted.
"""
import os
import sys
import urllib.parse
import urllib.error
from datetime import datetime, timezone

import store
from crapi import api_get, load_token, normalize_tag

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "auto_fetch.log")

# Player tags to auto-archive. Add more tags here to track multiple accounts.
DEFAULT_TAGS = [
    "#20GQJGRJ0J",   # main (Sȼøɍȼħfɍøsŧ)
    "#89RYQJRGL",    # Nɨǥħŧȼøɍɇ✨晚神
    "#U929YPC28",    # 384637
    "#C0YGVC8RV",    # Leslie✨晚神
    "#QCJY99PLG",    # 塔米饭
    "#2V2UVU8L",     # 神奇糕仔吃米饭
    "#YUQYJV08",     # RamboOo
    "#CPGRQ8VQV",    # !¡osama™️!¡
    "#8QQ29J9Q8",    # Arain
    "#UYPLJJ0JU",    # ✨Endlessイナバ❤️3M
    "#V2LUQ8880",    # Zzr
]


def log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def fetch_one(tag, token):
    enc = urllib.parse.quote(tag)
    player = api_get(f"players/{enc}", token)
    try:
        battles = api_get(f"players/{enc}/battlelog", token)
    except Exception as e:
        log(f"  [warn] battlelog failed for {tag}: {e}")
        battles = []
    now_iso = datetime.now(timezone.utc).isoformat()
    new_count = store.archive_battles(tag, battles or [])
    snap_added = store.archive_snapshot(tag, player, now_iso)
    log(f"  {tag}: {player.get('name','?')} · {player.get('trophies','?')} 杯 · "
        f"新存档 {new_count} 场 · 快照 {'+1' if snap_added else '未变'}")
    return new_count


def main():
    store.init_db()
    token = load_token()
    if not token:
        log("[error] no CR_API_TOKEN found (env or .env). Aborting.")
        sys.exit(1)

    tags = [normalize_tag(t) for t in sys.argv[1:]] or DEFAULT_TAGS
    log(f"auto_fetch start · {len(tags)} tag(s)")
    total_new = 0
    for tag in tags:
        try:
            total_new += fetch_one(tag, token)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            log(f"  [error] {tag}: HTTP {e.code} {body[:200]}")
            if e.code == 403:
                log("    -> 403: current outbound IP likely not whitelisted for this token.")
        except Exception as e:
            log(f"  [error] {tag}: {e}")
    log(f"auto_fetch done · {total_new} new battle(s) archived")


if __name__ == "__main__":
    main()
