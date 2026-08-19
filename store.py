#!/usr/bin/env python3
"""
Local archive/storage for Clash Royale data (SQLite, stdlib only).

Since the official API only returns the ~25 most recent battles, we accumulate
history locally: every fetch upserts battles (deduplicated by a stable key) and
records a profile snapshot for trend charts.
"""
import os
import json

import db

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = db.SQLITE_PATH

# Backend-neutral connection + placeholder translation live in db.py, so this
# module works on both local SQLite and cloud Postgres (Neon) unchanged.
get_conn = db.get_conn
_q = db._translate


def init_db():
    db.init_schema()


def archive_battles(player_tag, battles):
    """Upsert a list of raw battle objects. Returns count of NEW battles."""
    if not battles:
        return 0
    conn = get_conn()
    new = 0
    try:
        for b in battles:
            team = (b.get("team") or [{}])[0]
            opp = (b.get("opponent") or [{}])[0]
            btime = b.get("battleTime", "")
            mode = b.get("gameMode", {}).get("name", "")
            bid = f"{player_tag}|{btime}|{mode}"
            tc = team.get("crowns", 0)
            oc = opp.get("crowns", 0)
            result = "win" if tc > oc else "loss" if tc < oc else "draw"
            values = (bid, player_tag, btime, mode, b.get("type", ""), tc, oc,
                      result, opp.get("name", ""), opp.get("tag", ""), json.dumps(b))
            if db.upsert_battle(conn, values):
                new += 1
        if not db.IS_POSTGRES:
            conn.commit()
    finally:
        conn.close()
    return new


def archive_snapshot(player_tag, player, ts):
    """Record one profile snapshot. Skips if identical to the latest one."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            _q("SELECT trophies, battle_count FROM snapshots "
               "WHERE player_tag = ? ORDER BY ts DESC LIMIT 1"),
            (player_tag,),
        )
        row = cur.fetchone()
        trophies = player.get("trophies")
        wins = player.get("wins")
        losses = player.get("losses")
        bc = player.get("battleCount")
        # Only append when something changed, to keep the trend line meaningful.
        if row and row[0] == trophies and row[1] == bc:
            return False
        cur.execute(
            _q("""INSERT INTO snapshots
               (player_tag, ts, trophies, best, wins, losses, battle_count, three_crown)
               VALUES (?,?,?,?,?,?,?,?)"""),
            (player_tag, ts, trophies, player.get("bestTrophies"), wins, losses, bc,
             player.get("threeCrownWins")),
        )
        if not db.IS_POSTGRES:
            conn.commit()
        return True
    finally:
        conn.close()


SPECIAL_SLOTS = 3
import re as _re

# Some brand-new evolutions (e.g. Evo Elite Barbarians, Aug 2026) are not yet on
# Supercell's official CDN, so the API returns only a 'medium' icon. RoyaleAPI's
# asset host does have them under cards-150/<slug>-ev1.png. We use that as a
# fallback so EVO cards always show their evolution art.
_ROYALEAPI_EVO = "https://cdn.royaleapi.com/static/img/cards-150/{slug}-ev1.png"


def _card_slug(name):
    """'Elite Barbarians' -> 'elite-barbarians' (RoyaleAPI asset slug)."""
    if not name:
        return ""
    s = name.lower().replace(".", "").replace("'", "")
    s = _re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s



def _card_brief(c, idx=None):
    """Normalize a card and resolve its EQUIPPED form (EVO/HERO/plain) this battle.

    The battlelog 'cards' array is ordered by deck slot for BOTH team and
    opponent, and the slots have fixed capabilities (per the game's rules):

      slot 0 = Evolution slot : plain | EVO                (never Hero)
      slot 1 = Hero slot      : plain | Hero | Champion    (never EVO)
      slot 2 = Wild slot      : plain | EVO | Hero | Champion
      slot 3..7               : always plain

    The API never states the equipped form directly, and a card may own both an
    evolution and a hero form (heroMedium icon present). We resolve it from
    POSITION + evolutionLevel + whether it OWNS a hero form (heroMedium):

      - evolutionLevel not None  => a special form is equipped this battle
      - rarity == 'champion'     => Champion (rendered as HERO)
      - In the Wild slot, HERO iff the card owns a hero form (heroMedium icon),
        else EVO. We do NOT use evolutionMedium: some EVO cards (Elite Barbarians)
        only ship a 'medium' icon even when equipped as EVO.

    Verified against 6 confirmed decks (mine + 5 opponents), incl. Elite Barbarians
    equipped as EVO in the Wild slot with only a 'medium' icon.
    idx=None (position unknown) falls back to the same OWNS-hero-form heuristic.
    """
    icons = c.get("iconUrls", {}) or {}
    evo_lvl = c.get("evolutionLevel")
    is_champ = c.get("rarity") == "champion"
    has_hero_icon = bool(icons.get("heroMedium"))
    has_evo_icon = bool(icons.get("evolutionMedium"))
    # HERO iff the card ships a hero icon but NO evolution icon. This is the only
    # combination that reliably means "equipped as Hero":
    #   Mega Minion / Ice Golem / Knight / Valkyrie: heroMedium, no evolutionMedium -> HERO
    #   Wizard equipped as EVO: has BOTH icons -> EVO (evolution icon wins)
    #   Elite Barbarians equipped as EVO: only 'medium' icon -> EVO
    wild_is_hero = has_hero_icon and not has_evo_icon
    form = ""

    if idx is None:
        if is_champ:
            form = "hero"
        elif evo_lvl is not None:
            form = "hero" if wild_is_hero else "evo"
    elif idx == 0:                       # Evolution slot: plain | EVO
        if evo_lvl is not None:
            form = "evo"
    elif idx == 1:                       # Hero slot: plain | Hero | Champion
        if is_champ or evo_lvl is not None:
            form = "hero"
    elif idx == 2:                       # Wild slot: plain | EVO | Hero | Champion
        if is_champ:
            form = "hero"
        elif evo_lvl is not None:
            form = "hero" if wild_is_hero else "evo"
    # idx >= 3: always plain

    # If equipped as EVO but the API gave no evolution art, fall back to
    # RoyaleAPI's evolution asset so the tile isn't stuck on the plain image.
    if form == "evo" and not has_evo_icon:
        slug = _card_slug(c.get("name"))
        if slug:
            icons = dict(icons)
            icons["evolutionMedium"] = _ROYALEAPI_EVO.format(slug=slug)

    return {
        "name": c.get("name"),
        "iconUrls": icons,
        "elixir": c.get("elixirCost"),
        "rarity": c.get("rarity"),
        "evolutionLevel": evo_lvl,
        "form": form,
        "isEvo": form == "evo",
        "isHero": form == "hero",
    }


def _tower_brief(c):
    """Normalize a Tower Troop (supportCards entry)."""
    return {
        "name": c.get("name"),
        "iconUrls": c.get("iconUrls", {}) or {},
        "level": c.get("level"),
    }


def _player_brief(pl):
    """Normalize one player on a side (name/tag + resolved deck + towers).
    Used for both 1v1 and 2v2 -- a side may contain multiple players."""
    return {
        "name": pl.get("name", ""),
        "tag": pl.get("tag", ""),
        "cards": [_card_brief(c, i) for i, c in enumerate(pl.get("cards", []))],
        "towers": [_tower_brief(c) for c in pl.get("supportCards", [])],
    }


def get_history(player_tag, limit=500):
    """Return accumulated battles + snapshots + summary for a player."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            _q("SELECT id, player_tag, battle_time, mode, type, my_crowns, opp_crowns, "
               "result, opp_name, opp_tag, raw FROM battles "
               "WHERE player_tag = ? ORDER BY battle_time DESC LIMIT ?"),
            (player_tag, limit),
        )
        brows = db._rows_as_dicts(cur)
        cur.execute(
            _q("SELECT ts, trophies, wins, losses, battle_count FROM snapshots "
               "WHERE player_tag = ? ORDER BY ts ASC"),
            (player_tag,),
        )
        srows = db._rows_as_dicts(cur)
    finally:
        conn.close()

    battles = []
    from collections import Counter
    mode_counter = Counter()
    result_counter = Counter()
    ladder_points = []  # (battleTime, trophies_after) for Ladder battles only
    for r in brows:
        raw = {}
        try:
            raw = json.loads(r["raw"])
        except Exception:
            pass
        team = (raw.get("team") or [{}])[0]
        opp = (raw.get("opponent") or [{}])[0]
        battles.append({
            "battleTime": r["battle_time"],
            "mode": r["mode"],
            "type": r["type"],
            "myCrowns": r["my_crowns"],
            "oppCrowns": r["opp_crowns"],
            "result": r["result"],
            "oppName": r["opp_name"],
            "oppTag": r["opp_tag"],
            # Per-player decks. In 2v2 (TeamVsTeam) each side has 2 players, so
            # these carry both teammates; in 1v1 they have a single entry.
            "myPlayers": [_player_brief(pl) for pl in (raw.get("team") or [])],
            "oppPlayers": [_player_brief(pl) for pl in (raw.get("opponent") or [])],
            # Back-compat single-deck fields (first player of each side).
            "myCards": [_card_brief(c, i) for i, c in enumerate(team.get("cards", []))],
            "oppCards": [_card_brief(c, i) for i, c in enumerate(opp.get("cards", []))],
            "myTowers": [_tower_brief(c) for c in team.get("supportCards", [])],
            "oppTowers": [_tower_brief(c) for c in opp.get("supportCards", [])],
        })
        mode_counter[r["mode"]] += 1
        result_counter[r["result"]] += 1

        # Ladder trophy trend: only real Ladder PvP battles carry startingTrophies
        # + trophyChange. Everything else (Showdown, friendly, boat) is excluded.
        if r["type"] == "PvP" and r["mode"] == "Ladder":
            st = team.get("startingTrophies")
            ch = team.get("trophyChange")
            if st is not None and ch is not None:
                ladder_points.append({
                    "battleTime": r["battle_time"],
                    "before": st,
                    "change": ch,
                    "after": st + ch,
                })

    # ladder_points came from DESC rows -> sort ascending by time for the chart.
    ladder_points.sort(key=lambda p: p["battleTime"])

    total = result_counter["win"] + result_counter["loss"]
    return {
        "playerTag": player_tag,
        "totalArchived": len(brows),
        "wins": result_counter["win"],
        "losses": result_counter["loss"],
        "draws": result_counter["draw"],
        "winRate": round(result_counter["win"] / total * 100, 1) if total else 0,
        "modes": mode_counter.most_common(),
        "battles": battles,
        "snapshots": srows,
        "ladderTrend": ladder_points,
    }


if __name__ == "__main__":
    init_db()
    print(f"DB ready at {DB_PATH}")
