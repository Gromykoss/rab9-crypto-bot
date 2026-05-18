# Transfer Linking Research

Engineering notes for detecting linked wallets and coordinated activity in RAB9. Complements `docs/project-state.md` and `docs/ALPHA_ENGINE_ROADMAP.md`. Describes practical approaches only; no implementation in this document.

**Scope:** Solana-first, token-scoped, manual Telegram diagnostics. Not a global on-chain analytics platform.

---

## Problem statement

RAB9 already supports:

- **Trade plane:** pair + maker via Birdeye (`/makertrades`, `/makerfind`, `/pairmakers`).
- **Transfer plane:** wallet + token via Arkham `/transfers` (`/wallettx`, `/wallettrade`).
- **Token discovery plane:** top flow addresses via Arkham (`/tokenflow`).

“Linked wallets” and “coordinated activity” require connecting these planes without treating every pool/router touch as a human cabal. Evidence must stay **token-scoped**, **capped**, and **source-labeled**.

---

## Transfer graph concepts

### Definition (RAB9 context)

A **transfer graph** for investigation `(token, window, seed_wallets)` is a directed multigraph:

- **Nodes:** addresses (wallets, programs, pools, CEX hot wallets when labeled).
- **Edges:** observed movements of the **target token** between nodes, plus optional non-transfer edges from other sources.

### Edge types (do not merge)

| Type | Source (current repo) | Meaning |
|------|------------------------|---------|
| `transfer` | Arkham `GET /transfers?base=&tokens=` | Wallet-centric IN/OUT vs counterparty for token mint |
| `swap` | Solscan `account/defi/activities` or Birdeye `/defi/v3/txs` | Parsed DEX activity; counterparty may be pool/router, not peer wallet |
| `pair_trade` | Birdeye `/defi/txs/pair` | Maker trades on pool address; client-side maker match |
| `flow_rank` | Arkham `/token/top_flow/{chain}/{token}` | Token-level prominence; not a direct wallet-to-wallet transfer |

Reports must state which edge types contributed to a conclusion. A dense maker history on a pair does not prove wallet-to-wallet funding.

### Node metadata

Reuse patterns from `arkham.py` (`/intelligence/address/{address}/all`, `classify_token_flow_address`):

- `arkhamLabel`, `arkhamEntity`, `program`, `isUserAddress`
- Derived class: **infrastructure**, **known entity**, **unknown candidate**, **program / ignore**

### Graph lifetime

For RAB9, graphs are **ephemeral per command** (built in memory, discarded after report). Optional future: JSON investigation snapshot on disk (see `docs/project-state.md`).

---

## 1-hop vs multi-hop analysis

### 1-hop (recommended default)

**1-hop** = edges where one endpoint is the seed wallet and the other is a **counterparty** from transfer IN/OUT (`transfer_counterparty`, `summarize_wallet_transfer_items` in `arkham.py`).

**Pros:**

- Bounded API cost: one wallet × paginated `/transfers` + capped intel lookups on unique CPs.
- Interpretable in Telegram (table of counterparties).
- Aligns with data RAB9 already extracts (`unique_counterparties`, `main_counterparty`).

**Use for:** `/walletlinks TOKEN WALLET` MVP, follow-up on `/wallettx`.

### Multi-hop (defer default)

**Multi-hop** = expand graph to counterparties of counterparties (BFS depth ≥ 2).

**Cons with current APIs:**

- Each hop multiplies Arkham `/transfers` or intel calls.
- CP-of-CP often hits pools, routers, or unlabeled program accounts — low signal.
- No shared index in RAB9 to answer “all wallets that received from X” without N wallet queries.

**When to allow (explicit opt-in only):**

- `deep` flag on a future link command.
- Hard caps: max 3 secondary wallets, max 1 extra hop, max 30 total intel calls.
- Only expand from **unknown candidate** nodes, never from infrastructure-class nodes.

**Rule:** Default depth = 1. Multi-hop is a research mode, not the product default.

---

## Shared counterparty logic

### Definitions

- **Counterparty (CP):** other address on a transfer edge (from `transfer_counterparty`).
- **Shared CP:** same CP address appears in transfer summaries for **two or more seed wallets** for the same token within the analysis window.

### Existing building blocks

` summarize_wallet_transfer_items` already computes:

- `unique_counterparties`
- `main_counterparty` when one CP accounts for >50% of events (≥2 events)

`classify_wallet_trade_behavior` uses **Pool-centric trading pattern** when `main_counterparty_count / total > 0.7` — this is a **single-wallet** hub signal, not coordination.

### Coordination heuristics (token-scoped)

| Signal | Condition | Interpretation |
|--------|-----------|----------------|
| Shared funder | ≥2 seeds have IN from same non-infra CP | Possible common source (wallet or labeled entity) |
| Shared distributor | ≥2 seeds have OUT to same non-infra CP | Possible common exit path or pool |
| Mutual CP | A funds B and B funds A (both directions, same token) | Tight pair; verify not wash via pool |
| Hub CP | One CP dominates IN or OUT for multiple seeds | Often pool/router — check infrastructure class first |

**Requirements:**

- Compare CPs by normalized address string (lowercase).
- Exclude CPs classified as infrastructure/program before counting “shared.”
- Require minimum event count per seed (e.g. ≥2 transfers or ≥1 IN + 1 OUT) to avoid noise.

**Not supported today:** global “all wallets funded by CP X” without querying each wallet or an external graph API.

---

## Accumulation / distribution patterns

### Transfer-based (Arkham plane)

From `transfer_direction` / `summarize_wallet_transfer_items`:

- **Accumulation signal:** token IN dominates; few or no OUTs in returned window.
- **Distribution signal:** token OUT dominates; few or no INs.
- **Active trading:** both IN and OUT; `build_potential_trade_cycles` in `wallettrade` detects IN-led cycles.

Limitations: direction is inferred from `from`/`to` vs wallet; swaps may not appear as clean IN/OUT (`docs/SWAP_SOURCE_RESEARCH.md`).

### Trade-based (Birdeye plane)

From `summarize_maker_trades` / `behavior_hint` in `maker_sources.py`:

- Buy-heavy / sell-heavy / two-sided from normalized swap sides.
- `wallet_profile.py` aggregates cases into roles (e.g. Repeating Distribution Wallet).

### Linking the two planes

| Observation | Transfer plane | Trade plane |
|-------------|----------------|-------------|
| Wallet bought on DEX | May show IN from pool/router CP | Buy-heavy maker trades on pair |
| Wallet received airdrop/transfer | IN from deployer or wallet CP | Few or no pair trades |
| Wallet sold | OUT to pool or wallet | Sell-heavy maker trades |

**Coordinated accumulation (hypothesis):** multiple seed wallets show IN-heavy transfer pattern (or buy-heavy pair trades) in overlapping time window, shared non-infra CP optional.

**Coordinated distribution (hypothesis):** multiple seeds show OUT-heavy pattern or sell-heavy trades, overlapping OUT to same CP or same time band.

Do not label “cabal accumulating” without excluding infrastructure and stating window + source coverage.

---

## Pool / router false positives

### Why they dominate

Solana DEX flows often present as:

- `from` / `to` = pool vault, router, or aggregator program — not the human wallet peer.
- Multiple internal transfers per one user swap (`docs/SWAP_SOURCE_RESEARCH.md`).

Arkham `/transfers` may show **main_counterparty** = pool address → triggers “Pool-centric trading pattern” in `/wallettrade` even when behavior is normal trading.

### Mitigation (already partially in repo)

1. **Term list:** `TOKEN_FLOW_INFRASTRUCTURE_TERMS` in `arkham.py` (jupiter, raydium, meteora, pump, orca, exchange, router, bridge, CEX names, etc.).
2. **Program flag:** `program: true` on chain intel → treat as Program / Ignore.
3. **Entity/label:** known DEX/CEX entity → Infrastructure or Known Entity / Review, not cabal candidate.
4. **Hub rule:** >70% events to one CP → classify as pool-centric **before** shared-CP coordination scoring.

### False positive scenarios

| Scenario | Looks like | Actually |
|----------|------------|----------|
| All trades via one Raydium pool | Shared CP across wallets | Same pool, independent traders |
| Jupiter aggregator | Repeated CP | Router, not coordinator |
| CEX deposit address | Shared OUT CP | Withdrawal rail |
| Bonding curve / pump.fun | High flow rank + pool CP | Launch infra |

**Rule:** Never promote shared-CP alone to coordination; require **multiple non-infra wallet seeds** and **directional pattern alignment**.

---

## Infrastructure wallet filtering

### Pipeline (recommended order)

1. **Arkham intel** per address (`get_address_intelligence_all`) — one call per unique node.
2. **Classify** using same rules as `/tokenflow` (`classify_token_flow_address`):
   - Program → ignore for cluster scoring.
   - Infrastructure terms in label/entity → ignore.
   - Known entity → review only; do not auto-score as cabal.
   - Unknown candidate → eligible for cluster heuristics and `/watchwallet` suggestions.
3. **Transfer-only fallback:** if intel fails, heuristics on raw CP string (known program IDs list maintained separately — not in repo today; avoid ad-hoc expansion without validation).

### Wallets to exclude from “cluster member” set

- Programs (`program: true`).
- Labels/entities matching infrastructure terms.
- Pair/pool address from `/pairresolve` when known.
- SOL mint and token mint addresses themselves.

### Wallets to keep as nodes but not as “co-conspirators”

- Known CEX entities (context: deposit/withdrawal).
- Large market makers (labeled) — document as entity overlap, not cabal.

---

## Timing correlation ideas

RAB9 has timestamps on transfers (`transfer_timestamp`) and trades (`block_unix_time` in maker normalization). Amounts on Arkham transfers are often missing — time is the reliable correlate.

### Practical windows

| Window | Use |
|--------|-----|
| Same block / ±5 min | Strong simultaneity (suspicious or coordinated launch snipe) |
| ±2h | Aligns with `/makerfind around` client window |
| 24h / 7d | Token-scoped campaign; matches `/tokenflow` `timeLast` options |

### Correlation signals (rule-based)

- **Burst IN:** ≥N seeds receive token IN within window W.
- **Burst OUT:** ≥N seeds send OUT within W.
- **Sequential funnel:** Wallet A OUT → CP → Wallet B IN within short lag (1-hop only unless tx hash links events).
- **Trade-transfer alignment:** IN transfer time near buy-side pair trade time for same wallet (requires both planes fetched).

### Limits

- Clock skew and block time granularity unknown per source.
- No statistical test suite in bot — use counts and explicit windows in report text.
- Do not imply causation from correlation alone.

---

## Token-scoped cluster detection

### Definition

A **cluster** (RAB9) = set of **wallet addresses** (non-infra) that share at least one coordination signal for a **single token mint** within a defined time window.

Not a chain-wide entity cluster. Not persistent identity across tokens unless user runs multiple investigations.

### Detection workflow (conceptual)

```
1. Input: TOKEN, optional SEED_WALLETS[], optional WINDOW
2. Seeds := user wallets OR top-K candidates from /tokenflow (K ≤ 5, non-infra)
3. For each seed: fetch transfers (paginated, capped)
4. Build CP sets per seed; enrich top CPs (capped)
5. Compute shared CP, timing bursts, direction mix
6. Optional: pairresolve + pairmakers for trade-plane behavior on same token
7. Score evidence (see below); emit hypothesis + follow-up commands
```

### Overlap with `/tokenflow`

`/tokenflow` answers “who is large on this token.” Cluster detection answers “which of those wallets share transfer structure or timing.” Intersection is high-value: address in top flow **and** shared non-infra CP with another candidate.

### Output labels (align with roadmap)

Use hypothesis language from `docs/ALPHA_ENGINE_ROADMAP.md`: Entry Watch, Distribution Watch, Exit Risk, Noise, Needs More Data — plus link-specific **Coordinated Activity Suspected** when transfer evidence supports it.

Never output “cabal confirmed.”

---

## Why global graph indexing is not suitable yet

| Factor | RAB9 reality |
|--------|----------------|
| Architecture | Single-group Telegram bot; JSON watchlists; no graph DB |
| APIs | No bulk “all transfers for token” in integrated code; per-wallet `/transfers` |
| Cost | Arkham intel ~1 rps sensitive; N wallets × M CPs explodes |
| Data quality | Transfers miss swaps; amounts often absent |
| Product guardrails | No background deep scans; manual diagnostics only |
| Ops | One maintainer codebase; flat Python modules |

A global index (all edges for all tokens) would require continuous ingestion, storage, and deduplication — outside current stack and docs guardrails.

**Incremental path:** per-investigation graphs → optional snapshot JSON → optional CP intel cache. Revisit indexing only if repeated manual investigations on same token justify cache hits.

---

## Realistic Telegram UX constraints

| Constraint | Implication |
|------------|-------------|
| Message limit ~4096 chars; RAB9 chunks ~3800 (`utils.split_text`) | Top 10 CPs, top 5 cluster signals, no raw JSON |
| Manual commands | User triggers cost; no overnight cluster scan |
| Single group | No per-user investigation state unless saved to file |
| Latency | 20 pages × 1.2s delay = 24s+ sleep alone on deep Birdeye; Arkham intel serial |
| No interactive graph UI | Tables, bullets, compact addresses (`compact` helper) |
| Copy-paste follow-ups | Report ends with `/wallet`, `/wallettx`, `/makerfind`, `/walletprofile` hints |

**Report sections (recommended max):**

1. Coverage (sources, limits, empty feeds).
2. Seed wallet link summary (IN/OUT, main CP).
3. Top counterparties table (enriched).
4. Coordination signals (if any).
5. Trade-plane one-liner (if pair resolved).
6. Hypothesis + limitations.

---

## API quota constraints

### Arkham (integrated)

| Call | Typical use per investigation | Risk |
|------|----------------------------------|------|
| `/transfers` | 1–5 pages × seeds | Heavy; offset not wired beyond page 0 today |
| `/intelligence/address/all` | 1 + up to 10–15 CPs | Dominates quota on link reports |
| `/token/top_flow` | 0–1 | Heavy endpoint per docs |
| `/flow/address` | Optional | Not required for linking MVP |

Usage headers tracked (`x-intel-datapoints-*` in `arkham_get`). No global budget manager in code.

### Birdeye

| Call | Use | Risk |
|------|-----|------|
| `/defi/txs/pair` | Maker / link trade context | 429 stops scan; 1.2s inter-page delay |
| `/defi/v3/txs` | Swap fallback | Shallow only for link MVP |

### Solscan

- `account/defi/activities` — optional swap gap-fill; requires `SOLSCAN_API_KEY`.
- Account **transfer** API not integrated.

### Budget template (per manual investigation)

Suggested hard caps for planning (not enforced in code):

| Resource | MVP cap |
|----------|---------|
| Seed wallets | 1 (user) + up to 3 from tokenflow |
| Transfer pages per seed | 2 (100 events max if API allows) |
| Intel lookups | 12 total |
| Birdeye pair pages | 0–5 unless user ran maker command separately |
| Wall time target | < 60s preferred; acknowledge if exceeded |

---

## Recommended evidence scoring model

Lightweight **points + gates**, not ML. Scores are **investigation hints** for Telegram text.

### Gates (must pass before coordination points)

- Token mint valid; at least one seed wallet.
- ≥1 transfer or swap event on transfer/swap plane OR explicit “empty coverage” report.
- CP classified as infrastructure → **excluded** from shared-CP scoring.

### Evidence dimensions

| Dimension | Weight | Notes |
|-----------|--------|-------|
| Shared non-infra CP (≥2 seeds) | +3 | Strongest transfer-plane signal |
| Same-direction burst (≥2 seeds, window W) | +2 | IN burst or OUT burst |
| Tokenflow overlap (≥2 candidates in top 10) | +2 | Discovery only; weak alone |
| Trade-plane alignment (buy-heavy / sell-heavy on same pair) | +2 | Birdeye plane; separate label |
| Mutual IN/OUT between seeds (1-hop) | +3 | Rare; verify not pool |
| Infra-dominated CP | −5 | Pool-centric / program |
| Single seed only | cap score | No cluster claim |
| Empty Arkham transfers, swaps only | cap at “Needs More Data” | Planes disagree |

### Score bands

| Total | Label |
|-------|-------|
| 0–2 | Noise / Insufficient |
| 3–5 | Weak coordination suspected — manual review |
| 6–8 | Coordinated activity suspected — document CPs and times |
| ≥9 | Strong suspicion — still not “confirmed”; recommend multiple commands |

Always attach **dissenting evidence**: empty feeds, pool-centric main CP, 422/429, fallback used.

### Plane agreement bonus

+1 if transfer-plane and trade-plane direction agree for same seed (e.g. IN-heavy transfers and buy-heavy maker trades).

No bonus if only one plane has data.

---

## APIs: what exists vs not integrated

**Use today (factual from repo):**

- Arkham: `/transfers`, `/intelligence/address/.../all`, `/token/top_flow`, `/flow/address`
- Birdeye: pair txs, v3 wallet txs, markets/search, OHLCV
- Solscan: defi activities only

**Not integrated (do not plan as available until wired):**

- Arkham `/swaps`, `/transfers/tx/{hash}`, `/tx/{hash}`
- Solscan account transfer endpoints
- Dexscreener maker transaction API
- Bitquery

Research for new endpoints should follow `docs/SWAP_SOURCE_RESEARCH.md` probe-first pattern before production use.

---

## Implementation planning pointers

| Phase | Deliverable | Depends on |
|-------|-------------|------------|
| A | `/walletlinks TOKEN WALLET` — 1-hop, enriched CPs, coverage matrix | Paginated `/transfers`, new report module |
| B | Token-scoped overlap (`/tokenlinks` or `/tokenflow` appendix) | tokenflow + capped per-candidate transfers |
| C | Thin `/investigate TOKEN` orchestrator | A + `pairresolve` + `pairmakers` |
| D | Snapshot JSON + intel cache | A stable |
| E | Arkham `/swaps` or Solscan transfers probe | Research doc + field tests |

See `docs/project-state.md` § Transfer and cabal-investigation goals.

---

## References

- `docs/project-state.md` — current commands, limits, gaps
- `docs/ALPHA_ENGINE_ROADMAP.md` — mission, `/investigate`, guardrails
- `docs/SWAP_SOURCE_RESEARCH.md` — transfer vs swap gap
- `docs/WALLET_ALPHA_PLAN.md` — counterparty fields, entry/exit research
- `arkham.py` — transfer helpers, infrastructure terms, tokenflow classification
- `maker_sources.py` — pair+makER behavior
- `docs/FIELD_TESTING.md` — command acceptance criteria
