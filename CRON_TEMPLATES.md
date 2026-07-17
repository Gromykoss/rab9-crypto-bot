# RAB9 Cron Templates

Inspired by HOODRADAR's cron patterns. Add these to Hermes cron with `deliver`: `telegram:-1003979753733`.

## Smart wallet scan (hourly)
```
cronjob create \
  --schedule "0 * * * *" \
  --deliver "telegram:-1003979753733" \
  --prompt "Run cd /home/hermes-workspace/rab9 && python3 wallet_intel.py --scan-recent --top 10. If no new high-PnL wallets found, output nothing (wakeAgent pattern). If found, format as short Telegram alert."
```

## Dip detection (2x daily)
```
cronjob create \
  --schedule "0 7,15 * * *" \
  --deliver "telegram:-1003979753733" \
  --prompt "Run cd /home/hermes-workspace/rab9 && python3 scanner.py --dip --threshold 20. If no dips above threshold, stay silent. If found, brief with CA, name, drop%, MC."
```

## Cabal alert (every 30 min)
```
cronjob create \
  --schedule "*/30 * * * *" \
  --deliver "telegram:-1003979753733" \
  --prompt "Run cd /home/hermes-workspace/rab9 && python3 cabal_detector.py --recent --minutes 30. Alert immediately on CABAL_EXPLOSION or KOL_ACTIVATION. Stay silent if clean."
```
