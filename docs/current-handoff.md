# RAB9 current handoff

Concise state snapshot for MSF integration work. Entry point: `rab9_bot.py` (Telegram polling + MSF HTTP).

---

## MSF → RAB9 pipeline (live)

| Trigger | Path |
|---------|------|
| n8n / external | `POST /msf-signal` → `msf_http.py` (header `X-RAB9-SECRET`, `chain=solana`) |
| Telegram manual | `/testsignal ADDRESS` |
| Telegram one-liner | `RAB9_SIGNAL solana ADDRESS` in group |

All call `build_msf_signal_analysis_text(address)` → `split_text` (~3800 chars) → `TELEGRAM_GROUP_ID`.

**Not used in MSF path:** Arkham, legacy token watchlist alerts, full `/pairresolve` / `/pairmakers` diagnostic dumps.

**Env:** `TELEGRAM_*`, `BIRDEYE_API_KEY`, `RAB9_HTTP_SECRET` (+ optional `RAB9_HTTP_HOST`/`PORT`). Dexscreener uses default public URL.

**HTTP timeout:** MSF handler waits up to **90s** for analysis (`msf_http.py`).

---

## `msf_analysis.py` behavior (now)

1. **`choose_best_pair(address)`** — Birdeye market first, else Dexscreener #1 pair; merge Dex liq/vol onto Birdeye row when matched. No regex parse of full `/pairresolve` text.
2. **Unresolved** — compact message + source statuses; no pairmakers.
3. **Resolved** — `get_birdeye_pair_makers(pair, mode="normal")` (1 page, ≤50 raw trades).
4. **`summarize_pair_makers`** → behavior buckets + top 5 makers.
5. **`build_analyst_verdict`** — rule-based State / Why bullets / Meaning / Risk / Next check.
6. **Report sections:** Token, Quote, Input, Pair, Dex, Liq, Vol24h → Analyst verdict → Pairmakers stats → Behavior buckets → Top 5 → footer.

**Verdict states:** Needs more data, Weak/Noisy, Accumulation, Distribution, Mixed/Choppy.

**Verdict gates (normal scan):** `raw_trades < 15` or `unique_makers < 2` → Needs more data; `weak_ratio > 0.60` → Weak/Noisy; else buy/sell-heavy counts decide direction.

**Not implemented yet:** spiral scan, dust filter, deep/deep50 auto-escalation.

---

## Last completed features

- **Compact MSF report** — single structured message; no appended full Pair Resolve / Pair Makers diagnostics.
- **Clean Token / Quote** — `symbol_from_label()` strips `SYMBOL/mint` from pair_sources labels → `Token: HEDGY`, `Quote: SOL`.
- **Analyst verdict wording** — multi-bullet Why, plain Meaning, Risk list, Next check command; human-readable balance / weak / concentration lines.

Related docs: `docs/project-state.md`, `docs/transfer-linking-research.md`.

---

## Next planned tasks (MSF only, `msf_analysis.py`)

1. **Spiral scan normal → deep** — escalate pairmakers until verdict clear or cap; **no deep50 auto** (90s / API budget).
2. **MSF-only dust filter** — ignore trades with known `usd_value` below ~$10 before verdict; **keep trades when USD is n/a**; do not change `/pairmakers` output.

Design notes reviewed in chat; not in code yet.

---

## Deployment checklist

```bash
cd /opt/rab9-crypto-bot   # or project root

# 1. Syntax
venv/bin/python -m py_compile *.py

# 2. Import smoke
venv/bin/python -c "import handlers, msf_analysis, msf_http, rab9_bot; print('ok')"

# 3. Restart (service name varies by deploy: rab9 or rab9-crypto)
sudo systemctl restart rab9
sudo systemctl status rab9 --no-pager

# 4. Logs (optional)
journalctl -u rab9 -f
```

**Post-deploy verify (Telegram group):**

```
/testsignal <SOLANA_TOKEN_OR_PAIR_ADDRESS>
```

Expect: `MSF Signal Analysis`, Token/Quote lines, Analyst verdict, Pairmakers (normal), top 5 makers, no PnL/advice beyond footer disclaimer.

**Optional HTTP smoke (if secret configured):**

```bash
curl -s -X POST http://127.0.0.1:8089/msf-signal \
  -H "Content-Type: application/json" \
  -H "X-RAB9-SECRET: $RAB9_HTTP_SECRET" \
  -d '{"chain":"solana","address":"<ADDRESS>"}'
```

---

## Constraints (do not break)

- **No Arkham** in MSF pipeline.
- **No legacy watchlist** coupling to MSF signals.
- **Do not change** `/pairresolve` or `/pairmakers` command output (`pair_sources.py`, `build_pair_makers_text`).
- **Keep MSF report compact** — one primary message; avoid re-attaching full diagnostics.
- **No PnL, no trading advice** in MSF reports.
- **Production spiral cap (when built):** normal → deep only; deep50 manual/experimental only.

---

## Key files

| File | Role |
|------|------|
| `msf_analysis.py` | MSF report + verdict |
| `msf_http.py` | `/msf-signal` endpoint |
| `handlers.py` | `/testsignal`, `RAB9_SIGNAL` |
| `pair_sources.py` | Pair resolve data (read-only for MSF) |
| `maker_sources.py` | Pairmakers fetch (read-only for MSF) |
| `address_validation.py` | MSF Solana address rules |
| `rab9_bot.py` | App entry + MSF HTTP thread start |
