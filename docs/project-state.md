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
- Replaced the service entrypoint with neutral `rab9_bot.py`; removed the old branded startup file and updated the systemd example to launch `rab9_bot.py`.
- Added a minimal shared-secret HTTP endpoint at `POST /msf-signal` for n8n-msf direct triggers. It validates Solana payloads, runs existing pairresolve analysis, and posts the result to Песочница through the RAB9 bot without using Arkham or legacy alerts.
- Relaxed `/msf-signal` address validation for MSF/Dexscreener lowercase Solana token/pair addresses such as pump/pair ids while keeping `chain == solana` and shared-secret checks.
- Added `/testsignal ADDRESS` for manual MSF-style pairresolve testing inside Песочница, using the same relaxed Solana address validation and pairresolve pipeline as `/msf-signal`.
- Added first-stage MSF deep analysis for `/testsignal`, Telegram `RAB9_SIGNAL`, and `POST /msf-signal`: pairresolve, best-pair extraction, normal-mode pairmakers, and a compact no-PnL/no-advice analyst summary.
- Reworked the MSF/testsignal analysis output into a single compact structured report: token/pair metadata, normal-mode maker scan stats, behavior buckets, and top 5 makers only, without appending full diagnostics.
- Added a deterministic analyst verdict section to compact MSF/testsignal reports using only first-pass liquidity, volume, maker count, raw trades, behavior buckets, and maker concentration.
- Improved compact MSF analyst verdict wording with factual why bullets, human-readable meaning, and risk bullets while preserving the deterministic state rules.

## 2026-05-24

- Added production MSF spiral analysis for `/testsignal`, Telegram `RAB9_SIGNAL`, and `POST /msf-signal`: normal scan first, automatic deep scan only for unclear/noisy verdicts, no automatic deep50.
- Added MSF-only dust filtering for verdict construction: known USD trades below $10 are ignored, missing-USD trades are kept, and `/pairmakers` output remains unchanged.
- Added compact spiral trace plus raw/meaningful/dust/unknown trade counters to the MSF compact report.
- Added Market Cap / FDV to compact MSF reports, preferring Dexscreener marketCap and falling back to fdv when marketCap is unavailable.
- Extended MSF spiral analysis to normal -> deep -> deep50, using deep50 only when the deep verdict remains unclear and extending the HTTP processing timeout to 180 seconds.
