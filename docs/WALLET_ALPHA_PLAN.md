# RAB9 Wallet Alpha Plan

Goal: find wallets that historically entered tokens before meaningful price expansion and exited closer to upper parts of the move.

Important: token age at entry is not the main criterion. A wallet can buy minutes, days, weeks, or months after launch. The core question is what price did after the wallet entered, and how the wallet exited.

## 1. `/wallettrade WALLET TOKEN`

Purpose: produce one token-specific trade quality report for one wallet.

Input:

```text
/wallettrade WALLET TOKEN
```

Optional future form:

```text
/wallettrade solana WALLET TOKEN 180d
```

High-level flow:

1. Resolve `TOKEN` to a Solana token mint and primary pair/market.
2. Pull wallet-token transfer and swap history for the requested lookback.
3. Reconstruct wallet position over time:
   - token balance delta;
   - buy/sell direction;
   - estimated token amount;
   - estimated USD/SOL notional;
   - transaction hash and block time.
4. Identify entry event.
5. Build post-entry price series.
6. Compute post-entry performance windows.
7. Identify exit event.
8. Compute exit quality.
9. Classify wallet behavior for this token.
10. Return a compact human-readable report plus raw commands for follow-up:
    - `/wallet WALLET`
    - `/watchwallet WALLET wallettrade:TOKEN`
    - `/token solana TOKEN`

Report sections:

- Wallet and token context.
- Entry event.
- Post-entry performance.
- Exit event.
- Exit quality.
- Classification.
- Data quality and missing data notes.

## 2. Entry Event

The entry event is the first meaningful acquisition that starts a positive token position for the wallet within the analyzed period.

Preferred detection:

1. Sort all token balance-changing events by block time ascending.
2. Normalize transfers/swaps into signed token deltas:
   - positive delta: wallet receives token;
   - negative delta: wallet sends token.
3. Track cumulative token balance.
4. Entry event is the earliest positive delta where previous balance was zero or near-zero and new balance exceeds dust threshold.

Dust threshold:

- Use token decimals.
- Ignore tiny transfer noise below max of:
  - 0.01% of wallet maximum observed token balance;
  - a token-specific absolute minimum if known;
  - USD value below a configurable floor when price is available.

Entry event fields:

- `entry_time`
- `entry_tx`
- `entry_token_amount`
- `entry_price_usd`
- `entry_notional_usd`
- `entry_source`: swap, transfer, airdrop, LP movement, unknown
- `entry_confidence`: high, medium, low

Important distinction:

- If wallet receives tokens from another wallet without a swap, mark source as transfer and lower confidence for entry price.
- If wallet receives tokens from a DEX/pool/router and spends SOL/USDC/USDT, mark source as swap and confidence high.
- If transfer comes from a known deployer/team/airdrop address, do not treat it as a normal smart-money buy without manual review.

## 3. Post-Entry Performance

Post-entry performance measures what price did after the wallet entered. Token age at entry is recorded as context only, not as a primary score.

Required windows:

- 1h
- 4h
- 24h
- 7d
- 30d
- 90d

For each window:

1. Build price series from `entry_time` to `entry_time + window`.
2. Use `entry_price_usd` as baseline.
3. Find maximum price in the window.
4. Calculate:

```text
max_return = (max_price_after_entry / entry_price_usd) - 1
```

Also calculate:

```text
max_drawdown_after_entry = (min_price_after_entry_before_max_or_window_end / entry_price_usd) - 1
time_to_max_return = max_price_timestamp - entry_time
```

Suggested output table:

```text
Post-Entry Performance
1h:  max +X%, drawdown -Y%, time to max 00:12
4h:  max +X%, drawdown -Y%, time to max 02:31
24h: max +X%, drawdown -Y%, time to max 18:04
7d:  max +X%, drawdown -Y%, time to max 3d 4h
30d: max +X%, drawdown -Y%, time to max 11d
90d: max +X%, drawdown -Y%, time to max 44d
```

Data quality rules:

- If no reliable candle/price exists exactly at entry, use nearest price within tolerance.
- Tolerance should be small for fresh tokens, for example 5 minutes for intraday analysis.
- If nearest price is too far away, mark metric as low confidence.
- If liquidity is too low, flag returns as unreliable because a single wick can overstate tradable performance.

## 4. Exit Event

The exit event is the first meaningful reduction that materially closes or de-risks the position.

There can be multiple exit styles:

- Full exit: cumulative token balance returns to zero or near-zero.
- Major partial exit: wallet sells/transfers out at least 50% of maximum observed position.
- Scaling exit: multiple sells reduce position over time.
- No exit observed: wallet still holds or data is incomplete.

Detection:

1. Start after entry event.
2. Track cumulative token balance.
3. Identify negative deltas.
4. Determine:
   - first partial exit;
   - largest exit transaction;
   - full exit time if balance returns near zero;
   - weighted average exit price if multiple exits.

Exit event fields:

- `exit_time`
- `exit_tx`
- `exit_type`: full, partial, scaled, no exit, transfer-out, unknown
- `exit_token_amount`
- `exit_price_usd`
- `exit_notional_usd`
- `remaining_balance_pct`
- `exit_confidence`

Transfer-out caveat:

- Sending tokens to another wallet is not necessarily a sale.
- If destination is a known CEX, DEX, router, bridge, or aggregator, treat it as likely exit.
- If destination is an unlabeled wallet, mark as transfer-out and lower exit confidence.

## 5. Exit Quality

Exit quality measures whether the wallet sold close to the upper part of the post-entry move and avoided later downside.

Metrics:

```text
realized_return = (weighted_avg_exit_price / entry_price_usd) - 1
```

Post-entry range:

```text
post_entry_low = min(price from entry_time to analysis_end)
post_entry_high = max(price from entry_time to analysis_end)
exit_percentile = (weighted_avg_exit_price - post_entry_low) / (post_entry_high - post_entry_low)
```

Clamp percentile to 0..1 and show as percentage.

Drawdown avoided after exit:

```text
post_exit_high_or_exit_price = max(weighted_avg_exit_price, max price shortly after exit)
post_exit_low = min(price from exit_time to analysis_end)
drawdown_avoided = (post_exit_low / weighted_avg_exit_price) - 1
```

Interpretation:

- High exit percentile means wallet sold near the upper part of the observed move.
- Large negative post-exit drawdown means wallet avoided meaningful downside.
- If price continued much higher after exit, note "left upside on table".

Suggested output:

```text
Exit Quality
Realized return: +420%
Exit percentile: 82%
Drawdown avoided after exit: -67%
Exit quality: strong
```

## 6. Wallet Classification

Classifications are token-specific first. `/walletprofile` later aggregates them across many tokens.

### Scalper

Signals:

- Entry and exit within minutes to a few hours.
- Good 1h or 4h performance.
- Small holding time.
- Often many trades and high turnover.

Use when:

- `holding_time <= 4h`
- realized return positive or exit percentile high
- no meaningful long hold

### Swing Wallet

Signals:

- Holds from hours to days.
- Strong 24h or 7d post-entry performance.
- Exits before or around local top.

Use when:

- `4h < holding_time <= 14d`
- post-entry return strong in 24h/7d windows
- exit percentile reasonable

### Position Wallet

Signals:

- Holds for weeks or months.
- Strong 30d or 90d post-entry performance.
- May scale out instead of single exit.

Use when:

- `holding_time > 14d`
- 30d/90d post-entry return is meaningful
- no immediate dump behavior

### Good Entry / Bad Exit

Signals:

- Price moved strongly after entry.
- Wallet exited too early, too late, or into weakness.

Use when:

- max post-entry return is high
- realized return is weak relative to max possible return
- exit percentile low or price continued much higher after exit

### Good Entry / Good Exit

Signals:

- Strong post-entry performance.
- Realized return strong.
- Exit percentile high.
- Meaningful drawdown avoided after exit.

Use when:

- max post-entry return high
- realized return captures a meaningful part of the range
- exit percentile above target threshold, for example 70%

### Late Buyer / Exit Liquidity

Signals:

- Wallet enters after most of the move already happened.
- Post-entry max return is weak or negative.
- Drawdown after entry is large.
- Entry appears near local top or during hype spike.

Use when:

- entry percentile within pre-entry/local range is high
- post-entry return weak
- max drawdown after entry severe

## 7. Data Needed

### Arkham

Use for:

- Wallet labels and entities.
- Address intelligence.
- Entity classification: CEX, DEX, protocol, bridge, market maker, fund, unlabeled wallet.
- Historical transfers if available in plan.
- Historical balance data if accessible.
- Token flow endpoints as discovery layer for candidate wallets.

Needed fields:

- transaction hash
- block time
- from/to address
- token address
- amount
- USD value if provided
- counterparty labels/entities
- chain
- balance before/after if available

### Solscan

Use for Solana transaction truth and wallet-token activity.

Relevant Pro API categories from Solscan docs:

- Account transfer
- Account defi activities
- Account balance change activities
- Account transactions
- Token transfer
- Token defi activities
- Token historical data
- Token price
- Market historical data

Needed fields:

- wallet account transactions
- SPL token transfers by wallet
- token transfers filtered by token and from/to wallet
- swap/defi activity records
- block time
- token decimals
- amount
- source/destination
- transaction signature
- market/pool address

### Dexscreener

Use for:

- Token pair discovery.
- Current pair metadata.
- Current price/liquidity/volume.
- Pair creation timestamp.
- Recent rolling price change windows exposed in pair response.
- DEX/pair URL for human review.

Needed fields:

- chainId
- dexId
- pairAddress
- baseToken / quoteToken
- priceUsd
- liquidity.usd
- volume windows
- txns windows
- priceChange windows
- pairCreatedAt
- url

## 8. Dexscreener Historical Price Limits

The public Dexscreener API reference currently exposes endpoints for latest profiles, boosts, orders, pair lookup, token-pair lookup, token lookup, and search. It does not expose a general historical candle/OHLC endpoint in the public reference.

Practical consequence:

- Dexscreener alone is not enough to calculate exact historical post-entry performance for old wallet entries.
- Pair responses include current price and rolling fields such as `priceChange`, `volume`, and `txns`, but those are not a full historical price series.
- `pairCreatedAt` helps with token/pair age context, not performance reconstruction.

Recommended approach:

1. Use Dexscreener for pair discovery and current context.
2. Use Solscan Pro token historical price / market historical data if available.
3. Add a fallback historical price provider if needed, for example GeckoTerminal, Birdeye, Helius-enhanced swap reconstruction, or an internal RAB9 price recorder.
4. Store snapshots going forward so RAB9 can build its own price history for watched tokens.

## 9. `/walletprofile WALLET`

Purpose: aggregate many `/wallettrade WALLET TOKEN` results into a wallet-level alpha profile.

Input:

```text
/walletprofile WALLET
```

Pipeline:

1. Pull wallet token activity across a lookback period.
2. Exclude infrastructure and programs:
   - Jupiter
   - Raydium
   - Meteora
   - Orca
   - Phoenix
   - OpenBook
   - Pump / PumpSwap
   - CEX labels
   - routers
   - aggregators
   - bridges
3. Select candidate token trades:
   - positive token entry;
   - meaningful notional or meaningful balance;
   - token has price history;
   - not spam/airdrop-only unless later sold.
4. Run wallettrade-style analysis per token.
5. Aggregate metrics:
   - number of analyzed tokens;
   - win rate;
   - median max post-entry return;
   - median realized return;
   - median exit percentile;
   - average drawdown avoided;
   - average holding time;
   - best trades;
   - worst exits;
   - recurring DEX/routes;
   - preferred market-cap/liquidity bands if known.
6. Classify wallet-level style:
   - Scalper
   - Swing Wallet
   - Position Wallet
   - Mixed
   - Mostly Exit Liquidity
   - Insufficient Data

Suggested profile output:

```text
Wallet Alpha Profile
Wallet: WALLET
Analyzed tokens: 18
Data quality: medium

Style: Swing Wallet
Win rate: 61%
Median max post-entry return: +240%
Median realized return: +82%
Median exit percentile: 68%
Median holding time: 3d 8h

Strengths:
- Finds tokens before meaningful 7d moves.
- Usually exits before large post-top drawdowns.

Weaknesses:
- Often exits early on 30d runners.

Best examples:
- TOKEN1: Good Entry / Good Exit, +620% realized
- TOKEN2: Good Entry / Bad Exit, +40% realized, +900% max after entry

Next actions:
/wallet WALLET
/watchwallet WALLET alpha-profile
```

## 10. Implementation Phases

Phase 1: manual single-trade report.

- Add `/wallettrade WALLET TOKEN`.
- Use Solscan for transfers/swaps.
- Use one historical price source.
- Return entry, post-entry performance, exit, and classification.

Phase 2: better price engine.

- Add historical price provider abstraction.
- Prefer token/pair candles when available.
- Add fallback to swap-derived prices.
- Store data quality flags.

Phase 3: wallet profile.

- Add `/walletprofile WALLET`.
- Analyze top N historical token positions.
- Cache expensive lookups.
- Produce wallet-level style and score.

Phase 4: alpha candidate discovery.

- Use `/tokenflow` to find candidate wallets.
- Exclude infrastructure/programs.
- Run walletprofile on candidate wallets manually.
- Add watchlist only by explicit user command.

## Guardrails

- Do not auto-add wallets to wallet watchlist.
- Do not run wallettrade/profile in the alert loop.
- Keep expensive historical analysis manual.
- Always show data quality and source confidence.
- Do not treat labeled DEX/router/CEX/bridge/program addresses as smart-money wallets.
- Token age at entry is context, not the main score.

## Source Notes

- Dexscreener public API reference: https://docs.dexscreener.com/api/reference
- Solscan Pro API endpoint list and CU notes: https://docs.solscan.io/api-access
- Solscan token transfer endpoint: https://pro-api.solscan.io/pro-api-docs/v2.0/reference/v2-token-transfer
- Solscan account transactions endpoint: https://pro-api.solscan.io/pro-api-docs/v2.0/reference/v2-account-transactions
- Arkham API overview: https://docs.intel.arkm.com/openapi/transfers
