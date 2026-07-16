# RAB9 BUGS.md — Known Issues & Technical Debt

## Active Issues

### 1. MSF Listener — ранее без systemd управлялся как сырой процесс
**Severity:** Fixed (now remediated)
**Status:** ✅ Resolved — now managed as `msf-listener.service` (systemd --user)
**Details:** The MSF Listener (msf_listener.py) was running as a raw shell script with no service supervision, restart policy, or logging — just a bare Python PID. Added systemd user unit at `~/.config/systemd/user/msf-listener.service` with restart=always and log output to `/tmp/msf-listener.log`.

### 2. Hy3 free tier → миграция на Grok завершена
**Severity:** Critical — resolved
**Status:** ✅ Closed 16.07.2026
**Details:** Hy3 free tier закрылся 15.07. RAB9 мигрирован на Grok (xAI API) как основной LLM. Fallback: DeepSeek через OpenRouter. Hy3 больше не используется.

### 3. Signal pipeline v2 — never tested with live signal from Memes
**Severity:** Medium — untested integration path
**Status:** ⏳ Staging / needs E2E test
**Details:** The Signal pipeline v2 was developed but has never been tested end-to-end with a live signal from the Memes group. Unit testing was done, but the full integration path (Telegram → MSF Listener → RAB9 → signal dispatch) has not been validated in production. Risk: silent failures on first live trigger.

### 4. memory-engine MCP crashes without uv
**Severity:** Medium — crash on startup if uv missing
**Status:** ⏳ Needs dependency hardening
**Details:** The memory-engine MCP server crashes on launch when `uv` (the Python package/project manager) is not installed in the environment. This is a fragile dependency — `uv` is not part of the standard system image and must be present for memory operations to work. Consider fallback to `pip` or bundling `uv` with the project.

---

## Legend

| Status | Meaning |
|--------|---------|
| 🔴 Active | Bug is currently affecting production |
| ⏳ Monitoring / Staging | Known risk, not yet triggered or not fully validated |
| ✅ Resolved | Fix applied |
| 📅 Scheduled | Fix is planned with a timeline |
