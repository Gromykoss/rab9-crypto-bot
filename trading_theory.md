# Meme Coin Trading Theory

## 1. Meme Coin Lifecycle Patterns

- Stealth accumulation: low volume, no X buzz, MC < 100K, few makers → 🟡 ACCUMULATE (buy small lots)
- First pump: volume spike, X mentions rising, MC 100K-1M, maker count growing → 🟢 BUY (confirmation)
- Distribution: volume declining, X buzz fading, MC 1M-10M, sell-heavy makers → 🔴 SELL / WAIT
- Dead/Revival: volume near zero, no X activity, MC < 100K → 💀 DEAD (skip or cut losses)

## 1a. 4-Phase Trading Signals (phase_detector.py)

| Signal | Chart Phase | Key Triggers | Action |
|---|---|---|---|
| 🟢 **BUY** | accumulation → markup | vol rising, buy_ratio >1.3, kabals ≤2, score ≥50, ATH dd >-70%, sentiment pos, onchain clean | Enter position, confirm with pullback |
| 🟡 **ACCUMULATE** | accumulation | flat_days ≥3, vol stable/rising, buy_ratio ≥0.8, kabals ≤1, score ≥40, creator NOT selling | Buy small lots near support, wait for volume |
| 🔴 **SELL** | distribution → decay | buy_ratio <0.5+kabals OR phase=distribution+falling vol OR ATH dd >-80% OR creator dumped | Exit position / take profits |
| 💀 **DEAD** | decay / dead | vol <$5K, txn <100, MC <$100K, flat >14d, X inactive >7d, <5 makers | Skip entirely. If holding — cut losses. |
| ⏳ **WAIT** | any non-matching | insufficient confirmations for any signal | Monitor, no action |

### Hard Gates (phase must match)
- BUY → chart phase MUST be accumulation or markup
- ACCUMULATE → chart phase MUST be accumulation
- DEAD → priority over all other signals

## 2. Kabal Behaviour Rules

- Kabals BUY-heavy at MC < 100K + early lifecycle = accumulation (BULLISH)
- Kabals BUY-heavy at MC > 1M + late lifecycle = likely exit liquidity trap (BEARISH)
- Kabals SELL-heavy at any MC with buy_ratio < 0.5 = coordinated dump in progress (AVOID)
- 3+ kabals in top-5 = high manipulation risk, even if BUY-heavy
- Single kabal SELL-heavy + 10+ unknown makers BUY-heavy = cabal exiting to retail (BEARISH)

## 3. On-Chain Red Flags (priority ordered)

- Mutable metadata: creator can change token name/symbol -> HIGH RISK
- LP not burned: creator can pull liquidity -> EXTREME RISK
- Top-10 holders > 50% supply: concentrated -> HIGH RISK
- Creator wallet sold > 20% of initial supply -> dump in progress
- Creator wallet held > 7 days with no sells -> conviction signal (BULLISH)
- Low liquidity relative to MC (MC/LP ratio > 20x) -> slippage risk

## 4. Sentiment-to-Price Correlation

- X mentions growing + volume growing + no kabal selling = genuine momentum (BULLISH)
- X mentions growing + volume flat + kabals selling = fake buzz (BEARISH - pump and dump)
- X mentions declining + volume declining = dead token (AVOID)
- 'Influencer shill' pattern: sudden spike in mentions from low-follower accounts = paid promotion (HIGH RISK)
