# RAB9 Swap Source Research

Goal: identify the best source for parsed Solana swaps when Arkham `/transfers` returns no useful IN/OUT cycles but Solscan shows many SWAP activities for the wallet.

Reference wallet:

```text
2qnHs8fZZLUJFVCkTCEXXZnEZTgfu7HFVBFmbUmXiYiW
```

This document is research only. It does not imply code changes, background jobs, auto-watchlist behavior, or trading recommendations.

## Short Answer

Recommended MVP source: Solscan Pro `account/defi/activities`.

Why: it is closest to what the UI shows as SWAP activities and exposes parsed Solana DeFi activity records with wallet filter, token filter, timestamps, transaction signature, token1/token2, decimals, and amounts.

Best fallback: Birdeye `defi/v3/txs` / `defi/v3/token/txs-by-volume`.

Why: Birdeye has wallet `owner` filters, token-filtered trade endpoints, time filters, AMM source filters, and Solana trade records. It is likely easier than Bitquery for an MVP if the existing `BIRDEYE_API_KEY` works for those endpoints.

Best advanced source: Bitquery Solana `DEXTradeByTokens`.

Why: it can return wallet DEX trades with transaction signature, block time, buy/sell token, token amounts, USD amounts, price, protocol, and market. It is powerful but GraphQL-heavy and likely costlier.

Arkham should stay a label/entity and transfer-discovery source until `/swaps` is validated against Solana wallets in RAB9.

## Source Matrix

| Source | Wallet swaps | Token filter | Timestamp | Input/output tokens | Amounts | USD value | txHash | API key | Fit for RAB9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Solscan Pro API | Yes | Yes | Yes | Yes | Yes | Maybe/endpoint-dependent | Yes | Yes | Best MVP parsed swaps |
| Birdeye trades | Yes | Yes | Yes | Yes | Likely yes | Likely yes | Yes | Yes | Strong fallback/MVP candidate |
| Bitquery Solana DEX trades | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Best advanced source |
| Arkham swaps/transfers | Swaps endpoint exists; filters need probe | Likely, but verify | Likely | Unknown for Solana shape | Unknown | Unknown | Likely | Yes | Probe only; keep labels |

## 1. Solscan Pro API

Relevant endpoints:

```text
GET /v2.0/account/defi/activities
GET /v2.0/account/defi/activities/export
GET /v2.0/token/defi/activities
GET /v2.0/token/defi/activities/export
GET /v2.0/transaction/detail
```

Useful filters:

```text
address=WALLET
activity_type[]=ACTIVITY_TOKEN_SWAP
activity_type[]=ACTIVITY_AGG_TOKEN_SWAP
token=TOKEN
from_time=unix
to_time=unix
page_size=100
sort_by=block_time
sort_order=desc|asc
```

Observed schema from docs:

| Field | Use |
|---|---|
| `trans_id` | txHash/signature |
| `block_time`, `time` | timestamp |
| `activity_type` | swap / aggregator swap / LP / bridge classification |
| `from_address`, `to_address` | wallet/counterparty context |
| `platform`, `sources`, `routers` | DEX/router/platform context |
| `routers[].token1`, `routers[].token2` | input/output token candidates |
| `amount1`, `amount2` | parsed token amounts |
| `token1_decimals`, `token2_decimals` | amount normalization |
| `child_routers` | multi-hop route details |

Assessment:

| Question | Answer |
|---|---|
| Swaps by wallet | Yes, `address` on account defi activities |
| Filter by token | Yes, `token` query param |
| Timestamp | Yes, `block_time` and `time` |
| Input/output token | Yes, `token1` / `token2` in routers |
| Amount | Yes, `amount1` / `amount2` |
| USD value | Not guaranteed in docs for account defi activities; may need price join |
| txHash | Yes, `trans_id` |
| API key required | Yes |
| Fit | Best first implementation for `/walletswaps` |

Pros:

- Matches the Solscan UI mental model for SWAP activities.
- Has both wallet and token filters.
- Parsed token/amount fields reduce the need to decode Solana instructions.
- Supports aggregator swaps and route fields.

Cons:

- Paid/pro API.
- USD value may not be present on the account defi activity record.
- Multi-hop routes need normalization.
- Need verify whether `token=TOKEN` matches either side of swap in all cases.

Best use in RAB9:

- Primary source for `/walletswaps WALLET` and `/walletswaps WALLET TOKEN`.
- Use `transaction/detail` as a drilldown fallback when route parsing is ambiguous.

## 2. Birdeye Wallet Trades / Txs

Relevant endpoints:

```text
GET /defi/v3/txs
GET /defi/v3/txs/recent
GET /defi/v3/token/txs
GET /defi/v3/token/txs-by-volume
GET /defi/txs/token
```

Useful filters:

```text
owner=WALLET
token_address=TOKEN
address=TOKEN
tx_type=swap|buy|sell|all
source=raydium|meteora_dlmm|pump_amm|...
before_time=unix
after_time=unix
limit=100
ui_amount_mode=scaled
x-chain: solana
X-API-KEY: ...
```

Assessment:

| Question | Answer |
|---|---|
| Swaps by wallet | Yes, `owner` |
| Filter by token | Yes on token endpoints; V3 all endpoint filters need live validation |
| Timestamp | Yes, sort by `block_unix_time` |
| Input/output token | Expected in trade payload; verify exact keys |
| Amount | Expected in trade payload |
| USD value | Likely, especially volume-filter endpoints |
| txHash | Expected in transaction record |
| API key required | Yes |
| Fit | Good fallback or parallel MVP candidate |

Pros:

- RAB9 already has Birdeye key plumbing for `/pricesource`.
- Wallet owner and time filters are documented.
- Solana-only AMM source enum is useful for route classification.
- `token/txs-by-volume` supports volume filters and larger recent limits.

Cons:

- Response shape must be probed for exact input/output token names.
- Some endpoints cap offset + limit.
- Plan/rate limits matter.
- Token filtering may require choosing between `defi/v3/txs`, `defi/v3/token/txs`, and `token/txs-by-volume`.

Best use in RAB9:

- Fallback source if Solscan Pro is unavailable.
- Good source for wallet+token trade rows once response shape is validated.

## 3. Bitquery Solana DEX Trades

Relevant datasets:

```text
Solana.DEXTradeByTokens
Solana.DEXTrades
Trading.Trades
```

Useful filters:

```text
Transaction.Signer = WALLET
Trade.Account.Owner = WALLET
Trade.Buy.Account / Trade.Sell.Account = WALLET
Trade.Currency.MintAddress = TOKEN
Trade.Side.Currency.MintAddress = quote token
Transaction.Result.Success = true
Block.Time range
```

Useful fields:

| Field | Use |
|---|---|
| `Block.Time` | timestamp |
| `Transaction.Signature` | txHash |
| `Transaction.Signer` | wallet signer |
| `Trade.Currency.MintAddress` | traded token |
| `Trade.Side.Currency.MintAddress` | quote/other side token |
| `Trade.Amount`, `Trade.Side.Amount` | token amounts |
| `Trade.AmountInUSD`, `Trade.Side.AmountInUSD` | USD values |
| `Trade.Price`, `Trade.PriceInUSD` | execution price |
| `Trade.Dex.ProtocolName`, `ProtocolFamily` | DEX/router context |
| `Trade.Market.MarketAddress` | pool/market |

Assessment:

| Question | Answer |
|---|---|
| Swaps by wallet | Yes |
| Filter by token | Yes |
| Timestamp | Yes |
| Input/output token | Yes |
| Amount | Yes |
| USD value | Yes |
| txHash | Yes |
| API key required | Yes |
| Fit | Best v3 precision source |

Pros:

- Most complete for real DEX trade reconstruction.
- Can support later entry/exit quality and amount-aware analysis.
- Good protocol/pool metadata.
- Can query historical archive/combined datasets.

Cons:

- GraphQL complexity.
- Wallet identity may require testing multiple filters: signer, owner, buy account, sell account.
- Likely commercial limits/cost.
- More engineering time than Solscan/Birdeye.

Best use in RAB9:

- v3 precise source for `/wallettrade` once MVP proves useful.
- Good for validating Solscan/Birdeye rows on difficult wallets.

## 4. Arkham Swaps / Transfers Alternatives

Relevant endpoints listed by Arkham docs:

```text
GET /swaps
GET /transfers
GET /transfers/tx/{hash}
GET /tx/{hash}
GET /intelligence/address/{address}/all
GET /token/price/history/{chain}/{address}
```

Assessment:

| Question | Answer |
|---|---|
| Swaps by wallet | Endpoint exists; wallet filters need live probe |
| Filter by token | Likely, but verify exact params |
| Timestamp | Likely |
| Input/output token | Unknown until response shape is tested |
| Amount | Unknown for current access/chain |
| USD value | Unknown |
| txHash | Likely |
| API key required | Yes |
| Fit | Diagnostic/probe, not MVP source yet |

Pros:

- Already integrated in RAB9.
- Excellent wallet labels/entities.
- Useful transaction and counterparty context.

Cons:

- Current `/transfers` path returned zero IN/OUT cycles for a wallet where Solscan shows many swaps.
- `/transfers` is not enough for parsed swap reconstruction.
- `/swaps` response fields and Solana coverage need direct diagnostic testing.
- Arkham heavy endpoints can be credit/rate sensitive.

Best use in RAB9:

- Keep Arkham for labels and address context.
- Add a manual `/arkswaps` diagnostic only after `/walletswaps` source is chosen, if needed.

## Why Arkham `/transfers` Misses These Cycles

Likely causes:

- Parsed swaps are not simple wallet receives/sends in the transfer feed.
- Aggregator swaps can involve token accounts, pool vaults, routers, and temporary accounts.
- A swap can have multiple internal token movements that do not map cleanly to `from == wallet` or `to == wallet`.
- Arkham transfer filters may not return token-account level deltas in the shape RAB9 expects.

Implication:

RAB9 should use parsed DeFi/swap activity for wallet trade detection, then use Arkham labels as enrichment.

## MVP Proposal: `/walletswaps`

Commands:

```text
/walletswaps WALLET
/walletswaps WALLET TOKEN
```

Source order:

1. Solscan Pro `account/defi/activities`.
2. Birdeye `defi/v3/txs` or token-filtered trade endpoint as fallback.
3. Bitquery only after MVP if precision/cost is justified.

Request defaults:

| Setting | Value |
|---|---|
| chain | solana |
| activity types | token swap, aggregator token swap |
| sort | newest-first by block time |
| limit | 25 default, 50 max |
| optional token filter | match either input or output side |
| mode | manual only |

Normalize each swap into:

| Normalized field | Source field idea |
|---|---|
| `time` | `block_time` / `time` |
| `tx` | `trans_id` / signature |
| `source` | solscan / birdeye / bitquery |
| `platform` | platform/source/protocol |
| `token_in` | token spent by wallet if determinable |
| `amount_in` | input amount |
| `token_out` | token received by wallet if determinable |
| `amount_out` | output amount |
| `usd_value` | source USD value if present |
| `route` | direct / aggregator / multi-hop |
| `confidence` | high / medium / low |

Compact report:

```text
🔁 Wallet Swaps
Wallet: 2qnHs8...XiYiW
Token filter: BnXWv...pump / none
Source: Solscan Pro / account defi activities
Status: ok

Summary:
- Swaps returned: 25
- Token-filtered: yes/no
- Direct swaps: X
- Aggregator swaps: X
- Unique tokens touched: X
- Main platform: Jupiter/Raydium/Meteora/n/a

Swaps:
#1 2026-05-08T16:35:01Z | OUT SOL 1.2 -> IN TOKEN 6,000 | Raydium | tx: 5CJEF...RPpD
#2 2026-05-08T16:42:10Z | OUT TOKEN 3,000 -> IN SOL 0.8 | Jupiter | tx: 8adQ...9Kx2

Notes:
- No amount-based return calculated.
- No entry/exit quality calculated.
- Parsed swap source is being validated.
```

Rules:

- Do not calculate amount-based return until token side, quote side, decimals, and price path are reliable.
- Do not add background jobs.
- Do not add wallets to watchlist.
- Do not show raw events by default.
- Show readable errors for missing API key, 401, 429, or empty results.

## Recommended Source

Primary: Solscan Pro API.

Reason: the problem starts from Solscan UI showing SWAP activities, and the Pro API exposes the matching parsed activity category with wallet and token filters plus token/amount route fields.

Fallback: Birdeye trades.

Reason: RAB9 already has Birdeye setup, and Birdeye provides wallet owner and token trade endpoints for Solana. It can validate whether swaps are visible outside Solscan.

Advanced: Bitquery.

Reason: best long-term precision for real swap reconstruction, USD amounts, execution price, and protocol metadata, but more complex and likely costlier.

## Next Step

Build a manual diagnostic command before changing `/wallettrade`:

```text
/walletswaps WALLET
/walletswaps WALLET TOKEN
```

Start with Solscan Pro if a key is available. Return a compact normalized swap report and source status. Do not calculate amount-based return or exit quality until the normalized swap rows are verified against Solscan UI for known wallets.

## Sources

- Solscan account defi activities: https://pro-api.solscan.io/pro-api-docs/v2.0/reference/v2-account-defi-activities
- Solscan token defi activities: https://pro-api.solscan.io/pro-api-docs/v2.0/reference/v2-token-defi-activities
- Birdeye trades V3 all: https://docs.birdeye.so/reference/get-defi-v3-txs
- Birdeye recent trades V3: https://docs.birdeye.so/reference/get-defi-v3-txs-recent
- Birdeye token trades V3: https://docs.birdeye.so/reference/get-defi-v3-token-txs
- Birdeye token trades filtered by volume: https://docs.birdeye.so/reference/get-defi-v3-token-txs-by-volume
- Bitquery Solana DEX trades: https://docs.bitquery.io/docs/blockchain/Solana/solana-dextrades/
- Arkham API LLM index: https://intel.arkm.com/llms.txt
- Arkham swaps announcement: https://info.arkm.com/announcements/arkhams-swaps-feature-is-now-live
