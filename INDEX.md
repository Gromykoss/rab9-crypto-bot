# rab9 — Agent Map

## Start Here
- **AGENTS.md** — voice, boundaries, rules (read this first)
- **INDEX.md** — this file (filesystem map)

## Active Files (what matters now)
01. AGENTS.md — project rules, architecture, commands
02. rab9_bot.py — main bot entry
03. handlers.py — message handlers
04. arkham.py — Arkham enrichment
05. scanner.py, scoring.py — signal scanning/scoring
06. alerts.py, alert_state.json — alert system
07. wallet_watch.py, watchlist.py — watchlist management
08. burnie_sentiment_tracker.py — BURNIE tracker (cron only via script)
09. loop_verifier.py, loop_stops.py — verification loop
10. data/ — data directory (trades DB etc.)
11. .env, config.py — configuration

## Reference (look up when needed)
- docs/ — documentation
- *.save, *.save.* — backup versions of handlers
- requirements.txt
- venv/

## Ignore Unless Asked
- __pycache__/
- .git/
- All .save* backup files
- Old arkham backups
- wallet_watch_before_* files