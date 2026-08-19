#!/usr/bin/env python3
"""
Clash Royale data fetcher.

Fetches player profile, battle log, and upcoming chests from the official
Clash Royale API and prints a human-readable report.

Usage:
    python3 fetch.py <playerTag> [playerTag2 ...]
    python3 fetch.py 20GQJGRJ0J
    python3 fetch.py "#20GQJGRJ0J" 8LQ2V0VC

The API token is read from the CR_API_TOKEN environment variable, or from a
.env file in the same directory (KEY=VALUE format).

Note: the token is IP-locked. It only works from the IP registered when the
key was created at https://developer.clashroyale.com
"""
import os
import sys
import urllib.parse
import urllib.error
from collections import Counter

from crapi import api_get as _crapi_get, load_token, normalize_tag as _norm


def api_get(path, token):
    """Thin wrapper around crapi.api_get that raises a readable RuntimeError."""
    try:
        return _crapi_get(path, token)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} for {path}: {body}") from e


def normalize_tag(tag):
    """Normalize + URL-encode a tag for path use."""
    return urllib.parse.quote(_norm(tag))


def report_player(p):
    print("=" * 56)
    print("PLAYER PROFILE")
    print("=" * 56)
    print(f"Name: {p['name']}    Tag: {p['tag']}")
    print(f"King level: {p['expLevel']}")
    print(f"Trophies: {p['trophies']}    Best: {p['bestTrophies']}")
    print(f"Arena: {p.get('arena', {}).get('name', '?')}")
    wins, losses = p["wins"], p["losses"]
    total = wins + losses
    wr = (wins / total * 100) if total else 0
    print(f"Wins: {wins}   Losses: {losses}   Battles: {p['battleCount']}")
    print(f"Win rate (wins/(wins+losses)): {wr:.1f}%")
    print(f"Three-crown wins: {p['threeCrownWins']}")
    print(f"Current win/lose streak: {p.get('currentWinLoseStreak')}")
    clan = p.get("clan", {})
    print(f"Clan: {clan.get('name', 'None')} ({clan.get('tag', '')})  Role: {p.get('role')}")
    print(f"Star points: {p.get('starPoints')}")
    fav = p.get("currentFavouriteCard", {})
    print(f"Favorite card: {fav.get('name', 'None')}")

    for label, key in [
        ("Current Path of Legends", "currentPathOfLegendSeasonResult"),
        ("Best Path of Legends", "bestPathOfLegendSeasonResult"),
        ("Last Path of Legends", "lastPathOfLegendSeasonResult"),
    ]:
        if key in p and p[key]:
            s = p[key]
            print(f"{label}: league {s.get('leagueNumber')} trophies {s.get('trophies')} rank {s.get('rank')}")

    print("\n" + "-" * 56)
    print("CURRENT DECK")
    print("-" * 56)
    deck = p.get("currentDeck", [])
    total_elixir = 0
    for c in deck:
        ev = c.get("evolutionLevel")
        ev_str = f" [Evo Lv{ev}]" if ev else ""
        elixir = c.get("elixirCost", "?")
        if isinstance(elixir, int):
            total_elixir += elixir
        sl = c.get("starLevel")
        sl_str = f" *{sl}" if sl else ""
        print(f"  - {c['name']:<22} Lv{c.get('level')}/{c.get('maxLevel')} elixir {elixir}{ev_str}{sl_str}")
    if deck:
        print(f"  Avg elixir: {total_elixir / len(deck):.1f}")

    support = p.get("supportCards", [])
    if support:
        print("\nTower troops:")
        for c in support:
            print(f"  - {c['name']} Lv{c.get('level')}/{c.get('maxLevel')}")


def report_battlelog(battles):
    print("\n" + "=" * 56)
    print(f"BATTLE LOG (last {len(battles)} battles)")
    print("=" * 56)
    wins = losses = draws = 0
    opp_cards = Counter()
    rows = []
    for b in battles:
        team = b["team"][0]
        opp = b["opponent"][0]
        tc, oc = team.get("crowns", 0), opp.get("crowns", 0)
        if tc > oc:
            res, wins = "W", wins + 1
        elif tc < oc:
            res, losses = "L", losses + 1
        else:
            res, draws = "D", draws + 1
        gm = b.get("gameMode", {}).get("name", "")
        rows.append((b.get("battleTime", "")[:15], gm, tc, oc, res, opp.get("name", "?")))
        for c in opp.get("cards", []):
            opp_cards[c["name"]] += 1

    print(f"Record: {wins}W {losses}L {draws}D")
    print("\nRecent battles (time / mode / my-opp crowns / result / opponent):")
    for t, gm, tc, oc, res, opp in rows:
        print(f"  {t}  {gm:<22} {tc}-{oc} {res}  vs {opp}")

    print("\nMost common opponent cards (meta signal, Top 15):")
    for name, cnt in opp_cards.most_common(15):
        print(f"  {name:<24} {cnt}")


def report_chests(chests):
    print("\n" + "=" * 56)
    print("UPCOMING CHESTS")
    print("=" * 56)
    for item in chests.get("items", []):
        print(f"  +{item['index']}: {item['name']}")


def process_tag(raw_tag, token):
    enc = normalize_tag(raw_tag)
    print("\n" + "#" * 60)
    print(f"# Fetching data for {raw_tag}")
    print("#" * 60)
    player = api_get(f"players/{enc}", token)
    report_player(player)
    try:
        battles = api_get(f"players/{enc}/battlelog", token)
        report_battlelog(battles)
    except RuntimeError as e:
        print(f"\n[battlelog error] {e}")
    try:
        chests = api_get(f"players/{enc}/upcomingchests", token)
        report_chests(chests)
    except RuntimeError as e:
        print(f"\n[chests error] {e}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    token = load_token()
    if not token:
        print("ERROR: no API token found.")
        print("Set CR_API_TOKEN env var, or create a .env file with:")
        print("  CR_API_TOKEN=your_token_here")
        sys.exit(1)

    for raw_tag in sys.argv[1:]:
        try:
            process_tag(raw_tag, token)
        except RuntimeError as e:
            print(f"\n[error] {raw_tag}: {e}")
            if "403" in str(e):
                print("  -> 403 usually means your current IP is not in the token's allowed list,")
                print("     or the token is invalid. Re-check the IP whitelist at developer.clashroyale.com")


if __name__ == "__main__":
    main()
