# Clash Royale Tools

Pull Clash Royale player data from the official Supercell API and view it in a
local web app (or as a CLI report): profile, deck, battle log + opponent meta,
upcoming chests.

## The local app (recommended)

Zero dependencies (Python 3 standard library only). Just launch and it opens in
your browser:

```bash
./start.sh                 # macOS/Linux, opens http://127.0.0.1:8787
# or double-click start.command in Finder (macOS)
# or: python3 app.py [port]
```

Type any player tag in the search bar and hit 查询 / 刷新 to fetch live data.

## Hourly auto-fetch (background archiving)

To keep accumulating history even when the dashboard isn't open, register the
hourly LaunchAgent (macOS). Run this once in your OWN Terminal:

```bash
./install_autofetch.sh
```

This runs `auto_fetch.py` every hour, archiving battles + trophy snapshots into
`archive.db`. Edit the `DEFAULT_TAGS` list in `auto_fetch.py` to track more
accounts. Manage it with:

```bash
tail -f auto_fetch.log                                          # watch runs
launchctl bootout gui/$(id -u)/com.yuzhe.clashroyale.autofetch  # stop/remove
```

Note: the token is IP-locked, so auto-fetch only works from a machine whose
outbound IP is on the token's allowed list.

### History archive (beats the 25-battle API cap)

The official API only returns the ~25 most recent battles. The app stores every
fetch locally in `archive.db` (SQLite), deduplicated, so history accumulates the
more you use it. The "历史存档" section shows the full accumulated battle list
(with a mode filter) and a trophy trend chart built from profile snapshots.

## Setup

1. Get an API token at https://developer.clashroyale.com
   - Create a key and add your machine's outbound public IP(s) to
     "Allowed IP Addresses" (the token is IP-locked).
   - **This machine uses two outbound IPs** — add BOTH:
     - `123.116.51.111` (system/curl)
     - `23.248.176.111` (Python, i.e. the app)
2. Copy the token into `.env`:
   ```bash
   cp .env.example .env
   # then edit .env and paste your token
   ```

## CLI usage

```bash
python3 fetch.py 20GQJGRJ0J            # single player
python3 fetch.py 20GQJGRJ0J 8LQ2V0VC   # multiple players
python3 fetch.py "#20GQJGRJ0J"         # '#' is fine too
```

## Files

- `app.py` — local web server + API proxy
- `index.html` — the dashboard UI (single page)
- `store.py` — local SQLite archive (battles + snapshots)
- `start.sh` / `start.command` — one-click launchers
- `fetch.py` — CLI fetcher/reporter
- `.env` — your token (git-ignored, never commit)
- `.env.example` — template
- `archive.db` — local history database (git-ignored, auto-created)
- `AGENTS.md` — workflow instructions for AI agents

## Troubleshooting

- **HTTP 403 (`accessDenied.invalidIp`)**: your current outbound IP isn't on the
  token's allowed list. The error shows the exact IP — add it at
  developer.clashroyale.com (create a new key with both IPs) and update `.env`.
- **Missing authorization / 401**: token missing/wrong in `.env`.
