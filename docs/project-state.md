# Project State

## 2026-05-23

- Disabled the legacy token watchlist alert loop by default with `LEGACY_WATCHLIST_ALERTS_ENABLED=false`.
- RAB9 still starts normally, stays in the configured Telegram group, and keeps its message/command handlers active.
- The old watchlist alert builder now returns no active alert text while disabled, so RAB9 does not post legacy `Positive Alert` messages into Песочница.
- To re-enable the legacy flow later, set `LEGACY_WATCHLIST_ALERTS_ENABLED=true` in the environment and restart the bot.
- MSF messages in Песочница remain readable by the existing text handler; no Алихан, Evolution API, WhatsApp, or Arkham active-path changes were made.
- Added MSF signal ingestion for one-message `RAB9_SIGNAL solana <TOKEN_ADDRESS>` posts in Песочница.
- MSF signals now acknowledge with `🔎 RAB9 начал анализ MSF-сигнала...` and automatically run pairresolve analysis; plain Solana CA messages still show the existing buttons.
- The MSF ingestion path uses existing pair-source analysis only and does not call Arkham or re-enable legacy watchlist alerts.
