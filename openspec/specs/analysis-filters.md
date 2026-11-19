# Spec: analysis-filters — v1.4 FROZEN (2026-11-19, T6 social-weight closure)

> R4-R9 перенесены из pumpportal-ingress v0.1 (ревью e61ce676). Правки v1.0 по
> решению владельца 11.10: КАЧЕСТВО ВЫШЕ КОЛИЧЕСТВА — всё (включая alert фаз)
> идёт через накопительный дайджест, немедленной доставки нет.
> v1.1: гармонизация со standalone-analyzer v1.1 (signal-state-routing):
> t0-перепроверка — внутренний таймер (НЕ ingress-контакт), дедуп 24ч блокирует
> только повторный полный AI-анализ, hard DROP перекрывает мягкие гейты, очереди
> bounded. Машина состояний канонизирована в standalone-analyzer v1.1 — здесь
> analysis-filters = правила фильтрации ВНУТРИ этой машины.
> v1.1 → v1.2: GWT-биндинг — 9 сценариев в карточной форме с id, тесты
> `tests/test_analysis_filters_gwt.py`.
> v1.2 → v1.3: концентрация и confirmed-scam связаны с реальными verdict/queue
> точками.
> v1.3 → v1.4: per-token social-weight — offline-классификатор по кешу radar_x
> (один X-вызов на t0, full analysis переиспользует кеш); BURNIE jsonl не читается.

Purpose: отбор мигрантов перед полным AI-анализом и дисциплина доставки.
Files: определяются design'ом фичи 2 (модули пайплайна: msf_analysis, msf_dedupe, handlers, delivery).
Update Rule: изменение поведения = v-бамп + delta-карточка.
Neighbor Risks: operators/ (SAFETY_GATES, REJECT_DEFAULT), burnie_sentiment_tracker (шаблон сентимент-слоя).
Known Traps: пороги на t=0 мигранта должны быть мягкими (градуация ~85 SOL → пул ~3-17K$, MC ~9-75K$).

### Requirement: t0-cascade
Система SHALL для каждого нового мигранта выполнять мягкий t=0 чек (лог + флаг, без дропа), перепроверку через конфигурируемый интервал, и после перепроверки применять конфигурируемые пороги ликвидности/MC; токен, прошедший перепроверку, SHALL становиться кандидатом полного анализа. Очередь перепроверки SHALL быть персистентной (переживает рестарт).
### GIVEN мигрант на t=0 с пулом ниже порога — токен выжил до перепроверки `analysis-filters.t0_survives_recheck`
- WHEN на перепроверке ликвидность на месте и токен не умер
- THEN токен поставлен в очередь полного анализа
### GIVEN мигрант на t=0 — токен умер до перепроверки `analysis-filters.t0_dead_before_recheck`
- WHEN на перепроверке пул пуст/токен мёртв
- THEN полный анализ не запускается, факт — в строку дайджеста
### GIVEN непустая очередь перепроверки — рестарт процесса `analysis-filters.t0_queue_survives_restart`
- WHEN процесс перезапущен
- THEN очередь восстановлена из персистентного хранилища

### Requirement: migrant-risk-profile
Система SHALL выводить honeypot/rugcheck как информационную строку вердикта (не hard-гейт для мигранта), SHALL вычислять концентрацию топ-10 холдеров и ставить флаг в вердикт при превышении конфиг-порога; hard DROP остаётся только для подтверждённого scam.
### GIVEN топ-10 холдеров выше конфиг-порога `analysis-filters.supply_concentration_flag`
- WHEN формируется вердикт
- THEN вердикт содержит явный флаг концентрации

### Requirement: social-weight
Система SHALL повышать приоритет в очереди анализа для токенов с живым X-аккаунтом и понижать при подтверждённой негативной тональности по конфигурируемой процедуре проверки; отсутствие аккаунта SHALL NOT блокировать анализ.
### GIVEN проверка соцсетей токена вернула подтверждённый негатив выше порога `analysis-filters.social_negative_priority`
- WHEN формируется очередь
- THEN приоритет токена понижен, флаг — в вердикт

### Requirement: outcome-loop
Система SHALL для каждого вердикта PASS/FLAG фиксировать исход через конфигурируемый интервал (старт 24ч: 2x / умер / флэт) в персистентном jsonl.
### GIVEN вердикт PASS выдан более 24ч назад — исход зафиксирован `analysis-filters.outcome_recorded_after_24h`
- WHEN выполняется замер исхода
- THEN строка `{token, verdict, ts, outcome}` дописана в jsonl

### Requirement: delivery-discipline
Система SHALL доставлять владельцу вывод ТОЛЬКО через накопительный дайджест (окно и порог записей — конфиг, старт 4ч/≥3) без немедленных сообщений; полный отчёт в дайджесте — только для вердиктов PASS/FLAG, прошедших verifier И каскад выживания t0; REJECT/SKIP/alert фаз (CABAL_EXPLOSION/KOL_ACTIVATION) — строками в дайджесте; MC > 5M — escalate-строкой. Пустое окно не порождает пустых сообщений.
### GIVEN 10 REJECT за интервал дайджеста — reject не шумит `analysis-filters.reject_batched_no_spam`
- WHEN время дайджеста
- THEN владельцу доставлена одна пачка, не 10 сообщений
### GIVEN KABAL-активность на токене зафиксирована — alert фаз не пульсирует `analysis-filters.kabal_alert_not_pulsing`
- WHEN формируется очередь доставки
- THEN alert записан в дайджест, немедленной доставки нет
### GIVEN за окно дайджеста записей нет — пустое окно `analysis-filters.empty_digest_window`
- WHEN время дайджеста
- THEN доставка не выполняется, сообщений нет

### Requirement: rate-cap
Система SHALL ограничивать полные AI-анализы конфиг-порогом в час с приоритизацией по конфигурируемой формуле (ликвидность + KABAL-эскалация вне очереди); переполнение SHALL попадать в персистентную очередь, не теряться. Очереди SHALL быть bounded (конфиг-лимит, старт 500); KABAL-эскалация SHALL иметь собственный потолок (конфиг, старт ≤5/час); все пределы exceeded → строка дайджеста.
### GIVEN порог анализов в час исчерпан — переполнение очереди `analysis-filters.rate_cap_queue_overflow`
- WHEN приходит новый кандидат
- THEN кандидат поставлен в очередь, анализ отложен, событие переживает рестарт
### GIVEN лимит KABAL-эскалаций в час исчерпан — KABAL-потолок `analysis-filters.kabal_cap_overflow`
- WHEN новая KABAL-эскалация
- THEN эскалация в общую очередь по обычной формуле приоритета, не в обход rate cap

### Requirement: safety-priority
Система SHALL применять operators SAFETY_GATES с приоритетом: подтверждённый scam (DROP) — на любом этапе машины состояний и перекрывает мягкие гейты и очередь; мягкие эвристики (phase=DEAD, rugcheck=high) — INCONCLUSIVE/понижение, не DROP.
### GIVEN токен в t0_pending/analysis_queue `analysis-filters.confirmed_scam_drop`
- WHEN honeypot=fail подтверждён на любом чеке
- THEN немедленный DROP → sink(reject), из очередей удалён
