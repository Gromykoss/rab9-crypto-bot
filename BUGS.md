# RAB9 — Known Bugs & Issues

> Last updated: 2026-07-18

## Active Bugs

None currently.

## Resolved

### 1. MSF Listener не под systemd
- **Severity:** Medium
- **Symptom:** При ребуте сервера msf_listener.py не запускается автоматически
- **Impact:** Сигналы из Мемов не доходят до RAB9 до ручного перезапуска
- **Fix:** Создан systemd unit `msf-listener.service`
- **Status:** ✅ Исправлен — msf-listener.service работает

### 2. BUGS.md не существовал
- **Severity:** Info
- **Fixed:** 2026-07-18 — создан этот файл

## Resolved

### 3. MSF Listener не запущен (P0 — 18.07.2026)
- **Symptom:** pgrep пусто, процесс упал при перезапуске gateway
- **Fix:** Перезапущен вручную, PID 971190
- **Status:** ✅ Работает, ловит сигналы

### 4. Hy3 API key истекает 20.07.2026
- **Symptom:** Hy3 free tier на OpenRouter заканчивается
- **Fix:** 17.07.2026 — переключено на Grok (xAI API) с DeepSeek fallback
- **Status:** ✅ RAB9_LLM=hy3 удалён из .env, Grok primary, DeepSeek fallback через OpenRouter

### 5. Birdeye API key suspended (17.07.2026)
- **Symptom:** API key suspended, enrichment failed
- **Fix:** Birdeye исключён из пайплайна, DexScreener — единственный источник обогащения
- **Status:** ✅ Код устойчив (safe_get глотает ошибки)

## Infra Notes

- CHRONOLOGY.md создан задним числом (с 07.07.2026)
- Бэкапы: `/home/hermes-workspace/rab9/backups/`
