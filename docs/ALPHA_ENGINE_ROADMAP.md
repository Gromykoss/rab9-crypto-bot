# RAB9 Alpha Engine Roadmap

Purpose: define the target architecture for turning wallet behavior, price action, and repeated patterns into practical alpha intelligence.

This document is architectural only. It does not change code, runtime data, alert loops, tokens, environment files, or business logic.

## 1. Mission

RAB9 should answer:

```text
In this token, a wallet or wallet cluster with historical pattern X appeared.
They are doing Y now.
Historically, after Y, Z often happened.
```

Core equation:

```text
wallet behavior + price action + repeatability = alpha intelligence
```

The goal is not to predict every move. The goal is to identify repeatable behavior from wallets or maker groups and connect that behavior to what price did afterward.

## 2. Current Working Layers

RAB9 already has several manual diagnostic layers:

| Layer | Current role |
|---|---|
| `/tokenflow` | Finds top-flow addresses for a token through Arkham, enriches them, and classifies infrastructure vs candidate wallets. |
| `/wallettx WALLET TOKEN` | Tests Arkham wallet-token transfers and builds compact IN/OUT transfer diagnostics. |
| `/wallettrade WALLET TOKEN` | Summarizes transfer-based wallet/token behavior and uses Birdeye prices for approximate cycle price movement. |
| `/pricesource TOKEN TIMESTAMP` | Tests Birdeye historical price/OHLCV near a timestamp. |
| `/walletswaps WALLET [TOKEN]` | Finds parsed Solana swaps through Solscan/Birdeye sources and filters by token when provided. |
| `deep` / `deep10` | Scans more Birdeye wallet swap pages manually, with safe limits and delays. |
| Sell window price check | Compares Birdeye price near first and last token -> SOL events. |
| Swap behavior classification | Labels token-filtered swap behavior as distribution, accumulation, round-trip, no relevant swaps, or needs review. |

These layers are useful, but they are mostly wallet-centric. The next alpha step needs a pair-centric maker layer.

## 3. Main Gap

`/walletswaps WALLET TOKEN` through Birdeye wallet-level data does not always match the Dexscreener maker table.

Observed issue:

- Dexscreener shows pair-level maker trades.
- RAB9 wallet+token lookup can find too few events for the same wallet/token.
- For the `AgmLJ...` wallet on the Aliens token, RAB9 found little through wallet+token lookup, while Dexscreener showed many maker trades.

Likely reason:

- Dexscreener is organized around `pair + maker` trade activity.
- Current RAB9 swap diagnostics are organized around `wallet + token`.
- Routed swaps, pair migrations, aggregator paths, token aliases, and endpoint-specific filtering can cause wallet-level token searches to miss maker-table activity.

Conclusion: RAB9 needs a `pair + maker` layer before it can reliably compare current maker behavior against historical wallet behavior.

## 4. New Required Layer: Maker Trades

Future commands:

```text
/makertrades PAIR MAKER
/makertrades PAIR MAKER 50
```

Purpose: fetch trades for one maker on one specific pair.

Report shape:

| Field | Meaning |
|---|---|
| Pair | Pair address being inspected. |
| Maker | Maker wallet/address. |
| Source used | Bitquery, Solscan Pro, Birdeye, or other validated source. |
| Items returned | Number of maker trades returned after filtering. |
| Buy count | Pair-context buys by maker. |
| Sell count | Pair-context sells by maker. |
| Total buy USD | Sum of available buy-side USD notional. |
| Total sell USD | Sum of available sell-side USD notional. |
| First trade | Earliest trade timestamp in returned window. |
| Last trade | Latest trade timestamp in returned window. |
| Price change during maker window | Approximate pair/token price change between first and last maker trade. |
| Compact events | At most 20 rows: time, side, token amount, USD value, price, tx. |

Guardrails:

- Do not calculate exact PnL until position size and trade amounts are reliable.
- Do not give buy/sell advice.
- Keep the command manual.
- Keep reports compact.

## 5. Data Source Research Needed

Create a dedicated source research document for pair+maker trades.

Candidate sources:

| Source | Research question | Expected role |
|---|---|---|
| Bitquery Solana DEX trades | Can it query `pair + maker`, side, amount, USD value, price, and txHash reliably? | Best advanced candidate. |
| Solscan Pro account/defi/activities or pair endpoints | Can it filter by wallet and pair/token with parsed swap side and amount? | Possible MVP if endpoint shape is stable. |
| Birdeye pair/maker endpoints | Does Birdeye expose pair-level trades with maker filter, or only wallet/token trades? | Possible fallback if available. |
| Dexscreener official API | Does the public API expose the maker transactions shown in UI? | Validate limitations, likely not enough alone. |

Important note:

Dexscreener UI shows a maker table, but the official public API may not expose a direct maker-transactions endpoint. RAB9 should not assume the UI data is available through the official API until verified.

## 6. Behavior Classes

Target classes should describe behavior, not advice.

| Class | Meaning |
|---|---|
| Accumulation Pattern | Repeated or dominant buy-side activity in the token/pair. |
| Distribution Pattern | Repeated or dominant sell-side activity in the token/pair. |
| Round-trip Pattern | Both buy and sell activity are visible in the analyzed window. |
| Active Trading Wallet | Multiple buy/sell cycles across the token or across tokens. |
| Exit-Risk Candidate | Wallet or maker is selling into a move, especially if historical exits preceded drawdowns. |
| Possible Smart Entry | Wallet or maker bought before meaningful later price expansion in prior cases. |
| Noise / Infrastructure | Router, DEX, aggregator, CEX, bridge, program, or non-human execution path. |
| Needs More Data | Too few events, missing prices, unclear side, missing amount, or ambiguous source coverage. |

Classification should include compact evidence:

- direction counts;
- USD notional if available;
- first/last activity;
- price change during activity window;
- historical repeatability when wallet profile exists.

## 7. Historical Pattern Engine

Future command:

```text
/walletprofile WALLET
```

Purpose: build a historical behavior profile for one wallet across multiple tokens/pairs.

Inputs:

- parsed swaps by wallet;
- maker trades by pair where the wallet appears;
- token/pair price series;
- labels/entities to filter infrastructure;
- token metadata, decimals, and pair migration context.

Metrics:

| Metric | Meaning |
|---|---|
| Distribution cases | Number of tokens where wallet mostly sold into a window. |
| Accumulation cases | Number of tokens where wallet mostly bought into a window. |
| Average sell-window price change | Average price change from first to last visible sell event. |
| Average post-entry movement | Average max price movement after first meaningful buy. |
| Success/repeatability score | How often the wallet's pattern was followed by a meaningful later move. |

Constraints:

- Do not calculate exact PnL without reliable amounts, position tracking, and price at each trade.
- Prefer pattern quality over one-off wins.
- Separate infrastructure from candidate wallets before scoring.

## 8. Token Investigation Engine

Future commands:

```text
/investigate TOKEN
/investigate PAIR
```

Purpose: investigate a live token/pair by finding active makers/wallets, classifying their current behavior, and comparing that behavior with historical profiles.

Flow:

1. Resolve token to active pair(s).
2. Pull active makers/traders for the pair.
3. Filter infrastructure and noisy entities.
4. Classify current maker behavior:
   - accumulation;
   - distribution;
   - round-trip;
   - active trading;
   - needs more data.
5. Load or build historical wallet profiles.
6. Produce a hypothesis.

Hypothesis labels:

| Label | Meaning |
|---|---|
| Entry Watch | Candidate wallets are accumulating and have useful historical post-entry behavior. |
| Distribution Watch | Candidate wallets are selling, but price action context is not yet clearly adverse. |
| Exit Risk | Historically relevant sellers are distributing into weakness or after a sharp move. |
| Noise | Activity is mostly infrastructure, bots, or weak evidence. |
| Needs More Data | Source coverage, amount, price, or identity is insufficient. |

The report should explain evidence briefly and avoid repeating full summaries from lower-level commands.

## 9. Next Immediate Step

Next document:

```text
docs/MAKER_TRADES_SOURCE_RESEARCH.md
```

MVP research questions:

1. Which source can return Solana DEX trades by `pair + maker`?
2. Does it expose side, timestamp, price, token amount, USD value, and txHash?
3. Can it reproduce Dexscreener maker-table rows for known examples?
4. What are the cost, rate limits, and required API keys?
5. What is the minimum safe manual command shape for `/makertrades`?

Recommended MVP path:

1. Research Bitquery pair+maker DEX trades first.
2. Check whether Solscan Pro has pair-level or token-level maker filters.
3. Check Birdeye for pair trade endpoints with maker/owner filters.
4. Treat Dexscreener public API as a pair discovery and price context source unless maker transactions are officially exposed.

## 10. Guardrails

RAB9 Alpha Engine must keep these constraints:

- No auto trading.
- No buy/sell advice.
- No background deep scans.
- Manual diagnostics only for expensive lookups.
- Avoid API burn with strict limits, paging caps, and delays.
- No duplicated report sections.
- Concise reports.
- Clear source and data-quality notes.
- No exact PnL unless amounts, decimals, position tracking, and price source are all reliable.
- Infrastructure must be filtered before smart-wallet conclusions.

## Nearest Tasks

1. Create `docs/MAKER_TRADES_SOURCE_RESEARCH.md`.
2. Validate one source against a Dexscreener maker-table example.
3. Design `/makertrades PAIR MAKER 50` report contract.
4. Implement `/makertrades` as a manual diagnostic only.
5. Feed maker-trade evidence into future `/walletprofile`.
6. Use wallet profiles inside future `/investigate TOKEN` or `/investigate PAIR`.
