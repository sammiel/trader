# Check-in log

| Time (UTC) | Normal | Berkshire | Shadow | Trades since last | Issues |
|---|---|---|---|---|---|
| 2026-10-30 18:55 | 9969.37 (-0.31%) | 10000.22 (+0.00%, floor 10000.11) | 10000.00 | 0 (core BTC/SPY holds from 13:23 start still open) | none — loop run 41072224598 in progress, last tick 18:45, health ok; only 1 scheduled tick in 6h (cron drops, covered by loop) |
| 2026-10-31 00:58 | 10002.20 (+0.02%, SPY/QQQ at Fri close; bot logs NaN) | 10000.49 (+0.005%, floor 10000.24) | 10021.20 (+0.21%) | 2 opened (normal + shadow: index_pullback SPY & QQQ @ 19:30; Berkshire skipped, no_cushion) | BUG: since 00:00 UTC Sat, SPY/QQQ/IWM prices are NaN → equity, day_start, summary/kpi NaN (daily-loss halt & drawdown breaker can't fire while NaN). Not patched (can't reach Yahoo from check-in sandbox to test); dashboard refreshed with Fri-close prices. Loop 41121726797 in progress, last tick 00:45, health ok; 1 scheduled tick in 6h; 1 pages-build failure |
