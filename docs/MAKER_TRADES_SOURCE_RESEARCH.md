# RAB9 Maker Trades Source Research

Goal: identify the best source for a manual `/makertrades PAIR MAKER` diagnostic layer.

Context: RAB9 needs to answer whether a wallet or wallet cluster with historical behavior pattern X has appeared in a token, what it is doing now, and what historically tended to happen afterward.

Current gap: Dexscreener UI can show many pair-level maker trades for a specific pair and maker, while `/walletswaps WALLET TOKEN` through wallet-level Birdeye data can return too few rows. For example:

```text
Pair: 7nvp4qykvmpeuhobyrzcn1tqiz7k8pmk5uxqeebrzyh
Maker: AgmLJBMDCqWynYnQiPCuj9ewsNNsBJXyzoUhD9LJzN51
Token: F5tfztTnE4sYsMhZT5KrFpWvHmYSfJZoRjCuxKPbpump / Aliens
```

Conclusion: RAB9 needs a pair + maker layer, not only wallet + token diagnostics.

Sources checked:

- Bitquery Solana DEX Trades: https://docs.bitquery.io/docs/blockchain/Solana/solana-dextrades/
- Bitquery Crypto Trades API: https://docs.bitquery.io/docs/trading/crypto-trades-api/trades-api/
- Solscan Pro Account DeFi Activities: https://pro-api.solscan.io/pro-api-docs/v2.0/reference/v2-account-defi-activities
- Solscan Pro Token DeFi Activities: https://pro-api.solscan.io/pro-api-docs/v2.0/reference/v2-token-defi-activities
- Birdeye Trades - Pair: https://docs.birdeye.so/reference/get-defi-txs-pair
- Birdeye Trades - All V3: https://docs.birdeye.so/reference/get-defi-v3-txs
- Dexscreener API Reference: https://docs.dexscreener.com/api/reference

## Source Matrix

| Source | Pair filter | Maker filter | Token filter | Buy/Sell side | Amounts | USD value | Timestamp | TxHash | API key required | MVP fit | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Bitquery Solana DEX trades | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Strong, but GraphQL-heavy | Best source shape for exact `pair + maker`; likely needs query tuning and paid/trial access. |
| Solscan Pro | Partial | Yes | Yes | Partial/infer | Yes | Maybe | Yes | Yes | Yes | Medium fallback | Strong wallet/token DeFi activity source; pair-level reconstruction may require `platform`, `source`, router fields, or tx detail. |
| Birdeye | Yes | Yes via V3 | Partial | Likely | Likely | Likely | Yes | Yes | Yes | Best practical MVP | `defi/v3/txs` supports `owner` and `pool_id`; `defi/txs/pair` supports pair trades but docs do not show a maker filter on that endpoint. |
| Dexscreener official API | Yes | No public endpoint found | Yes/pair discovery | Aggregated only | No trade rows | Aggregated only | No trade rows | No trade rows | No | Not enough alone | Official API exposes pair/token/search/profile data, but no documented maker transactions endpoint. Do not use fragile UI scraping as MVP. |

## 1. Bitquery Solana DEX Trades

Fit: advanced primary-quality data source.

What it supports:

- Pair filter: yes, through `Pair.Market.Address` in the Trading `Trades` cube or market/pair fields in Solana DEX trade cubes.
- Maker filter: yes, through `Trader.Address`, `Transaction.Signer`, `Trade.Buy.Account`, or `Trade.Sell.Account`, depending on cube and protocol.
- Token filter: yes, through token mint fields.
- Buy/sell side: yes.
- Amounts: yes, base/quote amounts are available in Trading API examples.
- USD value: yes, examples expose USD amounts and price in USD.
- txHash: yes, transaction metadata includes hash/signature fields.
- Timestamp: yes, block time/timestamp fields are available.
- API key: required.

Strengths:

- Most complete candidate for `pair + maker`.
- Best chance to reproduce a Dexscreener maker table because it works at DEX trade level.
- Can later support historical profile metrics across many tokens/pairs.

Weaknesses:

- GraphQL query complexity.
- Requires API access token and likely quota planning.
- Field names differ by cube (`Trading.Trades`, `Solana.DEXTrades`, `DEXTradeByTokens`), so MVP needs one validated query contract.

MVP assessment: excellent data shape, but slower to implement than Birdeye because it needs query design and API access validation.

## 2. Solscan Pro

Fit: useful fallback and wallet activity source.

Relevant endpoints:

```text
GET /v2.0/account/defi/activities
GET /v2.0/token/defi/activities
GET /v2.0/transaction/detail
```

What it supports:

- Account DeFi Activities can query a maker wallet and filter by `activity_type`, `token`, `platform`, `source`, time range, pagination, and sort order.
- Token DeFi Activities can query a token and has a `from` filter, plus `platform`, `source`, and `token` filters.
- Responses include `trans_id`, `block_time`, `time`, `activity_type`, `from_address`, `to_address`, `platform`, `sources`, `routers`, token addresses, decimals, and amounts.

Open questions:

- Pair address may not be a first-class filter. It may need reconstruction from `platform`, `source`, `routers`, or transaction detail.
- Buy/sell side may need inference from token1/token2 or router direction.
- USD value is endpoint-dependent and should be validated against real responses.

MVP assessment: good fallback if Birdeye misses rows or if Bitquery is unavailable, but less direct for `PAIR + MAKER` unless pair/source mapping is reliable.

## 3. Birdeye

Fit: recommended practical MVP source.

Relevant endpoints:

```text
GET /defi/txs/pair
GET /defi/v3/txs
```

What docs show:

- `GET /defi/txs/pair` retrieves trades of a specified pair with `address`, `offset`, `limit`, `tx_type`, `sort_type`, and Solana `ui_amount_mode`. Limit is up to 50 and offset + limit must stay <= 10000.
- `GET /defi/v3/txs` retrieves trades with filters including `owner` for wallet, `pool_id` for liquidity pool, `source`, `before_time`, `after_time`, `limit`, and sort fields.

Why wallet-level `/defi/v3/txs` can differ from Dexscreener maker table:

- Wallet-level `owner + token` filtering is not the same as pair-level `pool_id + owner` filtering.
- Aggregator routes can hide or transform token-level rows.
- A maker table is pair-local; wallet-level token scans can include unrelated pools or miss pair-specific rows.
- Pair migrations or multiple pools can split activity across different pool IDs.
- Endpoint normalization can differ from Dexscreener UI's maker-table logic.

MVP assessment: best first implementation candidate because RAB9 already uses Birdeye and `defi/v3/txs` appears to support the exact combination needed: `owner` + `pool_id`.

## 4. Dexscreener Official API

Fit: pair discovery and market context only.

Official public endpoints include:

- latest token profiles;
- boosts and orders;
- pair by chain + pair address;
- pair search;
- token pairs by token;
- tokens by token address.

What is missing:

- No documented public endpoint for maker transactions.
- No documented public endpoint for trade rows filtered by maker.
- Pair responses include aggregate transaction counts, volume, price, liquidity, and token metadata, not the maker table rows needed for `/makertrades`.

MVP assessment: do not use Dexscreener UI scraping. Use official API only for pair metadata, pair discovery, and market context.

## Recommended Source

Primary source for MVP: Birdeye `GET /defi/v3/txs` with:

```text
owner=MAKER
pool_id=PAIR
tx_type=swap
limit=1..50
sort_by=block_unix_time
sort_type=desc
x-chain=solana
```

Why:

- It directly supports the two filters RAB9 needs for MVP: maker wallet and pair/pool.
- RAB9 already has `BIRDEYE_API_KEY` and Birdeye helper patterns.
- It is simpler than GraphQL for a first manual diagnostic command.

Fallback source: Solscan Pro.

Why:

- It can query account/token DeFi activities with parsed router and amount fields.
- It is useful if Birdeye misses wallet routes or if transaction detail is needed.
- Pair reconstruction needs validation, so it should not be primary until tested.

Advanced source later: Bitquery.

Why:

- Best long-term schema for exact pair, maker, side, amounts, USD values, price, and tx metadata.
- Best candidate for `/walletprofile` and `/investigate` at scale.
- More complex and likely more expensive, so validate after MVP command shape is proven.

## MVP `/makertrades` Design

Commands:

```text
/makertrades PAIR MAKER
/makertrades PAIR MAKER 50
```

Defaults:

- default limit: 20;
- max limit: 50;
- manual only;
- no deep background scan.

Report:

```text
Maker Trades Diagnostic
Pair: PAIR...
Maker: MAKER...
Source used: Birdeye /defi/v3/txs
Items returned: N

Summary:
- Buy count: X
- Sell count: Y
- Total buy USD: $X
- Total sell USD: $Y
- First trade: timestamp
- Last trade: timestamp
- Price change during maker window: +/-X%, if available

Behavior Classification:
- Primary: Maker Accumulation / Maker Distribution / Two-sided Active Maker / Weak Sample / Needs More Data
- Evidence: compact direction counts, USD totals, first/last time, maker-window price change

Events:
#1 time | BUY/SELL | amount token | value: $X | tx: abc...xyz
```

Buy/sell side should be pair-contextual:

- If maker receives base token and spends quote token, classify as `BUY`.
- If maker sends base token and receives quote token, classify as `SELL`.
- If source side is explicit, prefer source side but verify against token direction.
- If side cannot be confidently inferred, mark `UNKNOWN` and classify as `Needs More Data`.

Behavior Classification:

| Class | Rule |
|---|---|
| Maker Accumulation | Buy count >= 3, sell count == 0, total buy USD > 0. |
| Maker Distribution | Sell count >= 3, buy count == 0, total sell USD > 0. |
| Two-sided Active Maker | Buy count > 0 and sell count > 0. |
| Weak Sample | Items returned < 3. |
| Needs More Data | Missing side, missing amounts, missing USD value, or ambiguous pair mapping. |

## Guardrails

- No PnL unless source has reliable amount/value and position path.
- No buy/sell advice.
- No auto trading.
- No background deep scans.
- Manual diagnostics only.
- Avoid API burn with strict `limit <= 50`.
- Compact reports only.
- No duplicate summary sections.
- Show source and status clearly.
- Do not scrape Dexscreener UI as MVP.

## Next Step

Implement first:

```text
/makertrades PAIR MAKER 50
```

Primary MVP endpoint:

```text
Birdeye GET /defi/v3/txs
```

Required env key:

```text
BIRDEYE_API_KEY
```

Optional later env keys:

```text
SOLSCAN_API_KEY
BITQUERY_API_KEY
```

Validation case:

```text
/makertrades 7nvp4qykvmpeuhobyrzcn1tqiz7k8pmk5uxqeebrzyh AgmLJBMDCqWynYnQiPCuj9ewsNNsBJXyzoUhD9LJzN51 50
```

Compare returned rows against the Dexscreener maker table for the Aliens pair. If Birdeye `owner + pool_id` reproduces the maker table closely enough, keep it as MVP. If it misses rows, test Solscan Pro reconstruction, then Bitquery GraphQL.
