# RAB9 — Хронология

## 05.09.2026 — CONTRACT INDEX GATE rollout

- **причина** — Spec Drift Gate: введён единый контрактный индекс сессии, но rollout 05.09 не был закрыт датированной записью в CHRONOLOGY.
- **что сделано** — создан `PROJECT_MEMORY_GRAPH.md` (8 доменов: session-contract, telegram-ingest, signal-analysis, safety-gates, llm-verification, delivery-alerts, burnie-monitoring, persistence-config); в `AGENTS.md` после CONTEXT GATE вставлен CONTRACT INDEX GATE 0.5.
- **верификация** — проверены Boot Rule, Global Invariants, Domain Map (8 доменов), Change Routing и Spec Drift Gate; маршрут чтения: граф + AGENTS Gates на старте, остальные доки точечно по графу.
- **файлы** — `PROJECT_MEMORY_GRAPH.md`, `AGENTS.md`, `CHRONOLOGY.md`.

## 04.09.2026 — 39-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **39-й день без сигналов** (27.07–04.09). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 active (27d uptime, с 08.08), MSF Listener PID 2422530 active (13d, с 22.08), MSF HTTP :8089 200 (`ok=true`). Ошибки core за день — 0. Листенер — 7x штатных poll-ошибок (6x long-poll `read operation timed out`, 1x `Connection reset by peer` 20:55, 1x `502 Bad Gateway` 01:10 — transient, стандартное окно обслуживания Telegram). Live DexScreener (BURNIE, пара `5tYFviFW`): price $0.001623, MC $1.57M, liq $245K, vol24 $129K, 24h **−7.06%** (частичный откат после вчерашнего +29%), txns buy/sell 650/686 (ratio 0.95 — смешанно). X API жив (oauth2 whoami 200, не 402). GMGN read-only, trading disabled. Код за день не менялся. Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md (staged), M burnie_price_watch.py, M burnie_sentiment_tracker.py, M chart_analysis.py, M radar_x.py (не закоммичено), ?? briefings/, ?? лог-дампы от 21.08.

## 03.09.2026 — 38-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **38-й день без сигналов** (27.07–03.09). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 active (26d uptime, с 08.08), MSF Listener PID 2422530 active (12d, с 22.08), MSF HTTP :8089 200 (`ok=true`). Ошибки core за день — только ночной `Telegram NetworkError Bad Gateway` 01:10–01:10:56 (2x handler error + traceback, transient, стандартное окно обслуживания Telegram, самовосстановился). Листенер — 5x штатных poll-ошибок (long-poll timeouts/transient). Live DexScreener (BURNIE `CGEDT9QZ…Spump`): price $0.001724, MC $1.67M, liq $255K, vol24 $266.6K, 24h **+29.06%** (заметный разогрев после -1.36% вчера), txns buy/sell 980/1130 (ratio 0.87 — смешанно). X API жив (whoami 200, не 402). GMGN read-only, trading disabled. Код за день не менялся. Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md (staged), M burnie_price_watch.py, M burnie_sentiment_tracker.py, M chart_analysis.py, M radar_x.py (не закоммичено), ?? briefings/, ?? лог-дампы от 21.08.

## 02.09.2026 — 37-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **37-й день без сигналов** (27.07–02.09). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 active (25d uptime, с 08.08), MSF Listener PID 2422530 active (11d, с 22.08), MSF HTTP :8089 200 (`ok=true`). Ошибки core за день — только ночной `Telegram NetworkError Bad Gateway` 01:10 (5x handler error + traceback, transient, стандартное окно обслуживания Telegram, самовосстановился). Листенер — 6x штатных poll-ошибок (5x `read operation timed out`, 1x `Connection reset by peer` 02:12 — transient). Live DexScreener (BURNIE `CGEDT9Q…Spump`): price $0.001333, MC $1.29M, liq $219K, vol24 $83.9K, 24h **−1.36%**, txns buy/sell 134/75 (ratio 1.79 — покупки доминируют). X API жив (whoami 200, не 402). GMGN read-only, trading disabled. Код за день не менялся. Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md (staged), M burnie_price_watch.py, M burnie_sentiment_tracker.py, M chart_analysis.py, M radar_x.py (не закоммичено), ?? briefings/, ?? лог-дампы от 21.08.

## 01.09.2026 — 36-й день без MSF-сигналов

- **09:xx** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **36-й день без сигналов** (27.07–01.09). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 active (24d uptime, с 08.08), MSF Listener PID 2422530 active (10d, с 22.08), MSF HTTP :8089 200 (`ok=true`). Ошибки core за день — только ночной `Telegram NetworkError Bad Gateway` 01:10–01:11 (2x handler error + traceback, transient, стандартное окно обслуживания Telegram, самовосстановился); прочие hits — traceback-строки того же инцидента. Листенер — 0 ошибок (grep посчитал только подсказки journal). Live DexScreener: price $0.001287, MC $1.25M, liq $215K, vol24 $158.7K, 24h **−20.18%**, txns buy/sell 671/887 (ratio 0.76 — продажи доминируют). X API жив (whoami 200, не 402). GMGN read-only, trading disabled. Код за день не менялся. Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md, M burnie_price_watch.py, M burnie_sentiment_tracker.py, M chart_analysis.py, M radar_x.py (не закоммичено), ?? briefings/, ?? лог-дампы от 21.08.

## 31.08.2026 — 35-й день без MSF-сигналов

- **05:51** — RAB9: idle day. 0 MSF-сигналов — **35-й день без сигналов** (27.07–31.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 active (23d uptime, с 08.08), MSF Listener PID 2422530 active (9d, с 22.08), MSF HTTP :8089 200 (`ok=true`, 127.0.0.1). Ошибки core за день — только ночной `Telegram NetworkError Bad Gateway` 01:10 (traceback, transient, стандартное окно Telegram, самовосстановился). Листенер — 1x штатный long-poll timeout. Live DexScreener: price $0.001702, MC $1.65M, liq $250K, vol24 $73.9K, 24h **−1.56%**, txns buy/sell 271/246 (ratio 1.10 — смешанно). X API жив (whoami 200, не 402). GMGN read-only, trading disabled. Код за день не менялся. Обновлены: CHRONOLOGY.md (эта запись) + блок RAB9 в hermes-vault/10_System/Infrastructure Map.md (стадия, BURNIE-эталон 96/115, кроны, катализатор PolitiFi). Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md (staged), M burnie_price_watch.py, M burnie_sentiment_tracker.py, M chart_analysis.py, M radar_x.py (не закоммичено), ?? briefings/, ?? LOG_DUMP_20260821_160833.txt, ?? grok_manipulation_research_20260821_150547.txt, ?? rab9.log.bak-20260821.

## 29.08.2026 — 33-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **33-й день без сигналов** (27.07–29.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (21d uptime, с 08.08), MSF HTTP :8089 200 (`ok=true`, 127.0.0.1), MSF Listener PID 2422530 жив (7d uptime, с 22.08). Ошибки core за день — только ночной `Telegram NetworkError Bad Gateway` 01:10–01:11 (handler error + traceback, transient, стандартное окно обслуживания Telegram, самовосстановился). Листенер — штатный long-poll `read operation timed out` (6x за день). BURNIE price-watch жив, без аномалии цены. Live DexScreener: price $0.001993, MC $1.93M, liq $274K, vol24 $106K, 24h **−0.51%**, txns buy/sell 445/526 (ratio 0.85 — смешанно). X API жив (whoami 200, не 402). GMGN OpenAPI read-only, trading disabled. Код за день не менялся. Рабочее дерево без изменений: M AGENTS.md, M CHRONOLOGY.md (staged), M burnie_price_watch.py, M burnie_sentiment_tracker.py, M chart_analysis.py, M radar_x.py (не закоммичено), ?? LOG_DUMP_20260821_160833.txt, ?? grok_manipulation_research_20260821_150547.txt, ?? rab9.log.bak-20260821, ?? briefings/.

## 28.08.2026 — 32-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **32-й день без сигналов** (27.07–28.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (20d uptime, с 08.08), MSF HTTP :8089 200 (`ok=true`, 127.0.0.1), MSF Listener PID 2422530 жив (6d uptime, с 22.08). Ошибки core за день — 0. Листенер — штатный long-poll `read operation timed out` (~7x) + 1x SSL handshake timeout 03:38 (transient). BURNIE price-watch жив, без аномалии цены. Live DexScreener: price $0.002003, MC $1.94M, liq $273K, vol24 $76.9K, 24h **−16.26%**, txns buy/sell 366/338 (ratio 1.08 — смешанно). X API жив (whoami 200, не 402). GMGN OpenAPI read-only, trading disabled. Код за день не менялся. Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md (staged), M burnie_price_watch.py, M burnie_sentiment_tracker.py, M chart_analysis.py, M radar_x.py (не закоммичено), ?? LOG_DUMP_20260821_160833.txt, ?? grok_manipulation_research_20260821_150547.txt, ?? rab9.log.bak-20260821, ?? briefings/.

## 26.08.2026 — отчёт BURNIE «залипал»: заголовок/вердикт не реагировали на цену

- **причина** — Сергей: «что вверх цена что вниз, отчет один и тот-же?». Разбор кода `format_alert` + `compute_weighted_score` показал 3 дефекта: (1) заголовок `🟢/🔴` считался ТОЛЬКО из сентимента X-постов, цена не участвовала; (2) вес «рынок» в скоре = 10/100, падение цены меняло вердикт на ±9 баллов — незаметно; (3) фаза `разгон` (markup) рисовалась даже при падении -15.8% (противоречие).
- **что сделано** — (A) заголовок теперь считает цену первым: `change_24h < -10%` → «🔴 цена падает (откат/слив)», `> +10%` → «🟢 цена растёт (разогрев)», иначе падает на сентимент. (B) вес «рынок» поднят 10→20 через перераспределение (сентимент 20→15, виральность 20→15), сумма весов = 100, пороги вердикта остались 75/55/35, отображение `({total}/100)`. (C) если `phase == markup` и цена падает >10% — фаза рисуется как «откат после разгона».
- **верификация** — `py_compile` OK; self-test двух сценариев на одном снимке: DOWN -15.8% → `market:2`, total 55, заголовок «🔴 цена падает», TA «фаза: откат после разгона»; UP +20% → `market:20`, total 73, заголовок «🟢 цена растёт». Вердикт реально двигается (Δ18 баллов), сумма весов = 100. Копия `~/.hermes/profiles/rab9/scripts/burnie_sentiment_tracker.py` синхронизирована (md5 совпадает). Cron берёт скрипт из `~/rab9/` (`cd ~/rab9 && python3 burnie_sentiment_tracker.py`), правка рабочая.
- **файлы** — `burnie_sentiment_tracker.py`.
- **откат** — `git checkout -- burnie_sentiment_tracker.py`.

## 25.08.2026 — 30-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **30-й день без сигналов** (27.07–25.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (17d uptime, с 08.08), MSF HTTP :8089 200 (`ok=true`, 127.0.0.1), MSF Listener PID 2422530 жив (3d uptime, с 22.08). Ошибки core — 1x `Telegram handler error` httpx.ConnectError 15:20 (transient, самовосстановился). Листенер — штатный long-poll `read operation timed out` (~9x за день) + 3x SSL handshake timeout (07:58, 09:47, 13:08 — transient). BURNIE price-watch жив: baseline $0.002399, live $0.002426 — без аномалии, тишина. Live DexScreener: price $0.002426, MC $2.35M, liq $290K, vol24 $79.1K, 24h **−3.91%**, txns buy/sell 385/315 (ratio 1.22 — покупки слегка доминируют). dedupe: только BURNIE (96/115 HIGH CONVICTION, GMGN 10/15, verdict ⏳ WAIT | ❓ НЕИЗВЕСТНО). X API жив (whoami 200, не 402). GMGN OpenAPI read-only, trading disabled. Код за день не менялся. Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md (staged), M burnie_price_watch.py, M burnie_sentiment_tracker.py, M chart_analysis.py, M radar_x.py (manipulation research от 21.08 — не закоммичено), ?? LOG_DUMP_20260821_160833.txt, ?? grok_manipulation_research_20260821_150547.txt, ?? rab9.log.bak-20260821, ?? briefings/.

## 24.08.2026 — 29-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **29-й день без сигналов** (27.07–24.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (16d uptime, с 08.08), MSF HTTP :8089 200 (`ok=true`, 127.0.0.1), MSF Listener PID 2422530 жив (2d uptime, с 22.08). Ошибки core — httpx.ReadError 09:08 (transient) + 2x `Telegram handler error` Bad Gateway 19:58 (transient, стандартное окно обслуживания Telegram, самовосстановился). Листенер — штатный long-poll `read operation timed out` (~20x за день) + 2x 502 Bad Gateway 01:13–01:39 (transient, стандартное окно обслуживания Telegram). BURNIE price-watch жив: baseline $0.002522, live $0.002497 — без аномалии, тишина. Live DexScreener: price $0.002497, MC $2.42M, liq $294K, vol24 $62.9K, 24h **+3.52%**, txns buy/sell 301/378 (ratio 0.80 — смешанно). dedupe: только BURNIE (96/115 HIGH CONVICTION, GMGN 10/15, verdict ⏳ WAIT | ❓ НЕИЗВЕСТНО). X API жив (whoami 200, не 402). GMGN OpenAPI read-only, trading disabled. Код за день не менялся. Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md (staged), M burnie_price_watch.py, M burnie_sentiment_tracker.py, M chart_analysis.py, M radar_x.py (manipulation research от 21.08 — не закоммичено), ?? LOG_DUMP_20260821_160833.txt, ?? grok_manipulation_research_20260821_150547.txt, ?? rab9.log.bak-20260821, ?? briefings/.

## 23.08.2026 — 28-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **28-й день без сигналов** (27.07–23.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (15d uptime, с 08.08), MSF HTTP :8089 200 (`ok=true`, 127.0.0.1), MSF Listener PID 2422530 жив (с 22.08). Ошибки core — 0. Листенер — штатный long-poll `read operation timed out` (6x) + 2x SSL handshake timeout (00:35, 00:41) + 2x 502 Bad Gateway 01:11 (transient, стандартное окно обслуживания Telegram, самовосстановился). BURNIE price-watch жив: baseline $0.002415, live $0.002401 — без аномалии, тишина. Live DexScreener: price $0.002401, MC $2.33M, liq $285K, vol24 $276K, 24h **−13.18%**, txns buy/sell 1697/1417 (ratio 1.20 — покупки доминируют). dedupe: только BURNIE (96/115 HIGH CONVICTION, GMGN 10/15, verdict ⏳ WAIT | ❓ НЕИЗВЕСТНО). GMGN OpenAPI read-only, trading disabled. Код за день не менялся. Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md (staged), M burnie_price_watch.py, M burnie_sentiment_tracker.py, M chart_analysis.py, M radar_x.py (manipulation research от 21.08 — не закоммичено), ?? LOG_DUMP_20260821_160833.txt, ?? grok_manipulation_research_20260821_150547.txt, ?? rab9.log.bak-20260821, ?? briefings/.

## 22.08.2026 — 27-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **27-й день без сигналов** (27.07–22.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (14d uptime, с 08.08), MSF HTTP :8089 200 (`ok=true`, 127.0.0.1), MSF Listener PID 2422530 жив (рестартован 08:09 после деплоя 409-фикса). Ошибки core — только ночной `Telegram NetworkError Bad Gateway` 01:10 (6x handler error + traceback, transient, стандартное окно обслуживания Telegram, самовосстановился). Листенер — 1x `Connection reset by peer` 14:11 (transient). BURNIE price-watch жив: baseline $0.002801 (обновлён 23:10), live $0.002769 — без аномалии, тишина. Live DexScreener: price $0.002769, MC $2.69M, vol24 $182K, 24h +7.38%, txns buy/sell 678/974 (ratio 0.70 — смешанно). dedupe: только BURNIE (96/115 HIGH CONVICTION, GMGN 10/15, verdict ⏳ WAIT | ❓ НЕИЗВЕСТНО). GMGN OpenAPI read-only, trading disabled. За день: 409-фикс msf_listener задеплоен (commit `3edd7d0`, listener рестартован), AGENTS.md конденсирован 307→284 + KPI (staged). Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md (staged), M burnie_price_watch.py, M burnie_sentiment_tracker.py, M chart_analysis.py, M radar_x.py (manipulation research от 21.08 — не закоммичено), ?? LOG_DUMP_20260821_160833.txt, ?? grok_manipulation_research_20260821_150547.txt, ?? rab9.log.bak-20260821, ?? briefings/.

## 22.08.2026 — лог-гигиена rab9.log + 409-защита msf_listener (по дампу 21.08)

- **причина** — Сергей выложил `LOG_DUMP_20260821_160833.txt` (593 строки): обе службы живы, но дамп выявил два дефекта гигиены. (1) `rab9.log` = 1850 байт, mod 30.06 — мёртвый файл с июньским traceback `OSError [Errno 98] Address already in use`, не пишется 2 мес (текущий процесс логирует только в journald через stdout). (2) 409-гонка `getUpdates` при рестарте (см. 19.08, 26.07) — защиты на уровне кода не было.
- **что сделано** — (A) `rab9.log` → `rab9.log.bak-20260821` (архив трупа, не удалял). (B) `msf_listener.py`: добавлен import `urllib.error` + в except-блок детект `HTTPError 409` → `log.warning` + `setWebhook` (drop_pending_updates) + sleep 5 с; прочие HTTP-ошибки → `log.error` + sleep 10. Логика сигналов не тронута.
- **верификация** — `py_compile msf_listener.py` OK; `operators.tests.test_operators` 30/30 OK (enforced-слой не задет); dry-детект `HTTPError(409).code == 409` → True. Живых дублёров листенера ровно один (PID 2514283), user-юнит msf disabled (гонка systemd закрыта 19.08) — патч кода = подстраховка на будущий ручной рестарт.
- **файлы** — `msf_listener.py` (изменён), `rab9.log` → `rab9.log.bak-20260821`.
- **откат** — `git checkout -- msf_listener.py`; `mv rab9.log.bak-20260821 rab9.log`.

## 22.08.2026 — конденсация AGENTS.md (307→284) + KPI-блок (аудит MGT_maccha)

- **причина** — недельный аудит MGT_maccha (21.08) записал красную находку: `rab9/AGENTS.md` = 307 строк (>порог 300) и KPI=0 (отсутствуют метрики). Задача: сжать до <300 без потери правил + добавить KPI.
- **что сделано** — rab9 подготовил конденсацию, но его write заблокировал анти-self-modification шлюз (защищённый AGENTS.md требует живого approval человека). Сергей выбрал вариант 3: Hermes применил cross-profile patch.
  - Удалены 5 дублей: `### Data Flow (полный цикл)` (ASCII = дубль Потока сигналов), `### Сервисы (systemd)` (= дубль Компонентов), `## Быстрые команды` (= дубль Инфраструктуры RAB9), дубли self-test/раздельно-с-Алиханом в «Правилах Сергея».
  - Добавлен `## KPI (метрики проекта)` — 5 метрик (сигналы/день, точность верификатора ≥80%, false-positive <15%, аптайм листенера 100%, latency <5 мин).
- **верификация** — `wc -l` = 284 (было 307); `grep CRITICAL GATES` = 2, `grep ENFORCED-ЗАКОНЫ` = 1, операторы check_destination/verifier/mutation/safety на месте; KPI = 1 вхождение (дубль не создан).
- **статус** — файл стабилизирован, откат доступен (`git checkout -- AGENTS.md`).
- **файлы** — `AGENTS.md` (изменён Hermes через cross-profile patch; зона rab9, правка по императиву Сергея).

## 21.08.2026 — внедрение manipulation research в код (buy_ratio, breakout-interest, KOL-swarm)

- **причина** — прикладное применение инструкции Grok по манипуляциям (`grok_manipulation_research_result.md`) в живые модули: выводы §3/§4/§5/§7, проверенные на BURNIE, перенесены в код.
- **что сделано** —
  - `burnie_price_watch.py`: в price-алерт добавлен `buy_ratio` (buy/sell 24h из DexScreener `txns.h24`, бесплатно). ≥1.3 → «покупки доминируют» (подтверждение пробоя покупками), <0.5 → «продажи доминируют ⚠️» (dump), иначе «смешанно». §4.
  - `chart_analysis.py`: новый флаг `smart_money_breakout_interest` — цена выше пробойного уровня при объёме ×1.5–×2.0 → «интерес», но ещё НЕ кандидат (полный breakout остаётся ×2.0). Ниже ×1.5 = шум. §3/§7.
  - `radar_x.py`: `large_mention_count` (аккаунты ≥50k) + warning `⚠️ KOL-SWARM`: ≥2 крупных аккаунтов упомянули в одном снимке без #ad/disclosure → вероятный заказной разогрев (paid shill), НЕ органика. §5.
- **статус** — правки в рабочем дереве, НЕ закоммичены. RAB9 Core не рестартован (enrichment-модули — изменения подхватятся следующим прогоном анализа).
- **файлы** — `burnie_price_watch.py`, `chart_analysis.py`, `radar_x.py`.

## 21.08.2026 — 26-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **26-й день без сигналов** (27.07–21.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (13d 15h uptime, с 08.08), MSF HTTP :8089 200 (`ok=true`, 127.0.0.1), MSF Listener PID 2514283 жив (с 19.08). Core-ошибки — только ночной `Telegram NetworkError Bad Gateway` 01:10 (5x handler error + traceback, transient, стандартное окно обслуживания Telegram, самовосстановился). Листенер — штатный long-poll `read operation timed out` (6x за день). BURNIE price-watch жив: baseline $0.00255, текущая $0.00258 — без аномалии, тишина. Live DexScreener: price $0.00258, MC $2.50M, vol24 $500K, 24h −0.84%. dedupe: только BURNIE (96/115 HIGH CONVICTION, GMGN 10/15, verdict ⏳ WAIT | ❓ НЕИЗВЕСТНО). GMGN OpenAPI read-only, trading disabled. Код: 3 модуля правлены (внедрение manipulation research) — не закоммичено. Рабочее дерево: M CHRONOLOGY.md, M burnie_price_watch.py, M chart_analysis.py, M radar_x.py, ?? LOG_DUMP_20260821_160833.txt, ?? grok_manipulation_research_20260821_150547.txt.

## 21.08.2026 — BURNIE price-watch: крон чаще при аномалии цены + московское время

- ** причина ** — Сергей: крон BURNIE срабатывает 2 раза в сутки; нужно, чтобы при аномалии цены срабатывал чаще. Доп. требование: время переводить на местное автоматически (сейчас московский пояс).
- ** решение Сергея ** — порог аномалии **±20%** за короткое окно (~10 мин); поведение: сначала короткий цена-алерт → полный отчёт только если аномалия подтвердилась (удержалась на следующем тике). Полный трекер переведён с Бишкека (UTC+6) на Москву (UTC+3).
- ** что сделано ** — новый `burnie_price_watch.py` (no_agent, stdlib-only): DexScreener-цена (бесплатно, без X-кредитов) каждые 10 мин; двухфазная логика: (1) |Δ|≥20% → цена-алерт + фиксация `anomaly_ref`; (2) на следующем тике удержалась → запуск полного `burnie_sentiment_tracker.py` + полный отчёт; откатилась → ложная тревога, тишина. State в `~/.hermes/profiles/rab9/scripts/burnie_price_state.json`. Крон `ba5712e3dfa2` (profile rab9, `*/10 * * * *`, deliver local — скрипт self-send). Полный трекер `59d37ee6a323` (default) сдвинут: `0 0,12 * * *` → `0 3,15 * * *` (06:00/18:00 МСК).
- ** верификация ** — self-test трёх сценариев (baseline→тишина / скачок→алерт / удержание→полный отчёт) зелёный; live DexScreener ok (price $0.002228, MC $2.16M); реальный запуск из cron-dir: exit 0, baseline записан, тишина.
- ** файлы ** — `burnie_price_watch.py` (новый, + копия в scripts/).

## 21.08.2026 — фикс бага «пробой не ловился» (chart_analysis breakout) + апгрейд BURNIE-отчёта

- ** причина ** — Grok прошёл по `chart_analysis.py` (строки 646–712) и нашёл: breakout-детектор не ловит пробой, два из четырёх статусов (`candidate`, `confirmed`) — мёртвый код. Корень: `_support_resistance` кладёт в `resistance` только свинг-хаи `price > current` (строка 128), поэтому `current > resistance` всегда False, `above[n-1]` всегда False. Параллельный баг — в трекере `detect_warmup` (строка 2136 `price > resistance`) с тем же эффектом.
- ** что сделано ** — в `chart_analysis.py`: пробойный уровень теперь берётся как ближайший свинг-хай по МОДУЛЮ расстояния (`_breakout_res_price = min(swings["highs"], key=abs(p-current))`) — верх коридора, НЕ ATH (manipulation research §3). Он может быть НИЖЕ текущей цены → `candidate`/`confirmed` ожили. В `burnie_sentiment_tracker.py`: `fetch_chart_ta` тянет `breakout_status`/`smart_money_breakout`/`breakout_volume_ratio`/`breakout_resistance`/`rel_vol_14d`; `detect_warmup` переписан с мёртвого `price > resistance` на реальный `breakout_status`; `format_alert` показывает пробой в строке TA.
- ** верификация ** — `py_compile` чисто. Live: BURNIE price 0.002229, `breakout_status=confirmed`, `smart_money_breakout=True`, `breakout_volume_ratio=4.96`, `phase=markup high`. `detect_warmup` выдаёт «пробой сопротивления ПОДТВЕРЖДЁН (уровень $0.002074), объём ×5.0». Dry-run всего трекера — та же картина.
- ** файлы ** — `chart_analysis.py`, `burnie_sentiment_tracker.py`.

## 21.08.2026 — Grok Build: инструкция по манипуляциям перезапущена и сохранена

- ** причина ** — Сергей обнаружил: вывод Grok Build по манипуляциям мемкоинами пропал. Сохранились только промпты (`grok_research_prompt.txt` 07:34, `birdeye_eval_prompt.txt` 08:03), а сама инструкция (накопление → пробой → памп → раздача, ложный vs настоящий пробой) — ни в файлах, ни в CHRONOLOGY, ни в логах делегирования. Похоже, первый прогон не довели до конца или не записали вывод.
- ** что сделано ** — Grok Build перезапущен заново с готовым промптом `grok_research_prompt.txt` (`grok -p "$(cat grok_research_prompt.txt)" --output-format plain`), вывод сразу писался в файл. Завершился с кодом 0, stderr пуст.
- ** результат ** — `grok_manipulation_research_result.md` (38 КБ, 424 строки после чистки): полная инструкция для мониторинга RAB9 — цикл манипуляции (4 фазы), паттерны pump.fun (sniper/bundling/wash/KOL/rug), ядро «настоящий vs ложный пробой» (4 фильтра), ончейн-метрики раннего сигнала, X-классификация, карта аномалий A1–A10/B1–B6, сводные пороги. Reasoning-артефакт Grok Build из первой строки удалён.
- ** файлы ** — `grok_manipulation_research_result.md` (новый), `grok_manipulation_research_stderr.log` (пустой).

## 21.08.2026 — инцидент «msf-listener systemd vs фон» закрыт

- ** причина ** — два systemd-юнита на `msf-listener`: system (`/etc/systemd/system/`, active+enabled) и user (`~/.config/systemd/user/`, был enabled+inactive). User-юнит при автозапуске поднял бы второй long-poll на `@msf_rab_bot` → race/409. Плюс мёртвый дубль-поллер `msf_poller.py` (читал токен из несуществующего `~/rab9/msf_token.txt`).
- ** что сделано ** — `systemctl --user disable msf-listener.service` → user-юнит `disabled` (symlink `wants/` убран, unit-файл не удалялся, без `stop`). System-юнит НЕ трогали. `msf_poller.py` выпилен из обеих копий: `~/.hermes/scripts/` (не git) и `~/hermes-agent-lab/infra/scripts/` (git-tracked — коммит `45741eb` «remove duplicate msf_poller.py»).
- ** верификация ** — листенер жив и НЕ «фон»: PID **2514283** (`Ss`, с 19.08), PPID=1, cgroup `/system.slice/msf-listener.service` = это процесс system-юнита (MainPID 2514283). Offset пишется в `~/.hermes/secrets/rab9/msf_offset.txt` = **892536633** (обновлён 08:50). Ровно один `msf_listener.py`. System-юнит `active`+`enabled` (reboot-устойчив), user-юнит `disabled`+`inactive`.
- ** итог ** — инцидент закрыт: канон = systemd system-юнит (PID 2514283), дубль user-юнит отключён, поллер выпилен.

## 20.08.2026 — 25-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **25-й день без сигналов** (27.07–20.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (1 week 5 days uptime, с 08.08), MSF HTTP :8089 200 (`ok=true`, 127.0.0.1), MSF Listener PID 2514283 жив (с 19.08). Ошибки core — только ночной `Telegram NetworkError Bad Gateway` 01:11 (2x, transient, стандартное окно обслуживания Telegram, самовосстановился). Листенер — штатный long-poll `read operation timed out` (2x: 00:46, 05:18) + 1x `Connection reset by peer` 12:31 (transient). Secrets-миграция подтверждена: offset пишется в `~/.hermes/secrets/rab9/msf_offset.txt` (892536613, обновлён 23:17), корневой `msf_offset.txt` остановился на 19.08 07:35 (892536610). dedupe: только BURNIE (96/115 HIGH CONVICTION, MC $1.3M, GMGN 10/15, verdict ⏳ WAIT | ❓ НЕИЗВЕСТНО). GMGN OpenAPI read-only, trading disabled. Код за день не менялся (только CHRONOLOGY).

## 19.08.2026 — 24-й день без MSF-сигналов + secrets-миграция listener активирована

- **07:36** — MSF Listener рестартован (PID 14392 → **2514283**). Перед этим 2x `HTTP Error 409: Conflict` на getUpdates (05:24, 05:27) — временный race, n8n не активен (нет процессов/docker). Offset сохранён (`892536603`), апдейты не потеряны. Рестарт активировал secrets-миграцию от 13.08: новый листенер пишет offset в `~/.hermes/secrets/rab9/msf_offset.txt` (обновлён 23:15), корневой `msf_offset.txt` остановился на 07:35. Техдолг «listener работает на старом пути» закрыт.
- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **24-й день без сигналов** (27.07–19.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (1 week 4 days uptime, с 08.08), MSF HTTP :8089 200 (`ok=true`, 127.0.0.1), MSF Listener PID 2514283 жив. Core — 0 ошибок (только health-check GET). Листенер — штатные long-poll `read operation timed out` + 2x 409 Conflict утром (до рестарта). dedupe: только BURNIE (96/115 HIGH CONVICTION, MC $1.3M, GMGN 10/15, verdict ⏳ WAIT | ❓ НЕИЗВЕСТНО). GMGN OpenAPI read-only, trading disabled. Код за день не менялся (только CHRONOLOGY).

## 18.08.2026 — 23-й день без MSF-сигналов (CHRONOLOGY agent не запускался)

- Пропуск: дневной CHRONOLOGY agent не отработал — записи за 18.08 в хронологии нет (заполнено задним числом по логам). Listener: штатные long-poll `read operation timed out` + 2x `502 Bad Gateway` 19:54 (transient, стандартное окно обслуживания Telegram). Core: 5 строк лога, 0 ошибок, 0 сигналов. 0 MSF-сигналов — **23-й день без сигналов** (27.07–18.08).

## 17.08.2026 — 22-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **22-й день без сигналов** (27.07–17.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (uptime с 08.08), MSF HTTP :8089 200 (`ok=true`, 127.0.0.1), MSF Listener PID 14392 жив. Ошибки — только ночной Telegram Bad Gateway 01:10 (5х `Telegram handler error` + traceback, transient, стандартное окно обслуживания Telegram, самовосстановился). dedupe: только BURNIE (96/115 HIGH CONVICTION, MC $1.3M, GMGN 10/15). GMGN OpenAPI read-only, trading disabled. Код за день не менялся. Рабочее дерево: M CHRONOLOGY.md, M msf_listener.py (secrets-миграция с 13.08, listener НЕ рестартован — работает на старом пути), ?? kpi_report.py, ?? .kpi-proposal/, ?? briefings/.

## 16.08.2026 — 21-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **21-й день без сигналов** (27.07–16.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (1 неделя 1 день uptime, active с 08.08), MSF HTTP :8089 200 (`ok=true`, 127.0.0.1), MSF Listener PID 14392 жив. Ошибки — только штатный long-poll timeout листенера (7x за день: `read operation timed out`) + 1x ночной 502 Bad Gateway 01:11 (transient, стандартное окно обслуживания Telegram). Core — 0 ошибок (кроме пары NetworkError Bad Gateway 01:11, transient). dedupe: только BURNIE (96/115 HIGH CONVICTION, MC $1.3M, GMGN 10/15). GMGN OpenAPI read-only, trading disabled. Код за день не менялся. GitHub: 0 коммитов за день. Рабочее дерево: M CHRONOLOGY.md (staged), M msf_listener.py (secrets-миграция с 13.08, listener НЕ рестартован — работает на старом пути), ?? kpi_report.py, ?? .kpi-proposal/, ?? briefings/.

## 15.08.2026 — Enforced-слой: финальный точечный проход safety/verifier/dedupe

- Причина: финальный Maker-проход по 4 дефектам enforced-слоя: `phase=dead` давал hard `DROP`, warning `INCONCLUSIVE` попадал в verifier context, ручные handlers не помечали `INCONCLUSIVE`, а dedupe-recap мог обходить safety-drop при повторе.
- Что исправлено:
  - `operators/operator_safety.py`: hard `DROP` оставлен только для `honeypot in {fail,true,1}` и `rugcheck=rugged`; `phase=dead` теперь `INCONCLUSIVE`, включая `honeypot=pass` + `rugcheck=low/medium`.
  - `msf_http.py`: `SAFETY_INCONCLUSIVE_WARNING` больше не добавляется до verifier; verifier получает чистый `full_report`, warning добавляется после возможного `fixed_text` replace и перед отправкой.
  - `handlers.py`: `/testsignal`, `RAB9_SIGNAL` и сырой Solana-адрес добавляют warning при `INCONCLUSIVE` после `DROP`-проверки.
  - `msf_analysis.py` + `msf_dedupe.py`: dedupe-запись сохраняет `safety_flags`, а `check_dedupe` считает запись junk, если эти флаги сейчас дают `DROP`; повтор `honeypot/rugged` не возвращает recap мимо safety.
- Проверка: `venv/bin/python -m unittest operators.tests.test_operators -v` → 30/30 OK; `venv/bin/python -m py_compile operators/operator_safety.py operators/tests/test_operators.py msf_http.py handlers.py msf_analysis.py msf_dedupe.py` → чисто; прямые вызовы `check_safety("pass","low","DEAD")` → `INCONCLUSIVE`, `check_safety("fail","","BUY")` → `DROP`.

## 15.08.2026 — Enforced-слой: третий проход Maker закрыл N1-N7

- Причина: независимый Checker второго прохода подтвердил прошлые 8 фиксов, но нашёл новые дефекты N1-N7: `rugcheck=high` дропал свежие мемкоины, `unknown` safety fail-open уходил как ALLOW, safety-факты собирались вторым API-прогоном, ручные входы обходили safety, а `FLAG` с `fixed_text` без маркера `📝` мог отправить сырой текст.
- Что исправлено:
  - `operators/operator_safety.py`: `DROP` только для `honeypot in {fail,true,1}`, `rugcheck=rugged`, `phase=dead`; `ALLOW` только при `honeypot=pass` и `rugcheck in {low,medium}`; всё остальное (`unknown`, `high`, пустые/непонятные значения) → `INCONCLUSIVE`.
  - `msf_analysis.py`: `build_compact_analysis_text(address, mode)` теперь возвращает `(text, safety_flags)`; `safety_flags` берутся из того же прогона (`onchain_data`, `rugcheck_report/rugcheck_level`, `phase_signal`); удалён дубль `collect_safety_flags`.
  - `msf_http.py`: убран второй safety-прогон; `INCONCLUSIVE` добавляет предупреждение в текст перед отправкой, `DROP` возвращает `dropped_safety`; `FLAG` с пустым `fixed_text` или без маркера `📝` → `hold_flag`.
  - `handlers.py`: `/testsignal`, `RAB9_SIGNAL` и сырой Solana-адрес распаковывают `(text, safety_flags)` и применяют safety-gate; при `DROP` отправляют короткое «⛔ сигнал отклонён safety-гейтом».
  - `operators/tests/test_operators.py`: добавлены регрессии для `unknown/high/rugged/pass+low/pass+medium`, int destination и blank `fixed_text`.
- Проверка: `venv/bin/python -m unittest operators.tests.test_operators -v` → 31/31 OK; `venv/bin/python -m py_compile $(rg --files -g '*.py' -g '!venv/**' -g '!_archive/**' -g '!magpie/**' -g '!loop_stops.py' -g '!structured_reflection.py')` → чисто; `rg -n "collect_safety_flags" *.py` → пусто; `rg -n "from telegram|from config|import dotenv" operators/` → пусто.

## 15.08.2026 — Enforced-слой: закрыт второй проход Checker по 8 дефектам

- Причина: независимый Checker нашёл fail-open и неполную интеграцию operator-layer после первого прохода.
- Что исправлено:
  - `operator_verdict_gate.py`: `FLAG` без `fixed_text` теперь `HOLD`, `FLAG` с непустым `fixed_text` → `ALLOW`.
  - `operator_safety.py`: входы нормализуются через `str(...).strip().lower()`, `honeypot=True/"true"/"1"/"fail"` → `DROP`, `phase=dead` case-insensitive.
  - `operator_config_guard.py`: пустой/None action → `BLOCK`, blank approval-token на mutating action → `HOLD`.
  - `loop_verifier.py`: отсутствующий/пустой `verdict` в JSON verifier → `REJECT` с note `Verifier verdict missing`.
  - `msf_http.py`: `send_msf_pairresolve` возвращает реальные статусы (`sent`, `blocked_destination`, `suppressed_verifier`, `hold_flag`, `dropped_safety`), HTTP `ok=true` только для `sent`; добавлен вызов `check_safety` после сборки анализа и до отправки.
  - `msf_analysis.py`: добавлен `collect_safety_flags(address)` без изменения сигнатуры `build_compact_analysis_text`; факты берутся из `onchain_check`, `rugcheck_client`, `chart_analysis`/`meme_score`/`phase_detector`, недоступные значения остаются пустыми.
  - `handlers.py`, `alerts.py`, `burnie_sentiment_tracker.py`: добавлен второй слой `check_destination` на обходных Telegram-отправках.
- Mutation-gate: реальных Python-точек `systemd_edit/env_edit/config_edit/deploy/restart_service` в живом RAB9 runtime не найдено; фиктивные хуки не добавлялись. Мутирующий shell `scripts/deploy.sh` не трогался по запрету на systemd/deploy.
- Проверка: `venv/bin/python -m unittest operators.tests.test_operators -v` → 25/25 OK; `find . -path './venv' -prune -o -name '*.py' -print0 | xargs -0 venv/bin/python -B -m py_compile` → чисто; `grep -rn "from telegram\|from config\|import dotenv" operators/` → пусто.

## 15.08.2026 — Детерминирование профиля: enforced-оператор-слой `operators/`

- Запуск по цепочке Operator Layer (Hermes GPT): Hermes оркестрировал, Grok строил read-only карту, Codex = Maker писал код, Hermes+Grok = Checker.
- Мандат Сергея: **автопилот** — сигналы шлются без approval-токена на каждое событие (24/7 монитор мемов); approval нужен **только на смену конфига / деплой**. DESTINATION_LOCK allowlist = **оба** чата: Cryptanalyst `-1004425561477` + Песочница `-1003979753733`.
- Создан enforced-слой `operators/` (7 файлов, 232 строки, stdlib-only, enum `Verdict`+`CheckResult`, fail-closed, `__all__`, без side-effects при import):
  - `verdict.py` — `Verdict(ALLOW/BLOCK/HOLD/DROP/REJECT/INCONCLUSIVE)` + `CheckResult`.
  - `operator_destination.py` — `DESTINATION_LOCK` (allowlist 2 чата).
  - `operator_safety.py` — `SAFETY_GATES` (honeypot=fail / rugcheck high|rugged / phase=DEAD → DROP).
  - `operator_verdict_gate.py` — `REJECT_DEFAULT` (fail-closed verifier).
  - `operator_config_guard.py` — `APPROVAL_REQUIRED` на mutating (systemd_edit/env_edit/config_edit/deploy/restart_service).
  - `tests/test_operators.py` — 18 юнит-тестов, все зелёные (`venv/bin/python -m unittest`).
- Интеграция в боевой код (точечно):
  - `msf_http.py`: ранний `DESTINATION_LOCK` в начале `send_msf_pairresolve` + verifier-gate fail-closed (`except → suppress`, было `passing through`); default verdict `PASS` → `REJECT`.
  - `loop_verifier.py`: fail-open `PASS` → `REJECT` в 3 ветках (no api_key / API error / format error / exception). Закрыта главная дыра «нет ключа → публикуем без проверки».
  - `handlers.py`: `send_long_to_chat` получил destination-check.
- **Техдолг (решено Сергей, вариант B):** оператор `operator_safety` написан и протестирован, но **НЕ вшит** в `send_msf_pairresolve` — вердикт «AVOID» при rugcheck/honeypot/DEAD пока формируется текстом внутри `msf_analysis`, структуры `safety` наружу нет. Подключить при рефакторинге `msf_analysis.build_compact_analysis_text` (1108 строк, сердце анализа, меняется в T-132/T-134) — не ломать живой контур.
- Проверка Checker (Hermes+Grok adversarial): 18/18 тестов, py_compile чисто, запрещённых импортов нет, `import operators` без side-effects.

## 15.08.2026 (2-я половина) — Детерминирование rab9: проход 2 + 3 (закрытие багов Checker)

- **Checker проход 1** (Grok adversarial) нашёл 8 багов: FLAG→ALLOW (fail-open), loop_verifier missing verdict → FLAG, HTTP 200 «sent» после заглушки, `check_safety` не вызван, `check_mutation` мёртв, destination-lock на 1 пути из 5, case/bool fail-open в safety+mutation.
- **Проход 2 Maker** закрыл все 8: FLAG с `fixed_text`→ALLOW / без→HOLD; missing verdict→REJECT; status-возврат `msf_http` (`ok=status=="sent"`); `collect_safety_flags` + `check_safety` в поток; destination-lock во все 5 путей (helper `destination_allowed`); нормализация case/bool. Итог: 25 тестов.
- **Checker проход 2** подтвердил 8/8 закрыто, но нашёл 7 новых (N1-N7). Критичный **N1**: `rugcheck_client` ставит `level="high"` при ЛЮБОМ mint/freeze authority (норма для свежих мемов), а `check_safety` дропал `high` → автопилот переставал слать сигналы. **N4**: `unknown` honeypot/rugcheck → ALLOW (fail-open).
- **Решение Сергея (15.08):** N1 — `rugged` (подтверждённый) → DROP, `high` → предупреждение в тексте, НЕ DROP; N4 — `unknown` → INCONCLUSIVE + пометка «⚠️ safety не подтверждена» в тексте; N2+N3 — единый прогон (`build_compact_analysis_text` возвращает `(text, safety_flags)`, убрать дубль `collect_safety_flags`); N5 — NO_BYPASS (safety на `/testsignal` + сырой адрес); N6 — FLAG+fixed без маркера → HOLD; N7 — тесты.
- **Проход 3 Maker** закрыл N1-N7: N1 `rugged`→DROP/`high`→INCONCLUSIVE; N4 `unknown`→INCONCLUSIVE+пометка; N2+N3 `build_compact_analysis_text`→`(text, safety_flags)` из того же прогона (убран `collect_safety_flags`); N5 safety-gate в `run_testsignal_analysis`+`plain_text_handler`; N6 FLAG+fixed без `📝`→HOLD; N7 тесты (31). Checker подтвердил N1-N7, нашёл остаточные: DEAD как hard DROP (ложный DROP на тихих micro-cap), warning до verifier, handlers INCONCLUSIVE без пометки, dedupe-обход DROP.
- **Проход 4 Maker (финал)** закрыл остаточные: (1) `phase=DEAD` → INCONCLUSIVE (не DROP) — hard DROP остались только `honeypot=fail`+`rugcheck=rugged`; (2) предупреждение INCONCLUSIVE вшивается ПОСЛЕ verifier (не ломает FLAG/FAIL); (3) handlers 3 ручных анализа помечают INCONCLUSIVE; (4) `msf_dedupe` пишет `safety_flags`, `_is_junk` режет recap при DROP. Итог: 30 тестов.
- **Финальный Checker (4-й):** 4 правки CLOSED, 8 регрессий чистые, DROP-регрессии нет. Детерминированный DROP = ровно 2 scam-факта. Автопилот НЕ молчит на `dead`/`high`/`unknown`. **Детерминирование завершено.**

## 20.07.2026 — Доставка отчётов: Песочница → Cryptanalyst

- Решение Сергея: боевой группы нет; Песочница (`-1003979753733`) — тестовая прослойка, не боевой контур. Команда: «применяй».
- `.env`: `TELEGRAM_GROUP_ID` → **`-1004425561477`** (группа Cryptanalyst).
- `rab9-crypto-hermes` перезапущен: PID **3164401**, `:8089` 200.
- При рестарте `msf_listener.py` упал — поднят вручную, PID **3164468**.
- Сергей: оба бота (`@msf_rab_bot`, `@rab2610bot`) добавлены в Cryptanalyst.
- Конвейер после переноса: Мемы → `@msf_rab_bot` → `msf_listener` → `:8089` → `rab9_bot` → **Cryptanalyst**.

## 26.07.2026 — MSF Listener мёртв с ~21.07 + перевод в systemd

- Сигнал в Мемах не подхвачен. Диагноз: `msf_listener.py` нет в процессах; входящих POST нет (только health); offset застрял на **21 июля**.
- Причина: ручной процесс не поднялся после ребута (с ~21.07). Всё между 21 и 26 июля — потеряно.
- Поднят вручную (PID 1164800), затем заведён **`msf-listener.service`**: `Restart=always` (10 с), `enabled`, ждёт `rab9-crypto-hermes`. В строю systemd-PID **1166144**. Старый ручной процесс убит штатно (SIGTERM 143).
- Первый прогон после починки: `6rgcqxm…frzs` — VERIFIER PASS 100 → ⚫ SKIP (liq **$11 315 < $20 000**, MC $24 344, Vol 24h $52 246). Лог: сигнал пришёл из **Cryptanalyst**, не догнался из Мемов.
- Урок (закрывает «Не сделано» от 07.07): listener без systemd не переживает ребут.

## 26.07.2026 — X API 402 credits depleted → пополнение

- Gap после инфры: BURNIE/`xurl` → **402**, `credits depleted`. Это не бот.
- Не путать биллинги: SuperGrok / opencodex `:10100` ≠ X API (`xurl` / OAuth1).
- Сергей пополнил. Проверка: `xurl search` 200, OAuth1 `radar_x` 200, BURNIE tracker **BULLISH**.
- Снимок: followers **18 991**, sentiment **pos**, bullish pos=21 / toly=7, recent 10: 427♥ / 238↻.

## 26.07–31.07.2026 — n8n ворует getUpdates @msf_rab_bot (две волны)

**Волна 1 (26.07):** тест-ссылка в Мемах. 409 Conflict на `getUpdates` — n8n workflow `MSF - Telegram AI Filter MVP` active, конкурирует с `msf_listener`. Workflow выключен, listener restart. Отработана 1 ссылка: `asvm3zu5hmmg…` → SKIP (liq **$7 121 < $20k**). Вторая ссылка — `dexscreener.com/robinhood/…` (**CIAO** / `c1a0`): listener игнорирует — только `dexscreener.com/solana/<addr>` или raw Solana base58.

**Волна 2 (~29–31.07):** снова пропуски; 2 суток **0 сигналов**, 409 нет — хуже: апдейты съедаются без конфликта. Root cause: Docker **`n8n-msf`** (PID 2251, порт **5688**) + `node …/n8n` — ~2 недели, **ни одного сигнала в RAB9 с 29 июля**. `docker stop n8n-msf`, `RestartPolicy: no`, `systemctl restart msf-listener`.

- Урок: 409 = видимый конфликт; тихий steal = 100% потеря без ошибки в логах RAB9.

## 28.07–02.08.2026 — BURNIE tracker: кредиты, один крон, vote-spam

- Аудит X: трекер **5 вызовов / 4 ч = 30/день**. Оптимизация: убраны пустой `search sentiment` и дубль `from:ACCOUNT` → **3 вызова / 12 ч = 6/день (−80%)**.
- Дубли кронов: `cbc130e06a9f` (профиль rab9) + `59d37ee6a323` + мёртвый weekly `9399c1b08b31` (default). Сведено в **один**: `59d37ee6a323` (default), **06:00 / 18:00 UTC** → Cryptanalyst. `monitor_burnie.py` мёртв (Birdeye off).
- DexScreener через urllib без User-Agent → **403**; с UA: MC $1.44M, price $0.001489, 24h −2.04%, vol $56K, liq $192K.
- Отчёт врал из‑за **vote-spam** («New Listing Around the Corner»). Фильтр: pos **12–13 → 7**, vote_spam=3 отдельно. Moonshot-голосование: топчемся месяц (02.07: 185→150 … 06.07 минимум **56**).
- Решение Сергея: катализаторы — **ноябрьские выборы (PolitiFi)** + накопление на кошельках, не Moonshot.

## 28.07–02.08.2026 — BURNIE: TA/OHLCV, фаза decay, крупные аккаунты

- Фаза: накопление у дна. DexScreener: $0.001492, MC **$1.45M**, liq $193K, vol $52K. История: **$25M MC → $1.4M (−94% ATH)**.
- Ошибка порога: «пробой 10%» для мемкоина — не сигнал.
- OHLCV бесплатно: **GMGN `market kline` — 100 дней** (с 24.04) + GeckoTerminal ~45 свечей/запрос; локальный архив `data/ohlcv_archive/` — **90 свечей**. Окно 45 копить.
- Баг фазы: acc **0.12** / dist **0.38** (оба < 0.5) + fallback `trend=DOWNTREND` (−94% ATH) → «раздача». Факт: `flat_days: 43`, RSI **39.3** → **decay**, не distribution.
- Бесплатные поля в отчёт: buy/sell **0.9** (249b/274s); холдеры **10 174**, bundler'ы **3 (7.0%)**; RugCheck низкий.
- Драйвер ≠ «buy/pump»: мелкие @ClipsByDough (128) / @NickLor04939359 — шум; пропущен ретвит **@AlphaAgentcall** из‑за `-is:retweet`. Солидный аккаунт: достаточно двусмысленного «BURNIE» / RT/лайк офиц. @BurnieSendersX.
- Grok Build: оператор **`retweets_of:BurnieSendersX`**. Пойман **@DangerousThinkg (129 530)** — RT офиц. поста (13 мин, 10♥ / 6 RT / 505 просм.). Вердикт впервые **СЛЕДИТЬ (69/100)** с катализатором.
- Бюджет X: **3 → до 6** вызовов (timeline офиц. + `retweeted_by`). `liking_users`: OAuth2 **403**, OAuth1 пусто даже при 271 лайке. Замена: **`like_count` spike** + quotes; окно свежести **3ч → 12ч**. `quote_fresh`: @Benji_Yugi (6 336) + @elonmusk.
- Крон в LLM-режиме обходил `[SILENT]`: агент читал JSONL и сам сочинял отчёт. Переведён на **script-first / no_agent**.

## 03.08.2026 — Отчёты BURNIE: тишина event-first + слоты Бишкек

- За день 0 отчётов. Крон в 06:00 UTC отработал, stdout **silent**. Снимки: **fol/pos/neg = 0** (вчера 18:03: fol **19 082**, pos 21). X API жив (`followers_count: 19 091`); пустой снимок + event-first → `[SILENT]`.
- Сергей: отчёт **всегда** в 06:00 и 18:00 по местному; катализаторы — со ссылками.
- Местное = **Бишкек UTC+6** → cron `0 6,18` UTC заменён на **`0 0,12 * * *`** (06:00/18:00 Бишкек). Event-first остался только внутри текста (подсветка драйвера).

## 2026-07-28 — T-182 GMGN OpenAPI cutover (read-only)

## 2026-08-09
- AGENTS.md: добавлена секция «Архитектура и инфраструктура» (сервер, сервисы, БД, API, data flow)

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
- **28.07.2026 23:30** — CHRONOLOGY agent: day summary. 3 токена, 8 анализов (включая 6x `CGEDT9Q...` BURNIE). 6 CABAL_EXPLOSION алертов. 2 ошибки `meme_score` list index out of range (09:49, 13:27 — self-healed). Telegram NetworkError 01:11 (10 ошибок, transient, самовосстановился). RAB9 перезапущен в 13:49 (PID 1983572). BURNIE: 96/115 СИЛЬНЫЙ, GMGN 10/15, 10257 держателей. Инфраструктура стабильна.
- **29.07.2026 04:07** — chore: auto-sync 29.07 (`f6ee381`)
- **29.07.2026 12:59** — MSF Listener перезапущен (новый PID 2365196). Причина: watchdog или ручной рестарт.
- **29.07.2026 23:30** — CHRONOLOGY agent: idle day. 0 MSF-сигналов за весь день — только health-check'и :8089 каждые 15 мин. Инфраструктура стабильна: RAB9 Core active (PID 1983572, 1d+ uptime), MSF HTTP :8089 200, MSF Listener PID 2365196 жив. dedupe: только BURNIE (96/115). Контекст за день: удаление opencodex из всех профилей (включая rab9), перевод rab9 на DeepSeek. X API credits на нуле — BURNIE sentiment tracker не обновляется. GMGN OpenAPI read-only, trading disabled.
- **30.07.2026 04:04** — chore: auto-sync 30.07 (`2f4668a`)
- **30.07.2026 23:30** — CHRONOLOGY agent: idle day. 0 MSF-сигналов за весь день — только health-check'и :8089 каждые 15 мин. Инфраструктура стабильна: RAB9 Core active (PID 1983572, 2d+ uptime), MSF HTTP :8089 200, MSF Listener PID 2365196 жив (1d+). Ошибки: 4x NetworkError Bad Gateway в 01:11 (transient, самовосстановился). dedupe: только BURNIE (96/115). X API credits на нуле с 27.07 — BURNIE sentiment tracker не обновляется. GMGN OpenAPI read-only, trading disabled. GitHub: 1 коммит за день (auto-sync).
- **31.07.2026 03:33** — security: add backups/ to .gitignore (`c926900`)
- **31.07.2026 04:04** — chore: auto-sync 31.07 (`5ebaba2`)
- **31.07.2026 11:20** — Circulation Graph добавлен в AGENTS.md: CAUSED/FIXED_BY/RESULTED_IN/LEARNED_FROM/APPLIED_TO edges. CIRCULATION_GRAPH.md скопирован из robot-man во все проекты включая RAB9.
- **31.07.2026 12:14** — Daily Audit: DeepSeek $8.10, 40 cron джоб 0 error, 0 MSF-сигналов за день. X API credits на нуле — BURNIE sentiment tracker не получает новые данные.
- **31.07.2026 18:02** — BURNIE sentiment tracker: pos, 19058 followers (-2), toly=3, голосование за листинг активно. Сентимент стабильно bullish, strong_negative=0.
- **31.07.2026 23:30** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — только health-check'и :8089. MSF Listener перезапущен (новый PID 3432372, uptime 3 мин). Telegram NetworkError в 13:26 (httpx.ReadError — transient). RAB9 Core active (PID 1983572, 3d+ uptime). dedupe: только BURNIE (96/115). X API credits на нуле с 27.07. GMGN OpenAPI read-only, trading disabled.
- **01.08.2026 04:04** — chore: auto-sync 01.08 (`6bb8645`)
- **01.08.2026 10:00-23:59** — Шестой день без MSF-сигналов (27.07-01.08). Мемы молчат. Только health-check'и :8089 каждые ~15 мин. RAB9 Core active (PID 1983572, 4d+ uptime). MSF Listener PID 3432372 жив (20h+ uptime).
- **01.08.2026 01:10** — Telegram NetworkError (Bad Gateway). 4 ошибки за 5 секунд. Transient — самовосстановился. Паттерн повторяется каждую ночь в ~01:10 (Telegram maintenance window).
- **01.08.2026 18:02** — BURNIE sentiment tracker: 🟢 BULLISH. pos=20/neg=1. Фолловеры: 19,067 (±0). MC: $1.4M, Price: $0.001412 (+0.9%). Рынок flat — накопление. Вердикт: СЛЕДИТЬ (69/100). X API credits на нуле — search-слой заглушен, данные не обновляются.
- **01.08.2026 23:30** — CHRONOLOGY agent: idle day. 0 MSF-сигналов. Инфраструктура стабильна: RAB9 Core 4d+, MSF HTTP :8089 200. 0 ошибок кроме ночного NetworkError. GitHub: 0 коммитов кроме auto-sync. X API credits на нуле с 27.07 — 6-й день. GMGN OpenAPI read-only, trading disabled. dedupe: только BURNIE.
- **02.08.2026 00:29** — chore: auto-sync 02.08 — burnie tracker, chart analysis, strategy (`337db8b`)
- **02.08.2026 04:21** — chore: auto-sync 02.08 (`5092e9d`)
- **02.08.2026 07:42** — fix: ban X write operations in Rab9 profile (caused rogue reply 01.08.2026) (`ee49ad6`)
- **02.08.2026 23:30** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — 7-й день без сигналов (27.07-02.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core active (PID 1983572), MSF HTTP :8089 200, MSF Listener PID 3432372 (20h+ uptime). 0 ошибок в логах. BURNIE: 0 свежих X-взаимодействий (X API credits на нуле). dedupe: только BURNIE (96/115). GMGN OpenAPI read-only, trading disabled. GitHub: 1 коммит за день (ban X write ops).
- **03.08.2026 00:19** — chore: auto-sync 02.08 night — chart, gmgn, meme_score, msf, onchain, token_intel + honeypot_check + llm_fallback test (`c79ef34`)
- **03.08.2026 00:23** — fix: BURNIE tracker — не ронять прогон при rate-limit X API (user_data=None) + CHRONOLOGY sync (`0f024f3`)
- **03.08.2026 04:06** — chore: auto-sync 03.08 — chrono (`036bfaa`)
- **03.08.2026 12:37** — BURNIE tracker fix: добавлен `x_api_errors` флаг + `format_degraded()` — при сбое X API теперь приходит короткий отчёт «⚠️ трекер жив, X API недоступен» вместо молчания. Скрипт синхронизирован в `~/.hermes/profiles/rab9/scripts/`.
- **03.08.2026 15:44** — MoA Auto: `moa-auto` скилл в общем доступе. AGENTS.md RAB9 обновлён: «⛔ НИКОГДА `delegate_task` без `acp_command`». Codex через `acp_command='codex'`, Grok через `acp_command='grok'`.
- **03.08.2026 23:30** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — 8-й день без сигналов (27.07-03.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core active (PID 1983572, 6d uptime), MSF HTTP :8089 200, MSF Listener PID 3432372 жив. 0 ошибок в логах. BURNIE: X API credits на нуле 8-й день — трекер даёт деградированный отчёт. dedupe: только BURNIE (96/115). GMGN OpenAPI read-only, trading disabled. GitHub: 0 коммитов за день.
- **04.08.2026 04:06** — chore: auto-sync 04.08 (`151bbac`)
- **04.08.2026 ~14:39** — RAB9 Core перезапущен (systemctl restart). Причина неясна — возможно, перезагрузка сервера. Новый PID 795. MSF Listener рестартован вместе с ним (новый PID 796, оба под systemd).
- **04.08.2026 01:10** — Telegram NetworkError (Bad Gateway). 8 ошибок за 5 секунд. Transient — самовосстановился. Стандартное окно обслуживания Telegram.
- **04.08.2026 12:11** — BURNIE sentiment tracker: 🟢 BULLISH. pos=23/neg=3. Фолловеры: 19,133 (+17). 5 катализаторов: jeremy_cheely (10.7K), RedGhostLover (7.7K), Tonybiskits (6.9K) + RT-спайки. X API credits восстановлены — трекер работает в полном режиме (не degraded).
- **04.08.2026 23:30** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — 9-й день без сигналов (27.07-04.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core active (PID 795, 7h uptime), MSF HTTP :8089 200, MSF Listener PID 796 под systemd. 8 ошибок (только ночной NetworkError — transient). BURNIE: X API жив, трекер в полном режиме, сентимент стабильно bullish, 19,133 подписчиков. dedupe: только BURNIE (96/115). GMGN OpenAPI read-only, trading disabled. GitHub: 1 коммит (auto-sync). Рабочее дерево чистое.
- **05.08.2026 04:03** — chore: auto-sync 05.08 (`f3db1e2`)
- **05.08.2026 07:18** — RAB9 Core перезапущен: новый PID 802, MSF Listener PID 804 (под systemd). Health :8089 200. Причина перезапуска: перезагрузка VPS или systemctl restart.
- **05.08.2026 10:07** — Инфраструктурное: Kimi API ключ удалён из всех конфигов (включая RAB9). Vision уходит на DeepSeek. `context_file_max_chars` поднят 20K → 30K для всех 5 профилей (включая rab9). Memory clean: 96% → 51%.
- **05.08.2026 11:29** — Buzz-брифинг: BURNIE bullish, 19,133 подписчиков. 9-й день без MSF-сигналов. RAB9 в брифинге: «всё штатно».
- **05.08.2026 12:07** — Daily Audit: rab9 0 cron-джоб, git clean (только CHRONOLOGY + AGENTS.md staged). CHRONOLOGY свежесть 8h.
- **05.08.2026 23:30** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — 10-й день без сигналов (27.07-05.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 802 (16h uptime), MSF HTTP :8089 200, MSF Listener PID 804. 0 ошибок в логах. BURNIE: X API жив, трекер в полном режиме. dedupe: только BURNIE (96/115). GMGN OpenAPI read-only, trading disabled.
- **06.08.2026 04:03** — chore: auto-sync 06.08 (`df5a517`)
- **06.08.2026 23:30** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — 11-й день без сигналов (27.07-06.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 802 (1d 16h uptime), MSF HTTP :8089 200, MSF Listener PID 804 под systemd. 3 ошибки: ночной NetworkError (01:11, 2x) + Conflict (04:50, getUpdates race — transient). BURNIE: dedupe 96/115, X API жив (трекер в полном режиме). GMGN OpenAPI read-only, trading disabled. GitHub: 0 коммитов кроме auto-sync. Рабочее дерево чистое.

## 07.08.2026 — xAI key fix + agent-bus escalation rules

- **08:21** — Buzz agent-bus: всем профилям (включая RAB9) добавлена директива «ДОКЛАД HERMES В AGENT-BUS» в SOUL.md. Обнаружил проблему → напиши @Hermes в agent-bus.
- **10:19** — xAI API key восстановлен. radar_x тестовый скан BURNIE: ok=True, 10 постов. Инцидент #005 закрыт. X-радар RAB9 полностью функционален.
- **14:10** — RAB9 Core перезапущен: PID 802 → 3927992. Причина неясна (возможно, VPS reboot). MSF Listener перезапущен вместе с ним.
- **15:15** — Ещё один рестарт RAB9 Core: PID 3927992 → 78799. MSF Listener → PID 78800. Оба под systemd.
- **01:11** — Telegram NetworkError (Bad Gateway) — transient, стандартное окно обслуживания.
- **05:49** — Telegram NetworkError (httpx.ReadError) — transient, самовосстановился.
- **23:30** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — 12-й день без сигналов (27.07-07.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 78799 (8h uptime), MSF HTTP :8089 200, MSF Listener PID 78800. 2 ошибки (оба NetworkError — transient). BURNIE: dedupe 96/115, X API жив. GMGN OpenAPI read-only, trading disabled. GitHub: 0 коммитов кроме auto-sync.

## 08.08.2026 — VPS hardening: localhost-only порты + платформенные изменения

- **07:45–07:48** — Харденинг VPS: все сервисы перезапущены, порты закрыты на localhost. RAB9 Core PID 14391, MSF Listener PID 14392 (offset 892536603 сохранён — апдейты не потеряны). `:8089/health` **200**, порт 8089 теперь слушает только `127.0.0.1`.
- Пост-харденинг проверка: **0 ошибок**/exception за 30 мин, исходящие живы (Telegram API 302, DexScreener 200). У RAB9 нет входящих публичных портов — localhost-связка listener→core не затронута.
- Замечено: на `127.0.0.1:8099` висит `python3` PID 1072 — **НЕ RAB9** (чужой процесс, не трогал).
- Платформенные изменения (Hermes infra, код RAB9 не менялся): новый memory-слой NexusOS, разделение очередей bridge, buzz-каналы в конфигах. RAB9-профиль работает штатно.
- **security:** `.env.bak*` добавлен в `.gitignore` — не коммитить бэкапы с секретами (обнаружен незакоммиченный `.env.bak.0808_0748`).
- **08.08.2026 12:38** — chore: CHRONOLOGY 08.08 — VPS hardening (localhost-only ports) + security: .env.bak* in .gitignore (`6f04a53`)
- **08.08.2026 12:40** — chore: CHRONOLOGY 08.08 — VPS hardening, NexusOS memory layer, bridge queues, buzz configs (`86d3dc8`)
- **08.08.2026 12:43** — chore: CHRONOLOGY 08.08 — record 86d3dc8 (auto-sync) (`3801c70`)
- **08.08.2026 12:43** — chore: CHRONOLOGY 08.08 — record 3801c70 (auto-sync) (`4715404`)

## 09.08.2026 — 13-й день без MSF-сигналов

- **04:06** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — 13-й день без сигналов (27.07-09.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (15h uptime), MSF HTTP :8089 200 (127.0.0.1), MSF Listener PID 14392 (поднят вместе с RAB9 после харденинга). 6 health-check'ов за смену, 0 ошибок. dedupe: только BURNIE (96/115). GMGN OpenAPI read-only, trading disabled. GitHub: 0 коммитов кроме авто-синков CHRONOLOGY. Платформенные изменения (buzz-каналы, NexusOS, bridge queues) не затронули RAB9.
- **09.08.2026 00:32** — chrono: 2026-08-09 (`1440bf7`)
- **09.08.2026 06:13** — docs: секция «Архитектура и инфраструктура» (Сервер, Сервисы, БД, API, Data Flow) (`091331b`)
- **09.08.2026 10:00** — AGENTS.md: добавлено правило #0 «ЯЗЫК» — все reasoning/ответы/обсуждения ТОЛЬКО на русском. Без исключений.
- **09.08.2026 ~23:30** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **14-й день без сигналов** (27.07-09.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (1d 15h uptime), MSF HTTP :8089 200 (127.0.0.1), MSF Listener PID 14392 жив. 2 ошибки: ночной NetworkError Bad Gateway 01:10 (transient, стандартное окно). dedupe: только BURNIE (96/115). GMGN OpenAPI read-only, trading disabled. AGENTS.md изменён (языковое правило). Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md.
- **09.08.2026 23:15** — chrono: 2026-08-09 evening — 14-й день без сигналов (`fcb6ff2`)

## 10.08.2026 — 15-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **15-й день без сигналов** (27.07-10.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (2d 15h uptime), MSF HTTP :8089 200 (127.0.0.1), MSF Listener PID 14392 жив. 1 ошибка: ночной NetworkError Bad Gateway 01:10 (transient, стандартное окно обслуживания Telegram). dedupe: только BURNIE (96/115). GMGN OpenAPI read-only, trading disabled. AGENTS.md: правило #0 «ЯЗЫК» staged (добавлено 09.08, не закоммичено). GitHub: 0 коммитов за день. Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md (staged).
- **10.08.2026 23:16** — chrono: 2026-08-10 — 15-й день без сигналов (`8b36b74`)

## 11.08.2026 — 16-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **16-й день без сигналов** (27.07–11.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (3d 15h uptime), MSF HTTP :8089 200 (127.0.0.1), MSF Listener PID 14392 жив. 6 ошибок: NetworkError httpx.ReadError в 14:25 (transient, самовосстановился). dedupe: только BURNIE (96/115 HIGH CONVICTION, MC $1.3M, GMGN 10/15). GMGN OpenAPI read-only, trading disabled. AGENTS.md и CHRONOLOGY.md staged (незакоммичены). Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md, ?? briefings/.
- **11.08.2026 23:16** — chrono: 2026-08-11 (`31fd915`)

## 12.08.2026 — 17-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **17-й день без сигналов** (27.07–12.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (4d 15h uptime), MSF HTTP :8089 200 (127.0.0.1), MSF Listener PID 14392 жив. 6 NetworkError (httpx.ReadError в 01:22 — transient, стандартное окно обслуживания Telegram, самовосстановился). dedupe: только BURNIE (96/115 HIGH CONVICTION, MC $1.3M, GMGN 10/15). GMGN OpenAPI read-only, trading disabled. GitHub: 0 коммитов за день (кроме авто-синка CHRONOLOGY). Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md, ?? briefings/.
- **12.08.2026 23:15** — chrono: 2026-08-12 (`9d41709`)

## 13.08.2026 — 18-й день без MSF-сигналов + секреты в vault

- **12:14–12:16** — Секреты MSF Listener вынесены в vault: `msf_listener.py` переписан на `SECRETS_DIR = ~/.hermes/secrets/rab9/` (`msf_offset.txt` + `msf_token.txt`). Файлы перемещены (`msf_token.txt` удалён из корня репо, `msf_offset.txt` в корне остался — туда пишет running-процесс). ⚠️ Листенер не рестартован после правки кода — PID 14392 работает на старом пути (offset в корне обновляется 23:14), новый путь активируется только после restart.
- **21:43** — `AGENTS.md`: подтверждено правило #0 «ЯЗЫК» (русский, без исключений) + новое правило #5 «CHRONOLOGY АВТОМАТИЧЕСКИ» (сдвиг нумерации 5→9). Не закоммичено.
- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **18-й день без сигналов** (27.07–13.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (5d 15h uptime), MSF HTTP :8089 200 (127.0.0.1), MSF Listener PID 14392 жив. Ошибки листенера — только штатный long-poll timeout (`read operation timed out`, 7x за день) + 1x ночной 502 Bad Gateway 01:10 (transient). dedupe: только BURNIE (96/115 HIGH CONVICTION, MC $1.3M, GMGN 10/15). GMGN OpenAPI read-only, trading disabled. Рабочее дерево: M AGENTS.md, M CHRONOLOGY.md, M msf_listener.py, ?? briefings/.
- **13.08.2026 23:16** — chrono: 2026-08-13 (`22be26f`)

## 14.08.2026 — 19-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle day. 0 MSF-сигналов — **19-й день без сигналов** (27.07–14.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (6d 15h uptime), MSF HTTP :8089 200 (127.0.0.1), MSF Listener PID 14392 жив. Ошибки листенера — только штатный long-poll timeout (`read operation timed out`, 9x за день) + 1x SSL handshake timeout (21:53, transient). Core — 0 ошибок. dedupe: только BURNIE (96/115 HIGH CONVICTION, MC $1.3M, GMGN 10/15). GMGN OpenAPI read-only, trading disabled. Рабочее дерево: M AGENTS.md, MM CHRONOLOGY.md, M msf_listener.py, ?? briefings/.
- **14.08.2026 23:15** — chrono: 2026-08-14 (`bb41c60`)

## 15.08.2026 — enforced-оператор-слой RAB9

- **code_change** — Добавлен чистый stdlib-only слой `operators/` с `Verdict`/`CheckResult` и операторами destination, safety, verifier gate, config guard. Интеграция точечная: `msf_http.py` блокирует неразрешённый `TELEGRAM_GROUP_ID` до анализа и suppress при недоступном/REJECT verifier; `handlers.py/send_long_to_chat` блокирует произвольные chat_id; `loop_verifier.py` переведён с fail-open PASS на fail-closed REJECT в ветках unavailable/API error/format error/exception. Проверка: `/home/hermes-workspace/rab9/venv/bin/python -m py_compile ...` чисто; `/home/hermes-workspace/rab9/venv/bin/python -m unittest operators.tests.test_operators` — 18 tests OK. Systemd, `.env`, `config.py`, `magpie/`, `_archive/`, `loop_stops.py`, `structured_reflection.py` не трогались.
- **15.08.2026 15:44** — operator: зашить законы rab9 в enforced-код (operators/) (`5ba2d67`)
- **15.08.2026 23:15** — CHRONOLOGY agent: итог дня. День активный по коду — детерминирование профиля RAB9 завершено (enforced-слой `operators/`, 4 прохода Maker/Checker, детерминированный hard DROP = ровно 2 scam-факта `honeypot=fail`+`rugcheck=rugged`). 0 MSF-сигналов — **20-й день без сигналов** (27.07–15.08), мемы молчат. Инфраструктура стабильна: RAB9 Core PID 14391 (6d 15h uptime), MSF HTTP :8089 200 (127.0.0.1), MSF Listener PID 14392 жив. Ошибки core — 0. dedupe: только BURNIE (96/115 HIGH CONVICTION, MC $1.3M, GMGN 10/15). GMGN OpenAPI read-only, trading disabled. Незакоммичено: `msf_listener.py` (secrets-миграция с 13.08 — listener НЕ рестартован, работает на старом пути), untracked `kpi_report.py` + `.kpi-proposal/` (KPI/E2E-отчёт). Рабочее дерево: M CHRONOLOGY.md (staged), M msf_listener.py, ?? kpi_report.py, ?? .kpi-proposal/, ?? briefings/.
- **15.08.2026 23:16** — chrono: 2026-08-15 — детерминирование operators/ завершено, 20-й день без сигналов (`12ed4f9`)
- **15.08.2026 23:16** — chrono: 2026-08-15 (auto-sync record 12ed4f9) (`5d1c647`)
- **15.08.2026 23:17** — chrono: 2026-08-15 (auto-sync record 5d1c647) (`27b7d92`)

## 27.08.2026 — 32-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle день. 0 MSF-сигналов — **32-й день без сигналов** (27.07–27.08); запись за 26.08 не была создана (пропуск, инфраструктура по логам 26.08 ошибок core не показывала). Инфраструктура стабильна: RAB9 Core active (PID 14391), MSF HTTP :8089 healthy (127.0.0.1), msf-listener active. Ошибки за 27.08: 2x Telegram NetworkError Bad Gateway 01:10 (transient, стандартное окно обслуживания, самовосстановился). dedupe: только BURNIE (96/115 HIGH CONVICTION, MC $1.3M). GMGN read-only, trading disabled. Рабочее дерево: незакоммиченные правки burnie_price_watch.py, burnie_sentiment_tracker.py, chart_analysis.py, radar_x.py, AGENTS.md (M) — изменений 16–25.08 не фиксировать как сегодня, даты правок не проверены.
- **27.08.2026 23:15** — chrono: 2026-08-27 — 32-й день без сигналов, закрыт пробел 26.08
- **16.08.2026 23:15** — chrono: 2026-08-16 (`753ff99`)
- **17.08.2026 23:16** — chrono: 2026-08-17 (`e190ef4`)
- **19.08.2026 04:00** — daily-sync: auto-commit (`c5c544a`)
- **19.08.2026 23:17** — chrono: 2026-08-19 — 24-й день без сигналов, listener secrets-миграция активирована (`7a2834b`)
- **20.08.2026 04:04** — auto-sync infra 20260820 (`2a39e16`)
- **20.08.2026 23:17** — chrono: 2026-08-20 (`52928a1`)
- **21.08.2026 08:52** — chrono: 2026-08-21 — закрыт инцидент msf-listener systemd vs фон (`40ff044`)
- **21.08.2026 08:55** — chore: CHRONOLOGY 21.08.2026 — msf-listener systemd vs фон инцидент закрыт (`a3326b0`)
- **21.08.2026 13:30** — feat: Grok манипуляции + breakout-фикс + price-watch крон (21.08) (`77349ac`)
- **21.08.2026 13:42** — chore: daily briefing 20.08 + CHRONOLOGY (feat 77349ac) (`0808974`)
- **21.08.2026 13:42** — chrono: 2026-08-21 — daily briefing commit (0808974) (`7215863`)
- **21.08.2026 23:17** — chrono: 2026-08-21 (`0531a80`)
- **22.08.2026 08:08** — fix(msf-listener): 409-защита getUpdates + архив мёртвого rab9.log (`3edd7d0`)
- **22.08.2026 23:17** — chrono: 2026-08-22 (`9332b24`)
- **23.08.2026 23:16** — chrono: 2026-08-23 (`3b7c010`)
- **24.08.2026 23:17** — chrono: 2026-08-24 (`eb2190d`)
- **25.08.2026 23:16** — chrono: 2026-08-25 (`634932d`)
- **27.08.2026 23:16** — chrono: 2026-08-27 (`46a31c2`)
- **28.08.2026 23:17** — chrono: 2026-08-28 (`a413c63`)
- **29.08.2026 23:17** — chrono: 2026-08-29 (`fe16cfa`)

## 30.08.2026 — 33-й день без MSF-сигналов

- **23:15** — CHRONOLOGY agent: idle день. 0 MSF-сигналов — **33-й день без сигналов** (27.07–30.08). Мемы молчат. Инфраструктура стабильна: RAB9 Core active, MSF Listener active (PID 2422530, uptime 1 неделя с 22.08), MSF HTTP :8089 200 (127.0.0.1). Ошибки: 6 transient в логе листенера (штатные long-poll timeouts), ошибок core — нет (journal err --since today: No entries). dedupe: только BURNIE (96/115 HIGH CONVICTION, MC $1.3M). GMGN read-only, trading disabled. Рабочее дерево: незакоммиченные M burnie_price_watch.py, burnie_sentiment_tracker.py, chart_analysis.py, radar_x.py, AGENTS.md (даты правок не подтверждены — не атрибутировать сегодняшнему дню).
- **30.08.2026 23:16** — chrono: 2026-08-30 (`4f4402a`)
- **31.08.2026 05:55** — chrono: 2026-08-31 + инфраструктурная карта (`f458c76`)
- **31.08.2026 23:17** — chrono: 2026-08-31 (`ca42935`)
- **31.08.2026 23:17** — briefing: 2026-08-31 (`a36cc46`)
- **01.09.2026 23:17** — chrono: 2026-09-01 (`6c21f90`)
- **02.09.2026 23:17** — chrono: 2026-09-02 (`7110bb8`)
- **03.09.2026 23:17** — chrono: 2026-09-03 (`ca5e22b`)
- **04.09.2026 23:17** — chrono: 2026-09-04 (`49345e9`)
