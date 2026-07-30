# RAB9 — Хронология

## 2026-07-28 — T-182 GMGN OpenAPI cutover (read-only)

- **13:15** — `gmgn_client.py` переписан с scrape `gmgn.ai/defi/quotation` → **official `gmgn-cli` OpenAPI**.
- Enrichment: `token info` + `security` + `holders` → score 0–15 + security/tags для Grok.
- `msf_analysis.py`: `enrich_token()`, Grok block `GMGN OPENAPI (read-only)`, source tag `gmgn-openapi`.
- Trading **disabled** (API key Enable Trading=OFF). Swap не вызывается.
- Self-test BURNIE: score **10/15 strong**, holders=10251, top10=18.1%, renounced mint/freeze, locked.
- `gmgn-cli` path: `/home/hermes-workspace/.hermes/node/bin/gmgn-cli`, conf `~/.config/gmgn/.env`.
- RAB9 restarted: `rab9-crypto-hermes` active, `:8089/health` 200.

## 2026-07-28 — T-182 layer2: track SM/KOL + wallet-score

- **13:30** — `track_token_flow()` + `wallet_stats_score()` / `score_wallets()` in `gmgn_client.py`.
- `wallet_intel.cross_reference_makers(..., gmgn_wallet_scores=)` — SUPPLEMENT only, cabal P≥80% intact.
- `msf_analysis`: GMGN TRACK + WALLET-SCORE in Grok; source tags `gmgn-track`, `gmgn-wallet`.
- Self-test: SM wallet score 97/100 HIGH; track on live mint Smugs → distribution (26 SM hits).
- Trading still disabled. RAB9 restart OK, health 200.


## 2026-07-28 — Report quality fix (BURNIE path)

- Safe `.env` key parsers (meme_score/cabal/chart/onchain/creator/loop_verifier) — no crash on commented Birdeye.
- `meme_score.fetch_market`: mint fallback via DexScreener tokens endpoint.
- Summary report always shows: Score line + GMGN block + Track + wallet intel (no empty makers spam).
- Dedupe: junk Score 0 ignored; re-hit shows useful recap (name/MC/GMGN/verdict).
- Self-test BURNIE: Score **96/115 HIGH CONVICTION**, GMGN 10/15, clean structure; rehit recap OK.
- RAB9 restarted, health 200.


## 25.07.2026 — Profile memory created (Operator Watch)

- **15:50** — RAB9 profile memory created: `MEMORY.md` + `USER.md` в `~/.hermes/profiles/rab9/memories/`. Причина: Operator Watch обнаружил пустые memory-файлы профиля RAB9.
- No direct code changes today.

## 2026-07-24

- CONTEXT GATE (rule #0) added to `AGENTS.md`
- No direct code changes today

## 2026-07-20 — T-134 auto-sol study: 7 P0+P1 improvements

Имплементированы улучшения MSF-сигнального пайплайна по мотивам auto-sol (@0xrichboy, errnex/auto-sol).

### P0 (5 шт.)
1. **RugCheck gate** (`rugcheck_client.py`) — проверка rugcheck.xyz перед AI-анализом. Level=high/rugged → force AVOID.
2. **Score header** — детерминированная строка `Score X/115 TIER | liq=… vol=… risk=…` над AI-прозой. AI не может менять скор.
3. **Template fallback** (`msf_template.py`) — структурированная карта без LLM, когда Grok+DeepSeek недоступны.
4. **sourceTags** — provenance-строка в каждом сигнале (msf-telegram, dexscreener, rugcheck, gmgn, etc.)
5. **24h address dedupe** (`msf_dedupe.py`) — JSON `/data/msf_dedupe.json`. Повторный пинг → "already analyzed Xh ago".

### P1 (2 шт.)
6. **GMGN smart-money** (`gmgn_client.py`) — обогащение через GMGN rank endpoint. 403/empty → silent skip.
7. **Hard liq/MC pre-filter** — если liq < $20K или MC > $50M → skip. Настраивается через `MIN_LIQUIDITY_USD`, `MAX_MARKET_CAP_USD`.

### Изменённые файлы
- `meme_score.py` — новый pillar `score_whale()` (0-15 pts), GMGN+RugCheck входы, max=115, новые tier-пороги
- `msf_analysis.py` — интеграция всех 7 улучшений в `build_compact_analysis_text`
- `config.py` — новые env vars

### Новые файлы
- `rugcheck_client.py`
- `gmgn_client.py`
- `msf_dedupe.py`
- `msf_template.py`

## 2026-07-17 05:10 — Birdeye исключён из пайплайна

API key suspended. Код уже был устойчив — `safe_get` глотает ошибки, DexScreener подхватывает. Изменения:
- `.env`: ключ закомментирован
- `AGENTS.md`: Birdeye убран из описания пайплайна
- Все `get_birdeye_*()` возвращают пустые результаты при отсутствии ключа — пайплайн не падает

### Контекст
Hy3 free tier на OpenRouter истекает 20.07.2026 (через 5 дней). Простейший путь: переключить `RAB9_LLM=grok`.

### Изменения
1. **xAI API key** — восстановлен из hermes-vault (был отредактирован vault bootstrap). Policy обновлена: rab9-агенту добавлен доступ к xai.
2. **.env**: `RAB9_LLM=hy3 → grok`, `XAI_API_KEY` восстановлен.
3. **Service restart** — `systemctl restart rab9-crypto-hermes`, active, :8089 health 200.
4. **Тест-сигнал** — обработан (unsupported_chain на SOL-адрес — ожидаемо).

### Текущее состояние

| Компонент | Статус |
|-----------|--------|
| RAB9 Core | 🟢 active, Grok backend |
| MSF HTTP | 🟢 :8089, 200 |
| MSF Listener | 🟢 PID 10199 |
| LLM | 🟢 Grok (xAI API, $0.30/1M) |
| Hy3 | ⏳ работает до 20.07, fallback доступен |

### Стоимость
Hy3: $0 → Grok: $0.30/1M токенов. При текущем объёме сигналов — копейки.

## 2026-07-14 — Agent-Driven Development Rules

AGENTS.md: добавлены 8 правил делегирования в Codex CLI / Grok Build (build plan, security gate, verification ladder). Методика Tony Simons (wp-chatgpt-publisher). Skill: `codex-grok-delegation`.

## 2026-07-07 — Hy3 295B как основной LLM

### Контекст
Из закладок X: @NousResearch анонсировал Hy3 — бесплатный 295B MoE на Nous Portal. Проверен на OpenRouter (`tencent/hy3:free`). Показал лучший анализ чем Grok-3-mini: структурнее, конкретные цифры (Liq/MC%, Vol/MC%), 256K контекст.

### Изменения

**1. `token_intel.py` — добавлен `ask_hy3()`**
- OpenRouter API, free tier, 256K контекст
- `ask_llm()` — диспетчер: `RAB9_LLM=hy3|grok` из `.env`
- Hy3 по умолчанию, Grok как fallback

**2. Сравнение Hy3 vs Grok на $ANSEM**
- Hy3: структура с эмодзи, Liq/MC 1%, Vol/MC 4.3%, «обвал 30-50%», actionable-вердикт
- Grok: короче (200 vs 465 токенов), общие формулировки, менее конкретный
- Hy3 — $0 (free tier) vs Grok $0.30/1M

**3. RAB9 перезапущен с Hy3**
- `.env`: `RAB9_LLM=hy3`, `OPENROUTER_API_KEY=sk-or-...`
- Тест на $ANSEM: CABAL_EXPLOSION, VERIFIER PASS 100
- systemctl restart успешен

**4. AGENTS.md обновлён**
- LLM Backend: таблица Hy3 vs Grok
- Поток сигналов: Grok → Hy3

### Не сделано
- Hy3 free tier может закончиться (2 недели с 06.07). Нужен мониторинг.

### Контекст
n8n-вебхук перестал передавать сигналы из Мемов в RAB9. Порт 8089 снаружи доступен (200 OK), но POST-запросы от n8n не доходят. Пользователь потребовал исключить n8n и настроить прямую событийную модель.

### Изменения

**1. Удалён n8n из цепочки сигналов**
- Старая цепочка: Мемы → @msf_rab_bot → n8n → HTTP :8089 → RAB9
- Новая цепочка: Мемы → @msf_rab_bot → msf_listener.py → HTTP :8089 → RAB9

**2. Создан `msf_listener.py`** (`/home/hermes-workspace/rab9/msf_listener.py`)
- Событийная модель: long-poll Telegram API (getUpdates, timeout=30s)
- Триггеры: DexScreener-ссылка ИЛИ сырой Solana-адрес (44 символа base58)
- Форвард: POST на `localhost:8089/msf-signal` с заголовком `X-RAB9-SECRET`
- PID: 1770538 (background, нужно перевести в systemd)

**3. Обновлён `msf_poller.py`** (`/home/hermes-workspace/.hermes/scripts/msf_poller.py`)
- Секрет читается из `.env`, а не из `/proc/<pid>/environ`

**4. Обновлён `AGENTS.md`**
- Архитектура v2: два бота (@msf_rab_bot + @rab2610bot), полный поток сигналов
- Правила строительства v1: 8 правил (инфра-верификация, pre-deploy, cabal, wallet intel, откат, баги, self-test)
- Инфраструктурная верификация: добавлена проверка MSF Listener

**5. Канбан-доска crypto**
- Задача `t_b65deaac`: «Починить n8n-вебхук MSF: сигналы не доходят до RAB9 (:8089)»
- Статус: ready (n8n заменён на msf_listener.py, ожидает реальной проверки)

**6. Бекапы** (`/home/hermes-workspace/rab9/backups/0707_1747/`)
- AGENTS.md.bak, msf_listener.py.bak, msf_token.txt.bak, .env.bak

### Текущее состояние

| Компонент | Статус | PID |
|-----------|--------|-----|
| RAB9 Core (rab9_bot.py) | ✅ systemd | 1768139 |
| MSF HTTP (:8089) | ✅ 200 OK | внутри RAB9 |
| MSF Listener | ✅ background | 1770538 |
| Telegram (@rab2610bot) | ✅ polling | внутри RAB9 |
| Telegram (@msf_rab_bot) | ✅ слушает Мемы | внешний |
| Кабал-детектор | ✅ готов | — |
| Wallet Intel | ✅ 8 KABAL + 42 susp | — |

### Ожидание
Реальная проверка: когда кто-то кинет DexScreener-ссылку в Мемы → сигнал должен дойти до RAB9 и появиться в Песочнице.

### Не сделано
- MSF Listener не под systemd — при ребуте сервера упадёт
- BUGS.md не создан
- CHRONOLOGY.md создан задним числом (начиная с 07.07.2026)

---

## 2026-07-05 — Создание кабал-детектора

- `cabal_detector.py`: детекция PUMPFUN_WHALE_AIRDROP, KOL_ACTIVATION, CABAL_EXPLOSION, FLYWHEEL_ACTIVE
- `kol_wallets.json`: база кошельков KOL (Ansem + будет пополняться)
- Интеграция в MSF-пайплайн: перед каждым анализом → кабал-чек → алерт
- Паттерны $ANSEM сохранены в `data/cabal_pattern_ansem.md`

## 2026-07-22 — AutoHedge радиолокационная находка + проект idle

- **12:00** — X Hotspot Radar: обнаружен AutoHedge (@cyrilXBT) — open-source 4-agent Solana hedge fund (Director/Quant/Risk/Execution) + Orbit (KOL-tracking для ранних мемкоин-сигналов). → T-158: интеграция в RAB9 scoring/execution.
- **22-23.07** — Проект idle. MSF Listener жив, сигналов в канале нет. Git clean (Daily Audit 23.07). Hy3 free tier истекает — Grok как основной LLM.

## 2026-07-21 — Hy3 LLM миграция + Birdeye fallback

- **05:10** — Hy3 free tier на OpenRouter истекает 20.07.2026. xAI API key восстановлен из hermes-vault. RAB9_LLM переключён на grok как основной провайдер.

## 2026-06-20 — Миграция RAB9 на hermes-user

- Перенос с `/root/rab9/` → `/home/hermes-workspace/rab9/`
- Сервис `rab9-crypto-hermes.service`
- Три новых модуля: `trade_db.py`, `pair_trade_collector.py`, `pair_trade_analyzer.py`
- 190 226 сделок в базе, 22 токена
- Создан `wallet_intel.py`: кросс-референс 1354 кошельков
- Интеграция wallet intelligence в `msf_analysis.py`
- GitHub синхронизирован: `Gromykoss/rab9-crypto-bot`
- **25.07.2026 23:06** — chronology: auto-update 25.07.2026 (`ae899ce`)
- **26.07.2026 04:12** — chore: auto-sync 26.07 (`dcbfd16`)
- **26.07.2026 23:25** — CHRONOLOGY agent: idle day. 0 MSF-сигналов. Telegram NetworkError (Bad Gateway) в 01:10 — transient, самовосстановился. Health-чеки стабильны (:8089 200). MSF Listener PID 1166144 жив. Без изменений кода.
- **27.07.2026 04:07** — chore: auto-sync 27.07 (`9ed8b81`)
- **27.07.2026 04:08** — chore: auto-sync CHRONOLOGY 27.07 (`946aedf`)
- **27.07.2026 04:08** — chore: CHRONOLOGY final 27.07 (`0d2e5b1`)
- **27.07.2026 04:25** — smoke test (`de127c5`)
- **27.07.2026 23:30** — CHRONOLOGY agent: idle day. 1 токен (`6rgcQxmntX19GsUdcf79EQZVgkmDdBCiy4crPoCEFRZs`), 2 анализа (VERIFIER PASS 100 оба). Инфраструктура стабильна: RAB9 Core active (PID 3164401, 6d uptime), MSF HTTP :8089 200, MSF Listener PID 1166144 жив. 0 ошибок в логах.
- **28.07.2026 04:04** — chore: auto-sync 28.07 (`dd5b260`)
- **28.07.2026 23:30** — CHRONOLOGY agent: day summary. 3 токена, 8 анализов (включая 6× `CGEDT9Q...` BURNIE). 6 CABAL_EXPLOSION алертов. 2 ошибки `meme_score` list index out of range (09:49, 13:27 — self-healed). Telegram NetworkError 01:11 (10 ошибок, transient, самовосстановился). RAB9 перезапущен в 13:49 (PID 1983572). BURNIE: 96/115 СИЛЬНЫЙ, GMGN 10/15, 10257 держателей. Инфраструктура стабильна.
- **29.07.2026 04:07** — chore: auto-sync 29.07 (`f6ee381`)
- **29.07.2026 12:59** — MSF Listener перезапущен (новый PID 2365196). Причина: watchdog или ручной рестарт.
- **29.07.2026 23:30** — CHRONOLOGY agent: idle day. 0 MSF-сигналов за весь день — только health-check'и :8089 каждые 15 мин. Инфраструктура стабильна: RAB9 Core active (PID 1983572, 1d+ uptime), MSF HTTP :8089 200, MSF Listener PID 2365196 жив. dedupe: только BURNIE (96/115). Контекст за день: удаление opencodex из всех профилей (включая rab9), перевод rab9 на DeepSeek. X API credits на нуле — BURNIE sentiment tracker не обновляется. GMGN OpenAPI read-only, trading disabled.
