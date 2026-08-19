# AGENTS.md — Clash Royale data workflow

This project fetches Clash Royale player data via the **official Supercell API**
and prints a human-readable report. When the user asks you to "pull my Clash
Royale data" / "拉一下我的皇室战争数据" / "查这个玩家" etc., follow this workflow.

## Two ways to use this project

### 1. Local web app (recommended for the user)

A zero-dependency Python web app. The user just double-clicks `start.command`
(or runs `./start.sh`), the browser opens automatically, and data is fetched
and displayed (profile, deck, battle log + meta chart, chests). There is a
"刷新" (refresh) button to re-fetch live.

```bash
cd ~/Projects/clash-royale-tools
./start.sh            # or: python3 app.py [port]
# opens http://127.0.0.1:8787
```

### 2. CLI report

```bash
cd ~/Projects/clash-royale-tools
python3 fetch.py 20GQJGRJ0J
python3 fetch.py 20GQJGRJ0J 8LQ2V0VC   # multiple players
```

The tag may be given with or without the leading `#`; both scripts normalize
and URL-encode it (`#` -> `%23`). Tags are case-insensitive.

## Default player

The user's own tag is **`#20GQJGRJ0J`** (name: Sȼøɍȼħfɍøsŧ#).
If the user says "pull my data" without giving a tag, use this one.

## Token & auth (IMPORTANT — two outbound IPs!)

- The API token lives in **`.env`** as `CR_API_TOKEN=...` (git-ignored, never
  commit it). Both `app.py` and `fetch.py` auto-load it.
- The token is **IP-locked** to whatever IP the request goes out from.
- **This machine has TWO different outbound IPs depending on the tool:**
  - `curl` / system network -> **`123.116.51.111`**
  - **Python (`app.py` / `fetch.py`) -> `23.248.176.111`**  ← the one the app uses
- So the token's key at developer.clashroyale.com should whitelist **BOTH**
  IPs: `123.116.51.111` and `23.248.176.111`.
- **If you get `HTTP 403` (`accessDenied.invalidIp`)**: the error body includes
  the exact current IP, e.g. `does not allow access from IP <x.x.x.x>`. Read it,
  then tell the user to add that IP to the key's allowed list (keys can't be
  edited — they must Create New Key with both IPs) and paste the new token so
  you can update `.env`.
  - Check Python's current outbound IP:
    `python3 -c "import urllib.request,ssl,certifi; print(urllib.request.urlopen('https://ipinfo.io/ip',context=ssl.create_default_context(cafile=certifi.where())).read().decode())"`
- **If you get `Missing authorization` / 401**: token missing or malformed in `.env`.
- Note: python.org's macOS Python lacks system CA certs; both scripts already
  work around this using `certifi`.

## Local history archive

The official API only returns the ~25 most recent battles (server-side rolling
cache; older battles are not stored anywhere). To keep longer history, the app
**accumulates data locally** in `archive.db` (SQLite):
- Every `/api/player` fetch upserts battles deduplicated by
  `playerTag|battleTime|mode`, so repeated fetches never double-count.
- Each fetch also records a profile snapshot (trophies / wins / losses /
  battleCount) — only when something changed — powering the trophy trend chart.
- `GET /api/history?tag=...` returns the accumulated battles + snapshots +
  mode breakdown. The frontend shows an "历史存档" section with a mode filter
  and a trophy trend sparkline.
- The more often the app runs/refreshes, the fuller the history gets.
- `store.py` owns all DB logic; `archive.db` is git-ignored.

Note on game modes: `Showdown_*` and Trophy Road count as "climbing trophies"
even though they are not classic Ladder / Path of Legends ranked matches. If a
user says "I'm climbing but see no ranked games", check the `type`/`gameMode`
of their battles — most may be `Showdown_Friendly`, not `Ladder`.

## API reference (in case you need endpoints directly)

Base URL: `https://api.clashroyale.com/v1`
Auth header: `Authorization: Bearer <token>`

| Data | Endpoint |
|---|---|
| Player profile | `players/{tag}` |
| Battle log | `players/{tag}/battlelog` |
| Upcoming chests | `players/{tag}/upcomingchests` |
| Clan | `clans/{clanTag}` |
| Global player ranking | `locations/global/pathoflegend/players` |

`{tag}` must be URL-encoded (`#20GQJGRJ0J` -> `%2320GQJGRJ0J`).

Raw curl example (for debugging):

```bash
source .env
curl -s -H "Authorization: Bearer $CR_API_TOKEN" \
  "https://api.clashroyale.com/v1/players/%2320GQJGRJ0J" | python3 -m json.tool
```

## After fetching: analysis

The user is an experienced player (12k+ trophies). When they want analysis, go
beyond raw numbers:
- Evaluate the current deck vs. the current meta (as of Aug 2026 the ladder is
  dominated by evolution + single-hero/single-champion decks; hero abilities
  became single-use per deployment).
- Comment on deck archetype, win-condition, cycle/elixir, strengths & gaps
  (e.g. tower-troop depth, evolution slot usage).
- If asked, analyze specific losses from the battle log.

## Notes

- Respond to the user in Chinese (中文).
- Do not commit `.env`. Do not print the full token back to the user.
