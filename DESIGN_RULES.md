# RAB9 — Design Rules (v1, 17.07.2026)

Inspired by HOODRADAR's design rules. These are the non-negotiable principles this codebase follows.

## 1. Research only — no autotrade

RAB9 analyzes signals. It never sends transactions, holds no private keys, places no orders.
Every module that touches chain data must make this visible.

## 2. Empty is OK

No setups? No matches? "Not found"?
→ Valid output. Not an error. Not a bug. Not something to fix.

A null result is data. Treat it as such.

## 3. Full addresses always

Contract addresses are never shortened in analysis output.
`0x7aD...` → rejected. `0x7aD3c8Fb9E2d41A6B0C5eF8D9A1b2C3d4E5f6A7B` → correct.

## 4. Honeypots dropped, never hyped

If security check fails → DROP with reason.
Never include unsafe tokens as "maybe" or "DYOR-flagged."

## 5. High-PnL ≠ KOL unless tagged

Wallet tracking shows PnL. It does not show influence.
KOL labeling requires separate verification.

## 6. Cabal detection runs first

Every signal → `cabal_detector.analyze()` → before any enrichment or analysis.
CABAL_EXPLOSION? → alert immediately.

## 7. Maker ≠ Checker

Grok proposes. DeepSeek verifies.
Single-model answers are drafts. Consensus answers are signals.

## 8. DexScreener is the source of truth

Birdeye removed 17.07.2026 (API suspended).
DexScreener + `safe_get()` = enough.

## 9. Cron-friendly silence

Scheduled scans produce output only when they have something to say.
"wakeAgent" pattern: notify on hits, sleep on empty.

## 10. Telegram is the delivery layer

All signals → `-1003979753733` (Sandbox).
No other output channels without explicit approval.
