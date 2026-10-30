# Backtest report

Generated 2026-10-30 13:00:00+00:00. Costs per side: crypto fee 0.10% + slippage 0.08%; ETF slippage 0.03%.

| Strategy | Trades | Win % | Profit factor | Avg R | Net return | CAGR | Max DD | OOS trades | OOS PF | @0.4% fee | Gate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| trend | 416 | 32.5 | 1.08 | 0.078 | 12.84% | 3.07% | -21.89% | 167 | 0.86 | -22.04% | FAIL: profit factor 1.08 < 1.15; out-of-sample profit factor 0.86 < 1.0 |
| bounce | 367 | 50.4 | 0.52 | -0.134 | -18.35% | -4.95% | -18.88% | 159 | 0.45 | -45.53% | FAIL: profit factor 0.52 < 1.15; out-of-sample profit factor 0.45 < 1.0 |
| bounce_no_trend_filter | 1942 | 47.8 | 0.53 | -0.144 | -72.21% | -27.43% | -72.72% | 929 | 0.55 | -96.71% | FAIL: profit factor 0.53 < 1.15; out-of-sample profit factor 0.55 < 1.0; max drawdown -72.72% |
| index_pullback | 506 | 70.0 | 1.49 | 0.037 | 33.94% | 1.35% | -10.68% | 176 | 1.78 | n/a | PASS |

Buy & hold, crypto equal-weight: {'net_return_pct': 91.54, 'oos_return_pct': -44.06, 'max_drawdown_pct': -67.26}  
Buy & hold, index ETFs equal-weight (2005+): {'net_return_pct': 1124.21, 'oos_return_pct': 163.54, 'max_drawdown_pct': -55.04}


Enabled for paper trading: `{"trend": false, "bounce": false, "index_pullback": true, "source": "backtest 2026-10-30 13:00:00+00:00"}`
