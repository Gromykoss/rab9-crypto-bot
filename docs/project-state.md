# RAB9 Alpha Engine — Project State

Engineering snapshot of the repository as of the current codebase. Intended for future AI agents and maintainers. Production entrypoint: `rab9_arkham.py` (not `rab9_bot.py`, which is legacy and gitignored).

---

## Runtime architecture

Flat Python modules at repo root (no package). Telegram bot uses `python-telegram-bot` long polling.

```
rab9_arkham.py
  → config.py (.env at import)
  → handlers.register_handlers()
  → alerts.post_init() → background alert_loop
```

| Module | Role |
|--------|------|
| `handlers.py` | Commands, callbacks, group lock, `asyncio.to_thread` for blocking work, message chunking |
| `alerts.py` | Hourly watchlist diff vs Dexscreener; sends to `TELEGRAM_GROUP_ID` |
| `dex.py` | Dexscreener HTTP (`latest` profiles, `token-pairs`) |
| `scanner.py` + `scoring.py` | Scan pipelines and pair scoring |
| `token_intel.py` | `/token` + Grok/xAI |
| `watchlist.py` | Token watchlist JSON |
| `wallet_watch.py` | Wallet watchlist JSON + Arkham snapshots |
| `arkham.py` | Arkham client, transfers, flows, intel formatters |
| `swap_sources.py` | Solscan defi activities + Birdeye v3 txs fallback |
| `maker_sources.py` | Birdeye pair trades, maker find, pair makers |
| `pair_sources.py` | Dex + Birdeye address resolution |
| `price_sources.py` | Birdeye OHLCV / price near timestamp |
| `wallet_profile.py` | Multi-case wallet profiling |
| `keyboards.py` | Reply / inline keyboards |
| `utils.py` | Formatting, `split_text` (~3800 chars) |

**Persistence (JSON, project directory):** `watchlist.json`, `alert_state.json`, `wallet_watchlist.json`.

**Security:** Commands allowed only when `str(chat_id) == str(TELEGRAM_GROUP_ID)`. API keys from `.env` (see `.env.example`).

**Concurrency:** Heavy work runs in `asyncio.to_thread`; HTTP is synchronous `requests`. No shared rate-limit budget across commands.

---

## Active Telegram commands

All registered in `handlers.register_handlers()`. Plain-text Solana/EVM addresses open inline keyboards (`token_chain_keyboard`).

| Group | Commands |
|-------|----------|
| Core | `/start`, `/menu`, `/status` |
| Scanners | `/micro`, `/degen`, `/scan`, `/hot` |
| Token intel | `/token`, `/grok`, `/morning`, `/evening` |
| Token watch | `/watch`, `/watchlist`, `/checkwatch`, `/refreshwatch`, `/unwatch`, `/alertsnow` |
| Arkham | `/arkhamstatus`, `/arktoken`, `/wallet`, `/walletflow`, `/tokenflow` |
| Wallet ↔ token (transfers) | `/wallettx`, `/wallettrade` |
| Solana swaps | `/walletswaps` (optional `TOKEN`, `limit`, `deep`, `deep10`) |
| Prices | `/pricesource` |
| Pair / maker (Birdeye) | `/makertrades`, `/makerfind`, `/pairmakers`, `/pairresolve` |
| Wallet profile | `/walletprofile` |
| Wallet watch | `/watchwallet`, `/walletlist`, `/checkwallets`, `/unwatchwallet` |

**Not implemented:** `/walletlinks`, `/investigate`, Arkham `/swaps` probe command, background deep scans.

---

## APIs and integrations

| Service | Config | Used for |
|---------|--------|----------|
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_GROUP_ID` | Bot transport, group lock |
| Dexscreener | `DEXSCREENER_BASE_URL` (default `https://api.dexscreener.com`) | Scans, `/token`, watchlist snapshots, alerts, `pair_sources` |
| xAI Grok | `XAI_API_KEY`, `XAI_BASE_URL` | `/token`, `/grok`, morning/evening |
| Arkham | `ARKHAM_API_KEY`, base `https://api.arkm.com` | Intel, flows, `/transfers`, usage headers |
| Birdeye | `BIRDEYE_API_KEY`, base `https://public-api.birdeye.so` | Pair txs, v3 wallet txs, OHLCV |
| Solscan Pro | `SOLSCAN_API_KEY`, base `https://pro-api.solscan.io/v2.0` | Primary `/walletswaps` path |

### Arkham endpoints in code

| Path | Commands / use |
|------|----------------|
| `/chains` | Status |
| `/intelligence/token/{chain}/{address}` | `/arktoken` |
| `/intelligence/address/{address}/all` | `/wallet`, `/tokenflow` enrichment (up to 10), wallet watch |
| `/flow/address/{address}?timeLast=` | `/walletflow` |
| `/token/top_flow/{chain}/{address}?timeLast=` | `/tokenflow` |
| `/transfers?base=&tokens=&chains=&flow=all&...` | `/wallettx`, `/wallettrade` |

Documented in research but **not wired:** `/swaps`, `/transfers/tx/{hash}`, `/tx/{hash}`.

### Birdeye endpoints in code

| Path | Module | Use |
|------|--------|-----|
| `/defi/txs/pair` | `maker_sources` | Pair trades, maker filter client-side |
| `/defi/txs/pair/seek_by_time` | `maker_sources` | `/makerfind around` |
| `/defi/v3/txs` | `swap_sources` | Wallet swaps fallback / deep |
| `/defi/v2/markets`, `/defi/v3/search`, `/defi/v3/pair/overview/single` | `pair_sources` | `/pairresolve` |
| OHLCV / price helpers | `price_sources` | `/pricesource`, `/wallettrade` cycle prices |

### Solscan in code

- `GET /account/defi/activities` — `/walletswaps` when key present.

No Solscan SPL **account transfer** endpoint integrated (listed as needed in `docs/WALLET_ALPHA_PLAN.md`).

---

## Maker / pair architecture shift

**Problem (documented in `docs/ALPHA_ENGINE_ROADMAP.md`, `docs/MAKER_TRADES_SOURCE_RESEARCH.md`):** Dexscreener UI is **pair + maker** oriented. RAB9 wallet diagnostics were **wallet + token** oriented (`/walletswaps`, Arkham `/transfers`). Same wallet on a token can show many maker rows on Dexscreener but few events in wallet-level or transfer feeds (routing, pair address vs mint, aggregators).

**Response in codebase:** Pair-centric layer on Birdeye:

| Command | Axis | Source |
|---------|------|--------|
| `/makertrades PAIR MAKER [limit] [deep\|deep10]` | pair + maker | Birdeye `/defi/txs/pair` |
| `/makerfind PAIR MAKER [deep\|deep50\|around TIMESTAMP [fallback]]` | pair + maker, deep search | Birdeye pair + seek_by_time |
| `/pairmakers PAIR [deep\|deep50] [full]` | pair → ranked makers | Birdeye pair pages |
| `/pairresolve ADDRESS` | token/pair → pool candidate | Dexscreener + Birdeye |
| `/walletprofile WALLET PAIR:TOKEN[:TIMESTAMP]...` | wallet across pair cases | `makerfind` + Birdeye prices |

**Still wallet-centric:** `/walletswaps`, `/wallettx`, `/wallettrade`, `/tokenflow` (token-wide top addresses).

**Dexscreener:** pair discovery and metrics; public API does not expose UI maker table (per research docs).

---

## Wallet profiling logic (`wallet_profile.py`)

Command: `/walletprofile WALLET` + up to **5** cases `PAIR:TOKEN` or `PAIR:TOKEN:ISO_TIMESTAMP`.

Per case:

1. **With timestamp:** `get_birdeye_maker_find(pair, wallet, mode="around", anchor_time)` — strict anchored scan (no fallback; `allow_fallback` never passed).
2. **Without timestamp:** `get_birdeye_maker_find(..., mode="deep50")` — latest-window pair scan (up to 50 pages, 2500 raw cap in `maker_sources`).
3. `summarize_maker_trades` → buy/sell counts, net direction, first/last time.
4. `get_birdeye_price_near(token, first_seen)` and same for `last_seen` (0.3s delay between cases and price calls).
5. Price movement % = `(last - first) / first * 100` when both prices exist.

**Aggregate role** (`classify_wallet_role`), requires **≥2 active cases** (matched trades > 0):

| Condition | Role |
|-----------|------|
| `active_cases < 2` | Weak / Needs More Data |
| `sell_heavy_cases >= 2` | Repeating Distribution Wallet |
| `buy_heavy_cases >= 2` and no sell-heavy | Repeating Accumulation Wallet |
| `two_sided_cases >= 2` | Repeating Two-sided Active Maker |
| else | Mixed Active Wallet |

`net_direction` per case: buy-heavy / sell-heavy / mixed from maker trade sides. No PnL, no auto trading.

---

## `/makerfind around TIMESTAMP` behavior

Implemented in `maker_sources.get_birdeye_maker_find` + `scan_birdeye_maker_find`.

**Parse:** ISO timestamp (`Z` supported); invalid → `anchored_unavailable`, no HTTP.

**Window:** `anchor ± 2h` (`MAKER_FIND_AROUND_WINDOW_SECONDS = 7200`).

**API:** `GET /defi/txs/pair/seek_by_time` with `before_time = anchor_unix + 2h`, `limit=50`, `offset = page_index * 50`, `tx_type=swap`. No `sort_type` on time path.

**Client filter:** keep rows with `anchor - 2h <= trade_time <= anchor + 2h`; skip rows with no timestamp; if `trade_time < lower_bound` set `stop_after_page` (assumes newest-first pages).

**Limits:** max **20** pages, **1000** raw pair rows, early stop after **50** matched maker trades, **1.2s** sleep between pages (`DEEP_DELAY_SECONDS`).

**Maker match:** recursive key scan (`owner`, `wallet`, `maker`, `trader`, etc.) vs requested maker address.

**Strict default** (`/makerfind ... around TIMESTAMP` without `fallback`):

- **429:** stop; message that rate limit blocked anchored results; **no** latest-window fallback.
- **422:** stop; time query rejected; no fallback.
- **Empty:** `anchored_unavailable`; “Latest-window fallback skipped for strict anchored scan.”

**Explicit fallback** (`... around TIMESTAMP fallback`): second scan via `/defi/txs/pair` `sort_type=desc` without time bounds; report warns results are latest-window.

**No HTTP retry** on failed pages.

---

## Roadmap (`docs/ALPHA_ENGINE_ROADMAP.md` and related)

**Mission:** correlate wallet/maker behavior, price action, and repeatability — manual diagnostics only.

**Already shipped (beyond original roadmap “future” list):** `/makertrades`, `/makerfind`, `/pairmakers`, `/pairresolve`, `/walletprofile` (case-based).

**Still planned / not in code:**

| Item | Source doc |
|------|------------|
| `/investigate TOKEN` or `/investigate PAIR` | `ALPHA_ENGINE_ROADMAP.md` |
| Historical pattern engine at wallet scale (roadmap `/walletprofile WALLET` multi-token) | Roadmap §7 — differs from current PAIR:TOKEN case command |
| `/wallettrade` v2 with reliable amounts, entry/exit quality | `WALLET_ALPHA_PLAN.md`, `PRICE_SOURCE_RESEARCH.md` |
| Arkham `/swaps` diagnostic | `SWAP_SOURCE_RESEARCH.md` |
| Bitquery or validated pair+maker source if Birdeye insufficient | `MAKER_TRADES_SOURCE_RESEARCH.md` |
| Transfer/counterparty link command (e.g. `/walletlinks`) | gap analysis; not in repo |

**Guardrails (docs):** no auto trading, no buy/sell advice, no background deep scans, cap pages/delays, no exact PnL without reliable amounts, filter infrastructure before “smart wallet” labels.

**Research docs:** `MAKER_TRADES_SOURCE_RESEARCH.md`, `SWAP_SOURCE_RESEARCH.md`, `PRICE_SOURCE_RESEARCH.md`, `WALLET_ALPHA_PLAN.md`, `FIELD_TESTING.md`.

---

## Known limitations and bottlenecks

| Area | Limitation |
|------|------------|
| Arkham `/transfers` | `offset` fixed at `"0"`; max 50 events per call; often missing amount/usdValue; may miss swap-shaped activity vs Solscan |
| Arkham `/transfers` vs swaps | Aggregator/pool routing may not appear as simple wallet IN/OUT (`docs/SWAP_SOURCE_RESEARCH.md`) |
| Arkham quota | `/tokenflow` adds up to 10× `/intelligence/address` per call; heavy endpoints rate-sensitive (~1 rps cited in docs) |
| Birdeye | Pair maker filter is client-side on pair trade payloads; deep modes are slow (pages × 1.2s delay) |
| Wallet + token path | Can undercount vs Dexscreener maker table for same wallet/token |
| Config | Scan thresholds hardcoded in `config.py`; env not reloaded without restart |
| State | JSON files without file locking |
| Thread pool | Long `to_thread` jobs block worker threads |
| Telegram | Reports truncated (e.g. 10 makerfind events, 20 makertrades); `split_text` chunking |
| Dependencies | `requirements.txt` unpinned versions |
| Repo noise | Many `*_before_*`, `*_backup_*`, `*.save` copies — not used at runtime |

---

## Transfer and cabal-investigation goals

No dedicated cabal/cluster command exists. Engineering direction implied by docs and current commands:

**Transfer investigation (partial today):**

- `/wallettx` — Arkham wallet+token `/transfers`, IN/OUT summary, unique/main counterparty, optional cycle list, first 20 events.
- `/wallettrade` — same transfer feed (limit 50) + IN/OUT cycle heuristics + Birdeye price on up to 5 completed cycles; behavior class includes “Pool-centric” when one counterparty dominates.
- `/tokenflow` — token-level top flow addresses + Arkham label/entity enrichment and infrastructure vs candidate classification (not wallet-specific).

**Gaps for link/cabal-style analysis:**

- No counterparty enrichment loop on transfers (unlike `/tokenflow` on flow addresses).
- No transfer pagination beyond single Arkham page.
- No graph / shared-counterparty / wallet-cluster aggregation in code.
- No `/walletlinks TOKEN WALLET` (counterparty map + labels + optional top-flow membership).
- Swap truth for routing: `/walletswaps` (Solscan → Birdeye), not merged into transfer reports automatically.

**Cabal / cluster goals (documentation only):**

- Roadmap: “wallet or wallet **cluster** with historical pattern X” (`ALPHA_ENGINE_ROADMAP.md`).
- Future `/investigate`: active makers on a pair, filter infrastructure, compare to `/walletprofile`-style history, hypothesis labels (Entry Watch, Distribution Watch, Exit Risk, Noise, Needs More Data).
- `WALLET_ALPHA_PLAN.md`: counterparty labels/entities, transfer amounts, distinguish swap vs wallet-to-wallet transfer, filter CEX/DEX/bridge/program before scoring wallets.

**Practical near-term path (not implemented):** extend transfer diagnostics with paginated `/transfers`, enriched counterparties (pattern from `format_token_flow_record`), optional cross-check against `/tokenflow` and shallow `/walletswaps` when transfer feed is empty — keep manual, capped, and separate from alert loop.

---

## Dependencies and entry

```
requirements.txt: python-dotenv, python-telegram-bot, requests, colorama
```

Run: `python rab9_arkham.py`. Requires `TELEGRAM_BOT_TOKEN`; optional keys gate Birdeye/Solscan features per README.

---

## Related files for agents

| Task | Read first |
|------|------------|
| New command | `handlers.py`, relevant `*_sources.py` or `arkham.py` |
| Maker behavior | `maker_sources.py` |
| Transfers | `arkham.py` (`get_wallet_token_transfers`, `summarize_wallet_transfer_items`) |
| Product direction | `docs/ALPHA_ENGINE_ROADMAP.md` |
| Test expectations | `docs/FIELD_TESTING.md` |
| Command list | `README.md` |
