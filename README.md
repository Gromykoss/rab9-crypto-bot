# RAB9 Crypto Intel Bot

RAB9 is a Telegram crypto-intel bot for a locked Telegram group. It scans fresh Dexscreener profiles, scores token pairs, builds Grok/xAI-assisted token analysis, keeps token and wallet watchlists, and sends alert messages when watched token metrics change enough to matter.

The bot runs with Telegram polling from `rab9_bot.py`. Runtime state is stored as JSON files in the project directory.

## What The Bot Does

- Scans Dexscreener latest profiles in four modes: micro, degen, normal, and hot.
- Scores token pairs by market cap, liquidity, volume, buy/sell pressure, age, and risk flags.
- Builds token intel reports with Dexscreener data and a Grok decision layer.
- Tracks a token watchlist and compares current metrics against first snapshots.
- Tracks a wallet watchlist using Arkham address intelligence.
- Checks Arkham API status, token intel, and wallet/address intel.
- Runs a background alert loop after startup and can also check alerts manually.
- Rejects commands outside the configured `TELEGRAM_GROUP_ID`.

## Commands

Core:

- `/start` - show bot overview and basic command hints.
- `/menu` - show inline action menu.
- `/status` - check Telegram config, API keys, Dexscreener, watchlist count, and time.

Scanners:

- `/micro` - scan low market-cap tokens, roughly `$20K-$100K`.
- `/degen` - scan degen range, roughly `$100K-$2M`.
- `/scan` - normal scan, roughly `$2M-$15M`.
- `/hot` - scan for short-term volume and price impulse.

Token intel:

- `/token solana ADDRESS` - analyze a token pair through Dexscreener metrics and Grok.
- Sending a Solana or EVM address as plain text can trigger token-analysis flow through handlers.
- `/grok TEXT` - ask Grok for a short crypto-intel answer.
- `/morning` - generate a morning crypto-intel checklist.
- `/evening` - generate an evening crypto-intel checklist.

Token watchlist:

- `/watch solana ADDRESS note` - add or update a token watch item.
- `/watchlist` - show watched tokens and first snapshots.
- `/checkwatch` - compare watched tokens against current Dexscreener data.
- `/refreshwatch` - refresh watchlist snapshots.
- `/unwatch ADDRESS` - remove a token from watchlist.
- `/alertsnow` - run the alert check immediately.

Arkham and wallets:

- `/arkhamstatus` - check Arkham API availability and usage headers.
- `/arktoken ADDRESS` - check Arkham token intel on Solana by default.
- `/arktoken solana ADDRESS` - check Arkham token intel for an explicit chain.
- `/wallet ADDRESS` - check Arkham wallet/address intelligence.
- `/walletflow ADDRESS 24h` - manually check Arkham historical USD flow for a wallet/address. Period is optional; default is `24h`.
- `/tokenflow solana ADDRESS 7d` - manually check Arkham top token flow for a token contract, enrich the first 10 flow addresses with Arkham wallet intelligence, and classify them as infrastructure, known entities, unknown candidates, or programs. Jupiter/DEX/router/exchange-style infrastructure is not treated as smart-money wallets. Period is optional; default is `24h`. Enrichment makes up to 10 additional Arkham address lookups per `/tokenflow` call, so this command stays manual.
- `/wallettx WALLET TOKEN 25` - manually inspect Arkham `/transfers` diagnostics for one wallet/token pair.
- `/wallettrade WALLET TOKEN` - manually summarize wallet/token transfer behavior and potential IN/OUT cycles from Arkham `/transfers`, then use Birdeye close prices near first IN/OUT timestamps to estimate approximate cycle price movement for up to the latest 5 completed cycles. No amount-based returns, entry quality, or exit quality are calculated.
- `/pricesource TOKEN 2026-05-07T18:45:29Z` - manually test Birdeye Solana historical price/OHLCV near an ISO timestamp. Requires `BIRDEYE_API_KEY`; no amount-based return is calculated.
- `/walletswaps WALLET`, `/walletswaps WALLET TOKEN`, `/walletswaps WALLET TOKEN 50 deep`, or `/walletswaps WALLET TOKEN 50 deep10` - manually inspect parsed Solana swap activities. Normal mode uses Solscan Pro account defi activities when `SOLSCAN_API_KEY` is available, with Birdeye trades V3 fallback. Deep modes scan Birdeye pages for older wallet/token swaps. Token-filtered reports include an approximate sell-window price check when token -> SOL events are found and a short swap behavior classification such as `Distribution Pattern`, `Accumulation Pattern`, or `Round-trip Pattern`.
- `/makertrades PAIR MAKER 50 deep10` - manually inspect Birdeye pair trades through `/defi/txs/pair` with `address=PAIR`, then filter maker-like fields client-side to compare against Dexscreener maker-table activity. Normal mode checks the latest page; `deep` scans up to 5 pages and `deep10` up to 10 pages with safe delays. No PnL or trading advice is provided.
- `/makerfind PAIR MAKER deep50` or `/makerfind PAIR MAKER around 2026-05-12T18:24:15Z` - manually search deeper through Birdeye pair trades for one maker. `deep` scans up to 20 pages; `deep50` scans up to 50 pages. `around` is strict by default and uses Birdeye pair seek-by-time with a +/-2h window. Use `/makerfind PAIR MAKER around TIMESTAMP fallback` only when you explicitly want latest-window fallback labeled as non-anchored. Compact search report only.
- `/pairmakers PAIR deep50` or `/pairmakers PAIR deep50 full` - manually discover top maker wallets in Birdeye pair trades. `deep` scans up to 20 pages and `deep50` up to 50 pages with safe delays, then ranks makers by trade count. `full` adds full copy-ready wallet addresses for the visible top 20 makers. Discovery tool only; no PnL or trading advice.
- `/walletprofile WALLET PAIR:TOKEN PAIR:TOKEN` or `/walletprofile WALLET PAIR:TOKEN:TIMESTAMP` - manually profile one wallet across up to 5 pair/token cases using maker-find scans plus Birdeye price movement during activity windows. Timestamped cases use strict anchored around scans and do not mix in latest-window trades. No PnL or trading advice is provided.
- `/pairresolve ADDRESS` - manually resolve token/pair addresses through Dexscreener and Birdeye to find the pool/market address candidate to use with `/makertrades`.
- `/watchwallet ADDRESS note` - add or update a wallet watch item.
- `/walletlist` - show wallet watchlist.
- `/checkwallets` - refresh wallet snapshots through Arkham.
- `/unwatchwallet ADDRESS_OR_NUMBER` - remove a wallet by address or list number.

## Module Structure

- `rab9_bot.py` - application entry point, logging setup, Telegram polling, handler registration.
- `config.py` - `.env` loading, API keys, base URLs, runtime JSON paths, scan thresholds.
- `handlers.py` - Telegram command handlers, callback handlers, group lock, long-message splitting.
- `alerts.py` - background alert loop, alert classification, cooldowns, alert state persistence.
- `dex.py` - Dexscreener HTTP client helpers and best-pair selection.
- `scanner.py` - `/micro`, `/degen`, `/scan`, and `/hot` scan builders.
- `scoring.py` - score/risk calculations for token pair metrics.
- `token_intel.py` - token intel report and Grok/xAI request logic.
- `watchlist.py` - token watchlist load/save, snapshots, comparisons, formatting.
- `wallet_watch.py` - wallet watchlist load/save, Arkham wallet snapshots, formatting.
- `arkham.py` - Arkham API helpers for status, token intel, wallet/address intel, and manual flow checks.
- `price_sources.py` - manual Birdeye historical price/OHLCV diagnostics for future wallet-trade research.
- `swap_sources.py` - manual parsed swap diagnostics using Solscan Pro with Birdeye fallback.
- `maker_sources.py` - manual Birdeye pair+maker trade diagnostics.
- `pair_sources.py` - manual Dexscreener/Birdeye pair and pool address resolver.
- `wallet_profile.py` - manual wallet behavior profiling across multiple pair/token cases.
- `keyboards.py` - Telegram reply and inline keyboards.
- `utils.py` - formatting, parsing, time, and message chunk utilities.
- `requirements.txt` - Python package dependencies.
- `.env.example` - template for required environment variables.

## Run Locally

Use Python 3.12 or a compatible modern Python 3 version.

```powershell
cd C:\path\to\rab9-crypto-bot
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` locally and set:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_GROUP_ID`
- `XAI_API_KEY`
- `ARKHAM_API_KEY`
- optional `BIRDEYE_API_KEY` for `/pricesource`
- optional `SOLSCAN_API_KEY` for `/walletswaps`
- optional `DEXSCREENER_BASE_URL`
- optional `XAI_BASE_URL`
- `RAB9_HTTP_SECRET` for the local MSF HTTP endpoint
- optional `RAB9_HTTP_HOST`, default `127.0.0.1`
- optional `RAB9_HTTP_PORT`, default `8089`
- optional `ALERT_INTERVAL_SECONDS`
- optional `ALERT_COOLDOWN_SECONDS`

Start the bot:

```powershell
python rab9_bot.py
```

The bot uses long polling. Keep the process running while testing.

## MSF HTTP Signal Endpoint

When `RAB9_HTTP_SECRET` is set, n8n-msf can trigger pairresolve analysis directly:

```bash
curl -X POST http://127.0.0.1:8089/msf-signal \
  -H "Content-Type: application/json" \
  -H "X-RAB9-SECRET: $RAB9_HTTP_SECRET" \
  -d '{"source":"msf","chain":"solana","address":"TOKEN_ADDRESS","text":"MSF signal text"}'
```

The endpoint only accepts `chain: solana` and Solana base58 addresses of 32-44 chars. Valid requests post the pairresolve report into the configured Telegram group.

## Deploy To VPS

Example Ubuntu deployment:

```bash
sudo apt update
sudo apt install -y python3 python3-venv git
git clone https://github.com/Gromykoss/rab9-crypto-bot.git
cd rab9-crypto-bot
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env
```

Create `/etc/systemd/system/rab9-crypto.service`:

```ini
[Unit]
Description=RAB9 Crypto Intel Bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/rab9-crypto-bot
ExecStart=/opt/rab9-crypto-bot/venv/bin/python /opt/rab9-crypto-bot/rab9_bot.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Adjust paths if the repo is not in `/opt/rab9-crypto-bot`, then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable rab9-crypto
sudo systemctl start rab9-crypto
sudo systemctl status rab9-crypto
```

View logs:

```bash
journalctl -u rab9-crypto -f
```

## Do Not Commit

Keep these local-only:

- `.env`
- `venv/`
- `__pycache__/`
- `*.pyc`
- `*.log`
- `*.save`
- `watchlist.json`
- `alert_state.json`
- `wallet_watchlist.json`
- backup files matching `*_backup_*.py` or `*_before_*.py`

## Troubleshooting

- Bot exits with `Missing required env variable: TELEGRAM_BOT_TOKEN`: create `.env` in the project folder and set the bot token.
- Commands reply with group-lock error: set `TELEGRAM_GROUP_ID` to the exact Telegram group chat id.
- `/status` shows Dexscreener error: check VPS networking and Dexscreener availability.
- Grok commands say API key is missing: set `XAI_API_KEY` and restart the bot.
- Arkham commands say API key is missing or return errors: set `ARKHAM_API_KEY`, check quota, then retry `/arkhamstatus`.
- `/pricesource` says `BIRDEYE_API_KEY missing`: set `BIRDEYE_API_KEY` and restart the bot.
- `/walletswaps` says `SOLSCAN_API_KEY missing`: add `SOLSCAN_API_KEY` for Solscan Pro, or set `BIRDEYE_API_KEY` to try the fallback.
- Watchlist or alert data is missing after moving the project: copy `watchlist.json`, `alert_state.json`, and `wallet_watchlist.json` into the project directory.
- Alerts do not appear immediately after startup: the background alert loop waits briefly, then runs every `ALERT_INTERVAL_SECONDS`; use `/alertsnow` for a manual check.
- `ModuleNotFoundError`: activate the venv and run `pip install -r requirements.txt`.
