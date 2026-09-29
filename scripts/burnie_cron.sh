#!/usr/bin/env bash
# Обёртка крона BURNIE: event-first.
# - hard_alert → печатаем полный отчёт (format_alert) → крон доставляет в Telegram
# - иначе    → пустой stdout → крон молчит (никакого LLM-посредника)
cd /home/hermes-workspace/rab9 || exit 1
OUT="$(python3 burnie_sentiment_tracker.py 2>&1)"
if [ "$OUT" != "[SILENT]" ]; then
  printf '%s\n' "$OUT"
fi
exit 0
