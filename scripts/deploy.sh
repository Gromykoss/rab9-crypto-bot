#!/usr/bin/env bash
# RAB9 Crypto — Deploy Script
# Правила: бэкап → diff → линт → деплой → рестарт → smoke.
set -euo pipefail

DIR="/home/hermes-workspace/rab9"
BACKUP_TS=$(date +%m%d_%H%M)

red()  { echo -e "\033[31m✗ $*\033[0m"; }
green(){ echo -e "\033[32m✓ $*\033[0m"; }
info() { echo -e "\033[36m→ $*\033[0m"; }

info "=== RAB9 Deploy — $(date '+%Y-%m-%d %H:%M:%S') ==="

# 1. Проверка git
cd "$DIR"
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    red "Есть незакоммиченные изменения. Сначала git commit."
    exit 1
fi

# 2. Бэкап ключевых файлов
info "Бэкап..."
for f in rab9_bot.py msf_listener.py cabal_detector.py wallet_intel.py msf_http.py handlers.py; do
    [ -f "$f" ] && cp "$f" "$f.bak.$BACKUP_TS"
done
green "Бэкап готов"

# 3. Линт
info "Линт..."
for f in rab9_bot.py cabal_detector.py wallet_intel.py msf_listener.py; do
    python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null && \
        green "  $f OK" || red "  $f ОШИБКА"
done

# ── EVAL GATE (fleet standard eval-gates, 20.10.2026, kind: service) ──
info "Eval gate (kind: service)..."
if python3 "$HOME/.hermes/scripts/eval_runner.py" "$DIR/evals/deploy-gate/eval.yaml" > /dev/null 2>&1; then
    green "Eval gate PASS"
else
    red "Eval gate FAIL — вердикт: $DIR/evals/deploy-gate/.evals/latest.json"
    exit 2
fi

# 4. Рестарт сервиса
info "Рестарт rab9-crypto-hermes..."
sudo systemctl restart rab9-crypto-hermes
sleep 2
systemctl is-active --quiet rab9-crypto-hermes && green "Сервис active" || red "Сервис НЕ active!"

# 5. Health check
info "Health check..."
sleep 1
HEALTH=$(curl -s --max-time 5 http://localhost:8089/health 2>/dev/null)
echo "$HEALTH" | grep -q '"ok".*true' && green "Health OK: $HEALTH" || red "Health FAIL: $HEALTH"

# 6. Smoke
info "Smoke..."
bash ~/.hermes/scripts/rab9-smoke-monitor.sh && green "Smoke ПРОЙДЕН" || red "Smoke ПРОВАЛЕН"

green "=== Деплой завершён ==="
