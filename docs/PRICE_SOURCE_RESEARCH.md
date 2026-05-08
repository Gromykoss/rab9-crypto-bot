# RAB9 Price Source Research

Goal: find a reliable source for Solana token price, market cap, liquidity, and volume near wallet IN/OUT timestamps so `/wallettrade v2` can estimate:

- price/MC near IN
- price/MC near OUT
- max price after IN
- max price between IN and OUT
- Entry Quality
- Exit Quality

No RAB9 code changes are implied by this document.

## Source Comparison

| Source | Supports Solana | Historical price by timestamp | OHLCV candles | Wallet-token trades | Amount/usdValue | API key required | Free/trial availability | Pros | Cons | Best use in RAB9 |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| Dexscreener | Yes | No public timestamp lookup | No public OHLCV in API reference | No | No | No | Free public API | Already used; good token/pair discovery; current price, liquidity, FDV/MC, volume, pairCreatedAt | No documented historical candles; rolling `priceChange/volume/txns` are not a price series | Pair discovery and current context only |
| GeckoTerminal | Yes | Approx via pool OHLCV candle nearest timestamp | Yes, pool OHLCV | Pool trades only, not wallet-centric | OHLCV volume, not wallet swap amounts | Public docs imply no key for basic API; CoinGecko paid API has on-chain endpoints | Public/basic access exists; paid CoinGecko tiers for broader on-chain API | Good no/low-friction candles; top pools by token; works for unlisted DEX tokens | Need pool selection; market cap may be null; historical range/granularity limits; multi-pair migrations can distort price | Fallback candle source for price-at-time |
| Birdeye | Yes | Yes, `history_price` with `time_from/time_to` | Yes, `/defi/ohlcv`, max 1000 records | Yes, trade endpoints filter by owner/token/pair | Trades and PnL endpoints can expose amounts/USD depending endpoint | Yes, `X-API-KEY` | API key required; plan limits/cost depend account | Best direct fit for token historical price/OHLCV and wallet/pair trades; supports Solana headers | Requires key; rate limits/cost; need validate token coverage and response fields for meme tokens | Recommended MVP source |
| Bitquery | Yes | Yes via DEX trades / OHLC aggregation | Yes via Solana DEXTradeByTokens / Trading APIs | Yes, wallet trades by signer/account/trader | Yes, trade amount, USD, PriceInUSD, market cap/supply in Trading APIs | Yes | API token required; commercial/trial via Bitquery | Most complete for real swaps, wallet trades, OHLC, USD amounts, market cap/supply snapshots | GraphQL complexity; cost; schema learning; can be overkill for MVP | Best advanced source for precise `/wallettrade` later |
| Solscan Pro API | Yes | Limited: token price/historical endpoints; daily/range oriented | Historical token/market data exists, but less candle-focused | Yes: account/token defi activities and transfers | Defi activities include token amounts/decimals; USD depends endpoint/coverage | Yes | Paid Pro levels; documented CU/month and request limits | Strong Solana transaction truth; account/token swaps with token amounts; can link tx hashes | Paid; price endpoints may be coarse/deprecated; historical price range limited in some endpoints | Validate Arkham cycles and reconstruct swap amounts |
| Arkham | Yes | Has token price history endpoints in LLM index, but not enough verified detail in public page | Unknown/limited | `/transfers`, `/swaps` | `/transfers` may not include amount/usdValue for current use; `/swaps` may expose more if filters fit | Yes | API access required; heavy endpoints 1 rps | Already integrated; labels/entities are excellent; transfer discovery works | `/transfers` response currently insufficient for PnL; heavy endpoint limits; price-history details need live validation | Keep for labels, transfer discovery, and possible `/swaps` probe |

## Source Notes

### Dexscreener

The public API reference lists latest profiles, boosted tokens, orders, pair lookup, token-pair lookup, token lookup, and search. Pair/token responses expose current `priceUsd`, `liquidity`, `fdv`, `marketCap`, rolling `txns`, `volume`, `priceChange`, and `pairCreatedAt`.

Findings:

- No documented public historical OHLCV/candles endpoint.
- No direct price-at-timestamp endpoint.
- No wallet-token trade endpoint.
- Free public API is useful for current context and pair discovery.
- Rate limits in docs: 60 rpm for profile/boost/order endpoints and 300 rpm for pair/search/token endpoints.

RAB9 use: keep using Dexscreener for current pair selection, liquidity sanity, and `pairAddress`, not for historical `/wallettrade v2` calculations.

### GeckoTerminal

GeckoTerminal is on-chain/pool-first. To get historical price, identify the token's relevant pool, then query pool OHLCV:

```text
/networks/{network}/tokens/{token_address}/pools
/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}
```

Useful parameters:

- `network`: `solana`
- `pool_address`
- `timeframe`: `minute`, `hour`, `day`
- `aggregate`
- `before_timestamp`
- `limit`
- `currency`: `usd` or token/native depending endpoint/version

Findings:

- Suitable for approximate price-at-time via nearest candle.
- Pool discovery is possible from token address.
- OHLCV is pool-specific; pool migration and multiple pools are major risks.
- `market_cap_usd` may be null; `fdv` is more consistently available.

RAB9 use: fallback candle provider when Birdeye is unavailable.

### Birdeye

Relevant endpoints:

```text
GET /defi/history_price
GET /defi/ohlcv
GET /defi/v3/txs
GET /defi/v3/token/txs-by-volume
GET /defi/txs/pair
POST /wallet/v2/pnl/details
```

Useful parameters:

- `address`: token or pair address
- `address_type`: `token` or `pair` for history price
- `type`: candle/timeframe such as `1m`, `5m`, `1H`, `1D`
- `time_from`, `time_to`: unix seconds
- header `x-chain: solana`
- header `X-API-KEY`
- trade filters: `owner`, `token_address`, `pool_id`, `tx_type`, `before_time`, `after_time`

Findings:

- Directly supports Solana token historical price and OHLCV.
- OHLCV endpoint documents max 1000 records.
- Trade endpoints can filter by wallet owner, token, pair, time, and tx type.
- Requires API key; 401/403/429 responses are documented.

RAB9 use: primary MVP source because it covers both candles and future swap refinement.

### Bitquery

Relevant APIs:

- `Solana.DEXTradeByTokens`
- `Trading.Trades`
- `Trading.Pairs`
- wallet trade filters by signer/account/trader
- OHLC aggregation using `Block.Time(interval: ...)`

Findings:

- Can query Solana wallet DEX trades and token DEX trades.
- Can return `Price`, `PriceInUSD`, amounts, USD amounts, DEX protocol, tx signature, market/pair, and sometimes supply/market cap fields.
- Can build OHLCV from DEX trades.
- Requires API token.

RAB9 use: advanced precise source when `/wallettrade` moves from behavior-only to true swap/PnL analysis.

### Solscan Pro API

Relevant endpoints:

```text
GET /v2.0/account/defi/activities
GET /v2.0/token/defi/activities
GET /v2.0/token/transfer
GET /v2.0/token/historical-data
GET /v2.0/token/price
GET /v2.0/market/* historical market data
GET /v2.0/transaction/detail
```

Findings:

- Account defi activities can filter by wallet address, token, activity type, and unix time range.
- Account/token defi activity schemas include transaction hash, block time, from/to, platform/source, token1/token2, decimals, and amounts.
- Token transfer endpoint can filter by token and from/to wallet addresses.
- Token price endpoint is documented as deprecated and date-based (`YYYYMMDD`), so it is not ideal for minute-level timestamp lookup.
- Token historical-data supports limited ranges in docs (`7`, `30` days).
- Pro API is paid; documented plans start at Level 2 with monthly CU/request limits.

RAB9 use: best Solana transaction validator and swap-amount source, not first-choice candle source.

### Arkham

Current RAB9 usage:

- `/transfers` for wallet/token transfer diagnostics.
- `/token/top_flow` for top-flow discovery.
- address intelligence for labels/entities.

Findings:

- Arkham docs list `/transfers`, `/swaps`, `/token/price/history/{chain}/{address}`, `/token/market/{id}`, token volume/flow endpoints, and network history.
- Heavy endpoints include `/transfers`, `/swaps`, `/token/top_flow`, and token volume, with 1 rps limits.
- Current `/transfers` response observed in RAB9 does not reliably include amount/usdValue/price for `/wallettrade` PnL.
- `/swaps` and token price-history should be probed in a separate diagnostic before relying on them.

RAB9 use: labels/entities and transfer discovery remain valuable. Arkham alone is not enough for v2 price/PNL until `/swaps` and price history response shapes are validated.

## MVP Architecture for `/wallettrade v2`

### A. If Price Candles Are Available

Use this for approximate price-action metrics.

1. Reuse `/wallettrade v1` cycles from Arkham `/transfers`.
2. For each cycle:
   - IN timestamp = first IN in cycle.
   - OUT timestamp = first OUT in cycle, if present.
3. Resolve token to main pool:
   - Dexscreener for current pool candidates.
   - Birdeye token OHLCV if token-level candles are reliable.
   - GeckoTerminal top pool as fallback.
4. Fetch candles around:
   - IN timestamp +/- tolerance.
   - OUT timestamp +/- tolerance.
   - IN to `IN + horizon` for max after entry.
   - IN to OUT for max between IN and OUT.
5. Compute approximate:
   - entry price near IN;
   - exit price near OUT;
   - max price after IN;
   - max price between IN and OUT;
   - entry percentile within post-entry range;
   - exit percentile within IN-to-OUT/post-entry range.

Do not call it exact PnL unless real swap amounts are available.

### B. If Trades/Swaps Are Available

Use this for more accurate wallet behavior.

1. Query wallet+token DEX trades from Birdeye, Bitquery, or Solscan.
2. Match by wallet, token, tx hash, and timestamp.
3. Extract:
   - side: buy/sell;
   - token amount;
   - quote amount;
   - USD amount;
   - execution price;
   - DEX/pool.
4. Build real entries/exits from swap events.
5. Use candles only for post-entry max and drawdown after exit.

This is the path toward realized return and exit quality.

### C. If No Reliable Source Exists

Keep `/wallettrade v1` as behavior-only:

- IN/OUT counts.
- cycle detection.
- main counterparty.
- no PnL;
- no entry quality;
- no exit quality.

## Recommended MVP Source

Primary: Birdeye.

Why:

- Direct Solana support.
- Token historical price endpoint.
- Token OHLCV endpoint.
- Trade endpoints with wallet owner, token/pair, and time filters.
- Better fit for timestamp-based lookup than Dexscreener.
- Less GraphQL complexity than Bitquery for MVP.

Fallback: GeckoTerminal.

Why:

- Pool OHLCV is available and simple.
- Can discover pools from token address.
- Useful when Birdeye key/plan is unavailable.
- Good enough for approximate price-at-time if pool selection is sane.

Advanced later: Bitquery.

Use Bitquery when RAB9 needs precise wallet swaps, USD amounts, supply/market-cap snapshots, and deeper historical OHLC across DEX protocols.

## Risks / Unknowns

- Dexscreener may not provide historical candles through the public API.
- Price by timestamp is usually approximate unless using exact swap execution price.
- Pool migration and multiple pairs can break calculations if RAB9 chooses the wrong pool.
- Liquidity fragmentation can make max price and candle wicks misleading.
- Token decimals and scaled UI amounts must be handled before using amounts.
- Without real swap amounts, PnL will be approximate or invalid.
- Market cap may require supply data at timestamp; FDV may be easier than true circulating market cap.
- Birdeye/Bitquery/Solscan cost and rate limits need live account validation.
- Arkham `/swaps` and token price history response shapes should be tested before relying on them.

## Next Step

Build a manual `/pricesource TOKEN TIMESTAMP` diagnostic before `/wallettrade v2`.

It should:

1. Query Birdeye `history_price` and `ohlcv` for Solana.
2. Query GeckoTerminal top pool OHLCV as fallback.
3. Return nearest candle price, candle timestamp, distance from requested timestamp, liquidity/volume if available, and data-quality flags.
4. Avoid PnL until swap amounts are available.

## Source Links

- Dexscreener API reference: https://docs.dexscreener.com/api/reference
- GeckoTerminal FAQ: https://apiguide.geckoterminal.com/faq
- CoinGecko/GeckoTerminal OHLCV guide: https://www.coingecko.com/learn/dex-data-api
- Birdeye historical price: https://docs.birdeye.so/reference/get-defi-history_price
- Birdeye OHLCV: https://docs.birdeye.so/reference/get-defi-ohlcv
- Birdeye trades V3: https://docs.birdeye.so/reference/get-defi-v3-txs
- Bitquery Solana DEX trades: https://docs.bitquery.io/docs/blockchain/Solana/solana-dextrades/
- Solscan Pro endpoints: https://docs.solscan.io/api-access
- Solscan account defi activities: https://pro-api.solscan.io/pro-api-docs/v2.0/reference/v2-account-defi-activities
- Solscan token transfer: https://pro-api.solscan.io/pro-api-docs/v2.0/reference/v2-token-transfer
- Solscan token historical data: https://pro-api.solscan.io/pro-api-docs/v2.0/reference/v2-token-historical-data
- Arkham API docs / LLM index: https://intel.arkm.com/llms.txt
