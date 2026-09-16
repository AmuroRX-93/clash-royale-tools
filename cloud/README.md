# Cloud collection

GitHub Actions runs the collector hourly at minute 17 and on manual dispatch. It reads the current subscriptions from the existing Neon database, archives raw battles with the same deduplication key as the local app, and records each run in collection_runs. No player data or credentials are committed.

Required encrypted repository secrets: CR_API_TOKEN and DATABASE_URL. API requests use the existing RoyaleAPI proxy, so the token must allow its egress IP.

The original local app remains unchanged. Schedule runs may be delayed. GitHub disables scheduled workflows in public repositories after 60 days of repository inactivity; re-enable the workflow if this occurs. The website warns when no collection has started for three hours.
