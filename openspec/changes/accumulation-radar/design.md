# Design: accumulation-radar (из спеки v1.0)

## Архитектура

1. **Поток (pumpportal_listener):** третья подписка `subscribeTokenTrade` keys=[MINT].
   Маршрут: txType-события по BURNIE-минту → append `data/trades_stream.jsonl`
   ({ts, wallet, tx_type, token_amount, sol_amount}) — fsync, без дедупа.
2. **Детектор (analyzer_main):** `accumulation_radar(sink)` — тик каждые 900с:
   читает окно 24ч из trades_stream → признаки (1)-(5) из спеки → при срабатывании
   всех пяти: sink.write("alert", текст-свод) + cooldown-файл data/radar_cooldown.json
   (last_signal_ts; 6ч).
3. Конфиг: RADAR_MIN_BUYERS=5, RADAR_SELL_RATIO=0.25, RADAR_DIP_PCT=-5,
   RADAR_HOLDING_RATIO=0.3, RADAR_COOLDOWN_H=6.

## Потоки

WS-трейд → trades_stream.jsonl → radar-тик (окно 24ч) → признаки → sink(alert) → дайджест.

## Риски

- Объём потока: BURNIE малоликвиден (~сотни сделок/день) — рост файла медленный,
  ротация при >20К строк.
- Ложные срабатывания на дне с последующей продажей — калибровка outcome'ами
  (сигналы пишутся с бейзлайном цены; верификация через verdict_outcomes-механику —
  radar-алерты идут в тот же outcome-цикл как type=alert).
