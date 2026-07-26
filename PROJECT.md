# RAB9 — PROJECT.md

## Что это

Крипто-сигналы на базе AI-анализа. Пайплайн: мемы в Telegram → обнаружение токенов → обогащение через DexScreener → анализ через Grok → верификация через MoA (Mixture of Agents) → сигнал в Песочницу. Два Telegram-бота.

## Зачем / как возникла идея

В крипто-трейдинге сигналы часто приходят из Telegram-мемов раньше чем из традиционных источников. MSF (Memecoin Super Feed) — канал где шерится информация о новых токенах. Нужен был инструмент, который:
1. Мониторит мемы 24/7 (msf_listener)
2. Обогащает сырые адреса данными DexScreener
3. Анализирует через Grok (тренды X, ончейн)
4. Проверяет через MoA (два AI должны согласиться)
5. Отсеивает кабальные токены и скамы

## Возможности

- Мониторинг Telegram-мемов 24/7 через @msf_rab_bot
- Обогащение через DexScreener (market cap, ликвидность, холдеры)
- Cabal Detector — обнаружение KOL-пампов и кабальных токенов
- Wallet Intelligence — cross-reference кошельков мейкеров с KABAL (P≥80%)
- Grok-анализ: тренды X, мемкоин-радар, narrative detection
- MoA-верификация: Grok (reference) + DeepSeek (aggregator) — оба PASS → сигнал
- Loop verifier: PASS/FLAG/REJECT. REJECT default
- 5 enrichment модулей: radar_x, radar_gh, chart, onchain, meme_score (100 баллов)
- Сигналы в Песочницу (-1003979753733)
- BURNIE: 80/100 SOLID (эталонный мемкоин)

## Техстек

- **Язык:** Python
- **Боты:** @msf_rab_bot (слушатель Мемов), @rab2610bot (аналитика + доставка)
- **Systemd:** rab9-crypto-hermes (rab9_bot.py), msf_listener.py
- **LLM:** Grok (grok-3-mini, $0.30/1M) — основной. DeepSeek (OpenRouter) — fallback + MoA-агрегатор
- **API:** DexScreener (единственный источник обогащения, Birdeye исключён 17.07.2026)
- **БД:** SQLite (rab9_trades.db)
- **Верификация:** MoA deepseek-xai preset, REJECT default

## Текущая стадия

Idle с 20.07.2026. MSF Listener жив, но сигналов в канале нет. BURNIE sentiment tracker работает (дважды в день). Последнее активное изменение кода: T-134 auto-sol study. Профильная память создана 25.07.

## Ключевые решения и компромиссы

- **Мемы как источник сигналов** — нестандартно, но мемы часто опережают традиционные источники
- **DexScreener без Birdeye** — Birdeye API отозван 17.07, DexScreener остался единственным
- **MoA с REJECT default** — консервативно: оба AI должны согласиться. Лучше пропустить чем false positive
- **Только Песочница** — сигналы не в прод, только в тестовый канал. Без approval gate.
- **Loop brakes:** max 3 enrichment-модуля, 2 FLAG подряд → REJECT, MC > 5M → эскалация человеку
